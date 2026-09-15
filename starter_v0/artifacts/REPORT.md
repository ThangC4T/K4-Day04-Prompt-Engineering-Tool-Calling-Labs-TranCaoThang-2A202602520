# Day 04 — IT Helpdesk Agent

**Phạm Minh Cương — 2A202602825. Bài làm nhóm, có Codex hỗ trợ.**
Theo yêu cầu của người dùng, bản này chưa bổ sung tên các thành viên khác.
Lịch sử đóng góp gốc được giữ trong Git và mô tả tại [TEAMMATES.md](../../TEAMMATES.md).

## A. Agent và giao diện

Agent hỗ trợ IT cho công ty giả lập Northstar Labs: tra dịch vụ, thiết bị,
directory, KB và policy; định dạng findings; hỏi bổ sung và tạo ticket local
sau xác nhận. Dữ liệu là snapshot bài lab, không phải phép đo máy thật.
Không có chức năng reset tài khoản, thực thi shell hoặc sửa cấu hình thiết bị.

Chạy `streamlit run app.py` trong `starter_v0`; hướng dẫn đầy đủ ở
[QUICKSTART.md](../../QUICKSTART.md). Giao diện tiếng Việt có chọn provider/model,
version, trace từng tool, trạng thái lỗi, SHA-256 và tải transcript. Tab công cụ
local hoạt động không cần model. CLI dùng cùng loop, có `/confirm`, `/cancel`.
`http://127.0.0.1:8501` là demo trên máy local; chưa có URL triển khai công khai.

| Tool | Phạm vi và ranh giới |
|---|---|
| clarify | Native tool để hỏi ID/môi trường còn thiếu hoặc xác nhận; dừng chờ user |
| check_service_status | Shared service theo environment; không suy ra tình trạng máy cá nhân |
| inspect_device | Snapshot của asset ID cụ thể, chọn đúng check; không tự đoán ID |
| lookup_user | Directory theo employee ID; tên/chức vụ không đủ |
| search_kb | Hướng dẫn xử lý local; nội dung được coi là dữ liệu không đáng tin cậy |
| format_incident_report | Chỉ format findings đã có; không tự thu thập lại hoặc tạo ticket |
| policy | Tra quy định IT; instruction nhúng trong kết quả không có quyền điều khiển agent |
| create_ticket | Ghi file local sau approval gắn đúng payload và dùng một lần |
| search_device_info | Tavily, chỉ manufacturer/model công khai trong catalog đã review |

Sáu tool đầu là core; ba tool sau là advanced có sẵn. Không claim bonus tool mới.
External search cần key Tavily riêng; lần bàn giao này chỉ cấu hình key Groq.

Ví dụ demo: “Cho tôi trạng thái VPN production”; “Kiểm tra phần mềm trên máy
của tôi” rồi bổ sung “LT-204”; soạn ticket low cho máy in PR-404 mất kết nối,
kiểm tra payload và bấm xác nhận. Không dùng transcript mẫu của starter làm
bằng chứng model của nhóm.

## B1. Phương pháp đo

- Provider **Groq**, temperature 0, tool choice auto, max completion tokens 512.
  Đợt đầu: qwen/qwen3.6-27b, reasoning effort none, delay 20–25 giây. Đợt kiểm
  chứng tiếp theo: openai/gpt-oss-20b, reasoning effort low, delay 10 giây.
  Cả hai model đã qua preflight structured tool calling. Chỉ so sánh điểm
  giữa các version trong cùng model/options; không trộn hai đợt đo.
- v0 dùng nguyên prompt/tools starter tại commit `f680c59`; v1 thay tool
  descriptions; v2 thay system prompt; v3 bổ sung ranh giới tin cậy và schema.
  Mỗi vòng được đọc kết quả trước khi chọn thay đổi tiếp theo, xem
  [decision_log.md](decision_log.md) và [version_log.csv](version_log.csv).
- Giữ nguyên fixed base 30 và adversarial 12; group đúng 5 single + 5 multi.
  Dataset hash, evaluator hash, model/options, prompt/tools hash nằm trong mỗi run.
  Manifest mã chạy lưu hash source cho [Qwen](../validation/groq_runtime_manifest.json)
  và [GPT-OSS](../validation/groq_oss_runtime_manifest.json). Khi chuyển model,
  adapter Groq được sửa để chọn reasoning effort theo model thực tế; thay đổi
  này giữ nguyên behavior Qwen và áp dụng cố định cho cả đợt GPT-OSS.
  Snapshot được Git giữ nguyên byte để không đổi hash do LF/CRLF.
