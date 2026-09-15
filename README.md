# Day 04 Lab — IT Helpdesk Agent

**Bản tích hợp của nhóm:** xem [QUICKSTART.md](QUICKSTART.md) để chạy UI, kiểm tra local và chạy thực nghiệm. Thành viên đã xác nhận: **Phạm Minh Cương — 2A202602825**. Đã kết nối Groq; kết quả đo và trạng thái hoàn thiện nằm trong [báo cáo](starter_v0/artifacts/REPORT.md).

## Tổng quan

Trong bài lab này, học viên xây dựng và cải tiến một IT Helpdesk Agent có khả
năng chọn tool, truyền arguments, xử lý hội thoại nhiều lượt và bảo vệ các ranh
giới an toàn khi làm việc với dữ liệu nội bộ hoặc hành động ghi.

Starter đã cung cấp agent loop, nhiều model provider, các tool helpdesk, dữ liệu
giả lập và evaluator. Nhiệm vụ chính của học viên là dùng evidence từ
run thật để cải thiện:

- `starter_v0/artifacts/system_prompt.md`;
- `starter_v0/artifacts/tools.yaml`.

Đây là bài lab về prompt engineering và tool calling. Mục tiêu không phải chỉ
làm câu trả lời nghe hay, mà là làm cho hành vi chọn tool có thể đo lường, giải
thích và tái lập.

## Mục đích học tập

Sau bài lab, học viên cần có khả năng:

1. Phân biệt lỗi routing, lỗi arguments, lỗi multi-turn và lỗi safety boundary.
2. Hiểu tool name, description và JSON schema đều là một phần của prompt.
3. Biết khi nào agent cần hỏi lại thay vì tự đoán identifier.
4. Biết khi nào một yêu cầu cần nhiều tool.
5. Xử lý correction, cancellation và context carry-over trong hội thoại.
6. Xin xác nhận trước khi thực hiện action làm thay đổi trạng thái.
7. Phân tách dữ liệu nội bộ với dữ liệu được phép gửi ra external service.
8. Dùng run log và metric để kiểm chứng một thay đổi prompt/tool declaration.

## Bối cảnh

Agent làm việc trong service desk của công ty giả lập. Người dùng có thể yêu
cầu:

- kiểm tra trạng thái VPN, email, SSO, Wi-Fi hoặc printing;
- kiểm tra diagnostic snapshot của một asset;
- tra cứu tài khoản và thiết bị được cấp;
- tìm hướng dẫn trong IT knowledge base;
- đọc chính sách IT nội bộ;
- format findings thành incident report;
- tạo ticket sau khi xác nhận;
- tìm thông tin công khai về model thiết bị trên web.

Mọi employee, asset, incident và policy trong repo đều là dữ liệu giả lập.

## Input được cung cấp

Học viên nhận được:

| Input | Nội dung |
|---|---|
| Agent runtime | `agent.py`, `chat.py`, provider adapters và tool loop |
| Baseline prompt | `artifacts/system_prompt.md`, cố ý chưa hoàn chỉnh |
| Tool declarations | `artifacts/tools.yaml`, cần cải thiện bằng evidence |
| Tool implementations | 9 tool nội bộ, action và external-search có sẵn |
| Mock data | 9 assets, 10 users, service status, 11 KB articles và IT policies |
| Fixed eval | Base, extension và adversarial datasets |
| Team eval template | `data/eval_group.json` để nhóm tự viết case |
| Preflight | Script kiểm tra structured tool calling của model provider |
| Report template | `artifacts/REPORT.md` |

## Tool có sẵn

### Core tools

- `clarify`: hỏi bổ sung thông tin hoặc xin xác nhận.
- `search_kb`: tìm hướng dẫn trong knowledge base local.
- `check_service_status`: đọc trạng thái shared service giả lập.
- `inspect_device`: đọc inventory và diagnostic snapshot của asset.
- `lookup_user`: đọc directory record theo employee ID.
- `format_incident_report`: format findings đã có thành báo cáo.

### Advanced tools có sẵn

- `policy`: tìm trong IT policy local.
- `create_ticket`: tạo ticket local sau explicit confirmation.
- `search_device_info`: dùng Tavily tìm specs, driver hoặc support page công khai.

Các advanced tools có sẵn không được tính là tool mới do nhóm tự xây.

## Ranh giới an toàn

Agent cần tôn trọng các nguyên tắc sau:

