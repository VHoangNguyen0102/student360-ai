# Student360 AI — Tổng Quan Kiến Trúc Hệ Thống

> Version: 2.0 (MVP Optimized)  
> Date: 22/03/2026  
> Scope: Tổng quan hệ thống + Chi tiết kiến trúc Router & Native Tools (Không LangGraph, Không Vector DB)

## 1. Mục tiêu tài liệu

Tài liệu này mô tả kiến trúc tổng quan của hệ thống AI tách repo (`student360-ai`) khỏi monorepo backend. Hệ thống sử dụng kiến trúc **Parent Router & Native Tool Calling**, tối ưu luồng xử lý bằng HTTP/SSE cho trải nghiệm thời gian thực và xử lý bất đồng bộ cho các tác vụ nền, đảm bảo tính gọn nhẹ, dễ bảo trì và triển khai nhanh chóng.

## 2. Kiến trúc tổng thể

```text
Mobile App (React Native)
        |
        | HTTPS (REST / SSE)
        v
NestJS Backend (student360)
  - Auth, RBAC, business CRUD
  - Public API contract giữ nguyên
  - AI Gateway (thin proxy)
        |
        | Internal HTTP + Service Token
        v
student360-ai (repo riêng - FastAPI)
  - API Layer (REST & SSE Endpoints)
  - Router Layer (Intent Classification)
  - Sub-Agents Layer (Prompt & Tools Logic)
  - Core AI (LLM Native Tool Calling)
  - Workers Layer (ARQ jobs - Background processing)
        |
        +--> PostgreSQL (shared - Relational Data)
        +--> Redis (shared - Cache & Queue)
        +--> AI Model API (Gemini / Ollama Local)
```

## 3. Boundary trách nhiệm

### 3.1 NestJS Backend chịu trách nhiệm

- Authentication, authorization, user/session domain.
- Toàn bộ business transaction write cho modules nghiệp vụ.
- Public API cho mobile/web.
- Làm Proxy chuyển tiếp request từ App sang AI Service.

### 3.2 student360-ai chịu trách nhiệm

- Phân luồng ý định (Intent Routing) và xử lý logic hội thoại.
- Tool calling lấy dữ liệu qua API nội bộ, tổng hợp insights.
- Thực thi các tác vụ nền (phân loại tự động, tìm bất thường).
- **Tuyệt đối không** ghi đè trực tiếp dữ liệu nghiệp vụ thật (chỉ ghi vào bảng `ai_*`).

## 4. Cấu trúc thư mục (student360-ai)

```text
app/
  api/v1/
    chat_stream.py   # Endpoint dùng SSE cho real-time chat
    tasks_sync.py    # Endpoint REST cho các tác vụ phân loại/phân tích
  core/
    router.py        # Parent Agent: Phân tích Intent và điều phối
    llm_client.py    # Wrapper gọi API Gemini/Ollama, xử lý Function Calling
  agents/
    finance_agent.py # Xử lý prompt & tool liên quan 6 Lọ
    scholar_agent.py # Xử lý prompt & tool Học bổng
    career_agent.py  # Xử lý prompt & tool Việc làm
  tools/
    finance_tools.py # Các hàm fetch data từ NestJS (get_jar_balance,...)
  workers/
    anomaly.py       # Job quét bất thường
    reports.py       # Job sinh báo cáo tháng
```

## 5. Luồng hoạt động tổng quát

### 5.1 Luồng chat AI trực tiếp (Real-time SSE)

1. App gọi endpoint Stream (giao tiếp 1 chiều) ở NestJS.
2. NestJS forward request sang FastAPI (`student360-ai`).
3. **Router** nhận diện Intent nhanh (VD: Finance hay Career).
4. Request chuyển đến **Sub-Agent** tương ứng. Sub-Agent nạp System Prompt và danh sách Tools.
5. LLM quyết định Tool cần gọi (Native Tool Calling). Backend AI thực thi Tool lấy data từ NestJS.
6. LLM tổng hợp data và sinh chữ. FastAPI dùng **SSE** đẩy từng chunk text về thẳng Mobile App.
7. Lưu log hội thoại vào PostgreSQL (bảng `ai_chat_sessions`).

