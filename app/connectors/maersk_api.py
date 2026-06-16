import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.connectors.base import BaseConnector
from app.core.exceptions import NotFoundError, ParsingFailedError, SourceUnavailableError, TimeoutError
from app.core.normalizer import normalize_status
from app.models.response import DateBlock, LastEvent, RouteBlock, TrackingData, TrackingEvent

logger = logging.getLogger(__name__)

_BASE = "https://api.maersk.com/track-and-trace-private/v2"


class MaerskAPIConnector(BaseConnector):
    name = "maersk_api"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        if not settings.maersk_api_enabled:
            raise SourceUnavailableError(
                self.name,
                "Maersk API is disabled. Set MAERSK_API_ENABLED=true and provide credentials to enable it.",
            )
        if not settings.maersk_consumer_key:
            raise SourceUnavailableError(
                self.name,
                "MAERSK_CONSUMER_KEY is not set. Maersk official API requires approved access.",
            )

        url = f"{_BASE}/shipments"
        headers = {"Consumer-Key": settings.maersk_consumer_key}

        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.get(url, params={"trackingNumber": number}, headers=headers)
        except httpx.TimeoutException:
            raise TimeoutError(self.name)
        except httpx.RequestError as exc:
            raise SourceUnavailableError(self.name, str(exc))

        if response.status_code == 404:
            raise NotFoundError(number, self.name)
        if response.status_code in (401, 403):
            raise SourceUnavailableError(self.name, f"HTTP {response.status_code}: authentication required")
        if response.status_code >= 500:
            raise SourceUnavailableError(self.name, f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise SourceUnavailableError(self.name, f"Unexpected HTTP {response.status_code}")

        try:
            data = response.json()
        except Exception:
            raise ParsingFailedError(self.name, "Response is not valid JSON")

        return _parse_response(data, number)


def _parse_response(data: dict, number: str) -> TrackingData:
    try:
        shipments = data.get("shipments", [])
        if not shipments:
            raise NotFoundError(number, "maersk_api")

        shipment = shipments[0]
        transport_plans = shipment.get("transportPlans", [])

        events: list[TrackingEvent] = []
        for tp in transport_plans:
            for leg in tp.get("transportLegs", []):
                for event in leg.get("events", []):
                    parsed = _parse_event(event)
                    if parsed:
                        events.append(parsed)

        events.sort(key=lambda e: e.datetime or "", reverse=False)

        last_event: LastEvent | None = None
        raw_status: str | None = None
        current_status: str | None = None

        if events:
            last = events[-1]
            last_event = LastEvent(
                event_code=last.event_code,
                event_name=last.event_name,
                location=last.location,
                datetime=last.datetime,
            )
            raw_status = last.event_name
            current_status = normalize_status(raw_status or "", "sea_container")

        route = _parse_route(transport_plans)
        dates = _parse_dates(transport_plans)

        return TrackingData(
            current_status=current_status,
            raw_status=raw_status,
            last_event=last_event,
            dates=dates,
            route=route,
            events=events,
        )
    except (NotFoundError, KeyError, IndexError, TypeError) as exc:
        if isinstance(exc, NotFoundError):
            raise
        raise ParsingFailedError("maersk_api", str(exc))


def _parse_event(event: dict) -> TrackingEvent | None:
    activity = event.get("classifierCode", "") or event.get("activity", "")
    description = event.get("description", "")
    event_dt = event.get("eventDateTime") or event.get("estimatedEventDate")
    location = (event.get("location") or {}).get("cityName") or (event.get("facility") or {}).get("cityName", "")

    if not description and not activity:
        return None

    return TrackingEvent(
        event_code=activity,
        event_name=description,
        normalized_status=normalize_status(description, "sea_container"),
        location=location,
        datetime=_normalize_datetime(event_dt),
        raw_datetime=str(event_dt) if event_dt else None,
        raw_text=description,
        vessel=event.get("vesselName"),
        voyage=event.get("voyageNumber"),
    )


def _parse_route(transport_plans: list) -> RouteBlock:
    if not transport_plans:
        return RouteBlock()
    plan = transport_plans[0]
    legs = plan.get("transportLegs", [])
    if not legs:
        return RouteBlock()
    origin = (legs[0].get("loadLocation") or {}).get("cityName") or (legs[0].get("departureLocation") or {}).get("cityName")
    destination = (legs[-1].get("dischargeLocation") or {}).get("cityName") or (legs[-1].get("arrivalLocation") or {}).get("cityName")
    transit = [
        (leg.get("dischargeLocation") or {}).get("cityName", "")
        for leg in legs[:-1]
        if (leg.get("dischargeLocation") or {}).get("cityName")
    ]
    return RouteBlock(origin=origin, destination=destination, transit_points=transit)


def _parse_dates(transport_plans: list) -> DateBlock:
    if not transport_plans:
        return DateBlock()
    plan = transport_plans[0]
    legs = plan.get("transportLegs", [])
    if not legs:
        return DateBlock()
    first, last = legs[0], legs[-1]
    return DateBlock(
        etd=_normalize_datetime(first.get("departureDateTime") or first.get("estimatedDepartureDate")),
        eta=_normalize_datetime(last.get("arrivalDateTime") or last.get("estimatedArrivalDate")),
        actual_departure=_normalize_datetime(first.get("actualDepartureDateTime")),
        actual_arrival=_normalize_datetime(last.get("actualArrivalDateTime")),
    )


def _normalize_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return str(value)
