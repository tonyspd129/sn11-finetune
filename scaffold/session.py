"""Session = the full transcript the harness exports (no `submit`; export-on-end)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Session:
    task: str
    model: str
    messages: list[dict[str, Any]] = field(default_factory=list)   # OpenAI-format transcript
    tool_log: list[dict[str, Any]] = field(default_factory=list)   # structured per-call records
    llm_calls: list[dict[str, Any]] = field(default_factory=list)  # raw wire per turn: {turn, request, response}
    stop_reason: str = "running"                                   # final_answer|max_turns|max_tokens|error
    turns: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def export(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
