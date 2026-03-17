# Phase 1 — AI 6 Lọ (Tổng Quan Triển Khai Đến Hiện Tại)

> Date: 17/03/2026  
> Scope: Từ khởi động đến trạng thái hiện tại (Phase 1)

## 1. Mục tiêu Phase 1

- Đạt feature parity tối thiểu để NestJS có thể chuyển sang thin proxy.
- Hoàn thiện API chat và classify cơ bản cho 6 Lọ.
- Thiết lập nền tảng dữ liệu AI (ai_* tables) cho logging và alert.

## 2. Trạng thái triển khai hiện tại

### 2.1 NestJS Backend (đã làm)

- AI gateway proxy (ai_core module) đã tồn tại.
- `POST /api/v1/ai/chat` forward sang `student360-ai`.
- `POST /api/v1/ai/6jars/classify` forward sang `student360-ai`.
- Anomaly alerts đọc từ AI service qua proxy:
  - `GET /api/v1/ai/anomalies`
  - `PATCH /api/v1/ai/anomalies/:id/read`

### 2.2 Database (đã làm)

- Đã có các bảng AI cơ bản:
  - `ai_chat_sessions`
  - `ai_messages`
  - `ai_usage_logs`
  - `ai_anomaly_alerts`
  - `ai_user_preferences_6jars`
- Đã có bảng embedding nền tảng:
  - `transaction_embeddings`
  - `ai_message_embeddings`

### 2.3 student360-ai (đã có skeleton)

- Có API endpoints và routing khung trong `app/api/v1/`.
- Có agents, core, workers, models, utils (cấu trúc thư mục).
- Chưa hoàn thiện triển khai chi tiết (đang ở mức scaffolding).

## 3. API contract đã thống nhất (Phase 1)

- Chat:
  - `POST /api/v1/chat`
  - Input: `user_id`, `session_id`, `message`, `context_hint`
  - Output: `reply`, `session_id`, `usage`

- Classify:
  - `POST /api/v1/classify`
  - Input: `user_id`, `description`, `amount`
  - Output: `suggested_jar_code`, `confidence`

- Anomalies:
  - `GET /api/v1/anomalies`
  - `PATCH /api/v1/anomalies/:id/read`

## 4. Những phần còn thiếu trong Phase 1

- Core AI layer (LLM, embeddings, vector store, memory) chưa hoàn thành.
- Finance agent và tool set 6 Lọ chưa được port đầy đủ.
- Anomaly worker trong `student360-ai` chưa chạy production.
- Semantic history retrieval và vector similarity classify chưa hoạt động.

## 5. Kết luận Phase 1

Phase 1 hiện đạt trạng thái **proxy-ready** từ NestJS, nhưng `student360-ai` vẫn thiếu triển khai thật sự để chạy production. Hoàn thiện core + tools + workers trong Phase 2.
