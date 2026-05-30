from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from ..models.requisition import RequisitionStatus


class DashboardStatsResponse(BaseModel):
    pedidos_em_producao: int
    pedidos_em_atraso: int
    pedidos_finalizados_hoje: int
    producao_pinheiro_industria: int
    producao_ar: int
    requisicoes_feitas_no_dia: int
    pedidos_sem_confirmacao_1h: int
    tempo_medio_finalizacao_segundos: Optional[int] = None


class DashboardVendorItem(BaseModel):
    vendor_name: str
    requisition_count: int


class DashboardReceiptAlertItem(BaseModel):
    id: int
    ped_number: str
    client_name: Optional[str] = None
    destination: str
    sent_at: datetime
    waiting_minutes: int


class DashboardRecentRequisitionItem(BaseModel):
    id: int
    ped_number: str
    client_name: Optional[str] = None
    vendor_name: Optional[str] = None
    status: RequisitionStatus
    emission_date: datetime
    delivery_date: Optional[date] = None
    destination: Optional[str] = None


class DashboardMachineUsageItem(BaseModel):
    machine_name: str
    total_operations: int
    in_production_count: int
    average_seconds: Optional[int] = None
    machine_status: str


class ManagementDashboardResponse(BaseModel):
    generated_at: datetime
    stats: DashboardStatsResponse
    top_vendors: list[DashboardVendorItem]
    receipt_alerts: list[DashboardReceiptAlertItem]
    recent_requisitions: list[DashboardRecentRequisitionItem]
    top_machines_ar: list[DashboardMachineUsageItem]
    top_machines_industria: list[DashboardMachineUsageItem]


class TechnicalPanelStatsResponse(BaseModel):
    system_online: bool
    connected_users: int
    requisitions_today: int
    average_response_ms: Optional[int] = None
    last_backup_at: Optional[datetime] = None
    database_connected: bool
    available_space_bytes: Optional[int] = None
    error_count_today: int


class TechnicalPanelLoggedUserResponse(BaseModel):
    id: int
    name: str
    last_login_at: Optional[datetime] = None


class TechnicalPanelResponse(BaseModel):
    generated_at: datetime
    stats: TechnicalPanelStatsResponse
    logged_users: list[TechnicalPanelLoggedUserResponse]
