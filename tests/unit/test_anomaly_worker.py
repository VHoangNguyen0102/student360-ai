from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.workers import anomaly


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


@pytest.mark.asyncio
async def test_run_anomaly_detection_creates_spike_and_budget_alerts(monkeypatch):
    month = datetime(2026, 4, 10, tzinfo=timezone.utc)
    current_row = anomaly.ExpenseRow(
        user_id="11111111-1111-1111-1111-111111111111",
        money_jar_id="22222222-2222-2222-2222-222222222222",
        jar_code="enjoyment",
        jar_name="Enjoyment",
        total_expense=Decimal("3000000"),
    )
    prev_row = anomaly.ExpenseRow(
        user_id=current_row.user_id,
        money_jar_id=current_row.money_jar_id,
        jar_code="enjoyment",
        jar_name="Enjoyment",
        total_expense=Decimal("1000000"),
    )
    budget_row = anomaly.BudgetRow(
        user_id=current_row.user_id,
        money_jar_id=current_row.money_jar_id,
        jar_code="enjoyment",
        jar_name="Enjoyment",
        budget_limit=Decimal("2500000"),
    )

    async def _fake_get_pool():
        return _FakePool(conn=object())

    async def _fake_fetch_monthly_expenses(conn, month_ref):
        if month_ref.month == 4:
            return [current_row]
        return [prev_row]

    async def _fake_fetch_active_budgets(conn, month_ref):
        return [budget_row]

    created_calls: list[str] = []

    async def _fake_insert_alert(*args, **kwargs):
        created_calls.append(kwargs["alert_type"])
        return True

    monkeypatch.setattr(anomaly, "get_pool", _fake_get_pool)
    monkeypatch.setattr(anomaly, "_fetch_monthly_expenses", _fake_fetch_monthly_expenses)
    monkeypatch.setattr(anomaly, "_fetch_active_monthly_budgets", _fake_fetch_active_budgets)
    monkeypatch.setattr(anomaly, "_insert_alert_if_missing", _fake_insert_alert)

    summary = await anomaly.run_anomaly_detection(reference_month=month)

    assert summary["month"] == "2026-04"
    assert summary["alerts_created"] == 2
    assert summary["spike_alerts_created"] == 1
    assert summary["budget_alerts_created"] == 1
    assert summary["alerts_skipped_duplicate"] == 0
    assert created_calls == [anomaly.ALERT_TYPE_SPIKE, anomaly.ALERT_TYPE_BUDGET]


@pytest.mark.asyncio
async def test_run_anomaly_detection_skips_duplicate_alerts(monkeypatch):
    month = datetime(2026, 5, 4, tzinfo=timezone.utc)
    current_row = anomaly.ExpenseRow(
        user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        money_jar_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        jar_code="essentials",
        jar_name="Essentials",
        total_expense=Decimal("1500000"),
    )
    prev_row = anomaly.ExpenseRow(
        user_id=current_row.user_id,
        money_jar_id=current_row.money_jar_id,
        jar_code="essentials",
        jar_name="Essentials",
        total_expense=Decimal("900000"),
    )

    async def _fake_get_pool():
        return _FakePool(conn=object())

    async def _fake_fetch_monthly_expenses(conn, month_ref):
        if month_ref.month == 5:
            return [current_row]
        return [prev_row]

    async def _fake_fetch_active_budgets(conn, month_ref):
        return []

    async def _fake_insert_alert(*args, **kwargs):
        return False

    monkeypatch.setattr(anomaly, "get_pool", _fake_get_pool)
    monkeypatch.setattr(anomaly, "_fetch_monthly_expenses", _fake_fetch_monthly_expenses)
    monkeypatch.setattr(anomaly, "_fetch_active_monthly_budgets", _fake_fetch_active_budgets)
    monkeypatch.setattr(anomaly, "_insert_alert_if_missing", _fake_insert_alert)

    summary = await anomaly.detect_anomalies(reference_month=month)

    assert summary["alerts_created"] == 0
    assert summary["alerts_skipped_duplicate"] == 1
    assert summary["spike_alerts_created"] == 0
