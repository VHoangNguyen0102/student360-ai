"""Orchestrator state definition.

We keep this minimal and explicit so the graph is easy to reason about.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.models.chat import ContextHint


class OrchestratorState(TypedDict, total=False):
	# Accumulated message list for this request.
	messages: Annotated[list[BaseMessage], add_messages]

	# Session/user context.
	user_id: str
	session_id: str
	context_hint: ContextHint

	# Routing output.
	selected_agent: str
	route_reason: str

	# Used for API response/debugging.
	agent_used: list[str]
