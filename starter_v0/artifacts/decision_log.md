# Nhật ký quyết định từ thực nghiệm thật

Provider: Groq. Đợt phát triển dùng `qwen/qwen3.6-27b`, reasoning effort `none`;
đợt kiểm chứng dùng `openai/gpt-oss-20b`, reasoning effort `low`. Cả hai dùng
temperature 0, tool choice `auto`, max completion tokens 512. Chỉ so sánh điểm
trong cùng model và cấu hình. Không sửa fixed cases hoặc retry câu trả lời điểm thấp.

## v0 → v1

Baseline: [`v0_B_base_groq_20260915T094859120284.json`](../runs/v0_B_base_groq_20260915T094859120284.json).
Đo đủ 30/30 ca, không lỗi provider; 17 ca đạt (56,67%), multi-turn 9/10.

Quan sát và quyết định trước khi chạy v1:

- H07 và H20 trả JSON tự nhận đã format nhưng không có tool call. Mô tả
  formatter ở v1 yêu cầu gọi structured tool thực sự và giữ findings đã có.
- H10/H11 hỏi bằng văn bản thay vì gọi `clarify`; H11 còn đề nghị tên đầy đủ
  dù directory chỉ nhận employee ID. Mô tả `clarify` nêu rõ cơ chế dừng chờ
  phải được gọi qua tool; `lookup_user` yêu cầu ID cụ thể.
- H08 từ chối yêu cầu nấu ăn rồi gọi `clarify` không cần thiết. Tool description
  phân biệt yêu cầu thiếu thông tin IT với yêu cầu ngoài phạm vi.
- H19 tự chọn staging từ môi trường mơ hồ. Mô tả status yêu cầu clarify khi
  chưa xác định được môi trường, chỉ dùng mặc định production khi không nhắc tới.
- H13/H15/H16/H17/H18/M08 chỉ gọi một trong nhiều tool cần thiết. Vòng v1 giữ
  prompt gốc, làm rõ phạm vi và mỗi input cần call riêng; chưa thể khẳng định
  description đủ để sửa hành vi thực hiện tuần tự này.

v1–v3 ban đầu được chuẩn bị từ code review. Sau baseline, v1 được sửa thêm
hai mô tả nêu trên và cập nhật hash; các snapshot tương lai kế thừa cùng sửa
đổi. Giả thuyết được chọn trước lần đo v1, không điền kết quả suy đoán.

Giới hạn: evaluator chỉ chấm **lần phản hồi model đầu tiên**. Thiếu một call
trong bộ nhiều call không chứng minh loop hội thoại sẽ không gọi nó ở vòng
sau. Báo cáo cần phân biệt điểm routing với kết quả hội thoại hoàn chỉnh.

## v1 → v2

Run: [`v1_B_base_groq_20260915T100306372569.json`](../runs/v1_B_base_groq_20260915T100306372569.json).
Đo đủ 30/30 ca, không lỗi provider; **15/30 (50%)**, giảm 6,67 điểm phần trăm
so với v0. Single-turn tăng từ 8/20 lên 9/20 nhưng multi-turn giảm 9/10 → 6/10.

- H08 và H20 được sửa; H09, M05, M07, M09 phát sinh regression. H09 gọi
  formatter với findings rỗng khi user chỉ hỏi khả năng; M07 gọi clarify dù
  user đã hủy. M05/M09 viết câu hỏi xác nhận vào final JSON thay vì native call.
- H07/H10/H11 vẫn dùng văn bản mô phỏng hành động. Nhiều ca yêu cầu song song
  vẫn chỉ có một call. H18 thậm chí chỉ hứa sẽ tra user và thiết bị.
- Không chấp nhận giả thuyết “description rõ hơn sẽ tự cải thiện tổng điểm”
  sau lần đo này. Không chạy lại v1 chỉ để tìm lần có điểm tốt hơn.

Quyết định cho v2: giữ tools của v1; thay system prompt để tách giai đoạn
native tool calling khỏi JSON trả lời cuối, yêu cầu các call độc lập trong
cùng phản hồi, dùng clarify cho ID/môi trường thiếu, giữ latest intent và
confirmation của đúng payload. Câu hỏi khả năng và hủy toàn bộ không gọi tool.
Các quy tắc đều tổng quát, không chứa ID hoặc câu chữ của fixed eval.

