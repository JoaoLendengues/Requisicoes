from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrderCenterStatsResponse(BaseModel):
    pedidos_aguardando_recebimento: int
    pedidos_em_producao: int
    pedidos_aguardando_faturamento: int
    pedidos_faturados: int
    pedidos_cancelados: int
    pedidos_atrasados: int
    tempo_medio_producao_segundos: Optional[int] = None


class OrderCenterItemResponse(BaseModel):
    id: int
    source_requisition_id: Optional[int] = None
    production_split_id: Optional[int] = None
    split_sequence: Optional[int] = None
    is_partial_split: bool = False
    ped_number: str
    client_name: Optional[str] = None
    vendor_name: Optional[str] = None
    weight: Optional[float] = None
    total_weight: Optional[float] = None
    status: str
    emission_date: Optional[datetime] = None
    delivery_date: Optional[date] = None
    destination: Optional[str] = None
    waiting_minutes: Optional[int] = None
    sent_to_production_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    invoiced_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    machine_name: Optional[str] = None
    operator_names: list[str] = Field(default_factory=list)
    helper_names: list[str] = Field(default_factory=list)
    delay_days: Optional[int] = None
    production_time_seconds: Optional[int] = None
    deadline_met: Optional[bool] = None


class OrderCenterResponse(BaseModel):
    generated_at: datetime
    stats: OrderCenterStatsResponse
    aguardando_recebimento: list[OrderCenterItemResponse]
    em_producao: list[OrderCenterItemResponse]
    aguardando_faturamento: list[OrderCenterItemResponse]
    faturados: list[OrderCenterItemResponse]
    cancelados: list[OrderCenterItemResponse]
    atrasados: list[OrderCenterItemResponse]
