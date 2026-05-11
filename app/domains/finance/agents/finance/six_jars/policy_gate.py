"""
Six Jars domain — Policy Gate.

Enforces tool access rules based on intent:
  knowledge_6jars  → KNOWLEDGE_ONLY_TOOLS (get_financial_guidelines only — no personal data)
  personal_finance → ALL tools (must fetch real user data)
  hybrid           → ALL tools (fetch data + give advice)
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.domains.finance.agents.finance.scholarships.tools import ALL_SCHOLARSHIP_TOOLS
from app.domains.finance.agents.finance.six_jars.tools import ALL_SIX_JARS_TOOLS
from app.domains.finance.agents.finance.six_jars.tools.knowledge import get_financial_guidelines


# Knowledge tool is safe for all intents — it contains no personal data
KNOWLEDGE_ONLY_TOOLS: list[Any] = [get_financial_guidelines]

# Personal data tools — restricted to personal_finance and hybrid intents
_ALL_TOOLS: list[Any] = ALL_SIX_JARS_TOOLS


def _resolve_mode_tools() -> list[Any]:
  mode = (settings.FINANCE_AGENT_MODE or "six_jars").strip().lower()
  if mode == "scholarships":
    return list(ALL_SCHOLARSHIP_TOOLS)
  if mode == "combined":
    return [*ALL_SIX_JARS_TOOLS, *ALL_SCHOLARSHIP_TOOLS]
  return list(ALL_SIX_JARS_TOOLS)


def get_tools_for_intent(intent: str) -> list[Any]:
    """
    Return the list of LangChain tools allowed for a given intent.

    Rules:
      - knowledge_6jars  → [get_financial_guidelines] (knowledge retrieval only, no personal data)
      - personal_finance → all tools available
      - hybrid           → all tools available
      - unknown/fallback → all tools (safe default: never block valid data access)
    """
    #return ALL_SCHOLARSHIP_TOOLS
    if intent == "knowledge_6jars":
        return list(KNOWLEDGE_ONLY_TOOLS)
    return list(_ALL_TOOLS)


def intent_allows_tools(intent: str) -> bool:
    """Convenience check: does this intent have any tools available?"""
    return len(get_tools_for_intent(intent)) > 0
