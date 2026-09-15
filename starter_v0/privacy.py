"""Best-effort credential redaction for provider input, UI and persisted traces.

This is a backstop for recognizable credentials, not a general DLP classifier.
The external-search boundary uses a positive public-product allowlist instead.
"""
from __future__ import annotations

import re
import os
from typing import Any


SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|mat khau|mật khẩu|token|api[ _-]?key|"
    r"mfa|otp|recovery[ _-]?code)\b[\"']?\s*(?::|=|\bis\b|\bla\b|\blà\b)\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
)
API_SECRET = re.compile(r"\b(?:gsk_[A-Za-z0-9]{20,}|sk-(?:proj-|or-v1-)?[A-Za-z0-9_-]{16,}|tvly-[A-Za-z0-9_-]{16,})\b")
SECRET_KEYS = {"password", "passwd", "token", "api_key", "apikey", "otp", "mfa", "recovery_code", "authorization"}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for key, secret in os.environ.items():
            if key.endswith(("_API_KEY", "_TOKEN")) and len(secret) >= 8:
                result = result.replace(secret, "[REDACTED]")
        return API_SECRET.sub("[REDACTED]", SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", result))
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).casefold().replace("-", "_") in SECRET_KEYS
            else redact_sensitive(item)
            for key, item in value.items()
        }
    return value
