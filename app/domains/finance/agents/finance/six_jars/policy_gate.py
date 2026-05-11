"""
Six Jars domain — Policy Gate.

Enforces tool access rules based on intent:
  knowledge_6jars  → NO tools (answer from knowledge only)
  personal_finance → ALL tools (must fetch real user data)
  hybrid           → ALL tools (fetch data + give advice)
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.domains.finance.agents.finance.scholarships.tools import ALL_SCHOLARSHIP_TOOLS
from app.domains.finance.agents.finance.six_jars.tools import ALL_SIX_JARS_TOOLS


# Intentionally separate constant for type + import clarity
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
      - knowledge_6jars  → [] (no database tools, pure knowledge)
      - personal_finance → all tools available
      - hybrid           → all tools available
      - unknown/fallback → all tools (safe default: never block valid data access)
    """
    return ALL_SCHOLARSHIP_TOOLS
    if intent == "knowledge_6jars":
      return []  # Policy: NO personal-data tool calls for pure knowledge questions
    return _resolve_mode_tools()


def intent_allows_tools(intent: str) -> bool:
    """Convenience check: does this intent require tool calls?"""
    return intent != "knowledge_6jars"
