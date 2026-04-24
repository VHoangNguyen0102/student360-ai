"""Core Backend Client: gọi sang NestJS backend (internal APIs) bằng HTTP async.

Vì sao file này quan trọng:
- AI service thường cần *đọc dữ liệu nghiệp vụ* (profile sinh viên, giao dịch,
      kế hoạch tài chính, v.v.). Nguồn dữ liệu “chuẩn” nằm ở backend NestJS.
- Để tránh coupling vào DB schema nghiệp vụ, dự án đặt rule:

      **AI service KHÔNG ghi trực tiếp vào business tables**.
      Mọi thao tác ghi/side-effect đi qua NestJS API (đã có auth, validation, audit).

Cấu hình liên quan (xem `app/config.py`):
- BACKEND_URL: base URL của NestJS (mặc định http://localhost:3000)
- BACKEND_INTERNAL_API_KEY: API key nội bộ để AI service gọi backend

Thiết kế thường gặp (khi implement):
- Tạo `httpx.AsyncClient` dùng chung (singleton) với `base_url=BACKEND_URL`.
- Gắn header auth cho mọi request (ví dụ: Authorization/Bearer hoặc x-api-key).
- Đặt timeout hợp lý + retry có kiểm soát (đừng retry các lệnh không idempotent).
- Khi app shutdown có thể đóng client (tương tự DB pool), nếu cần.

Gợi ý: nếu bạn muốn trace luồng nghiệp vụ, hãy tìm các “tools” trong
`app/domains/finance/.../tools/` xem chỗ nào cần gọi backend. Khi đó backend client
được implement sẽ là adapter tập trung cho mọi call.
"""

# Hiện tại chưa implement (Phase 1A).
# Khi cần, implement bằng `httpx.AsyncClient` (đã có trong dependencies).
