"""Agent registry.

Keeps imports localized so missing agents don't break the orchestrator.
"""

from __future__ import annotations

from typing import Any

from app.agents.finance.agent import get_finance_agent
from app.agents.orchestrator.placeholder import PlaceholderAgent


def get_specialist_agent(agent_id: str) -> Any:
    agent_id = (agent_id or "").strip().lower()

    if agent_id == "finance":
        return get_finance_agent()

    # The following domains exist as folders but are not implemented yet.
    if agent_id == "career":
        return PlaceholderAgent(
            "career",
            "Mảng nghề nghiệp (career) hiện chưa được triển khai trong chế độ chat multi-agent.",
        )
    if agent_id == "content":
        return PlaceholderAgent(
            "content",
            "Mảng nội dung (content) hiện chưa được triển khai trong chế độ chat multi-agent.",
        )
    if agent_id == "personalization":
        return PlaceholderAgent(
            "personalization",
            "Mảng cá nhân hoá (personalization) hiện chưa được triển khai trong chế độ chat multi-agent.",
        )

    return PlaceholderAgent(
        "unknown",
        "Xin lỗi, hệ thống chưa hỗ trợ mảng này trong chế độ chat multi-agent.",
    )
