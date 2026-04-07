# Phân Tích Công Nghệ AI Trong Thư Mục `student360-ai`

## 1. Mục tiêu phân tích

Tài liệu này phân tích **toàn bộ stack AI** đang được dùng trong dự án `student360-ai`, bao gồm:

- Công nghệ lõi để chạy AI (LLM, framework, orchestration).
- Cách hệ thống gọi tool và lấy dữ liệu nghiệp vụ.
- Hạ tầng vận hành AI (API, worker, queue, DB, logging, security).
- Mức độ hoàn thiện hiện tại: phần nào đã chạy thực tế, phần nào mới là khung (TODO).
- Rủi ro kỹ thuật và khuyến nghị nâng cấp.

Phân tích bám trên mã nguồn hiện có, không giả định ngoài code.

---

## 2. Tổng quan nhanh các công nghệ AI chính

| Nhóm                 | Công nghệ đang dùng                        | Vai trò                                                      |
| -------------------- | ------------------------------------------ | ------------------------------------------------------------ |
| Ngôn ngữ             | Python 3.12                                | Nền tảng triển khai toàn bộ AI service                       |
| API Framework        | FastAPI + Uvicorn                          | Expose endpoint chat/classify/anomaly cho backend gọi nội bộ |
| LLM Orchestration    | LangChain Core                             | Chuẩn hóa chat model, messages, tool binding                 |
| LLM Provider (Cloud) | Google Gemini qua `langchain-google-genai` | Mô hình chính trên cloud (mặc định)                          |
| LLM Provider (Local) | Ollama qua `langchain-ollama`              | Chạy local model (ví dụ `qwen2.5:3b`)                        |
| Agent Pattern        | Manual ReAct loop (không LangGraph)        | Tự điều khiển vòng lặp model -> tool -> model                |
| Routing Pattern      | Rule-based keyword + LLM fallback          | Orchestrator phân luồng câu hỏi về specialist agent          |
| Data Layer           | PostgreSQL (asyncpg)                       | Đọc dữ liệu tài chính, lưu dữ liệu AI (`ai_*`)               |
| Queue/Worker         | Redis + ARQ (định hướng)                   | Nền cho anomaly/report/background jobs                       |
| Logging              | structlog                                  | Log có cấu trúc cho quan sát hệ thống                        |
| Validation/Schema    | Pydantic v2 + pydantic-settings            | Kiểm soát schema request/response + env config               |
| HTTP Integration     | httpx (định hướng), service token auth     | Giao tiếp nội bộ với NestJS backend                          |

---

## 3. Phân tích kiến trúc AI theo lớp

## 3.1 Lớp mô hình (Model Layer)

### 3.1.1 Cơ chế chọn provider

Hệ thống dùng biến môi trường `LLM_PROVIDER` để chọn runtime model:

- `gemini`: gọi model cloud qua `ChatGoogleGenerativeAI`.
- `ollama`: gọi model local qua `ChatOllama`.

Thiết kế này cho phép:

- Dễ chuyển giữa cloud và local để tối ưu chi phí.
- Dùng local LLM cho dev/test hoặc môi trường hạn chế API key.

### 3.1.2 Gemini stack

- Package chính: `langchain-google-genai` + `google-genai`.
- Default model chat: `gemini-2.5-flash-lite`.
- Có khai báo model embedding: `gemini-embedding-001` (đang ở mức config/định hướng).

### 3.1.3 Ollama stack

- Package chính: `langchain-ollama`.
- Default model local: `qwen2.5:3b`.
- Docker Compose có profile `local-llm` để bật service ollama riêng.

### 3.1.4 Nhận xét kỹ thuật

Ưu điểm:

- Đa provider, giảm lock-in.
- Có thể fallback môi trường linh hoạt.

Điểm cần lưu ý:

- Chưa thấy cơ chế fallback tự động cloud <-> local khi provider lỗi.
- Chưa có routing theo loại tác vụ (task-based model selection).

---

## 3.2 Lớp Agent và Orchestration

### 3.2.1 Orchestrator Pattern

Kiến trúc dùng **parent orchestrator** để định tuyến sang agent chuyên biệt:

- `finance`
- `career`
- `content`
- `personalization`

### 3.2.2 Thuật toán routing

Routing hiện tại theo 3 bước:

1. Ưu tiên `context_hint` từ client.
2. Nếu `auto`: match keyword rule-based.
3. Nếu không match: gọi LLM classifier để chọn agent.

Cấu trúc này là hybrid routing, cân bằng:

- Tốc độ (keyword nhanh, không tốn token).
- Khả năng hiểu ngữ cảnh (LLM fallback).

### 3.2.3 Maturity theo agent

