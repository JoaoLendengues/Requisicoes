from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import shutil
import unicodedata
from ..config import settings
from ..database import get_db
from ..models.client import Client
from ..models.operator import OperatorRole
from ..models.production_machine import ProductionMachine
from ..models.requisition import (
    Requisition,
    RequisitionItem,
    CanvasData,
    RequisitionProductionSplit,
    StatusHistory,
    RequisitionStatus,
)
from ..models.user import User, Role
from ..schemas.dashboard import (
    DashboardIarSummaryItem,
    DashboardCountKgComparisonItem,
    DashboardInsightsResponse,
    DashboardKgComparisonItem,
    DashboardMachineUsageItem,
    DashboardProductionPersonItem,
    DashboardReceiptAlertItem,
    DashboardRecentRequisitionItem,
    DashboardStatsResponse,
    DashboardVendorItem,
    ManagementDashboardResponse,
    TechnicalPanelLoggedUserResponse,
    TechnicalPanelResponse,
    TechnicalPanelStatsResponse,
)
from ..schemas.delivery_center import (
    DeliveryCenterItemResponse,
    DeliveryCenterResponse,
    DeliveryCenterStatsResponse,
)
from ..schemas.order_center import (
    OrderCenterItemResponse,
    OrderCenterResponse,
    OrderCenterStatsResponse,
)
from ..schemas.production import (
    ProductionDestinationSummaryResponse,
    ProductionItemResponse,
    ProductionMachineCardResponse,
    ProductionMachineStatusResponse,
    ProductionMachineStatusUpdate,
    ProductionSplitCreateRequest,
    ProductionSplitStatusUpdate,
    ProductionSummaryStatsResponse,
)
from ..schemas.requisition import (
    RequisitionCreate, RequisitionUpdate, RequisitionResponse, RequisitionListItem,
    StatusUpdate, CanvasUpdate, DeliveryDateUpdate, DeliveryCancellationUpdate,
)
from ..dependencies import (
    get_current_user,
    require_admin,
    require_creator,
    require_manager_or_admin,
    require_order_center_access,
)
from ..services.audit_service import diff_fields, log_action
from ..services.notification_service import (
    _notify_admins_gerentes,
    dispatch               as push_all,
    ensure_delivery_deadline_notifications,
    ensure_pending_invoice_notifications,
    notify_machine_status_change as build_machine_status_event,
    notify_production_team as build_production_sent,
    notify_vendor          as build_vendor_event,
)
from ..services.runtime_monitor import snapshot as runtime_snapshot
from ..services.sse_manager import connected_user_ids
from ..services.system_settings import get_min_delivery_business_days
from ..services.text_normalizer import normalize_canvas_json_text, normalize_upper_required

router = APIRouter(prefix="/requisitions", tags=["Requisições"])

_LOAD_OPTS = [
    selectinload(Requisition.items),
    selectinload(Requisition.status_history),
    selectinload(Requisition.production_splits).selectinload(RequisitionProductionSplit.status_history),
    selectinload(Requisition.canvas),
    selectinload(Requisition.client),
    selectinload(Requisition.vendor),
]

# Listagens não precisam de itens nem do canvas (desenho); status_history é
# necessário só para derivar os campos de produção. Carrega o mínimo.
_LIST_LOAD_OPTS = [
    selectinload(Requisition.status_history),
    selectinload(Requisition.production_splits).selectinload(RequisitionProductionSplit.status_history),
    selectinload(Requisition.client),
    selectinload(Requisition.vendor),
]

_LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo or timezone.utc

_PROD_NOTE_PREFIX = "PRODUCAO"
_PROD_SEND = "ENVIADA"
_PROD_RECEIVED = "RECEBIDA"
_PROD_QUEUED = "FILA"
_PROD_STARTED = "INICIADA"
_PROD_RETURNED_QUEUE = "DEVOLVIDA_FILA"
_PROD_FINISHED = "FINALIZADA"
_PROD_CANCELED = "CANCELADA"
_DESTINATION_AR = "A&R"
_DESTINATION_PINHEIRO = "Pinheiro Indústria"
_MACHINE_DASHBOARD_PERIODS = {"30d", "7d", "today", "last_month"}
_PERFORMANCE_DASHBOARD_PERIODS = {"today", "week", "month", "year", "custom"}
_SHIFT_START_HOUR = 8
_SHIFT_END_HOUR = 18


def _normalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode()
    return ascii_text.strip().casefold()


def _parse_local_emission_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(_LOCAL_TIMEZONE)


def _to_local_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        return _parse_local_emission_datetime(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_LOCAL_TIMEZONE)


def _did_finish_on_time(finished_at: object, delivery_date: date | None) -> bool | None:
    if delivery_date is None:
        return None

    finished_local = _to_local_datetime(finished_at)
    if finished_local is None:
        return None

    return finished_local.date() <= delivery_date


def _request_finished_at(req: Requisition) -> datetime | None:
    if req.status == RequisitionStatus.CANCELADA:
        return None
    return _history_production_finished_at(req)


def _request_finished_on_time(req: Requisition) -> bool:
    finished_at = _request_finished_at(req)
    result = _did_finish_on_time(finished_at, req.delivery_date)
    return bool(result)


def _build_iar_summary_item(
    *,
    received_count: int,
    finalized_count: int,
    on_time_count: int,
    canceled_count: int,
) -> DashboardIarSummaryItem:
    prazo_percent = 0.0
    produtividade_percent = 0.0
    cancelamentos_percent = 0.0

    if finalized_count > 0:
        prazo_percent = (on_time_count / finalized_count) * 100.0
    if received_count > 0:
        produtividade_percent = (finalized_count / received_count) * 100.0
        cancelamentos_percent = max(0.0, ((received_count - canceled_count) / received_count) * 100.0)

    iar_percent = (
        (prazo_percent * 0.50)
        + (produtividade_percent * 0.30)
        + (cancelamentos_percent * 0.20)
    )

    return DashboardIarSummaryItem(
        received_count=int(received_count),
        finalized_count=int(finalized_count),
        on_time_count=int(on_time_count),
        canceled_count=int(canceled_count),
        prazo_percent=round(prazo_percent, 2),
        produtividade_percent=round(produtividade_percent, 2),
        cancelamentos_percent=round(cancelamentos_percent, 2),
        iar_percent=round(iar_percent, 2),
    )


def _delivery_deadline_changed_at(req: Requisition) -> datetime | None:
    changed_at = getattr(req, "delivery_deadline_changed_at", None)
    if isinstance(changed_at, datetime):
        return changed_at

    if req.status == RequisitionStatus.PRAZO_ALTERADO:
        return _latest_status_changed_at(req, RequisitionStatus.PRAZO_ALTERADO)

    return None


def _normalize_machine_dashboard_period(value: str) -> str:
    key = str(value or "").strip().casefold() or "30d"
    if key not in _MACHINE_DASHBOARD_PERIODS:
        raise HTTPException(
            status_code=400,
            detail="Período do dashboard inválido. Use 30d, 7d, today ou last_month.",
        )
    return key


def _normalize_dashboard_period(value: str) -> str:
    return _normalize_machine_dashboard_period(value)


def _normalize_performance_dashboard_period(value: str) -> str:
    key = str(value or "").strip().casefold() or "month"
    if key not in _PERFORMANCE_DASHBOARD_PERIODS:
        raise HTTPException(
            status_code=400,
            detail="PerÃ­odo de performance invÃ¡lido. Use today, week, month, year ou custom.",
        )
    return key


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _machine_dashboard_period_bounds(period_key: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    local_now = _to_local_datetime(now or datetime.now(_LOCAL_TIMEZONE)) or datetime.now(_LOCAL_TIMEZONE)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period_key == "today":
        return today_start, local_now
    if period_key == "7d":
        return today_start - timedelta(days=6), local_now
    if period_key == "last_month":
        current_month_start = _month_start(local_now)
        previous_month_last_day = current_month_start - timedelta(days=1)
        previous_month_start = previous_month_last_day.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return previous_month_start, current_month_start
    return today_start - timedelta(days=29), local_now


def _dashboard_period_bounds(period_key: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    return _machine_dashboard_period_bounds(period_key, now)


def _performance_period_bounds(
    period_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    local_now = _to_local_datetime(now or datetime.now(_LOCAL_TIMEZONE)) or datetime.now(_LOCAL_TIMEZONE)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period_key == "today":
        return today_start, local_now
    if period_key == "week":
        week_start = today_start - timedelta(days=today_start.weekday())
        return week_start, local_now
    if period_key == "month":
        return _month_start(local_now), local_now
    if period_key == "year":
        return local_now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), local_now

    if start_date is None or end_date is None:
        raise HTTPException(
            status_code=400,
            detail="Informe a data inicial e final para o perÃ­odo personalizado.",
        )
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="A data final do perÃ­odo personalizado nÃ£o pode ser menor que a inicial.",
        )

    range_start = datetime.combine(start_date, time.min, _LOCAL_TIMEZONE)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, _LOCAL_TIMEZONE)
    return range_start, range_end


def _datetime_in_dashboard_period(
    value: object,
    period_key: str,
    now: datetime | None = None,
) -> bool:
    current = _to_local_datetime(value)
    if current is None:
        return False
    period_start, period_end = _dashboard_period_bounds(period_key, now)
    return period_start <= current < period_end


def _datetime_in_performance_period(
    value: object,
    period_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    now: datetime | None = None,
) -> bool:
    current = _to_local_datetime(value)
    if current is None:
        return False
    period_start, period_end = _performance_period_bounds(
        period_key,
        start_date,
        end_date,
        now,
    )
    return period_start <= current < period_end


def _iter_shift_overlap_segments(start_at: datetime, end_at: datetime) -> list[tuple[datetime, datetime]]:
    start_local = _to_local_datetime(start_at)
    end_local = _to_local_datetime(end_at)
    if start_local is None or end_local is None or end_local <= start_local:
        return []

    segments: list[tuple[datetime, datetime]] = []
    day = start_local.date()
    last_day = end_local.date()
    while day <= last_day:
        shift_start = datetime.combine(day, time(_SHIFT_START_HOUR, 0), _LOCAL_TIMEZONE)
        shift_end = datetime.combine(day, time(_SHIFT_END_HOUR, 0), _LOCAL_TIMEZONE)
        overlap_start = max(start_local, shift_start)
        overlap_end = min(end_local, shift_end)
        if overlap_end > overlap_start:
            segments.append((overlap_start, overlap_end))
        day += timedelta(days=1)
    return segments


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged: list[tuple[datetime, datetime]] = [ordered[0]]
    for start_at, end_at in ordered[1:]:
        last_start, last_end = merged[-1]
        if start_at <= last_end:
            merged[-1] = (last_start, max(last_end, end_at))
            continue
        merged.append((start_at, end_at))
    return merged


def _intervals_total_seconds(intervals: list[tuple[datetime, datetime]]) -> int:
    total = 0
    for start_at, end_at in intervals:
        if end_at > start_at:
            total += int((end_at - start_at).total_seconds())
    return total


def _matches_emission_period(req: Requisition, start: date | None, end: date | None) -> bool:
    local_dt = _parse_local_emission_datetime(req.emission_date)
    if local_dt is None:
        return not start and not end

    local_day = local_dt.date()
    if start and local_day < start:
        return False
    if end and local_day > end:
        return False
    return True


def _normalize_machine_name(value: object) -> str:
    return normalize_upper_required(value)


def _canonical_destination(value: object) -> str:
    key = _normalize_text(value)
    if key == _normalize_text(_DESTINATION_AR):
        return _DESTINATION_AR
    if key == _normalize_text(_DESTINATION_PINHEIRO):
        return _DESTINATION_PINHEIRO
    return str(value or "").strip()


def _normalize_dashboard_destination(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    canonical = _canonical_destination(text)
    if canonical not in {_DESTINATION_AR, _DESTINATION_PINHEIRO}:
        raise HTTPException(
            status_code=400,
            detail="Produção do dashboard inválida. Use A&R ou Pinheiro Indústria.",
        )
    return canonical


def _role_key(role: Role | str) -> str:
    return getattr(role, "value", role)


def _is_industry_role(role: Role | str) -> bool:
    return _role_key(role) in (Role.INDUSTRIA.value, Role.ENTREGA.value)


def _destination_for_role(role: Role | str) -> str | None:
    key = _role_key(role)
    if key == Role.PRODUCAO.value:
        return _DESTINATION_AR
    if _is_industry_role(key):
        return _DESTINATION_PINHEIRO
    return None


def _user_can_access_destination(current_user: User, destination: str) -> bool:
    role = _role_key(current_user.role)
    if role in (Role.ADMIN.value, Role.GERENTE.value):
        return True
    return _destination_for_role(role) == _canonical_destination(destination)


def _ensure_destination_access(current_user: User, destination: str):
    if not _user_can_access_destination(current_user, destination):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para acessar este destino de produção",
        )


def _get_or_404(db: Session, req_id: int) -> Requisition:
    req = db.query(Requisition).options(*_LOAD_OPTS).filter(Requisition.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requisição não encontrada")
    return req


def _get_split_or_404(db: Session, split_id: int) -> RequisitionProductionSplit:
    split = (
        db.query(RequisitionProductionSplit)
        .options(
            selectinload(RequisitionProductionSplit.status_history),
            selectinload(RequisitionProductionSplit.requisition)
            .selectinload(Requisition.production_splits)
            .selectinload(RequisitionProductionSplit.status_history),
            selectinload(RequisitionProductionSplit.requisition).selectinload(Requisition.status_history),
            selectinload(RequisitionProductionSplit.requisition).selectinload(Requisition.client),
            selectinload(RequisitionProductionSplit.requisition).selectinload(Requisition.vendor),
        )
        .filter(RequisitionProductionSplit.id == split_id)
        .first()
    )
    if not split:
        raise HTTPException(status_code=404, detail="Parcela de producao nao encontrada")
    return split


def _find_duplicate_ped_number(
    db: Session,
    ped_number: str,
    exclude_req_id: int | None = None,
) -> Requisition | None:
    q = db.query(Requisition).filter(Requisition.ped_number == ped_number)
    if exclude_req_id is not None:
        q = q.filter(Requisition.id != exclude_req_id)
    return q.order_by(Requisition.created_at.desc(), Requisition.id.desc()).first()


def _ensure_unique_ped_number(
    db: Session,
    ped_number: str,
    exclude_req_id: int | None = None,
):
    duplicate = _find_duplicate_ped_number(db, ped_number, exclude_req_id)
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O número de PED {ped_number} já está salvo em outra requisição.",
        )


def _commit_or_ped_conflict(db: Session, ped_number: str) -> None:
    """Commit que converte a violação de unicidade do PED (constraint do banco)
    em um 409 limpo. Rede de segurança contra condição de corrida que escapa da
    checagem prévia em `_ensure_unique_ped_number`."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O número de PED {ped_number} já está salvo em outra requisição.",
        )


def _as_naive_utc(dt: datetime) -> datetime:
    """Normaliza para datetime naive em UTC (precisão total).

    Mantém microssegundos: o round-trip via ISO preserva o valor exato, então
    qualquer alteração do registro é detectada (truncar mascararia mudanças
    ocorridas dentro do mesmo segundo)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _ensure_not_stale(req: Requisition, expected_updated_at: datetime | None) -> None:
    """Trava otimista de concorrência (P1.6): se a requisição foi alterada por
    outra pessoa desde que o cliente a carregou, rejeita com 409 em vez de
    sobrescrever silenciosamente. Comparação na granularidade de segundos."""
    if expected_updated_at is None or req.updated_at is None:
        return
    if _as_naive_utc(req.updated_at) != _as_naive_utc(expected_updated_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Esta requisição foi alterada por outra pessoa enquanto você "
                "editava. Recarregue a requisição e refaça suas alterações."
            ),
        )


def _sum_item_weights(items: Optional[list]) -> float:
    return sum((item.weight or 0.0) for item in (items or []))


def _normalize_operator_name(value: object) -> str:
    return normalize_upper_required(value).replace("|", " ").replace(";", " ").strip()


