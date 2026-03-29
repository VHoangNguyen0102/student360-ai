"""
Shim: re-exports for legacy imports (`from app.domains.finance.agents.finance.prompts import ...`).
Prefer `app.domains.finance.agents.finance.six_jars.prompts_*` in new code.
"""
from app.domains.finance.agents.finance.six_jars.prompts_agent import get_finance_system_prompt
from app.domains.finance.agents.finance.six_jars.prompts_classify import CLASSIFY_SYSTEM_PROMPT

__all__ = ["get_finance_system_prompt", "CLASSIFY_SYSTEM_PROMPT"]
