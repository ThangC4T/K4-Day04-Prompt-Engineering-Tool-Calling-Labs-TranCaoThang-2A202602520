from __future__ import annotations

import json
import os
from typing import Any

from providers.base import ModelResponse, ToolCall


class OpenAIProvider:
    """OpenAI Chat Completions provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.deepseek.com",
        default_model: str = "deepseek-flash",
    ) -> None:
        self.api_key_env = api_key_env
        # Allow OpenAI-compatible endpoints (e.g. DeepSeek) via env without
        # changing call sites. Supports both OPENAI_* and DEEPSEEK_* names.
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or None
        self.default_model = os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL") or default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install openai") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            # Fallback for OpenAI-compatible setup using DeepSeek key name.
            api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env} (or DEEPSEEK_API_KEY)")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments or "{}")
            calls.append(ToolCall(name=call.function.name, args=args))
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp)
