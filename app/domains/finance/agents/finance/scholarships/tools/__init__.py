"""
Scholarship tool registry.

Khi implement: import tool functions từ matching.py (hoặc modules khác) và
append vào ALL_SCHOLARSHIP_TOOLS. `composition.get_finance_tools()` sẽ gom
cùng six-jars tools.
"""

from __future__ import annotations

from typing import Any

from app.agents.finance.scholarships.tools.matching import (
	find_scholarship_id_by_name,
	get_scholarship_details,
)

ALL_SCHOLARSHIP_TOOLS: list[Any] = [
	find_scholarship_id_by_name,
	get_scholarship_details,
]

__all__ = ["ALL_SCHOLARSHIP_TOOLS"]
