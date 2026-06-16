import re

from bs4 import BeautifulSoup

from app.core.date_utils import normalize_date
from app.core.normalizer import normalize_status
from app.models.response import TrackingEvent

_DATE_RE = re.compile(
    r"\d{2}[-/ ][A-Za-z]{3}[-/ ]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{2}/\d{2}/\d{4}"
    r"|\d{2}\.\d{2}\.\d{4}"
)


def parse_generic_table_events(html: str, shipment_type: str) -> list[TrackingEvent]:
    """Extract tracking events from a plain HTML table.

    Shared by air and container scrapers — the only difference is the
    shipment_type passed to normalize_status.
    """
    soup = BeautifulSoup(html, "html.parser")
    events: list[TrackingEvent] = []

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
                normalized_status=normalize_status(desc_val, shipment_type),
                location=loc_val,
                datetime=normalize_date(date_val),
                raw_datetime=date_val,
                raw_text=" | ".join(non_empty),
            ))

    return events
