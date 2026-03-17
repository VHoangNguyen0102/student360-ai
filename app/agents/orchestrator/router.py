"""Intent classification + conditional routing logic.

Routing priority:
1) Explicit `context_hint` from client
2) Rule-based keyword matching
3) LLM classification fallback

This module is pure logic (no LangGraph wiring).
"""

from __future__ import annotations

from app.agents.orchestrator.classifier import llm_classify_agent
from app.agents.orchestrator.keywords import (
	CAREER_KEYWORDS,
	CONTENT_KEYWORDS,
	FINANCE_KEYWORDS,
	PERSONALIZATION_KEYWORDS,
)
from app.models.chat import ContextHint


def _normalize(text: str) -> str:
	return (text or "").lower().strip()


def _has_any(text: str, keywords: list[str]) -> bool:
	t = _normalize(text)
	return any(k in t for k in keywords)


def route_by_keywords(message: str) -> tuple[str | None, str | None]:
	"""Return (agent_id, reason) if deterministically routed by keywords."""
	if _has_any(message, FINANCE_KEYWORDS):
		return "finance", "keyword:finance"
	if _has_any(message, CAREER_KEYWORDS):
		return "career", "keyword:career"
	if _has_any(message, CONTENT_KEYWORDS):
		return "content", "keyword:content"
	if _has_any(message, PERSONALIZATION_KEYWORDS):
		return "personalization", "keyword:personalization"
	return None, None


async def route_agent(message: str, context_hint: ContextHint) -> tuple[str, str]:
	"""Return (agent_id, route_reason). Always returns a valid agent id."""
	if context_hint == ContextHint.FINANCE:
		return "finance", "hint:finance"
	if context_hint == ContextHint.CAREER:
		return "career", "hint:career"
	if context_hint == ContextHint.CONTENT:
		return "content", "hint:content"
	if context_hint == ContextHint.AUTO:
		routed, reason = route_by_keywords(message)
		if routed:
			return routed, reason or "keyword"

		# LLM fallback only when keywords cannot decide.
		try:
			agent, confidence, _raw = await llm_classify_agent(message)
			if confidence >= 0.6:
				return agent, f"llm:{confidence:.2f}"
			return "finance", f"llm_low_conf:{confidence:.2f}"
		except Exception as exc:
			# If the classifier LLM fails (quota, network, etc.), default safely.
			return "finance", f"llm_error:{type(exc).__name__}"

	# Unknown hint: default to finance.
	return "finance", "hint:unknown_default_finance"
