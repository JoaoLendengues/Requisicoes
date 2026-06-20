from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from ..services.text_normalizer import normalize_upper_required


class DeliveryCreate(BaseModel):
    client_id: int = Field(gt=0)
    vendor_id: int = Field(gt=0)
    city: str = Field(min_length=1, max_length=120)
    truck_name: str = Field(min_length=1, max_length=120)
    loaded_by: str = Field(min_length=1, max_length=150)
    delivery_date: date

    @field_validator("city", "truck_name", "loaded_by", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return normalize_upper_required(value)


class DeliveryScheduleUpdate(BaseModel):
    delivery_date: date
    reason: str = Field(min_length=3)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        return normalize_upper_required(value)


class DeliveryCancellationUpdate(BaseModel):
    reason: str = Field(min_length=3)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        return normalize_upper_required(value)


class DeliveryVendorResponse(BaseModel):
    id: int
    code: str
    name: str

    model_config = {"from_attributes": True}


class DeliveryResponse(BaseModel):
    id: int
    client_id: int
    client_code: str
    client_name: str
    vendor_id: int
    vendor_name: str
    city: str
    truck_name: str
    loaded_by: str
    delivery_date: date
    delivered_at: datetime | None = None
    deadline_changed_at: datetime | None = None
    deadline_change_reason: str | None = None
    created_at: datetime

