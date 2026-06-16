from unittest.mock import AsyncMock

import pytest

from app.models.request import ShipmentInput, TrackingRequest
from app.models.response import TrackingData
from app.services import cache_service, tracking_service


@pytest.fixture(autouse=True)
def disable_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_service, "get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set_cached", AsyncMock(return_value=None))


async def test_invalid_format_returns_error() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="test-001", number="INVALID")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "unknown"
    assert any(e.code == "INVALID_FORMAT" for e in result.errors)


async def test_multiple_shipments_processed_independently() -> None:
    request = TrackingRequest(shipments=[
        ShipmentInput(id="ok", number="MSKU1880987"),
        ShipmentInput(id="bad", number="NOTANUMBER"),
    ])
    response = await tracking_service.process_request(request)
    assert len(response.results) == 2
    bad = next(r for r in response.results if r.input["id"] == "bad")
    assert any(e.code == "INVALID_FORMAT" for e in bad.errors)


async def test_awb_number_detected_correctly() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="080-38652331")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "air_awb"


async def test_captcha_required_error_not_crashes_pipeline() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="air", number="020-26227456")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "air_awb"
    assert any(e.code in ("CAPTCHA_REQUIRED", "SOURCE_UNAVAILABLE") for e in result.errors)


async def test_maersk_disabled_by_default_returns_source_unavailable() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="msk", number="MSKU1880987")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "sea_container"
    # Maersk connector skipped — falls through to track_trace_container and carrier_fallback
    assert any(e.code in ("SOURCE_UNAVAILABLE", "CAPTCHA_REQUIRED") for e in result.errors)
    # Maersk connector itself should NOT appear as the source since it's disabled
    assert result.source is None


async def test_maersk_connector_used_when_enabled(
    monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData
) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[ShipmentInput(id="msk", number="MSKU1880987")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.tracking is not None
    assert result.tracking.current_status == "in_transit"
    assert result.source is not None
    assert "maersk" in result.source.final_source


async def test_summary_counts_correct(
    monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData
) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[
        ShipmentInput(id="ok", number="MSKU1880987"),
        ShipmentInput(id="bad", number="BAD"),
    ])
    response = await tracking_service.process_request(request)
    assert response.summary.total == 2


async def test_debug_mode_includes_steps() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="d1", number="MSKU1880987")])
    response = await tracking_service.process_request(request, include_debug=True)
    result = response.results[0]
    assert result.debug is not None
    assert len(result.debug) > 0
    assert result.debug[0].step == "detect_type"


async def test_maersk_disabled_shows_in_debug() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="msk", number="MSKU1880987")])
    response = await tracking_service.process_request(request, include_debug=True)
    result = response.results[0]
    assert result.debug is not None
    step_names = [s.step for s in result.debug]
    assert "query_maersk_api" in step_names
    maersk_step = next(s for s in result.debug if s.step == "query_maersk_api")
    assert maersk_step.status == "failed"
    assert "MAERSK_API_ENABLED" in (maersk_step.error or "")


async def test_debug_mode_false_no_steps() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="d2", number="MSKU1880987")])
    response = await tracking_service.process_request(request, include_debug=False)
    result = response.results[0]
    assert result.debug is None


async def test_airfrance_awb_returns_login_required() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="af", number="074-12345675")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "air_awb"
    assert any(e.code == "LOGIN_REQUIRED" for e in result.errors)


async def test_klm_awb_returns_login_required() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="kl", number="076-12345675")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.type == "air_awb"
    assert any(e.code == "LOGIN_REQUIRED" for e in result.errors)


async def test_airfrance_awb_carrier_identified() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="af2", number="074-12345675")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.detected is not None
    assert result.detected.carrier is not None
    assert result.detected.carrier.name == "Air France Cargo"
