import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks

from app.config import settings
from app.core import detector, router
from app.core.exceptions import TrackingError
from app.core.translator import translate_status
from app.models.request import ShipmentInput, TrackingRequest
from app.models.response import (
    DebugStep,
    DelayInfo,
    ErrorBlock,
    QualityBlock,
    ShipmentResult,
    SourceBlock,
    StatusChange,
    SummaryBlock,
    TrackingData,
    TrackingResponse,
)
from app.services import cache_service, webhook_service

logger = logging.getLogger(__name__)

_RISK_THRESHOLDS = [
    (3, "low"),
    (7, "medium"),
    (14, "high"),
]


async def process_request(
    request: TrackingRequest,
    include_debug: bool = False,
    background_tasks: BackgroundTasks | None = None,
) -> TrackingResponse:
    checked_at = datetime.now(timezone.utc).isoformat()
    request_id = f"tracking-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    webhook_url = str(request.webhook_url) if request.webhook_url else None

    async def bounded_track(shipment: ShipmentInput) -> ShipmentResult:
        async with semaphore:
            return await _track_one(shipment, include_debug)

    results = await asyncio.gather(*[bounded_track(s) for s in request.shipments])

    if webhook_url and background_tasks:
        for result in results:
            if result.status_change and result.status_change.changed:
                number = result.detected.normalized_number if result.detected else "unknown"
                background_tasks.add_task(
                    webhook_service.fire,
                    webhook_url,
                    number,
                    result.status_change,
                    result,
                )

    success = sum(1 for r in results if not r.errors or all(e.code == "PARTIAL_DATA" for e in r.errors))
    failed = len(results) - success

    return TrackingResponse(
        request_id=request_id,
        checked_at=checked_at,
        summary=SummaryBlock(total=len(results), success=success, failed=failed),
        results=list(results),
    )


async def _track_one(shipment: ShipmentInput, include_debug: bool) -> ShipmentResult:
    debug_steps: list[DebugStep] = []
    errors: list[ErrorBlock] = []
    input_dict = shipment.model_dump(exclude_none=True)

    detected = detector.detect(shipment.number)
    debug_steps.append(DebugStep(step="detect_type", status="success", result=detected.type))

    if detected.type == "unknown":
        errors.append(ErrorBlock(
            code="INVALID_FORMAT",
            message=f"Number '{shipment.number}' does not match AWB or container number format",
        ))
        return ShipmentResult(
            input=input_dict,
            detected=detected,
            errors=errors,
            debug=debug_steps if include_debug else None,
        )

    cached = await cache_service.get_cached(detected.normalized_number)
    if cached:
        debug_steps.append(DebugStep(step="cache_lookup", status="success", result="hit"))
        result = ShipmentResult.model_validate(cached)
        if include_debug:
            result.debug = debug_steps
        return result

    debug_steps.append(DebugStep(step="cache_lookup", status="success", result="miss"))

    connectors = router.get_connectors(detected.normalized_number, detected.type)
    tracking_data: TrackingData | None = None
    final_source: str | None = None

    for connector in connectors:
        step_name = f"query_{connector.name}"
        try:
            tracking_data = await connector.fetch(detected.normalized_number, detected.type)
            _apply_translations(tracking_data)
            final_source = connector.name
            debug_steps.append(DebugStep(
                step=step_name,
                status="success",
                events_count=len(tracking_data.events),
            ))
            break
        except TrackingError as exc:
            debug_steps.append(DebugStep(step=step_name, status="failed", error=exc.message))
            errors.append(ErrorBlock(code=exc.code, message=exc.message, source=exc.source))

    quality = _build_quality(tracking_data, errors)
    delay = _compute_delay(tracking_data)
    status_change = await _detect_status_change(detected.normalized_number, tracking_data)

    source_block: SourceBlock | None = None
    if final_source:
        source_block = SourceBlock(
            primary_source=connectors[0].name,
            final_source=final_source,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    result = ShipmentResult(
        input=input_dict,
        detected=detected,
        tracking=tracking_data,
        source=source_block,
        quality=quality,
        delay=delay,
        status_change=status_change,
        errors=errors,
        debug=debug_steps if include_debug else None,
    )

    if tracking_data and not errors:
        await cache_service.set_cached(detected.normalized_number, result.model_dump())

    return result


def _compute_delay(tracking_data: TrackingData | None) -> DelayInfo | None:
    if tracking_data is None:
        return None

    current_status = tracking_data.current_status
    dates = tracking_data.dates

    if not dates.eta:
        return None

    try:
        eta = datetime.fromisoformat(dates.eta)
        if eta.tzinfo is None:
            eta = eta.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    # Cargo already delivered — compare actual arrival vs ETA if available
    if current_status == "delivered":
        if dates.actual_arrival:
            try:
                actual = datetime.fromisoformat(dates.actual_arrival)
                if actual.tzinfo is None:
                    actual = actual.replace(tzinfo=timezone.utc)
                delay_days = (actual - eta).days
                return _make_delay_info(delay_days)
            except ValueError:
                pass
        return DelayInfo(delay_detected=False, delay_days=0, risk_level="none")

    now = datetime.now(timezone.utc)
    if now <= eta:
        return DelayInfo(delay_detected=False, delay_days=0, risk_level="none")

    delay_days = (now - eta).days
    return _make_delay_info(delay_days)


def _make_delay_info(delay_days: int) -> DelayInfo:
    if delay_days <= 0:
        return DelayInfo(delay_detected=False, delay_days=delay_days, risk_level="none")

    for threshold, level in _RISK_THRESHOLDS:
        if delay_days <= threshold:
            return DelayInfo(delay_detected=True, delay_days=delay_days, risk_level=level)

    return DelayInfo(delay_detected=True, delay_days=delay_days, risk_level="critical")


async def _detect_status_change(number: str, tracking_data: TrackingData | None) -> StatusChange | None:
    if tracking_data is None:
        return None

    current = tracking_data.current_status
    previous = await cache_service.get_previous_status(number)

    if current:
        await cache_service.set_previous_status(number, current)

    changed = previous is not None and previous != current
    return StatusChange(
        changed=changed,
        previous_status=previous,
        previous_status_ua=translate_status(previous),
        current_status=current,
        current_status_ua=translate_status(current),
    )


def _apply_translations(tracking_data: TrackingData) -> None:
    tracking_data.current_status_ua = translate_status(tracking_data.current_status)
    for event in tracking_data.events:
        event.normalized_status_ua = translate_status(event.normalized_status)


def _build_quality(tracking_data: TrackingData | None, errors: list[ErrorBlock]) -> QualityBlock:
    if tracking_data is None:
        return QualityBlock(confidence=0.0, data_complete=False, missing_fields=["all"])

    missing: list[str] = []
    if not tracking_data.dates.eta:
        missing.append("eta")
    if not tracking_data.dates.etd:
        missing.append("etd")
    if not tracking_data.route.origin:
        missing.append("origin")
    if not tracking_data.route.destination:
        missing.append("destination")
    if not tracking_data.events:
        missing.append("events")

    has_errors = bool(errors)
    confidence = max(0.0, 1.0 - len(missing) * 0.15 - (0.3 if has_errors else 0.0))

    return QualityBlock(
        confidence=round(confidence, 2),
        data_complete=not missing,
        missing_fields=missing,
        warnings=[e.code for e in errors if e.code == "PARTIAL_DATA"],
    )
