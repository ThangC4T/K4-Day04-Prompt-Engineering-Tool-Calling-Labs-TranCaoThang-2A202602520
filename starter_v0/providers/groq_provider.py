"""Groq's OpenAI-compatible API, with isolated credentials and configuration."""
from __future__ import annotations

import os
from providers.openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    def __init__(self) -> None:
        super().__init__(api_key_env="GROQ_API_KEY",
                         base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                         default_model="qwen/qwen3.6-27b", settings_prefix="GROQ")
        self.request_options = self.options_for_model(self.default_model)

    def options_for_model(self, model: str) -> dict:
        options = {"max_completion_tokens": int(os.getenv("GROQ_MAX_TOKENS", "512"))}
        # Let the local dispatcher observe and reject undeclared model calls
        # instead of Groq converting them into opaque HTTP 400 responses.
        # This never disables tool_runtime's allowlist, schema or write gate.
        if os.getenv("GROQ_LOCAL_TOOL_VALIDATION", "").lower() in {"1", "true", "yes"}:
            options["extra_body"] = {"disable_tool_validation": True}
        effort = os.getenv("GROQ_REASONING_EFFORT")
        if effort:
            options["reasoning_effort"] = effort
        elif model.startswith("qwen/"):
            options["reasoning_effort"] = "none"
        elif model.startswith("openai/gpt-oss"):
            options["reasoning_effort"] = "low"
        return options

    def complete(self, messages, tools=None, *, model=None, temperature=0.0, tool_choice=None):
        # Resolve options against the actual requested model, including CLI/UI
        # overrides. GPT-OSS does not accept Qwen's reasoning_effort='none'.
        self.request_options = self.options_for_model(model or self.default_model)
        return super().complete(messages, tools, model=model, temperature=temperature,
                                tool_choice=tool_choice)
