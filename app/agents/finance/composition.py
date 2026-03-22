"""
Compose finance agent surface from subdomains (six_jars, scholarships, …).

Single place to merge tool lists and system prompts so `agent.py` stays thin.
"""
from __future__ import annotations

from typing import Any

from app.agents.finance.scholarships.tools import ALL_SCHOLARSHIP_TOOLS
from app.agents.finance.six_jars.prompts_agent import get_finance_system_prompt as _six_jars_system_prompt
from app.agents.finance.six_jars.tools import ALL_SIX_JARS_TOOLS


def get_finance_tools() -> list[Any]:
    """All LangChain tools exposed to the finance chat agent."""
    return [*ALL_SIX_JARS_TOOLS, *ALL_SCHOLARSHIP_TOOLS]


def get_finance_system_prompt() -> str:
    """
    System prompt for the finance agent.
    Today: six-jars only. Later: append or branch using get_scholarship_system_prompt().
    """
    return _six_jars_system_prompt()
