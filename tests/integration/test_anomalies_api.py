import pytest
from fastapi import HTTPException

from app.api.finance import anomalies


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class _FakeConn:
    def __init__(self, *, rows=None, execute_result="UPDATE 1"):
        self._rows = rows or []
        self._execute_result = execute_result

    async def fetch(self, query, *params):
        return self._rows

    async def execute(self, query, *params):
        return self._execute_result


@pytest.mark.asyncio
async def test_get_anomaly_alerts_returns_list(monkeypatch):
    rows = [
        {
            "id": "d86ed8f8-e80d-46ce-a8c0-b7bf0a18ec96",
            "user_id": "11111111-1111-1111-1111-111111111111",
            "module_type": "finance",
            "alert_type": "spike_expense",
            "target_id": "22222222-2222-2222-2222-222222222222",
            "description": "test alert",
            "is_read": False,
            "created_at": "2026-04-01T00:00:00+00:00",
        }
    ]

    async def _fake_get_pool():
        return _FakePool(_FakeConn(rows=rows))

    monkeypatch.setattr(anomalies, "get_pool", _fake_get_pool)

    result = await anomalies.get_anomaly_alerts(
        user_id="11111111-1111-1111-1111-111111111111",
        module_type="finance",
        is_read=False,
        _="token",
    )

    assert len(result) == 1
    assert result[0].alert_type == "spike_expense"
    assert result[0].is_read is False


@pytest.mark.asyncio
async def test_mark_alert_read_raises_404_when_not_found(monkeypatch):
    async def _fake_get_pool():
        return _FakePool(_FakeConn(execute_result="UPDATE 0"))

    monkeypatch.setattr(anomalies, "get_pool", _fake_get_pool)

    with pytest.raises(HTTPException) as exc_info:
        await anomalies.mark_alert_read(
            alert_id="d86ed8f8-e80d-46ce-a8c0-b7bf0a18ec96",
            user_id="11111111-1111-1111-1111-111111111111",
            _="token",
        )

    assert exc_info.value.status_code == 404
