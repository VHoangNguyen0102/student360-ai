"""
Scholarship tool registry.

Modules:
  matching.py      -- Fuzzy scholarship lookup + full scholarship details (public data).
  applications.py  -- Ho so xin hoc bong cua sinh vien (can user_id tu RunnableConfig).
                      Quy tac nghiep vu: moi sinh vien chi apply 1 hoc bong tai 1 thoi diem
                      nen chi co 1 tool tu dong lay don dang pending, khong can truyen ID.
                      Dang dung mock data -- refactor khi co schema DB that.

`composition.get_finance_tools()` se gom cung six-jars tools.
"""

from __future__ import annotations

from typing import Any

from .applications import get_current_scholarship_application
from .matching import find_scholarship_id_by_name, get_scholarship_details

ALL_SCHOLARSHIP_TOOLS: list[Any] = [
	# Public scholarship data (khong can user_id)
	find_scholarship_id_by_name,
	get_scholarship_details,
	# Student-specific: lay don hoc bong dang pending, tu dong theo user_id
	get_current_scholarship_application,
]

__all__ = ["ALL_SCHOLARSHIP_TOOLS"]

