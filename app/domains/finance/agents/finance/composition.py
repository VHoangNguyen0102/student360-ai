"""
Compose finance agent surface from subdomains (six_jars, scholarships, …).

Single place to merge tool lists and system prompts so `agent.py` stays thin.
"""
from __future__ import annotations

from typing import Any

from app.core.prompts.chat_voice import get_global_chat_style_rules
from app.domains.finance.agents.finance.scholarships.tools import ALL_SCHOLARSHIP_TOOLS
from app.domains.finance.agents.finance.six_jars.prompts_followups import (
    get_finance_six_jars_followup_rules,
)
from app.domains.finance.agents.finance.six_jars.prompts_agent import get_finance_system_prompt as _six_jars_system_prompt
from app.domains.finance.agents.finance.six_jars.tools import ALL_SIX_JARS_TOOLS


def get_finance_tools(mode: str | None = None) -> list[Any]:
    """All LangChain tools exposed to the finance chat agent.

    Mode is controlled by `FINANCE_AGENT_MODE` (env) by default.
    """
    selected = (mode or settings.FINANCE_AGENT_MODE or "six_jars").strip().lower()

    if selected == "scholarships":
        return [*ALL_SCHOLARSHIP_TOOLS]
    if selected == "combined":
        return [*ALL_SIX_JARS_TOOLS, *ALL_SCHOLARSHIP_TOOLS]
    # default: six_jars
    return [*ALL_SIX_JARS_TOOLS]


def get_finance_system_prompt(mode: str | None = None) -> str:
    """
    System prompt for the finance agent.
    Controlled by `FINANCE_AGENT_MODE` (env) by default.
    """
    return (
        _six_jars_system_prompt().rstrip()
        + "\n\n"
        + get_global_chat_style_rules()
        + "\n\n"
        + get_finance_six_jars_followup_rules()
    )
