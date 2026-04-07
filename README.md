# student360-ai

AI service for Student360 using a single FastAPI app with domain-separated routing.

## Domains

- Finance (active)
- Career (stub, FastAPI router ready)
- Elearning (stub, FastAPI router ready)

## Structure

```
app/
   api/
      finance/        # Active routes: chat, classify, anomalies
      career/         # Stub routes
      elearning/      # Stub routes
   domains/
      finance/        # Agents, models, orchestrator scaffold
      career/         # Empty (reserved)
      elearning/      # Empty (reserved)
   core/
   utils/
```

## Key Endpoints

Finance:

- POST /api/v1/chat
- POST /api/v1/classify
- POST /api/v1/classify/override
- GET /api/v1/anomalies
- PATCH /api/v1/anomalies/{id}/read

Career (stub):

- GET /api/v1/career/health

Elearning (stub):

- GET /api/v1/elearning/health

OpenAPI JSON:

- http://localhost:8001/openapi.json

Swagger UI:

- http://localhost:8001/docs

ReDoc:

- http://localhost:8001/redoc

## Quick Start

```bash
cp .env.example .env
uv pip install -e .
uvicorn app.main:app --reload
```

## Local LLM (Ollama)

```bash
docker compose --profile local-llm up -d
docker compose --profile local-llm exec ollama ollama pull qwen2.5:3b
```

## Makefile Helpers

```bash
make up
make up-llm
make pull-model
make openapi
```