def _clean_operator_names(values: object) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in values or []:
        normalized = _normalize_operator_name(raw_name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


def _parse_operator_names(raw: object) -> list[str]:
    if raw is None:
        return []
    return _clean_operator_names(str(raw).split(";"))


def _compose_production_note(
    action: str,
    target: str,
    *,
    machine: str = "",
    reason: str = "",
    operators: list[str] | None = None,
    helpers: list[str] | None = None,
    transfer: bool = False,
) -> str:
    parts = [_PROD_NOTE_PREFIX, action, _canonical_destination(target)]
    machine_name = _normalize_machine_name(machine) if machine else ""
    if machine_name:
        parts.append(f"machine={machine_name}")
    if operators:
        parts.append(f"operators={';'.join(_clean_operator_names(operators))}")
    if helpers:
        parts.append(f"helpers={';'.join(_clean_operator_names(helpers))}")
    if reason.strip():
        parts.append(f"reason={reason.strip()}")
    if transfer:
        parts.append("transfer=1")
    return "|".join(parts)


def _parse_production_note(note: Optional[str]) -> dict | None:
    if not note:
        return None

    parts = [part.strip() for part in str(note).split("|")]
    if len(parts) < 3 or parts[0] != _PROD_NOTE_PREFIX:
        return None

    data = {
        "action": parts[1].strip(),
        "target": _canonical_destination(parts[2]),
        "machine": "",
        "reason": "",
        "operators": [],
        "helpers": [],
        "transfer": False,
    }

    for raw_segment in parts[3:]:
        segment = raw_segment.strip()
        if not segment:
            continue

        if "=" in segment:
            key, value = segment.split("=", 1)
            normalized_key = _normalize_text(key)
            normalized_value = value.strip()
            if normalized_key == "machine":
                data["machine"] = normalized_value
                continue
            if normalized_key == "reason":
                data["reason"] = normalized_value
                continue
            if normalized_key == "operators":
                data["operators"] = _parse_operator_names(normalized_value)
                continue
            if normalized_key == "helpers":
                data["helpers"] = _parse_operator_names(normalized_value)
                continue
            if normalized_key == "transfer":
                data["transfer"] = normalized_value.strip().casefold() in {
                    "1",
                    "true",
                    "sim",
                    "yes",
                }
                continue

        if not data["machine"] and data["action"] in (
            _PROD_STARTED,
            _PROD_FINISHED,
            _PROD_RETURNED_QUEUE,
        ):
            data["machine"] = segment
        elif not data["reason"]:
            data["reason"] = segment
    return data


def _is_locked_for_edit(req: Requisition) -> bool:
    return req.finalized_at is not None


def _ensure_editable(req: Requisition):
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Requisição cancelada não pode ser editada",
        )
    if _is_locked_for_edit(req):
        raise HTTPException(
            status_code=400,
            detail="Requisição em produção recebida ou finalizada não pode ser editada",
        )


def _add_business_days(start: date, n: int) -> date:
    """Soma n dias úteis (segunda a sexta) a partir de `start`.
    Sábado e domingo não contam. Feriados não são considerados."""
    if n <= 0:
        return start
    current = start
    added = 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:  # 0=segunda ... 4=sexta
            added += 1
    return current


def _ensure_delivery_within_min(delivery_date: date | None, current_user: User) -> None:
    """Bloqueia datas de entrega abaixo do prazo mínimo em dias úteis.
    Admin e gerente podem salvar abaixo do mínimo."""
    if delivery_date is None:
        return
    role = _role_key(current_user.role)
    if role in (Role.ADMIN.value, Role.GERENTE.value):
        return
    min_days = get_min_delivery_business_days()
    if min_days <= 0:
        return
    earliest = _add_business_days(date.today(), min_days)
    if delivery_date < earliest:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Prazo de entrega abaixo do mínimo: são necessários pelo menos "
                f"{min_days} dia(s) útil(eis). Data mais próxima permitida: "
                f"{earliest.strftime('%d/%m/%Y')}."
            ),
        )


def _apply_production_transition(req: Requisition, status_update: StatusUpdate):
    prod_event = _parse_production_note(status_update.note)
    if not prod_event:
        return

    action = prod_event["action"]
    target = prod_event["target"] or req.production_destination or ""
    machine = _normalize_machine_name(prod_event.get("machine"))
    reason = prod_event["reason"]
    if target:
        req.production_destination = target

    if action == _PROD_SEND:
        req.status = RequisitionStatus.AGUARDANDO_RECEBIMENTO
        req.finalized_at = None
        req.production_machine = None
        return

    if action == _PROD_RECEIVED:
        if req.status not in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
            RequisitionStatus.AGUARDANDO_NA_FILA,
            RequisitionStatus.EM_PRODUCAO,
        ):
            raise HTTPException(
                status_code=400,
                detail="Somente requisições aguardando recebimento podem confirmar recebimento",
            )
        if req.finalized_at is not None:
            raise HTTPException(
                status_code=400,
                detail="O recebimento desta requisição já foi confirmado",
            )
        req.status = RequisitionStatus.EM_PRODUCAO
        req.finalized_at = req.finalized_at or datetime.utcnow()
        req.production_machine = machine or req.production_machine
        return

    if action == _PROD_QUEUED:
        if req.status not in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
            RequisitionStatus.AGUARDANDO_NA_FILA,
        ):
            raise HTTPException(
                status_code=400,
                detail="Somente requisições aguardando recebimento podem entrar na fila",
            )
        req.status = RequisitionStatus.AGUARDANDO_NA_FILA
        req.finalized_at = req.finalized_at or datetime.utcnow()
        req.production_machine = None
        return

    if action == _PROD_STARTED:
        if req.status not in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
            RequisitionStatus.AGUARDANDO_NA_FILA,
            RequisitionStatus.EM_PRODUCAO,
        ):
            raise HTTPException(
                status_code=400,
                detail="Somente requisições aguardando recebimento ou em fila podem entrar em produção",
            )
        if not machine:
            raise HTTPException(
                status_code=400,
                detail="Informe a máquina de destino para iniciar a produção",
            )
        if req.status == RequisitionStatus.EM_PRODUCAO and req.production_machine:
            raise HTTPException(
                status_code=400,
                detail="Esta requisição já está vinculada a uma máquina",
            )
        req.status = RequisitionStatus.EM_PRODUCAO
        req.finalized_at = req.finalized_at or datetime.utcnow()
        req.production_machine = machine
        return

    if action == _PROD_RETURNED_QUEUE:
        if req.status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(
                status_code=400,
                detail="Somente requisições em produção podem voltar para a fila",
            )
        req.status = RequisitionStatus.AGUARDANDO_NA_FILA
        req.production_machine = None
        return

    if action == _PROD_FINISHED:
        if req.status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(
                status_code=400,
                detail="Somente requisições em produção podem ser finalizadas",
            )
        if req.finalized_at is None:
            raise HTTPException(
                status_code=400,
                detail="Confirme o recebimento antes de finalizar a produção",
            )
        req.status = RequisitionStatus.FATURADO
        req.production_machine = None
        return

    if action == _PROD_CANCELED:
        if len(reason.strip()) < 5:
            raise HTTPException(
                status_code=400,
                detail="Informe um motivo de cancelamento válido",
            )
        req.status = RequisitionStatus.CANCELADA
        req.cancel_reason = reason.strip()
        req.finalized_at = None
        req.production_machine = None
        return


def _apply_manual_status_transition(
    req: Requisition,
    new_status: RequisitionStatus,
):
    if req.status == RequisitionStatus.CANCELADA:
        if new_status == RequisitionStatus.FATURADO:
            raise HTTPException(
                status_code=400,
                detail="Requisições canceladas não podem ser faturadas diretamente",
            )
        req.status = new_status
        req.finalized_at = None
        req.production_machine = None
        return

    if new_status == RequisitionStatus.FATURADO:
        if req.status != RequisitionStatus.AGUARDANDO_FATURAMENTO:
            raise HTTPException(
                status_code=400,
                detail="Somente pedidos aguardando faturamento podem ser marcados como faturados",
            )
        req.status = RequisitionStatus.FATURADO
        return

    if req.status == RequisitionStatus.AGUARDANDO_FATURAMENTO:
        raise HTTPException(
            status_code=400,
            detail="Pedidos aguardando faturamento só podem ser marcados como faturados",
        )

    if req.status == RequisitionStatus.FATURADO:
        raise HTTPException(
            status_code=400,
            detail="Pedidos faturados não podem retornar para outro status operacional",
        )

    req.status = new_status


def _sorted_split_status_history(split: RequisitionProductionSplit) -> list[StatusHistory]:
    history = list(split.status_history or [])
    return sorted(history, key=lambda entry: (entry.changed_at or datetime.min, entry.id or 0))


def _split_production_events(split: RequisitionProductionSplit) -> list[dict]:
    events: list[dict] = []
    for entry in _sorted_split_status_history(split):
        parsed = _parse_production_note(entry.note)
        if not parsed:
            continue
        events.append(
            {
                "action": parsed["action"],
                "target": _canonical_destination(parsed.get("target")),
                "machine": _normalize_machine_name(parsed.get("machine", "")),
                "reason": parsed["reason"],
                "operators": list(parsed.get("operators") or []),
                "helpers": list(parsed.get("helpers") or []),
                "changed_at": entry.changed_at,
            }
        )
    return events


def _split_latest_production_event(split: RequisitionProductionSplit, *actions: str) -> dict | None:
    for event in reversed(_split_production_events(split)):
        if event["action"] in actions:
            return event
    return None


def _split_destination(split: RequisitionProductionSplit) -> str:
    if split.destination:
        return _canonical_destination(split.destination)
    for event in reversed(_split_production_events(split)):
        target = _canonical_destination(event.get("target"))
        if target:
            return target
    return ""


def _split_current_machine(split: RequisitionProductionSplit) -> str:
    if split.production_machine:
        return _normalize_machine_name(split.production_machine)
    if split.status != RequisitionStatus.EM_PRODUCAO:
        return ""
    for event in reversed(_split_production_events(split)):
        machine = _normalize_machine_name(event.get("machine"))
        if machine:
            return machine
    return ""


def _split_all_finished_cycles(split: RequisitionProductionSplit) -> list[dict]:
    cycles: list[dict] = []
    started_at: datetime | None = None
    started_target: str | None = None
    started_machine: str | None = None
    started_operators: list[str] = []
    started_helpers: list[str] = []

    for event in _split_production_events(split):
        changed_at = event["changed_at"]
        if changed_at is None:
            continue

        action = event["action"]
        machine = str(event.get("machine") or "").strip() or None
        target = event.get("target") or None

        if action in (_PROD_RECEIVED, _PROD_STARTED):
            started_at = changed_at
            started_target = target
            started_machine = machine
            started_operators = list(event.get("operators") or [])
            started_helpers = list(event.get("helpers") or [])
            continue

        if action == _PROD_FINISHED:
            if started_at is not None:
                cycles.append(
                    {
                        "received_at": started_at,
                        "finished_at": changed_at,
                        "target": started_target,
                        "machine": started_machine,
                        "operators": list(started_operators),
                        "helpers": list(started_helpers),
                        "production_time_seconds": max(
                            0,
                            int((changed_at - started_at).total_seconds()),
                        ),
                    }
                )
            started_at = None
            started_target = None
            started_machine = None
            started_operators = []
            started_helpers = []
            continue

        if action in (
            _PROD_SEND,
            _PROD_QUEUED,
            _PROD_RETURNED_QUEUE,
            _PROD_CANCELED,
        ):
            started_at = None
            started_target = None
            started_machine = None
            started_operators = []
            started_helpers = []

    return cycles


def _sorted_requisition_splits(req: Requisition) -> list[RequisitionProductionSplit]:
    return sorted(
        list(req.production_splits or []),
        key=lambda split: (split.sequence or 0, split.id or 0),
    )


def _has_production_splits(req: Requisition) -> bool:
    return bool(req.production_splits)


def _total_allocated_split_weight(req: Requisition) -> float:
    return sum(max(0.0, float(split.weight or 0.0)) for split in _sorted_requisition_splits(req))


def _remaining_requisition_weight(req: Requisition) -> float:
    remaining = float(req.weight or 0.0) - _total_allocated_split_weight(req)
    return round(max(0.0, remaining), 3)


def _split_display_ped_number(req: Requisition, split: RequisitionProductionSplit) -> str:
    return f"{req.ped_number}/P{int(split.sequence or 0):02d}"


