from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
from ..models.requisition import RequisitionStatus


class RequisitionItemCreate(BaseModel):
    position: str
    quantity: Optional[float] = None
    comp: Optional[str] = None
    desenv: Optional[str] = None
    chapa: Optional[str] = None
    tipo: Optional[str] = None
    weight: Optional[float] = None
    draw_ref: Optional[str] = None


class RequisitionItemResponse(RequisitionItemCreate):
    id: int
    requisition_id: int

    model_config = {"from_attributes": True}


class RequisitionCreate(BaseModel):
    ped_number: str
    delivery_date: Optional[date] = None
    os_number: Optional[str] = None
    client_id: int
    obra: Optional[str] = None
    retirada: bool = False
    entrega: bool = False
    delivery_address: Optional[str] = None
    phone: Optional[str] = None
    weight: float = 0.0
    items: List[RequisitionItemCreate] = []


class RequisitionUpdate(BaseModel):
    ped_number: Optional[str] = None
    delivery_date: Optional[date] = None
    os_number: Optional[str] = None
    client_id: Optional[int] = None
    obra: Optional[str] = None
    retirada: Optional[bool] = None
    entrega: Optional[bool] = None
    delivery_address: Optional[str] = None
    phone: Optional[str] = None
    weight: Optional[float] = None
    items: Optional[List[RequisitionItemCreate]] = None


class StatusUpdate(BaseModel):
    status: RequisitionStatus
    note: Optional[str] = None


class CanvasUpdate(BaseModel):
    json_data: str


class StatusHistoryResponse(BaseModel):
    id: int
    old_status: Optional[str]
    new_status: str
    note: Optional[str]
    changed_at: datetime
    changed_by_id: int

    model_config = {"from_attributes": True}


class RequisitionResponse(BaseModel):
    id: int
    ped_number: str
    emission_date: datetime
    delivery_date: Optional[date]
    os_number: Optional[str]
    vendor_id: int
    client_id: int
    obra: Optional[str]
    nf_attachment: Optional[str]
    retirada: bool
    entrega: bool
    delivery_address: Optional[str]
    phone: Optional[str]
    weight: float
    status: RequisitionStatus
    finalized_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[RequisitionItemResponse] = []
    status_history: List[StatusHistoryResponse] = []

    model_config = {"from_attributes": True}
