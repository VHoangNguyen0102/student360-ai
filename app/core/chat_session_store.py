"""In-process chat history per thread (replaces LangGraph MemorySaver for MVP).

Multi-replica production should back this with Redis or Postgres.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

_sessions: dict[str, list[BaseMessage]] = {}
_master_lock = asyncio.Lock()
_thread_locks: dict[str, asyncio.Lock] = {}

MAX_HISTORY_MESSAGES = 40


async def _thread_lock(thread_id: str) -> asyncio.Lock:
    async with _master_lock:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


async def reset_thread(thread_id: str) -> None:
    lock = await _thread_lock(thread_id)
    async with lock:
        _sessions.pop(thread_id, None)


def _trim_history(hist: list[BaseMessage]) -> None:
    """Keep at most MAX_HISTORY_MESSAGES, always preserving the SystemMessage at index 0."""
    if len(hist) <= MAX_HISTORY_MESSAGES:
        return
    system_msg = hist[0] if isinstance(hist[0], SystemMessage) else None
    keep = hist[-(MAX_HISTORY_MESSAGES - 1):]
    hist.clear()
    if system_msg:
        hist.append(system_msg)
    hist.extend(keep)


async def run_finance_turn(
    thread_id: str,
    incoming: list[BaseMessage],
    system_prompt: str,
    runner: Callable[[list[BaseMessage], RunnableConfig], Awaitable[None]],
    tool_config: RunnableConfig,
    history: list[BaseMessage] | None = None,
) -> list[BaseMessage]:
    """
    Append `incoming` to the thread transcript, ensure a system message exists,
    run `runner` (typically tool-calling loop) which mutates the list in place.
    Returns new messages for this HTTP turn (including incoming user message(s)).

    The system prompt is updated on every turn so that intent changes between
    turns are reflected correctly (e.g. switching from knowledge to personal mode).
    """
    lock = await _thread_lock(thread_id)
    async with lock:
        hist = _sessions.setdefault(thread_id, [])
        if not hist:
            if history:
                hist.extend(history)
            else:
                hist.append(SystemMessage(content=system_prompt))
        else:
            # Update system prompt when intent changes between turns
            if hist and isinstance(hist[0], SystemMessage):
                if hist[0].content != system_prompt:
                    hist[0] = SystemMessage(content=system_prompt)
        idx = len(hist)
        for m in incoming:
            hist.append(m)
        await runner(hist, tool_config)
        _trim_history(hist)
        return hist[idx:]
