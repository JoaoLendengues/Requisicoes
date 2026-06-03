from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeliveryCenterStatsResponse(BaseModel):
    deliveries_today: int
    delayed_deliveries: int
    changed_delivery_deadlines: int
    completed_deliveries: int


class DeliveryCenterItemResponse(BaseModel):
    id: int
    ped_number: str
    client_name: Optional[str] = None
    vendor_name: Optional[str] = None
    weight: Optional[float] = None
    destination: Optional[str] = None
    delivery_date: Optional[date] = None
    status: str
    delivered_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    deadline_changed_at: Optional[datetime] = None
    deadline_change_reason: Optional[str] = None


class DeliveryCenterResponse(BaseModel):
    generated_at: datetime
    stats: DeliveryCenterStatsResponse
    rows: list[DeliveryCenterItemResponse] = Field(default_factory=list)
