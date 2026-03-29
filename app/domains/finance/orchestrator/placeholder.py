"""Placeholder agent used for domains not yet implemented.

This keeps orchestrator plumbing stable while other agents are still TODO.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class PlaceholderAgent:
    def __init__(self, agent_id: str, message: str):
        self.agent_id = agent_id
        self.message = message

    async def ainvoke(self, _input: Any, *_args: Any, **_kwargs: Any) -> dict:
        return {"messages": [AIMessage(content=self.message)]}
