from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Any

from env_loader import load_lab_env
from providers import make_provider
from providers.base import ToolCall
from tools import load_tool_declarations, to_openai_tools
from privacy import redact_sensitive
from tool_runtime import execute_tool_call
from versioning import artifact_version_dict, build_artifact_version


ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
load_lab_env(ROOT)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("_") or "run"


def json_text(value: Any, *, max_chars: int | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...<truncated>"
    return text


def trim_history(history: list[dict[str, str]], window: int) -> list[dict[str, str]]:
    if window <= 0:
        return []
    return history[-window * 2:]


def assistant_tool_message(response_text: str | None, calls: list[ToolCall]) -> dict[str, Any]:
    used_ids: set[str] = set()
    for call in calls:
        if not call.id or call.id in used_ids:
            call.id = "call_" + uuid4().hex
        used_ids.add(call.id)
    return {"role": "assistant", "content": redact_sensitive(response_text), "tool_calls": [
        {"id": call.id, "type": "function", "function": {
            "name": call.name, "arguments": json.dumps(redact_sensitive(call.args), ensure_ascii=False),
        }} for call in calls
    ]}


def trim_context(messages: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    """Keep complete turns so tool outputs never lose their originating call."""
    if window <= 0:
        return messages[:1]
    starts = [i for i, message in enumerate(messages) if message.get("role") == "user"]
    return [messages[0], *messages[starts[-window]:]] if len(starts) > window else messages


def run_model_tool_loop(
    *,
    provider: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None,
    max_tool_rounds: int,
    confirmation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds must be positive")
    working_messages = deepcopy(redact_sensitive(messages))
    rounds: list[dict[str, Any]] = []
    all_tool_events: list[dict[str, Any]] = []

    def finish(status: str, text: str) -> dict[str, Any]:
        working_messages.append({"role": "assistant", "content": text})
        if confirmation_state is not None:
            confirmation_state.pop("approved_action", None)
        return {"status": status, "assistant_text": text, "rounds": rounds,
                "tool_events": all_tool_events, "working_messages": working_messages}

    # Approval comes from a UI button or /confirm, never from a model boolean.
    # Execute the stored payload directly: the model cannot silently alter it.
    approved = confirmation_state.get("approved_action") if confirmation_state else None
    pending = confirmation_state.get("pending_action") if confirmation_state else None
    if approved and approved == pending:
        call = ToolCall(name=approved["name"], args=deepcopy(approved["args"]))
        working_messages.append(assistant_tool_message(None, [call]))
        event = execute_tool_call(call, tools=tools, confirmation_state=confirmation_state)
        all_tool_events.append(event)
        working_messages.append({"role": "tool", "tool_call_id": call.id, "content": json_text(event["result"])})
        rounds.append({"round": 0, "source": "user_confirmation", "assistant_text": None,
                       "tool_calls": [{"name": call.name, "args": redact_sensitive(call.args)}], "tool_results": [event]})
        result = event["result"]
        text = (f"Đã tạo ticket {result['ticket_id']}." if result.get("status") == "created"
                else "Chưa tạo được ticket. Xem lỗi trong trace và kiểm tra lại nội dung.")
        return finish("action_completed" if result.get("status") == "created" else "action_error", text)
    if confirmation_state is not None:
        confirmation_state.clear()  # a new/revised request invalidates older consent

    for round_index in range(1, max_tool_rounds + 1):
        response = provider.complete(working_messages, tools, model=model, temperature=0.0)
        calls = response.tool_calls
        round_record: dict[str, Any] = {
            "round": round_index,
            "assistant_text": redact_sensitive(response.text),
            "tool_calls": [{"name": call.name, "args": redact_sensitive(call.args)} for call in calls],
            "tool_results": [],
        }

        if not calls:
            rounds.append(round_record)
            return finish("answered", redact_sensitive(response.text or ""))

        message = assistant_tool_message(response.text, calls)
        metadata = getattr(response, "assistant_metadata", {})
        if metadata.get("gemini_parts"):
            message["provider_metadata"] = metadata
        if "reasoning_content" in metadata:
            message["reasoning_content"] = metadata["reasoning_content"]
        working_messages.append(message)
        pause: tuple[str, str] | None = None

        for call in calls:
            event = ({"tool": call.name, "args": redact_sensitive(call.args),
                      "result": {"error": "skipped_awaiting_user"}} if pause else
                     execute_tool_call(call, tools=tools, confirmation_state=confirmation_state))
            round_record["tool_results"].append(event)
            all_tool_events.append(event)
            working_messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": json_text(event["result"])})

            # Detect the clarification/pause tool by its output flag (rename-proof),
            # not by a hard-coded tool name.
            result = event.get("result", {})
            if isinstance(result, dict) and result.get("awaiting_user"):
                question = result.get("question") or "Bạn bổ sung thêm thông tin nhé."
                pause = ("waiting_for_user", question)
            elif isinstance(result, dict) and result.get("awaiting_confirmation"):
                pause = ("waiting_for_confirmation", "Vui lòng kiểm tra nội dung ticket và xác nhận bằng nút trên giao diện hoặc /confirm trong CLI.\n" + json_text(result["pending_action"]))

        rounds.append(round_record)
        if pause:
            return finish(*pause)

    return finish("max_tool_rounds", f"Stopped after {max_tool_rounds} tool rounds. Inspect the transcript for details.")


def write_transcript(path: Path, transcript: dict[str, Any]) -> None:
    transcript["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_sensitive(transcript), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive IT Helpdesk Agent chat with transcript logging.")
    parser.add_argument("--provider", choices=["openrouter", "openai", "anthropic", "gemini", "groq"], required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--version", required=True, help="Student-chosen artifact version label, e.g. v0, v1, v2.")
    parser.add_argument("--system-prompt", type=Path, default=ARTIFACTS_DIR / "system_prompt.md")
    parser.add_argument("--tools", type=Path, default=ARTIFACTS_DIR / "tools.yaml")
    parser.add_argument("--transcripts-dir", type=Path, default=ROOT / "transcripts")
    parser.add_argument("--history-window", type=int, default=5, help="Keep the last N user/assistant pairs in context.")
    parser.add_argument("--max-tool-rounds", type=int, default=4)
    args = parser.parse_args()

    system_prompt = args.system_prompt.read_text(encoding="utf-8")
    tool_declarations = load_tool_declarations(args.tools)
    openai_tools = to_openai_tools(tool_declarations)
    provider = make_provider(args.provider)
    selected_model = args.model or getattr(provider, "default_model", None)
    artifact_version = build_artifact_version(args.version, args.system_prompt, args.tools)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([
        safe_slug(args.version),
        safe_slug(args.provider),
        timestamp,
    ])
    transcript_path = args.transcripts_dir / f"{transcript_id}.transcript.json"
    transcript: dict[str, Any] = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": args.provider,
        "model": selected_model,
        "system_prompt": str(args.system_prompt),
        "tools": str(args.tools),
        "history_window": args.history_window,
        "max_tool_rounds": args.max_tool_rounds,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }

    print(f"IT Helpdesk Agent chat. artifact_version={artifact_version.artifact_version}")
    print("Type /exit to stop; /confirm approves the displayed ticket; /cancel discards it.")

    history: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    confirmation_state: dict[str, Any] = {}
    turn_index = 0
    while True:
        try:
            user_text = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            break
        if user_text == "/confirm":
            if not confirmation_state.get("pending_action"):
                print("No ticket is waiting for confirmation.")
                continue
            confirmation_state["approved_action"] = deepcopy(confirmation_state["pending_action"])
        elif user_text == "/cancel":
            confirmation_state.clear()
            user_text = "Hủy yêu cầu tạo ticket. Không thực hiện hành động nào."
        user_text = redact_sensitive(user_text)

        turn_index += 1
        messages = [
            *trim_context(history, args.history_window),
            {"role": "user", "content": user_text},
        ]

        turn_record: dict[str, Any] = {
            "turn_index": turn_index,
            "started_at": now_iso(),
            "user": user_text,
            "status": "started",
            "assistant_text": None,
            "rounds": [],
            "tool_events": [],
        }

        try:
            result = run_model_tool_loop(
                provider=provider,
                messages=messages,
                tools=openai_tools,
                model=args.model,
                max_tool_rounds=args.max_tool_rounds,
                confirmation_state=confirmation_state,
            )
            history = result.pop("working_messages")
            turn_record.update(result)
            assistant_text = result["assistant_text"]
            print(f"\nAgent> {assistant_text}")
        except Exception as exc:
            confirmation_state.pop("approved_action", None)
            turn_record.update({
                "status": "provider_error",
                "error": type(exc).__name__,
            })
            print(f"\nERROR> {turn_record['error']}")

        turn_record["ended_at"] = now_iso()
        transcript["turns"].append(turn_record)
        write_transcript(transcript_path, transcript)
        print(f"Transcript saved: {transcript_path}")

    write_transcript(transcript_path, transcript)
    print(f"Final transcript: {transcript_path}")


if __name__ == "__main__":
    main()
