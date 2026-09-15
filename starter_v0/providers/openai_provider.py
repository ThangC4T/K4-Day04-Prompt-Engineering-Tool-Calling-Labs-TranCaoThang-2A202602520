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
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
        settings_prefix: str = "OPENAI",
    ) -> None:
        self.api_key_env = api_key_env
        # Credentials, endpoint and model must stay in the same namespace.
        # To use DeepSeek explicitly, set OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL.
        self.base_url = base_url or os.getenv(f"{settings_prefix}_BASE_URL") or None
        self.default_model = os.getenv(f"{settings_prefix}_MODEL") or default_model

    def complete(
        self,
        messages: list[dict[str, Any]],
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
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=45.0, max_retries=1)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [{k: v for k, v in message.items() if k != "provider_metadata"} for message in messages],
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        kwargs.update(getattr(self, "request_options", {}))

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for call in msg.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Provider returned invalid JSON tool arguments") from exc
            calls.append(ToolCall(name=call.function.name, args=args, id=getattr(call, "id", None)))
        reasoning = getattr(msg, "reasoning_content", None)
        return ModelResponse(text=msg.content, tool_calls=calls, raw=resp,
                             assistant_metadata={"reasoning_content": reasoning} if reasoning is not None else {})
