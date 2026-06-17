import logging
from datetime import datetime, timezone

import httpx

from app.models.response import ShipmentResult, StatusChange

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT = 10


async def fire(
    webhook_url: str,
    number: str,
    status_change: StatusChange,
    result: ShipmentResult,
) -> None:
    payload = {
        "event": "status_changed",
        "shipment_number": number,
        "previous_status": status_change.previous_status,
        "previous_status_ua": status_change.previous_status_ua,
        "current_status": status_change.current_status,
        "current_status_ua": status_change.current_status_ua,
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "result": result.model_dump(),
    }

    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info(
            "Webhook delivered for %s → %s (HTTP %s)",
            number,
            webhook_url,
            response.status_code,
        )
    except Exception as exc:
        logger.warning(
            "Webhook delivery failed for %s → %s: %s", number, webhook_url, exc
        )
