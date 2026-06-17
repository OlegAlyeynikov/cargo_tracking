# Cargo Tracking API

An AI agent that accepts a list of AWB and container numbers, figures out what each number is,
queries external tracking sources, and returns a unified JSON response with statuses, events,
and errors per shipment.

## Tech Stack

- Python 3.12 + FastAPI + Pydantic v2
- httpx for plain HTTP requests, Playwright for JavaScript-rendered pages
- OpenRouter API for AI-based status normalization (fallback when rules do not match)
- Redis for result caching (cache-aside, configurable TTL)
- Docker + docker-compose

---

## Quick Start

### Option 1 — Local (no Docker)

```bash
cp .env.example .env
# Fill in OPENROUTER_API_KEY if you want AI status normalization

uv sync
uv run playwright install chromium

make dev
```

API: http://localhost:8000
Swagger docs: http://localhost:8000/docs

> Redis is optional. If it is not running, caching is silently skipped and the service still works.
> To start a local Redis quickly: `make redis`

### Option 2 — Docker (everything included)

```bash
make docker-up
```

This starts the API and Redis together. Logs: `make docker-logs`. Stop: `make docker-down`.

---

## Testing the Full Flow with curl

This section covers every endpoint and feature. Copy and run these commands one by one
to verify that everything works. All examples use `localhost:8000`.

### Health check

```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status": "ok", "version": "0.1.0"}
```

---

### 1. Basic tracking request

Send a mix of AWB numbers and container numbers. The API detects the type automatically.

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "air-1",  "number": "080-38652331"},
      {"id": "air-2",  "number": "501-20285134"},
      {"id": "sea-1",  "number": "MSKU1880987"},
      {"id": "sea-2",  "number": "TLLU4912250"},
      {"id": "bad-1",  "number": "NOTANUMBER"}
    ]
  }' | python3 -m json.tool
```

What to look for:
- `detected.type` is `air_awb` or `sea_container` for valid numbers
- `bad-1` gets `INVALID_FORMAT` in its `errors` list
- `summary.total` is 5, `summary.success` and `summary.failed` count the results
- Each result has a `quality` block with a `confidence` score

---

### 2. Debug mode — see every step the pipeline took

Add `?debug=true` to see exactly which connectors were tried and what happened.

```bash
curl -s -X POST "http://localhost:8000/api/v1/track?debug=true" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "test-1", "number": "MSKU1880987"}
    ]
  }' | python3 -m json.tool
```

The response will include a `debug` field on each result:

```json
"debug": {
  "shipment_number": "MSKU1880987",
  "steps": [
    {"step": "detect",        "status": "success", "result": "sea_container"},
    {"step": "maersk_api",    "status": "failed",  "error": "disabled"},
    {"step": "maersk_api",    "status": "retry",   "result": "attempt=2"},
    {"step": "track_trace_container", "status": "success", "url": "https://..."},
    {"step": "parse_events",  "status": "success", "events_count": 4}
  ]
}
```

Each step shows: which connector ran, whether it succeeded or failed, the URL it used,
and how many events were parsed. This is the main tool for debugging why a number
did not return data.

> Without `?debug=true`, the `debug` field is not present in the response at all.

---

### 3. Short format for integrations

Add `?short=true` to get a compact flat response. Useful for systems that only need
the current status and dates — not the full event history.

```bash
curl -s -X POST "http://localhost:8000/api/v1/track?short=true" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "internal-001", "number": "501-20285134"},
      {"id": "internal-002", "number": "MSKU1880987"}
    ]
  }' | python3 -m json.tool
```

Short format returns only: `id`, `number`, `type`, `current_status`, `eta`, `etd`,
`last_event_at`, `source`, `errors`. No events list, no quality block.

You can combine `?short=true&debug=true` if needed.

---

### 4. Webhook on status change

Pass a `webhook_url` in the request body. After the response is sent to you,
the API checks whether the current status is different from the last time it checked.
If it changed, a POST is sent to your webhook URL in the background.

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "order-123", "number": "MSKU1880987"}
    ],
    "webhook_url": "https://webhook.site/your-unique-id"
  }' | python3 -m json.tool
```

