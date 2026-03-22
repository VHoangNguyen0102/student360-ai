"""Finance subdomain: scholarships (scaffold)."""

from app.agents.finance.scholarships.prompts import get_scholarship_system_prompt
from app.agents.finance.scholarships.tools import ALL_SCHOLARSHIP_TOOLS

__all__ = ["get_scholarship_system_prompt", "ALL_SCHOLARSHIP_TOOLS"]
