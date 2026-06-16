import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.response import DateBlock, RouteBlock, TrackingData, TrackingEvent


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_maersk_tracking() -> TrackingData:
    return TrackingData(
        current_status="in_transit",
        raw_status="Loaded on vessel",
        dates=DateBlock(etd="2026-06-01T10:00:00+00:00", eta="2026-06-20T08:00:00+00:00"),
        route=RouteBlock(origin="CNSHA", destination="NLRTM", transit_points=["SGSIN"]),
        events=[
            TrackingEvent(
                event_code="LOAD",
                event_name="Loaded on vessel",
                normalized_status="departed",
                location="CNSHA",
                datetime="2026-06-01T10:00:00+00:00",
            )
        ],
    )
