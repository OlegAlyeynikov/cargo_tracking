from datetime import datetime, timedelta, timezone

import pytest

from app.models.response import DateBlock, TrackingData
from app.services.tracking_service import _compute_delay


def _tracking(
    eta: str | None = None,
    actual_arrival: str | None = None,
    current_status: str | None = None,
) -> TrackingData:
    return TrackingData(
        current_status=current_status,
        dates=DateBlock(eta=eta, actual_arrival=actual_arrival),
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _future(days: int = 5) -> str:
    return _iso(datetime.now(timezone.utc) + timedelta(days=days))


def _past(days: int) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(days=days))


def test_no_tracking_data_returns_none() -> None:
    assert _compute_delay(None) is None


def test_no_eta_returns_none() -> None:
    assert _compute_delay(_tracking()) is None


def test_eta_in_future_no_delay() -> None:
    result = _compute_delay(_tracking(eta=_future(5)))
    assert result is not None
    assert result.delay_detected is False
    assert result.risk_level == "none"
    assert result.delay_days == 0


def test_eta_today_no_delay() -> None:
    result = _compute_delay(_tracking(eta=_future(0)))
    assert result is not None
    assert result.delay_detected is False


def test_1_day_late_low_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(1)))
    assert result is not None
    assert result.delay_detected is True
    assert result.delay_days == 1
    assert result.risk_level == "low"


def test_3_days_late_low_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(3)))
    assert result is not None
    assert result.risk_level == "low"


def test_4_days_late_medium_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(4)))
    assert result is not None
    assert result.risk_level == "medium"


def test_7_days_late_medium_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(7)))
    assert result is not None
    assert result.risk_level == "medium"


def test_8_days_late_high_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(8)))
    assert result is not None
    assert result.risk_level == "high"


def test_14_days_late_high_risk() -> None:
    result = _compute_delay(_tracking(eta=_past(14)))
    assert result is not None
    assert result.risk_level == "high"


def test_15_days_late_critical() -> None:
    result = _compute_delay(_tracking(eta=_past(15)))
    assert result is not None
    assert result.delay_detected is True
    assert result.delay_days == 15
    assert result.risk_level == "critical"


def test_delivered_on_time_no_delay() -> None:
    eta = _future(2)
    actual = _future(1)
    result = _compute_delay(_tracking(eta=eta, actual_arrival=actual, current_status="delivered"))
    assert result is not None
    assert result.delay_detected is False
    assert result.risk_level == "none"


def test_delivered_late_shows_delay() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    eta = _iso(base)
    actual = _iso(base + timedelta(days=5))
    result = _compute_delay(_tracking(eta=eta, actual_arrival=actual, current_status="delivered"))
    assert result is not None
    assert result.delay_detected is True
    assert result.delay_days == 5
    assert result.risk_level == "medium"


def test_delivered_early_no_delay() -> None:
    base = datetime(2026, 1, 10, tzinfo=timezone.utc)
    eta = _iso(base)
    actual = _iso(base - timedelta(days=2))
    result = _compute_delay(_tracking(eta=eta, actual_arrival=actual, current_status="delivered"))
    assert result is not None
    assert result.delay_detected is False
    assert result.delay_days == -2
    assert result.risk_level == "none"


def test_delivered_without_actual_arrival_no_delay() -> None:
    result = _compute_delay(_tracking(eta=_past(10), current_status="delivered"))
    assert result is not None
    assert result.delay_detected is False
    assert result.risk_level == "none"
