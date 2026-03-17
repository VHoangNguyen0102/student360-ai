# Student360 AI — Tổng Quan Kiến Trúc Hệ Thống

> Version: 1.1  
> Date: 17/03/2026  
> Scope: Tổng quan hệ thống + chi tiết đầy đủ cho Finance (6 Lọ)

## 1. Mục tiêu tài liệu

Tài liệu này mô tả kiến trúc tổng quan của hệ thống AI tách repo (`student360-ai`) khỏi monorepo backend, đồng thời mô tả **đầy đủ** chức năng mục tiêu của 6 Lọ (bao gồm hiện tại và kế hoạch hoàn thiện).

## 2. Kiến trúc tổng thể

```text
Mobile App (React Native)
        |
        | HTTPS
        v
NestJS Backend (student360)
  - Auth, RBAC, business CRUD
  - Public API contract giữ nguyên
  - AI Gateway (thin proxy)
        |
        | Internal HTTP + Service Token
        v
student360-ai (repo riêng)
  - FastAPI API Layer
  - Agents Layer (LangGraph)
  - Core AI Layer (LLM, Embedding, Vector, Memory)
  - Workers Layer (ARQ jobs)
        |
        +--> PostgreSQL + pgvector (shared)
        +--> Redis (shared)
        +--> Gemini API
```

## 3. Boundary trách nhiệm

### 3.1 NestJS Backend chịu trách nhiệm

- Authentication, authorization, user/session domain.
- Toàn bộ business transaction write cho modules nghiệp vụ.
- Public API cho mobile/web.
- Là lớp tương thích ngược (backward compatibility).

### 3.2 student360-ai chịu trách nhiệm

- Orchestrate AI workflow theo agent.
- Tool calling, classify, anomaly detection, insights.
- Embedding pipeline, semantic retrieval.
- Quản lý hội thoại AI và usage logs.

### 3.3 Nguyên tắc DB ownership

- `student360-ai` chỉ **read** business tables khi cần phân tích.
- `student360-ai` **write** vào nhóm bảng `ai_*` và embedding tables.
- Các write tác vụ nghiệp vụ quan trọng (ví dụ tạo transaction thật) không ghi trực tiếp DB, mà gọi qua API backend.

## 4. Các thành phần chính trong repo student360-ai

```text
app/
  api/v1/
    chat.py, classify.py, ...
  agents/
    orchestrator/
    finance/
    career/
    content/
    personalization/
  core/
    llm.py, embeddings.py, vector_store.py, memory.py, backend_client.py
  workers/
    anomaly.py, embeddings.py, reports.py, feed_ranking.py
  models/
  utils/
```

## 5. Luồng hoạt động tổng quát

### 5.1 Luồng chat AI

1. App gọi endpoint AI ở NestJS.
2. NestJS forward request sang `student360-ai`.
3. API layer định tuyến vào agent phù hợp.
4. Agent gọi tools để lấy dữ liệu nghiệp vụ từ backend nội bộ.
5. LLM tổng hợp kết quả và trả response.
6. Lưu logs + conversation + metrics.
7. Trả response về app qua NestJS.

### 5.2 Luồng tác vụ nền (async)

1. Worker chạy theo cron hoặc event.
2. Đọc data từ PostgreSQL.
3. Tính toán/analyze (anomaly, embeddings, reports).
4. Ghi kết quả vào `ai_*` tables.
5. Backend đọc dữ liệu này để hiển thị cho người dùng.

## 6. Chi tiết trọng tâm: Finance Agent (6 Lọ + Scholarships)

## 6.1 Finance Agent scope

Finance Agent là domain trọng điểm giai đoạn đầu, gồm 2 trục:
- 6 Lọ: classify, chat tư vấn, thống kê, anomaly alerts, insights, và write actions có xác nhận.
- Scholarships: gợi ý học bổng phù hợp, theo dõi hạn nộp, cảnh báo kỳ hạn.

## 6.2 6 Lọ — Mục tiêu chức năng đầy đủ (end-state)

### 6.2.1 AI Chat 6 Lọ (multi-turn, tool-aware)

