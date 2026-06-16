# Cargo Tracking API

An AI agent that accepts a list of AWB and container numbers, figures out what each number is,
queries external tracking sources, and returns a unified JSON response with statuses, events,
and errors per shipment.

## Tech Stack

- Python 3.12 + FastAPI + Pydantic v2
- httpx for plain HTTP requests, Playwright for JavaScript-rendered pages
- OpenRouter API for AI-based status normalization (fallback when rules don't match)
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

> Redis is optional. If it's not running, caching is silently skipped and the service still works.
> To start a local Redis quickly: `make redis`

### Option 2 — Docker (everything included)

```bash
make docker-up
```

This starts the API and Redis together. Logs: `make docker-logs`. Stop: `make docker-down`.

---

## Usage

### Track shipments

```bash
curl -X POST http://localhost:8000/api/v1/track \
  -H "Content-Type: application/json" \
  -d @examples/input.json
```

### Track from CSV or Excel file

```bash
curl -X POST http://localhost:8000/api/v1/track/file \
  -F "file=@examples/input.csv"

# Excel works the same way
curl -X POST http://localhost:8000/api/v1/track/file \
  -F "file=@examples/input.xlsx"
```

Required column: `number`. Optional: `id`, `type`, `carrier`, `comment`.
If `id` is missing, rows are auto-numbered as `row-1`, `row-2`, etc.

### Track with debug steps visible

```bash
curl -X POST "http://localhost:8000/api/v1/track?debug=true" \
  -H "Content-Type: application/json" \
  -d '{"shipments": [{"id": "test-1", "number": "501-20285134"}]}'
```

The `?debug=true` parameter adds a `debug` field to each result showing every step the pipeline
took — which connector was tried, what happened, and why.

### Short format for integrations (section 8.1)

```bash
curl -X POST "http://localhost:8000/api/v1/track?short=true" \
  -H "Content-Type: application/json" \
  -d '{"shipments": [{"id": "internal-001", "number": "501-20285134"}]}'
```

Returns a compact response — one flat object per shipment with only the fields needed for
internal systems: `id`, `number`, `type`, `current_status`, `eta`, `etd`, `last_event_at`,
`source`, `errors`. The full response is always available without `?short=true`.

### Webhook on status change

```bash
curl -X POST "http://localhost:8000/api/v1/track" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [{"id": "internal-001", "number": "501-20285134"}],
    "webhook_url": "https://your-server.com/webhook"
  }'
```

If a shipment's status changed since the last check, a POST is sent to the webhook URL after
the response is returned (via FastAPI `BackgroundTasks` — no delay to the client). The webhook
body contains the shipment number, `status_change` block, and the full result object.

### Web UI

After `make ui-build`, a browser interface is available at `http://localhost:8000/ui/`.

It lets you upload a CSV or Excel file (or paste JSON directly), run tracking, and export
results to Excel. Webhook URL and debug mode can be toggled from the UI.

---

## Input Format

```json
{
  "shipments": [
    {"id": "internal-001", "number": "080-38652331"},
    {"id": "internal-002", "number": "501-20285134"},
    {"id": "internal-003", "number": "TLLU4912250"},
    {"id": "internal-004", "number": "MSKU1880987"},
    {"id": "invalid-001",  "number": "NOTANUMBER"}
  ]
}
```

The `id` field is optional but useful — it links each result back to your internal record.

---

## Output Format

See `examples/output.json` for a full real-world example. Short version:

```json
{
  "request_id": "tracking-20260616-120000-abc123",
  "checked_at": "2026-06-16T12:00:00+00:00",
  "summary": {"total": 2, "success": 1, "failed": 1},
  "results": [
    {
      "input": {"id": "internal-002", "number": "501-20285134"},
      "detected": {
        "type": "air_awb",
        "normalized_number": "501-20285134",
        "carrier": {"name": "Lufthansa Cargo", "code": "LH", "source": "awb_prefix"}
      },
      "tracking": {
        "current_status": "departed",
        "raw_status": "Flight LH8082 - DEP",
        "last_event": {
          "event_code": "DEP",
          "event_name": "Flight LH8082 - DEP",
          "location": "VIE → WAW",
          "datetime": "13 Jun 2026"
        },
        "dates": {"etd": null, "eta": null, "actual_departure": null, "actual_arrival": null},
        "route": {"origin": null, "destination": null, "transit_points": []},
        "events": [
          {
            "event_code": "FOH",
            "event_name": "Flight LH8474 - FOH",
            "normalized_status": "in_origin_terminal",
            "location": "HKG → FRA",
            "datetime": "07 Jun 2026"
          },
          {
            "event_code": "DEP",
            "event_name": "Flight LH8082 - DEP",
            "normalized_status": "departed",
            "location": "VIE → WAW",
            "datetime": "13 Jun 2026"
          }
        ]
      },
      "source": {
        "primary_source": "track_trace_air",
        "final_source": "track_trace_air",
        "url": null,
        "retrieved_at": "2026-06-16T12:00:00+00:00"
      },
      "quality": {
        "confidence": 0.7,
        "data_complete": false,
        "missing_fields": ["etd", "eta", "actual_departure", "actual_arrival"],
        "warnings": []
      },
      "errors": []
    }
  ]
}
```

---

## How It Works

Every shipment goes through this pipeline:

```
Input JSON
  → NumberTypeDetector      — is it AWB or container?
  → TrackingSourceRouter    — pick the right connectors for this prefix
  → Connector chain         — try each connector in order until one works
  → StatusNormalizer        — translate raw status to a standard code
  → ResponseBuilder         — build the final JSON result
```

Each shipment is processed independently. If one fails, the others still return results.
Up to 3 shipments are processed in parallel (controlled by a semaphore to avoid hammering sources).

---

## Connectors

This is the most important part of the system. Each connector handles a specific tracking source.
Below is a detailed explanation of each one — what it does, why it was built this way, and
what it cannot do.

---

### TrackTraceAirConnector — AWB tracking via track-trace.com

**Used for:** All AWB numbers except Air France (074) and KLM (076).

**How it works (two-step approach):**

First, we make a plain HTTP POST to `track-trace.com/aircargo/track_form` with the AWB number.
This is an internal endpoint that track-trace.com uses for its own form. The response is an
HTML fragment containing `#direct-form` (the carrier's tracking URL) and `#direct-type`
(whether the result is a redirect URL, a form, or a problem).

If we get a URL, we open it with Playwright (headless Chromium) and wait for the page to render.
Then we parse the tracking table.

**Why two steps instead of just using the track-trace.com page directly?**

track-trace.com renders its results inside an iframe using JavaScript. The tracking data is
not in the initial HTML — the browser has to load the carrier's page and inject it. When we
tried scraping the track-trace.com page directly, we never saw the `#direct-type` element
because it gets created dynamically. By hitting `track_form` directly (which is a simple form
endpoint), we get the carrier URL as plain text and skip the iframe entirely.

**Carrier-specific parsers:**

Different airlines render their tracking data differently:

- **ENXT** (used by many airlines including Lufthansa): An Angular SPA with a flight-legs
  table. Each row represents one flight segment. We skip "detail" rows (collapsed sub-rows
  that have only 1–2 non-empty cells) and skip rows where the first cell is not a number
  (the index column). We extract origin, destination, carrier code, flight number, date,
  and IATA status code per leg.

- **Lufthansa-cargo.com** (direct site): Playwright loads the page but only gets a login
  shell. Lufthansa uses bot fingerprinting that blocks headless browsers. The page renders
  nothing useful even with a 6-second wait. We return `NOT_FOUND` in this case.

- **Generic parser**: For any other carrier page, we scan all HTML tables and extract rows
  that contain a date-like string and a text description.

**Result type "problem":**

If track-trace.com returns `type=problem`, it means the carrier is not supported or the
AWB prefix is unknown to them. We return `NOT_FOUND` — not `SOURCE_UNAVAILABLE` — because
this is a definitive "no data" answer, not a temporary failure.

---

### TrackTraceContainerConnector — container tracking via track-trace.com

**Used for:** Sea container numbers that are not COSCO, Maersk, or leasing-only prefixes.
Also handles TRHU and TLLU (Triton containers) via a direct HTTP path.

**How it works:**

Same two-step approach as the air connector: POST to `track-trace.com/container/track_form`,
get the carrier URL, then scrape the carrier page.

**Triton (tritoncontainer.com) — no Playwright needed:**

For TRHU and TLLU numbers, track-trace.com redirects to `tritoncontainer.com`. This site
renders a simple HTML table without JavaScript. We fetch it with plain httpx (much faster
and more reliable than Playwright).

The table has an unusual layout — it's transposed. Column 0 is a field label ("On Hire Date",
"Customer", etc.) and each column after that represents one interchange event. We read the
interchange type names from row 1 and build events column by column, then sort them by
the "Interchange Sequence" field (ascending = chronological order).

Note: Triton is a container leasing company. Their data shows when the container was hired
out and returned, not the shipping route. If you need route events (vessel name, port of
loading, etc.), you need the shipping line's bill of lading — not the container number.

**Maersk (maersk.com) — fast rejection:**

If track-trace.com redirects to a Maersk URL, we immediately raise `SOURCE_UNAVAILABLE`
without launching Playwright. Maersk uses strong bot protection (Akamai Bot Manager) and
their public tracking page does not work with headless browsers. The right way to get Maersk
data is through the Maersk Track & Trace API (see MaerskAPIConnector below).

**Generic Playwright path:**

For all other carriers, we open the carrier URL with Playwright, wait 3 seconds for rendering,
and parse whatever tables appear on the page.

---

### MaerskAPIConnector — Maersk Track & Trace API

**Used for:** MSKU, MAEU, MAEI container prefixes (when enabled).

**Disabled by default.** Maersk's official API requires approved access — you need a company
email and a customer code. To enable it:

```env
MAERSK_API_ENABLED=true
MAERSK_CONSUMER_KEY=your_key
MAERSK_CLIENT_SECRET=your_secret
```

Request access at: https://developer.maersk.com

**Why use the API instead of scraping?**

Maersk's website is protected by Akamai Bot Manager, which detects headless browsers.
Playwright gets blocked even when we mimic a real browser. The API gives us structured JSON
directly and is the officially supported way to get tracking data.

---

### CoscoConnector — COSCO Shipping Lines portal (SCCT)

**Used for:** CAIU, CBHU, CCLU, CXDU, FCIU prefixes.

**How it works:**

COSCO has a public tracking portal at `elines.coscoshipping.com/scct`. We navigate to it
with Playwright, passing the container number as a URL parameter. Then we click the "Search"
button and wait 6 seconds for the Vue.js SPA to load results.

We check the page text for phrases like "no results found" or "not found" before trying to
parse events. If any of those phrases appear, we return `NOT_FOUND` immediately.

**Why Playwright and not the API?**

COSCO does have a `shipmentExists` API endpoint, but it returns base64-encoded data that
appears to be encrypted or obfuscated with a custom algorithm. We tried XOR decoding with
several key candidates — none worked. Rather than spending time reverse-engineering it,
we use the public tracking UI which gives us the same data.

**Why not use track-trace.com for COSCO?**

track-trace.com does sometimes redirect COSCO numbers to the SCCT portal, but the redirect
is inconsistent and was returning "problem" for several CAIU numbers during testing.
Going directly to the COSCO portal gives more reliable results.

---

### AirFranceConnector — Air France / KLM Cargo (074, 076 prefixes)

**Used for:** AWB numbers starting with 074 (Air France Cargo) or 076 (KLM Cargo).

**What it does:** Returns `LOGIN_REQUIRED` with an explanation.

**Why not scrape afklcargo.com?**

We checked. The site has a REST API at `/api/tracking/{awb}` that returns proper JSON —
but it requires authentication (returns 401 without a token). The site also runs Akamai
Bot Manager, so Playwright gets blocked before the page even loads. There is no public
tracking page that works without logging in.

track-trace.com also does not support Air France — it redirects 074/076 numbers back to
its own form page with no carrier URL.

**Integration path:** If you get API credentials from the Air France Cargo developer portal,
replace this connector with an authenticated httpx client using a Bearer token. The connector
structure is already in place.

---

### CarrierFallbackConnector — last resort

**Used for:** Any number where all other connectors failed or don't apply.

Returns `SOURCE_UNAVAILABLE` with a message saying no direct integration exists yet.
This is intentional — the pipeline should never throw an unhandled exception. Every
shipment must return a result, even if that result is an error.

---

### Leasing company detection (not a connector, but part of routing)

Containers with prefixes like UETU (Textainer), TEXU (Textainer), TTNU (Triton), TGHU (Triton),
and others belong to container leasing companies. These companies rent containers to shipping
lines — they don't operate vessels themselves.

If you send a leasing container number, there is no "shipping route" to track. The container
could be on any ship operated by any shipping line. To track it, you need the shipping line's
bill of lading number, not the container number.

We return `SOURCE_UNAVAILABLE` with a clear explanation of this — rather than silently failing
or returning empty results.

**TRHU and TLLU are exceptions** — they are also Triton, but `tritoncontainer.com` returns
useful interchange history for them, so they go through `TrackTraceContainerConnector`.

---

## Number Detection

| Format | Detected as | Example |
|--------|-------------|---------|
| `\d{3}-?\d{8}` | `air_awb` | `501-20285134` |
| `[A-Z]{4}\d{7}` | `sea_container` | `TLLU4912250` |
| Anything else | `unknown` | → `INVALID_FORMAT` error |

For AWB numbers, the first 3 digits are the airline prefix. We look up the airline name and
IATA code in `data/awb_prefixes.json` (covers ~32 major carriers).

For containers, the first 4 letters are the owner code (BIC code). We look up the shipping
line in a built-in mapping.

ISO 6346 check digit validation is performed on container numbers. An invalid check digit
produces a warning in the `quality.warnings` field — the number is still processed, not rejected.

---

## Status Normalization

Every tracking source uses its own status names. We normalize them all to a common set of
values so that your application only needs to handle one vocabulary.

Normalization works in two stages:

1. **Deterministic lookup**: A dictionary of known raw status strings maps to standard codes.
   IATA event codes (DEP, RCS, RCF, DLV, etc.) and common text patterns are covered here.

2. **AI fallback (OpenRouter)**: If the lookup returns "unknown", we send the raw status to
   an LLM via OpenRouter and ask it to classify the status. This covers unusual phrases from
   carrier websites that are not in our dictionary. Requires `OPENROUTER_API_KEY`.

| Code | Meaning |
|------|---------|
| `not_found` | Number is valid but no tracking data exists |
| `created` | Booking or record was created |
| `booked` | Cargo is booked with the carrier |
| `received` | Cargo received at warehouse or terminal |
| `in_origin_terminal` | Cargo is at the origin terminal |
| `departed` | Cargo or vessel/flight has departed |
| `in_transit` | Cargo is in transit |
| `arrived` | Cargo arrived at port or airport |
| `customs` | Customs processing in progress |
| `ready_for_pickup` | Ready to be collected |
| `delivered` | Delivered to recipient |
| `container_picked_up` | Empty or loaded container picked up |
| `container_returned` | Empty container returned to depot |
| `exception` | Delay, hold, or failed event |
| `unknown` | Status could not be classified |

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

---

## Connector Routing Summary

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

133 tests cover: number detection (including ISO 6346 check digit), status normalization,
delay detection, status change detection, Ukrainian translations, file parsing, API endpoints,
service pipeline, quality block, and per-connector behavior (with mocks for external sources).

---

## Bonus Features Implemented

All items from section 15 of the spec are implemented:

- **Redis caching** — results are cached by shipment number with a configurable TTL.
  Cache is skipped silently if Redis is not available.
- **Status change detection** — each result includes a `status_change` block comparing
  the current status to the previous one (stored in Redis with a 7-day TTL).
- **Webhook on status change** — pass `webhook_url` in the request body; a POST is fired
  as a background task when `status_change.changed` is true.
- **Delay detection** — if ETA is set and the current date is past it with no delivery,
  `delay_detected: true` and `risk_level` (low / medium / high / critical) are added.
- **Ukrainian translations** — `current_status_ua` on each result and `normalized_status_ua`
  on each event, using the exact descriptions from section 7 of the spec.
- **Short format** — `?short=true` returns a flat compact response for integrations (section 8.1).
- **CSV / Excel input** — `POST /api/v1/track/file` accepts `.csv` and `.xlsx` files.
- **Excel export** — available from the web UI via the Export Excel button.
- **Web UI** — React + Tailwind interface at `/ui/` for file upload, JSON input, results
  table with expandable events, and Excel export. Run `make ui-build` first.
- **Debug mode** — `?debug=true` adds a step-by-step log to each result showing which
  connectors were tried and what happened.
- **Semaphore limiting** — max 3 concurrent external requests to avoid overloading sources.

---

## Known Limitations

- **Air France / KLM (074, 076)**: Their tracking API requires OAuth credentials protected
  by Akamai. Returns `LOGIN_REQUIRED`. No public scraping path available.
- **Maersk web scraping**: Blocked by Akamai Bot Manager. Use the official API with credentials.
- **Lufthansa direct site**: Bot fingerprinting blocks Playwright. The ENXT portal (used as
  a fallback by track-trace.com) works for most Lufthansa AWBs.
- **Leasing containers** (UETU, TTNU, etc.): These are not shipping lines. Route tracking
  requires the shipping line's bill of lading number.
- **COSCO inactive containers**: Numbers older than ~6 months may not appear in the SCCT
  portal even if they are valid.
- **CargoAI**: Supports 220+ airlines via API, but requires a paid API key. Not integrated.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in what you need:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Optional | Enables AI status normalization fallback |
| `MAERSK_API_ENABLED` | Optional | Set to `true` to enable Maersk API connector |
| `MAERSK_CONSUMER_KEY` | If enabled | Maersk API consumer key |
| `MAERSK_CLIENT_SECRET` | If enabled | Maersk API client secret |
| `REDIS_URL` | Optional | Default: `redis://localhost:6379/0` |
| `CACHE_TTL_SECONDS` | Optional | How long to cache results (default: 3600) |
| `REQUEST_TIMEOUT_SECONDS` | Optional | Per-connector timeout (default: 60) |
