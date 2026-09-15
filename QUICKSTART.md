# Chạy bài lab của nhóm

Thành viên đã xác nhận: **Phạm Minh Cương — 2A202602825**. Danh sách và lịch
sử đóng góp: [TEAMMATES.md](TEAMMATES.md).

## Windows PowerShell

```powershell
cd starter_v0
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở `http://localhost:8501`. Tab **Công cụ local** hoạt động không cần API key,
đọc dữ liệu giả lập có sẵn. Tab **Hội thoại** cần một model provider có key.
Trên macOS/Linux, dùng `python3 -m venv .venv` và `.venv/bin/python` thay cho
đường dẫn Python của Windows.

## Bật hội thoại với model thật

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Điền **một** key phù hợp vào `.env`, không gửi key vào chat hoặc Git:
`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` hoặc `GEMINI_API_KEY`.
Khởi động lại UI. Model có thể chọn trên sidebar hoặc đặt bằng biến tương ứng
`GROQ_MODEL`, `OPENROUTER_MODEL`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL`.

Bản tích hợp đã preflight thành công với Groq. Cấu hình thực nghiệm:
`GROQ_MODEL=openai/gpt-oss-20b`, `GROQ_MAX_TOKENS=512`,
`GROQ_REASONING_EFFORT=low`. Đợt Qwen trước đó được lưu riêng trong báo cáo;
model này chạm quota ngày nên các bản được đo lại trên cùng GPT-OSS để so sánh.
Key chỉ lưu trong `.env` bị Git bỏ qua. Điều chỉnh giãn cách giữa các case
theo hạn mức thực tế của tài khoản; xem
[Groq rate limits](https://console.groq.com/docs/rate-limits).

`GROQ_LOCAL_TOOL_VALIDATION=1` yêu cầu Groq trả cả tool call không hợp lệ để
dispatcher local ghi nhận và từ chối, thay vì mất nội dung call trong HTTP 400.
Allowlist, JSON Schema và approval gate local luôn hoạt động. Tool lạ vẫn
bị chấm sai và không được thực thi; xem [API reference](https://console.groq.com/docs/api-reference).

Nếu dùng endpoint tương thích OpenAI, đặt rõ `OPENAI_BASE_URL`,
`OPENAI_API_KEY`, `OPENAI_MODEL`. Provider `openai` mặc định dùng OpenAI;
cấu hình của OpenAI không tự áp vào OpenRouter hoặc Groq. Kết quả live và
các giới hạn đã quan sát được ghi trong [báo cáo](starter_v0/artifacts/REPORT.md).

UI giữ lịch sử tool call/result, hiển thị trace và hashes, tự lưu transcript
trong `transcripts/ui/`. Thay provider/model/version cần bắt đầu hội thoại mới.
Ticket chỉ được ghi sau nút **Xác nhận tạo ticket** cho payload đang hiển thị.
Nút xác nhận thực thi chính payload đó, không gọi model để sửa nội dung.

CLI cũng dùng chung loop:

```powershell
.\.venv\Scripts\python.exe chat.py --provider groq --version v3
```

CLI có `/confirm`, `/cancel`, `/exit`. Hai giao diện Rich của thành viên vẫn
được giữ: `python chat_rich.py --provider groq --version v3` và
`python helpdesk_cli.py chat --provider groq --version v3`.

## Kiểm tra local

```powershell
.\.venv\Scripts\python.exe scripts/check_submission.py
.\.venv\Scripts\python.exe -m unittest discover -s checks -v
```

Các test dùng tool local, HTTP mock và model test double; chúng **không phải**
điểm eval LLM. CI chạy lại các kiểm tra này trên push/PR, không cần secrets.

## Thực nghiệm v0–v3 khi có key

`artifacts/versions/` giữ bốn bộ artifact riêng. v0 là nguyên starter; v1–v3
là các ứng viên chuẩn bị từ code review, chưa được tuyên bố là cải tiến đã đo.
Chạy và phân tích **từng phiên bản**, không chạy bốn bản liên tiếp chỉ để đủ tên.

```powershell
# Xem kế hoạch, không gọi API:
.\.venv\Scripts\python.exe scripts/run_experiment.py --version v0 --provider groq
# Chạy thật baseline + preflight, ghi JSON và cập nhật version_log.csv:
.\.venv\Scripts\python.exe scripts/run_experiment.py --version v0 --provider groq --delay 25 --run
```

Đọc `failures`, `observed_mismatch`, `tool_results`, rồi kiểm tra lại hypothesis
trước khi thay `--version` thành v1, v2, v3. Khi sửa snapshot, cập nhật hashes
trong `experiment_plan.json`; current prompt/tools phải khớp v3. Giữ cùng model,
provider, tool-choice, dataset và runtime để so sánh. Không sửa fixed suites.
Snapshot artifact được Git giữ nguyên byte (kể cả kiểu xuống dòng) để SHA-256
của lần chạy trên Windows vẫn khớp khi checkout trên hệ điều hành khác.

Sau v3:

```powershell
.\.venv\Scripts\python.exe scripts/run_experiment.py --version v3 --suite group --provider groq --delay 25 --run
.\.venv\Scripts\python.exe scripts/run_experiment.py --version v3 --suite adversarial --provider groq --delay 25 --run
.\.venv\Scripts\python.exe scripts/check_submission.py --require-live
```

Run lỗi provider không được ghi thành metric hợp lệ. Run PASS về routing vẫn
cần review tool error/empty result và câu trả lời. Eval không cấp quyền ghi
ticket; `confirmed=true` từ model chỉ được ghi nhận là lựa chọn routing.
Kiểm tra hành động thực qua UI với nút xác nhận và dữ liệu giả lập.

`search_device_info` dùng Tavily (cần `TAVILY_API_KEY`) và chỉ cho phép model
thiết bị trong `PUBLIC_PRODUCTS` tại implementation. Chuỗi nối thêm ID,
serial/hostname/diagnostics không được gửi đi; model ngoài catalog phải được
review rồi mới bổ sung. Tool này là advanced, không phải bonus mới.

## Chuẩn bị nộp

Hoàn thiện [báo cáo](starter_v0/artifacts/REPORT.md) bằng run và transcript thật,
ít nhất ba adversarial case được review, thông tin và reflection của nhóm.
Các thư mục `runs/`, `transcripts/` đang được gitignore: review dữ liệu rồi dùng
`git add -f <từng-file-đã-review>` để nộp log được chọn, giữ các lần chạy khác
để đối chiếu; không chỉ chọn lần điểm cao nhất. Không commit `.env`, `.venv`,
ticket tạo ra hoặc dữ liệu thật.

URL chung do người dùng yêu cầu:
https://github.com/anhtri04/K4-Day04-Prompt-Engineering-Tool-Calling-Labs-NguyenAnhTri-02730

Việc push code không tự nộp VLearn. Từng thành viên phải nộp cùng URL trên
tài khoản VLearn của mình sau khi hoàn tất các phần evidence và thông tin nhóm.

Tài liệu API tham khảo: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling),
[Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling),
[Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
Provider Groq dùng [API tương thích OpenAI](https://console.groq.com/docs/openai)
và [local tool calling](https://console.groq.com/docs/tool-use/overview).
