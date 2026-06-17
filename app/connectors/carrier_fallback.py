import logging

from app.connectors.base import BaseConnector
from app.core.exceptions import SourceUnavailableError
from app.models.response import TrackingData

logger = logging.getLogger(__name__)


class CarrierFallbackConnector(BaseConnector):
    """Generic fallback for carrier websites not yet integrated.
    Returns SOURCE_UNAVAILABLE with a descriptive message."""

    name = "carrier_fallback"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        logger.info(
            "CarrierFallbackConnector: %s — no direct integration available", number
        )
        raise SourceUnavailableError(
            self.name,
            "Direct carrier integration is not yet implemented. Add a carrier-specific connector to support this number.",
        )
