"""Pydantic models for AI-generated Action Proposals (one-tap execution)."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ActionType(str, Enum):
    CREATE_TRANSACTION = "CREATE_TRANSACTION"
    DISTRIBUTE_INCOME = "DISTRIBUTE_INCOME"
    TRANSFER_BETWEEN_JARS = "TRANSFER_BETWEEN_JARS"
    UPDATE_ALLOCATION = "UPDATE_ALLOCATION"
    CREATE_AUTO_TRANSFER_SCHEDULE = "CREATE_AUTO_TRANSFER_SCHEDULE"
    DELETE_AUTO_TRANSFER_SCHEDULE = "DELETE_AUTO_TRANSFER_SCHEDULE"
    TOGGLE_AUTO_TRANSFER_SCHEDULE = "TOGGLE_AUTO_TRANSFER_SCHEDULE"
    UPDATE_AUTO_TRANSFER_SCHEDULE = "UPDATE_AUTO_TRANSFER_SCHEDULE"
    DELETE_TRANSACTION = "DELETE_TRANSACTION"


class ActionProposal(BaseModel):
    type: ActionType
    title: str
    description: str
    params: dict[str, Any]
    risk_level: str = "low"  # low | medium | high
