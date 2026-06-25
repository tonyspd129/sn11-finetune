"""Skill framework with progressive disclosure.

The model becomes aware of skills via a one-line INDEX in the system prompt (name +
description), and pulls the full body on demand with the `load_skill` tool. Skills flagged
`always_on` are injected in full (used for universal guidance like 'work-methodically').

Skills live as `base_harness/skills/**/SKILL.md` (frontmatter + body), discovered by loader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Skill:
    name: str
    content: str                                         # the body (loaded on demand)
    description: str = ""                                 # one-liner shown in the index
    triggers: Optional[list[str]] = field(default=None)  # optional keywords (for retrieval/pre-filtering)
    always_on: bool = False                               # if True, body is always injected


class SkillManager:
    def __init__(self, skills: Optional[list[Skill]] = None):
        self.skills = skills or []
        self._by_name = {s.name: s for s in self.skills}

    # ---- lookup (used by the load_skill tool) --------------------------- #
    def get(self, name: str) -> Optional[Skill]:
        return self._by_name.get(name)

    def get_body(self, name: str) -> Optional[str]:
        s = self._by_name.get(name)
        return s.content if s else None

    # ---- prompt assembly ----------------------------------------------- #
    def always_on_skills(self) -> list[Skill]:
        return [s for s in self.skills if s.always_on]

    def render_always_on(self) -> str:
        ao = self.always_on_skills()
        if not ao:
            return ""
        return "\n\n# Skills (always apply)\n" + "\n\n".join(f"## {s.name}\n{s.content}" for s in ao)

    def index(self) -> str:
        """One-line catalog of the LOAD-ABLE skills (always-on ones are injected in full)."""
        listed = [s for s in self.skills if not s.always_on]
        if not listed:
            return ""
        lines = [f"- {s.name}: {s.description or _first_line(s.content)}" for s in listed]
        return ("# Available skills\n"
                "Call load_skill(name) to read one in full before relying on it.\n"
                + "\n".join(lines))

    # ---- optional trigger-based pre-filtering --------------------------- #
    def relevant(self, task: str) -> list[Skill]:
        t = task.lower()
        return [s for s in self.skills if not s.triggers or any(k.lower() in t for k in s.triggers)]


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        ln = ln.strip()
        if ln:
            return ln[:100]
    return ""
