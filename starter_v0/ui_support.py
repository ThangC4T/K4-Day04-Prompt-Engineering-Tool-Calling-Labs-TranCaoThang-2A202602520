"""Conversation state and safe transcript persistence for the Streamlit UI."""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from versioning import artifact_version_dict, build_artifact_version
from privacy import redact_sensitive


PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(value: Any) -> Any:
    """Remove configured API secrets from messages, diagnostics and downloads."""
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    result = value
    for key, secret in os.environ.items():
        if (key.endswith("_API_KEY") or key in {"OPENAI_API_KEY", "TAVILY_API_KEY"}) and secret:
            result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", result)
    result = re.sub(r"\bAIza[A-Za-z0-9_-]{20,}\b", "[REDACTED]", result)
    return redact_sensitive(result)


def available_versions(root: Path) -> dict[str, tuple[Path, Path]]:
    versions = {}
    for version in ("v0", "v1", "v2", "v3"):
        folder = root / "artifacts" / "versions" / version
        paths = (folder / "system_prompt.md", folder / "tools.yaml")
        if all(path.is_file() for path in paths):
            versions[version] = paths
    versions["working"] = (root / "artifacts" / "system_prompt.md", root / "artifacts" / "tools.yaml")
    return versions


def default_provider() -> str:
    return next((name for name, key in PROVIDER_KEYS.items() if os.getenv(key)), "openrouter")


def new_transcript(
    *, root: Path, version: str, prompt_path: Path, tools_path: Path,
    provider: str, model: str, history_window: int, max_tool_rounds: int,
) -> dict[str, Any]:
    artifact = build_artifact_version(version, prompt_path, tools_path)
    created = timestamp()
    transcript_id = f"{version}_{provider}_ui_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"
    return {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact),
        "provider": provider,
        "model": model,
        "system_prompt": prompt_path.relative_to(root).as_posix(),
        "tools": tools_path.relative_to(root).as_posix(),
        "source": "streamlit",
        "runtime_mode": "live_api",
        "dataset_notice": "Local helpdesk data is fictional. Provider responses are real only after a successful API call.",
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "created_at": created,
        "updated_at": created,
        "turns": [],
    }


def public_transcript(transcript: dict[str, Any]) -> dict[str, Any]:
    # The context contains the same tool results and a copy of the system prompt;
    # the export remains compatible with the CLI without duplicating all context.
    return redact({key: value for key, value in transcript.items() if key != "context_messages"})


def transcript_json(transcript: dict[str, Any]) -> str:
    return json.dumps(public_transcript(transcript), ensure_ascii=False, indent=2, default=str)


def save_transcript(root: Path, transcript: dict[str, Any]) -> Path:
    transcript["updated_at"] = timestamp()
    folder = root / "transcripts" / "ui"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{transcript['transcript_id']}.transcript.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(transcript_json(transcript), encoding="utf-8")
    temporary.replace(path)
    return path


def conversation_messages(transcript: dict[str, Any], system_prompt: str, user_text: str) -> list[dict[str, Any]]:
    context = copy.deepcopy(transcript.get("context_messages", []))
    if not context:
        context = [{"role": "system", "content": system_prompt}]
        for turn in transcript["turns"]:
            if turn.get("assistant_text") and turn.get("status") != "provider_error":
                context.extend([
                    {"role": "user", "content": turn["user"]},
                    {"role": "assistant", "content": turn["assistant_text"]},
                ])
    # Keep complete user-initiated turns; never cut a tool result away from its call.
    starts = [index for index, message in enumerate(context) if message.get("role") == "user"]
    window = transcript["history_window"]
    if len(starts) > window:
        context = [context[0], *context[starts[-window]:]] if window else [context[0]]
    context.append({"role": "user", "content": redact(user_text)})
    return context


def safe_provider_error(exc: Exception) -> str:
    """Do not persist SDK error bodies, URLs or exception messages with secrets."""
    error_name = type(exc).__name__
    if "Authentication" in error_name or "Permission" in error_name:
        return "Nhà cung cấp từ chối xác thực. Kiểm tra API key và quyền truy cập model trong .env."
    if "RateLimit" in error_name:
        return "Nhà cung cấp đang giới hạn lượt gọi hoặc tài khoản hết hạn mức. Kiểm tra tài khoản rồi thử lại."
    if "Timeout" in error_name or "Connection" in error_name:
        return "Không kết nối được nhà cung cấp. Kiểm tra mạng và thử lại."
    return "Không hoàn tất được lượt gọi model. Kiểm tra kết nối, API key, tên model và các thư viện trong requirements.txt."
