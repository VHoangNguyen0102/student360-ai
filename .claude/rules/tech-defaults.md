# Tech Defaults — Student360 AI

Default technical decisions and conventions for this service.

---

## Logging

**Use structlog exclusively.** Never use `print()` or the standard `logging` module directly.

```python
import structlog
log = structlog.get_logger(__name__)

# Correct usage
log.info("chat_request_received", user_id=user_id, session_id=session_id)
log.warning("provider_fallback", from_provider="vertexai", to_provider="gemini")
log.error("tool_call_failed", tool="get_jar_balances", error=str(e))
```

**Required context fields in structured logs:**
- `user_id` — always bind when available
- `session_id` — for chat/agent operations
- `intent` — for classified requests
- `provider` — when logging LLM calls
- `latency_ms` — for performance-critical paths

---

## Error Handling

### API Layer
```python
# Return structured errors with appropriate HTTP status
raise HTTPException(
    status_code=422,
    detail={"error": "Invalid request", "code": "INVALID_REQUEST"}
)
```

### Domain / Agent Layer
```python
# Raise domain-specific exceptions, let API layer translate
class AgentProcessingError(Exception):
    pass
```

### Tool Layer
```python
# Return error dict instead of raising — ReAct loop recovers
async def get_jar_balances(...) -> dict:
    try:
        result = await backend.get_balances(user_id)
        return result
    except Exception as e:
        log.error("tool_failed", tool="get_jar_balances", error=str(e))
        return {"error": f"Không thể lấy số dư: {str(e)}"}
```

---

## API Response Format

### Success
```json
{
  "message": "...",
  "session_id": "...",
  "usage": { "input_tokens": 0, "output_tokens": 0 },
  "intent": "personal_finance",
  "provider": "gemini"
}
```

### Error
```json
{
  "error": "Human-readable message in Vietnamese",
  "code": "MACHINE_READABLE_CODE",
  "detail": "Optional technical detail (dev mode only)"
}
```

### Pagination (list endpoints)
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

## Async Conventions

- All I/O operations must be `async` — no blocking calls in the event loop
- Use `asyncpg` for DB queries (never synchronous SQLAlchemy in async context)
- Use `httpx.AsyncClient` for HTTP calls (wrapped by `BackendClient`)
- Background tasks use ARQ workers, not `asyncio.create_task()` (which loses on restart)

```python
# Correct: async DB query
async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM table WHERE ...")

# Correct: async HTTP
async with backend_client as client:
    result = await client.get_balances(user_id)
```

---

## Configuration

All configuration is managed via **Pydantic Settings** in `app/config.py`. 

Rules:
- Never hardcode URLs, keys, timeouts, or thresholds
- Add new config fields to the `Settings` class with sensible defaults
- Secrets (API keys, tokens) must be sourced from environment variables or `.env` file
- Use `@cached_property` for derived settings (e.g., computed URLs)

```python
# Correct: use settings
from app.config import settings
url = settings.backend_url + "/api/transactions"

# Wrong: hardcoded
url = "http://localhost:3000/api/transactions"
```

---

## LLM Calls

- Always use the factory function `get_chat_model()` from `app/core/llm/factory.py`
- Never instantiate LLM providers directly in domain/tool code
- For per-request model override, use the context manager:
  ```python
  from app.core.llm.runtime_model import override_model
  with override_model(provider="gemini", model="gemini-2.5-flash-lite"):
      model = get_chat_model()
  ```
- Set reasonable timeouts: Gemini/VertexAI = 30s, Ollama = 120s

---

## Database Patterns

```python
# Standard async query pattern
async def get_user_data(pool: asyncpg.Pool, user_id: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1",
            user_id
        )
    return dict(row) if row else None
```

- Use parameterized queries (`$1`, `$2`) — never f-strings in SQL
- Transactions use `async with conn.transaction():`
- Connection pool is initialized once at startup in `app/core/database.py`

---

## Testing Standards

```python
# Async test function
@pytest.mark.asyncio
async def test_classify_intent():
    result = await classify_intent("tôi muốn biết về 6 lọ")
    assert result.intent == "knowledge_6jars"

# Mock the BackendClient, never hit real backend in unit tests
@pytest.fixture
def mock_backend(mocker):
    return mocker.patch("app.core.backend_client.BackendClient")
```

- Unit tests mock `BackendClient` and LLM responses
- Integration tests use a real running service (CI environment)
- Minimum coverage target: **70%** for domain logic
- Test file naming: `test_<module_name>.py`
