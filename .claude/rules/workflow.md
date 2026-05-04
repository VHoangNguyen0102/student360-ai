# Workflow Rules — Student360 AI

Standard procedures for implementing features, debugging, and testing in this codebase.

---

## Implementing a New Feature

### 1. Understand the Domain First
- Read `docs/FINANCE_6JARS_ARCHITECTURE.md` for Finance domain context
- Identify which domain the feature belongs to (finance / career / elearning)
- Check if there's an existing intent type or tool that overlaps

### 2. Locate the Right Layer
| What you're building | Where it goes |
|---|---|
| New HTTP endpoint | `app/api/<domain>/` |
| New AI tool (agent action) | `app/domains/<domain>/agents/<name>/tools/` |
| New prompt variation | `app/domains/<domain>/agents/<name>/prompts.py` or `six_jars/prompts_*.py` |
| New intent classification rule | `app/domains/finance/agents/finance/six_jars/intent_classifier.py` |
| New tool access policy | `app/domains/finance/agents/finance/six_jars/policy_gate.py` |
| New background job | `app/workers/` |
| New LLM provider | `app/core/llm/providers/` + register in `factory.py` |

### 3. Follow the Existing Pattern
- API routes must use `verify_service_token` dependency for auth
- All database operations use `asyncpg` with the pool from `app/core/database.py`
- All external HTTP calls go through `BackendClient` in `app/core/backend_client.py`
- All new tools must be registered in `app/domains/finance/agents/finance/composition.py`

### 4. Add Tests
- Unit tests → `tests/unit/`
- Integration tests (hitting real HTTP endpoints) → `tests/integration/`
- Use `pytest-asyncio` for async test functions
- Run: `pytest tests/ -v --cov=app`

---

## Debugging an Issue

### Step 1: Reproduce with Logs
```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```
structlog outputs JSON lines. Filter with:
```bash
uvicorn ... 2>&1 | python -m json.tool | grep "event"
```

### Step 2: Check the ReAct Loop
Most issues in the chat endpoint originate in `react_loop.py`. Add a breakpoint or log at:
- Start of the loop (what tools are available)
- Each tool call (input/output)
- Final message assembly

### Step 3: Isolate the LLM Provider
Test with Ollama locally to rule out API quota issues:
```bash
DEFAULT_LLM_PROVIDER=ollama uvicorn app.main:app --reload
```

### Step 4: Check Intent Classification
If the agent behaves unexpectedly, the issue may be intent misclassification. Check `intent_classifier.py` and add the pattern to the keyword rules if it's predictable.

### Step 5: Validate Tool Gating
If a tool call is missing, check `policy_gate.py` — the intent may be restricting access to that tool.

---

## Running the Service

```bash
# Install dependencies
pip install -e ".[dev]"

# Start backing services (DB + Redis)
docker-compose up -d postgres redis

# Run migrations (if any)
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

---

## Adding a New Domain Agent (e.g., Career)

1. Create `app/domains/career/agents/career/agent.py` — implement a `CareerAgent` class similar to `FinanceToolAgent`
2. Create tools in `app/domains/career/agents/career/tools/`
3. Create prompts in `app/domains/career/agents/career/prompts.py`
4. Wire the router in `app/api/career/routes.py` (currently a stub)
5. Register the domain keyword patterns in `app/domains/finance/orchestrator/keywords.py` (if using the orchestrator scaffold)
6. Add integration tests in `tests/integration/`

---

## Code Review Checklist

Before submitting a PR:
- [ ] No hardcoded secrets or API keys
- [ ] All new config values added to `app/config.py` (Pydantic Settings)
- [ ] New tools registered in `composition.py`
- [ ] Vietnamese response tone preserved in any prompt changes
- [ ] structlog used for all logging (no `print()` statements)
- [ ] Tests added or updated for changed behavior
- [ ] Type hints present on all new functions
- [ ] No direct database queries (use BackendClient for student data)