Every result includes a `status_change` block:

```json
"status_change": {
  "changed": true,
  "previous_status": "in_transit",
  "previous_status_ua": "Вантаж у транзиті.",
  "current_status": "arrived",
  "current_status_ua": "Вантаж прибув у порт / аеропорт."
}
```

If `changed` is `false`, the webhook is not called. Previous status is kept in Redis
for 7 days (`STATUS_TTL_SECONDS`).

> Use https://webhook.site to get a free test URL and see the incoming POST.

---

### 5. Periodic re-check (polling)

Pass `poll_interval_minutes` to register a subscription. The API runs tracking for these
shipments automatically every N minutes and calls the webhook if anything changes.

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "order-456", "number": "MSKU1880987"}
    ],
    "webhook_url": "https://webhook.site/your-unique-id",
    "poll_interval_minutes": 60
  }' | python3 -m json.tool
```

The response is the same as a normal tracking response. In the background, a subscription
is saved in Redis. The scheduler runs every 60 seconds and fires subscriptions that are due.

Subscriptions expire automatically after 7 days with no re-runs (Redis TTL).

**List all active subscriptions:**

```bash
curl -s http://localhost:8000/api/v1/track/schedules | python3 -m json.tool
```

Returns a list of subscription objects. Each one shows the shipments, webhook URL,
interval in seconds, and when the next run is scheduled.

**Cancel a subscription:**

Use the `request_id` from the tracking response (field `request_id` at the top level).

```bash
curl -s -X DELETE http://localhost:8000/api/v1/track/schedule/tracking-20260616-120000-abc123
```

Returns `{"cancelled": "tracking-20260616-120000-abc123"}` on success.
Returns HTTP 404 if the subscription does not exist or already expired.

---

### 6. Upload a CSV file

The file must have a `number` column. Other columns (`id`, `type`, `carrier`, `comment`)
are optional. If `id` is missing, rows are numbered `row-1`, `row-2`, etc.

Example CSV:
```
id,number,comment
air-1,080-38652331,first AWB
sea-1,MSKU1880987,Maersk container
```

```bash
curl -s -X POST http://localhost:8000/api/v1/track/file \
  -F "file=@examples/input.csv" | python3 -m json.tool
```

---

### 7. Upload an Excel file (.xlsx)

Same format as CSV, just in an Excel file. The first sheet is used. Column names must
match: `number`, `id`, `type`, `carrier`, `comment`.

```bash
curl -s -X POST http://localhost:8000/api/v1/track/file \
  -F "file=@examples/input.xlsx" | python3 -m json.tool
```

You can also combine with `?debug=true` or `?short=true`:

```bash
curl -s -X POST "http://localhost:8000/api/v1/track/file?debug=true" \
  -F "file=@examples/input.csv" | python3 -m json.tool
```

---

### 8. Maersk API (when enabled)

By default, Maersk numbers go through `track-trace.com`. If you have Maersk API credentials,
you can enable the direct API connector:

```env
MAERSK_API_ENABLED=true
MAERSK_CONSUMER_KEY=your_key
MAERSK_CLIENT_SECRET=your_secret
```

Then test with a real MSKU number:

```bash
curl -s -X POST "http://localhost:8000/api/v1/track?debug=true" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "maersk-test", "number": "MSKU1880987"}
    ]
  }' | python3 -m json.tool
```

With the API enabled, `debug.steps` will show `maersk_api` with `"status": "success"` instead
of `"status": "failed"` → `"error": "disabled"`.

---

### 9. Leasing container — expected error

Containers from leasing companies (UETU, TEXU, TTNU, TGHU, etc.) are not operated by
shipping lines, so there is no route to track. The API explains this clearly.

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "lease-1", "number": "UETU1234565"}
    ]
  }' | python3 -m json.tool
```

Expected: `errors[0].code` is `SOURCE_UNAVAILABLE` with a message explaining that
this is a Textainer container and you need the shipping line's bill of lading to track it.

