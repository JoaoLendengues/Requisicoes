from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, field_validator


class AvulseDeliveryCreate(BaseModel):
    client_id: int
    vendor_id: int
    delivery_date: date
    description: Optional[str] = None
    weight: Optional[float] = None

    @field_validator("weight", mode="before")
    @classmethod
    def coerce_weight(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class AvulseCancellation(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("Informe um motivo com pelo menos 3 caracteres")
        return v.strip()


class AvulseDeliveryResponse(BaseModel):
    id: int
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    delivery_date: date
    description: Optional[str] = None
    weight: Optional[float] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
