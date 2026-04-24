# Bản Đồ Cấu Trúc Thư Mục Dự Án student360-ai

## 1. Mục đích tài liệu

Tài liệu này giúp bạn trả lời nhanh 2 câu hỏi:

- Thư mục nào chịu trách nhiệm phần nào?
- File nào đang làm gì, file nào là khung TODO?

Phạm vi: toàn bộ dự án `student360-ai` (ưu tiên phần `app/` vì đây là lõi runtime).

---

## 2. Cấu trúc cấp cao của dự án

```text
student360-ai/
  .env.example
  docker-compose.yml
  Dockerfile
  Makefile
  pyproject.toml
  README.md
  app/
  docs/
  tests/
  list_models_check.py
  test_agent_issue.py
  test_gemini_tool.py
```

### Vai trò từng phần ở root

- `.env.example`: Mẫu biến môi trường (provider LLM, DB, Redis, secret nội bộ).
- `pyproject.toml`: Khai báo dependency, Python version, optional deps theo phase.
- `README.md`: Hướng dẫn chạy local/cloud, trạng thái phase.
- `Dockerfile`: Build container chạy FastAPI service.
- `docker-compose.yml`: Chạy `ai-service`, profile tùy chọn cho `ollama` local.
- `Makefile`: Lệnh tắt build/up/down/logs cho docker compose.
- `list_models_check.py`: Script hỗ trợ kiểm tra model/provider.
- `test_agent_issue.py`: Script debug hành vi agent/tool calling.
- `test_gemini_tool.py`: Script smoke-test tool calling với Gemini/Ollama.
- `docs/`: Tài liệu kiến trúc, kế hoạch phase, báo cáo phân tích.
- `tests/`: Unit/integration tests.
- `app/`: Mã nguồn runtime chính.

---

## 3. Thư mục app: trung tâm của hệ thống

```text
app/
  __init__.py
  config.py
  main.py
  agents/
  api/
  core/
  models/
  utils/
  workers/
```

### 3.1 File nền tảng trong app

- `app/main.py`
    - Entry point FastAPI.
    - Đăng ký router đang hoạt động (`chat`, `classify`, `anomalies`).
    - Các router phase sau đang để comment.

- `app/config.py`
    - Quản lý toàn bộ settings bằng Pydantic Settings.
    - Chứa các biến quan trọng: `LLM_PROVIDER`, `GEMINI_API_KEY`, `OLLAMA_*`, `DATABASE_URL`, `REDIS_URL`, `AI_SERVICE_SECRET`.

---

## 4. app/agents: lớp AI Orchestration và Specialist

```text
app/agents/
  orchestrator/
  finance/
  career/
  content/
  personalization/
```

## 4.1 app/agents/orchestrator

### Vai trò

- Điều phối request đến agent chuyên biệt.
- Quyết định route bằng `context_hint`, keyword và fallback LLM classifier.

### File chính

- `agent.py`: Orchestrator runtime, nhận message và dispatch sang specialist.
- `router.py`: Logic route theo ưu tiên (hint -> keyword -> LLM fallback).
- `classifier.py`: Classifier LLM trả về agent + confidence.
- `keywords.py`: Bộ từ khóa định tuyến rule-based.
- `prompts.py`: Prompt cho classifier router.
- `registry.py`: Bản đồ `agent_id -> agent instance`.
- `placeholder.py`: Agent tạm cho domain chưa triển khai.
- `state.py`: TypedDict state chuẩn cho orchestrator.

### Trạng thái

- Đã hoạt động cho routing.
- Domain chưa xong sẽ trả lời qua placeholder message.

## 4.2 app/agents/finance

### Vai trò

- Agent đã triển khai thực tế mạnh nhất hiện tại.
- Tập trung use case 6 jars và một phần affordability.

### File chính

- `agent.py`: Finance agent runtime, gọi vòng lặp tool calling.
- `react_loop.py`: Vòng lặp ReAct thủ công (không LangGraph).
- `composition.py`: Gộp system prompt + danh sách tools.
- `prompts.py`: Shim re-export prompt theo cấu trúc mới.
- `prompts_affordability.py`: Prompt cho bài toán affordability.

### Nhánh six_jars

- `six_jars/prompts_agent.py`: System prompt cho trợ lý tài chính 6 lọ.
- `six_jars/prompts_classify.py`: Prompt classify jar code.
- `six_jars/prompts_affordability.py`: Prompt affordability chuyên biệt.
- `six_jars/tools/jars.py`: Bộ tool đọc dữ liệu tài chính (balance, transactions, budgets, trend, compare...).

### Nhánh scholarships

- `scholarships/prompts.py`: Prompt học bổng (đang mức cơ bản/TODO).
- `scholarships/tools/matching.py`: Khung tool matching học bổng (TODO).

### finance/tools

- `affordability.py`: Tool đánh giá khả năng chi trả, đã có logic chạy.
- `goals.py`: TODO.
- `loans.py`: TODO.
- `receipt.py`: TODO.

### Trạng thái

- Finance là domain chạy thật hiện tại.
- Một số nhánh mở rộng đang ở mức TODO.

## 4.3 app/agents/career

### Vai trò

- Dự kiến xử lý CV, phỏng vấn, job matching.

### File

- `agent.py`, `prompts.py`, `tools/cv.py`, `tools/interview.py`, `tools/jobs.py`.

### Trạng thái

- Chủ yếu là placeholder TODO, chưa có logic production.

## 4.4 app/agents/content

### Vai trò

- Dự kiến moderation, tagging, generation nội dung.

### File

- `agent.py`, `prompts.py`, `tools/moderation.py`, `tools/tagging.py`, `tools/generation.py`.

