import asyncio
import logging
import re

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from app.config import settings
from app.connectors.base import BaseConnector
from app.core.date_utils import normalize_date
from app.core.exceptions import NotFoundError, SourceUnavailableError, TimeoutError
from app.core.normalizer import normalize_status
from app.models.response import (
    DateBlock,
    RouteBlock,
    TrackingData,
    TrackingEvent,
    last_event_from,
)

logger = logging.getLogger(__name__)

_TRACK_FORM_URL = "https://www.track-trace.com/aircargo/track_form"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "Origin": "https://www.track-trace.com",
    "Referer": "https://www.track-trace.com/aircargo",
}

_DATE_RE = re.compile(
    r"\d{2}[-/ ][A-Za-z]{3}[-/ ]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{2}/\d{2}/\d{4}"
    r"|\d{2}\.\d{2}\.\d{4}"
)


class TrackTraceAirConnector(BaseConnector):
    name = "track_trace_air"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        try:
            return await asyncio.wait_for(
                _fetch(number, self.save_debug_html),
                timeout=settings.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(self.name)


async def _fetch(number: str, save_debug_html=None) -> TrackingData:
    carrier_url, result_type = await _resolve_carrier_url(number)

    if result_type == "problem" or (result_type == "url" and not carrier_url):
        raise NotFoundError(number, "track_trace_air")

    if result_type == "form":
        raise SourceUnavailableError(
            "track_trace_air",
            "Carrier requires direct form submission and is not yet supported",
        )

    logger.info("Fetching air carrier page for %s: %s", number, carrier_url)
    return await _scrape_with_playwright(carrier_url, number, save_debug_html)


async def _resolve_carrier_url(number: str) -> tuple[str, str]:
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                _TRACK_FORM_URL,
                content=f"number={number}&config=206100",
                headers=_HEADERS,
            )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise TimeoutError("track_trace_air")
    except httpx.HTTPError as exc:
        raise SourceUnavailableError("track_trace_air", str(exc))

    soup = BeautifulSoup(response.text, "html.parser")
    form_el = soup.find(id="direct-form")
    type_el = soup.find(id="direct-type")

    url = form_el.get_text(strip=True) if form_el else ""
    if type_el:
        span = type_el.find("span")
        result_type = (
            span.get_text(strip=True) if span else type_el.get_text(strip=True)
        )
    else:
        result_type = ""

    logger.info(
        "track-trace air resolve %s: type=%r url=%.80s", number, result_type, url
    )
    return url, result_type


async def _scrape_with_playwright(
    url: str, number: str, save_debug_html=None
) -> TrackingData:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent=_HEADERS["User-Agent"],
            )

            try:
                nav_response = await page.goto(
                    url,
                    timeout=settings.request_timeout_seconds * 1000,
                    wait_until="domcontentloaded",
                )
            except PlaywrightTimeout:
                raise TimeoutError("track_trace_air")

            if nav_response and nav_response.status >= 400:
                raise SourceUnavailableError(
                    "track_trace_air",
                    f"Carrier site returned HTTP {nav_response.status}",
                )

            # Allow JS-rendered content to load
            await asyncio.sleep(settings.playwright_render_wait_seconds)
            html = await page.content()
        finally:
            await browser.close()

    events = _parse_events(html, url)
    if not events:
        if save_debug_html:
            save_debug_html(number, html)
        raise NotFoundError(number, "track_trace_air")

    # Use last event with a known status; fall back to absolute last
    known = [
        e for e in events if e.normalized_status and e.normalized_status != "unknown"
    ]
    last = known[-1] if known else events[-1]
    return TrackingData(
        current_status=last.normalized_status,
        raw_status=last.event_name,
        last_event=last_event_from(last),
        dates=DateBlock(),
        route=RouteBlock(),
        events=events,
    )


def _parse_events(html: str, url: str) -> list[TrackingEvent]:
    if "lufthansa" in url:
        return _parse_lufthansa(html)
    if "enxt" in url:
        return _parse_enxt(html)
    return _parse_generic_tables(html)


def _parse_lufthansa(html: str) -> list[TrackingEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[TrackingEvent] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [
            th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])
        ]
        for row in rows[1:]:
            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
            if not cells or not any(cells):
                continue

            event_map = dict(zip(headers, cells))
            event_name = (
                event_map.get("event")
                or event_map.get("status")
                or event_map.get("description")
                or next(
                    (c for c in cells if len(c) > 3 and not _DATE_RE.search(c)), None
                )
            )
            date_val = (
                event_map.get("date")
                or event_map.get("time")
                or next((c for c in cells if _DATE_RE.search(c)), None)
            )
            location = event_map.get("station") or event_map.get("location")

            if not event_name:
                continue

            events.append(
                TrackingEvent(
                    event_name=event_name,
                    normalized_status=normalize_status(event_name, "air_awb"),
                    location=location,
                    datetime=normalize_date(date_val),
                    raw_datetime=date_val,
                    raw_text=" | ".join(c for c in cells if c),
                )
            )

    return events


def _parse_enxt(html: str) -> list[TrackingEvent]:
    """
    ENXT Angular SPA table layout (after Playwright renders it):
      Row 0: headers [idx, flight_takeoff, flight_land, Carrier, Flight Nr, Flight Date, Weight, Volume, Pieces, Flight Status, CO2, ...]
      Odd data rows: [N, origin, dest, carrier, flight_nr, date, weight, volume, pieces, status_code, co2, ...]
      Even detail rows: single collapsed detail cell — skip these
    """
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [
            th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])
        ]
        if "flight nr" not in " ".join(headers) and "flight_takeoff" not in " ".join(
            headers
        ):
            continue

        events: list[TrackingEvent] = []
        for row in rows[1:]:
            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
            clean = [c.strip() for c in cells]
            # Skip detail/expand rows (only 1 non-empty, or first cell is not a number)
            non_empty = [c for c in clean if c]
            if len(non_empty) <= 2:
                continue
            if not (clean[0].isdigit() if clean else False):
                continue

            # Expected: [idx, origin, dest, carrier, flight_nr, date, weight, volume, pieces, status, ...]
            origin = clean[1] if len(clean) > 1 else None
            dest = clean[2] if len(clean) > 2 else None
            carrier = clean[3] if len(clean) > 3 else None
            flight_nr = clean[4] if len(clean) > 4 else None
            date_val = (
                clean[5] if len(clean) > 5 and _DATE_RE.search(clean[5]) else None
            )
            status_code = clean[9] if len(clean) > 9 else None

            event_name = (
                f"Flight {carrier}{flight_nr}"
                if carrier and flight_nr
                else "Flight leg"
            )
            if status_code:
                event_name += f" - {status_code}"
            location = f"{origin} → {dest}" if origin and dest else None

            events.append(
                TrackingEvent(
                    event_code=status_code,
                    event_name=event_name,
                    normalized_status=normalize_status(
                        status_code or event_name, "air_awb"
                    ),
                    location=location,
                    datetime=normalize_date(date_val),
                    raw_datetime=date_val,
                    raw_text=" | ".join(c for c in clean if c),
                )
            )

        if events:
            return events

    return []


def _parse_generic_tables(html: str) -> list[TrackingEvent]:
    from app.connectors.scraping_utils import parse_generic_table_events

    return parse_generic_table_events(html, "air_awb")
