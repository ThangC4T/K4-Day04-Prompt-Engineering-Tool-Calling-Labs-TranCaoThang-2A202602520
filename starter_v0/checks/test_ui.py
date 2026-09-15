"""UI smoke tests with no API calls and no live-evidence claims."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from providers.base import ModelResponse, ToolCall


class UITests(unittest.TestCase):
    def test_ticket_button_creates_only_after_click(self):
        ticket = {"summary": "VPN unavailable", "priority": "medium", "asset_id": "LT-204", "confirmed": True}
        with tempfile.TemporaryDirectory() as folder, \
             patch("tools.create_ticket.tool.TICKET_DIR", Path(folder)), \
             patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-placeholder"}), \
             patch("providers.openrouter_provider.OpenRouterProvider.complete", return_value=ModelResponse(tool_calls=[ToolCall("create_ticket", ticket)])) as complete, \
             patch("ui_support.save_transcript", return_value=ROOT / "transcripts/test-double.json"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.chat_input[0].set_value("Create ticket").run()
            self.assertFalse(app.exception)
            self.assertFalse(list(Path(folder).iterdir()))
            next(button for button in app.button if button.label == "Xác nhận tạo ticket").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(list(Path(folder).glob("*.json"))), 1)
            self.assertEqual(complete.call_count, 1)
            self.assertFalse(app.session_state["transcript"]["turns"][-1]["provider_response_observed"])

    def test_no_key_ui_and_local_tool_work(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": ""}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.chat_input[0].disabled)
            button = next(button for button in app.button if button.label == "Chạy công cụ local")
            button.click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["local_result"]["tool"], "check_service_status")
            self.assertEqual(len(app.session_state["transcript"]["turns"]), 0)

    def test_chat_trace_uses_shared_loop_and_resets_configuration(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-placeholder"}), \
             patch("providers.openrouter_provider.OpenRouterProvider.complete", side_effect=[
                 ModelResponse(tool_calls=[ToolCall("check_service_status", {"service": "vpn"})]),
                 ModelResponse(text='{"intent":"service_status","action":"answered","reply":"VPN status checked","evidence_ids":[]}')]), \
             patch("ui_support.save_transcript", return_value=ROOT / "transcripts/test-double.json"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.chat_input[0].set_value("Check VPN production").run()
            self.assertFalse(app.exception)
            transcript = app.session_state["transcript"]
            self.assertEqual(transcript["turns"][0]["status"], "answered")
            self.assertEqual(len(transcript["turns"][0]["tool_events"]), 1)
            self.assertTrue(any(m["role"] == "tool" for m in transcript["context_messages"]))
            self.assertTrue(next(s for s in app.selectbox if s.label == "Nhà cung cấp").disabled)
            next(b for b in app.button if b.label == "＋ Hội thoại mới").click().run()
            self.assertEqual(len(app.session_state["transcript"]["turns"]), 0)
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
