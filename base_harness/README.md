# base_harness

A **pure agent harness**: it manages the multi-turn conversation between an
OpenAI-compatible LLM and a set of tools, and **exports the full session** at the end.
There is **no `submit`** — the loop ends when the model returns a final answer (no tool
call) or a budget limit is hit. **Verification/scoring lives outside the harness.**

```
LLM (local vLLM / any OpenAI-compatible)  ⇄  Harness loop  ⇄  Tools (run in the container)
                                              │
                                              └── exports Session (full transcript)
```

This is the base every miner extends. Competition context: [../sn11-finetune.md](../sn11-finetune.md)
(eval lifecycle), [../miner.md](../miner.md) (how to compete), and [../validator.md](../validator.md)
(how it's evaluated & audited).

## Install / run
```bash
pip install openai
export OPENROUTER_API_KEY=sk-...            # or LLM_API_KEY
export LLM_MODEL=qwen/qwen3.6-35b-a3b       # default
export LLM_BASE_URL=https://openrouter.ai/api/v1   # the evaluator injects a local vLLM endpoint
python -m base_harness.example_miner
```

Minimal use:
```python
from base_harness import Harness
session = Harness(workdir="/workspace", max_turns=40).run("Fix /app so `make` succeeds.")
session.export("session.json")
```

## What the harness loads

The harness loads everything from **this package's own files** — there are **no override
arguments**. You build it with `Harness()`:

| Surface | Where it's loaded from |
|---|---|
| **tools** | `tools/<name>/{metadata.json, tool.py}` (each tool = JSON schema + `run`) |
| **skills** | `skills/**/SKILL.md` |
| **system prompt** | `skills/system.md` |
| **compaction** | `compaction.py` |
| **prompt builder** | `prompt.py` |

```python
from base_harness import Harness
session = Harness(workdir="/workspace").run("…task…")
```

**To customize, EDIT those files** in your copy of the package (a miner ships their own
`base_harness`). There's nothing to wire up — the harness always loads its own files, the same
way it imports `context` / `llm` / `loader`. `examples/miner_plugins/` holds reference versions
to copy into the package locations above.

**Fail fast.** A file that is present but broken (won't import, invalid JSON, missing the
expected export) **raises** at construction — it does not silently fall back. Deliberate for the
competition: a broken submission fails loudly instead of running on defaults and reporting a
misleading score.

### The prompt builder
`prompt.py` decides *how* the system prompt (prose) and *skills* are assembled into
`messages[0]` — ordering, markdown-vs-XML framing, task-aware skill inlining. It runs **once at
run start** (so the system message stays KV-cache-stable) and only returns the prompt string;
it does not touch tool schemas, the loop, or the filesystem. It exposes
`build_system_prompt(ctx)` / `make_prompt_builder()` / `build(ctx)`, where `ctx` is a
`PromptContext` (`task`, `base_system`, `skills`, `tool_specs`, `config`). See
[example_miner.py](example_miner.py) and [examples/miner_plugins/](examples/miner_plugins/).

## The tool contract
Each tool is a directory with a **`metadata.json`** (the schema) + a **`tool.py`** (the code).
Keeping the schema as data lets it be read/audited without executing the tool.

`tools/<name>/metadata.json`:
```json
{
  "name": "my_tool",
  "description": "what it does",
  "parameters": {"type": "object", "properties": {}},
  "version": "1.0"
}
```
`tools/<name>/tool.py`:
```python
from base_harness.toolkit import ToolResult

def run(args: dict, ctx) -> ToolResult:
    out, _, _ = ctx.shell.run("...")        # cwd persists across calls
    return ToolResult(output=out)
```
Discovery globs `**/tool.py`, reads the sibling `metadata.json`, and imports `run`. A tool.py
without a `metadata.json` (or invalid JSON, or no `run`) RAISES. `RunContext` gives the tool the
workspace `shell`, `workdir`, `config` (operator wiring: `web_allowlist`, …), and `skill_lookup`.
`ToolResult` is structured + bounded (`output`, `is_error`, `truncated`, `metadata`).

## Skills & progressive disclosure
The model sees a one-line **index** of loadable skills in the system prompt and pulls a full
body on demand via the `load_skill` tool. Skills flagged `always_on: true` in frontmatter are
injected in full every turn. Frontmatter keys: `name`, `description`, `triggers`, `always_on`.

## Notes / deliberate boundaries
- **Sequential tool execution** (observe-then-act) — terminal work needs the result before the next step.
- **`web_fetch`** is allowlist-gated (`config["web_allowlist"]`) and blocks internal/loopback/metadata IPs.
  ⚠️ *Defense in depth only* — real egress control must be enforced at the **network layer**,
  because the agent can bypass any tool via `execute_command`.
- **`execute_command` runs inside this harness's container** — run the harness in a hardened sandbox.
- **The LLM endpoint is operator-controlled.** In the competition the evaluator serves the
  miner's weights locally and injects `base_url`/`api_key`; miner values are ignored.
- The exported `Session.messages` is OpenAI-format and *is* your trajectory (for scoring or training).

## Files
| File | Purpose |
|---|---|
| `harness.py` | the loop (`Harness.run`); loads tools/skills/system/compaction/prompt from this package |
| `llm.py` | OpenAI-compatible client (OpenRouter default; lazy `openai` import) |
| `loader.py` | discovery for the dir surfaces: `discover_tools` / `discover_skills` / `load_system_prompt` |
| `toolkit.py` | `Tool` contract, `ToolManager`, `Shell`, security helpers (`is_internal_host`, `GuardedRedirect`) |
| `context.py` | `ContextManager` + `Compaction` ABC (+ `NoOpCompaction`) |
| `promptkit.py` | `PromptContext` (the read-only input handed to a prompt builder) |
| `compaction.py` | **default** compaction (no-op); harness imports `make_compaction` — edit to customize |
| `prompt.py` | **default** prompt builder; harness imports `build_system_prompt` — edit to customize |
| `skill.py` | `Skill` + `SkillManager` (index / always-on / `load_skill` lookup) |
| `session.py` | `Session` — full transcript export |
| `tools/` | the 7 default tool plugins |
| `skills/` | default skills + `system.md` (the baseline prompt) |
| `example_miner.py`, `examples/` | build/inspect demo; `examples/` = reference files to copy in |
