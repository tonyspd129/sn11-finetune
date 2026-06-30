"""OpenAI-compatible chat client. Default backend = OpenRouter; swap by changing
base_url/api_key/model (e.g. to a local vLLM endpoint) with no other changes."""
from __future__ import annotations

import json
import os
from typing import Any


class LLMClient:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        self.model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.6-35b-a3b")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        self.api_key = (api_key or os.environ.get("LLM_API_KEY")
                        or os.environ.get("OPENROUTER_API_KEY", ""))
        # sampling: explicit arg > env (validator-injected) > default (greedy / 4096)
        self.temperature = (temperature if temperature is not None
                            else float((os.environ.get("LLM_TEMPERATURE") or "0.0").strip()))
        self.max_tokens = (max_tokens if max_tokens is not None
                           else int((os.environ.get("LLM_MAX_TOKENS") or "4096").strip()))
        self.extra_body = extra_body or {}
        self.last_request: dict[str, Any] | None = None   # exact payload of the most recent generate()
        try:
            from openai import OpenAI   # imported lazily: only needed to actually call a model
        except ImportError as e:  # pragma: no cover
            raise ImportError("scaffold needs the `openai` package to call a model: "
                              "pip install openai") from e
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None):
        """Returns the raw OpenAI response; caller reads .choices[0].message and .usage.
        Also stashes a JSON-safe snapshot of the exact request in `self.last_request`."""
        kwargs: dict[str, Any] = dict(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        # snapshot NOW (messages is the live, growing list) and decouple via a JSON round-trip
        self.last_request = json.loads(json.dumps(kwargs, default=str))
        return self.client.chat.completions.create(**kwargs)
