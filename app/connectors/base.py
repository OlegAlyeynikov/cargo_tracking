import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.response import TrackingData

logger = logging.getLogger(__name__)

_DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "debug")


class BaseConnector(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self.last_url: str | None = None
        self.debug: bool = False

    @abstractmethod
    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        """Fetch tracking data for a given number. Raises TrackingError on failure."""

    def save_debug_html(self, number: str, html: str) -> None:
        if not self.debug:
            return
        try:
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            path = os.path.join(_DEBUG_DIR, f"{self.name}_{number}_{ts}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.debug("Saved debug HTML: %s", path)
        except OSError as exc:
            logger.warning("Could not save debug HTML: %s", exc)