### Trạng thái

- TODO, chưa triển khai thực tế.

## 4.5 app/agents/personalization

### Vai trò

- Dự kiến ranking feed, tóm tắt cá nhân hóa.

### File

- `agent.py`, `prompts.py`, `tools/feed.py`, `tools/summary.py`.

### Trạng thái

- TODO, chưa triển khai thực tế.

---

## 5. app/api: lớp HTTP endpoint

```text
app/api/v1/
  chat.py
  classify.py
  anomalies.py
  career.py
  content.py
  feed.py
  receipt.py
  internal.py
```

### Endpoint đã có logic

- `chat.py`
    - Endpoint chat chính.
    - Gọi orchestrator.
    - Có fallback khi model trả final message rỗng.
    - Có log tool usage.

- `classify.py`
    - Pipeline classify 2 bước:
        1. Exact keyword preference trong DB.
        2. LLM fallback.
    - Có endpoint override để lưu preference người dùng.

- `anomalies.py`
    - Đọc danh sách cảnh báo bất thường.
    - Đánh dấu alert đã đọc.

### Endpoint chưa hoàn thiện

- `career.py`: TODO.
- `content.py`: TODO.
- `feed.py`: TODO.
- `receipt.py`: TODO.
- `internal.py`: TODO webhook nội bộ sau job async.

---

## 6. app/core: hạ tầng lõi dùng chung

```text
app/core/
  database.py
  chat_session_store.py
  backend_client.py
  llm/
```

### File chính

- `database.py`
    - Tạo và quản lý asyncpg pool.
    - Chuẩn hóa DSN từ SQLAlchemy style sang asyncpg style.

- `chat_session_store.py`
    - In-process session memory theo `thread_id`.
    - Có lock chống race condition theo thread.
    - Ghi chú rõ: muốn scale multi-replica thì nên chuyển Redis/Postgres-backed.

- `backend_client.py`
    - Khung client để gọi backend nội bộ.
    - Hiện đang TODO.

### app/core/llm

- `__init__.py`: Hàm `get_llm` dùng thống nhất toàn hệ thống.
- `factory.py`: Chọn provider theo cấu hình.
- `providers/gemini.py`: Build ChatGoogleGenerativeAI.
- `providers/ollama.py`: Build ChatOllama.

---

## 7. app/models: schema request/response

```text
app/models/
  chat.py
  classify.py
  affordability.py
  career.py
  content.py
```

### Vai trò

- Chứa Pydantic models cho API layer.
- Chuẩn hóa contract giữa service AI và caller.

### Trạng thái

- `chat.py`, `classify.py` đã dùng thực tế.
- `career.py`, `content.py` đang TODO.
- `affordability.py` hỗ trợ domain finance nâng cao.

---

## 8. app/utils: tiện ích dùng chung

- `auth.py`
    - Verify service token (Bearer) giữa hệ thống nội bộ.

- `logging.py`
    - Cấu hình structlog.
    - Local dùng console renderer, môi trường khác dùng JSON renderer.

---

## 9. app/workers: tác vụ nền

```text
app/workers/
  anomaly.py
  embeddings.py
  feed_ranking.py
  reports.py
```

### Vai trò dự kiến

- Chạy các job AI định kỳ (anomaly detection, embedding, feed ranking, monthly report).

### Trạng thái

- Hầu hết là TODO scaffold, chưa có triển khai xử lý nền đầy đủ.

---

## 10. docs và tests

## 10.1 docs

- Chứa tài liệu thiết kế và kế hoạch theo phase.
- Có các tài liệu định hướng kiến trúc AI tách service khỏi backend chính.

## 10.2 tests

- Có phân tách `unit` và `integration`.
- Một số test orchestrator/router đã có.
- Nhiều test khác còn TODO, chưa phủ đủ tất cả domain.

---

## 11. Đọc nhanh trạng thái dự án qua cấu trúc thư mục

Nếu nhìn theo thư mục, có thể hiểu nhanh như sau:

1. Đã chạy thực tế tốt:

- `app/agents/finance`
- `app/agents/orchestrator`
- `app/api/v1/chat.py`
- `app/api/v1/classify.py`
- `app/api/v1/anomalies.py`
- `app/core/llm`
- `app/core/database.py`

2. Mới ở mức khung mở rộng:

- `app/agents/career`
- `app/agents/content`
- `app/agents/personalization`
- `app/workers/*`
- `app/api/v1/career.py`, `content.py`, `feed.py`, `receipt.py`, `internal.py`

3. Ý nghĩa kiến trúc hiện tại:

- Dự án đã có khung multi-agent hoàn chỉnh về mặt tổ chức mã nguồn.
- Domain finance là mũi nhọn đã có logic thật.
- Các domain còn lại đã có vị trí thư mục/file rõ ràng để mở rộng theo phase.

---

## 12. Gợi ý cách đọc code theo thứ tự (onboarding nhanh)

Để hiểu nhanh nhất, đọc theo thứ tự:

1. `app/main.py` -> biết endpoint nào đang bật.
2. `app/api/v1/chat.py` -> luồng chat từ HTTP vào orchestrator.
3. `app/agents/orchestrator/agent.py` + `router.py` + `registry.py` -> cách định tuyến agent.
4. `app/agents/finance/agent.py` + `react_loop.py` + `six_jars/tools/jars.py` -> phần AI chạy thật.
5. `app/core/llm/factory.py` + providers -> cách chọn model Gemini/Ollama.
6. `app/core/database.py` + `chat_session_store.py` -> data access và session memory.

Sau đó mới sang các thư mục TODO để lên roadmap triển khai.
