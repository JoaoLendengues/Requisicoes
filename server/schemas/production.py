from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..models.production_machine import MachineOperationalStatus


class ProductionMachineStatusUpdate(BaseModel):
    status: MachineOperationalStatus


class ProductionItemResponse(BaseModel):
    id: int
    ped_number: str
    client_name: Optional[str] = None
    vendor_name: Optional[str] = None
    obra: Optional[str] = None
    weight: Optional[float] = None
    status: str
    emission_date: datetime
    created_at: datetime
    delivery_date: Optional[date] = None
    destination: Optional[str] = None
    machine_name: Optional[str] = None
    waiting_since: Optional[datetime] = None
    production_started_at: Optional[datetime] = None
    operator_names: list[str] = Field(default_factory=list)


class ProductionMachineCardResponse(BaseModel):
    id: int
    destination: str
    name: str
    sort_order: int
    status: MachineOperationalStatus
    operators: list[str] = Field(default_factory=list)
    quantity_in_production: int
    finalized_count: int
    average_seconds: Optional[int] = None
    rows: list[ProductionItemResponse] = Field(default_factory=list)


class ProductionSummaryStatsResponse(BaseModel):
    aguardando_recebimento: int
    aguardando_na_fila: int
    em_producao: int


class ProductionDestinationSummaryResponse(BaseModel):
    generated_at: datetime
    destination: str
    stats: ProductionSummaryStatsResponse
    waiting_receipt: list[ProductionItemResponse] = Field(default_factory=list)
    waiting_queue: list[ProductionItemResponse] = Field(default_factory=list)
    machines: list[ProductionMachineCardResponse] = Field(default_factory=list)


class ProductionMachineStatusResponse(BaseModel):
    id: int
    destination: str
    name: str
    status: MachineOperationalStatus
    updated_at: datetime
