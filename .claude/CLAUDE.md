# Student360 AI Service — Claude Code Guide

## Project Overview

**Student360 AI** is an intelligent AI service that provides reasoning, financial analysis, and student advisory capabilities through specialized AI agents. It acts as the AI processing layer within the larger Student360 platform.

**Role in the system:**
- Receives requests from the NestJS Backend via HTTP (Bearer token auth)
- Processes them through domain-specific AI agents
- Returns structured results or proposed actions for user approval
- Persists conversation history and analysis to its own database

---

## Architecture

```
NestJS Backend ──HTTP──► FastAPI (student360-ai)
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
               Finance      Career   E-learning
               Domain       (stub)    (stub)
                    │
            FinanceToolAgent
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  IntentClassifier  PolicyGate  ReActLoop
        │                           │
   (knowledge /              12 Finance Tools
    personal /              (balances, goals,
    hybrid)                  loans, receipts…)
                                    │
                          Google Gemini / VertexAI
                             / Ollama (local)
```

**Layer mapping:**
| Layer | Path | Responsibility |
|---|---|---|
| HTTP API | `app/api/` | Route handlers, request validation |
| Domain Logic | `app/domains/` | Business agents, orchestration |
| Core Infra | `app/core/` | LLM factory, DB pool, session store |
| Workers | `app/workers/` | Async background jobs (ARQ) |

---

## Tech Stack

| Category | Technology |
|---|---|
| Runtime | Python 3.12+ |
| Web Framework | FastAPI + Uvicorn (ASGI) |
| Data Validation | Pydantic v2 |
| AI Orchestration | LangChain Core 0.3+ |
| LLM Providers | Google Gemini (primary), VertexAI, Ollama (local) |
| Database | PostgreSQL via asyncpg + SQLAlchemy Async |
| Caching / Queue | Redis + ARQ |
| Logging | structlog (structured JSON logs) |
| Testing | pytest + pytest-asyncio + pytest-cov |

**Active LLM models:**
- `gemini-2.0-flash-lite` — default fast model
- `gemini-2.5-flash-lite` — upgraded reasoning
- `qwen2.5:3b` — local Ollama fallback

---

## Domain Status

| Domain | Status | Key Files |
|---|---|---|
| Finance (6 Jars) | **Active / Production** | `app/domains/finance/`, `app/api/finance/` |
| Career | Stub (router only) | `app/api/career/routes.py` |
| E-learning | Stub (router only) | `app/api/elearning/routes.py` |

**Finance domain endpoints:**
- `POST /api/v1/chat` — Main chatbot with full ReAct loop
- `POST /api/v1/classify` — Transaction intent classification
- `POST /api/v1/classify/override` — User feedback on classification
- `GET  /api/v1/anomalies` — Spending anomaly alerts
- `POST /api/v1/insights` — Monthly financial report generation

---

## Key Architectural Patterns

### 1. Multi-Provider LLM with Runtime Override
The LLM provider is selected at config time (VertexAI → Gemini → Ollama) but can be overridden **per-request** via context managers in `app/core/llm/`. The chat endpoint accepts `provider` and `model` fields in the request body to enable this.

### 2. Intent-Based Agent Routing (3 Layers)
1. **Client hint** — request body carries `context_type` (knowledge / personal / hybrid)
2. **Keyword match** — zero-latency rule-based pattern check
3. **LLM classifier** — fallback when rules are inconclusive (confidence threshold: 0.6)

### 3. Policy Gating
`PolicyGate` restricts which tools the agent may call based on detected intent. A "knowledge" intent cannot access personal balance tools.

### 4. ReAct Loop (Reasoning + Acting)
`react_loop.py` implements the standard ReAct cycle: Thought → Action (tool call) → Observation → repeat until final answer.

### 5. Two-Step Classification with Learning
The classify pipeline first hits a **preference table** (zero-latency DB lookup for known patterns), then falls back to LLM. The `override` endpoint lets users correct classifications, building the preference table over time.

### 6. Backend-as-Data-Proxy
This service does **not** own the main database. All student financial data is fetched from the NestJS Backend via HTTP. Each tool in `app/domains/finance/agents/finance/tools/` makes HTTP calls to the Backend.

---

## Critical Files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app factory, router registration |
| `app/config.py` | All env-based configuration (Pydantic Settings) |
| `app/api/finance/chat.py` | Primary chat endpoint with provider fallback logic |
| `app/domains/finance/agents/finance/agent.py` | `FinanceToolAgent` — main agent class |
| `app/domains/finance/agents/finance/react_loop.py` | ReAct execution loop |
| `app/domains/finance/agents/finance/six_jars/intent_classifier.py` | Intent classification |
| `app/domains/finance/agents/finance/six_jars/policy_gate.py` | Tool access control |
| `app/core/llm/factory.py` | LLM provider selection |
| `app/core/chat_session_store.py` | In-process conversation history |
| `app/workers/anomaly.py` | Background anomaly detection |
| `docs/FINANCE_6JARS_ARCHITECTURE.md` | Full architecture spec (Vietnamese) |

---

## Global Rules

1. **Do not refactor without explicit request** — the codebase has deliberate design decisions (e.g., intent-based routing layers). Ask before restructuring.
2. **Do not modify production config files** — `.env`, `docker-compose.yml`, `Dockerfile` are environment-specific. Suggest changes, don't apply directly.
3. **Preserve existing code style** — async-first Python, structlog for logging, Pydantic for all data models.
4. **No CRUD services layer** — this service uses the agent pattern. Don't introduce a traditional service/repository layer unless asked.
5. **Vietnamese language in responses** — AI responses to users are in Vietnamese. Keep prompt tone helpers in `app/core/prompts/` consistent.
6. **Backend is the data source** — never add direct DB queries for student data. Always proxy through the NestJS Backend HTTP client.
