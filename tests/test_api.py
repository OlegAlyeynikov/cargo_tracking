from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.services import cache_service


@pytest.fixture(autouse=True)
def disable_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_service, "get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set_cached", AsyncMock(return_value=None))


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_track_endpoint_returns_valid_schema(client: AsyncClient) -> None:
    payload = {"shipments": [{"id": "internal-001", "number": "080-38652331"}]}
    response = await client.post("/api/v1/track", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "checked_at" in data
    assert "summary" in data
    assert "results" in data
    assert len(data["results"]) == 1


async def test_track_invalid_number(client: AsyncClient) -> None:
    payload = {"shipments": [{"id": "bad", "number": "NOTANUMBER"}]}
    response = await client.post("/api/v1/track", json=payload)
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["detected"]["type"] == "unknown"
    assert any(e["code"] == "INVALID_FORMAT" for e in result["errors"])


async def test_track_multiple_shipments(client: AsyncClient) -> None:
    payload = {
        "shipments": [
            {"id": "internal-001", "number": "080-38652331"},
            {"id": "internal-009", "number": "MSKU1880987"},
            {"id": "bad", "number": "NOTANUMBER"},
        ]
    }
    response = await client.post("/api/v1/track", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] == 3
    assert len(data["results"]) == 3


async def test_track_empty_list_rejected(client: AsyncClient) -> None:
    payload = {"shipments": []}
    response = await client.post("/api/v1/track", json=payload)
    assert response.status_code == 422


async def test_debug_mode_query_param(client: AsyncClient) -> None:
    payload = {"shipments": [{"id": "d1", "number": "MSKU1880987"}]}
    response = await client.post("/api/v1/track?debug=true", json=payload)
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["debug"] is not None


async def test_all_input_shipments_from_json_file(client: AsyncClient) -> None:
    import json
    from pathlib import Path
    root = Path(__file__).parent.parent
    candidates = ["entry_data.json", "Вхіхні_дані_для_пошуку.json"]
    source = next((root / f for f in candidates if (root / f).exists()), None)
    assert source is not None, f"Input JSON not found. Expected one of: {candidates}"
    data = json.loads(source.read_text())
    response = await client.post("/api/v1/track", json=data)
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["total"] == 10
    types = {r["input"]["id"]: r["detected"]["type"] for r in result["results"]}
    for i in range(1, 6):
        assert types[f"internal-00{i}"] == "air_awb"
    for i in range(6, 11):
        key = f"internal-0{i:02d}"
        assert types[key] == "sea_container"