Agent có thể trả lời chính xác theo dữ liệu người dùng bằng bộ tools read-only:
- `get_jar_balance`
- `get_jar_allocations`
- `get_jar_statistics`
- `get_recent_transactions`
- `get_top_expenses`
- `search_transactions`
- `get_budget_status`
- `get_monthly_summary`
- `compare_months`
- `get_spending_trend`
- `get_auto_transfers`

Yêu cầu end-state:
- Hỗ trợ multi-round tool chaining (tối đa N rounds).
- Có history summarization khi session dài (semantic retrieval).
- Hỗ trợ streaming response (SSE) cho trải nghiệm realtime.
- System prompt có thể inject số dư và % phân bổ hiện tại (không cần gọi tool cho câu hỏi đơn giản).

### 6.2.2 Classify giao dịch vào lọ (3 bước + cache)

Pipeline mục tiêu:
1. Exact keyword match theo `ai_user_preferences_6jars`.
2. Vector similarity theo `transaction_embeddings` với ngưỡng tin cậy khác nhau cho `confirmed_by=user` và `confirmed_by=ai`.
3. LLM fallback khi 2 bước trên không chắc chắn.

Kết quả trả về: `suggested_jar_code`, `confidence`, `source`.

### 6.2.3 Override học theo người dùng

Khi user sửa gợi ý, hệ thống lưu mapping keyword -> jar để tăng độ chính xác cho lần sau và cập nhật embedding độ tin cậy cao.

### 6.2.4 Anomaly Detection (daily + signals)

Worker chạy cron hằng ngày (23:00), phát hiện:
- `spike_expense`
- `near_threshold`
- `recurring_increase`

Alerts lưu vào `ai_anomaly_alerts`, có API để list + mark read.

### 6.2.5 Monthly Insights & Reports

- Sinh báo cáo cuối tháng: tóm tắt thu/chi, jar dư/thiếu, top chi tiêu, gợi ý điều chỉnh.
- Lưu báo cáo vào bảng AI + expose API để app hiển thị.

### 6.2.6 Spending Forecast

- Dự báo chi tiêu cuối tháng theo pattern 2-3 tháng gần nhất.
- Cảnh báo sớm jar nào có nguy cơ âm.

### 6.2.7 Write Actions có xác nhận

Luồng 2 bước (Suggest → Confirm) cho các write tools:
- `create_transaction`
- `transfer_between_jars`
- `update_transaction`

Quy tắc an toàn:
- Không ghi dữ liệu thật nếu chưa có confirm rõ ràng trong cùng session.
- Audit log đầy đủ ở backend.

### 6.2.8 Bulk Categorization

- `POST /api/v1/ai/6jars/classify/bulk` để phân loại hàng loạt (import CSV).

### 6.2.9 Cross-Context Reasoning (6 Lọ + Scholarships)

- Cho phép một câu hỏi kích hoạt nhiều context (finance + scholarships) để đưa ra khuyến nghị tổng hợp.

## 6.3 Chức năng Scholarships (mở rộng ngay sau 6 Lọ)

Scholarships được đặt cùng Finance Agent để hỗ trợ ra quyết định tài chính tổng hợp.

### 6.3.1 Scholarship Matching

Dựa trên profile + học lực + nhu cầu tài chính để gợi ý học bổng phù hợp.

Kết quả:
- Danh sách học bổng đề xuất.
- Match score theo hồ sơ.
- Giải thích vì sao phù hợp hoặc không phù hợp.

### 6.3.2 Scholarship Due Monitoring

- Theo dõi deadline nộp hồ sơ.
- Cảnh báo các mốc cần chuẩn bị (CV, bài luận, giấy tờ).
- Nhắc nhở điều kiện duy trì học bổng (nếu có).

### 6.3.3 Scholarship Advisory

- Gợi ý chiến lược nộp học bổng theo thứ tự ưu tiên.
- Ước lượng tác động tới ngân sách học tập theo từng kịch bản.

## 6.4 Luồng xử lý tích hợp 6 Lọ + Scholarships

Ví dụ truy vấn: "Tháng này tôi chi hơi quá, có nên nộp học bổng X không?"