---

### 10. Invalid number format

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "bad-1", "number": "NOTANUMBER"},
      {"id": "bad-2", "number": "12345"}
    ]
  }' | python3 -m json.tool
```

Expected: both get `INVALID_FORMAT` in `errors`. The `detected` field is `null`.
Other shipments in the same request are not affected.

---

### 11. Container with invalid check digit (quality warning)

ISO 6346 check digit validation runs on all container numbers. A wrong check digit
does not block processing — it adds a warning to the `quality` block.

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "warn-1", "number": "MSKU1880980"}
    ]
  }' | python3 -m json.tool
```

Look for `quality.warnings` containing `"invalid_check_digit"`.

The same works for AWB numbers — the 8th digit (modulo-7 of the first 7) is validated.

---

### 12. Air France / KLM — expected LOGIN_REQUIRED

```bash
curl -s -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {"id": "af-1", "number": "074-12345678"},
      {"id": "klm-1", "number": "076-12345678"}
    ]
  }' | python3 -m json.tool
```

Expected: `errors[0].code` is `LOGIN_REQUIRED`. This is not a bug — their tracking API
requires OAuth credentials and is protected by Akamai Bot Manager.

---

## Input Format

```json
{
  "shipments": [
    {
      "id": "internal-001",
      "number": "080-38652331",
      "type": "air_awb",
      "carrier": "CX",
      "comment": "optional note"
    }
  ],
  "webhook_url": "https://your-server.com/webhook",
  "poll_interval_minutes": 30
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `shipments` | Yes | List of shipments. Min 1, max 50. |
| `shipments[].id` | Yes | Your internal record ID — returned as-is in the result. |
| `shipments[].number` | Yes | AWB or container number. Spaces and dashes are accepted. |
| `shipments[].type` | No | Type hint: `air_awb` or `sea_container`. Not trusted without validation. |
| `shipments[].carrier` | No | Carrier hint. Not used for routing decisions. |
| `shipments[].comment` | No | Free text. Passed through to the result. |
| `webhook_url` | No | URL to POST when a status changes. Applied to all shipments in the request. |
| `poll_interval_minutes` | No | If set, re-checks shipments every N minutes. Range: 1–1440. Requires Redis. |

---

## Output Format

Full annotated response with all possible fields:

```json
{
  "request_id": "tracking-20260616-120000-abc123",
  "checked_at": "2026-06-16T12:00:00+00:00",
  "summary": {
    "total": 2,
    "success": 1,
    "failed": 1
  },
  "results": [
    {
      "input": {
        "id": "internal-001",
        "number": "501-20285134"
      },
      "detected": {
        "type": "air_awb",
        "normalized_number": "501-20285134",
        "carrier": {
          "name": "Lufthansa Cargo",
          "code": "LH",
          "source": "awb_prefix"
        }
      },
      "tracking": {
        "current_status": "departed",
        "current_status_ua": "Вантаж або судно/рейс відправлено.",
        "raw_status": "Flight LH8082 - DEP",
        "last_event": {
          "event_code": "DEP",
          "event_name": "Flight LH8082 - DEP",
          "location": "VIE → WAW",
          "datetime": "2026-06-13T14:30:00",
          "timezone": "+02:00",
          "timezone_confidence": "source_provided"
        },
        "dates": {
          "etd": "2026-06-13",
          "eta": "2026-06-14",
          "actual_departure": null,
          "actual_arrival": null
        },
        "route": {
          "origin": "HKG",
          "destination": "WAW",
          "transit_points": ["FRA", "VIE"]
        },
        "events": [
          {
            "event_code": "RCS",
            "event_name": "Shipment received",
            "normalized_status": "received",
            "normalized_status_ua": "Вантаж прийнято складом / авіалінією.",
            "location": "HKG",
            "datetime": "2026-06-07",
            "raw_datetime": "07 Jun 2026",
            "timezone": null,
            "timezone_confidence": "unknown",
            "raw_text": "07 Jun 2026 | RCS | HKG | Shipment received"
          }
        ]
      },
      "source": {
        "primary_source": "track_trace_air",
        "final_source": "track_trace_air",
        "url": "https://www.lufthansa-cargo.com/...",
        "retrieved_at": "2026-06-16T12:00:00+00:00"
      },
      "quality": {
        "confidence": 0.8,
        "data_complete": false,
        "missing_fields": ["actual_departure", "actual_arrival"],
        "warnings": []
      },
      "delay": {
        "delay_detected": true,
        "delay_days": 2,
        "risk_level": "medium"
      },
      "status_change": {
        "changed": true,
        "previous_status": "in_transit",
        "previous_status_ua": "Вантаж у транзиті.",
        "current_status": "departed",
        "current_status_ua": "Вантаж або судно/рейс відправлено."
      },
      "errors": [],
      "debug": null
    }
  ]
}
```

### Quality block

The `quality` block appears on every result regardless of success or failure.

| Field | Description |
|-------|-------------|
| `confidence` | Score from 0.0 to 1.0. How complete and reliable the data is. |
| `data_complete` | `true` if all key fields are present (current_status, last_event, dates, route). |
| `missing_fields` | List of field names that are absent or empty. |
| `warnings` | List of warning codes. See table below. |

**Possible warnings:**

| Warning | Meaning |
|---------|---------|
| `invalid_check_digit` | AWB or container number failed check digit validation. Number is still processed. |
| `partial_route` | Origin or destination is missing from the route block. Events may still be present. |

### Delay block

The `delay` block is added when `dates.eta` is set and delivery has not happened yet.

| `risk_level` | Meaning |
|-------------|---------|
| `none` | ETA is in the future or delivery already happened |
| `low` | 1–2 days past ETA |
| `medium` | 3–7 days past ETA |
| `high` | 8–14 days past ETA |
| `critical` | More than 14 days past ETA |
| `unknown` | ETA is set but could not be compared to today |

### Event datetime and timezone

All normalized datetimes are in ISO 8601 format: `2026-06-13T14:30:00` or `2026-06-13`.
Timezone is stored separately, not embedded in the datetime string (unless the source
provides it as `2026-06-13T14:30:00+02:00`).

| Field | Example | Meaning |
|-------|---------|---------|
| `datetime` | `"2026-06-13T14:30:00"` | Normalized ISO 8601 date or datetime |
| `raw_datetime` | `"13 Jun 2026 14:30"` | Original string from the source, unchanged |
| `timezone` | `"+02:00"` or `null` | UTC offset if the source provided it |
| `timezone_confidence` | `"source_provided"` or `"unknown"` | Whether timezone came from the data or is missing |

### Debug log

Only present when `?debug=true` is passed. Omitted from the response otherwise.

```json
"debug": {
  "shipment_number": "MSKU1880987",
  "steps": [
    {
      "step": "detect",
      "status": "success",
      "result": "sea_container"
    },
    {
      "step": "maersk_api",
      "status": "failed",
      "error": "disabled"
    },
    {
      "step": "track_trace_container",
      "status": "success",
      "url": "https://www.maersk.com/tracking/MSKU1880987",
      "result": "attempt=1"
    },
    {
      "step": "parse_events",
      "status": "success",
      "events_count": 6
    }
  ]
}
```

Possible step statuses: `success`, `failed`, `retry`, `skipped`.

---

## Number Detection

| Format | Detected as | Example |
|--------|-------------|---------|
| `\d{3}-?\d{8}` | `air_awb` | `501-20285134`, `50120285134` |
| `[A-Z]{4}\d{7}` | `sea_container` | `TLLU4912250`, `MSKU1880987` |
| Anything else | `unknown` | Returns `INVALID_FORMAT` |

For AWB numbers, the first 3 digits are the airline prefix. We look up the airline name and
IATA code in `data/awb_prefixes.json` (~32 major carriers). The 8th digit is the check digit
(first 7 digits mod 7). A mismatch adds `invalid_check_digit` to `quality.warnings`.

For containers, the first 4 letters are the owner code (BIC code). We look up the shipping
line in a built-in mapping. ISO 6346 check digit validation runs on all container numbers.
A mismatch adds `invalid_check_digit` to `quality.warnings` — the number is still processed.

---

## Status Codes

Every tracking event and result has a `normalized_status` in English and `normalized_status_ua`
in Ukrainian.

| Code | Ukrainian | Meaning |
|------|-----------|---------|
| `not_found` | Номер валідний, але tracking-дані не знайдено. | Valid number, no data found |
| `created` | Запис або booking створено. | Booking or record was created |
| `booked` | Вантаж заброньований у перевізника. | Cargo is booked with the carrier |
| `received` | Вантаж прийнято складом / авіалінією. | Received at warehouse or terminal |
| `in_origin_terminal` | Вантаж на origin terminal. | At the origin terminal |
| `departed` | Вантаж або судно/рейс відправлено. | Departed |
| `in_transit` | Вантаж у транзиті. | In transit |
| `arrived` | Вантаж прибув у порт / аеропорт. | Arrived at port or airport |
| `customs` | Митні процедури. | Customs processing |
| `ready_for_pickup` | Готовий до отримання. | Ready to be collected |
| `delivered` | Доставлено / видано. | Delivered to recipient |
| `container_picked_up` | Порожній або завантажений контейнер забраний. | Container picked up |
| `container_returned` | Порожній контейнер повернуто. | Empty container returned |
| `exception` | Проблема, затримка, hold, failed event. | Delay, hold, or failed event |
| `unknown` | Статус не вдалося класифікувати. | Status could not be classified |

**Normalization** works in two steps:
1. Dictionary lookup of known raw status strings and IATA event codes (DEP, RCS, RCF, DLV, etc.)
2. AI fallback via OpenRouter if the dictionary returns `unknown` — requires `OPENROUTER_API_KEY`

---

## Error Codes

| Code | When it appears |
|------|----------------|
| `INVALID_FORMAT` | Number does not match AWB or container format |
| `NOT_FOUND` | Valid number but no tracking data found at the source |
| `SOURCE_UNAVAILABLE` | Source is disabled, blocked, or temporarily down |
| `TIMEOUT` | Request or page load exceeded the timeout limit |
| `CAPTCHA_REQUIRED` | Site requires CAPTCHA — automatic extraction is not possible |
| `LOGIN_REQUIRED` | Source requires a login or API credentials |
| `PARSING_FAILED` | Response received but could not be parsed |
| `PARTIAL_DATA` | Data found but some key fields are missing |

Each error has three fields: `code`, `message` (human-readable), and `source` (which connector raised it).

---

## Connector Routing

| Number type | Prefix / pattern | Connector order |
|-------------|-----------------|-----------------|
| AWB | 074 (Air France) | AirFranceConnector → fallback |
| AWB | 076 (KLM) | AirFranceConnector → fallback |
| AWB | all others | TrackTraceAir → fallback |
| Container | MSKU, MAEU, MAEI | MaerskAPI* → TrackTraceContainer → fallback |
| Container | CAIU, CBHU, CCLU, CXDU, FCIU | CoscoConnector → TrackTraceContainer → fallback |
| Container | TRHU, TLLU | TrackTraceContainer (→ tritoncontainer.com) → fallback |
| Container | UETU, TEXU, TTNU, TGHU, TCKU, TOLU, CARU, BSIU, LGHU | Leasing error → fallback |
| Container | all others | TrackTraceContainer → fallback |

*MaerskAPI is only active when `MAERSK_API_ENABLED=true`.

---

## Connectors

### TrackTraceAirConnector — AWB tracking via track-trace.com

**Used for:** All AWB numbers except Air France (074) and KLM (076).

**How it works (two-step):**

First, we POST to `track-trace.com/aircargo/track_form` with the AWB number. This internal
form endpoint returns an HTML fragment with `#direct-form` (the carrier tracking URL) and
`#direct-type` (redirect, form, or problem).

