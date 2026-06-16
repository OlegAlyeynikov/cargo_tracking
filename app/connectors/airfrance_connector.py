import logging

from app.connectors.base import BaseConnector
from app.core.exceptions import LoginRequiredError
from app.models.response import TrackingData

logger = logging.getLogger(__name__)

_API_URL = "https://www.afklcargo.com/api/tracking/{awb}"
_TRACKING_URL = "https://www.afklcargo.com/en/tools-and-tips/tools/cargo-tracking"


class AirFranceConnector(BaseConnector):
    """Connector for Air France Cargo / KLM Cargo (AWB prefixes 074, 076).

    The afklcargo.com REST API (/api/tracking/{awb}) requires OAuth authentication
    protected by Akamai Bot Manager. Public scraping is not possible without credentials.
    Returns LOGIN_REQUIRED to signal that an API key / partner account is needed.

    Integration path: obtain API credentials from Air France Cargo Developer Portal,
    then replace this connector with an authenticated httpx client using Bearer token.
    """

    name = "airfrance_cargo"

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        logger.info(
            "AirFranceConnector: %s — API requires authentication (Akamai-protected, 401)",
            number,
        )
        raise LoginRequiredError(
            self.name,
        )
