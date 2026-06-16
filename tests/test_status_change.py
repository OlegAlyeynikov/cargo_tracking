from unittest.mock import AsyncMock, patch

import pytest

from app.models.request import ShipmentInput, TrackingRequest
from app.models.response import TrackingData
from app.services import cache_service, tracking_service


@pytest.fixture(autouse=True)
def disable_result_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_service, "get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set_cached", AsyncMock(return_value=None))


async def test_no_previous_status_change_is_false(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set_previous_status", AsyncMock())

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="MSKU1880987")])
    response = await tracking_service.process_request(request)
    result = response.results[0]

    assert result.status_change is not None
    assert result.status_change.changed is False
    assert result.status_change.previous_status is None
    assert result.status_change.current_status == "in_transit"
    assert result.status_change.current_status_ua == "У транзиті"


async def test_same_status_change_is_false(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value="in_transit"))
    monkeypatch.setattr(cache_service, "set_previous_status", AsyncMock())

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="MSKU1880987")])
    response = await tracking_service.process_request(request)
    result = response.results[0]

    assert result.status_change is not None
    assert result.status_change.changed is False


async def test_different_status_change_is_true(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value="departed"))
    monkeypatch.setattr(cache_service, "set_previous_status", AsyncMock())

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="MSKU1880987")])
    response = await tracking_service.process_request(request)
    result = response.results[0]

    assert result.status_change is not None
    assert result.status_change.changed is True
    assert result.status_change.previous_status == "departed"
    assert result.status_change.previous_status_ua == "Відправлено"
    assert result.status_change.current_status == "in_transit"
    assert result.status_change.current_status_ua == "У транзиті"


async def test_no_tracking_data_status_change_is_none() -> None:
    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="INVALID123")])
    response = await tracking_service.process_request(request)
    result = response.results[0]
    assert result.status_change is None


async def test_status_saved_to_cache_on_success(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value=None))
    set_mock = AsyncMock()
    monkeypatch.setattr(cache_service, "set_previous_status", set_mock)

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    request = TrackingRequest(shipments=[ShipmentInput(id="t1", number="MSKU1880987")])
    await tracking_service.process_request(request)

    set_mock.assert_called_once_with("MSKU1880987", "in_transit")


async def test_webhook_fired_on_status_change(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from fastapi import BackgroundTasks

    from app import config
    from app.connectors import maersk_api
    from app.services import webhook_service

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value="departed"))
    monkeypatch.setattr(cache_service, "set_previous_status", AsyncMock())

    fire_mock = AsyncMock()
    monkeypatch.setattr(webhook_service, "fire", fire_mock)

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    bg = BackgroundTasks()
    request = TrackingRequest(
        shipments=[ShipmentInput(id="t1", number="MSKU1880987")],
        webhook_url="https://example.com/hook",
    )
    await tracking_service.process_request(request, background_tasks=bg)

    assert len(bg.tasks) == 1


async def test_webhook_not_fired_when_no_change(monkeypatch: pytest.MonkeyPatch, sample_maersk_tracking: TrackingData) -> None:
    from fastapi import BackgroundTasks

    from app import config
    from app.connectors import maersk_api

    monkeypatch.setattr(config.settings, "maersk_api_enabled", True)
    monkeypatch.setattr(cache_service, "get_previous_status", AsyncMock(return_value="in_transit"))
    monkeypatch.setattr(cache_service, "set_previous_status", AsyncMock())

    async def mock_fetch(self, number: str, shipment_type: str) -> TrackingData:
        return sample_maersk_tracking

    monkeypatch.setattr(maersk_api.MaerskAPIConnector, "fetch", mock_fetch)

    bg = BackgroundTasks()
    request = TrackingRequest(
        shipments=[ShipmentInput(id="t1", number="MSKU1880987")],
        webhook_url="https://example.com/hook",
    )
    await tracking_service.process_request(request, background_tasks=bg)

    assert len(bg.tasks) == 0