### 5.2 Luồng tác vụ nền (Async - Không dùng SSE)

1. Worker (ARQ) chạy theo cron (VD: 23:00 hằng ngày).
2. Query data từ PostgreSQL (hoặc qua NestJS API).
3. Ném data vào Prompt để LLM phân tích (tìm bất thường, tổng hợp báo cáo).
4. Ghi kết quả vào các bảng `ai_*` (VD: `ai_anomaly_alerts`).
5. App gọi REST API qua NestJS để lấy dữ liệu này lên UI.

## 6. Chi tiết trọng tâm: Finance Agent (6 Lọ + Scholarships)

### 6.1 AI Chat 6 Lọ (multi-turn, tool-aware)

- Agent sử dụng các tools read-only: `get_jar_balance`, `get_recent_transactions`, `get_budget_status`,...
- Cung cấp sẵn số dư và % phân bổ hiện tại vào System Prompt ngay từ đầu để LLM không tốn lượt gọi Tool cho các câu hỏi phổ thông.
- Dùng giao thức SSE để phản hồi chữ theo thời gian thực.

### 6.2 Phân loại giao dịch (Classify) - Tối ưu 2 bước

Không sử dụng Vector Database để hệ thống nhẹ và nhanh nhất có thể:

1. **Exact Keyword Match:** So khớp từ khóa cứng theo cấu hình người dùng lưu trong `ai_user_preferences_6jars` (Nhanh, không gọi LLM).
2. **LLM Fallback:** Nếu không khớp từ khóa, đưa tên giao dịch và danh sách các Lọ vào Prompt. LLM đọc, tự suy luận và trả về định dạng JSON (`suggested_jar_code`, `confidence`).

### 6.3 Cross-Context Reasoning (Kết hợp 6 Lọ & Scholarships)

Khi câu hỏi chạm đến cả 2 domain (VD: "Chi lố quá có nên nộp học bổng không?"):

- **Router** nhận diện 2 Intent.
- Kích hoạt cả `finance_tools` và `scholar_tools` để gom dữ liệu.
- Đưa **toàn bộ Context** vào một Prompt duy nhất cho LLM đánh giá tổng thể và đưa ra lời khuyên cuối cùng (không cần Multi-agent giao tiếp chéo).

### 6.4 Write Actions có xác nhận

Luồng thực thi thay đổi dữ liệu (tạo giao dịch, chuyển Lọ):

- AI chỉ đóng vai trò **Suggest** (đề xuất action bằng JSON trả về App).
- App hiển thị popup Confirm.
- Khi user bấm OK, App gọi thẳng REST API của NestJS để thực thi transaction. AI Service đứng ngoài quá trình ghi data này.

## 7. Database Design & Ownership

### 7.1 PostgreSQL (Shared)

- **Nhóm bảng nghiệp vụ (NestJS owns, AI read):** `jars`, `financial_transactions`, `scholarships`,... AI Service chỉ read hoặc gọi qua Internal API.
- **Nhóm bảng AI (AI owns write):**
  - `ai_chat_sessions`, `ai_messages`
  - `ai_usage_logs`
  - `ai_anomaly_alerts`
  - `ai_user_preferences_6jars` (Lưu keyword mapping cho bước 1 classify)

_(Lưu ý: Không cài đặt và không sử dụng extension pgvector trong giai đoạn này)._

### 7.2 Redis (Shared)

Dùng cho: Cache kết quả classify ngắn hạn, Rate limit API, và làm Queue cho ARQ Workers.

## 8. NFR (Non-Functional Requirements) & Roadmap

- **Observability:** Log đầy đủ request, response time và số lượng Token tiêu thụ.
- **Tiến độ MVP:** 1. Hoàn thiện luồng Chat Router + SSE. 2. Tích hợp Tool fetch data nội bộ. 3. Hoàn thiện luồng Classify bằng Prompt (Không Vector DB). 4. Test luồng bằng Local Model (Ollama/Qwen 2.5 3B) trước khi gắn API key thật.
