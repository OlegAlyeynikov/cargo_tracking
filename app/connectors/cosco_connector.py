import asyncio
import logging
import re

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from app.config import settings
from app.connectors.base import BaseConnector
from app.core.exceptions import NotFoundError, SourceUnavailableError, TimeoutError
from app.core.normalizer import normalize_status
from app.models.response import DateBlock, LastEvent, RouteBlock, TrackingData, TrackingEvent

logger = logging.getLogger(__name__)

_SCCT_BASE = "https://elines.coscoshipping.com/scct/public/ct/base"
_NO_RESULTS_TEXTS = (
    "no results found",
    "please check the number",
    "no data",
    "not found",
)
_DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{2}/\d{2}/\d{4}"
    r"|\d{2}[-. ][A-Za-z]{3}[-. ]\d{2,4}"
    r"|\d{2}\.\d{2}\.\d{4}"
)


class CoscoConnector(BaseConnector):
    name = "cosco"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        try:
            return await asyncio.wait_for(
                _scrape(number),
                timeout=settings.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(self.name)


async def _scrape(number: str) -> TrackingData:
    url = f"{_SCCT_BASE}?lang=en&trackingType=CNTR&number={number}"

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
                await page.goto(url, timeout=settings.request_timeout_seconds * 1000, wait_until="networkidle")
            except PlaywrightTimeout:
                raise TimeoutError("cosco")

            await asyncio.sleep(2)

            # Click Search if button present
            search_btn = page.locator("button").filter(has_text="Search")
            if await search_btn.count() > 0:
                await search_btn.first.click()
                await asyncio.sleep(6)

            html = await page.content()
        finally:
            await browser.close()

    page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()

    if any(phrase in page_text for phrase in _NO_RESULTS_TEXTS):
        raise NotFoundError(number, "cosco")

    events = _parse_cosco_html(html, number)
    if not events:
        raise NotFoundError(number, "cosco")

    known = [e for e in events if e.normalized_status and e.normalized_status != "unknown"]
    last = known[-1] if known else events[-1]
    return TrackingData(
        current_status=last.normalized_status,
        raw_status=last.event_name,
        last_event=LastEvent(
            event_code=last.event_code,
            event_name=last.event_name,
            location=last.location,
            datetime=last.datetime,
        ),
        dates=DateBlock(),
        route=RouteBlock(),
        events=events,
    )


def _parse_cosco_html(html: str, number: str) -> list[TrackingEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[TrackingEvent] = []

    # Try milestone/step elements first (COSCO uses card-based UI)
    for el in soup.find_all(attrs={"class": re.compile(r"milestone|step|event|track", re.I)}):
        text = el.get_text(" ", strip=True)
        if not text or len(text) < 5:
            continue
        date_match = _DATE_RE.search(text)
        date_val = date_match.group(0) if date_match else None
        desc = text.replace(date_val, "").strip() if date_val else text
        if not desc:
            continue
        events.append(TrackingEvent(
            event_name=desc[:200],
            normalized_status=normalize_status(desc, "sea_container"),
            datetime=date_val,
            raw_datetime=date_val,
            raw_text=text[:300],
        ))

    if events:
        return events

    # Fallback: generic table parsing
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        for row in rows[1:]:
            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
            non_empty = [c for c in cells if c]
            if len(non_empty) < 2:
                continue
            date_val = next((c for c in non_empty if _DATE_RE.search(c)), None)
            desc_val = next(
                (c for c in non_empty if not _DATE_RE.search(c) and len(c) > 3), None
            )
            loc_val = next(
                (c for c in non_empty if c not in (date_val, desc_val) and len(c) > 2), None
            )
            if not desc_val:
                continue
            events.append(TrackingEvent(
                event_name=desc_val,
                normalized_status=normalize_status(desc_val, "sea_container"),
                location=loc_val,
                datetime=date_val,
                raw_datetime=date_val,
                raw_text=" | ".join(non_empty),
            ))

    return events
