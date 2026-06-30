"""The pure harness: manages the conversation between the LLM and the tools.
No `submit` — it runs think->act->observe until a final answer (no tool call) or a budget
limit, then returns the full Session for export. Verification lives OUTSIDE the harness.

The harness loads its tools, skills, system prompt, compaction, and prompt builder from THIS
package's own files — the same way it imports `context` / `llm` / `loader`:
    ./tools/**         (each tool: metadata.json + tool.py)
    ./skills/**        (SKILL.md + system.md)
    ./compaction.py    (the compaction module)
    ./prompt.py        (the system-prompt builder)
To customize, edit those files (a miner ships their own copy of the package). A present-but-
broken file RAISES (fail fast).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .compaction import make_compaction
from .context import ContextManager
from .llm import LLMClient
from .loader import discover_skills, discover_tools, load_system_prompt
from .prompt import build_system_prompt
from .promptkit import PromptContext
from .session import Session
from .skill import SkillManager
from .toolkit import RunContext, Shell, ToolManager

_PKG = Path(__file__).parent          # tools/, skills/, compaction.py, prompt.py live here


def _env_int(name: str) -> int | None:
    v = (os.environ.get(name) or "").strip()
    return int(v) if v else None


def _env_float(name: str) -> float | None:
    v = (os.environ.get(name) or "").strip()
    return float(v) if v else None


class Harness:
    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        workdir: str = "/workspace",
        max_turns: int | None = None,
        max_tokens_budget: int | None = None,
        wall_clock_s: float | None = None,
        config: dict | None = None,
    ):
        self.llm = llm or LLMClient()
        self.tools = ToolManager(discover_tools(str(_PKG / "tools")))   # broken plugin RAISES
        self.skills = SkillManager(discover_skills(str(_PKG / "skills")))
        self.system_prompt = load_system_prompt(str(_PKG / "skills")) or "You are an autonomous terminal agent."
        self.compaction = make_compaction()                            # imported from .compaction
        self.prompt_builder = build_system_prompt                       # imported from .prompt
        self.workdir = workdir
        # budgets: explicit arg > env (validator-injected) > hardcoded default
        self.max_turns = max_turns if max_turns is not None else (_env_int("MAX_TURNS") or 40)
        self.max_tokens_budget = (max_tokens_budget if max_tokens_budget is not None
                                  else _env_int("MAX_TOKENS_BUDGET"))   # None = unlimited
        self.wall_clock_s = (wall_clock_s if wall_clock_s is not None
                             else _env_float("WALL_CLOCK_S"))           # None = unlimited
        self.config = config or {}

    def _build_system(self, task: str) -> str:
        """Assemble messages[0] via the (miner or default) prompt builder, ONCE per run.
        STRICT: a builder that raises or returns a non-string propagates and terminates."""
        pctx = PromptContext(
            task=task, base_system=self.system_prompt, skills=self.skills,
            tool_specs=self.tools.specs(),
        )
        out = self.prompt_builder(pctx)
        if not isinstance(out, str) or not out.strip():
            raise ValueError("prompt builder returned an empty/non-string system prompt")
        return out

    def run(self, task: str) -> Session:
        shell = Shell(cwd=self.workdir)
        ctx = RunContext(shell=shell, workdir=self.workdir, config=self.config,
                         skill_lookup=self.skills.get_body)
        system = self._build_system(task)           # prompt builder owns prose+skills assembly
        cm = ContextManager(system_prompt=system, compaction=self.compaction)
        cm.add_user(task)
        session = Session(task=task, model=self.llm.model)
        t0 = time.time()
        try:
            for turn in range(1, self.max_turns + 1):
                session.turns = turn
                resp = self.llm.generate(cm.build(), self.tools.specs())
                msg = resp.choices[0].message
                usage = getattr(resp, "usage", None)
                if usage:
                    session.usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    session.usage["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0

                # raw wire capture: exact request payload + full response dump (finish_reason,
                # raw content, structured tool_calls or their absence) — survives our parsing.
                try:
                    raw_response = resp.model_dump()
                except Exception:
                    raw_response = {"_note": "response.model_dump() unavailable",
                                    "content": getattr(msg, "content", None)}
                session.llm_calls.append({"turn": turn,
                                          "request": getattr(self.llm, "last_request", None),
                                          "response": raw_response})

                assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ]
                cm.add_assistant(assistant_msg)

                if not tool_calls:
                    session.stop_reason = "final_answer"
                    break

                for tc in tool_calls:                      # sequential: observe-then-act
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    tool = self.tools.get(name)
                    if tool is None:
                        result, is_error = f"error: unknown tool '{name}'", True
                    else:
                        try:
                            r = tool.run(args, ctx)
                            result, is_error = r.output, r.is_error
                        except Exception as e:
                            result, is_error = f"error: tool '{name}' raised: {e}", True
                    cm.add_tool_result(tc.id, name, result)
                    session.tool_log.append(
                        {"turn": turn, "name": name, "args": args, "result": result, "is_error": is_error}
                    )

                cm.maybe_compact()

                tok = session.usage["prompt_tokens"] + session.usage["completion_tokens"]
                if self.max_tokens_budget and tok > self.max_tokens_budget:
                    session.stop_reason = "max_tokens"
                    break
                if self.wall_clock_s and (time.time() - t0) > self.wall_clock_s:
                    session.stop_reason = "timeout"
                    break
            else:
                session.stop_reason = "max_turns"
        except Exception as e:
            session.stop_reason = "error"
            session.error = repr(e)
        finally:
            shell.close()
            session.messages = cm.messages
            session.ended_at = time.time()
        return session
