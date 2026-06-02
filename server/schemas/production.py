from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from ..models.operator import OperatorRole
from ..models.production_machine import MachineOperationalStatus


class ProductionMachineStatusUpdate(BaseModel):
    status: MachineOperationalStatus


class ProductionItemResponse(BaseModel):
    id: int
    source_requisition_id: Optional[int] = None
    production_split_id: Optional[int] = None
    split_sequence: Optional[int] = None
    is_partial_split: bool = False
    ped_number: str
    client_name: Optional[str] = None
    vendor_name: Optional[str] = None
    obra: Optional[str] = None
    weight: Optional[float] = None
    total_weight: Optional[float] = None
    status: str
    emission_date: datetime
    created_at: datetime
    delivery_date: Optional[date] = None
    destination: Optional[str] = None
    machine_name: Optional[str] = None
    operator_names: list[str] = Field(default_factory=list)
    helper_names: list[str] = Field(default_factory=list)
    waiting_since: Optional[datetime] = None
    production_started_at: Optional[datetime] = None


class ProductionSplitCreateRequest(BaseModel):
    weight: float
    destination: str
    machine_name: str
    operators: list[str] = Field(default_factory=list)
    helpers: list[str] = Field(default_factory=list)


class ProductionSplitStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class ProductionTeamMemberResponse(BaseModel):
    id: int
    name: str
    role: OperatorRole


class ProductionMachineCardResponse(BaseModel):
    id: int
    destination: str
    name: str
    sort_order: int
    status: MachineOperationalStatus
    operators: list[str] = Field(default_factory=list)
    team_members: list[ProductionTeamMemberResponse] = Field(default_factory=list)
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