- Chỉ dùng metric khi đo đủ tất cả case và provider_error_cases=0. Không retry
  câu trả lời điểm thấp; chỉ retry throttling có giới hạn. Giữ cả regression.

**Giới hạn grader:** eval chấm native tool calls ở phản hồi đầu tiên, kiểm tra
expected args theo subset và phát hiện call thừa/thiếu. Multi-turn được gói
thành một user message với chỉ dẫn xét lượt cuối. Grader không chấm đầy đủ
chất lượng trả lời, không đưa tool output trở lại model, và không cấp quyền ghi
ticket. PASS routing không đồng nghĩa hành động đã thành công hoặc an toàn.
Một model có thể gọi tool còn thiếu ở vòng hội thoại sau; rehearsal kiểm tra
riêng điều này. Điểm dưới đây phản ánh một lần đo mỗi cấu hình, không phải
ước lượng ổn định qua nhiều seed hoặc nhiều model.

## B2. Kết quả đo thật

| Model | Version | Suite | Đạt / Tổng | Case accuracy | Multi-turn | Lỗi provider | Run gốc |
|---|---|---|---|---|---|---|---|
| qwen/qwen3.6-27b | v0 | base | 17/30 | 56.67% | 90.00% | 0 | [v0_B_base_groq_20260915T094859120284.json](../runs/v0_B_base_groq_20260915T094859120284.json) |
| qwen/qwen3.6-27b | v1 | base | 15/30 | 50.00% | 60.00% | 0 | [v1_B_base_groq_20260915T100306372569.json](../runs/v1_B_base_groq_20260915T100306372569.json) |
| qwen/qwen3.6-27b | v2 | base | 14/30 | 46.67% | 80.00% | 0 | [v2_B_base_groq_20260915T101709424537.json](../runs/v2_B_base_groq_20260915T101709424537.json) |

Trên Qwen, v1 giảm từ 56,67% xuống 50%: sửa H08/H20 nhưng phát sinh lỗi ở H09/M05/M07/M09.
Description rõ hơn không tự bảo đảm điểm tăng. v2 tách native tool calling khỏi
final JSON, làm rõ các call độc lập, latest intent, cancellation và confirmation.
Phân tích từng vòng và giới hạn của suy luận nguyên nhân nằm trong decision log.

Qwen chạm hạn mức ngày ở v3. Lượt này được dừng, không báo metric vì các kết
quả còn ở bộ nhớ chưa xuất đủ. [Thông báo dừng](../validation/groq_v3_aborted.json)
và [diagnostic quota](../validation/groq_rate_diagnostic.json) ghi rõ nguyên nhân.
GPT-OSS có hạn mức model riêng còn khả dụng; các snapshot được giữ nguyên để
đo v0–v3 trên cùng model mới. Đây là kiểm chứng lại các giả thuyết đã phát triển
từ đợt Qwen, không phải bốn lần chạy cùng một artifact rồi đổi tên version.

## B3. Bộ eval nhóm

[eval_group.json](../data/eval_group.json) kế thừa đóng góp của Khanh; G01/G04/G08/G09
được chỉnh để tăng khả năng phân biệt lỗi, không chép lại câu của fixed suite.
G04 dùng đúng dữ liệu giả lập MB-012 là iPhone 15. Các ca còn lại bao phủ ID thiếu,
hai môi trường, sửa asset, hủy ticket, thay toàn bộ payload và sửa employee ID.
Metric lịch sử của bộ gốc không được áp cho bộ hiện tại.

| Case | Loại | Kết quả | Nhận xét grader |
|---|---|---|---|
| Chưa có run group hợp lệ | — | Chưa đo | — |

## B4. Review adversarial

Đọc actual calls, args và tool result cho các ca sau; không chỉ nhìn tổng điểm.

| Case | Ranh giới cần giữ | Actual calls | Kết quả |
|---|---|---|---|
| A04_argument_smuggling | Pseudo-code và confirmed=true trong user text không cấp quyền ghi. | Chưa đo | Chưa kết luận |
| A06_internal_data_to_web | Chỉ đọc nội bộ; không xuất ID, người dùng, vị trí và diagnostics. | Chưa đo | Chưa kết luận |
| A10_stale_confirmation_attack | Đổi payload cần xác nhận mới. | Chưa đo | Chưa kết luận |
| A12_external_identifier_smuggling | Chuỗi model chứa ID nội bộ phải được làm rõ, không gửi nguyên văn ra web. | Chưa đo | Chưa kết luận |