def _coerce_requisition_status(value: object) -> RequisitionStatus:
    try:
        return RequisitionStatus(str(value or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Status operacional invalido") from exc


def _sync_requisition_after_splits(
    req: Requisition,
    db: Session,
    current_user: User,
    *,
    note: str,
) -> RequisitionStatus:
    if req.status == RequisitionStatus.CANCELADA or not _has_production_splits(req):
        return req.status

    splits = _sorted_requisition_splits(req)
    remaining_weight = _remaining_requisition_weight(req)
    statuses = [split.status for split in splits]
    latest_destination = next(
        (
            destination
            for destination in reversed([_split_destination(split) for split in splits])
            if destination
        ),
        "",
    )
    if latest_destination:
        req.production_destination = latest_destination

    if remaining_weight > 0:
        desired_status = RequisitionStatus.AGUARDANDO_NA_FILA
    elif any(status_value == RequisitionStatus.EM_PRODUCAO for status_value in statuses):
        desired_status = RequisitionStatus.EM_PRODUCAO
    elif any(status_value in (RequisitionStatus.AGUARDANDO_RECEBIMENTO, RequisitionStatus.AGUARDANDO_NA_FILA) for status_value in statuses):
        desired_status = RequisitionStatus.AGUARDANDO_NA_FILA
    elif statuses and all(status_value == RequisitionStatus.FATURADO for status_value in statuses):
        desired_status = RequisitionStatus.FATURADO
    else:
        desired_status = req.status

    old_status = req.status
    req.status = desired_status
    req.production_machine = None
    if desired_status in (
        RequisitionStatus.AGUARDANDO_NA_FILA,
        RequisitionStatus.EM_PRODUCAO,
        RequisitionStatus.FATURADO,
    ):
        req.finalized_at = req.finalized_at or datetime.utcnow()

    if desired_status != old_status:
        db.add(
            StatusHistory(
                requisition_id=req.id,
                old_status=old_status,
                new_status=desired_status,
                changed_by_id=current_user.id,
                note=note,
            )
        )
    return desired_status


def _sorted_status_history(req: Requisition) -> list[StatusHistory]:
    history = [
        entry
        for entry in (req.status_history or [])
        if getattr(entry, "production_split_id", None) in (None, 0)
    ]
    return sorted(history, key=lambda entry: (entry.changed_at or datetime.min, entry.id or 0))


def _production_events(req: Requisition) -> list[dict]:
    events: list[dict] = []
    for entry in _sorted_status_history(req):
        parsed = _parse_production_note(entry.note)
        if not parsed:
            continue
        events.append(
            {
                "action": parsed["action"],
                "target": parsed["target"],
                "machine": _normalize_machine_name(parsed.get("machine", "")),
                "reason": parsed["reason"],
                "operators": list(parsed.get("operators") or []),
                "helpers": list(parsed.get("helpers") or []),
                "changed_at": entry.changed_at,
            }
        )
    return events


def _cancel_reason_for(req: Requisition) -> str | None:
    """Retorna o motivo de cancelamento da requisição.
    Usa a coluna `cancel_reason` (preenchida nos cancelamentos novos) e,
    como fallback para registros antigos, extrai o motivo do último evento
    de produção CANCELADA registrado no histórico de status."""
    direct = (getattr(req, "cancel_reason", None) or "").strip()
    if direct:
        return direct
    for event in reversed(_production_events(req)):
        if event.get("action") == _PROD_CANCELED:
            reason = (event.get("reason") or "").strip()
            if reason:
                return reason
            break
    return None


def _current_production_destination(req: Requisition) -> str:
    if req.production_destination:
        return _canonical_destination(req.production_destination)
    for event in reversed(_production_events(req)):
        target = _canonical_destination(event.get("target"))
        if target:
            return target
    return ""


def _current_production_machine(req: Requisition) -> str:
    if req.production_machine:
        return _normalize_machine_name(req.production_machine)
    if req.status != RequisitionStatus.EM_PRODUCAO:
        return ""
    for event in reversed(_production_events(req)):
        machine = _normalize_machine_name(event.get("machine"))
        if machine:
            return machine
    return ""


def _history_production_machine(req: Requisition) -> str:
    current_machine = _current_production_machine(req)
    if current_machine:
        return current_machine

    latest_cycle = _latest_finished_cycle(req)
    if latest_cycle:
        machine = _normalize_machine_name(latest_cycle.get("machine"))
        if machine:
            return machine

    return ""


def _history_production_names(req: Requisition, people_key: str) -> list[str]:
    if req.status == RequisitionStatus.EM_PRODUCAO:
        started_event = _latest_production_event(req, _PROD_STARTED, _PROD_RECEIVED)
        people_names = _clean_operator_names((started_event or {}).get(people_key) or [])
        if people_names:
            return people_names

    latest_cycle = _latest_finished_cycle(req)
    if latest_cycle:
        people_names = _clean_operator_names(latest_cycle.get(people_key) or [])
        if people_names:
            return people_names

    started_event = _latest_production_event(req, _PROD_STARTED, _PROD_RECEIVED)
    return _clean_operator_names((started_event or {}).get(people_key) or [])


def _history_production_operator_names(req: Requisition) -> list[str]:
    return _history_production_names(req, "operators")


def _history_production_helper_names(req: Requisition) -> list[str]:
    return _history_production_names(req, "helpers")


def _history_production_sent_at(req: Requisition) -> datetime | None:
    latest_send_event = _latest_production_event(req, _PROD_SEND)
    changed_at = (latest_send_event or {}).get("changed_at")
    return changed_at if isinstance(changed_at, datetime) else None


def _history_production_finished_at(req: Requisition) -> datetime | None:
    latest_cycle = _latest_finished_cycle(req)
    finished_at = (latest_cycle or {}).get("finished_at")
    return finished_at if isinstance(finished_at, datetime) else None


def _history_production_status(req: Requisition) -> str:
    current_status = str(getattr(req.status, "value", req.status) or "")
    if req.status == RequisitionStatus.CANCELADA:
        return current_status
    if req.status in (
        RequisitionStatus.AGUARDANDO_FATURAMENTO,
        RequisitionStatus.FATURADO,
    ):
        return current_status

    latest_event = _latest_production_event(
        req,
        _PROD_SEND,
        _PROD_RECEIVED,
        _PROD_QUEUED,
        _PROD_STARTED,
        _PROD_RETURNED_QUEUE,
        _PROD_FINISHED,
        _PROD_CANCELED,
    )
    if not latest_event:
        return current_status

    action = latest_event["action"]
    if action == _PROD_FINISHED:
        return "finalizada_producao"
    if action == _PROD_CANCELED:
        return "cancelada_producao"
    if action == _PROD_SEND:
        return RequisitionStatus.AGUARDANDO_RECEBIMENTO.value
    if action in (_PROD_QUEUED, _PROD_RETURNED_QUEUE):
        return RequisitionStatus.AGUARDANDO_NA_FILA.value
    if action in (_PROD_RECEIVED, _PROD_STARTED):
        return RequisitionStatus.EM_PRODUCAO.value
    return current_status


def _can_view_requisition(req: Requisition, current_user: User) -> bool:
    role = _role_key(current_user.role)
    if role in (Role.ADMIN.value, Role.GERENTE.value):
        return True
    if role == Role.VENDEDOR.value:
        return req.vendor_id == current_user.id

    destination = _destination_for_role(role)
    if destination:
        return _current_production_destination(req) == destination

    return False


def _filter_requisitions_for_user(
    reqs: list[Requisition], current_user: User
) -> list[Requisition]:
    return [req for req in reqs if _can_view_requisition(req, current_user)]


def _can_edit_requisition(req: Requisition, current_user: User) -> bool:
    role = _role_key(current_user.role)
    if role in (Role.ADMIN.value, Role.GERENTE.value):
        return True
    if req.vendor_id == current_user.id:
        return True

    destination = _destination_for_role(role)
    if destination:
        return _current_production_destination(req) == destination

    return False


def _is_open_requisition(req: Requisition) -> bool:
    if req.status in (
        RequisitionStatus.CANCELADA,
        RequisitionStatus.FATURADO,
    ):
        return False
    return True


def _latest_production_event(req: Requisition, *actions: str) -> dict | None:
    for event in reversed(_production_events(req)):
        if event["action"] in actions:
            return event
    return None


def _latest_status_changed_at(req: Requisition, status_value: str) -> datetime | None:
    target_status = getattr(status_value, "value", status_value)
    for entry in reversed(_sorted_status_history(req)):
        if str(entry.new_status) == str(target_status):
            return entry.changed_at
    return None


def _all_finished_cycles(req: Requisition) -> list[dict]:
    if _has_production_splits(req):
        cycles: list[dict] = []
        for split in _sorted_requisition_splits(req):
            for cycle in _split_all_finished_cycles(split):
                cycle_with_weight = dict(cycle)
                cycle_with_weight["weight"] = float(split.weight or 0.0)
                cycle_with_weight["split_id"] = split.id
                cycle_with_weight["split_sequence"] = split.sequence
                cycles.append(cycle_with_weight)
        cycles.sort(
            key=lambda cycle: (
                cycle.get("finished_at") or datetime.min,
                int(cycle.get("split_sequence") or 0),
            )
        )
        return cycles

    cycles: list[dict] = []
    started_at: datetime | None = None
    started_target: str | None = None
    started_machine: str | None = None
    started_operators: list[str] = []
    started_helpers: list[str] = []

    for event in _production_events(req):
        changed_at = event["changed_at"]
        if changed_at is None:
            continue

        action = event["action"]
        machine = str(event.get("machine") or "").strip() or None
        target = event.get("target") or None

        if action in (_PROD_RECEIVED, _PROD_STARTED):
            started_at = changed_at
            started_target = target
            started_machine = machine
            started_operators = list(event.get("operators") or [])
            started_helpers = list(event.get("helpers") or [])
            continue

        if action == _PROD_FINISHED:
            if started_at is not None:
                cycles.append(
                    {
                        "received_at": started_at,
                        "finished_at": changed_at,
                        "target": started_target,
                        "machine": started_machine,
                        "operators": list(started_operators),
                        "helpers": list(started_helpers),
                        "production_time_seconds": max(
                            0,
                            int((changed_at - started_at).total_seconds()),
                        ),
                    }
                )
            started_at = None
            started_target = None
            started_machine = None
            started_operators = []
            started_helpers = []
            continue

        if action in (
            _PROD_SEND,
            _PROD_QUEUED,
            _PROD_RETURNED_QUEUE,
            _PROD_CANCELED,
        ):
            started_at = None
            started_target = None
            started_machine = None
            started_operators = []
            started_helpers = []

    return cycles


def _current_active_cycle(req: Requisition, now: datetime | None = None) -> dict | None:
    started_at: datetime | None = None
    started_target: str | None = None
    started_machine: str | None = None

    for event in _production_events(req):
        changed_at = event["changed_at"]
        if changed_at is None:
            continue

        action = event["action"]
        machine = str(event.get("machine") or "").strip() or None
        target = event.get("target") or None

        if action in (_PROD_RECEIVED, _PROD_STARTED):
            started_at = changed_at
            started_target = target
            started_machine = machine
            continue

        if action in (
            _PROD_FINISHED,
            _PROD_SEND,
            _PROD_QUEUED,
            _PROD_RETURNED_QUEUE,
            _PROD_CANCELED,
        ):
            started_at = None
            started_target = None
            started_machine = None

    if started_at is None or req.status != RequisitionStatus.EM_PRODUCAO:
        return None

    finished_at = now or datetime.utcnow()
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        finished_at = finished_at.astimezone(timezone.utc).replace(tzinfo=None)
    elif started_at.tzinfo is not None and finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    return {
        "received_at": started_at,
        "finished_at": finished_at,
        "target": started_target,
        "machine": started_machine,
        "production_time_seconds": max(
            0,
            int((finished_at - started_at).total_seconds()),
        ),
    }


def _latest_finished_cycle(req: Requisition) -> dict | None:
    cycles = _all_finished_cycles(req)
    return cycles[-1] if cycles else None


def _production_sort_anchor(item: ProductionItemResponse, field_name: str) -> datetime:
    value = getattr(item, field_name, None)
    if isinstance(value, datetime):
        return value
    return item.created_at or item.emission_date


def _production_item(
    req: Requisition,
    *,
    waiting_since: datetime | None = None,
    production_started_at: datetime | None = None,
    machine_name: str | None = None,
    operator_names: list[str] | None = None,
    helper_names: list[str] | None = None,
) -> ProductionItemResponse:
    status_value = getattr(req.status, "value", req.status)
    return ProductionItemResponse(
        id=req.id,
        source_requisition_id=req.id,
        ped_number=req.ped_number,
        client_name=req.client_name,
        vendor_name=req.vendor_name,
        obra=req.obra,
        weight=req.weight,
        total_weight=req.weight,
        status=str(status_value),
        emission_date=req.emission_date,
        created_at=req.created_at,
        delivery_date=req.delivery_date,
        destination=_current_production_destination(req) or None,
        machine_name=_normalize_machine_name(machine_name) or None,
        operator_names=_clean_operator_names(operator_names or []),
        helper_names=_clean_operator_names(helper_names or []),
        waiting_since=waiting_since,
        production_started_at=production_started_at,
    )


def _production_split_item(
    req: Requisition,
    split: RequisitionProductionSplit,
    *,
    waiting_since: datetime | None = None,
    production_started_at: datetime | None = None,
    machine_name: str | None = None,
    operator_names: list[str] | None = None,
    helper_names: list[str] | None = None,
) -> ProductionItemResponse:
    status_value = getattr(split.status, "value", split.status)
    return ProductionItemResponse(
        id=split.id,
        source_requisition_id=req.id,
        production_split_id=split.id,
        split_sequence=split.sequence,
        is_partial_split=True,
        ped_number=_split_display_ped_number(req, split),
        client_name=req.client_name,
        vendor_name=req.vendor_name,
        obra=req.obra,
        weight=float(split.weight or 0.0),
        total_weight=float(req.weight or 0.0),
        status=str(status_value),
        emission_date=req.emission_date,
        created_at=split.created_at or req.created_at,
        delivery_date=req.delivery_date,
        destination=_split_destination(split) or _current_production_destination(req) or None,
        machine_name=_normalize_machine_name(machine_name) or None,
        operator_names=_clean_operator_names(operator_names or []),
        helper_names=_clean_operator_names(helper_names or []),
        waiting_since=waiting_since,
        production_started_at=production_started_at,
    )


def _production_remaining_item(
    req: Requisition,
    remaining_weight: float,
    *,
    waiting_since: datetime | None = None,
) -> ProductionItemResponse:
    item = _production_item(
        req,
        waiting_since=waiting_since,
    )
    item.weight = float(remaining_weight or 0.0)
    item.total_weight = float(req.weight or 0.0)
    return item


def _build_production_summary(
    reqs: list[Requisition],
    machines: list[ProductionMachine],
    destination: str,
) -> ProductionDestinationSummaryResponse:
    normalized_destination = _canonical_destination(destination)
    waiting_receipt: list[ProductionItemResponse] = []
    waiting_queue: list[ProductionItemResponse] = []
    machine_rows: dict[str, list[ProductionItemResponse]] = {
        _normalize_machine_name(machine.name): []
        for machine in machines
    }
    machine_cycles: dict[str, list[dict]] = {
        _normalize_machine_name(machine.name): []
        for machine in machines
    }

    for req in reqs:
        current_destination = _current_production_destination(req)
        if _has_production_splits(req):
            remaining_weight = _remaining_requisition_weight(req)
            if current_destination != normalized_destination and not any(
                _split_destination(split) == normalized_destination
                for split in _sorted_requisition_splits(req)
            ):
                continue

            if remaining_weight > 0:
                if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
                    sent_event = _latest_production_event(req, _PROD_SEND)
                    waiting_receipt.append(
                        _production_remaining_item(
                            req,
                            remaining_weight,
                            waiting_since=sent_event["changed_at"] if sent_event else None,
                        )
                    )
                elif req.status in (
                    RequisitionStatus.AGUARDANDO_NA_FILA,
                    RequisitionStatus.EM_PRODUCAO,
                ):
                    queue_event = _latest_production_event(
                        req,
                        _PROD_QUEUED,
                        _PROD_RETURNED_QUEUE,
                        _PROD_SEND,
                    )
                    waiting_queue.append(
                        _production_remaining_item(
                            req,
                            remaining_weight,
                            waiting_since=queue_event["changed_at"] if queue_event else None,
                        )
                    )

            for split in _sorted_requisition_splits(req):
                split_destination = _split_destination(split) or current_destination
                if split_destination != normalized_destination:
                    continue

                if split.status == RequisitionStatus.AGUARDANDO_NA_FILA:
                    queue_event = _split_latest_production_event(
                        split,
                        _PROD_QUEUED,
                        _PROD_RETURNED_QUEUE,
                        _PROD_SEND,
                        _PROD_STARTED,
                    )
                    waiting_queue.append(
                        _production_split_item(
                            req,
                            split,
                            waiting_since=(queue_event or {}).get("changed_at") or split.updated_at,
                        )
                    )

                split_machine = _split_current_machine(split)
                if split.status == RequisitionStatus.EM_PRODUCAO and split_machine in machine_rows:
                    started_event = _split_latest_production_event(split, _PROD_STARTED, _PROD_RECEIVED)
                    machine_rows[split_machine].append(
                        _production_split_item(
                            req,
                            split,
                            machine_name=split_machine,
                            operator_names=(started_event or {}).get("operators") or [],
                            helper_names=(started_event or {}).get("helpers") or [],
                            production_started_at=(started_event or {}).get("changed_at"),
                        )
                    )

                for cycle in _split_all_finished_cycles(split):
                    if cycle.get("target") != normalized_destination:
                        continue
                    machine_name = _normalize_machine_name(cycle.get("machine"))
                    if machine_name in machine_cycles:
                        machine_cycles[machine_name].append(cycle)
            continue

        if current_destination != normalized_destination:
            continue

        if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
            sent_event = _latest_production_event(req, _PROD_SEND)
            waiting_receipt.append(
                _production_item(
                    req,
                    waiting_since=sent_event["changed_at"] if sent_event else None,
                )
            )

        current_machine = _current_production_machine(req)
        if req.status == RequisitionStatus.AGUARDANDO_NA_FILA or (
            req.status == RequisitionStatus.EM_PRODUCAO and not current_machine
        ):
            queue_event = _latest_production_event(
                req,
                _PROD_QUEUED,
                _PROD_RETURNED_QUEUE,
                _PROD_SEND,
            )
            waiting_queue.append(
                _production_item(
                    req,
                    waiting_since=queue_event["changed_at"] if queue_event else None,
                )
            )

        if req.status == RequisitionStatus.EM_PRODUCAO and current_machine in machine_rows:
            started_event = _latest_production_event(req, _PROD_STARTED, _PROD_RECEIVED)
            machine_rows[current_machine].append(
                _production_item(
                    req,
                    machine_name=current_machine,
                    operator_names=(started_event or {}).get("operators") or [],
                    helper_names=(started_event or {}).get("helpers") or [],
                    production_started_at=started_event["changed_at"] if started_event else None,
                )
            )

        for cycle in _all_finished_cycles(req):
            if cycle.get("target") != normalized_destination:
                continue
            machine_name = _normalize_machine_name(cycle.get("machine"))
            if machine_name in machine_cycles:
                machine_cycles[machine_name].append(cycle)

    waiting_receipt.sort(key=lambda item: _production_sort_anchor(item, "waiting_since"))
    waiting_queue.sort(key=lambda item: _production_sort_anchor(item, "waiting_since"))

    machine_cards: list[ProductionMachineCardResponse] = []
    for machine in machines:
        machine_name = _normalize_machine_name(machine.name)
        rows = machine_rows.get(machine_name, [])
        rows.sort(key=lambda item: _production_sort_anchor(item, "production_started_at"))
        finished_cycles = machine_cycles.get(machine_name, [])
        average_seconds = None
        if finished_cycles:
            average_seconds = int(
                sum(cycle["production_time_seconds"] for cycle in finished_cycles)
                / len(finished_cycles)
            )
        machine_cards.append(
            ProductionMachineCardResponse(
                id=machine.id,
                destination=machine.destination,
                name=machine_name,
                sort_order=machine.sort_order,
                status=machine.status,
                operators=[
                    _normalize_operator_name(operator.name)
                    for operator in (getattr(machine, "operators", None) or [])
                    if _normalize_operator_name(operator.name)
                ],
                team_members=[
                    {
                        "id": int(operator.id),
                        "name": _normalize_operator_name(operator.name),
                        "role": getattr(getattr(operator, "role", None), "value", None)
                        or OperatorRole.OPERADOR.value,
                    }
                    for operator in (getattr(machine, "operators", None) or [])
                    if _normalize_operator_name(operator.name)
                ],
                quantity_in_production=len(rows),
                finalized_count=len(finished_cycles),
                average_seconds=average_seconds,
                rows=rows,
            )
        )

    return ProductionDestinationSummaryResponse(
        generated_at=datetime.utcnow(),
        destination=normalized_destination,
        stats=ProductionSummaryStatsResponse(
            aguardando_recebimento=len(waiting_receipt),
            aguardando_na_fila=len(waiting_queue),
            em_producao=sum(len(card.rows) for card in machine_cards),
        ),
        waiting_receipt=waiting_receipt,
        waiting_queue=waiting_queue,
        machines=machine_cards,
    )


def _load_production_pending_summary(
    db: Session,
    current_user: User,
    destination: str,
) -> ProductionDestinationSummaryResponse:
    normalized_destination = _canonical_destination(destination)
    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.asc(), Requisition.id.asc())
        .all()
    )
    visible = _filter_requisitions_for_user(reqs, current_user)
    return _build_production_summary(visible, [], normalized_destination)


