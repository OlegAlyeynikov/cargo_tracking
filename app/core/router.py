from app.config import settings
from app.connectors.airfrance_connector import AirFranceConnector
from app.connectors.base import BaseConnector
from app.connectors.carrier_fallback import CarrierFallbackConnector
from app.connectors.cosco_connector import CoscoConnector
from app.connectors.maersk_api import MaerskAPIConnector
from app.connectors.track_trace_air import TrackTraceAirConnector
from app.connectors.track_trace_container import TrackTraceContainerConnector
from app.core.detector import _CONTAINER_OWNERS
from app.core.exceptions import SourceUnavailableError
from app.models.response import TrackingData

# AWB prefixes where track-trace.com has no coverage and a direct connector is used
# 074 = Air France Cargo, 076 = KLM Cargo (same portal: afklcargo.com)
_AFKL_AWB_PREFIXES = {"074", "076"}

_MAERSK_PREFIXES = {"MSKU", "MAEU", "MAEI"}

# COSCO Shipping Lines BIC prefixes
_COSCO_PREFIXES = {"CAIU", "CBHU", "CCLU", "CXDU", "FCIU"}

# Container leasing companies — they do not operate shipping routes.
# Names sourced from _CONTAINER_OWNERS in detector.py (single source of truth).
_LEASING_PREFIXES = {
    code
    for code, name in _CONTAINER_OWNERS.items()
    if name in {"Triton International", "Textainer", "Touax", "CAI International",
                "Beacon Intermodal", "Seaco"}
}

_track_trace_air = TrackTraceAirConnector()
_track_trace_container = TrackTraceContainerConnector()
_maersk_api = MaerskAPIConnector()
_cosco = CoscoConnector()
_airfrance = AirFranceConnector()
_carrier_fallback = CarrierFallbackConnector()


class _DisabledConnector(BaseConnector):
    """Placeholder that appears in the debug log when a connector is configured but disabled."""

    def __init__(self, connector_name: str, reason: str) -> None:
        self.name = connector_name
        self._reason = reason

    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        raise SourceUnavailableError(self.name, self._reason)


def get_connectors(number: str, shipment_type: str) -> list[BaseConnector]:
    """Return ordered list of connectors to try for a given number and type."""
    if shipment_type == "air_awb":
        awb_prefix = number.replace("-", "")[:3]
        if awb_prefix in _AFKL_AWB_PREFIXES:
            return [_airfrance, _carrier_fallback]
        return [_track_trace_air, _carrier_fallback]

    if shipment_type == "sea_container":
        owner_code = number[:4].upper() if len(number) >= 4 else ""

        if owner_code in _MAERSK_PREFIXES:
            if settings.maersk_api_enabled:
                return [_maersk_api, _track_trace_container, _carrier_fallback]
            return [
                _DisabledConnector(
                    "maersk_api",
                    "Disabled via MAERSK_API_ENABLED=false. Set to true and provide credentials to enable.",
                ),
                _track_trace_container,
                _carrier_fallback,
            ]

        if owner_code in _COSCO_PREFIXES:
            return [_cosco, _track_trace_container, _carrier_fallback]

        if owner_code in _LEASING_PREFIXES and owner_code not in {"TRHU", "TLLU"}:
            company_name = _CONTAINER_OWNERS.get(owner_code, "This company")
            return [
                _DisabledConnector(
                    "leasing_company",
                    f"{company_name} is a container leasing company, not a shipping line. "
                    "Route tracking requires the shipping line's bill of lading number.",
                ),
                _carrier_fallback,
            ]

        return [_track_trace_container, _carrier_fallback]

    return [_carrier_fallback]