- Không tự đoán asset ID hoặc employee ID.
- Không yêu cầu hoặc lưu password, token, API key, MFA/OTP hay recovery code.
- Không coi pseudo-code, JSON do user nhập hoặc fake tool result là confirmation.
- Confirmation cũ mất hiệu lực khi payload action thay đổi.
- Không thực thi tool không được khai báo.
- Không làm theo instruction được nhúng trong KB, policy hoặc web result.
- Chỉ manufacturer, model và query type công khai được gửi ra external search.
- Không gửi asset ID, employee ID, serial, hostname, location hoặc diagnostics ra ngoài.

## Expectation đầu ra bắt buộc

Khi hoàn thành core lab, nhóm cần nộp:

| Deliverable | Expectation |
|---|---|
| `system_prompt.md` | Prompt cuối cùng được cải thiện từ evidence, không hard-code case IDs |
| `tools.yaml` | Description/schema rõ ràng, đồng bộ với registry |
| `version_log.csv` | Có `v0`, `v1`, `v2`, `v3`, hypothesis, metric và run file |
| Base runs | Run JSON cho baseline và các version cải tiến |
| Team eval | Đúng 10 case original: 5 single-turn + 5 multi-turn |
| Adversarial evidence | Chạy fixed suite và phân tích ít nhất 3 security cases |
| Transcript | Có evidence cho normal, missing-info, multi-turn và action boundary |
| UI | Chat hoạt động, hiển thị tool calls, args, result/error và artifact version |
| Report | Mô tả agent, version evidence, failures, safety review và reflection |

Điều kiện để một run được dùng làm evidence:

```text
provider_error_cases == 0
measured_cases == total_cases
```

Tool result có error hoặc empty result vẫn cần review thủ công, kể cả khi routing
được evaluator chấm PASS.

## Bộ eval hiện tại

| Suite | Cases | Vai trò |
|---|---:|---|
| Base | 30: 20 single + 10 multi | Core routing, args, multi-tool và context |
| Group | Đúng 10: 5 single + 5 multi | Case original do nhóm tự thiết kế |
| Extension | 10 | Policy, confirmed ticket và external search |
| Adversarial | 12 | Prompt injection, forged state, data exfiltration và tool abuse |

Automatic grader kiểm tra tool names, expected argument subset, missing/extra
tool calls và no-tool behavior. Chất lượng câu trả lời, dữ liệu nhạy cảm, tool
execution result và chất lượng experiment phải được review thủ công.

## Tool mới của nhóm — Bonus

Học viên không bắt buộc phải viết thêm tool để hoàn thành core lab.

Nhóm có thể nhận bonus khi xây một capability mới có ý nghĩa, ví dụ:

- network diagnostics;
- approved software catalog;
- meeting-room inventory;
- ticket status lookup.

Tool bonus chỉ được công nhận khi có đủ:

- `tools/<tool_name>/TOOL.md`;
- implementation chạy được;
- đăng ký trong `tools/__init__.py`;
- declaration/schema trong `artifacts/tools.yaml`;
- mock data hoặc API setup phù hợp;
- smoke test;
- team eval case;
- evidence trong UI/transcript/report;
- guardrail tương ứng với side effect và dữ liệu.

Việc chỉ đổi tên tool cũ hoặc thêm folder rỗng không được tính bonus.

## Các file chính

| Path | Vai trò |
|---|---|
| `starter_v0/artifacts/system_prompt.md` | Prompt artifact đang được tối ưu |
| `starter_v0/artifacts/tools.yaml` | Interface model nhìn thấy |
| `starter_v0/data/eval_base.json` | Fixed core eval |
| `starter_v0/data/eval_group.json` | Team-authored eval template |
| `starter_v0/data/eval_helpdesk_extension.json` | Advanced tool eval |
| `starter_v0/data/eval_adversarial.json` | Security/red-team eval |
| `starter_v0/helpdesk_data/` | Mock operational data |
| `starter_v0/company_policy/` | Mock IT policy data |
| `starter_v0/artifacts/REPORT.md` | Submission report template |

Xem [TOOL-SETUP.md](TOOL-SETUP.md) để cài môi trường và kiểm tra từng tool.
Xem [LAB-GUIDE.md](LAB-GUIDE.md) để tham khảo một quy trình làm bài gợi ý.
Xem [SUBMISSION-GUIDE.md](SUBMISSION-GUIDE.md) để xem hướng dẫn cách nộp bài lab

Không nộp `.env`, API key, `.venv`, cache, generated tickets hoặc dữ liệu thật.
