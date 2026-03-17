# Phase 2 — AI 6 Lọ (Kế Hoạch Chi Tiết)

> Date: 17/03/2026  
> Scope: Hoàn thiện đầy đủ tính năng 6 Lọ theo end-state

## 1. Mục tiêu Phase 2

- Hoàn thiện toàn bộ chức năng 6 Lọ theo mục tiêu end-state.
- Đưa `student360-ai` chạy production, NestJS chỉ làm thin proxy.
- Tăng chất lượng trả lời: context-aware, multi-step, streaming.

## 2. Workstreams chính

### 2.1 Core AI Infrastructure

- LLM Provider (Gemini): retry logic, tool calling, usage logging.
- Embedding Provider: `gemini-embedding-001`.
- Vector Store: pgvector query + save embedding.
- Conversation Memory: Redis checkpointer + fallback last-N.

**Deliverables**
- `app/core/llm.py`
- `app/core/embeddings.py`
- `app/core/vector_store.py`
- `app/core/memory.py`

### 2.2 Finance Agent + Tools (Read-only)

- Port đầy đủ 11 tools từ backend (6 Lọ).
- Chuẩn hóa schema args/returns để LLM dễ gọi.
- Add dynamic system prompt (jar balance + %).
- Support multi-round tool chaining (max rounds).

**Deliverables**
- `app/agents/finance/agent.py`
- `app/agents/finance/tools/jars.py`
- `app/agents/finance/prompts.py`

### 2.3 Classify Pipeline (3 bước + cache)

- Step 1: Exact match preferences.
- Step 2: Vector similarity (ngưỡng 0.92/0.88).
- Step 3: LLM fallback + save embedding.

**Deliverables**
- `app/agents/finance/classify.py`
- `app/core/vector_store.py` (query + save)

### 2.4 Anomaly Detection Worker

- Cron 23:00 daily.
- Đủ 3 loại alert: spike_expense, near_threshold, recurring_increase.
- Persist vào `ai_anomaly_alerts`.

**Deliverables**
- `app/workers/anomaly.py`
- ARQ scheduling + retry

### 2.5 Streaming + Semantic History

- SSE endpoint cho chat.
- Semantic history retrieval bằng `ai_message_embeddings`.
- Summarization fallback khi quá dài.

**Deliverables**
- `app/api/v1/chat.py` (stream)
- `app/core/memory.py` (semantic retrieval)

### 2.6 Insights + Forecast

- Monthly report worker.
- Spending forecast + early warning.

**Deliverables**
- `app/workers/reports.py`
- `app/workers/forecast.py`

### 2.7 Write Actions (Confirm-first)

- Suggest → Confirm flow.
- 3 write tools: create_transaction, transfer_between_jars, update_transaction.
- Audit log + rate limit.

**Deliverables**
- `app/agents/finance/tools/write.py`
- Backend endpoints for safe writes

### 2.8 Bulk Categorization

- Endpoint classify/bulk.
- Batch embedding + save.

**Deliverables**
- `app/api/v1/classify.py` (bulk)

### 2.9 Cross-Context Reasoning (6 Lọ + Scholarships)

- Orchestrator routing nhiều context.
- Compose response từ finance + scholarships tools.

**Deliverables**
- `app/agents/orchestrator/`
- Routing rules + prompt

## 3. Milestones (Gợi ý)

1. Core AI Infrastructure + Read-only tools
2. Classify pipeline + Vector store
3. Anomaly worker + Alerts
4. Streaming + Semantic history
5. Insights + Forecast
6. Write actions + Bulk
7. Cross-context reasoning

## 4. Acceptance Criteria

- Chat trả lời đúng theo dữ liệu thật, có tool chaining.
- Classify chính xác và ổn định (preference + vector + LLM).
- Alerts hoạt động ổn định và không spam.
- SSE streaming và semantic history chạy ổn.
- Write actions chỉ chạy sau confirm rõ ràng.

## 5. Rủi ro & Giảm thiểu

- LLM timeout: retry + timeout policy + degrade.
- Vector query chậm: index + cache.
- Data drift: threshold tuning và metrics.
- Chi phí LLM: usage caps theo user.
