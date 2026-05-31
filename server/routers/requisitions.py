from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import shutil
import unicodedata
from ..config import settings
from ..database import get_db
from ..models.client import Client
from ..models.production_machine import ProductionMachine
from ..models.requisition import (
    Requisition, RequisitionItem, CanvasData, StatusHistory, RequisitionStatus,
)
from ..models.user import User, Role
from ..schemas.dashboard import (
    DashboardMachineUsageItem,
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
    ProductionSummaryStatsResponse,
)
from ..schemas.requisition import (
    RequisitionCreate, RequisitionUpdate, RequisitionResponse, RequisitionListItem,
    StatusUpdate, CanvasUpdate, DeliveryDateUpdate,
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
    selectinload(Requisition.canvas),
    selectinload(Requisition.client),
    selectinload(Requisition.vendor),
]

# Listagens não precisam de itens nem do canvas (desenho); status_history é
# necessário só para derivar os campos de produção. Carrega o mínimo.
_LIST_LOAD_OPTS = [
    selectinload(Requisition.status_history),
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
            detail="Período de máquinas inválido. Use 30d, 7d, today ou last_month.",
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


def _sum_item_weights(items: Optional[list]) -> float:
    return sum((item.weight or 0.0) for item in (items or []))


def _normalize_operator_name(value: object) -> str:
    return normalize_upper_required(value).replace("|", " ").replace(";", " ").strip()


def _parse_operator_names(raw: object) -> list[str]:
    if raw is None:
        return []

    names: list[str] = []
    seen: set[str] = set()
    for part in str(raw).split(";"):
        normalized = _normalize_operator_name(part)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


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


def _sorted_status_history(req: Requisition) -> list[StatusHistory]:
    history = list(req.status_history or [])
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


def _history_production_operator_names(req: Requisition) -> list[str]:
    if req.status == RequisitionStatus.EM_PRODUCAO:
        started_event = _latest_production_event(req, _PROD_STARTED, _PROD_RECEIVED)
        operator_names = [
            str(name).strip()
            for name in ((started_event or {}).get("operators") or [])
            if str(name).strip()
        ]
        if operator_names:
            return operator_names

    latest_cycle = _latest_finished_cycle(req)
    if latest_cycle:
        operator_names = [
            str(name).strip()
            for name in (latest_cycle.get("operators") or [])
            if str(name).strip()
        ]
        if operator_names:
            return operator_names

    started_event = _latest_production_event(req, _PROD_STARTED, _PROD_RECEIVED)
    return [
        str(name).strip()
        for name in ((started_event or {}).get("operators") or [])
        if str(name).strip()
    ]


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
    cycles: list[dict] = []
    started_at: datetime | None = None
    started_target: str | None = None
    started_machine: str | None = None
    started_operators: list[str] = []

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
) -> ProductionItemResponse:
    status_value = getattr(req.status, "value", req.status)
    return ProductionItemResponse(
        id=req.id,
        ped_number=req.ped_number,
        client_name=req.client_name,
        vendor_name=req.vendor_name,
        obra=req.obra,
        weight=req.weight,
        status=str(status_value),
        emission_date=req.emission_date,
        created_at=req.created_at,
        delivery_date=req.delivery_date,
        destination=_current_production_destination(req) or None,
        machine_name=_normalize_machine_name(machine_name) or None,
        operator_names=[str(name).strip() for name in (operator_names or []) if str(name).strip()],
        waiting_since=waiting_since,
        production_started_at=production_started_at,
    )


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


def _build_delivery_center(reqs: list[Requisition]) -> DeliveryCenterResponse:
    now = datetime.utcnow()
    today = (_to_local_datetime(now) or datetime.now(_LOCAL_TIMEZONE)).date()

    rows: list[DeliveryCenterItemResponse] = []
    deliveries_today = 0
    delayed_deliveries = 0
    changed_delivery_deadlines = 0
    completed_deliveries = 0

    for req in reqs:
        # A tela de Entregas só deve listar pedidos marcados para entrega
        # e já faturados (etapa após finalização de produção).
        if (
            not req.entrega
            or req.status == RequisitionStatus.CANCELADA
            or req.status != RequisitionStatus.FATURADO
        ):
            continue

        deadline_changed_at = _delivery_deadline_changed_at(req)
        delivered_at = getattr(req, "delivered_at", None)
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

        rows.append(
            DeliveryCenterItemResponse(
                id=req.id,
                ped_number=req.ped_number,
                client_name=req.client_name,
                vendor_name=req.vendor_name,
                weight=float(req.weight or 0.0),
                destination=_current_production_destination(req) or None,
                delivery_date=delivery_date,
                status=str(getattr(req.status, "value", req.status) or ""),
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


def _build_management_dashboard(
    reqs: list[Requisition],
    machines: list[ProductionMachine],
    *,
    ar_period: str = "30d",
    industria_period: str = "30d",
) -> ManagementDashboardResponse:
    now = datetime.utcnow()
    generated_at = _to_local_datetime(now) or datetime.now(_LOCAL_TIMEZONE)
    today = now.date()
    one_hour_ago = now - timedelta(hours=1)

    top_vendors_counter: Counter[str] = Counter()
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
        vendor_name = (req.vendor_name or "").strip() or "Sem vendedor"
        top_vendors_counter[vendor_name] += 1

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

    top_vendors = [
        DashboardVendorItem(vendor_name=name, requisition_count=count)
        for name, count in top_vendors_counter.most_common(8)
    ]

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
        top_vendors=top_vendors,
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
                for name in _history_production_operator_names(req)
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
        setattr(req, "production_operator_names", operator_names)
        setattr(req, "production_operator_display", ", ".join(operator_names) or None)
        setattr(req, "production_sent_at", _history_production_sent_at(req))
        setattr(req, "production_finished_at", _history_production_finished_at(req))
        setattr(req, "production_status", _history_production_status(req))
        setattr(req, "invoiced", req.status == RequisitionStatus.FATURADO)
        setattr(req, "cancel_reason", _cancel_reason_for(req))
    return paginated


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
    db: Session = Depends(get_db),
    _: User = Depends(require_manager_or_admin),
):
    _check_invoice_alerts(db)
    normalized_ar_period = _normalize_machine_dashboard_period(ar_period)
    normalized_industria_period = _normalize_machine_dashboard_period(industria_period)

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
        .order_by(ProductionMachine.sort_order.asc(), ProductionMachine.id.asc())
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
        .order_by(ProductionMachine.sort_order.asc(), ProductionMachine.id.asc())
        .all()
    )
    return [
        _normalize_machine_name(machine.name)
        for machine in machines
        if _normalize_machine_name(machine.name)
    ]


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
    _ensure_editable(req)
    ped_number = data.ped_number if data.ped_number is not None else req.ped_number
    _ensure_unique_ped_number(db, ped_number, exclude_req_id=req.id)

    scalar_update = data.model_dump(exclude_unset=True, exclude={"items", "weight", "canvas_json"})
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
    req.delivery_deadline_changed_at = datetime.utcnow()
    req.delivery_deadline_change_reason = data.reason

    note = f"Prazo de entrega alterado de {old_str} para {new_str}. Motivo: {data.reason}"
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
    if req.status != RequisitionStatus.FATURADO:
        raise HTTPException(
            status_code=400,
            detail="Somente pedidos faturados podem ser marcados como entregues",
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
