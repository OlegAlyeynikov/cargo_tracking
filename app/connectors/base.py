from abc import ABC, abstractmethod

from app.models.response import TrackingData


class BaseConnector(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, number: str, shipment_type: str) -> TrackingData:
        """Fetch tracking data for a given number. Raises TrackingError on failure."""
