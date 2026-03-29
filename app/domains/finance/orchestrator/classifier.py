"""LLM-based routing fallback.

Used only when rule-based keyword routing cannot decide.
"""

from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

from app.domains.finance.orchestrator.prompts import get_route_classifier_system_prompt
from app.core.llm import get_llm


AllowedAgent = Literal["finance", "career", "content", "personalization"]


def _extract_json(text: str) -> dict | None:
    s = (text or "").strip()
    if not s:
        return None
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


async def llm_classify_agent(message: str) -> tuple[AllowedAgent, float, str]:
    """Return (agent_id, confidence, raw_text)."""
    llm = get_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(content=get_route_classifier_system_prompt()),
            HumanMessage(content=message),
        ]
    )

    raw = getattr(resp, "content", "")
    if not isinstance(raw, str):
        raw = str(raw)

    parsed = _extract_json(raw) or {}
    agent = str(parsed.get("agent", "finance")).strip().lower()
    conf = parsed.get("confidence", 0.0)
    try:
        conf_f = float(conf)
    except Exception:
        conf_f = 0.0

    if agent not in {"finance", "career", "content", "personalization"}:
        agent = "finance"
        conf_f = min(conf_f, 0.3)

    return agent, max(0.0, min(conf_f, 1.0)), raw
