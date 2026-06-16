from datetime import datetime
from pydantic import BaseModel, Field


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


class DatetimeInfo(BaseModel):
    datetime: str | None = None
    raw_datetime: str | None = None
    timezone: str | None = None
    timezone_confidence: str = "unknown"


class TrackingEvent(BaseModel):
    event_code: str | None = None
    event_name: str | None = None
    normalized_status: str | None = None
    location: str | None = None
    datetime: str | None = None
    raw_datetime: str | None = None
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
    is_actual: bool = True


class TrackingData(BaseModel):
    current_status: str | None = None
    raw_status: str | None = None
    last_event: LastEvent | None = None
    dates: DateBlock = Field(default_factory=DateBlock)
    route: RouteBlock = Field(default_factory=RouteBlock)
    events: list[TrackingEvent] = Field(default_factory=list)


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
    errors: list[ErrorBlock] = Field(default_factory=list)
    debug: list[DebugStep] | None = None


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