1. Agent lấy budget status từ 6 Lọ.
2. Agent lấy dữ liệu học bổng từ Scholarships tools.
3. Agent tính disposable cashflow sau chi tiêu thiết yếu.
4. Agent ước lượng tác động tài chính nếu theo học bổng.
5. Agent trả khuyến nghị có giải thích + cảnh báo.

## 7. Các domain khác (chỉ cấu trúc tổng)

### 7.1 Career Agent

- Job matching.
- CV parsing/review.
- Cover letter generation.
- Mock interview.

### 7.2 Content Agent

- Content drafting/co-pilot.
- Auto tagging metadata.
- Pre-moderation (toxicity/spam/policy).

### 7.3 Personalization Agent

- Feed ranking.
- AI summarization.
- Smart notifications.

## 8. Database design và tác vụ sử dụng

## 8.1 PostgreSQL (shared, primary)

### Nhóm bảng nghiệp vụ (backend owns, AI read)

- jars, financial_transactions, auto_transfer_schedules
- scholarships, scholarship_programs, scholarship_requirements (nếu có theo schema thực tế)
- profile/users và các bảng metadata liên quan

Dùng cho tác vụ:
- Tool query dữ liệu tài chính thực tế.
- Scholarship eligibility inputs.
- Monthly insights.

### Nhóm bảng AI (AI owns write)

- ai_chat_sessions
- ai_messages
- ai_usage_logs
- ai_anomaly_alerts
- ai_user_preferences_6jars
- ai_message_embeddings
- transaction_embeddings
- scholarship_related_embeddings (khi mở rộng scholarships semantic search)

Dùng cho tác vụ:
- Lưu hội thoại và lịch sử tương tác AI.
- Theo dõi cost/latency/tokens.
- Anomaly alert lifecycle.
- Personalization classify theo user behavior.
- Semantic retrieval cho classify/chat.

## 8.2 pgvector (trong PostgreSQL)

Dùng cho:
- Similar transaction lookup (classify step 2).
- Semantic memory retrieval.
- Scholarship case similarity (mở rộng).

Chiến lược:
- Bắt đầu bằng pgvector để đơn giản hóa vận hành.
- Chỉ tách vector DB riêng khi volume/latency vượt ngưỡng thực tế.

## 8.3 Redis (shared)

Dùng cho:
- Cache kết quả classify/chat ngắn hạn.
- Rate limit theo user.
- Queue backend cho workers (ARQ).
- Conversation checkpoint tạm thời.

## 9. API và phương thức giao tiếp

## 9.1 Public path (không đổi cho app)

App vẫn gọi NestJS endpoint cũ. NestJS làm proxy sang AI service.

## 9.2 Internal path NestJS <-> student360-ai

- Giao tiếp HTTP nội bộ có service token.
- Header chuẩn: `Authorization: Bearer <AI_SERVICE_SECRET>` hoặc `X-Service-Key`.
- Timeout/retry cấu hình ở BackendClient để tránh treo chuỗi request.

## 9.3 Đồng bộ và bất đồng bộ

- Sync: chat, classify, hỏi đáp finance.
- Async: anomaly job, embedding job, monthly reports.

## 10. Phi chức năng (NFR)

- Observability: log cấu trúc, trace request id, metrics latency/tokens.
- Reliability: retry cho Gemini transient errors.
- Security: service-to-service auth + least privilege DB user.
- Cost control: usage logs + limit theo ngày.
- Scalability: scale ngang API và workers độc lập.

## 11. Roadmap triển khai ngắn hạn

1. Hoàn tất feature parity 6 Lọ trên `student360-ai`.
2. Chuyển `ai.service.ts` ở NestJS thành thin proxy.
3. Bật anomaly worker production.
4. Thêm Scholarships tools vào Finance Agent.
5. Bổ sung observability dashboard cho AI usage.

## 12. Definition of Done cho giai đoạn Finance (6 Lọ + Scholarships)

- Chat 6 Lọ trả lời đúng theo dữ liệu thật.
- Classify đạt độ chính xác tương đương hệ hiện tại.
- Alerts được tạo/đọc/đánh dấu ổn định.
- Scholarships recommendation có score + explanation + guardrails.
- App không cần thay đổi API phía client.
- Không có write trực tiếp business tables từ AI service.
