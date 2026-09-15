---
name: create_ticket
track: bonus
kind: action
provider: local_ticket_store
requires_env: []
inputs: [summary, priority, asset_id, confirmed]
outputs: [status, ticket_id, path]
side_effect: local_file_write
requires_confirmation: true
---
# create_ticket

Creates a local mock helpdesk ticket under `tickets/`. It returns
`needs_confirmation` and writes nothing unless `confirmed` is explicitly true.
It rejects invalid asset IDs and ticket summaries containing credentials,
tokens, MFA values, or recovery codes.

## Boundary của runtime tích hợp

Tool dispatcher không coi boolean model truyền là consent. UI button hoặc CLI /confirm cấp phép đúng một payload đã hiển thị; payload thay đổi phải xác nhận lại. Evaluator không cấp quyền ghi, nên routing PASS không chứng minh tạo ticket thành công.
