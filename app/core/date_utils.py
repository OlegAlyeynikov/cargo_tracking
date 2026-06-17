import re
from datetime import datetime

_FORMATS = [
    "%d.%m.%Y",  # 20.05.2026  (track-trace air)
    "%d-%b-%Y",  # 19-Jan-2021 (triton)
    "%d %b %Y",  # 19 Jan 2021
    "%Y-%m-%d",  # 2026-05-20
    "%m/%d/%Y",  # 05/20/2026
    "%d/%m/%Y",  # 20/05/2026
    "%d.%m.%Y %H:%M",  # 20.05.2026 14:30
    "%d %b %Y %H:%M",  # 19 Jan 2021 08:00
]

_TZ_RE = re.compile(r"([+-]\d{2}:?\d{2}|Z)$")


def normalize_date(raw: str | None) -> str | None:
    """Parse raw date string and return ISO 8601. Never loses data on parse failure."""
    if not raw:
        return None
    cleaned = raw.strip()
    for fmt in _FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            if "%H" in fmt or "%M" in fmt:
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def parse_datetime_info(raw: str | None) -> tuple[str | None, str | None, str]:
    """Parse a date/datetime string and return (iso_datetime, timezone, timezone_confidence).

    timezone_confidence values:
      "source_provided" — timezone was explicitly present in the source data
      "unknown"         — no timezone info in source; datetime has no offset suffix
    """
    if not raw:
        return None, None, "unknown"
    cleaned = str(raw).strip()

    tz_match = _TZ_RE.search(cleaned)
    if tz_match:
        tz_raw = tz_match.group(1)
        tz_str = "+00:00" if tz_raw == "Z" else tz_raw
        if len(tz_str) == 5 and tz_str[0] in ("+", "-"):
            tz_str = f"{tz_str[:3]}:{tz_str[3:]}"
        try:
            dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            return dt.isoformat(), tz_str, "source_provided"
        except ValueError:
            pass

    for fmt in _FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            if "%H" in fmt or "%M" in fmt:
                return dt.strftime("%Y-%m-%dT%H:%M:%S"), None, "unknown"
            return dt.strftime("%Y-%m-%d"), None, "unknown"
        except ValueError:
            continue

    return cleaned, None, "unknown"