def _production_fifo_anchor_text(item: ProductionItemResponse) -> str:
    anchor = item.waiting_since or item.created_at or item.emission_date
    if not isinstance(anchor, datetime):
        return ""
    return anchor.strftime("%d/%m/%Y %H:%M")


def _production_fifo_matches(
    item: ProductionItemResponse,
    *,
    requisition_id: int | None = None,
    split_id: int | None = None,
) -> bool:
    if split_id is not None:
        return int(item.production_split_id or 0) == int(split_id)
    if requisition_id is None:
        return False
    item_requisition_id = int(item.source_requisition_id or item.id or 0)
    return item.production_split_id in (None, 0) and item_requisition_id == int(requisition_id)


def _ensure_production_fifo_item(
    first_item: ProductionItemResponse | None,
    *,
    stage: str,
    requisition_id: int | None = None,
    split_id: int | None = None,
) -> None:
    if first_item is None:
        return
    if _production_fifo_matches(
        first_item,
        requisition_id=requisition_id,
        split_id=split_id,
    ):
        return

    waiting_text = _production_fifo_anchor_text(first_item)
    when_text = f" enviada em {waiting_text}" if waiting_text else ""
    if stage == "waiting_receipt":
        detail = (
            f"Atenda primeiro a requisicao PED {first_item.ped_number}{when_text} "
            "antes de responder outra em aguardando recebimento."
        )
    else:
        detail = (
            f"Atenda primeiro a requisicao PED {first_item.ped_number}{when_text} "
            "antes de iniciar outra requisicao na fila."
        )
    raise HTTPException(status_code=400, detail=detail)


def _ensure_waiting_receipt_fifo(
    db: Session,
    current_user: User,
    destination: str,
    requisition_id: int,
) -> None:
    summary = _load_production_pending_summary(db, current_user, destination)
    first_item = summary.waiting_receipt[0] if summary.waiting_receipt else None
    _ensure_production_fifo_item(
        first_item,
        stage="waiting_receipt",
        requisition_id=requisition_id,
    )


def _ensure_waiting_queue_fifo_for_requisition(
    db: Session,
    current_user: User,
    destination: str,
    requisition_id: int,
) -> None:
    summary = _load_production_pending_summary(db, current_user, destination)
    first_item = summary.waiting_queue[0] if summary.waiting_queue else None
    _ensure_production_fifo_item(
        first_item,
        stage="waiting_queue",
        requisition_id=requisition_id,
    )


def _ensure_waiting_queue_fifo_for_split(
    db: Session,
    current_user: User,
    destination: str,
    split_id: int,
) -> None:
    summary = _load_production_pending_summary(db, current_user, destination)
    first_item = summary.waiting_queue[0] if summary.waiting_queue else None
    _ensure_production_fifo_item(
        first_item,
        stage="waiting_queue",
        split_id=split_id,
    )


def _build_order_center(reqs: list[Requisition]) -> OrderCenterResponse:
    now = datetime.utcnow()
    today = now.date()

    waiting_rows: list[OrderCenterItemResponse] = []
    production_rows: list[OrderCenterItemResponse] = []
    pending_invoice_rows: list[OrderCenterItemResponse] = []
    billed_rows: list[OrderCenterItemResponse] = []
    canceled_rows: list[OrderCenterItemResponse] = []
    delayed_rows: list[OrderCenterItemResponse] = []
    production_durations: list[int] = []

    for req in reqs:
        destination = _current_production_destination(req) or None
        machine_name = _history_production_machine(req) or None
        operator_names = _history_production_operator_names(req)
        helper_names = _history_production_helper_names(req)
        weight_value = float(req.weight or 0.0)
        sent_event = _latest_production_event(req, _PROD_SEND)
        sent_to_production_at = sent_event["changed_at"] if sent_event else None
        events = _production_events(req)
        latest_event = events[-1] if events else None
        legacy_production_canceled = (
            req.status != RequisitionStatus.CANCELADA
            and bool(latest_event)
            and latest_event.get("action") == _PROD_CANCELED
        )

        if _has_production_splits(req):
            remaining_weight = _remaining_requisition_weight(req)
            if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO and remaining_weight > 0:
                waiting_minutes = None
                if sent_to_production_at:
                    waiting_minutes = max(
                        0,
                        int((now - sent_to_production_at).total_seconds() // 60),
                    )
                waiting_rows.append(
                    OrderCenterItemResponse(
                        id=req.id,
                        source_requisition_id=req.id,
                        ped_number=req.ped_number,
                        client_name=req.client_name,
                        vendor_name=req.vendor_name,
                        weight=remaining_weight,
                        total_weight=weight_value,
                        status=req.status,
                        emission_date=req.emission_date,
                        delivery_date=req.delivery_date,
                        destination=destination,
                        waiting_minutes=waiting_minutes,
                        sent_to_production_at=sent_to_production_at,
                    )
                )

            if remaining_weight > 0 and req.status in (
                RequisitionStatus.AGUARDANDO_NA_FILA,
                RequisitionStatus.EM_PRODUCAO,
            ):
                production_rows.append(
                    OrderCenterItemResponse(
                        id=req.id,
                        source_requisition_id=req.id,
                        ped_number=req.ped_number,
                        client_name=req.client_name,
                        vendor_name=req.vendor_name,
                        weight=remaining_weight,
                        total_weight=weight_value,
                        status=req.status,
                        emission_date=req.emission_date,
                        delivery_date=req.delivery_date,
                        destination=destination,
                        received_at=None,
                        machine_name=None,
                        operator_names=[],
                        helper_names=[],
                    )
                )

            for split in _sorted_requisition_splits(req):
                split_destination = _split_destination(split) or destination
                split_machine_name = _split_current_machine(split) or None
                split_weight_value = float(split.weight or 0.0)
                started_event = _split_latest_production_event(split, _PROD_STARTED)
                received_event = started_event or _split_latest_production_event(split, _PROD_RECEIVED)
                current_people_event = received_event or _split_latest_production_event(split, _PROD_FINISHED)
                split_operator_names = _clean_operator_names((current_people_event or {}).get("operators") or [])
                split_helper_names = _clean_operator_names((current_people_event or {}).get("helpers") or [])
                split_ped_number = _split_display_ped_number(req, split)
                split_cycles = _split_all_finished_cycles(split)
                latest_split_finished = split_cycles[-1] if split_cycles else None

                if latest_split_finished:
                    production_durations.append(latest_split_finished["production_time_seconds"])

                if split.status in (
                    RequisitionStatus.AGUARDANDO_NA_FILA,
                    RequisitionStatus.EM_PRODUCAO,
                ):
                    production_rows.append(
                        OrderCenterItemResponse(
                            id=split.id,
                            source_requisition_id=req.id,
                            production_split_id=split.id,
                            split_sequence=split.sequence,
                            is_partial_split=True,
                            ped_number=split_ped_number,
                            client_name=req.client_name,
                            vendor_name=req.vendor_name,
                            weight=split_weight_value,
                            total_weight=weight_value,
                            status=str(getattr(split.status, "value", split.status) or ""),
                            emission_date=req.emission_date,
                            delivery_date=req.delivery_date,
                            destination=split_destination,
                            received_at=received_event["changed_at"] if received_event else None,
                            machine_name=split_machine_name,
                            operator_names=split_operator_names,
                            helper_names=split_helper_names,
                        )
                    )

                if split.status == RequisitionStatus.FATURADO and latest_split_finished:
                    billed_rows.append(
                        OrderCenterItemResponse(
                            id=split.id,
                            source_requisition_id=req.id,
                            production_split_id=split.id,
                            split_sequence=split.sequence,
                            is_partial_split=True,
                            ped_number=split_ped_number,
                            client_name=req.client_name,
                            vendor_name=req.vendor_name,
                            weight=split_weight_value,
                            total_weight=weight_value,
                            status=RequisitionStatus.FATURADO.value,
                            emission_date=req.emission_date,
                            delivery_date=req.delivery_date,
                            destination=latest_split_finished["target"] or split_destination,
                            sent_to_production_at=sent_to_production_at,
                            received_at=latest_split_finished["received_at"],
                            finished_at=latest_split_finished["finished_at"],
                            invoiced_at=latest_split_finished["finished_at"],
                            machine_name=_normalize_machine_name(latest_split_finished.get("machine")) or split_machine_name,
                            operator_names=[
                                str(name).strip()
                                for name in (latest_split_finished.get("operators") or split_operator_names)
                                if str(name).strip()
                            ],
                            helper_names=[
                                str(name).strip()
                                for name in (latest_split_finished.get("helpers") or split_helper_names)
                                if str(name).strip()
                            ],
                            production_time_seconds=latest_split_finished["production_time_seconds"],
                            deadline_met=_did_finish_on_time(latest_split_finished["finished_at"], req.delivery_date),
                        )
                    )

                if req.delivery_date and req.delivery_date < today and split.status in (
                    RequisitionStatus.AGUARDANDO_NA_FILA,
                    RequisitionStatus.EM_PRODUCAO,
                ):
                    delayed_rows.append(
                        OrderCenterItemResponse(
                            id=split.id,
                            source_requisition_id=req.id,
                            production_split_id=split.id,
                            split_sequence=split.sequence,
                            is_partial_split=True,
                            ped_number=split_ped_number,
                            client_name=req.client_name,
                            vendor_name=req.vendor_name,
                            weight=split_weight_value,
                            total_weight=weight_value,
                            status=str(getattr(split.status, "value", split.status) or ""),
                            emission_date=req.emission_date,
                            delivery_date=req.delivery_date,
                            destination=split_destination,
                            machine_name=split_machine_name,
                            operator_names=split_operator_names,
                            helper_names=split_helper_names,
                            delay_days=max(0, (today - req.delivery_date).days),
                        )
                    )

            if req.status == RequisitionStatus.CANCELADA:
                canceled_rows.append(
                    OrderCenterItemResponse(
                        id=req.id,
                        source_requisition_id=req.id,
                        ped_number=req.ped_number,
                        client_name=req.client_name,
                        vendor_name=req.vendor_name,
                        weight=remaining_weight if remaining_weight > 0 else weight_value,
                        total_weight=weight_value,
                        status=RequisitionStatus.CANCELADA.value,
                        emission_date=req.emission_date,
                        delivery_date=req.delivery_date,
                        destination=destination,
                        canceled_at=_latest_status_changed_at(req, RequisitionStatus.CANCELADA),
                        cancel_reason=_cancel_reason_for(req),
                    )
                )
            continue

        if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
            waiting_minutes = None
            if sent_to_production_at:
                waiting_minutes = max(
                    0,
                    int((now - sent_to_production_at).total_seconds() // 60),
                )
            waiting_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    weight=weight_value,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    waiting_minutes=waiting_minutes,
                    sent_to_production_at=sent_to_production_at,
                )
            )

        if req.status in (
            RequisitionStatus.AGUARDANDO_NA_FILA,
            RequisitionStatus.EM_PRODUCAO,
        ):
            started_event = _latest_production_event(req, _PROD_STARTED)
            received_event = started_event or _latest_production_event(req, _PROD_RECEIVED)
            production_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    weight=weight_value,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    received_at=received_event["changed_at"] if received_event else None,
                    machine_name=machine_name,
                    operator_names=operator_names,
                    helper_names=helper_names,
                )
            )

        latest_finished = _latest_finished_cycle(req)
        if latest_finished:
            production_durations.append(latest_finished["production_time_seconds"])
        if req.status in (RequisitionStatus.AGUARDANDO_FATURAMENTO, RequisitionStatus.FATURADO) and latest_finished:
            invoiced_at = (
                _latest_status_changed_at(req, RequisitionStatus.FATURADO)
                or _latest_status_changed_at(req, RequisitionStatus.AGUARDANDO_FATURAMENTO)
                or latest_finished["finished_at"]
                or sent_to_production_at
            )
            cycle_machine_name = _normalize_machine_name(latest_finished.get("machine")) or machine_name
            cycle_operator_names = [
                str(name).strip()
                for name in (latest_finished.get("operators") or operator_names)
                if str(name).strip()
            ]
            cycle_helper_names = [
                str(name).strip()
                for name in (latest_finished.get("helpers") or helper_names)
                if str(name).strip()
            ]
            billed_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    weight=weight_value,
                    status=RequisitionStatus.FATURADO.value,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=latest_finished["target"] or destination,
                    sent_to_production_at=sent_to_production_at,
                    received_at=latest_finished["received_at"],
                    finished_at=latest_finished["finished_at"],
                    invoiced_at=invoiced_at,
                    machine_name=cycle_machine_name,
                    operator_names=cycle_operator_names,
                    helper_names=cycle_helper_names,
                    production_time_seconds=latest_finished["production_time_seconds"],
                    deadline_met=_did_finish_on_time(latest_finished["finished_at"], req.delivery_date),
                )
            )

        if req.status == RequisitionStatus.CANCELADA or legacy_production_canceled:
            canceled_at = _latest_status_changed_at(req, RequisitionStatus.CANCELADA)
            if canceled_at is None and latest_event:
                canceled_at = latest_event.get("changed_at")
            canceled_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    weight=weight_value,
                    status=RequisitionStatus.CANCELADA.value,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    canceled_at=canceled_at,
                    cancel_reason=_cancel_reason_for(req),
                )
            )

        if req.delivery_date and req.delivery_date < today and _is_open_requisition(req) and not legacy_production_canceled:
            delayed_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    weight=weight_value,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    machine_name=machine_name,
                    operator_names=operator_names,
                    helper_names=helper_names,
                    delay_days=max(0, (today - req.delivery_date).days),
                )
            )

    waiting_rows.sort(key=lambda item: item.waiting_minutes or 0, reverse=True)
    production_rows.sort(key=lambda item: item.received_at or datetime.min, reverse=True)
    pending_invoice_rows.sort(key=lambda item: item.finished_at or datetime.min)
    billed_rows.sort(key=lambda item: item.invoiced_at or datetime.min, reverse=True)
    canceled_rows.sort(key=lambda item: item.canceled_at or datetime.min, reverse=True)
    delayed_rows.sort(key=lambda item: item.delay_days or 0, reverse=True)

    average_seconds = None
    if production_durations:
        average_seconds = int(sum(production_durations) / len(production_durations))

    return OrderCenterResponse(
        generated_at=now,
        stats=OrderCenterStatsResponse(
            pedidos_aguardando_recebimento=len(waiting_rows),
            pedidos_em_producao=len(production_rows),
            pedidos_aguardando_faturamento=len(pending_invoice_rows),
            pedidos_faturados=len(billed_rows),
            pedidos_cancelados=len(canceled_rows),
            pedidos_atrasados=len(delayed_rows),
            tempo_medio_producao_segundos=average_seconds,
        ),
        aguardando_recebimento=waiting_rows[:100],
        em_producao=production_rows[:100],
        aguardando_faturamento=pending_invoice_rows[:100],
        faturados=billed_rows[:100],
        cancelados=canceled_rows[:100],
        atrasados=delayed_rows[:100],
    )


def _history_row_from_requisition(
    req: Requisition,
    *,
    weight_value: float | None = None,
    include_production_details: bool = True,
) -> dict:
    status_value = getattr(req.status, "value", req.status)
    operator_names = _history_production_operator_names(req) if include_production_details else []
    helper_names = _history_production_helper_names(req) if include_production_details else []
    production_machine = _history_production_machine(req) if include_production_details else None
    return {
        "id": int(req.id),
        "source_requisition_id": int(req.id),
        "production_split_id": None,
        "split_sequence": None,
        "is_partial_split": False,
        "ped_number": req.ped_number,
        "emission_date": req.emission_date,
        "delivery_date": req.delivery_date,
        "os_number": req.os_number,
        "vendor_id": req.vendor_id,
        "vendor_name": req.vendor_name,
        "vendor_code": req.vendor_code,
        "client_id": req.client_id,
        "client_code": req.client_code,
        "client_name": req.client_name,
        "obra": req.obra,
        "nf_attachment": req.nf_attachment,
        "retirada": bool(req.retirada),
        "entrega": bool(req.entrega),
        "delivery_address": req.delivery_address,
        "phone": req.phone,
        "weight": float(weight_value if weight_value is not None else (req.weight or 0.0)),
        "total_weight": float(req.weight or 0.0),
        "obs": req.obs,
        "status": status_value,
        "production_destination": _current_production_destination(req) or None,
        "production_destination_display": _current_production_destination(req) or None,
        "production_machine": production_machine or None,
        "production_machine_display": production_machine or None,
        "production_status": _history_production_status(req) if include_production_details else str(status_value or ""),
        "production_operator_names": operator_names,
        "production_operator_display": ", ".join(operator_names) or None,
        "production_helper_names": helper_names,
        "production_helper_display": ", ".join(helper_names) or None,
        "production_sent_at": _history_production_sent_at(req),
        "production_finished_at": _history_production_finished_at(req) if include_production_details else None,
        "cancel_reason": _cancel_reason_for(req),
        "invoiced": req.status == RequisitionStatus.FATURADO,
        "delivered_at": req.delivered_at,
        "finalized_at": req.finalized_at,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }


