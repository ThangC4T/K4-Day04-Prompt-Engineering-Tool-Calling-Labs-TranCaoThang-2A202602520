"""Vietnamese Streamlit interface. Run: streamlit run app.py"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from chat import run_model_tool_loop
from env_loader import load_lab_env
from providers import make_provider
from tools import TOOL_FUNCTIONS, load_tool_declarations, to_openai_tools
from ui_support import (
    PROVIDER_KEYS, available_versions, conversation_messages, default_provider,
    new_transcript, redact, safe_provider_error, save_transcript, timestamp, transcript_json,
)


ROOT = Path(__file__).resolve().parent
load_lab_env(ROOT)
st.set_page_config(page_title="IT Helpdesk · K4", page_icon="🛠️", layout="wide")
st.markdown("""
<style>
    .block-container { max-width: 1140px; padding-top: 2.2rem; }
    [data-testid="stSidebar"] { background: #f1f5f9; }
    [data-testid="stChatMessage"] { border-radius: 14px; }
    div[data-testid="stMetric"] { background: #f5f7fb; border-radius: 12px; padding: 12px 16px; }
</style>
""", unsafe_allow_html=True)


def reset_conversation() -> None:
    for key in ("transcript", "config", "confirmation", "saved_path", "save_error"):
        st.session_state.pop(key, None)


def persist(transcript: dict[str, Any]) -> None:
    try:
        st.session_state.saved_path = str(save_transcript(ROOT, transcript))
        st.session_state.pop("save_error", None)
    except OSError:
        st.session_state.save_error = "Không ghi được transcript ra ổ đĩa. Bạn vẫn có thể tải JSON trong thanh bên."


def render_turn(turn: dict[str, Any]) -> None:
    with st.chat_message("user"):
        st.markdown(turn["user"])
    with st.chat_message("assistant", avatar="🛠️"):
        status = turn.get("status", "")
        if status == "provider_error":
            st.error(turn.get("error", "Lượt gọi model thất bại."))
        else:
            answer = turn.get("assistant_text") or "Model không trả về nội dung. Bạn hãy diễn đạt lại yêu cầu."
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, dict) and isinstance(parsed.get("reply"), str):
                    answer = parsed["reply"]
            except (ValueError, TypeError):
                pass
            st.markdown(answer)
        if status == "max_tool_rounds":
            st.warning("Đã chạm giới hạn vòng gọi tool. Xem trace trước khi gửi thêm yêu cầu.")
        if status == "waiting_for_user":
            st.caption("Đang chờ bạn bổ sung thông tin.")
        rounds = turn.get("rounds", [])
        events = turn.get("tool_events", [])
        if rounds:
            with st.expander(f"Trace · {len(rounds)} vòng xử lý · {len(events)} lượt tool"):
                for record in rounds:
                    st.markdown(f"**Vòng {record['round']}**")
                    if record.get("assistant_text"):
                        st.caption(record["assistant_text"])
                    if record.get("tool_calls"):
                        st.caption("Tool và tham số model yêu cầu")
                        st.json(redact(record["tool_calls"]), expanded=False)
                    if record.get("tool_results"):
                        st.caption("Kết quả thực thi / lỗi")
                        st.json(redact(record["tool_results"]), expanded=False)
        st.caption(f"{turn.get('ended_at', '')} · {status}")


def local_explorer() -> None:
    st.subheader("Kiểm tra công cụ local — không gọi model")
    st.caption("Dữ liệu giả lập của bài lab. Kết quả này không được lưu thành transcript model hoặc điểm eval.")
    labels = {
        "check_service_status": "Trạng thái dịch vụ",
        "inspect_device": "Chẩn đoán thiết bị",
        "lookup_user": "Tra cứu nhân viên giả lập",
        "search_kb": "Tìm hướng dẫn xử lý",
        "policy": "Tìm chính sách công ty",
    }
    selected = st.selectbox("Công cụ local", list(labels), format_func=labels.get, key="local_tool")
    with st.form("local_tool_form"):
        if selected == "check_service_status":
            service = st.selectbox("Dịch vụ", ["vpn", "wifi", "email", "sso", "printing"])
            environment = st.selectbox("Môi trường", ["production", "staging"])
            args = {"service": service, "environment": environment}
        elif selected == "inspect_device":
            asset_id = st.text_input("Mã thiết bị", "LT-204")
            check = st.selectbox("Nội dung kiểm tra", ["all", "network", "vpn", "security", "hardware", "software"])
            args = {"asset_id": asset_id, "check": check}
        elif selected == "lookup_user":
            args = {"employee_id": st.text_input("Mã nhân viên giả lập", "EMP-1001")}
        else:
            args = {"query": st.text_input("Từ khóa", "vpn" if selected == "search_kb" else "ticket confirmation")}
        execute = st.form_submit_button("Chạy công cụ local", type="primary")
    if execute:
        try:
            st.session_state.local_result = {"tool": selected, "args": args, "result": redact(TOOL_FUNCTIONS[selected](**args))}
        except Exception as exc:
            st.session_state.local_result = {"tool": selected, "error": type(exc).__name__}
    if "local_result" in st.session_state:
        st.json(st.session_state.local_result)


st.sidebar.markdown("### 🛠️ K4 · IT Helpdesk")
st.sidebar.caption("Phạm Minh Cương · 2A202602825\n\nBài làm nhóm · Day 04")
st.sidebar.button("＋ Hội thoại mới", on_click=reset_conversation, use_container_width=True)
locked = bool(st.session_state.get("transcript", {}).get("turns"))
providers = list(PROVIDER_KEYS)
provider_name = st.sidebar.selectbox("Nhà cung cấp", providers, index=providers.index(default_provider()), disabled=locked)
provider = make_provider(provider_name)
model = st.sidebar.text_input("Model", value=provider.default_model, key=f"model_{provider_name}", disabled=locked).strip()
versions = available_versions(ROOT)
version = st.sidebar.selectbox("Phiên bản prompt / tool", list(versions), index=list(versions).index("v3" if "v3" in versions else "working"), disabled=locked)
history_window = st.sidebar.slider("Số lượt giữ trong ngữ cảnh", 1, 12, 6, disabled=locked)
max_rounds = st.sidebar.slider("Giới hạn vòng tool / lượt", 1, 10, 6, disabled=locked)
if locked:
    st.sidebar.caption("Chọn “Hội thoại mới” để đổi cấu hình; transcript trước đó đã được lưu.")
prompt_path, tools_path = versions[version]
try:
    system_prompt = prompt_path.read_text(encoding="utf-8")
    declarations = load_tool_declarations(tools_path)
    openai_tools = to_openai_tools(declarations)
    config = (version, provider_name, model, history_window, max_rounds)
    if st.session_state.get("config") != config:
        st.session_state.transcript = new_transcript(
            root=ROOT, version=version, prompt_path=prompt_path, tools_path=tools_path,
            provider=provider_name, model=model, history_window=history_window, max_tool_rounds=max_rounds,
        )
        st.session_state.config = config
        st.session_state.confirmation = {}
except (OSError, ValueError, KeyError) as exc:
    st.error(f"Không đọc được cấu hình artifact ({type(exc).__name__}). Kiểm tra đường dẫn prompt và tools.yaml.")
    st.stop()
transcript = st.session_state.transcript
key_name = PROVIDER_KEYS[provider_name]
ready = bool(os.getenv(key_name, "").strip()) and bool(model)
if ready:
    st.sidebar.success(f"Đã cấu hình {key_name}")
    st.sidebar.caption("Kết nối chỉ được xác minh khi gửi yêu cầu.")
else:
    st.sidebar.warning(f"Chưa sẵn sàng: cần {key_name} và tên model.")
with st.sidebar.expander("Artifact và tool đã nạp"):
    st.code(transcript["artifact_version"], language=None)
    st.caption("SHA-256 prompt")
    st.code(transcript["prompt_hash"], language=None)
    st.caption("SHA-256 tools.yaml")
    st.code(transcript["tools_hash"], language=None)
    for declaration in declarations:
        st.text(declaration["name"])
if transcript["turns"]:
    st.sidebar.download_button("↓ Tải transcript JSON", transcript_json(transcript), file_name=f"{transcript['transcript_id']}.transcript.json", mime="application/json", use_container_width=True)
    if st.session_state.get("saved_path"):
        st.sidebar.caption("Tự động lưu: transcripts/ui/")
if st.session_state.get("save_error"):
    st.sidebar.error(st.session_state.save_error)

st.caption("K4 · DAY 04 LAB")
st.title("Hỗ trợ IT, có căn cứ.")
st.markdown("Mô tả sự cố của bạn. Trợ lý sẽ tra cứu, chẩn đoán và trình bày bước xử lý dựa trên kết quả công cụ.")
st.caption("Dữ liệu thiết bị, nhân viên và dịch vụ là dữ liệu giả lập trong bài lab.")
columns = st.columns(3)
columns[0].metric("Phiên bản", version)
columns[1].metric("Công cụ", len(declarations))
columns[2].metric("Lượt hội thoại", len(transcript["turns"]))
chat_tab, local_tab, guide_tab = st.tabs(["💬 Hội thoại", "🔎 Công cụ local", "📖 Hướng dẫn demo"])

with local_tab:
    local_explorer()

with guide_tab:
    st.subheader("Ba tình huống để demo")
    st.markdown("1. **Chẩn đoán nhiều nguồn:** `Tôi là EMP-1001, máy LT-204 không kết nối VPN. Hãy kiểm tra và hướng dẫn xử lý.`\n2. **Hội thoại nhiều lượt:** `Máy của tôi không vào được mạng.` → bổ sung mã thiết bị và biểu hiện khi trợ lý hỏi.\n3. **Tạo phiếu:** `Soạn ticket cho sự cố VPN trên LT-204, ưu tiên medium.` → xem nội dung → bấm xác nhận tạo ticket.")
    st.info("Trace hiển thị tên tool, tham số, kết quả và lỗi từng vòng. Transcript JSON lưu phiên bản và SHA-256 của prompt/tool để đối chiếu báo cáo.")
    st.markdown("**Cấu hình API:** sao chép `.env.example` thành `.env` trong `starter_v0/`, điền key của nhà cung cấp, sau đó khởi động lại ứng dụng. Có thể dùng biến `DAY04_ENV_FILE` để trỏ tới file môi trường bên ngoài repository.")
    st.caption("API key chỉ đọc từ môi trường máy chủ. Không dán key vào khung chat hoặc commit file .env.")

with chat_tab:
    if not ready:
        st.warning(f"Chưa cấu hình {key_name}. Bạn có thể kiểm tra dữ liệu ở tab Công cụ local; để chat với model, thêm key vào .env rồi khởi động lại ứng dụng.")
    if not transcript["turns"]:
        st.info("Bắt đầu với: “Máy LT-204 của EMP-1001 không kết nối VPN, hãy kiểm tra giúp tôi.”")
    for turn in transcript["turns"]:
        render_turn(turn)
    pending = st.session_state.confirmation.get("pending_action")
    submitted = None
    if pending:
        st.warning("Công cụ đang chờ xác nhận nội dung chính xác trước khi tạo ticket.")
        st.json(redact(pending))
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("Xác nhận tạo ticket", type="primary", disabled=not ready):
            st.session_state.confirmation["approved_action"] = copy.deepcopy(pending)
            submitted = "Tôi xác nhận thực hiện đúng nội dung ticket vừa hiển thị."
        if cancel_col.button("Hủy tạo ticket"):
            st.session_state.confirmation.clear()
            cancelled = {
                "turn_index": len(transcript["turns"]) + 1, "started_at": timestamp(),
                "ended_at": timestamp(), "user": "Hủy tạo ticket.", "status": "cancelled",
                "assistant_text": "Đã hủy yêu cầu tạo ticket. Bạn có thể tiếp tục mô tả sự cố.",
                "rounds": [], "tool_events": [], "provider_response_observed": False,
            }
            messages = conversation_messages(transcript, system_prompt, cancelled["user"])
            messages.append({"role": "assistant", "content": cancelled["assistant_text"]})
            transcript["context_messages"] = messages
            transcript["turns"].append(cancelled)
            persist(transcript)
            st.rerun()
    prompt = st.chat_input("Nhập sự cố, mã thiết bị hoặc câu hỏi của bạn…", disabled=not ready or bool(pending))
    submitted = submitted or prompt
    if submitted and submitted.strip():
        user_text = redact(submitted.strip())
        turn_record = {
            "turn_index": len(transcript["turns"]) + 1, "started_at": timestamp(),
            "user": user_text, "status": "started", "assistant_text": None,
            "rounds": [], "tool_events": [], "provider_response_observed": False,
        }
        try:
            with st.spinner("Đang tra cứu và xử lý sự cố…"):
                result = run_model_tool_loop(
                    provider=provider, messages=conversation_messages(transcript, system_prompt, user_text),
                    tools=openai_tools, model=model, max_tool_rounds=max_rounds,
                    confirmation_state=st.session_state.confirmation,
                )
            result = redact(result)
            context = result.pop("working_messages", None)
            if context:
                transcript["context_messages"] = context
            turn_record.update(result)
            turn_record["provider_response_observed"] = any(r.get("source") != "user_confirmation" for r in result.get("rounds", []))
        except Exception as exc:
            st.session_state.confirmation.pop("approved_action", None)
            turn_record.update(status="provider_error", error=safe_provider_error(exc), error_type=type(exc).__name__)
        turn_record["ended_at"] = timestamp()
        transcript["turns"].append(turn_record)
        persist(transcript)
        st.rerun()
