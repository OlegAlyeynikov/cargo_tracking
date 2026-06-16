from pydantic import BaseModel, Field, HttpUrl


class ShipmentInput(BaseModel):
    id: str = Field(..., description="Internal record ID for correlation")
    number: str = Field(..., description="AWB or container number")
    type: str | None = Field(None, description="Hint: air_awb | sea_container")
    carrier: str | None = Field(None, description="Carrier hint (not trusted without validation)")
    comment: str | None = None


class TrackingRequest(BaseModel):
    shipments: list[ShipmentInput] = Field(..., min_length=1, max_length=50)
    webhook_url: HttpUrl | None = Field(
        None,
        description="Optional URL to POST when a shipment status changes",
    )
