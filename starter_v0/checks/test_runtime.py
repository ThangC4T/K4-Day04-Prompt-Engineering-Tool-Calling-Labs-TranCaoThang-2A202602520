"""Deterministic tests use scripted responses, never submitted as LLM evidence."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import AgentRun
from chat import run_model_tool_loop, trim_context
from privacy import redact_sensitive
from providers.base import ModelResponse, ToolCall
from providers.anthropic_provider import _split_system
from providers.gemini_provider import _to_gemini_contents, _to_gemini_declarations
from providers.openai_provider import OpenAIProvider
from providers.openrouter_provider import OpenRouterProvider
from run_eval import evaluate_phase_b, run_case
from scripts.check_submission import check_local
from tool_runtime import execute_tool_call, ticket_action
from tools import load_tool_declarations, to_openai_tools
from tools import TOOL_FUNCTIONS
from tools.search_device_info.tool import search_device_info
from ui_support import conversation_messages, new_transcript, transcript_json

TOOLS = to_openai_tools(load_tool_declarations(ROOT / "artifacts/tools.yaml"))
TICKET = {"summary": "VPN is unavailable", "priority": "medium", "asset_id": "LT-204", "confirmed": True}


class ScriptedProvider:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.messages = []

    def complete(self, messages, tools, **kwargs):
        self.messages.append(copy.deepcopy(messages))
        return next(self.responses)


def loop(provider, state=None, messages=None, rounds=4):
    return run_model_tool_loop(provider=provider, messages=messages or [
        {"role": "system", "content": "Test fixture"}, {"role": "user", "content": "Check the service"}],
        tools=TOOLS, model="scripted-test-double", max_tool_rounds=rounds, confirmation_state=state)


class RuntimeTests(unittest.TestCase):
    def test_read_only_mock_tools_return_evidence(self):
        samples = [("inspect_device", {"asset_id": "LT-204", "check": "vpn"}),
                   ("lookup_user", {"employee_id": "EMP-1001"}),
                   ("search_kb", {"query": "vpn", "category": "vpn"}),
                   ("policy", {"query": "ticket confirmation"}),
                   ("format_incident_report", {"findings": [{"label": "VPN", "detail": "unavailable"}], "template": "brief"})]
        for name, args in samples:
            with self.subTest(tool=name):
                result = TOOL_FUNCTIONS[name](**args)
                self.assertNotIn("error", result)
                if "results" in result:
                    self.assertTrue(result["results"])

    def test_submission_contracts(self):
        self.assertEqual(check_local()["case_counts"]["group"], 10)

    def test_undeclared_tool_never_executes(self):
        with patch("tool_runtime.TOOL_FUNCTIONS", {"inspect_device": Mock()}) as functions:
            event = execute_tool_call(ToolCall("inspect_device", {"asset_id": "LT-204"}), tools=[])
            self.assertEqual(event["result"]["error"], "undeclared_tool")
            functions["inspect_device"].assert_not_called()

    def test_schema_rejects_unknown_and_wrong_types(self):
        for args in ({**TICKET, "confirmed": "true"}, {**TICKET, "shell": "echo"}, ["bad"]):
            self.assertEqual(execute_tool_call(ToolCall("create_ticket", args), tools=TOOLS)["result"]["error"], "invalid_arguments")

    def test_model_confirmation_is_not_write_permission(self):
        with tempfile.TemporaryDirectory() as folder, patch("tools.create_ticket.tool.TICKET_DIR", Path(folder)):
            result = execute_tool_call(ToolCall("create_ticket", TICKET), tools=TOOLS)
            self.assertEqual(result["result"]["status"], "needs_confirmation")
            self.assertFalse(list(Path(folder).iterdir()))

    def test_approval_is_payload_bound_and_single_use(self):
        with tempfile.TemporaryDirectory() as folder, patch("tools.create_ticket.tool.TICKET_DIR", Path(folder)):
            action = ticket_action(TICKET)
            state = {"approved_action": action, "pending_action": action}
            changed = {**TICKET, "priority": "high"}
            self.assertEqual(execute_tool_call(ToolCall("create_ticket", changed), tools=TOOLS, confirmation_state=state)["result"]["status"], "needs_confirmation")
            self.assertFalse(list(Path(folder).iterdir()))
            state["approved_action"] = copy.deepcopy(state["pending_action"])
            self.assertEqual(execute_tool_call(ToolCall("create_ticket", changed), tools=TOOLS, confirmation_state=state)["result"]["status"], "created")
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)
            self.assertEqual(execute_tool_call(ToolCall("create_ticket", changed), tools=TOOLS, confirmation_state=state)["result"]["status"], "needs_confirmation")

    def test_secrets_never_reach_ticket_file(self):
        with tempfile.TemporaryDirectory() as folder, patch("tools.create_ticket.tool.TICKET_DIR", Path(folder)):
            for summary in ('password="test-value"', 'mật khẩu là test-value', 'OTP: 123456'):
                args = {**TICKET, "summary": summary}
                state = {"approved_action": ticket_action(args)}
                self.assertEqual(execute_tool_call(ToolCall("create_ticket", args), tools=TOOLS, confirmation_state=state)["result"]["error"], "restricted_sensitive_data")
            self.assertFalse(list(Path(folder).iterdir()))

    def test_tool_results_have_real_role_and_matching_ids(self):
        provider = ScriptedProvider(ModelResponse(tool_calls=[ToolCall("check_service_status", {"service": "vpn"})]), ModelResponse(text="Done"))
        result = loop(provider)
        messages = provider.messages[1]
        call = next(message for message in messages if message.get("tool_calls"))
        output = next(message for message in messages if message["role"] == "tool")
        self.assertEqual(call["tool_calls"][0]["id"], output["tool_call_id"])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["working_messages"][-1]["content"], "Done")

    def test_clarification_pauses_and_resolves_all_call_ids(self):
        provider = ScriptedProvider(ModelResponse(tool_calls=[ToolCall("clarify", {"question": "Asset ID?"}), ToolCall("create_ticket", TICKET)]))
        result = loop(provider, {})
        self.assertEqual(result["status"], "waiting_for_user")
        self.assertEqual(result["tool_events"][1]["result"]["error"], "skipped_awaiting_user")
        self.assertEqual(len([m for m in result["working_messages"] if m["role"] == "tool"]), 2)

    def test_ui_approval_executes_exact_ticket_without_model(self):
        with tempfile.TemporaryDirectory() as folder, patch("tools.create_ticket.tool.TICKET_DIR", Path(folder)):
            state = {}
            result = loop(ScriptedProvider(ModelResponse(tool_calls=[ToolCall("create_ticket", TICKET)])), state)
            self.assertEqual(result["status"], "waiting_for_confirmation")
            state["approved_action"] = copy.deepcopy(state["pending_action"])
            no_provider_calls = ScriptedProvider()
            confirmed = loop(no_provider_calls, state)
            self.assertEqual(confirmed["status"], "action_completed")
            self.assertFalse(no_provider_calls.messages)
            self.assertFalse(state)
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)

    def test_native_tool_provenance_converts_for_all_providers(self):
        result = loop(ScriptedProvider(ModelResponse(tool_calls=[ToolCall("check_service_status", {"service": "vpn"})]), ModelResponse(text="Done")))
        messages = result["working_messages"]
        _, anthropic = _split_system(messages)
        self.assertTrue(any(block.get("type") == "tool_result" for m in anthropic for block in m["content"]))
        _, gemini = _to_gemini_contents(messages)
        self.assertTrue(any("function_response" in p for m in gemini for p in m["parts"]))
        from google.genai import types
        types.Tool(function_declarations=_to_gemini_declarations(TOOLS))
        for content in gemini:
            types.Content(**content)

    def test_context_trimming_keeps_tool_pair(self):
        history = [{"role": "system", "content": "s"}, {"role": "user", "content": "old"},
                   {"role": "assistant", "content": "old"}, {"role": "user", "content": "new"},
                   {"role": "assistant", "tool_calls": [{"id": "x"}]}, {"role": "tool", "tool_call_id": "x"}]
        self.assertEqual(trim_context(history, 1), [history[0], *history[3:]])
        self.assertEqual(trim_context(history, 0), history[:1])

    def test_limit_has_explicit_status(self):
        result = loop(ScriptedProvider(ModelResponse(tool_calls=[ToolCall("check_service_status", {"service": "vpn"})])), rounds=1)
        self.assertEqual(result["status"], "max_tool_rounds")

    def test_external_search_rejects_appended_private_text_without_http(self):
        with patch("tools.search_device_info.tool.requests.post") as post:
            for suffix in (" LT-204", " EMP-1001", " serial ABCDE", " hostname laptop.internal", " diagnostics broken"):
                result = search_device_info("Lenovo", "ThinkPad T14 Gen 4" + suffix)
                self.assertIn("error", result)
            post.assert_not_called()

    def test_external_search_exports_only_canonical_product(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-only-placeholder"}), patch("tools.search_device_info.tool.requests.post") as post:
            post.return_value.json.return_value = {"results": []}
            result = search_device_info("lenovo", "thinkpad t14 gen 4", "specs")
            self.assertNotIn("error", result)
            body = post.call_args.kwargs["json"]
            self.assertEqual(body["query"], "Lenovo ThinkPad T14 Gen 4 technical specifications official")
            self.assertEqual(body["include_domains"], ["support.lenovo.com", "psref.lenovo.com"])

    def test_provider_namespaces_are_isolated(self):
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://example.invalid/v1", "OPENAI_MODEL": "example-model"}, clear=True):
            direct, router = OpenAIProvider(), OpenRouterProvider()
            self.assertEqual(direct.base_url, "https://example.invalid/v1")
            self.assertEqual(router.base_url, "https://openrouter.ai/api/v1")
            self.assertEqual(router.default_model, "openai/gpt-4o-mini")

    def test_redaction_before_transcript_export(self):
        value = {"text": "password: demo-secret", "api_key": "demo-key"}
        self.assertNotIn("demo-secret", json.dumps(redact_sensitive(value)))
        self.assertNotIn("demo-key", json.dumps(redact_sensitive(value)))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "custom-provider-secret"}):
            self.assertNotIn("custom-provider-secret", transcript_json({"turns": [{"user": "custom-provider-secret"}]}))

    def test_missing_tool_is_failure_without_score_retry(self):
        agent = Mock()
        agent.run.return_value = AgentRun(text="no tool")
        case = {"query": "test", "failure_type": "wrong_tool", "expect": {"tool_calls": [{"name": "inspect_device", "args": {}}]}}
        result, _, attempts = run_case(agent, case)
        self.assertFalse(result["passed"])
        self.assertEqual(attempts, 1)
        self.assertEqual(agent.run.call_count, 1)

    def test_retry_throttling_but_redact_other_provider_errors(self):
        class RateLimitError(Exception):
            status_code = 429
        agent = Mock()
        agent.run.side_effect = [RateLimitError(), AgentRun(text="done")]
        case = {"query": "cancel", "failure_type": "unnecessary_tool", "expect": {"no_tool": True}}
        with patch("run_eval.time.sleep"):
            self.assertEqual(run_case(agent, case)[2], 2)
        agent.run.side_effect = ValueError("private-request-and-key")
        result, _, attempts = run_case(agent, case)
        self.assertEqual(attempts, 1)
        self.assertNotIn("private-request-and-key", str(result))


if __name__ == "__main__":
    unittest.main()
