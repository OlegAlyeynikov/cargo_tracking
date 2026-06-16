import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile

from app.models.request import TrackingRequest
from app.models.response import TrackingResponse
from app.services import tracking_service
from app.services.file_parser import parse_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["tracking"])


@router.post("", response_model=TrackingResponse)
async def track_shipments(
    request: TrackingRequest,
    background_tasks: BackgroundTasks,
    debug: bool = Query(False, description="Include per-step debug log in response"),
) -> TrackingResponse:
    logger.info("Tracking request: %d shipments", len(request.shipments))
    return await tracking_service.process_request(request, include_debug=debug, background_tasks=background_tasks)


@router.post("/file", response_model=TrackingResponse)
async def track_shipments_from_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    debug: bool = Query(False, description="Include per-step debug log in response"),
) -> TrackingResponse:
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
    return await tracking_service.process_request(request, include_debug=debug, background_tasks=background_tasks)
