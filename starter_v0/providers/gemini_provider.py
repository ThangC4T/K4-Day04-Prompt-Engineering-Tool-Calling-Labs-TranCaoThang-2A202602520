from __future__ import annotations

import json
import os
from typing import Any

from providers.base import ModelResponse, ToolCall


def _to_gemini_declarations(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for item in tools or []:
        function = item.get("function", item)
        declarations.append({
            "name": function["name"],
            "description": function.get("description", ""),
            "parameters_json_schema": function.get("parameters", {"type": "object", "properties": {}}),
        })
    return declarations


def _to_gemini_contents(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    call_names: dict[str, str] = {}
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            native_parts = msg.get("provider_metadata", {}).get("gemini_parts")
            parts: list[dict[str, Any]] = [{"text": content}] if content else []
            for call in msg.get("tool_calls", []):
                name = call["function"]["name"]
                call_names[call["id"]] = name
                parts.append({"function_call": {"name": name, "args": json.loads(call["function"]["arguments"])}})
            if parts:
                contents.append({"role": "model", "parts": native_parts or parts})
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "tool":
            name = call_names[msg["tool_call_id"]]
            part = {"function_response": {"name": name, "response": json.loads(content)}}
            if contents and contents[-1]["role"] == "user":
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    return ("\n\n".join(system_parts) if system_parts else None), contents


def _part_text(part: Any) -> str | None:
    if hasattr(part, "text"):
        return getattr(part, "text")
    if isinstance(part, dict):
        return part.get("text")
    return None


def _part_function_call(part: Any) -> Any | None:
    if hasattr(part, "function_call"):
        return getattr(part, "function_call")
    if isinstance(part, dict):
        return part.get("function_call")
    return None


def _function_call_name(call: Any) -> str | None:
    if hasattr(call, "name"):
        return getattr(call, "name")
    if isinstance(call, dict):
        return call.get("name")
    return None


def _function_call_args(call: Any) -> dict[str, Any]:
    if hasattr(call, "args"):
        return dict(getattr(call, "args") or {})
    if isinstance(call, dict):
        return dict(call.get("args") or {})
    return {}


class GeminiProvider:
    """Google Gemini API provider with normalized tool_calls output."""

    def __init__(
        self,
        *,
        api_key_env: str = "GEMINI_API_KEY",
        default_model: str = "gemini-3.5-flash",
    ) -> None:
        self.api_key_env = api_key_env
        self.default_model = os.getenv("GEMINI_MODEL") or default_model

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
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Install live provider dependency first: pip install google-genai") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.api_key_env}")

        system_instruction, contents = _to_gemini_contents(messages)
        declarations = _to_gemini_declarations(tools)
        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if declarations:
            config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]
            config_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
            config_kwargs["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                mode="ANY" if tool_choice == "required" else "AUTO"))

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model or self.default_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text_parts: list[str] = []
        calls: list[ToolCall] = []

        def append_call(function_call: Any) -> None:
            name = _function_call_name(function_call)
            if name:
                calls.append(ToolCall(name=name, args=_function_call_args(function_call)))

        candidates = getattr(resp, "candidates", []) or []
        native_parts = []
        for candidate in candidates[:1]:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                if hasattr(part, "model_dump"):
                    native_parts.append(part.model_dump(exclude_none=True))
                text = _part_text(part)
                if text and not getattr(part, "thought", False):
                    text_parts.append(text)
                function_call = _part_function_call(part)
                if function_call:
                    append_call(function_call)

        # Some SDK versions expose function calls directly on the response.
        if not calls:
            for function_call in getattr(resp, "function_calls", []) or []:
                append_call(function_call)

        deduped_calls: list[ToolCall] = []
        seen: set[tuple[str, str]] = set()
        for call in calls:
            key = (call.name, json.dumps(call.args, ensure_ascii=False, sort_keys=True))
            if key not in seen:
                seen.add(key)
                deduped_calls.append(call)

        return ModelResponse(text="\n".join(part for part in text_parts if part) or None,
                             tool_calls=calls, raw=resp, assistant_metadata={"gemini_parts": native_parts})