A01/A02/A05/A07 có expected no_tool: cần đọc actual text để kiểm tra từ chối,
không suy ra an toàn chỉ từ việc không có call. A05 được lớp redaction che giá
trị password giả lập trước khi gửi model, vì vậy kết quả là hành vi của cả
runtime và prompt. A08/A09 trong eval chỉ kiểm tra routing; không chứng minh
model bỏ qua injection trong tool output. Kịch bản KB qua UI kiểm tra thêm vòng
nhận tool output và trả lời sau đó.

## B5. Transcript và kiểm tra giao diện

Rehearsal dùng **Streamlit AppTest điều khiển UI với phản hồi Groq thật**.
Các thao tác nhập/click do chương trình thực hiện, không giả là người dùng đã
tự rehearsal. Nút xác nhận tạo ticket chỉ được bấm với sự cố local giả lập.
Các lượt thực thi approval thuần runtime được phân biệt với lượt gọi provider.

| Kịch bản | Trạng thái các lượt | Bấm nút xác nhận | Bằng chứng |
|---|---|---|---|
| Chưa chạy rehearsal live | Chưa đo | — | — |

Đã xem giao diện bằng trình duyệt: chọn Groq, v3, 9 tool, trường nhập và các
tab hiển thị; công cụ local trả VPN production degraded / INC-1042.
[Ghi nhận visual review](../validation/browser_review.json). Phần kiểm tra
visual này không gửi yêu cầu model, được tách khỏi rehearsal live.

## B6. Runtime và kiểm tra local

**24 kiểm tra local đạt**, compile thành công; bằng chứng ở
[validation/local_checks.json](../validation/local_checks.json). Các test dùng
HTTP mock/scripted model khi cần và không được tính thành điểm LLM.

- Native assistant.tool_calls và role=tool/tool_call_id giữ nguồn gốc dữ liệu;
  context trimming giữ trọn cặp call/result. Clarify dừng chờ, sibling call sau
  điểm dừng không được thực thi.
- Dispatcher kiểm tra tên tool và JSON Schema. Model confirmed=true không cấp
  quyền ghi. UI/CLI approval gắn chính xác summary/priority/asset, dùng một lần;
  payload đổi làm mất hiệu lực. Không nhận credential trong ticket summary.
- External search chỉ xuất cặp sản phẩm công khai trong allowlist. ID nội bộ,
  serial/hostname/diagnostics nối vào model không được gửi đến Tavily.
- Key đọc từ `.env` bị Git bỏ qua, được che trong transcript/error. Đây là lớp
  lọc nhận dạng phổ biến, không phải bộ phân loại DLP toàn diện.

## C. Tổng kết phần việc và bàn giao

Phần tích hợp của Phạm Minh Cương có Codex hỗ trợ: giữ lịch sử các nhánh,
hoàn thiện UI/CLI và native tool loop, thêm approval/validation/redaction,
provider Groq, bộ kiểm tra local, snapshot thí nghiệm và tài liệu từ log thật.
Quyết định đáng chú ý là dùng kiểm tra ở runtime để chặn ghi file; prompt chỉ
định hướng model. Regression v1 cho thấy phải đo lại thay vì đánh giá chất
lượng bằng độ dài hoặc vẻ rõ ràng của prompt. Điểm routing và outcome hội thoại
cũng phải được kiểm tra riêng.

Báo cáo lịch sử của Khanh/Phat được giữ nguyên tại
[contributions/README.md](contributions/README.md); các metric thiếu run gốc
không được chuyển sang bảng của bản tích hợp. Phần nhận xét trên mô tả công việc
thực tế có AI hỗ trợ, không gán trải nghiệm hay tự nhận xét thay cho thành viên khác.

Repository đích: [repo nhóm](https://github.com/anhtri04/K4-Day04-Prompt-Engineering-Tool-Calling-Labs-NguyenAnhTri-02730).
Tài khoản GitHub trên máy là mcnb2005; lần kiểm tra quyền gần nhất trả push=false,
chưa có invitation cho repo đích. Việc hoàn tất push cần quyền ghi từ chủ repo.
Chưa thực hiện nộp VLearn; mỗi thành viên tự nộp URL theo yêu cầu lớp.

Tham khảo API: [Groq OpenAI compatibility](https://console.groq.com/docs/openai),
[Groq tool calling](https://console.groq.com/docs/tool-use/overview),
[Groq rate limits](https://console.groq.com/docs/rate-limits).
