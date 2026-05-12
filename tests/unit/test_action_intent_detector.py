"""Tests for ActionIntentDetector.

Tests the classifier in isolation by mocking the LLM response.
Covers: action messages, non-action messages, typos, abbreviations,
timeout, error fallback, empty input, and ambiguous LLM output.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.finance.agents.finance.action_intent_detector import ActionIntentDetector


def _llm_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = text
    return resp


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    with patch(
        "app.domains.finance.agents.finance.action_intent_detector.get_chat_model",
        return_value=llm,
    ):
        yield llm


# ─────────────────────────────────────────────────────────────────────────────
# Action intent → True
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "moi chi 50k an sang",               # typo: mới → moi
    "chi 200k ăn sáng",                  # no prefix at all
    "vừa thanh toán tiền điện 500k",
    "nhận lương tháng 5 rồi",
    "phân bổ 10 triệu vào 6 lọ",
    "chuyển 300k từ lọ thiết yếu sang lọ học tập",
    "tạo lịch tiết kiệm 500k mỗi tháng",
    "xóa lịch tiết kiệm tháng này",
    "tạm dừng lịch tiết kiệm",
    "bật lại lịch đầu tư",
    "sửa lịch tiết kiệm thành 800k",
    "xóa giao dịch cà phê hôm qua",
    "ghi vào lọ thiết yếu 100k",
    "mới mua laptop 15 triệu",
    "có thu nhập thêm từ freelance 2 triệu",
])
async def test_action_messages_return_true(message: str, mock_llm):
    mock_llm.ainvoke.return_value = _llm_response("YES")
    result = await ActionIntentDetector(provider="gemini").detect(message, user_id="u1")
    assert result is True, f"Expected True for: {message!r}"
    mock_llm.ainvoke.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Non-action → False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "tôi có bao nhiêu tiền trong lọ tiết kiệm?",
    "Giải thích phương pháp 6 lọ cho tôi",
    "Tháng này tôi chi tiêu bao nhiêu?",
    "Lọ thiết yếu nên để ở đâu?",
    "Tôi nên phân bổ thu nhập như thế nào?",
])
async def test_non_action_messages_return_false(message: str, mock_llm):
    mock_llm.ainvoke.return_value = _llm_response("NO")
    result = await ActionIntentDetector(provider="gemini").detect(message, user_id="u1")
    assert result is False, f"Expected False for: {message!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Empty / whitespace input → False without calling LLM
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["", "   "])
async def test_empty_message_returns_false_without_llm_call(message: str, mock_llm):
    result = await ActionIntentDetector().detect(message)
    assert result is False
    mock_llm.ainvoke.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Ambiguous / unexpected LLM output → False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    "MAYBE",
    "",
    "   ",
    "Tôi không chắc",
    "no, this is clearly an action",   # starts with NO
])
async def test_ambiguous_llm_response_returns_false(raw: str, mock_llm):
    mock_llm.ainvoke.return_value = _llm_response(raw)
    result = await ActionIntentDetector().detect("chi 200k", user_id="u1")
    assert result is False, f"Expected False for raw={raw!r}"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["YES\n", "YES.", "YES - đây là hành động"])
async def test_yes_with_trailing_content_returns_true(raw: str, mock_llm):
    mock_llm.ainvoke.return_value = _llm_response(raw)
    result = await ActionIntentDetector().detect("chi 200k", user_id="u1")
    assert result is True, f"Expected True for raw={raw!r}"
    mock_llm.reset_mock()


# ─────────────────────────────────────────────────────────────────────────────
# Gemini list-of-dicts content format
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_content_response_handled(mock_llm):
    resp = MagicMock()
    resp.content = [{"text": "YES"}, {"text": " confirmed"}]
    mock_llm.ainvoke.return_value = resp
    result = await ActionIntentDetector().detect("chi 200k")
    assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Timeout → False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_returns_false(mock_llm):
    async def slow(*_args, **_kwargs):
        await asyncio.sleep(10)

    mock_llm.ainvoke.side_effect = slow

    with patch(
        "app.domains.finance.agents.finance.action_intent_detector._DETECT_TIMEOUT_S",
        0.05,
    ):
        result = await ActionIntentDetector().detect("chi 200k")

    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# LLM exception → False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_exception_returns_false(mock_llm):
    mock_llm.ainvoke.side_effect = RuntimeError("RESOURCE_EXHAUSTED")
    result = await ActionIntentDetector().detect("chi 200k")
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Provider override is applied when constructing the model
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_override_is_applied():
    llm = AsyncMock()
    llm.ainvoke.return_value = _llm_response("NO")

    with patch(
        "app.domains.finance.agents.finance.action_intent_detector.get_chat_model",
        return_value=llm,
    ), patch(
        "app.domains.finance.agents.finance.action_intent_detector.llm_provider_override"
    ) as mock_override:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_override.return_value = ctx

        await ActionIntentDetector(provider="gemini").detect("số dư?")

        mock_override.assert_called_once_with("gemini")