If we get a URL, we open it with Playwright (headless Chromium) and parse the tracking table.

**Why not scrape track-trace.com directly?**

track-trace.com renders results inside a JavaScript iframe. The tracking data is not in the
initial HTML. By hitting `track_form` directly, we get the carrier URL as plain text and
skip the iframe entirely.

**Carrier-specific parsers:**
- **ENXT** (Lufthansa, many others): Angular SPA with a flight-legs table. We skip detail
  rows and extract origin, destination, flight number, date, and IATA status code per leg.
- **Lufthansa-cargo.com direct**: Playwright gets a login shell — their bot fingerprinting
  blocks headless browsers. Returns `NOT_FOUND`.
- **Generic**: For any other carrier page, we scan all HTML tables and extract rows that
  contain a date and a description.

If track-trace.com returns `type=problem`, we return `NOT_FOUND` — this is a definitive
"no data" answer from them, not a temporary failure.

---

### TrackTraceContainerConnector — container tracking via track-trace.com

**Used for:** Container numbers that are not COSCO, Maersk, or leasing-only prefixes.

Same two-step approach as the air connector. For Triton containers (TRHU, TLLU), the site
redirects to `tritoncontainer.com` which returns a simple HTML table — no Playwright needed.

**Triton (tritoncontainer.com):**
The table is transposed — column 0 is a field label, each column after that is one interchange
event. Triton shows when containers were hired out and returned, not shipping routes.