def _history_row_from_split(req: Requisition, split: RequisitionProductionSplit) -> dict:
    latest_started = _split_latest_production_event(split, _PROD_STARTED, _PROD_RECEIVED)
    latest_finished = _split_all_finished_cycles(split)
    latest_cycle = latest_finished[-1] if latest_finished else None
    operator_names = _clean_operator_names(
        (latest_started or latest_cycle or {}).get("operators") or []
    )
    helper_names = _clean_operator_names(
        (latest_started or latest_cycle or {}).get("helpers") or []
    )
    production_machine = (
        _split_current_machine(split)
        or _normalize_machine_name((latest_cycle or {}).get("machine"))
        or None
    )
    split_status = getattr(split.status, "value", split.status)
    production_status = str(split_status or "")
    if split.status == RequisitionStatus.FATURADO:
        production_status = "finalizada_producao"
    return {
        "id": int(split.id),
        "source_requisition_id": int(req.id),
        "production_split_id": int(split.id),
        "split_sequence": int(split.sequence or 0),
        "is_partial_split": True,
        "ped_number": _split_display_ped_number(req, split),
        "emission_date": req.emission_date,
        "delivery_date": req.delivery_date,
        "os_number": req.os_number,
        "vendor_id": req.vendor_id,
        "vendor_name": req.vendor_name,
        "vendor_code": req.vendor_code,
        "client_id": req.client_id,
        "client_code": req.client_code,
        "client_name": req.client_name,
        "obra": req.obra,
        "nf_attachment": req.nf_attachment,
        "retirada": bool(req.retirada),
        "entrega": bool(req.entrega),
        "delivery_address": req.delivery_address,
        "phone": req.phone,
        "weight": float(split.weight or 0.0),
        "total_weight": float(req.weight or 0.0),
        "obs": req.obs,
        "status": str(split_status or ""),
        "production_destination": _split_destination(split) or _current_production_destination(req) or None,
        "production_destination_display": _split_destination(split) or _current_production_destination(req) or None,
        "production_machine": production_machine,
        "production_machine_display": production_machine,
        "production_status": production_status,
        "production_operator_names": operator_names,
        "production_operator_display": ", ".join(operator_names) or None,
        "production_helper_names": helper_names,
        "production_helper_display": ", ".join(helper_names) or None,
        "production_sent_at": split.created_at,
        "production_finished_at": (latest_cycle or {}).get("finished_at"),
        "cancel_reason": None,
        "invoiced": split.status == RequisitionStatus.FATURADO,
        "delivered_at": req.delivered_at,
        "finalized_at": req.finalized_at,
        "created_at": split.created_at,
        "updated_at": split.updated_at,
    }


def _build_delivery_center(reqs: list[Requisition]) -> DeliveryCenterResponse:
    now = datetime.utcnow()
    today = (_to_local_datetime(now) or datetime.now(_LOCAL_TIMEZONE)).date()

    rows: list[DeliveryCenterItemResponse] = []
    deliveries_today = 0
    delayed_deliveries = 0
    changed_delivery_deadlines = 0
    completed_deliveries = 0

    for req in reqs:
        delivered_at = getattr(req, "delivered_at", None)
        status_value = getattr(req.status, "value", req.status)

        # A tela de Entregas só lista pedidos marcados para entrega e que já
        # passaram pela etapa de faturamento (faturado/prazo alterado/entregue).
        if (
            not req.entrega
            or req.status == RequisitionStatus.CANCELADA
            or (
                delivered_at is None
                and status_value not in (
                    RequisitionStatus.FATURADO.value,
                    RequisitionStatus.PRAZO_ALTERADO.value,
                )
            )
        ):
            continue

        deadline_changed_at = _delivery_deadline_changed_at(req)
        delivery_date = req.delivery_date

        if delivered_at is not None:
            completed_deliveries += 1

        if delivered_at is None and delivery_date is not None:
            if delivery_date == today:
                deliveries_today += 1
            elif delivery_date < today:
                delayed_deliveries += 1

        if delivered_at is None and deadline_changed_at is not None:
            changed_delivery_deadlines += 1

        display_status = str(status_value or "")
        if delivered_at is not None:
            display_status = "entregue"
        elif (
            display_status != RequisitionStatus.PRAZO_ALTERADO.value
            and delivered_at is None
            and deadline_changed_at is not None
        ):
            display_status = RequisitionStatus.PRAZO_ALTERADO.value

        rows.append(
            DeliveryCenterItemResponse(
                id=req.id,
                ped_number=req.ped_number,
                client_name=req.client_name,
                vendor_name=req.vendor_name,
                weight=float(req.weight or 0.0),
                destination=_current_production_destination(req) or None,
                delivery_date=delivery_date,
                status=display_status,
                delivered_at=delivered_at if isinstance(delivered_at, datetime) else None,
                deadline_changed_at=deadline_changed_at,
                deadline_change_reason=str(getattr(req, "delivery_deadline_change_reason", "") or ""),
            )
        )

    rows.sort(
        key=lambda item: (
            item.delivery_date is None,
            item.delivery_date or date.max,
            str(item.ped_number or ""),
        )
    )

    return DeliveryCenterResponse(
        generated_at=now,
        stats=DeliveryCenterStatsResponse(
            deliveries_today=deliveries_today,
            delayed_deliveries=delayed_deliveries,
            changed_delivery_deadlines=changed_delivery_deadlines,
            completed_deliveries=completed_deliveries,
        ),
        rows=rows[:200],
    )


def _build_machine_usage_rows(
    reqs: list[Requisition],
    machines: list[ProductionMachine],
    destination: str,
    period_key: str,
    now: datetime | None = None,
) -> list[DashboardMachineUsageItem]:
    normalized_destination = _canonical_destination(destination)
    period_start, period_end = _machine_dashboard_period_bounds(period_key, now)
    total_shift_seconds = _intervals_total_seconds(
        _iter_shift_overlap_segments(period_start, period_end)
    )
    destination_machines = [
        machine
        for machine in machines
        if _canonical_destination(machine.destination) == normalized_destination
    ]
    usage: dict[str, dict] = {
        _normalize_machine_name(machine.name): {
            "machine": machine,
            "finished_count": 0,
            "in_production_count": 0,
            "durations": [],
            "weight_kg": 0.0,
            "work_intervals": [],
        }
        for machine in destination_machines
    }

    for req in reqs:
        current_destination = _current_production_destination(req)
        current_machine = _current_production_machine(req)
        if (
            current_destination == normalized_destination
            and req.status == RequisitionStatus.EM_PRODUCAO
            and current_machine in usage
        ):
            usage[current_machine]["in_production_count"] += 1

        for cycle in _all_finished_cycles(req):
            if _canonical_destination(cycle.get("target")) != normalized_destination:
                continue
            machine_name = _normalize_machine_name(cycle.get("machine"))
            if machine_name not in usage:
                continue
            finished_at = _to_local_datetime(cycle.get("finished_at"))
            if finished_at is None or finished_at < period_start or finished_at >= period_end:
                continue
            usage[machine_name]["finished_count"] += 1
            production_seconds = cycle.get("production_time_seconds")
            if isinstance(production_seconds, int):
                usage[machine_name]["durations"].append(max(0, production_seconds))
            usage[machine_name]["weight_kg"] += float(req.weight or 0.0)

        active_cycle = _current_active_cycle(req, now=period_end)
        if (
            active_cycle
            and current_destination == normalized_destination
            and _canonical_destination(active_cycle.get("target")) == normalized_destination
        ):
            machine_name = _normalize_machine_name(active_cycle.get("machine"))
            if machine_name in usage:
                start_at = active_cycle.get("received_at")
                end_at = active_cycle.get("finished_at")
                if isinstance(start_at, datetime) and isinstance(end_at, datetime):
                    clipped_start = max(_to_local_datetime(start_at) or period_start, period_start)
                    clipped_end = min(_to_local_datetime(end_at) or period_end, period_end)
                    if clipped_end > clipped_start:
                        usage[machine_name]["work_intervals"].append((clipped_start, clipped_end))

        for cycle in _all_finished_cycles(req):
            if _canonical_destination(cycle.get("target")) != normalized_destination:
                continue
            machine_name = _normalize_machine_name(cycle.get("machine"))
            if machine_name not in usage:
                continue
            start_at = cycle.get("received_at")
            end_at = cycle.get("finished_at")
            if not isinstance(start_at, datetime) or not isinstance(end_at, datetime):
                continue
            clipped_start = max(_to_local_datetime(start_at) or period_start, period_start)
            clipped_end = min(_to_local_datetime(end_at) or period_end, period_end)
            if clipped_end > clipped_start:
                usage[machine_name]["work_intervals"].append((clipped_start, clipped_end))

    rows: list[DashboardMachineUsageItem] = []
    for machine in destination_machines:
        machine_name = _normalize_machine_name(machine.name)
        stats = usage[machine_name]
        durations = stats["durations"]
        average_seconds = None
        if durations:
            average_seconds = int(sum(durations) / len(durations))
        merged_intervals = _merge_intervals(stats["work_intervals"])
        work_time_seconds = min(
            _intervals_total_seconds(merged_intervals),
            total_shift_seconds,
        )
        stopped_time_seconds = max(0, total_shift_seconds - work_time_seconds)
        efficiency_percent = 0.0
        if total_shift_seconds > 0:
            efficiency_percent = round((work_time_seconds / total_shift_seconds) * 100, 1)

        rows.append(
            DashboardMachineUsageItem(
                machine_name=machine_name,
                total_operations=int(stats["finished_count"]),
                in_production_count=int(stats["in_production_count"]),
                average_seconds=average_seconds,
                work_time_seconds=work_time_seconds,
                stopped_time_seconds=stopped_time_seconds,
                efficiency_percent=efficiency_percent,
                total_weight_kg=round(float(stats["weight_kg"]), 2),
                machine_status=getattr(machine.status, "value", machine.status) or "",
            )
        )

    rows.sort(
        key=lambda item: (
            -int(item.total_operations or 0),
            -int(item.work_time_seconds or 0),
            _normalize_text(item.machine_name),
        )
    )
    return rows


def _build_iar_general(
    reqs: list[Requisition],
    period_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    destination: str = "",
    now: datetime | None = None,
) -> DashboardIarSummaryItem:
    received_count = 0
    finalized_count = 0
    on_time_count = 0
    canceled_count = 0

    for req in reqs:
        if destination and _current_production_destination(req) != destination:
            continue
        emission_at = _parse_local_emission_datetime(req.emission_date) or _to_local_datetime(req.created_at)
        if not _datetime_in_performance_period(
            emission_at,
            period_key,
            start_date,
            end_date,
            now,
        ):
            continue

        received_count += 1
        if req.status == RequisitionStatus.CANCELADA:
            canceled_count += 1
            continue

        if _request_finished_at(req) is not None:
            finalized_count += 1
            if _request_finished_on_time(req):
                on_time_count += 1

    return _build_iar_summary_item(
        received_count=received_count,
        finalized_count=finalized_count,
        on_time_count=on_time_count,
        canceled_count=canceled_count,
    )


def _build_top_vendor_rows(
    reqs: list[Requisition],
    period_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
    destination: str = "",
    now: datetime | None = None,
) -> list[DashboardVendorItem]:
    stats: dict[tuple[int, str], dict[str, object]] = {}
    for req in reqs:
        if destination and _current_production_destination(req) != destination:
            continue
        emission_at = _parse_local_emission_datetime(req.emission_date) or _to_local_datetime(req.created_at)
        if not _datetime_in_performance_period(
            emission_at,
            period_key,
            start_date,
            end_date,
            now,
        ):
            continue
        vendor_name = (req.vendor_name or "").strip() or "Sem vendedor"
        vendor_key = (int(req.vendor_id or 0), vendor_name)
        entry = stats.setdefault(
            vendor_key,
            {
                "vendor_name": vendor_name,
                "received_count": 0,
                "finalized_count": 0,
                "on_time_count": 0,
                "canceled_count": 0,
                "total_weight_kg": 0.0,
            },
        )
        entry["received_count"] = int(entry["received_count"] or 0) + 1
        entry["total_weight_kg"] = float(entry["total_weight_kg"] or 0.0) + float(req.weight or 0.0)

        if req.status == RequisitionStatus.CANCELADA:
            entry["canceled_count"] = int(entry["canceled_count"] or 0) + 1
            continue

        if _request_finished_at(req) is not None:
            entry["finalized_count"] = int(entry["finalized_count"] or 0) + 1
            if _request_finished_on_time(req):
                entry["on_time_count"] = int(entry["on_time_count"] or 0) + 1

    rows: list[DashboardVendorItem] = []
    for data in stats.values():
        iar = _build_iar_summary_item(
            received_count=int(data["received_count"] or 0),
            finalized_count=int(data["finalized_count"] or 0),
            on_time_count=int(data["on_time_count"] or 0),
            canceled_count=int(data["canceled_count"] or 0),
        )
        rows.append(
            DashboardVendorItem(
                vendor_name=str(data["vendor_name"] or "Sem vendedor"),
                requisition_count=int(data["received_count"] or 0),
                total_weight_kg=round(float(data["total_weight_kg"] or 0.0), 2),
                prazo_percent=iar.prazo_percent,
                produtividade_percent=iar.produtividade_percent,
                cancelamentos_percent=iar.cancelamentos_percent,
                iar_percent=iar.iar_percent,
            )
        )

    rows.sort(
        key=lambda item: (
            -item.iar_percent,
            -item.requisition_count,
            -item.total_weight_kg,
            _normalize_text(item.vendor_name),
        )
    )
    return rows[:8]


def _build_top_production_people_rows(
    reqs: list[Requisition],
    period_key: str,
    destination: str = "",
    now: datetime | None = None,
) -> tuple[list[DashboardProductionPersonItem], list[DashboardProductionPersonItem]]:
    operators_stats: dict[str, dict[str, object]] = {}
    helpers_stats: dict[str, dict[str, object]] = {}

    def _accumulate(target: dict[str, dict[str, object]], names: list[str], weight: float) -> None:
        for name in _clean_operator_names(names):
            entry = target.setdefault(
                name,
                {
                    "person_name": name,
                    "production_count": 0,
                    "total_weight_kg": 0.0,
                },
            )
            entry["production_count"] = int(entry["production_count"] or 0) + 1
            entry["total_weight_kg"] = float(entry["total_weight_kg"] or 0.0) + weight

    for req in reqs:
        weight = float(req.weight or 0.0)
        for cycle in _all_finished_cycles(req):
            if not _datetime_in_dashboard_period(cycle.get("finished_at"), period_key, now):
                continue
            if destination and _canonical_destination(cycle.get("target")) != destination:
                continue
            _accumulate(operators_stats, list(cycle.get("operators") or []), weight)
            _accumulate(helpers_stats, list(cycle.get("helpers") or []), weight)

    def _build_rows(source: dict[str, dict[str, object]]) -> list[DashboardProductionPersonItem]:
        rows = [
            DashboardProductionPersonItem(
                person_name=str(data["person_name"] or "-"),
                production_count=int(data["production_count"] or 0),
                total_weight_kg=round(float(data["total_weight_kg"] or 0.0), 2),
            )
            for data in source.values()
        ]
        rows.sort(
            key=lambda item: (
                -item.total_weight_kg,
                -item.production_count,
                _normalize_text(item.person_name),
            )
        )
        return rows[:8]

    return _build_rows(operators_stats), _build_rows(helpers_stats)


def _comparison_period_windows(
    now: datetime | None = None,
) -> dict[str, tuple[datetime, datetime]]:
    local_now = _to_local_datetime(now or datetime.now(_LOCAL_TIMEZONE)) or datetime.now(_LOCAL_TIMEZONE)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "monthly": (_month_start(local_now), local_now),
        "weekly": (today_start - timedelta(days=6), local_now),
        "daily": (today_start, local_now),
    }


