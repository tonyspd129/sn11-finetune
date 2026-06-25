"""OpenAI-compatible chat client. Default backend = OpenRouter; swap by changing
base_url/api_key/model (e.g. to a local vLLM endpoint) with no other changes."""
from __future__ import annotations

import os
from typing import Any


class LLMClient:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        extra_body: dict[str, Any] | None = None,
    ):
        self.model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.6-35b-a3b")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        self.api_key = (api_key or os.environ.get("LLM_API_KEY")
                        or os.environ.get("OPENROUTER_API_KEY", ""))
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_body = extra_body or {}
        try:
            from openai import OpenAI   # imported lazily: only needed to actually call a model
        except ImportError as e:  # pragma: no cover
            raise ImportError("base_harness needs the `openai` package to call a model: "
                              "pip install openai") from e
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None):
        """Returns the raw OpenAI response; caller reads .choices[0].message and .usage."""
        kwargs: dict[str, Any] = dict(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        return self.client.chat.completions.create(**kwargs)
