"""Prompt-assembly framework: the read-only context handed to a system-prompt builder.

A prompt builder is `build(ctx: PromptContext) -> str` — it turns the available material
(base prose, skills, tools, the task) into the final system message. The DEFAULT builder lives
in `prompt.py`; override it by passing `prompt=<your prompt.py>` to the Harness.

The builder is called ONCE at run start (the system message must stay stable across turns for
KV-cache efficiency), and it only RETURNS the system-prompt string — it does not control tool
schemas (those ship via `tools=`), the loop, or the filesystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .skill import SkillManager


@dataclass(frozen=True)
class PromptContext:
    """Everything a prompt builder may read. Read-only."""
    task: str                                  # the task (enables task-aware assembly)
    base_system: str                           # miner system.md / explicit arg / core baseline
    skills: SkillManager                       # .skills list + render_always_on() / index() / get_body()
    tool_specs: list[dict[str, Any]] = field(default_factory=list)   # tool schemas (also sent via tools=)
    config: dict[str, Any] = field(default_factory=dict)
