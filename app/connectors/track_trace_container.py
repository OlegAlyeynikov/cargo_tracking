import asyncio
import logging

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from app.config import settings
from app.connectors.base import BaseConnector
from app.core.date_utils import normalize_date
from app.core.exceptions import NotFoundError, SourceUnavailableError, TimeoutError
from app.core.normalizer import normalize_status
from app.models.response import DateBlock, RouteBlock, TrackingData, TrackingEvent, last_event_from

logger = logging.getLogger(__name__)

_TRACK_FORM_URL = "https://www.track-trace.com/container/track_form"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "Origin": "https://www.track-trace.com",
    "Referer": "https://www.track-trace.com/container",
}


class TrackTraceContainerConnector(BaseConnector):
    name = "track_trace_container"

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
        raise NotFoundError(number, "track_trace_container")

    if result_type == "form":
        raise SourceUnavailableError(
            "track_trace_container",
            "Carrier requires direct form submission and is not yet supported",
        )

    logger.info("Fetching carrier page for %s: %s", number, carrier_url)

    if "tritoncontainer.com" in carrier_url:
        return await _scrape_triton_httpx(carrier_url, number)

    if "maersk.com" in carrier_url:
        raise SourceUnavailableError(
            "track_trace_container",
            "Maersk scraping is not supported. Enable MAERSK_API_ENABLED=true for Maersk tracking.",
        )

    return await _scrape_with_playwright(carrier_url, number, save_debug_html)


async def _resolve_carrier_url(number: str) -> tuple[str, str]:
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                _TRACK_FORM_URL,
                content=f"number={number}&config=206100",
                headers=_HEADERS,
            )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise TimeoutError("track_trace_container")
    except httpx.HTTPError as exc:
        raise SourceUnavailableError("track_trace_container", str(exc))

    soup = BeautifulSoup(response.text, "html.parser")
    direct_form_el = soup.find(id="direct-form")
    direct_type_el = soup.find(id="direct-type")

    url = direct_form_el.get_text(strip=True) if direct_form_el else ""
    result_type = ""
    if direct_type_el:
        span = direct_type_el.find("span")
        result_type = span.get_text(strip=True) if span else direct_type_el.get_text(strip=True)

    logger.info("track-trace resolve %s: type=%r url=%.80s", number, result_type, url)
    return url, result_type


# --- tritoncontainer.com -------------------------------------------------


async def _scrape_triton_httpx(url: str, number: str) -> TrackingData:
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": _HEADERS["User-Agent"]},
            )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise TimeoutError("track_trace_container")
    except httpx.HTTPError as exc:
        raise SourceUnavailableError("track_trace_container", str(exc))

    events = _parse_triton_table(response.text, number)
    if not events:
        raise NotFoundError(number, "track_trace_container")

    last = events[-1]
    return TrackingData(
        current_status=last.normalized_status,
        raw_status=last.event_name,
        last_event=last_event_from(last),
        dates=DateBlock(),
        route=RouteBlock(),
        events=events,
    )