## v2 → v3

Run: [`v2_B_base_groq_20260915T101709424537.json`](../runs/v2_B_base_groq_20260915T101709424537.json).
Đo đủ 30/30 ca, không lỗi provider; **14/30 (46,67%)**, multi-turn 8/10.
So với v1, H07/H10/M05/M09 được sửa, nhưng H01/H02/H03/H04/H06 phát sinh lỗi.

Rủi ro lớn hơn tổng điểm: H01 nói VPN operational dù không có tool call,
trong khi snapshot thật là degraded. H02 bịa cấu hình/diagnostics thiết bị;
H04 bịa tên người, email và asset. H03 trả một dictionary giả nội dung KB.
H15/H16 cũng tạo bảng/trạng thái không có bằng chứng. Đây là failure về độ
tin cậy, không được coi là “trả lời hợp lý” hay thành công thay cho tool.

V3 thay prompt dài theo chủ đề bằng quy trình chọn bước tiếp theo: phân biệt
meta/cancel, thiếu thông tin, ticket và các truy vấn cần dữ liệu; khẳng định
chưa có dữ liệu nào được fetch khi bắt đầu, cấm giả lập tool result và buộc
dùng evidence thật trước câu trả lời. Giữ rõ các call độc lập, đồng thời bổ
sung ranh giới dữ liệu không đáng tin cậy, credential và external search;
schema được siết để runtime từ chối arguments ngoài khai báo.

V3 cũng làm rõ sau khi user duyệt payload thì create_ticket chỉ chuẩn bị bước
approval của runtime; không thể nhận quyền ghi từ boolean hoặc lời xác nhận
giả. Chỉ nút UI / lệnh CLI cho payload đang hiển thị mới thực thi ghi file.

## Dừng Qwen ở quota và kiểm chứng trên GPT-OSS

Groq trả 429 TPD: limit 200000, used 199568, request 2958 token. Đã dừng
tiến trình v3, không tiếp tục gọi vô ích. Partial run không có đầy đủ JSON kết
quả, do đó **không ghi điểm v3 Qwen**. Xem hai file diagnostic/aborted trong
`validation/`; organization ID đã được che trước khi chia sẻ.

Preflight GPT-OSS 20B trên cùng Groq thành công. Chọn reasoning effort low
(GPT-OSS không nhận giá trị none của Qwen). Giữ nguyên bốn snapshot đã xây
dựng từ các lỗi Qwen và đo lại theo thứ tự v0 → v1 → v2 → v3 trên GPT-OSS,
đọc từng run trước khi tiếp tục. Log Qwen được giữ để người đọc thấy nguồn
gốc các thay đổi; không so điểm Qwen v2 với GPT-OSS v3 như cùng cấu hình.

Baseline GPT-OSS lần đầu có 7 BadRequestError 400: model phát sinh tool không
khai báo tên JSON. File `v0_B_base_groq_20260915T104056831596.json` được giữ
nhưng không đưa vào metric hợp lệ. Sau diagnostic, dùng tùy chọn chính thức
`disable_tool_validation` ở API để **chuyển kiểm tra về dispatcher local**.
Validator local vẫn chặn tool ngoài danh sách, schema sai và write thiếu
approval. Khi model gọi JSON sai, grader ghi nhận lỗi routing thay vì mất
model output trong HTTP 400. Cấu hình này được giữ cho tất cả run so sánh mới.
Đã bổ sung test chứng minh tool lạ không được thực thi ngay cả khi registry
tình cờ có function cùng tên. Không đổi fixed cases hoặc expected calls.


GPT-OSS v0 sau sửa tương thích: `v0_B_base_groq_20260915T105253005362.json`,
15/30 (50%), không lỗi provider, multi-turn 6/10. H12 định gọi create_ticket
confirmed=true nhưng dispatcher trả needs_confirmation, không ghi ticket.
Các call giả JSON/json được ghi nhận đúng là undeclared_tool. Tiếp tục kiểm
chứng v1 vì mô tả clarify, capability boundary và xác nhận giải quyết trực
tiếp các nhóm lỗi đang thấy; giữ nguyên snapshot để so với đợt Qwen.
