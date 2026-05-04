# Project Memory — Student360 AI

Running log of important decisions, discovered patterns, and recurring issues.
Update this file as you learn more about the codebase.

---

## Architecture Decisions

### ADR-001: Single Agent with Intent Switching (not true multi-agent)
**Decision:** Despite the orchestrator scaffold in `app/domains/finance/orchestrator/`, the runtime uses a single `FinanceToolAgent` whose behavior is controlled by intent-based prompt switching.
**Why:** Simpler to reason about, lower latency, avoids inter-agent coordination overhead at the current scale.
**Impact:** When adding new finance behaviors, extend the intent → prompt mapping rather than creating a new agent class.

### ADR-002: Backend-as-Data-Proxy
**Decision:** This AI service never queries the main student database directly. All data access goes through the NestJS Backend HTTP API.
**Why:** Single source of truth for business data; avoids dual-ownership of the DB schema.
**Impact:** All tool implementations in `app/domains/finance/agents/finance/tools/` must use `backend_client.py`.

### ADR-003: In-Process Chat Session Store (MVP)
**Decision:** Conversation history is kept in-memory (dictionary + asyncio locks) in `app/core/chat_session_store.py`.
**Why:** Simplest working solution for MVP. Production migration path is Redis/Postgres.
**Impact:** Sessions are lost on server restart. Do not rely on long-term persistence in tests.

### ADR-004: Multi-Provider LLM with Context Manager Override
**Decision:** Default provider is configured via env var, but can be overridden per-request via Python context managers.
**Why:** Enables A/B testing of providers without restart; allows local dev to use Ollama.
**Impact:** The `provider` and `model` fields in `ChatRequest` drive the override. See `app/core/llm/factory.py`.

---

## Known Patterns

### Provider Fallback Chain
```
VertexAI (preferred, GCP) → Gemini (quota fallback) → Ollama (local last resort)
```
Fallback is triggered on `RESOURCE_EXHAUSTED` (HTTP 429) or connection errors.

### Intent → Prompt Mapping
| Intent | Prompt Strategy | Tool Access |
|---|---|---|
| `knowledge_6jars` | Educational, no personal data | Knowledge tools only |
| `personal_finance` | Personalized advice | Full tool set |
| `hybrid` | Mixed: explain + personalize | Full tool set |

### Classification Confidence Threshold
The LLM fallback classifier in `intent_classifier.py` uses a confidence threshold of **0.6**. Below this, it defaults to `personal_finance`.

---

## Recurring Issues & Fixes

### Issue: Empty final message from LLM
**Symptom:** The ReAct loop completes but the last message is empty.
**Fix:** `chat.py` synthesizes a fallback response from the last tool output when this happens. Check `_synthesize_from_tool_output()` logic.

### Issue: Ollama exceeds 120s timeout
**Symptom:** `qwen2.5:3b` is slow on large tool call chains.
**Fix:** A warning is logged. If this is frequent, increase `OLLAMA_TIMEOUT_SECONDS` in config or switch to a smaller model.

### Issue: VertexAI `streamGenerateContent` auth errors
**Symptom:** 401/403 from the VertexAI endpoint.
**Fix:** Ensure `GOOGLE_CLOUD_PROJECT` and `VERTEX_AI_LOCATION` are set, and that `gcloud auth application-default login` has been run locally.

---

## TODO / Open Items

- [ ] Smart data entry (auto-classify on transaction creation) — Backend API ready, Frontend integration pending
- [ ] Budget UI — Backend API ready, Frontend not yet built
- [ ] Anomaly alert badges/notifications — Worker exists, Frontend integration needed
- [ ] Report AI Insights block — Backend endpoint exists, UI not built
- [ ] Migrate `chat_session_store.py` to Redis for production
- [ ] Career domain agent — stub only, no logic
- [ ] E-learning domain agent — stub only, no logic
