# s360-ai

AI service for Student360. This repository owns LLM orchestration, prompt composition, retrieval, streaming responses, background AI jobs, and AI-facing API endpoints.

# Stack

- Python 3.12+
- FastAPI and Uvicorn
- Pydantic v2 and pydantic-settings
- LangChain integrations for Google GenAI and Ollama
- SQLAlchemy async with asyncpg
- Redis and ARQ workers
- httpx, structlog, and SSE streaming

# Architecture

- Keep HTTP concerns in `app/api/`.
- Keep shared configuration and infrastructure in `app/core/` and `app/config.py`.
- Keep domain-specific AI behavior in `app/domains/`.
- Keep reusable agent workflows in `app/agents/`.
- Keep data models and schemas in `app/models/`.
- Keep background execution in `app/workers/`.

# LLM Workflow Rules

- Make LLM calls through existing provider, agent, or workflow abstractions.
- Keep model selection, temperature, token limits, and streaming behavior explicit.
- Validate and normalize inputs before they reach the LLM workflow.
- Prefer structured outputs when downstream code depends on fields or decisions.
- Log workflow metadata, timing, and failures without logging secrets or sensitive student data.

# Prompt Rules

- Separate prompt text/templates from business logic and transport code.
- Keep prompts focused on role, task, constraints, context, and output format.
- Do not bury feature rules inside ad hoc prompt strings when they belong in domain logic.
- Version or name important prompt variants clearly.

# Retrieval Rules

- Keep retrieval, ranking, and context assembly separate from final answer generation.
- Limit retrieved context to what the workflow needs.
- Preserve source metadata when retrieved content is used for reasoning or citations.
- Handle empty, low-confidence, or stale retrieval results explicitly.

# Pipeline Conventions

- Compose AI pipelines from small testable steps: validate, retrieve, assemble context, call model, parse, persist or stream.
- Keep async boundaries clear; do not block event loops with sync I/O.
- Return stable error shapes from API endpoints.
- Add focused tests for parsing, prompt assembly, and workflow branching when behavior changes.
