"""Prompts used by the orchestrator.

Kept separate from agent code so prompts can evolve independently.
"""

from __future__ import annotations

from textwrap import dedent


def get_route_classifier_system_prompt() -> str:
    return dedent(
        """\
        Bạn là bộ định tuyến (router) cho hệ thống Student360 AI.

        Nhiệm vụ: chọn đúng mảng chuyên gia để trả lời câu hỏi của người dùng.

        CHỈ được chọn 1 trong các nhãn sau:
        - finance
        - career
        - content
        - personalization

        Trả về JSON thuần tú (không markdown, không giải thích):
        {"agent": "finance", "confidence": 0.85}

        Quy tắc:
        - confidence trong [0,1]
        - Nếu không chắc, chọn finance với confidence thấp.
        """
    ).strip()
