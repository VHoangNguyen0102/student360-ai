"""
Conversation Memory — LangGraph MemorySaver checkpointer.
For local dev, in-process memory is sufficient.
Upgrade to AsyncPostgresSaver for multi-replica production deployments.
"""
from langgraph.checkpoint.memory import MemorySaver

# Module-level singleton — shared across all agent calls in this process.
_checkpointer = MemorySaver()


def get_checkpointer() -> MemorySaver:
    """Return the shared LangGraph checkpointer."""
    return _checkpointer

