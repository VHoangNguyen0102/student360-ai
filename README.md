# student360-ai

> Multi-agent AI service for Student360 — Python FastAPI + LangGraph

## Stack

| Layer | Tech |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI |
| Agents | LangGraph |
| LLM | Google Gemini (`gemini-2.5-flash-lite`) |
| Embedding | Google Gemini (`gemini-embedding-001`) |
| DB | PostgreSQL + pgvector (shared with backend) |
| Queue | ARQ + Redis (shared with backend) |

## Quick Start

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY, DATABASE_URL, REDIS_URL, etc.

uv pip install -e .
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Phase Status

| Phase | Scope | Status |
|---|---|---|
| **1A** | Core infra (LLM, Embedding, Vector Store) | 🔴 TODO |
| **1B** | Finance Agent — 6 Jars chat + classify | 🔴 TODO |
| **1C** | Anomaly detection worker | 🔴 TODO |
| **B** | Career Agent (job match, CV, cover letter) | ⚪ Planned |
| **C** | Orchestrator + Content Agent | ⚪ Planned |
| **D** | Personalization + Receipt OCR | ⚪ Planned |

## Docs

- [Phase 1 — 6 Jars](docs/phase1-6jars.md)
- [Agent Architecture](docs/agents.md)
- [API Reference](docs/api.md)
- [Tools Catalog](docs/tools.md)
