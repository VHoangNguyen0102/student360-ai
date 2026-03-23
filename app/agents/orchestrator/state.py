"""Orchestrator request state (plain dict shape; no LangGraph reducers)."""

from __future__ import annotations

from typing import TypedDict

from langchain_core.messages import BaseMessage

from app.models.chat import ContextHint


class OrchestratorState(TypedDict, total=False):
    messages: list[BaseMessage]
    user_id: str
    session_id: str
    context_hint: ContextHint
    selected_agent: str
    route_reason: str
    agent_used: list[str]
