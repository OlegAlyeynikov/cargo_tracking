import logging

from fastapi import APIRouter, Query

from app.models.request import TrackingRequest
from app.models.response import TrackingResponse
from app.services import tracking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["tracking"])


@router.post("", response_model=TrackingResponse)
async def track_shipments(
    request: TrackingRequest,
    debug: bool = Query(False, description="Include per-step debug log in response"),
) -> TrackingResponse:
    logger.info("Tracking request: %d shipments", len(request.shipments))
    return await tracking_service.process_request(request, include_debug=debug)
