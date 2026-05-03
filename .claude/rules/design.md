# Design Rules — Student360 AI

Principles and conventions that govern how this codebase is structured.

---

## Architecture Principles

### 1. Clean Layered Architecture
```
app/api/         ← HTTP boundary: validation, auth, routing only
app/domains/     ← Business logic: agents, tools, prompts
app/core/        ← Infrastructure: LLM, DB, HTTP client, session
app/workers/     ← Async jobs: background processing
app/utils/       ← Shared helpers: auth, logging
```

**Rule:** Never import `app/domains/` from `app/core/`. The domain layer depends on core, not the reverse.

### 2. Separation of Concerns
- **API handlers** (`app/api/`) know nothing about agent internals. They validate input, call the domain layer, and format the response.
- **Agents** (`app/domains/`) know nothing about HTTP. They receive plain Python objects and return plain Python objects.
- **Tools** are pure functions: receive typed arguments, call the Backend HTTP API, return structured data.

### 3. Dependency Injection via FastAPI
Use FastAPI `Depends()` for:
- Auth (`verify_service_token`)
- DB pool (`get_db`)
- Backend client (`get_backend_client`)

Do **not** use global singletons for these (except the connection pool which is process-wide by design).

---

## Agent Design

### Tool Design Contract
Every tool must follow this pattern:
```python
async def tool_name(
    arg1: str,          # typed inputs
    arg2: int,
    backend: BackendClient,
) -> dict:              # always return a dict (JSON-serializable)
    ...
```

- Tools must be **idempotent** where possible (safe to call twice)
- Tools must **never raise** unhandled exceptions to the ReAct loop — catch and return an error dict
- Tool descriptions in the docstring are sent to the LLM — write them clearly in English

### Prompt Engineering
- System prompts are in Vietnamese to maintain consistent conversation tone
- Keep prompt templates in dedicated `prompts.py` files, not inline in agent/tool code
- Use f-strings with named variables for clarity:
  ```python
  SYSTEM_PROMPT = f"Bạn là trợ lý tài chính. Ngày hôm nay: {today}"
  ```

### Intent Classification
- Keywords in `intent_classifier.py` are the first layer — prefer adding new keywords over tuning the LLM fallback
- LLM fallback prompts must include few-shot examples for reliability
- Always validate that the returned intent is one of the known enum values

---

## Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Python files | `snake_case.py` | `intent_classifier.py` |
| Classes | `PascalCase` | `FinanceToolAgent` |
| Functions / methods | `snake_case` | `classify_intent()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_CONFIDENCE_THRESHOLD` |
| Pydantic models | `PascalCase` | `ChatRequest`, `ClassifyResponse` |
| API route prefixes | `/api/v1/<domain>/` | `/api/v1/finance/chat` |
| Tool names (LangChain) | `snake_case` with domain prefix | `get_jar_balances`, `check_affordability` |
| Intent enum values | `snake_case` | `knowledge_6jars`, `personal_finance` |

---

## Data Model Rules

- All request/response models use **Pydantic v2**
- Use `model_config = ConfigDict(from_attributes=True)` for ORM models
- Optional fields default to `None`, not empty strings
- Monetary amounts are stored as `float` (VND, no decimals needed at current scale)
- All timestamps are UTC, stored as `datetime` — format for display in Vietnamese locale at the API boundary

---

## Error Handling

- API handlers return structured errors: `{"error": "...", "code": "..."}` with appropriate HTTP status codes
- Domain/agent code raises typed exceptions (define in `app/core/exceptions.py` if needed)
- Tool functions return `{"error": "message"}` dicts instead of raising — the ReAct loop handles error recovery
- Never expose internal stack traces in API responses (log them with structlog, return a safe message)

---

## Vietnamese Localization

- All user-facing text (LLM responses, error messages) must be in Vietnamese
- Currency formatting: use dots as thousands separator, append "đ" — e.g., `1.500.000đ`
- Date formatting: `DD/MM/YYYY` (Vietnamese convention)
- Tone: friendly and supportive, consistent with the prompts in `app/core/prompts/chat_voice.py`
