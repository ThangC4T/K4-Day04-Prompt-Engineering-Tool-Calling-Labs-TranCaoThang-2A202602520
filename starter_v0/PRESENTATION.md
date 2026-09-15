# Kịch bản demo IT Helpdesk

Trạng thái: kịch bản chuẩn bị, chưa có rehearsal với model thật.

1. Mở `streamlit run app.py`; giới thiệu mock data và tab Công cụ local. Chạy VPN production để thấy tool trả dữ liệu mà không cần key.
2. Khi có key, chọn v0 rồi gửi cùng một scenario cho v3 trong hội thoại mới. Mở trace, so args, nguồn dữ liệu và version hashes. Chỉ nói có cải thiện khi run thật chứng minh được.
3. Hỏi “Máy của tôi không vào được mạng”, bổ sung asset ID ở lượt sau. Cho thấy agent giữ context và không đoán ID.
4. Yêu cầu ticket cho sự cố giả lập. Cho thấy chưa có ghi file trước nút xác nhận; kiểm tra payload rồi bấm tạo. Trình bày ticket ID từ tool result.
5. Trình bày một case adversarial từ report với run JSON và review thực tế. Nếu chưa có key/run, chỉ giới thiệu thiết kế boundary, không gọi đây là demo model đã đạt.

Tài liệu nguồn của thành viên được giữ tại [contributions/phat/PRESENTATION.md](artifacts/contributions/phat/PRESENTATION.md).
