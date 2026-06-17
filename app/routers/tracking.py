import logging
from typing import Union

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile

from app.models.request import TrackingRequest
from app.models.response import TrackingResponse, TrackingResponseShort, to_short
from app.services import scheduler_service, tracking_service
from app.services.file_parser import parse_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["tracking"])


@router.post("", response_model=Union[TrackingResponse, TrackingResponseShort])
async def track_shipments(
    request: TrackingRequest,
    background_tasks: BackgroundTasks,
    debug: bool = Query(False, description="Include per-step debug log in response"),
    short: bool = Query(
        False, description="Return short format for integrations (section 8.1)"
    ),
) -> Union[TrackingResponse, TrackingResponseShort]:
    logger.info("Tracking request: %d shipments", len(request.shipments))
    response = await tracking_service.process_request(
        request, include_debug=debug, background_tasks=background_tasks
    )

    if request.poll_interval_minutes is not None:
        background_tasks.add_task(
            scheduler_service.save_subscription,
            response.request_id,
            request,
            request.poll_interval_minutes,
        )

    if short:
        return TrackingResponseShort(
            request_id=response.request_id,
            checked_at=response.checked_at,
            summary=response.summary,
            results=[to_short(r) for r in response.results],
        )
    return response


@router.post("/file", response_model=Union[TrackingResponse, TrackingResponseShort])
async def track_shipments_from_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    debug: bool = Query(False, description="Include per-step debug log in response"),
    short: bool = Query(
        False, description="Return short format for integrations (section 8.1)"
    ),
) -> Union[TrackingResponse, TrackingResponseShort]:
    """Accept a CSV or Excel file and track all shipment numbers in it.

    Required column: number
    Optional columns: id, type, carrier, comment
    """
    content = await file.read()
    filename = file.filename or "upload"

    try:
        shipments = parse_file(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info("File upload '%s': %d shipments", filename, len(shipments))
    request = TrackingRequest(shipments=shipments)
    response = await tracking_service.process_request(
        request, include_debug=debug, background_tasks=background_tasks
    )
    if short:
        return TrackingResponseShort(
            request_id=response.request_id,
            checked_at=response.checked_at,
            summary=response.summary,
            results=[to_short(r) for r in response.results],
        )
    return response


@router.delete("/schedule/{request_id}", tags=["scheduling"])
async def cancel_poll_subscription(request_id: str) -> dict:
    """Cancel a periodic re-check subscription by its request_id."""
    deleted = await scheduler_service.cancel_subscription(request_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Subscription '{request_id}' not found"
        )
    return {"cancelled": request_id}


@router.get("/schedules", tags=["scheduling"])
async def list_poll_subscriptions() -> list[dict]:
    """List all active periodic re-check subscriptions."""
    return await scheduler_service.list_subscriptions()