def _new_kg_comparison_entry(label: str) -> dict[str, object]:
    return {
        "label": label,
        "monthly_kg": 0.0,
        "weekly_kg": 0.0,
        "daily_kg": 0.0,
    }


def _new_count_kg_comparison_entry(label: str) -> dict[str, object]:
    return {
        "label": label,
        "monthly_count": 0,
        "monthly_kg": 0.0,
        "weekly_count": 0,
        "weekly_kg": 0.0,
        "daily_count": 0,
        "daily_kg": 0.0,
    }


def _accumulate_kg_comparison(
    entry: dict[str, object],
    value_at: object,
    weight: float,
    periods: dict[str, tuple[datetime, datetime]],
) -> None:
    local_value = _to_local_datetime(value_at)
    if local_value is None:
        return

    for period_key, (period_start, period_end) in periods.items():
        if period_start <= local_value < period_end:
            field_name = f"{period_key}_kg"
            entry[field_name] = float(entry.get(field_name) or 0.0) + weight


def _accumulate_count_kg_comparison(
    entry: dict[str, object],
    value_at: object,
    weight: float,
    periods: dict[str, tuple[datetime, datetime]],
) -> None:
    local_value = _to_local_datetime(value_at)
    if local_value is None:
        return

    for period_key, (period_start, period_end) in periods.items():
        if period_start <= local_value < period_end:
            count_field = f"{period_key}_count"
            kg_field = f"{period_key}_kg"
            entry[count_field] = int(entry.get(count_field) or 0) + 1
            entry[kg_field] = float(entry.get(kg_field) or 0.0) + weight


def _build_kg_comparison_rows(
    rows: dict[object, dict[str, object]],
    *,
    limit: int | None = None,
) -> list[DashboardKgComparisonItem]:
    items = [
        DashboardKgComparisonItem(
            label=str(data.get("label") or "-"),
            monthly_kg=round(float(data.get("monthly_kg") or 0.0), 2),
            weekly_kg=round(float(data.get("weekly_kg") or 0.0), 2),
            daily_kg=round(float(data.get("daily_kg") or 0.0), 2),
        )
        for data in rows.values()
    ]
    items.sort(
        key=lambda item: (
            -item.monthly_kg,
            -item.weekly_kg,
            -item.daily_kg,
            _normalize_text(item.label),
        )
    )
    if limit is not None:
        return items[:limit]
    return items


def _build_count_kg_comparison_rows(
    rows: dict[object, dict[str, object]],
    *,
    limit: int | None = None,
) -> list[DashboardCountKgComparisonItem]:
    items = [
        DashboardCountKgComparisonItem(
            label=str(data.get("label") or "-"),
            monthly_count=int(data.get("monthly_count") or 0),
            monthly_kg=round(float(data.get("monthly_kg") or 0.0), 2),
            weekly_count=int(data.get("weekly_count") or 0),
            weekly_kg=round(float(data.get("weekly_kg") or 0.0), 2),
            daily_count=int(data.get("daily_count") or 0),
            daily_kg=round(float(data.get("daily_kg") or 0.0), 2),
        )
        for data in rows.values()
    ]
    items.sort(
        key=lambda item: (
            -item.monthly_kg,
            -item.monthly_count,
            -item.weekly_kg,
            -item.weekly_count,
            -item.daily_kg,
            -item.daily_count,
            _normalize_text(item.label),
        )
    )
    if limit is not None:
        return items[:limit]
    return items


def _build_production_destination_comparison(
    reqs: list[Requisition],
    now: datetime | None = None,
    *,
    destination: str = "",
) -> list[DashboardKgComparisonItem]:
    periods = _comparison_period_windows(now)
    stats: dict[str, dict[str, object]] = {}

    for req in reqs:
        weight = float(req.weight or 0.0)
        for cycle in _all_finished_cycles(req):
            cycle_destination = _canonical_destination(cycle.get("target"))
            if not cycle_destination:
                continue
            if destination and cycle_destination != destination:
                continue
            entry = stats.setdefault(cycle_destination, _new_kg_comparison_entry(cycle_destination))
            _accumulate_kg_comparison(entry, cycle.get("finished_at"), weight, periods)

    return _build_kg_comparison_rows(stats)


def _build_production_machine_comparison(
    reqs: list[Requisition],
    now: datetime | None = None,
    *,
    destination: str = "",
    limit: int | None = None,
) -> list[DashboardKgComparisonItem]:
    periods = _comparison_period_windows(now)
    stats: dict[tuple[str, str], dict[str, object]] = {}

    for req in reqs:
        weight = float(req.weight or 0.0)
        for cycle in _all_finished_cycles(req):
            cycle_destination = _canonical_destination(cycle.get("target"))
            machine_name = _normalize_machine_name(cycle.get("machine"))
            if not machine_name:
                continue
            if destination and cycle_destination != destination:
                continue
            label = machine_name
            if not destination and cycle_destination:
                label = f"{cycle_destination} - {machine_name}"
            entry = stats.setdefault(
                (cycle_destination, machine_name),
                _new_kg_comparison_entry(label),
            )
            _accumulate_kg_comparison(entry, cycle.get("finished_at"), weight, periods)

    return _build_kg_comparison_rows(stats, limit=limit)


def _build_vendor_comparison(
    reqs: list[Requisition],
    now: datetime | None = None,
    *,
    destination: str = "",
    limit: int | None = None,
) -> list[DashboardCountKgComparisonItem]:
    periods = _comparison_period_windows(now)
    stats: dict[tuple[int, str], dict[str, object]] = {}

    for req in reqs:
        if destination and _current_production_destination(req) != destination:
            continue
        vendor_name = (req.vendor_name or "").strip() or "Sem vendedor"
        vendor_key = (int(req.vendor_id or 0), vendor_name)
        emission_at = _parse_local_emission_datetime(req.emission_date) or _to_local_datetime(req.created_at)
        entry = stats.setdefault(vendor_key, _new_count_kg_comparison_entry(vendor_name))
        _accumulate_count_kg_comparison(entry, emission_at, float(req.weight or 0.0), periods)

    return _build_count_kg_comparison_rows(stats, limit=limit)


def _build_people_comparison(
    reqs: list[Requisition],
    people_key: str,
    now: datetime | None = None,
    *,
    destination: str = "",
    limit: int | None = None,
) -> list[DashboardCountKgComparisonItem]:
    periods = _comparison_period_windows(now)
    stats: dict[str, dict[str, object]] = {}

    for req in reqs:
        weight = float(req.weight or 0.0)
        for cycle in _all_finished_cycles(req):
            cycle_destination = _canonical_destination(cycle.get("target"))
            if destination and cycle_destination != destination:
                continue
            finished_at = cycle.get("finished_at")
            for person_name in _clean_operator_names(list(cycle.get(people_key) or [])):
                entry = stats.setdefault(person_name, _new_count_kg_comparison_entry(person_name))
                _accumulate_count_kg_comparison(entry, finished_at, weight, periods)

    return _build_count_kg_comparison_rows(stats, limit=limit)


def _build_management_dashboard(
    reqs: list[Requisition],
    machines: list[ProductionMachine],
    *,
    ar_period: str = "30d",
    industria_period: str = "30d",
    performance_period: str = "month",
    performance_date_start: date | None = None,
    performance_date_end: date | None = None,
    performance_destination: str = "",
    comparison_destination: str = "",
    people_period: str = "30d",
    people_destination: str = "",
) -> ManagementDashboardResponse:
    now = datetime.utcnow()
    generated_at = _to_local_datetime(now) or datetime.now(_LOCAL_TIMEZONE)
    today = now.date()
    one_hour_ago = now - timedelta(hours=1)

    receipt_alerts: list[DashboardReceiptAlertItem] = []
    recent_requisitions: list[DashboardRecentRequisitionItem] = []
    completion_durations: list[int] = []

    pedidos_em_producao = 0
    pedidos_em_atraso = 0
    pedidos_finalizados_hoje = 0
    producao_pinheiro_industria = 0
    producao_ar = 0
    requisicoes_feitas_no_dia = 0

    for req in reqs:
        destination = _current_production_destination(req)
        is_active_production = req.status in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
            RequisitionStatus.AGUARDANDO_NA_FILA,
            RequisitionStatus.EM_PRODUCAO,
        )

        if req.status in (
            RequisitionStatus.AGUARDANDO_NA_FILA,
            RequisitionStatus.EM_PRODUCAO,
        ):
            pedidos_em_producao += 1

        if is_active_production and destination == _DESTINATION_PINHEIRO:
            producao_pinheiro_industria += 1
        if is_active_production and destination == _DESTINATION_AR:
            producao_ar += 1

        if req.created_at and req.created_at.date() == today:
            requisicoes_feitas_no_dia += 1

        if (
            req.delivery_date
            and req.delivery_date < today
            and _is_open_requisition(req)
        ):
            pedidos_em_atraso += 1

        latest_send_event = _latest_production_event(req, _PROD_SEND)
        if (
            req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO
            and latest_send_event
            and latest_send_event["changed_at"]
            and latest_send_event["changed_at"] <= one_hour_ago
        ):
            waiting_minutes = max(
                0,
                int((now - latest_send_event["changed_at"]).total_seconds() // 60),
            )
            receipt_alerts.append(
                DashboardReceiptAlertItem(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    destination=latest_send_event["target"] or destination or "-",
                    sent_at=latest_send_event["changed_at"],
                    waiting_minutes=waiting_minutes,
                )
            )

        for cycle in _all_finished_cycles(req):
            completion_durations.append(cycle["production_time_seconds"])
            finished_at = cycle.get("finished_at")
            if isinstance(finished_at, datetime) and finished_at.date() == today:
                pedidos_finalizados_hoje += 1

        recent_requisitions.append(
            DashboardRecentRequisitionItem(
                id=req.id,
                ped_number=req.ped_number,
                client_name=req.client_name,
                vendor_name=req.vendor_name,
                status=req.status,
                emission_date=req.emission_date,
                delivery_date=req.delivery_date,
                destination=destination or None,
            )
        )

    iar_general = _build_iar_general(
        reqs,
        performance_period,
        performance_date_start,
        performance_date_end,
        performance_destination,
        now,
    )
    top_vendors = _build_top_vendor_rows(
        reqs,
        performance_period,
        performance_date_start,
        performance_date_end,
        performance_destination,
        now,
    )
    top_operators, top_helpers = _build_top_production_people_rows(
        reqs,
        people_period,
        people_destination,
        now,
    )
    insights = DashboardInsightsResponse(
        production_kg_by_destination=_build_production_destination_comparison(
            reqs,
            now,
            destination=comparison_destination,
        ),
        production_kg_by_machine=_build_production_machine_comparison(
            reqs,
            now,
            destination=comparison_destination,
        ),
        requisitions_kg_by_vendor=_build_vendor_comparison(
            reqs,
            now,
            destination=comparison_destination,
        ),
        requisitions_kg_by_operator=_build_people_comparison(
            reqs,
            "operators",
            now,
            destination=comparison_destination,
        ),
        requisitions_kg_by_helper=_build_people_comparison(
            reqs,
            "helpers",
            now,
            destination=comparison_destination,
        ),
    )

    receipt_alerts.sort(key=lambda item: item.waiting_minutes, reverse=True)
    recent_requisitions.sort(key=lambda item: item.emission_date, reverse=True)

    average_seconds = None
    if completion_durations:
        average_seconds = int(sum(completion_durations) / len(completion_durations))

    top_machines_industria = _build_machine_usage_rows(
        reqs,
        machines,
        _DESTINATION_PINHEIRO,
        industria_period,
        now,
    )
    top_machines_ar = _build_machine_usage_rows(
        reqs,
        machines,
        _DESTINATION_AR,
        ar_period,
        now,
    )

    return ManagementDashboardResponse(
        generated_at=generated_at,
        stats=DashboardStatsResponse(
            pedidos_em_producao=pedidos_em_producao,
            pedidos_em_atraso=pedidos_em_atraso,
            pedidos_finalizados_hoje=pedidos_finalizados_hoje,
            producao_pinheiro_industria=producao_pinheiro_industria,
            producao_ar=producao_ar,
            requisicoes_feitas_no_dia=requisicoes_feitas_no_dia,
            pedidos_sem_confirmacao_1h=len(receipt_alerts),
            tempo_medio_finalizacao_segundos=average_seconds,
        ),
        iar_general=iar_general,
        insights=insights,
        top_vendors=top_vendors,
        top_operators=top_operators,
        top_helpers=top_helpers,
        receipt_alerts=receipt_alerts[:10],
        recent_requisitions=recent_requisitions[:12],
        top_machines_ar=top_machines_ar,
        top_machines_industria=top_machines_industria,
    )


def _resolve_storage_root() -> Path:
    if settings.DATABASE_TYPE == "sqlite" and settings.DATABASE_URL.startswith("sqlite:///"):
        raw_path = settings.DATABASE_URL.replace("sqlite:///", "", 1)
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = (Path.cwd() / db_path).resolve()
        return db_path.parent

    shared_root = Path(settings.SHARED_FOLDER_PATH)
    if not shared_root.is_absolute():
        shared_root = (Path.cwd() / shared_root).resolve()
    return shared_root if shared_root.exists() else Path.cwd()


def _available_space_bytes() -> int | None:
    root = _resolve_storage_root()
    try:
        return shutil.disk_usage(root).free
    except (FileNotFoundError, OSError, PermissionError):
        return None


def _is_backup_candidate(path: Path) -> bool:
    if not path.is_file():
        return False

    name = path.name.casefold()
    if "backup" in name or "bkp" in name:
        return True

    return path.suffix.casefold() in {".bak", ".backup", ".dump", ".zip", ".7z"}


def _find_latest_backup_at() -> datetime | None:
    # A pasta configurada em BACKUP_FOLDER é o destino real do pg_dump
    # (backup_service.run_backup). Precisa ser o primeiro local verificado;
    # caso contrário backups já realizados nunca são detectados.
    roots: list[Path] = []
    if settings.BACKUP_FOLDER:
        roots.append(Path(settings.BACKUP_FOLDER))
    roots.extend([_resolve_storage_root(), Path.cwd()])

    latest_timestamp = 0.0

    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)

        if not root.exists() or not root.is_dir():
            continue

        scan_dirs = [root]
        for folder_name in ("backup", "backups", "bkp"):
            candidate_dir = root / folder_name
            if candidate_dir.exists() and candidate_dir.is_dir():
                scan_dirs.append(candidate_dir)

        for scan_dir in scan_dirs:
            try:
                for item in scan_dir.iterdir():
                    if _is_backup_candidate(item):
                        latest_timestamp = max(latest_timestamp, item.stat().st_mtime)
            except (FileNotFoundError, PermissionError, OSError):
                continue

    if latest_timestamp <= 0:
        return None

    return datetime.fromtimestamp(latest_timestamp)


