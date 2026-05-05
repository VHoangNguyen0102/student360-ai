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


async def _thread_lock(thread_id: str) -> asyncio.Lock:
    async with _master_lock:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


async def reset_thread(thread_id: str) -> None:
    lock = await _thread_lock(thread_id)
    async with lock:
        _sessions.pop(thread_id, None)


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
    """
    lock = await _thread_lock(thread_id)
    async with lock:
        hist = _sessions.setdefault(thread_id, [])
        if not hist:
            if history:
                hist.extend(history)
            else:
                hist.append(SystemMessage(content=system_prompt))
        idx = len(hist)
        for m in incoming:
            hist.append(m)
        await runner(hist, tool_config)
        return hist[idx:]