**Maersk redirect:** If track-trace.com tries to redirect to Maersk, we immediately raise
`SOURCE_UNAVAILABLE` and skip Playwright. The right path is the Maersk API.

---

### MaerskAPIConnector — Maersk Track & Trace API

**Used for:** MSKU, MAEU, MAEI container prefixes (disabled by default).

Maersk's website is protected by Akamai Bot Manager — Playwright gets blocked. The official
API gives structured JSON and is the supported way to get Maersk data.

Set `MAERSK_API_ENABLED=true` and add your credentials to enable it.
Request access at: https://developer.maersk.com

---

### CoscoConnector — COSCO Shipping Lines portal

**Used for:** CAIU, CBHU, CCLU, CXDU, FCIU prefixes.

We navigate to `elines.coscoshipping.com/scct` with Playwright, pass the container number
as a URL parameter, click Search, and wait 6 seconds for the Vue.js SPA to load results.

**Why not use the COSCO API?**

COSCO has a `shipmentExists` endpoint but it returns base64-encoded data that appears to be
encrypted with a custom algorithm. XOR decoding with several key candidates did not work.
The public tracking UI gives us the same data without reverse engineering.

---

### AirFranceConnector — Air France / KLM Cargo (074, 076)

Returns `LOGIN_REQUIRED`. Their tracking API requires OAuth credentials and is protected by
Akamai Bot Manager — both API and web scraping are blocked without authentication.