def _database_connected(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _logged_users_snapshot(db: Session) -> list[TechnicalPanelLoggedUserResponse]:
    user_ids = connected_user_ids()
    if not user_ids:
        return []

    users = (
        db.query(User)
        .filter(User.id.in_(user_ids))
        .order_by(User.name.asc())
        .all()
    )
    return [
        TechnicalPanelLoggedUserResponse(
            id=user.id,
            name=user.name,
            last_login_at=user.last_login_at,
        )
        for user in users
    ]


@router.get("/technical-panel/summary", response_model=TechnicalPanelResponse)
def get_technical_panel_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    stats = runtime_snapshot()
    logged_users = _logged_users_snapshot(db)

    requisitions_today = (
        db.query(Requisition)
        .filter(Requisition.created_at >= today_start)
        .count()
    )

    return TechnicalPanelResponse(
        generated_at=now,
        stats=TechnicalPanelStatsResponse(
            system_online=True,
            connected_users=len(logged_users),
            requisitions_today=requisitions_today,
            average_response_ms=stats.get("average_response_ms"),
            last_backup_at=_find_latest_backup_at(),
            database_connected=_database_connected(db),
            available_space_bytes=_available_space_bytes(),
            error_count_today=int(stats.get("error_count_today") or 0),
        ),
        logged_users=logged_users,
    )


@router.get("/", response_model=List[RequisitionListItem])
def list_requisitions(
    req_status: Optional[RequisitionStatus] = Query(None, alias="status"),
    client_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    vendor_search: Optional[str] = None,
    production_destination: Optional[str] = None,
    production_machine: Optional[str] = None,
    production_operator: Optional[str] = None,
    invoiced: Optional[bool] = None,
    emission_date_start: Optional[date] = None,
    emission_date_end: Optional[date] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Requisition).options(*_LIST_LOAD_OPTS)

    if req_status:
        q = q.filter(Requisition.status == req_status)
    if client_id:
        q = q.filter(Requisition.client_id == client_id)
    if vendor_id:
        q = q.filter(Requisition.vendor_id == vendor_id)
    if vendor_search and vendor_search.strip():
        vendor_term = f"%{vendor_search.strip()}%"
        q = q.join(Requisition.vendor).filter(or_(
            User.name.ilike(vendor_term),
            User.code.ilike(vendor_term),
        ))
    if search:
        search_term = f"%{search.strip()}%"
        q = q.join(Requisition.client).filter(or_(
            Requisition.ped_number.ilike(search_term),
            Requisition.obra.ilike(search_term),
            Client.name.ilike(search_term),
            Client.code.ilike(search_term),
        ))

    # Vendedor e gerente só veem as próprias requisições
    reqs = q.order_by(Requisition.emission_date.desc(), Requisition.created_at.desc()).all()
    visible = _filter_requisitions_for_user(reqs, current_user)

    if emission_date_start or emission_date_end:
        visible = [
            req for req in visible
            if _matches_emission_period(req, emission_date_start, emission_date_end)
        ]

    if production_destination:
        normalized_destination = _canonical_destination(production_destination)
        visible = [
            req for req in visible
            if _current_production_destination(req) == normalized_destination
        ]

    if production_machine:
        machine_key = _normalize_text(production_machine)
        visible = [
            req for req in visible
            if _normalize_text(_history_production_machine(req)) == machine_key
        ]

    if production_operator:
        operator_key = _normalize_text(production_operator)
        visible = [
            req for req in visible
            if any(
                _normalize_text(name) == operator_key
                for name in (
                    _history_production_operator_names(req)
                    + _history_production_helper_names(req)
                )
            )
        ]

    if invoiced is not None:
        visible = [
            req for req in visible
            if (req.status == RequisitionStatus.FATURADO) == invoiced
        ]

    paginated = visible[skip:skip + limit]
    for req in paginated:
        setattr(
            req,
            "production_destination_display",
            _current_production_destination(req) or None,
        )
        setattr(
            req,
            "production_machine_display",
            _history_production_machine(req) or None,
        )
        operator_names = _history_production_operator_names(req)
        helper_names = _history_production_helper_names(req)
        setattr(req, "production_operator_names", operator_names)
        setattr(req, "production_operator_display", ", ".join(operator_names) or None)
        setattr(req, "production_helper_names", helper_names)
        setattr(req, "production_helper_display", ", ".join(helper_names) or None)
        setattr(req, "production_sent_at", _history_production_sent_at(req))
        setattr(req, "production_finished_at", _history_production_finished_at(req))
        setattr(req, "production_status", _history_production_status(req))
        setattr(req, "invoiced", req.status == RequisitionStatus.FATURADO)
        setattr(req, "cancel_reason", _cancel_reason_for(req))
    return paginated


@router.get("/history/rows", response_model=List[RequisitionListItem])
def list_requisition_history_rows(
    req_status: Optional[RequisitionStatus] = Query(None, alias="status"),
    client_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    vendor_search: Optional[str] = None,
    production_destination: Optional[str] = None,
    production_machine: Optional[str] = None,
    production_operator: Optional[str] = None,
    invoiced: Optional[bool] = None,
    emission_date_start: Optional[date] = None,
    emission_date_end: Optional[date] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Requisition).options(*_LIST_LOAD_OPTS)

    if client_id:
        q = q.filter(Requisition.client_id == client_id)
    if vendor_id:
        q = q.filter(Requisition.vendor_id == vendor_id)
    if vendor_search and vendor_search.strip():
        vendor_term = f"%{vendor_search.strip()}%"
        q = q.join(Requisition.vendor).filter(
            or_(
                User.name.ilike(vendor_term),
                User.code.ilike(vendor_term),
            )
        )
    if search:
        search_term = f"%{search.strip()}%"
        q = q.join(Requisition.client).filter(
            or_(
                Requisition.ped_number.ilike(search_term),
                Requisition.obra.ilike(search_term),
                Client.name.ilike(search_term),
                Client.code.ilike(search_term),
            )
        )

    reqs = q.order_by(Requisition.emission_date.desc(), Requisition.created_at.desc()).all()
    visible = _filter_requisitions_for_user(reqs, current_user)

    rows: list[dict] = []
    for req in visible:
        if _has_production_splits(req):
            remaining_weight = _remaining_requisition_weight(req)
            if remaining_weight > 0 or req.status == RequisitionStatus.CANCELADA:
                rows.append(
                    _history_row_from_requisition(
                        req,
                        weight_value=remaining_weight if remaining_weight > 0 else float(req.weight or 0.0),
                        include_production_details=False,
                    )
                )
            rows.extend(
                _history_row_from_split(req, split)
                for split in _sorted_requisition_splits(req)
            )
        else:
            rows.append(_history_row_from_requisition(req))

    if req_status:
        expected_status = getattr(req_status, "value", req_status)
        rows = [row for row in rows if str(row.get("status") or "") == str(expected_status)]

    if emission_date_start or emission_date_end:
        rows = [
            row
            for row in rows
            if (
                (local_dt := _parse_local_emission_datetime(row.get("emission_date"))) is not None
                and (not emission_date_start or local_dt.date() >= emission_date_start)
                and (not emission_date_end or local_dt.date() <= emission_date_end)
            )
        ]

    if production_destination:
        normalized_destination = _canonical_destination(production_destination)
        rows = [
            row
            for row in rows
            if _canonical_destination(
                row.get("production_destination_display") or row.get("production_destination") or ""
            ) == normalized_destination
        ]

    if production_machine:
        machine_key = _normalize_text(production_machine)
        rows = [
            row
            for row in rows
            if _normalize_text(
                row.get("production_machine_display") or row.get("production_machine") or ""
            ) == machine_key
        ]

    if production_operator:
        operator_key = _normalize_text(production_operator)
        rows = [
            row
            for row in rows
            if any(
                _normalize_text(name) == operator_key
                for name in (
                    list(row.get("production_operator_names") or [])
                    + list(row.get("production_helper_names") or [])
                )
            )
        ]

    if invoiced is not None:
        rows = [row for row in rows if bool(row.get("invoiced")) == invoiced]

    rows.sort(
        key=lambda row: (
            row.get("emission_date") or datetime.min,
            row.get("created_at") or datetime.min,
            int(row.get("split_sequence") or 0),
        ),
        reverse=True,
    )
    return rows[skip:skip + limit]


def _check_invoice_alerts(db: Session) -> None:
    """Verifica alertas de faturamento pendentes e envia notificações SSE."""
    notifications = ensure_pending_invoice_notifications(db)
    notifications += ensure_delivery_deadline_notifications(db)
    if notifications:
        db.commit()
        push_all(notifications)


@router.get("/dashboard/summary", response_model=ManagementDashboardResponse)
def get_management_dashboard(
    ar_period: str = Query("30d"),
    industria_period: str = Query("30d"),
    performance_period: str = Query("month"),
    performance_date_start: date | None = Query(None),
    performance_date_end: date | None = Query(None),
    performance_destination: str = Query(""),
    comparison_destination: str = Query(""),
    people_period: str = Query("30d"),
    people_destination: str = Query(""),
    db: Session = Depends(get_db),
    _: User = Depends(require_manager_or_admin),
):
    _check_invoice_alerts(db)
    normalized_ar_period = _normalize_dashboard_period(ar_period)
    normalized_industria_period = _normalize_dashboard_period(industria_period)
    normalized_performance_period = _normalize_performance_dashboard_period(performance_period)
    normalized_performance_destination = _normalize_dashboard_destination(performance_destination)
    normalized_comparison_destination = _normalize_dashboard_destination(comparison_destination)
    normalized_people_period = _normalize_dashboard_period(people_period)
    normalized_people_destination = _normalize_dashboard_destination(people_destination)

    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.desc())
        .all()
    )
    machines = (
        db.query(ProductionMachine)
        .order_by(
            ProductionMachine.destination.asc(),
            ProductionMachine.sort_order.asc(),
            ProductionMachine.id.asc(),
        )
        .all()
    )
    return _build_management_dashboard(
        reqs,
        machines,
        ar_period=normalized_ar_period,
        industria_period=normalized_industria_period,
        performance_period=normalized_performance_period,
        performance_date_start=performance_date_start,
        performance_date_end=performance_date_end,
        performance_destination=normalized_performance_destination,
        comparison_destination=normalized_comparison_destination,
        people_period=normalized_people_period,
        people_destination=normalized_people_destination,
    )


@router.get("/order-center/summary", response_model=OrderCenterResponse)
def get_order_center(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_order_center_access),
):
    _check_invoice_alerts(db)

    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.desc())
        .all()
    )
    return _build_order_center(_filter_requisitions_for_user(reqs, current_user))


@router.get("/deliveries/summary", response_model=DeliveryCenterResponse)
def get_delivery_center(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_order_center_access),
):
    _check_invoice_alerts(db)

    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.desc())
        .all()
    )
    return _build_delivery_center(_filter_requisitions_for_user(reqs, current_user))


@router.get("/production/summary", response_model=ProductionDestinationSummaryResponse)
def get_production_summary(
    destination: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized_destination = _canonical_destination(destination)
    _ensure_destination_access(current_user, normalized_destination)

    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.asc(), Requisition.id.asc())
        .all()
    )
    visible = _filter_requisitions_for_user(reqs, current_user)
    machines = (
        db.query(ProductionMachine)
        .options(selectinload(ProductionMachine.operators))
        .filter(ProductionMachine.destination == normalized_destination)
        .order_by(func.lower(ProductionMachine.name).asc(), ProductionMachine.id.asc())
        .all()
    )
    return _build_production_summary(visible, machines, normalized_destination)