def _parse_triton_table(html: str, number: str) -> list[TrackingEvent]:
    """
    tritoncontainer.com table layout (all rows have 4 cells):
      Row 0: ["History"]                                — title, skip
      Row 1: ["Interchange Type", "TypeA", "TypeB", …] — interchange type per column
      Row 2+: ["Field Label", valA, valB, …]           — data rows

    We iterate per column (interchange event) and pull field values.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 3:
        return []

    # Row 0 = title ("History"), row 1 = interchange-type header
    def _cells(row) -> list[str]:
        return [td.get_text(strip=True) for td in row.find_all(["td", "th"])]

    type_row_cells = _cells(rows[1])
    if not type_row_cells or type_row_cells[0] != "Interchange Type":
        return []

    interchange_types = type_row_cells[1:]  # column names
    num_events = len(interchange_types)

    # Build field_name → list[str] from rows 2+
    field_map: dict[str, list[str]] = {}
    for row in rows[2:]:
        cells = _cells(row)
        if not cells:
            continue
        label = cells[0]
        values = cells[1:]
        if label:
            field_map[label] = values

    if not field_map:
        return []

    seq_values = field_map.get("Interchange Sequence", [])

    # Build (sequence, event) pairs so we can sort chronologically
    indexed: list[tuple[int, TrackingEvent]] = []

    for col_idx in range(num_events):
        def _val(label: str, idx: int = col_idx) -> str:
            vals = field_map.get(label, [])
            return vals[idx] if idx < len(vals) else ""

        interchange_type = interchange_types[col_idx]
        if not interchange_type:
            continue

        try:
            seq = int(seq_values[col_idx]) if col_idx < len(seq_values) else 0
        except ValueError:
            seq = 0

        on_hire_date = _val("On Hire Date")
        off_hire_date = _val("Off Hire/Retired Date")
        on_hire_port = _val("On Hire Port") or _val("On Hire Depot")
        off_hire_port = _val("Off Hire Port") or _val("Off Hire Depot")
        customer = _val("Customer")

        if on_hire_date:
            event_name = f"{interchange_type} - On Hire"
            if customer:
                event_name += f" ({customer})"
            indexed.append((seq, TrackingEvent(
                event_name=event_name,
                normalized_status=_map_triton_status(interchange_type, "on_hire"),
                location=on_hire_port or None,
                datetime=normalize_date(on_hire_date),
                raw_datetime=on_hire_date,
                raw_text=f"{interchange_type} | {on_hire_date} | {on_hire_port}",
            )))

        if off_hire_date:
            event_name = f"{interchange_type} - Off Hire"
            if customer:
                event_name += f" ({customer})"
            indexed.append((seq, TrackingEvent(
                event_name=event_name,
                normalized_status=_map_triton_status(interchange_type, "off_hire"),
                location=off_hire_port or None,
                datetime=normalize_date(off_hire_date),
                raw_datetime=off_hire_date,
                raw_text=f"{interchange_type} | {off_hire_date} | {off_hire_port}",
            )))

    indexed.sort(key=lambda x: x[0])
    return [ev for _, ev in indexed]


def _map_triton_status(interchange_type: str, phase: str) -> str:
    lower = interchange_type.lower()
    if phase == "on_hire":
        if "lease out" in lower:
            return "container_picked_up"
        if "reposition" in lower:
            return "in_transit"
        return "in_origin_terminal"
    # off_hire
    if "turn in" in lower:
        return "container_returned"
    return "arrived"


# --- generic Playwright scraping ----------------------------------------


async def _scrape_with_playwright(url: str, number: str, save_debug_html=None) -> TrackingData:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                )
            )

            try:
                nav_response = await page.goto(url, timeout=settings.request_timeout_seconds * 1000, wait_until="domcontentloaded")
            except PlaywrightTimeout:
                raise TimeoutError("track_trace_container")

            if nav_response and nav_response.status >= 400:
                raise SourceUnavailableError(
                    "track_trace_container",
                    f"Carrier site returned HTTP {nav_response.status}",
                )

            await asyncio.sleep(settings.playwright_render_wait_seconds)
            html = await page.content()
        finally:
            await browser.close()

    events = _parse_generic_tables(html)
    if not events:
        if save_debug_html:
            save_debug_html(number, html)
        raise NotFoundError(number, "track_trace_container")

    last = events[-1]
    return TrackingData(
        current_status=last.normalized_status,
        raw_status=last.event_name,
        last_event=last_event_from(last),
        dates=DateBlock(),
        route=RouteBlock(),
        events=events,
    )


def _parse_generic_tables(html: str) -> list[TrackingEvent]:
    from app.connectors.scraping_utils import parse_generic_table_events
    return parse_generic_table_events(html, "sea_container")