If you get API credentials from the Air France Cargo developer portal, replace this connector
with an authenticated httpx client using a Bearer token. The connector structure is ready.

---

### CarrierFallbackConnector — last resort

Used when all other connectors fail or do not apply. Returns `SOURCE_UNAVAILABLE`.
Every shipment always gets a result — the pipeline never throws an unhandled exception.

---

### Leasing company detection

Containers from leasing companies (UETU, TTNU, TEXU, TGHU, etc.) are not operated by shipping
lines. There is no shipping route to track for them. The container could be on any vessel
operated by any carrier.

We return `SOURCE_UNAVAILABLE` with a clear message explaining this instead of returning
empty results silently.

**TRHU and TLLU are exceptions** — they belong to Triton, but `tritoncontainer.com` returns
useful interchange history for them, so they go through `TrackTraceContainerConnector`.

---

## Web UI

After `make ui-build`, a browser interface is available at `http://localhost:8000/ui/`.

It lets you upload a CSV or Excel file (or paste JSON directly), run tracking, and export
results to Excel. Webhook URL and debug mode can be toggled from the UI.

---

## Adding a New Carrier Connector

1. Create `app/connectors/your_carrier.py` and extend `BaseConnector`:

```python
from app.connectors.base import BaseConnector
from app.core.exceptions import NotFoundError
from app.models.response import TrackingData

class YourCarrierConnector(BaseConnector):
    name = "your_carrier"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        # fetch and parse data here
        # raise NotFoundError, SourceUnavailableError, etc. on failure
        ...
```

