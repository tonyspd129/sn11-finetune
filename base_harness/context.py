"""Context management: holds the message list and applies a (pluggable) compaction
strategy between turns. Default compaction is a NO-OP (empty), as specified."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Compaction(ABC):
    """Strategy for shrinking the conversation when it grows. Miners override this."""
    @abstractmethod
    def compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class NoOpCompaction(Compaction):
    """Default: do nothing (empty compaction)."""
    def compact(self, messages):
        return messages


class ContextManager:
    def __init__(self, system_prompt: str, compaction: Compaction | None = None):
        self.compaction = compaction or NoOpCompaction()
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": content}
        )

    def maybe_compact(self) -> None:
        # System message is always preserved; compaction sees the full list and returns a new one.
        self.messages = self.compaction.compact(self.messages)

    def build(self) -> list[dict[str, Any]]:
        return self.messages
