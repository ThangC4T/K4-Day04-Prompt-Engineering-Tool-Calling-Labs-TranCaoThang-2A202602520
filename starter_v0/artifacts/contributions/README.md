# Hồ sơ đóng góp được giữ lại khi tích hợp

Các file dưới đây giữ nội dung từ branch của thành viên để bảo toàn nguồn gốc
đóng góp, gồm cả self-reflection đã có. Đây là **tài liệu lịch sử chưa được xác
minh bằng run JSON trong repository**, không phải báo cáo kết quả của bản hiện
tại. Không dùng các số PASS/FAIL trong thư mục này để điền metric hiện tại.

| Thư mục | Branch nguồn | Commit nguồn | Nội dung |
|---|---|---|---|
| `khanh/` | `origin/khanh` | `d24c84248ec451c79fa4fed531b94b7429908dc2` | Báo cáo và self-reflection Khanh, version log, bộ eval nhóm gốc |
| `phat/` | `origin/phat` | `25cbaca024261a9588fc8f07712f0b10a4b134b1` | Báo cáo bảo mật, kịch bản trình bày, version log, bộ eval nhóm gốc |

Các file được lấy từ Git và ghi UTF-8; xuống dòng được chuẩn hóa LF. Tên thư
mục dựa trên branch, không suy đoán họ tên hoặc MSSV của tác giả. Git history
của các branch đã được tích hợp; không tạo commit dưới danh tính thành viên khác.

Hai branch có mô tả model, điểm số và run khác nhau. Tại thời điểm rà soát,
không có file `runs/*.json` hoặc transcript thực tế được nêu trong các báo cáo
đó trong cây Git tương ứng. `samples/` là dữ liệu ví dụ của starter, không thay
thế bằng chứng nhóm. Vì vậy chưa thể đối chiếu metric, hashes, lỗi provider,
tool results, request external hoặc file ticket đã được tạo.

`khanh/version_log.csv` có trường `prompt_hash` của v0 không khớp dạng hash
trong `artifact_version`; giữ nguyên để tác giả đối chiếu với run gốc. Các
tuyên bố như "giữ run đẹp nhất" và suy luận về năng lực một model từ vài case
trong tài liệu lịch sử không được kế thừa thành kết luận của báo cáo hiện tại.

Bộ eval hiện tại kế thừa Khanh và sửa G01, G04, G08, G09. Do đầu vào đã đổi,
kết quả trên bộ cũ không được áp sang bộ mới. Xem [báo cáo hiện tại](../REPORT.md)
và [eval hiện tại](../../data/eval_group.json). Khi nhận được log gốc, cần giữ
nguyên tất cả lần chạy có liên quan, phân biệt artifact/dataset/model/harness
của từng run, và ghi cả regression thay vì chỉ chọn điểm cao nhất.