2. Raise the right exception on failure — never return partial or empty data silently.
   The pipeline catches these exceptions and converts them to error codes automatically.

3. Register it in `app/core/router.py` — add your connector to the list returned by
   `get_connectors()` for the relevant prefix or type.

4. Add a test in `tests/` that mocks the fetch and verifies error handling.

---

## Running Tests

```bash
make test        # run all tests
make test-v      # verbose output
```

133 tests cover: number detection (including ISO 6346 and AWB check digit), status normalization,
delay detection, status change detection, Ukrainian translations, file parsing, API endpoints,
service pipeline, quality block, and per-connector behavior (with mocks for external sources).

---

## Environment Variables

Copy `.env.example` to `.env` and fill in what you need.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | `""` | Enables AI status normalization fallback. Optional. |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Which model to use for AI normalization. |
| `MAERSK_API_ENABLED` | `false` | Set to `true` to enable Maersk API connector. |
| `MAERSK_CONSUMER_KEY` | `""` | Maersk API consumer key. Required if enabled. |
| `MAERSK_CLIENT_SECRET` | `""` | Maersk API client secret. Required if enabled. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL. |
| `CACHE_TTL_SECONDS` | `300` | How long tracking results are cached (5 minutes). |
| `STATUS_TTL_SECONDS` | `604800` | How long status history is kept for change detection (7 days). |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Per-connector HTTP timeout. |
| `MAX_CONCURRENT_REQUESTS` | `3` | Max shipments processed in parallel (semaphore). |
| `RETRY_ATTEMPTS` | `2` | How many times to retry a connector on `SOURCE_UNAVAILABLE` or `TIMEOUT`. |
| `PLAYWRIGHT_RENDER_WAIT_SECONDS` | `5` | Seconds to wait for JavaScript to render after page load. |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `DEBUG` | `false` | FastAPI debug mode. Do not use in production. |
| `LANGSMITH_TRACING` | `false` | Set to `true` to enable LangSmith tracing for AI calls. |
| `LANGSMITH_API_KEY` | `""` | LangSmith API key. Required when tracing is enabled. |
| `LANGSMITH_PROJECT` | `cargo-tracking` | LangSmith project name for grouping traces. |

### LangSmith tracing

When `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` is set, every OpenRouter AI call is
traced automatically via `langsmith.wrappers.wrap_openai`. Traces appear in your LangSmith
dashboard grouped under `LANGSMITH_PROJECT`.

Install the package first (it is an optional dependency):

```bash
uv add langsmith
# or with the extras group:
uv sync --extra tracing
```

If `langsmith` is not installed but the flag is set, the service logs a warning and continues
without tracing — it does not crash.

---

## Known Limitations

- **Air France / KLM (074, 076)**: Their tracking API requires OAuth credentials protected
  by Akamai. Returns `LOGIN_REQUIRED`. No public scraping path exists.
- **Maersk web scraping**: Blocked by Akamai Bot Manager. Use the official API with credentials.
- **Lufthansa direct site**: Bot fingerprinting blocks Playwright. The ENXT portal (used as
  a fallback via track-trace.com) works for most Lufthansa AWBs.
- **Leasing containers** (UETU, TTNU, etc.): These are not shipping lines. Route tracking
  requires the shipping line's bill of lading number, not the container number.
- **COSCO inactive containers**: Numbers older than ~6 months may not appear in the SCCT
  portal even if they are valid.
- **Periodic polling without Redis**: If Redis is not available, `poll_interval_minutes` is
  accepted but the subscription is not saved. The initial tracking still runs normally.
- **CargoAI**: Supports 220+ airlines via API, but requires a paid API key. Not integrated.
