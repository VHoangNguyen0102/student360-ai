# student360-ai

> Multi-agent AI service for Student360 — Python FastAPI, orchestrator routing, native tool calling (no LangGraph).

## Stack

| Layer | Tech |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI |
| Agents | Orchestrator + specialist agents (manual tool loop) |
| LLM | Google Gemini (cloud) **or** [Ollama](https://ollama.com/) (local, e.g. `qwen2.5:3b`) |
| DB | PostgreSQL (shared with backend) |
| Queue | ARQ + Redis (shared with backend) |

## Quick Start

```bash
cp .env.example .env
# Fill in DATABASE_URL, REDIS_URL, AI_SERVICE_SECRET, BACKEND_*, etc.
# For Gemini: LLM_PROVIDER=gemini and GEMINI_API_KEY=...

uv pip install -e .
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs (or http://localhost:8001/docs when mapped via Docker).

## Local LLM (Ollama / Qwen2.5 3B)

1. In `.env`: `LLM_PROVIDER=ollama`. You do **not** need `GEMINI_API_KEY` for this mode.
2. **Ollama on the host** (uvicorn on host): keep `OLLAMA_BASE_URL=http://127.0.0.1:11434`, run Ollama locally, then pull the model once:

   ```bash
   ollama pull qwen2.5:3b
   ```

3. **Ollama in Docker** (same Compose file as `ai-service`):

   In `.env`: `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL=http://ollama:11434`.

   The `ollama` service is behind the Compose profile **`local-llm`**. **One command** starts **both** `ai-service` and `ollama` — do not rely on a second plain `docker compose up` for “only the AI image”; without the profile, the Ollama container is not part of the stack.

   **First time (or new machine / new volume):**

   ```bash
   docker compose --profile local-llm up -d --build
   docker compose --profile local-llm exec ollama ollama pull qwen2.5:3b
   ```

   Run `pull` only after the `ollama` container is up. Ollama does not download models on its own; you need `pull` once per volume (or when you change `OLLAMA_MODEL`).

   **After you change application source** (rebuild `ai-service`):

   ```bash
   docker compose --profile local-llm up -d --build
   ```

   **Normal start** (e.g. after reboot, images already built):

   ```bash
   docker compose --profile local-llm up -d
   ```

   You do **not** run `pull` on every `up` — the model stays in the `ollama_data` volume. No extra “start the model” command: once the `ollama` container is running, it serves on port 11434 (also published to the host for debugging).

If `ollama list` shows a different tag for Qwen 2.5 3B, set `OLLAMA_MODEL` in `.env` to match.

## Docker (Gemini only — no Ollama container)

If you use **Gemini** (`LLM_PROVIDER=gemini`) and do not need the local LLM profile:

```bash
docker compose up -d --build
```

PostgreSQL and Redis are expected from the NestJS backend stack (not defined in this compose file).

## Phase Status

| Phase | Scope | Status |
|---|---|---|
| **1A** | Core infra (LLM, adapters) | In progress |
| **1B** | Finance Agent — 6 Jars chat + classify | In progress |
| **1C** | Anomaly detection worker | 🔴 TODO |
| **B** | Career Agent (job match, CV, cover letter) | ⚪ Planned |
| **C** | Orchestrator + Content Agent | ⚪ Planned |
| **D** | Personalization + Receipt OCR | ⚪ Planned |

## Docs

- [Phase 1 — 6 Jars](docs/phase1-6jars.md)
- [Agent Architecture](docs/agents.md)
- [API Reference](docs/api.md)
- [Tools Catalog](docs/tools.md)