- `Finance Agent`: đã có triển khai thực tế (tool-calling + session memory in-process).
- `Career Agent`: TODO (placeholder).
- `Content Agent`: TODO.
- `Personalization Agent`: TODO.

Kết luận: hệ thống multi-agent ở mức **khung kiến trúc tốt**, nhưng hiện chỉ `Finance` là chạy được theo logic AI thực.

---

## 3.3 Lớp Tool Calling (phần cốt lõi của AI thực dụng)

### 3.3.1 Cách thực thi tool

Dự án không dùng LangGraph mà tự viết vòng lặp ReAct:

- `llm.bind_tools(tools)` để model biết danh sách tool.
- Lặp tối đa `max_iterations`.
- Với mỗi `tool_call`: parse args -> thực thi tool -> append `ToolMessage` -> model suy luận tiếp.

Ý nghĩa:

- Toàn quyền kiểm soát flow.
- Dễ debug từng bước.
- Ít phụ thuộc framework orchestration nặng.

### 3.3.2 Bộ tool hiện có (đang dùng mạnh)

Trong domain Finance/Six Jars, đã có nhiều tool read-centric:

- Xem số dư, phân bổ, thống kê lọ.
- Lấy giao dịch gần nhất, top chi tiêu, tìm kiếm giao dịch.
- Theo dõi budget, tổng hợp tháng, so sánh tháng.
- Trend chi tiêu và auto-transfer schedule.
- Tool affordability `can_afford_this` (đánh giá khả năng chi trả).

Đây là dấu hiệu hệ thống đang theo hướng **AI có grounding dữ liệu thật**, không trả lời thuần ngôn ngữ.

### 3.3.3 Chất lượng tool engineering

Điểm tốt:

- Có chuẩn hóa serialize kiểu dữ liệu DB (Decimal, UUID, datetime).
- Có giới hạn an toàn (ví dụ limit tối đa).
- Có tách layer composition để gom tool/prompt gọn.

Điểm còn thiếu:

- Một số tool/nhánh vẫn TODO (scholarship tools, receipt tools).
- Chưa thấy circuit breaker/retry policy chuẩn hóa riêng cho từng tool DB-call.

---

## 3.4 Lớp Prompt Engineering

Hệ thống có tách prompt thành file riêng theo domain:

- Prompt router classifier (yêu cầu JSON output rõ ràng).
- Prompt Finance 6 Jars (tiếng Việt, nguyên tắc hành vi, phạm vi trả lời).
- Prompt classify và affordability theo bài toán.

Cách tổ chức này tốt cho:

- Bảo trì prompt độc lập với business code.
- A/B test prompt sau này dễ hơn.

Rủi ro nhỏ:

- Có lỗi typo/chữ trong prompt tiếng Việt ở một vài dòng, có thể ảnh hưởng nhẹ đến nhất quán output.

---

## 3.5 Lớp API AI

### 3.5.1 Endpoint đã hoạt động

- `POST /api/v1/chat`: gọi orchestrator, trả reply + usage.
- `POST /api/v1/classify`: pipeline phân loại 2 bước (preference exact match -> LLM fallback).
- `POST /api/v1/classify/override`: lưu preference người dùng.
- `GET /api/v1/anomalies`, `PATCH /api/v1/anomalies/{id}/read`: đọc/đánh dấu cảnh báo.

### 3.5.2 Đặc điểm AI trong API layer

- Có xử lý quota lỗi Gemini (`RESOURCE_EXHAUSTED`/429) ở chat endpoint.
- Có fallback tổng hợp phản hồi khi final assistant message rỗng sau tool-calling.
- Có log tool usage để truy vết hành vi model.

### 3.5.3 Phần API chưa hoàn thiện

Các endpoint `career`, `content`, `feed`, `receipt` mới là router placeholder TODO.

---

## 3.6 Lớp dữ liệu và trí nhớ hội thoại

### 3.6.1 Data access

- DB dùng `asyncpg` pool lazy-init.
- Truy vấn SQL trực tiếp trong tool cho tốc độ và kiểm soát cao.

### 3.6.2 Memory cho hội thoại

- Session memory đang là **in-process dict** theo `thread_id`.
- Có lock theo thread để tránh race condition trong 1 process.

Đánh giá:

- Phù hợp MVP/single instance.
- Không phù hợp scale ngang (multi-replica) vì memory không shared.

### 3.6.3 Hướng nâng cấp rõ ràng trong code

- Comment đã chỉ ra cần Redis/Postgres-backed memory cho production multi-replica.

---

## 3.7 Lớp worker/background AI

Cấu hình phụ thuộc cho ARQ + Redis đã có, nhưng worker thực tế đa số đang TODO:

- `anomaly.py`: TODO
- `embeddings.py`: TODO
- `feed_ranking.py`: TODO
- `reports.py`: TODO

Kết luận:

- Kiến trúc đã chuẩn bị cho AI async workloads.
- Chưa đạt mức production-complete ở background intelligence.

---

## 3.8 Lớp quan sát, bảo mật, và vận hành

### 3.8.1 Observability

- Dùng `structlog` với local console / non-local JSON renderer.
- Có log route agent, dispatch, tool used, lỗi invoke.

Thiếu hiện tại:

- Chưa thấy metric backend (Prometheus/OpenTelemetry) trong code hiện tại.
- Chưa có tracing phân tán end-to-end từ NestJS sang FastAPI.

### 3.8.2 Security

- Service-to-service auth qua Bearer token (`AI_SERVICE_SECRET`).
- Cấu hình tách theo env bằng `pydantic-settings`.

Điểm cần tăng cường:

- Chưa thấy guard chi tiết theo scope endpoint.
- Chưa thấy policy mã hóa/rotation secret ở tầng app (phụ thuộc môi trường triển khai).

### 3.8.3 Deployment

- Docker hóa sẵn, có profile bật local LLM riêng.
- Thiết kế tách service AI khỏi backend chính là hợp lý cho scale độc lập.

---

## 4. Đánh giá mức độ hoàn thiện công nghệ AI

## 4.1 Những gì đã “thật sự chạy AI”

1. Multi-provider LLM (Gemini/Ollama) đã đi vào code thực.
2. Orchestrator routing chạy được với keyword + LLM fallback.
3. Finance agent có vòng lặp tool-calling hoạt động.
4. Bộ tools Six Jars đã khá đầy đủ cho use case tài chính.
5. Classify pipeline đã có ưu tiên preference trước khi gọi LLM.

## 4.2 Những gì mới ở mức khung hoặc TODO

1. Career/Content/Personalization agents chưa triển khai logic.
2. Scholarship tools chưa có implement thật.
3. Receipt OCR và các worker nền (anomaly/report/feed/embedding) chưa hoàn tất.
4. Bộ test nhiều file còn TODO.
5. Session memory chưa distributed-ready.

---

## 5. Nhận định kiến trúc AI tổng thể

Dự án đang đi theo triết lý **AI ứng dụng thực dụng**:

- Tập trung vào tool-calling gắn dữ liệu thật.
- Ưu tiên kiến trúc nhẹ, dễ kiểm soát (manual loop, không LangGraph).
- Có khả năng chạy cloud lẫn local model.

Mức trưởng thành hiện tại có thể đánh giá:

- **Kiến trúc:** 8/10 (rõ lớp, tách trách nhiệm tốt, dễ mở rộng).
- **Tính năng AI production hiện hữu:** 5.5/10 (mạnh ở Finance, thiếu ở các domain còn lại).
- **Độ sẵn sàng scale production:** 5/10 (cần hoàn thiện memory phân tán, worker, test, observability sâu).

---

## 6. Khuyến nghị nâng cấp ưu tiên (thực tế, ngắn gọn)

## 6.1 Ưu tiên cao (nên làm trước)

1. Hoàn thiện worker anomaly + report và wiring ARQ cron thật.
2. Chuyển chat session memory sang Redis/Postgres để hỗ trợ multi-replica.
3. Bổ sung test tối thiểu cho `chat`, `classify`, `router`, `six_jars tools`.
4. Chuẩn hóa retry/timeout/error mapping cho toàn bộ tool DB-call.

## 6.2 Ưu tiên trung bình

1. Implement scholarship tools và bật cross-context reasoning tài chính + học bổng.
2. Triển khai content/career/personalization agent theo đúng interface orchestrator.
3. Bổ sung metric + tracing để theo dõi token, latency, tool success rate.

## 6.3 Ưu tiên tối ưu dài hạn

1. Xây policy dynamic model selection (task-aware: classify/chat/planning).
2. Cân nhắc semantic memory retrieval khi hội thoại dài.
3. Thiết kế guardrail/response policy tập trung cho nhiều domain AI.

---

## 7. Kết luận

`student360-ai` đã có nền tảng công nghệ AI khá vững cho một service tách riêng:

- FastAPI + LangChain + Gemini/Ollama + tool-calling manual loop là bộ khung hợp lý.
- Use case tài chính 6 lọ đã có chiều sâu thực thi dữ liệu thật.

Tuy nhiên, hệ thống hiện mới hoàn thiện mạnh ở một domain (Finance). Để đạt mức AI platform hoàn chỉnh cho Student360, cần ưu tiên hoàn tất các domain còn lại, worker nền, test, và năng lực vận hành production (distributed memory + observability sâu).
