from typing import Any, Callable
from pydantic import BaseModel, Field, model_serializer


class ErrorBlock(BaseModel):
    code: str
    message: str
    source: str = ""


class CarrierInfo(BaseModel):
    name: str | None = None
    code: str | None = None
    source: str | None = None


class DetectedInfo(BaseModel):
    type: str
    normalized_number: str
    carrier: CarrierInfo | None = None
    warnings: list[str] = Field(default_factory=list, exclude=True)


class DatetimeInfo(BaseModel):
    datetime: str | None = None
    raw_datetime: str | None = None
    timezone: str | None = None
    timezone_confidence: str = "unknown"


class TrackingEvent(BaseModel):
    event_code: str | None = None
    event_name: str | None = None
    normalized_status: str | None = None
    normalized_status_ua: str | None = None
    location: str | None = None
    datetime: str | None = None
    raw_datetime: str | None = None
    timezone: str | None = None
    timezone_confidence: str = "unknown"
    raw_text: str | None = None
    vessel: str | None = None
    voyage: str | None = None


class DateBlock(BaseModel):
    etd: str | None = None
    eta: str | None = None
    actual_departure: str | None = None
    actual_arrival: str | None = None


class RouteBlock(BaseModel):
    origin: str | None = None
    destination: str | None = None
    transit_points: list[str] = Field(default_factory=list)


class LastEvent(BaseModel):
    event_code: str | None = None
    event_name: str | None = None
    location: str | None = None
    datetime: str | None = None
    timezone: str | None = None
    timezone_confidence: str = "unknown"
    is_actual: bool = True


def last_event_from(event: "TrackingEvent") -> LastEvent:
    return LastEvent(
        event_code=event.event_code,
        event_name=event.event_name,
        location=event.location,
        datetime=event.datetime,
        timezone=event.timezone,
        timezone_confidence=event.timezone_confidence,
    )


class TrackingData(BaseModel):
    current_status: str | None = None
    current_status_ua: str | None = None
    raw_status: str | None = None
    last_event: LastEvent | None = None
    dates: DateBlock = Field(default_factory=DateBlock)
    route: RouteBlock = Field(default_factory=RouteBlock)
    events: list[TrackingEvent] = Field(default_factory=list)


class StatusChange(BaseModel):
    changed: bool
    previous_status: str | None = None
    previous_status_ua: str | None = None
    current_status: str | None = None
    current_status_ua: str | None = None


class SourceBlock(BaseModel):
    primary_source: str
    final_source: str
    url: str | None = None
    retrieved_at: str


class QualityBlock(BaseModel):
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    data_complete: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DebugStep(BaseModel):
    step: str
    status: str
    result: str | None = None
    url: str | None = None
    events_count: int | None = None
    error: str | None = None


class DebugLog(BaseModel):
    shipment_number: str
    steps: list[DebugStep]


class DelayInfo(BaseModel):
    delay_detected: bool
    delay_days: int | None = None
    risk_level: str  # none | low | medium | high | critical | unknown


class ShipmentResult(BaseModel):
    input: dict
    detected: DetectedInfo | None = None
    tracking: TrackingData | None = None
    source: SourceBlock | None = None
    quality: QualityBlock = Field(default_factory=QualityBlock)
    delay: DelayInfo | None = None
    status_change: StatusChange | None = None
    errors: list[ErrorBlock] = Field(default_factory=list)
    debug: DebugLog | None = None

    @model_serializer(mode="wrap")
    def _serialize(
        self, handler: Callable[["ShipmentResult"], dict[str, Any]]
    ) -> dict[str, Any]:
        data = handler(self)
        if data.get("debug") is None:
            data.pop("debug", None)
        return data


class SummaryBlock(BaseModel):
    total: int
    success: int
    failed: int


class TrackingResponse(BaseModel):
    request_id: str
    checked_at: str
    summary: SummaryBlock
    results: list[ShipmentResult]


class ShipmentResultShort(BaseModel):
    id: str
    number: str
    type: str
    current_status: str | None
    eta: str | None
    etd: str | None
    last_event_at: str | None
    source: str | None
    errors: list[ErrorBlock]


class TrackingResponseShort(BaseModel):
    request_id: str
    checked_at: str
    summary: SummaryBlock
    results: list[ShipmentResultShort]


def to_short(result: "ShipmentResult") -> ShipmentResultShort:
    input_data = result.input or {}
    tracking = result.tracking
    source = result.source
    detected = result.detected

    return ShipmentResultShort(
        id=input_data.get("id", ""),
        number=input_data.get("number", ""),
        type=detected.type if detected else "unknown",
        current_status=tracking.current_status if tracking else None,
        eta=tracking.dates.eta if tracking else None,
        etd=tracking.dates.etd if tracking else None,
        last_event_at=tracking.last_event.datetime
        if tracking and tracking.last_event
        else None,
        source=source.final_source if source else None,
        errors=result.errors,
    )
