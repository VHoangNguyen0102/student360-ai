"""
Scholarship tool registry.

Modules:
  matching.py      -- Fuzzy scholarship lookup + full scholarship details (public data).
  applications.py  -- Ho so xin hoc bong cua sinh vien (can user_id tu RunnableConfig).
                       2 tools:
                         get_my_scholarship_applications    -- Danh sach tat ca hoc bong sinh vien da apply,
                                                               co the loc theo status.
                         get_scholarship_application_detail -- Chi tiet 1 ho so: tai lieu da nop,
                                                               lich su xet duyet, yeu cau hoc bong.
                                                               Dung de LLM du doan ty le trung tuyen.

`composition.get_finance_tools()` se gom cung six-jars tools.
"""

from __future__ import annotations

from typing import Any

from .applications import (
    get_my_scholarship_applications,
    get_scholarship_application_detail,
)
from .matching import find_scholarship_id_by_name, get_scholarship_details

ALL_SCHOLARSHIP_TOOLS: list[Any] = [
    # Public scholarship data (khong can user_id)
    find_scholarship_id_by_name,
    get_scholarship_details,
    # Student-specific: ho so apply cua sinh vien (can user_id tu config)
    get_my_scholarship_applications,
    get_scholarship_application_detail,
]

__all__ = ["ALL_SCHOLARSHIP_TOOLS"]
