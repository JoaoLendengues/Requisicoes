from pydantic import BaseModel, field_validator
from datetime import datetime, date
from typing import Optional, List
from ..models.requisition import RequisitionStatus
from ..services.text_normalizer import normalize_upper_optional, normalize_upper_required


def _validate_ped_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    ped_number = str(value).strip()
    if not ped_number:
        raise ValueError("Número de PED é obrigatório")
    if not ped_number.isdigit():
        raise ValueError("Número de PED deve conter apenas dígitos")
    if int(ped_number) == 0:
        raise ValueError("Número de PED deve ser maior que zero")
    return ped_number


class RequisitionItemCreate(BaseModel):
    position: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    comp: Optional[str] = None
    desenv: Optional[str] = None
    chapa: Optional[str] = None
    tipo: Optional[str] = None
    weight: Optional[float] = None
    draw_ref: Optional[str] = None

    @field_validator("position", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator(
        "product_code",
        "product_name",
        "comp",
        "desenv",
        "chapa",
        "tipo",
        "draw_ref",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


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
    obs: Optional[str] = None
    items: List[RequisitionItemCreate] = []

    @field_validator("ped_number")
    @classmethod
    def validate_ped_number(cls, value: str) -> str:
        return _validate_ped_number(value) or ""

    @field_validator("os_number", "obra", "delivery_address", "obs", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


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
    obs: Optional[str] = None
    items: Optional[List[RequisitionItemCreate]] = None

    @field_validator("ped_number")
    @classmethod
    def validate_ped_number(cls, value: Optional[str]) -> Optional[str]:
        return _validate_ped_number(value)

    @field_validator("os_number", "obra", "delivery_address", "obs", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class StatusUpdate(BaseModel):
    status: RequisitionStatus
    note: Optional[str] = None


class DeliveryDateUpdate(BaseModel):
    delivery_date: date
    reason: str

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if len(value.strip()) < 5:
            raise ValueError("Informe um motivo com pelo menos 5 caracteres")
        return value


class CanvasUpdate(BaseModel):
    json_data: str


class CanvasDataResponse(BaseModel):
    json_data: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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
    vendor_name: Optional[str] = None
    vendor_code: Optional[str] = None
    client_id: int
    client_code: Optional[str] = None
    client_name: Optional[str] = None
    obra: Optional[str]
    nf_attachment: Optional[str]
    retirada: bool
    entrega: bool
    delivery_address: Optional[str]
    phone: Optional[str]
    weight: float
    obs: Optional[str] = None
    status: RequisitionStatus
    production_destination: Optional[str] = None
    production_destination_display: Optional[str] = None
    production_machine: Optional[str] = None
    production_machine_display: Optional[str] = None
    production_status: Optional[str] = None
    production_operator_names: List[str] = []
    production_operator_display: Optional[str] = None
    production_sent_at: Optional[datetime] = None
    production_finished_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    invoiced: bool = False
    finalized_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[RequisitionItemResponse] = []
    status_history: List[StatusHistoryResponse] = []
    canvas: Optional[CanvasDataResponse] = None

    model_config = {"from_attributes": True}
