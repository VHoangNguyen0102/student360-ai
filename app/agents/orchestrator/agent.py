"""
Orchestrator Agent — Phase C.
Routes requests to specialist agents using LangGraph Supervisor pattern.
Active in Phase C+ only. Phase 1 routes directly to FinanceAgent.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph

from app.agents.orchestrator.registry import get_specialist_agent
from app.agents.orchestrator.router import route_agent
from app.agents.orchestrator.state import OrchestratorState
from app.models.chat import ContextHint

_orchestrator_agent = None
logger = structlog.get_logger()


def _last_human_message(messages: list[BaseMessage]) -> BaseMessage | None:
	for msg in reversed(messages or []):
		if getattr(msg, "type", None) == "human":
			return msg
	return None


async def _node_route(state: OrchestratorState) -> OrchestratorState:
	last_human = _last_human_message(state.get("messages", []))
	message_text = getattr(last_human, "content", "") if last_human else ""

	hint = state.get("context_hint", ContextHint.AUTO)
	selected, reason = await route_agent(str(message_text), hint)

	logger.info(
		"orchestrator_route",
		selected_agent=selected,
		route_reason=reason,
		context_hint=str(hint),
		session_id=state.get("session_id"),
		user_id=state.get("user_id"),
	)

	return {
		"selected_agent": selected,
		"route_reason": reason,
	}


async def _node_dispatch(state: OrchestratorState) -> OrchestratorState:
	agent_id = state.get("selected_agent", "finance")
	session_id = state.get("session_id") or ""
	user_id = state.get("user_id") or ""

	last_human = _last_human_message(state.get("messages", []))
	if last_human is None:
		return {
			"messages": [AIMessage(content="Xin lỗi, mình chưa nhận được câu hỏi.")],
			"agent_used": [agent_id],
		}

	specialist = get_specialist_agent(agent_id)
	# Cách B: tách memory theo mảng (subthread).
	subthread_id = f"{session_id}:{agent_id}" if session_id else agent_id
	config = {"configurable": {"thread_id": subthread_id, "user_id": user_id}}

	logger.info(
		"orchestrator_dispatch",
		agent_id=agent_id,
		subthread_id=subthread_id,
		session_id=session_id,
		user_id=user_id,
		route_reason=state.get("route_reason"),
	)

	result = await specialist.ainvoke({"messages": [last_human]}, config=config)
	spec_messages = result.get("messages", []) if isinstance(result, dict) else []

	# Avoid duplicating the same human message in the returned state.
	if spec_messages:
		first = spec_messages[0]
		if getattr(first, "type", None) == "human" and getattr(first, "content", None) == getattr(last_human, "content", None):
			spec_messages = spec_messages[1:]

	if not spec_messages:
		spec_messages = [AIMessage(content="Xin lỗi, mình chưa thể xử lý yêu cầu lúc này.")]

	return {
		"messages": spec_messages,
		"agent_used": [agent_id],
	}


def get_orchestrator_agent():
	"""Return a compiled orchestrator graph (singleton)."""
	global _orchestrator_agent
	if _orchestrator_agent is not None:
		return _orchestrator_agent

	graph = StateGraph(OrchestratorState)
	graph.add_node("route", _node_route)
	graph.add_node("dispatch", _node_dispatch)
	graph.add_edge(START, "route")
	graph.add_edge("route", "dispatch")
	graph.add_edge("dispatch", END)

	_orchestrator_agent = graph.compile()
	return _orchestrator_agent
