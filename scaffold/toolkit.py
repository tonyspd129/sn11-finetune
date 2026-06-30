"""Tool framework: the contract + registry + workspace shell + shared helpers.
The actual tools live as plugins under `scaffold/tools/**/tool.py` (each exports
`metadata` + `run`) and are discovered by `loader.py`. Miners add their own tree."""
from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --------------------------------------------------------------------------- #
# Result + execution context
# --------------------------------------------------------------------------- #
@dataclass
class ToolResult:
    output: str
    is_error: bool = False
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class Shell:
    """Workspace shell. Stateless per call but PERSISTS cwd via a trailing marker, so
    `cd` works across execute_command calls. Combines stdout+stderr (stderr merged)."""

    def __init__(self, cwd: str = "/workspace"):
        os.makedirs(cwd, exist_ok=True)
        self.cwd = os.path.abspath(cwd)

    def run(self, command: str, timeout: int = 120) -> tuple[str, int, bool]:
        marker = f"__CWD_{uuid.uuid4().hex}__"
        wrapped = (
            f"cd {shlex.quote(self.cwd)} || exit 1\n"
            f"{command}\n"
            f"rc=$?\n"
            f"printf '\\n{marker}%s\\n' \"$(pwd)\"\n"
            f"exit $rc\n"
        )
        timed_out = False
        try:
            p = subprocess.run(
                ["bash", "-c", wrapped],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # merge so the marker is truly last
                text=True, timeout=timeout, start_new_session=True,
            )
            out, code = (p.stdout or ""), p.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") if isinstance(e.stdout, str) else ""
            code, timed_out = -1, True
        if marker in out:
            idx = out.rfind(marker)
            tail = out[idx + len(marker):].strip().splitlines()
            if tail and tail[0]:
                self.cwd = tail[0]
            out = out[:idx].rstrip("\n")
        if timed_out:
            out += f"\n... [timed out after {timeout}s] ..."
        return out, code, timed_out

    def close(self) -> None:
        pass


@dataclass
class RunContext:
    shell: Shell
    workdir: str
    config: dict[str, Any] = field(default_factory=dict)  # validator-owned operator policy (miner-unforgeable); read via ctx.config
    skill_lookup: Optional[Callable[[str], Optional[str]]] = None  # name -> skill body (set by Harness)


# --------------------------------------------------------------------------- #
# Tool contract, function-adapter, registry
# --------------------------------------------------------------------------- #
class Tool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    @abstractmethod
    def run(self, args: dict[str, Any], ctx: RunContext) -> ToolResult: ...

    def spec(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class FunctionTool(Tool):
    """Wraps a plugin's exported `metadata` dict + `run(args, ctx)` function into a Tool.
    This is what every `tool.py` in the tree becomes."""

    def __init__(self, metadata: dict[str, Any], run_fn: Callable[[dict, RunContext], ToolResult]):
        self.name = metadata["name"]
        self.description = metadata.get("description", "")
        self.parameters = metadata.get("parameters", {"type": "object", "properties": {}})
        self.version = metadata.get("version")
        self._run = run_fn

    def run(self, args, ctx):
        return self._run(args, ctx)


class ToolManager:
    """Holds the discovered tools (the tool-side analog of SkillManager). Constructed from a
    list of Tools; same name => later one wins (override)."""

    def __init__(self, tools: Optional[list[Tool]] = None) -> None:
        self.tools = list(tools or [])
        self._by_name: dict[str, Tool] = {t.name: t for t in self.tools}

    def get(self, name: str) -> Optional[Tool]:
        return self._by_name.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._by_name.values()]

    def names(self) -> list[str]:
        return list(self._by_name)


# --------------------------------------------------------------------------- #
# Public helpers (tool authors import these)
# --------------------------------------------------------------------------- #
def truncate(text: str, max_chars: int = 6000, max_lines: int = 200) -> tuple[str, bool]:
    truncated = False
    lines = text.splitlines()
    if len(lines) > max_lines:
        half = max_lines // 2
        lines = lines[:half] + [f"... [{len(lines) - max_lines} lines omitted] ..."] + lines[-half:]
        truncated = True
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [truncated] ..."
        truncated = True
    return out, truncated


def resolve_path(ctx: RunContext, path: str) -> str:
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(ctx.shell.cwd, path)
