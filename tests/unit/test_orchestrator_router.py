import pytest

from app.agents.orchestrator import router as router_module
from app.models.chat import ContextHint


@pytest.mark.asyncio
async def test_route_agent_respects_explicit_hint():
    agent_id, reason = await router_module.route_agent("anything", ContextHint.CAREER)
    assert agent_id == "career"
    assert reason == "hint:career"


@pytest.mark.asyncio
async def test_route_agent_keywords_cv_to_career():
    agent_id, reason = await router_module.route_agent("Giúp mình viết CV", ContextHint.AUTO)
    assert agent_id == "career"
    assert reason.startswith("keyword:career")


@pytest.mark.asyncio
async def test_route_agent_llm_fallback_error_defaults_finance(monkeypatch: pytest.MonkeyPatch):
    async def _boom(_message: str):
        raise RuntimeError("quota")

    monkeypatch.setattr(router_module, "llm_classify_agent", _boom)

    agent_id, reason = await router_module.route_agent("không có keyword", ContextHint.AUTO)
    assert agent_id == "finance"
    assert reason.startswith("llm_error:")