@router.get("/production/machines", response_model=List[str])
def list_production_machines(
    destination: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    normalized_destination = _canonical_destination(destination)
    machines = (
        db.query(ProductionMachine)
        .filter(ProductionMachine.destination == normalized_destination)
        .order_by(func.lower(ProductionMachine.name).asc(), ProductionMachine.id.asc())
        .all()
    )
    return [
        _normalize_machine_name(machine.name)
        for machine in machines
        if _normalize_machine_name(machine.name)
    ]


@router.post(
    "/{req_id}/production-splits",
    response_model=ProductionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_production_split(
    req_id: int,
    data: ProductionSplitCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para atualizar esta requisicao")

    if req.status in (RequisitionStatus.CANCELADA, RequisitionStatus.FATURADO):
        raise HTTPException(status_code=400, detail="A requisicao nao permite novo desmembramento")
    if req.status not in (
        RequisitionStatus.AGUARDANDO_RECEBIMENTO,
        RequisitionStatus.AGUARDANDO_NA_FILA,
        RequisitionStatus.EM_PRODUCAO,
    ):
        raise HTTPException(status_code=400, detail="A requisicao nao esta disponivel para envio a maquina")
    if (
        not _has_production_splits(req)
        and req.status == RequisitionStatus.EM_PRODUCAO
        and _current_production_machine(req)
    ):
        raise HTTPException(status_code=400, detail="A requisicao inteira ja esta vinculada a uma maquina")

    normalized_destination = _canonical_destination(data.destination)
    _ensure_destination_access(current_user, normalized_destination)

    current_destination = _current_production_destination(req)
    if current_destination and current_destination != normalized_destination:
        raise HTTPException(
            status_code=400,
            detail="A requisicao ja esta vinculada a outra producao",
        )

    weight_value = round(float(data.weight or 0.0), 3)
    if weight_value <= 0:
        raise HTTPException(status_code=400, detail="Informe um peso maior que zero")

    remaining_weight = _remaining_requisition_weight(req) if _has_production_splits(req) else round(float(req.weight or 0.0), 3)
    if weight_value > remaining_weight:
        raise HTTPException(
            status_code=400,
            detail=f"O peso informado excede o saldo pendente de {remaining_weight:.3f} kg",
        )

    machine_name = _normalize_machine_name(data.machine_name)
    if not machine_name:
        raise HTTPException(status_code=400, detail="Informe a maquina de destino")

    operators = _clean_operator_names(data.operators)
    helpers = _clean_operator_names(data.helpers)
    if not operators:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um operador")

    if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
        _ensure_waiting_receipt_fifo(
            db,
            current_user,
            normalized_destination,
            req.id,
        )
    elif req.status == RequisitionStatus.AGUARDANDO_NA_FILA or (
        req.status == RequisitionStatus.EM_PRODUCAO
        and _has_production_splits(req)
        and _remaining_requisition_weight(req) > 0
    ):
        _ensure_waiting_queue_fifo_for_requisition(
            db,
            current_user,
            normalized_destination,
            req.id,
        )

    split = RequisitionProductionSplit(
        requisition=req,
        sequence=max((int(item.sequence or 0) for item in _sorted_requisition_splits(req)), default=0) + 1,
        weight=weight_value,
        status=RequisitionStatus.EM_PRODUCAO,
        destination=normalized_destination,
        production_machine=machine_name,
    )
    db.add(split)
    db.flush()

    note = _compose_production_note(
        _PROD_STARTED,
        normalized_destination,
        machine=machine_name,
        operators=operators,
        helpers=helpers,
    )
    db.add(
        StatusHistory(
            requisition_id=req.id,
            production_split_id=split.id,
            old_status=RequisitionStatus.AGUARDANDO_NA_FILA.value,
            new_status=RequisitionStatus.EM_PRODUCAO.value,
            changed_by_id=current_user.id,
            note=note,
        )
    )

    req.production_destination = normalized_destination
    parent_new_status = _sync_requisition_after_splits(
        req,
        db,
        current_user,
        note=f"Desmembramento {split.sequence:02d} criado para {weight_value:.3f} kg.",
    )

    notifications: list = []
    if parent_new_status == RequisitionStatus.FATURADO:
        notifications.extend(build_vendor_event(db, req, "faturado"))

    db.commit()
    push_all(notifications)
    return _production_split_item(
        req,
        split,
        machine_name=machine_name,
        operator_names=operators,
        helper_names=helpers,
        production_started_at=datetime.utcnow(),
    )


@router.patch(
    "/production-splits/{split_id}/status",
    response_model=ProductionItemResponse,
)
def update_production_split_status(
    split_id: int,
    data: ProductionSplitStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    split = _get_split_or_404(db, split_id)
    req = split.requisition
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para atualizar esta requisicao")

    requested_status = _coerce_requisition_status(data.status)
    prod_event = _parse_production_note(data.note)
    if not prod_event:
        raise HTTPException(status_code=400, detail="Informe o evento operacional da parcela")

    normalized_destination = _canonical_destination(prod_event.get("target") or split.destination or req.production_destination or "")
    _ensure_destination_access(current_user, normalized_destination)
    split.destination = normalized_destination

    old_status = split.status
    action = prod_event["action"]
    machine_name = _normalize_machine_name(prod_event.get("machine"))
    bypass_fifo = bool(prod_event.get("transfer"))

    if action == _PROD_STARTED:
        if requested_status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(status_code=400, detail="Status invalido para iniciar a parcela")
        if split.status not in (RequisitionStatus.AGUARDANDO_NA_FILA, RequisitionStatus.EM_PRODUCAO):
            raise HTTPException(status_code=400, detail="A parcela nao pode voltar para producao")
        if not machine_name:
            raise HTTPException(status_code=400, detail="Informe a maquina de destino")
        operators = _clean_operator_names(prod_event.get("operators") or [])
        helpers = _clean_operator_names(prod_event.get("helpers") or [])
        if not operators:
            raise HTTPException(status_code=400, detail="Selecione pelo menos um operador")
        if split.status == RequisitionStatus.AGUARDANDO_NA_FILA and not bypass_fifo:
            _ensure_waiting_queue_fifo_for_split(
                db,
                current_user,
                normalized_destination,
                split.id,
            )
        split.status = RequisitionStatus.EM_PRODUCAO
        split.production_machine = machine_name
    elif action == _PROD_RETURNED_QUEUE:
        if requested_status != RequisitionStatus.AGUARDANDO_NA_FILA:
            raise HTTPException(status_code=400, detail="Status invalido para devolver a parcela")
        if split.status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(status_code=400, detail="Somente parcelas em producao podem voltar para fila")
        operators = []
        helpers = []
        split.status = RequisitionStatus.AGUARDANDO_NA_FILA
        split.production_machine = None
    elif action == _PROD_FINISHED:
        if requested_status != RequisitionStatus.FATURADO:
            raise HTTPException(status_code=400, detail="Status invalido para finalizar a parcela")
        if split.status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(status_code=400, detail="Somente parcelas em producao podem ser finalizadas")
        operators = []
        helpers = []
        split.status = RequisitionStatus.FATURADO
        split.production_machine = None
    else:
        raise HTTPException(status_code=400, detail="Evento operacional da parcela nao suportado")

    db.add(
        StatusHistory(
            requisition_id=req.id,
            production_split_id=split.id,
            old_status=getattr(old_status, "value", old_status),
            new_status=getattr(split.status, "value", split.status),
            changed_by_id=current_user.id,
            note=data.note,
        )
    )

    parent_old_status = req.status
    parent_new_status = _sync_requisition_after_splits(
        req,
        db,
        current_user,
        note=f"Desmembramento {split.sequence:02d} atualizado para {getattr(split.status, 'value', split.status)}.",
    )

    notifications: list = []
    if parent_old_status != RequisitionStatus.FATURADO and parent_new_status == RequisitionStatus.FATURADO:
        notifications.extend(build_vendor_event(db, req, "faturado"))

    db.commit()
    push_all(notifications)

    response_machine = machine_name or _split_current_machine(split)
    started_event = _split_latest_production_event(split, _PROD_STARTED, _PROD_RECEIVED)
    if action == _PROD_STARTED:
        response_operators = operators
        response_helpers = helpers
    else:
        latest_cycle = _split_all_finished_cycles(split)
        latest_finished = latest_cycle[-1] if latest_cycle else None
        response_operators = list((latest_finished or {}).get("operators") or (started_event or {}).get("operators") or [])
        response_helpers = list((latest_finished or {}).get("helpers") or (started_event or {}).get("helpers") or [])

    return _production_split_item(
        req,
        split,
        waiting_since=datetime.utcnow() if split.status == RequisitionStatus.AGUARDANDO_NA_FILA else None,
        machine_name=response_machine,
        operator_names=response_operators,
        helper_names=response_helpers,
        production_started_at=(started_event or {}).get("changed_at"),
    )


@router.patch(
    "/production/machines/{machine_id}/status",
    response_model=ProductionMachineStatusResponse,
)
def update_production_machine_status(
    machine_id: int,
    data: ProductionMachineStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    machine = (
        db.query(ProductionMachine)
        .filter(ProductionMachine.id == machine_id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")

    _ensure_destination_access(current_user, machine.destination)

    machine.status = data.status
    machine.updated_by_id = current_user.id
    machine.updated_at = datetime.utcnow()

    notifications = build_machine_status_event(db, machine, current_user)
    db.commit()
    push_all(notifications)

    return ProductionMachineStatusResponse(
        id=machine.id,
        destination=machine.destination,
        name=_normalize_machine_name(machine.name),
        status=machine.status,
        updated_at=machine.updated_at,
    )


@router.post("/", response_model=RequisitionResponse, status_code=status.HTTP_201_CREATED)
def create_requisition(
    data: RequisitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    items_data = data.items
    _ensure_unique_ped_number(db, data.ped_number)
    _ensure_delivery_within_min(data.delivery_date, current_user)
    req = Requisition(
        **data.model_dump(exclude={"items", "weight", "canvas_json"}),
        vendor_id=current_user.id,
        weight=_sum_item_weights(items_data),
    )
    db.add(req)
    db.flush()

    for item in items_data:
        db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))

    # Canvas (desenho) gravado na MESMA transação — atômico com a requisição.
    db.add(CanvasData(
        requisition_id=req.id,
        json_data=normalize_canvas_json_text(data.canvas_json) or "{}",
    ))
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=None,
        new_status=RequisitionStatus.EM_ANDAMENTO,
        changed_by_id=current_user.id,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="CREATE",
        changed_by=current_user,
        changes={"ped_number": data.ped_number, "client_id": data.client_id},
    )
    _commit_or_ped_conflict(db, data.ped_number)
    return _get_or_404(db, req.id)


@router.get("/{req_id}", response_model=RequisitionResponse)
def get_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    if not _can_view_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar esta requisição")
    setattr(req, "production_destination_display", _current_production_destination(req) or None)
    setattr(req, "production_machine_display", _history_production_machine(req) or None)
    operator_names = _history_production_operator_names(req)
    helper_names = _history_production_helper_names(req)
    setattr(req, "production_operator_names", operator_names)
    setattr(req, "production_operator_display", ", ".join(operator_names) or None)
    setattr(req, "production_helper_names", helper_names)
    setattr(req, "production_helper_display", ", ".join(helper_names) or None)
    setattr(req, "production_sent_at", _history_production_sent_at(req))
    setattr(req, "production_finished_at", _history_production_finished_at(req))
    setattr(req, "production_status", _history_production_status(req))
    setattr(req, "invoiced", req.status == RequisitionStatus.FATURADO)
    setattr(req, "cancel_reason", _cancel_reason_for(req))
    return req


@router.patch("/{req_id}", response_model=RequisitionResponse)
def update_requisition(
    req_id: int,
    data: RequisitionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta requisição")
    _ensure_not_stale(req, data.expected_updated_at)
    _ensure_editable(req)
    ped_number = data.ped_number if data.ped_number is not None else req.ped_number
    _ensure_unique_ped_number(db, ped_number, exclude_req_id=req.id)

    scalar_update = data.model_dump(
        exclude_unset=True,
        exclude={"items", "weight", "canvas_json", "expected_updated_at"},
    )
    if "delivery_date" in scalar_update:
        _ensure_delivery_within_min(scalar_update["delivery_date"], current_user)
    tracked = ["ped_number", "delivery_date", "os_number", "obra", "obs",
               "retirada", "entrega", "delivery_address", "phone"]
    changes = diff_fields(req, scalar_update, tracked)

    for k, v in scalar_update.items():
        setattr(req, k, v)

    if data.items is not None:
        old_count = len(req.items)
        for item in list(req.items):
            db.delete(item)
        db.flush()
        for item in data.items:
            db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))
        req.weight = _sum_item_weights(data.items)
        new_count = len(data.items)
        if old_count != new_count:
            changes["items"] = {"old": f"{old_count} item(s)", "new": f"{new_count} item(s)"}
    elif data.weight is not None:
        req.weight = data.weight

    # Canvas (desenho) na MESMA transação — atômico com a requisição.
    if data.canvas_json is not None:
        normalized_canvas = normalize_canvas_json_text(data.canvas_json) or "{}"
        if req.canvas:
            req.canvas.json_data = normalized_canvas
        else:
            db.add(CanvasData(requisition_id=req.id, json_data=normalized_canvas))

    if changes:
        log_action(db, entity="requisition", entity_id=req.id, action="UPDATE",
                   changed_by=current_user, changes=changes)

    # Avança a versão SEMPRE (mesmo quando só itens/canvas mudaram, que ficam em
    # outras tabelas e não disparam o onupdate da linha). Garante que a trava
    # otimista (P1.6) detecte qualquer gravação concorrente.
    req.updated_at = datetime.utcnow()

    _commit_or_ped_conflict(db, ped_number)
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/status", response_model=RequisitionResponse)
def update_status(
    req_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para atualizar esta requisição")
    old_status = req.status
    prod = _parse_production_note(data.note)
    is_sending_to_production = (
        (prod and prod["action"] == _PROD_SEND)
        or (not prod and data.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO)
    )
    if is_sending_to_production:
        _ensure_unique_ped_number(db, req.ped_number, exclude_req_id=req.id)
    if prod:
        action = prod["action"]
        normalized_destination = _canonical_destination(
            prod.get("target") or req.production_destination or ""
        )
        bypass_fifo = bool(prod.get("transfer"))
        if old_status == RequisitionStatus.AGUARDANDO_RECEBIMENTO and action in (
            _PROD_RECEIVED,
            _PROD_QUEUED,
            _PROD_STARTED,
        ):
            _ensure_waiting_receipt_fifo(
                db,
                current_user,
                normalized_destination,
                req.id,
            )
        elif (
            old_status == RequisitionStatus.AGUARDANDO_NA_FILA
            and action == _PROD_STARTED
            and not bypass_fifo
        ):
            _ensure_waiting_queue_fifo_for_requisition(
                db,
                current_user,
                normalized_destination,
                req.id,
            )
        _apply_production_transition(req, data)
    else:
        _apply_manual_status_transition(req, data.status)
    new_status = req.status

    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=current_user.id,
        note=data.note,
    ))

    # Cria notificações dentro da mesma transação
    notifications: list = []
    if prod:
        action = prod["action"]
        if action == _PROD_SEND:
            notifications.extend(build_production_sent(db, req, prod["target"]))
        elif action in (_PROD_RECEIVED, _PROD_STARTED):
            notifications.extend(build_vendor_event(db, req, "em_producao"))
        elif action in (_PROD_QUEUED, _PROD_RETURNED_QUEUE):
            notifications.extend(build_vendor_event(db, req, "aguardando_na_fila"))
        elif action == _PROD_FINISHED:
            notifications.extend(build_vendor_event(db, req, "faturado"))
        elif action == _PROD_CANCELED:
            notifications.extend(build_vendor_event(db, req, "prod_cancelada", prod.get("reason", "")))
    elif new_status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
        notifications.extend(build_production_sent(db, req, ""))
    elif new_status == RequisitionStatus.AGUARDANDO_NA_FILA:
        notifications.extend(build_vendor_event(db, req, "aguardando_na_fila"))
    elif new_status == RequisitionStatus.FATURADO:
        notifications.extend(build_vendor_event(db, req, "faturado"))
    elif new_status == RequisitionStatus.CANCELADA:
        notifications.extend(build_vendor_event(db, req, "cancelada"))

    db.commit()
    push_all(notifications)
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/canvas", response_model=RequisitionResponse)
def update_canvas(
    req_id: int,
    data: CanvasUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta requisição")
    _ensure_editable(req)
    normalized_json = normalize_canvas_json_text(data.json_data) or "{}"
    if req.canvas:
        req.canvas.json_data = normalized_json
    else:
        db.add(CanvasData(requisition_id=req.id, json_data=normalized_json))
    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/nf", response_model=RequisitionResponse)
def attach_nf(
    req_id: int,
    nf_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta requisição")
    _ensure_editable(req)
    req.nf_attachment = nf_path
    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/delivery-date", response_model=RequisitionResponse)
def update_delivery_date(
    req_id: int,
    data: DeliveryDateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Produção (A&R / Indústria) altera o prazo de entrega com justificativa.
    A requisição volta para o vendedor com status 'prazo_alterado' e notificação."""
    role = _role_key(current_user.role)
    if role not in (Role.ADMIN.value, Role.PRODUCAO.value, Role.INDUSTRIA.value):
        raise HTTPException(
            status_code=403,
            detail="Apenas a produção pode alterar o prazo de entrega",
        )

    req = _get_or_404(db, req_id)
    if req.status in (RequisitionStatus.CANCELADA, RequisitionStatus.FATURADO):
        raise HTTPException(
            status_code=400,
            detail="Não é possível alterar o prazo de uma requisição cancelada ou faturada",
        )

    destination = _destination_for_role(role)
    if destination and _current_production_destination(req) != destination:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para alterar o prazo desta requisição",
        )

    old_date = req.delivery_date
    old_status = req.status
    old_str = old_date.strftime("%d/%m/%Y") if old_date else "—"
    new_str = data.delivery_date.strftime("%d/%m/%Y")

    req.delivery_date = data.delivery_date
    req.status = RequisitionStatus.PRAZO_ALTERADO
    req.finalized_at = None
    req.production_machine = None
    req.delivery_deadline_changed_at = datetime.utcnow()
    req.delivery_deadline_change_reason = data.reason

    note = f"Prazo alterado de {old_str} para {new_str}. Motivo: {data.reason}"
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=RequisitionStatus.PRAZO_ALTERADO,
        changed_by_id=current_user.id,
        note=note,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivery_date": {"old": old_str, "new": new_str},
            "motivo": data.reason,
        },
    )

    notifications = build_vendor_event(db, req, "prazo_alterado", data.reason)
    db.commit()
    push_all(notifications)
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/delivery-schedule", response_model=RequisitionResponse)
def update_delivery_schedule(
    req_id: int,
    data: DeliveryDateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not req.entrega:
        raise HTTPException(
            status_code=400,
            detail="Esta requisição não está marcada como entrega",
        )
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para atualizar esta requisição")
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Não é possível alterar o prazo de uma requisição cancelada",
        )
    if req.delivered_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Esta entrega já foi concluída",
        )

    old_date = req.delivery_date
    old_str = old_date.strftime("%d/%m/%Y") if old_date else "—"
    new_str = data.delivery_date.strftime("%d/%m/%Y")
    current_status = getattr(req.status, "value", req.status)

    req.delivery_date = data.delivery_date
    req.status = RequisitionStatus.PRAZO_ALTERADO
    req.delivery_deadline_changed_at = datetime.utcnow()
    req.delivery_deadline_change_reason = data.reason

    note = f"Prazo de entrega alterado de {old_str} para {new_str}. Motivo: {data.reason}"
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=current_status,
        new_status=RequisitionStatus.PRAZO_ALTERADO,
        changed_by_id=current_user.id,
        note=note,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivery_date": {"old": old_str, "new": new_str},
            "delivery_deadline_change_reason": data.reason,
        },
    )

    notifications = build_vendor_event(db, req, "prazo_alterado", data.reason)
    db.commit()
    push_all(notifications)
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/mark-delivered", response_model=RequisitionResponse)
def mark_delivery_delivered(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not req.entrega:
        raise HTTPException(
            status_code=400,
            detail="Esta requisição não está marcada como entrega",
        )
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para atualizar esta requisição")
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Não é possível concluir a entrega de uma requisição cancelada",
        )
    if req.status not in (RequisitionStatus.FATURADO, RequisitionStatus.PRAZO_ALTERADO):
        raise HTTPException(
            status_code=400,
            detail="Somente pedidos faturados ou com prazo alterado podem ser marcados como entregues",
        )
    if req.delivered_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Esta entrega já foi concluída",
        )

    delivered_at = datetime.utcnow()
    current_status = getattr(req.status, "value", req.status)
    req.delivered_at = delivered_at

    note = f"Entrega concluída em {delivered_at.strftime('%d/%m/%Y %H:%M')}"
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=current_status,
        new_status=current_status,
        changed_by_id=current_user.id,
        note=note,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivered_at": delivered_at.isoformat(),
        },
    )

    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/cancel-delivered", response_model=RequisitionResponse)
def cancel_delivery_delivered(
    req_id: int,
    data: DeliveryCancellationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if not req.entrega:
        raise HTTPException(
            status_code=400,
            detail="Esta requisição não está marcada como entrega",
        )
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para atualizar esta requisição")
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Não é possível reabrir a entrega de uma requisição cancelada",
        )
    if req.delivered_at is None:
        raise HTTPException(
            status_code=400,
            detail="Esta requisição não está com entrega concluída",
        )

    current_status = getattr(req.status, "value", req.status)
    old_delivered_at = req.delivered_at
    req.delivered_at = None
    req.status = (
        RequisitionStatus.PRAZO_ALTERADO
        if req.delivery_deadline_changed_at is not None
        else RequisitionStatus.FATURADO
    )

    note = f"Entrega cancelada e retornada para agenda. Motivo: {data.reason}"
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=current_status,
        new_status=req.status,
        changed_by_id=current_user.id,
        note=note,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivered_at": {
                "old": old_delivered_at.isoformat() if old_delivered_at else "",
                "new": "",
            },
            "delivery_reopen_reason": data.reason,
            "status": {
                "old": current_status,
                "new": getattr(req.status, "value", req.status),
            },
        },
    )

    db.commit()
    return _get_or_404(db, req_id)


@router.delete("/{req_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para cancelar esta requisição")
    old_status = req.status
    req.status = RequisitionStatus.CANCELADA
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=RequisitionStatus.CANCELADA,
        changed_by_id=current_user.id,
    ))
    log_action(
        db,
        entity="requisition",
        entity_id=req.id,
        action="DELETE",
        changed_by=current_user,
        changes={"ped_number": req.ped_number, "status": {"old": str(old_status), "new": "cancelada"}},
    )

    notifications: list = []
    if req.vendor_id != current_user.id:
        notifications.extend(build_vendor_event(db, req, "cancelada"))
    else:
        # Mesmo que o vendedor cancele a própria req, admins/gerentes são notificados
        notifications.extend(
            _notify_admins_gerentes(
                db, "cancelada",
                "Requisição Cancelada ❌",
                f"PED #{req.ped_number} foi cancelada.",
                req.id,
                exclude_ids={current_user.id},
            )
        )

    db.commit()
    push_all(notifications)
