"""
Six Jars domain — Policy Gate.

Enforces tool access rules based on intent:
  knowledge_6jars  → KNOWLEDGE_ONLY_TOOLS (get_financial_guidelines only — no personal data)
  personal_finance → ALL tools (must fetch real user data)
  hybrid           → ALL tools (fetch data + give advice)
"""
from __future__ import annotations

from typing import Any

from app.domains.finance.agents.finance.six_jars.tools import ALL_SIX_JARS_TOOLS
from app.domains.finance.agents.finance.six_jars.tools.knowledge import get_financial_guidelines


# Knowledge tool is safe for all intents — it contains no personal data
KNOWLEDGE_ONLY_TOOLS: list[Any] = [get_financial_guidelines]

# Personal data tools — restricted to personal_finance and hybrid intents
_ALL_TOOLS: list[Any] = ALL_SIX_JARS_TOOLS


def get_tools_for_intent(intent: str) -> list[Any]:
    """
    Return the list of LangChain tools allowed for a given intent.

    Rules:
      - knowledge_6jars  → [get_financial_guidelines] (knowledge retrieval only, no personal data)
      - personal_finance → all tools available
      - hybrid           → all tools available
      - unknown/fallback → all tools (safe default: never block valid data access)
    """
    if intent == "knowledge_6jars":
        return list(KNOWLEDGE_ONLY_TOOLS)
    return list(_ALL_TOOLS)


def intent_allows_tools(intent: str) -> bool:
    """Convenience check: does this intent have any tools available?"""
    return len(get_tools_for_intent(intent)) > 0
