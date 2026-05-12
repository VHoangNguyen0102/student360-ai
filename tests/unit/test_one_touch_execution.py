"""Tests for one-touch execution (Thực thi một chạm) feature.

Kịch bản: Khi enable_actions=False và ActionIntentDetector phát hiện hành động,
AI service phải trả về actionHint=True mà không gọi agent hoặc emit token events.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.config import settings

TEST_SECRET = "test-secret"
AUTH_HEADER = {"Authorization": f"Bearer {TEST_SECRET}"}


@pytest.fixture(autouse=True)
def patch_ai_service_secret(monkeypatch):
    monkeypatch.setattr(settings, "AI_SERVICE_SECRET", TEST_SECRET)


def parse_sse(text: str) -> list[dict]:
    """Parse SSE response body into list of {event, data} dicts."""
    events: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            raw = line[5:].strip()
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def _mock_detector(return_value: bool):
    """Return a patched ActionIntentDetector whose detect() returns return_value."""
    mock_cls = MagicMock()
    mock_inst = AsyncMock()
    mock_inst.detect = AsyncMock(return_value=return_value)
    mock_cls.return_value = mock_inst
    return mock_cls


# ─────────────────────────────────────────────────────────────────────────────
# Core behaviour: blocked path (enable_actions=False + detector returns True)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_returns_action_hint_when_enable_actions_false():
    """actionHint=True được trả về khi enable_actions=False và detector phát hiện action."""
    mock_agent = MagicMock()
    mock_agent.astream = AsyncMock()

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", _mock_detector(True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "Tôi vừa chi 200k vào đồ ăn sáng",
                    "enable_actions": False,
                },
                headers=AUTH_HEADER,
            )

    assert response.status_code == 200
    events = parse_sse(response.text)

    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1, "Phải có đúng 1 done event"

    done_data = done_events[0]["data"]
    assert done_data["actionHint"] is True, "actionHint phải là True khi mode tắt"
    assert done_data["actions"] == [], "Không có action proposals khi bị block"


@pytest.mark.asyncio
async def test_stream_does_not_call_agent_when_blocked():
    """Agent không được gọi khi request bị block."""
    mock_agent = MagicMock()
    mock_agent.astream = AsyncMock()

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", _mock_detector(True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "ghi chi 50k vào lọ thiết yếu",
                    "enable_actions": False,
                },
                headers=AUTH_HEADER,
            )

    mock_agent.astream.assert_not_called()


@pytest.mark.asyncio
async def test_stream_emits_no_token_events_when_blocked():
    """Không có token events nào được emit khi request bị block."""
    mock_agent = MagicMock()
    mock_agent.astream = AsyncMock()

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", _mock_detector(True)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "vừa thanh toán 300k tiền điện",
                    "enable_actions": False,
                },
                headers=AUTH_HEADER,
            )

    events = parse_sse(response.text)
    assert not [e for e in events if e.get("event") == "token"], "Không được có token events khi bị block"
    assert not [e for e in events if e.get("event") == "status"], "Không được có status events khi bị block"


# ─────────────────────────────────────────────────────────────────────────────
# Detector is called when enable_actions=False, skipped when True
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detector_called_when_enable_actions_false():
    """ActionIntentDetector.detect() được gọi khi enable_actions=False."""
    mock_agent = MagicMock()
    mock_agent.astream = AsyncMock()
    mock_cls = _mock_detector(True)

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", mock_cls):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "chi 200k ăn sáng",
                    "enable_actions": False,
                },
                headers=AUTH_HEADER,
            )

    mock_cls.return_value.detect.assert_called_once()


@pytest.mark.asyncio
async def test_detector_not_called_when_enable_actions_true():
    """ActionIntentDetector không được gọi khi enable_actions=True — agent chạy trực tiếp."""
    async def fake_astream(*args, **kwargs):
        yield ("token", "Đã ghi nhận.")

    mock_agent = MagicMock()
    mock_agent.astream = MagicMock(return_value=fake_astream())
    mock_cls = _mock_detector(True)

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", mock_cls), \
         patch("app.api.finance.chat.ActionExtractor") as mock_extractor_cls:
        mock_extractor = AsyncMock()
        mock_extractor.extract = AsyncMock(return_value=[])
        mock_extractor_cls.return_value = mock_extractor

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "vừa chi 200k",
                    "enable_actions": True,
                },
                headers=AUTH_HEADER,
            )

    mock_cls.return_value.detect.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Non-action messages should NOT be blocked
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "Số dư lọ tiết kiệm của tôi là bao nhiêu?",
    "Giải thích phương pháp 6 lọ cho tôi",
    "Tháng này tôi chi tiêu bao nhiêu?",
    "Lọ tiết kiệm nên để ở đâu?",
])
async def test_non_action_messages_not_blocked(message: str):
    """Khi detector trả False, agent được gọi và actionHint=False."""
    async def fake_astream(*args, **kwargs):
        yield ("token", "Đây là câu trả lời mẫu.")

    mock_agent = MagicMock()
    mock_agent.astream = MagicMock(return_value=fake_astream())

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", _mock_detector(False)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": message,
                    "enable_actions": False,
                },
                headers=AUTH_HEADER,
            )

    assert response.status_code == 200
    events = parse_sse(response.text)
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, f"Phải có done event cho message: {message!r}"
    assert done_events[0]["data"]["actionHint"] is False, (
        f"actionHint phải là False cho message: {message!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# enable_actions=True should bypass the block entirely
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enable_actions_true_bypasses_block():
    """Khi enable_actions=True, agent được gọi bình thường."""
    async def fake_astream(*args, **kwargs):
        yield ("token", "Đã ghi nhận khoản chi của bạn.")

    mock_agent = MagicMock()
    mock_agent.astream = MagicMock(return_value=fake_astream())

    with patch("app.api.finance.chat.get_finance_agent", return_value=mock_agent), \
         patch("app.api.finance.chat.ActionIntentDetector", _mock_detector(False)), \
         patch("app.api.finance.chat.ActionExtractor") as mock_extractor_cls:
        mock_extractor = AsyncMock()
        mock_extractor.extract = AsyncMock(return_value=[])
        mock_extractor_cls.return_value = mock_extractor

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/stream",
                json={
                    "user_id": "user-test-001",
                    "message": "Tôi vừa chi 200k vào đồ ăn sáng",
                    "enable_actions": True,
                },
                headers=AUTH_HEADER,
            )

    assert response.status_code == 200
    events = parse_sse(response.text)
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events
    assert done_events[0]["data"]["actionHint"] is False, (
        "actionHint phải là False khi enable_actions=True"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_requires_auth():
    """Endpoint phải từ chối request không có Bearer token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "user_id": "user-test-001",
                "message": "vừa chi 200k",
                "enable_actions": False,
            },
        )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_stream_rejects_invalid_token():
    """Endpoint phải từ chối Bearer token không hợp lệ."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "user_id": "user-test-001",
                "message": "vừa chi 200k",
                "enable_actions": False,
            },
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401
