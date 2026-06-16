"""Background scheduler for periodic shipment re-checks.

When a TrackingRequest includes poll_interval_minutes, the request is stored
in Redis as a subscription. An asyncio background task wakes every 60 seconds,
finds subscriptions that are due, re-runs tracking, and fires the webhook if
any status changed.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.models.request import ShipmentInput, TrackingRequest
from app.services import cache_service

logger = logging.getLogger(__name__)

_SCHEDULE_PREFIX = "cargo:schedule:"
_POLL_INTERVAL_SECONDS = 60


async def save_subscription(
    request_id: str,
    request: TrackingRequest,
    interval_minutes: int,
) -> None:
    client = await cache_service.get_client()
    if client is None:
        logger.warning("Redis unavailable — cannot persist poll subscription %s", request_id)
        return

    now = datetime.now(timezone.utc).timestamp()
    payload = {
        "request_id": request_id,
        "shipments": [s.model_dump() for s in request.shipments],
        "webhook_url": str(request.webhook_url) if request.webhook_url else None,
        "interval_seconds": interval_minutes * 60,
        "next_run_at": now + interval_minutes * 60,
    }
    key = f"{_SCHEDULE_PREFIX}{request_id}"
    ttl = interval_minutes * 60 * 24 * 7  # auto-expire subscriptions after 7 days of inactivity
    await client.set(key, json.dumps(payload), ex=ttl)
    logger.info("Scheduled poll every %d min for request %s", interval_minutes, request_id)


async def cancel_subscription(request_id: str) -> bool:
    client = await cache_service.get_client()
    if client is None:
        return False
    deleted = await client.delete(f"{_SCHEDULE_PREFIX}{request_id}")
    return bool(deleted)


async def list_subscriptions() -> list[dict]:
    client = await cache_service.get_client()
    if client is None:
        return []
    keys = await client.keys(f"{_SCHEDULE_PREFIX}*")
    if not keys:
        return []
    raw = await client.mget(*keys)
    result = []
    for item in raw:
        if item:
            try:
                result.append(json.loads(item))
            except (json.JSONDecodeError, ValueError):
                pass
    return result


async def _run_due_subscriptions() -> None:
    from app.services.tracking_service import process_request

    subscriptions = await list_subscriptions()
    now = datetime.now(timezone.utc).timestamp()

    for sub in subscriptions:
        if sub.get("next_run_at", float("inf")) > now:
            continue

        request_id = sub["request_id"]
        logger.info("Running scheduled poll for %s", request_id)

        try:
            shipments = [ShipmentInput(**s) for s in sub["shipments"]]
            webhook_url = sub.get("webhook_url")
            request = TrackingRequest(
                shipments=shipments,
                webhook_url=webhook_url,  # type: ignore[arg-type]
            )
            await process_request(request)

            # Update next_run_at in Redis
            interval = sub["interval_seconds"]
            sub["next_run_at"] = now + interval
            client = await cache_service.get_client()
            if client:
                key = f"{_SCHEDULE_PREFIX}{request_id}"
                await client.set(key, json.dumps(sub), ex=interval * 24 * 7)

        except Exception as exc:
            logger.warning("Scheduled poll failed for %s: %s", request_id, exc)


async def run_scheduler_loop() -> None:
    logger.info("Scheduler started — checking every %ds", _POLL_INTERVAL_SECONDS)
    while True:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        try:
            await _run_due_subscriptions()
        except Exception as exc:
            logger.warning("Scheduler error: %s", exc)
