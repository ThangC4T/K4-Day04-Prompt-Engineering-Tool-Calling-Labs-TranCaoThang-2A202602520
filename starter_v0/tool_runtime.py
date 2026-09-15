"""Shared, fail-closed model-to-tool boundary used by evaluation and chat."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator

from privacy import redact_sensitive, SECRET_ASSIGNMENT, API_SECRET
from providers.base import ToolCall
from tools import TOOL_FUNCTIONS
from tools.create_ticket.tool import SENSITIVE_DATA_PATTERN


def ticket_action(args: dict[str, Any]) -> dict[str, Any]:
    """Match the exact payload the implementation will write; no model token grants permission."""
    return {"name": "create_ticket", "args": {
        "summary": args.get("summary", "").strip(),
        "priority": args.get("priority", "medium").strip().lower(),
        "asset_id": args.get("asset_id", "").strip().upper(),
        "confirmed": True,
    }}


def execute_tool_call(
    call: ToolCall,
    *,
    tools: list[dict[str, Any]] | None = None,
    confirmation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {"tool": call.name, "args": redact_sensitive(call.args)}

    def reject(error: str, **details: Any) -> dict[str, Any]:
        return {**event, "result": {"error": error, **details}}

    declarations = {item.get("function", item).get("name"): item.get("function", item) for item in tools or []}
    if call.name not in declarations:
        return reject("undeclared_tool")
    func = TOOL_FUNCTIONS.get(call.name)
    if func is None:
        return reject("unknown_tool")
    if not isinstance(call.args, dict):
        return reject("invalid_arguments", message="Tool arguments must be a JSON object.")
    schema = deepcopy(declarations[call.name].get("parameters", {"type": "object", "properties": {}}))
    # Unknown arguments are never accepted, including for baseline schemas that omit this flag.
    schema["additionalProperties"] = False
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(call.args), key=lambda err: str(list(err.path)))
    except Exception:
        return reject("invalid_tool_schema")
    if errors:
        # ValidationError.message can echo user secrets; return only the failed path/rule.
        error = errors[0]
        return reject("invalid_arguments", path=list(error.path), rule=error.validator)
    if call.name == "create_ticket":
        summary = call.args.get("summary", "")
        if SENSITIVE_DATA_PATTERN.search(summary) or SECRET_ASSIGNMENT.search(summary) or API_SECRET.search(summary):
            return reject("restricted_sensitive_data")
        action = ticket_action(call.args)
        approved = confirmation_state.pop("approved_action", None) if confirmation_state is not None else None
        if approved != action:
            if confirmation_state is not None:
                confirmation_state["pending_action"] = deepcopy(action)
            return {**event, "result": {
                "status": "needs_confirmation",
                "awaiting_confirmation": True,
                "pending_action": action,
                "message": "Approve this exact ticket payload using the UI button or CLI /confirm command.",
            }}
        confirmation_state.pop("pending_action", None)
        args = action["args"]
    else:
        args = call.args
    try:
        result = func(**args)
    except Exception as exc:
        result = {"error": type(exc).__name__, "message": "Tool execution failed. Review local configuration."}
    return {**event, "result": redact_sensitive(result)}
