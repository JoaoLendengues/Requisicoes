from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from collections import Counter
from datetime import datetime, timedelta
import unicodedata
from ..database import get_db
from ..models.client import Client
from ..models.requisition import (
    Requisition, RequisitionItem, CanvasData, StatusHistory, RequisitionStatus,
)
from ..models.user import User, Role
from ..schemas.dashboard import (
    DashboardReceiptAlertItem,
    DashboardRecentRequisitionItem,
    DashboardStatsResponse,
    DashboardVendorItem,
    ManagementDashboardResponse,
)
from ..schemas.order_center import (
    OrderCenterItemResponse,
    OrderCenterResponse,
    OrderCenterStatsResponse,
)
from ..schemas.requisition import (
    RequisitionCreate, RequisitionUpdate, RequisitionResponse,
    StatusUpdate, CanvasUpdate,
)
from ..dependencies import (
    get_current_user,
    require_creator,
    require_manager_or_admin,
    require_order_center_access,
)

router = APIRouter(prefix="/requisitions", tags=["Requisições"])

_LOAD_OPTS = [
    selectinload(Requisition.items),
    selectinload(Requisition.status_history),
    selectinload(Requisition.canvas),
    selectinload(Requisition.client),
    selectinload(Requisition.vendor),
]

_PROD_NOTE_PREFIX = "PRODUCAO"
_PROD_SEND = "ENVIADA"
_PROD_RECEIVED = "RECEBIDA"
_PROD_FINISHED = "FINALIZADA"
_PROD_CANCELED = "CANCELADA"
_DESTINATION_AR = "A&R"
_DESTINATION_PINHEIRO = "Pinheiro Indústria"


def _normalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode()
    return ascii_text.strip().casefold()


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


def _get_or_404(db: Session, req_id: int) -> Requisition:
    req = db.query(Requisition).options(*_LOAD_OPTS).filter(Requisition.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requisição não encontrada")
    return req


def _sum_item_weights(items: Optional[list]) -> float:
    return sum((item.weight or 0.0) for item in (items or []))


def _parse_production_note(note: Optional[str]) -> dict | None:
    if not note:
        return None

    parts = str(note).split("|", 3)
    if len(parts) < 3 or parts[0] != _PROD_NOTE_PREFIX:
        return None

    data = {
        "action": parts[1].strip(),
        "target": _canonical_destination(parts[2]),
        "reason": "",
    }
    if len(parts) > 3:
        data["reason"] = parts[3].strip()
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


def _apply_production_transition(req: Requisition, status_update: StatusUpdate):
    prod_event = _parse_production_note(status_update.note)
    if not prod_event:
        return

    action = prod_event["action"]
    reason = prod_event["reason"]

    if action == _PROD_SEND:
        req.status = RequisitionStatus.AGUARDANDO_RECEBIMENTO
        req.finalized_at = None
        return

    if action == _PROD_RECEIVED:
        if req.status not in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
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
        req.finalized_at = datetime.utcnow()
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
        req.status = RequisitionStatus.EM_ANDAMENTO
        return

    if action == _PROD_CANCELED:
        if len(reason.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Informe um motivo de cancelamento com pelo menos 10 caracteres",
            )
        req.status = RequisitionStatus.EM_ANDAMENTO
        req.finalized_at = None
        return


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
                "reason": parsed["reason"],
                "changed_at": entry.changed_at,
            }
        )
    return events


def _current_production_destination(req: Requisition) -> str:
    for event in reversed(_production_events(req)):
        target = _canonical_destination(event.get("target"))
        if target:
            return target
    return ""


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
    if req.status == RequisitionStatus.CANCELADA:
        return False

    events = _production_events(req)
    if not events:
        return True
    return events[-1]["action"] != _PROD_FINISHED


def _latest_production_event(req: Requisition, action: str) -> dict | None:
    for event in reversed(_production_events(req)):
        if event["action"] == action:
            return event
    return None


def _latest_status_changed_at(req: Requisition, status_value: str) -> datetime | None:
    target_status = getattr(status_value, "value", status_value)
    for entry in reversed(_sorted_status_history(req)):
        if str(entry.new_status) == str(target_status):
            return entry.changed_at
    return None


def _latest_finished_cycle(req: Requisition) -> dict | None:
    received_at: datetime | None = None
    received_target: str | None = None
    latest_cycle: dict | None = None

    for event in _production_events(req):
        changed_at = event["changed_at"]
        if changed_at is None:
            continue

        action = event["action"]
        if action == _PROD_RECEIVED:
            received_at = changed_at
            received_target = event["target"] or None
            continue

        if action == _PROD_FINISHED:
            if received_at is not None:
                latest_cycle = {
                    "received_at": received_at,
                    "finished_at": changed_at,
                    "target": received_target,
                    "production_time_seconds": max(
                        0, int((changed_at - received_at).total_seconds())
                    ),
                }
            received_at = None
            received_target = None
            continue

        if action in (_PROD_SEND, _PROD_CANCELED):
            received_at = None
            received_target = None

    return latest_cycle


def _build_order_center(reqs: list[Requisition]) -> OrderCenterResponse:
    now = datetime.utcnow()
    today = now.date()

    waiting_rows: list[OrderCenterItemResponse] = []
    production_rows: list[OrderCenterItemResponse] = []
    finished_rows: list[OrderCenterItemResponse] = []
    canceled_rows: list[OrderCenterItemResponse] = []
    delayed_rows: list[OrderCenterItemResponse] = []
    production_durations: list[int] = []

    for req in reqs:
        destination = _current_production_destination(req) or None
        events = _production_events(req)

        if req.status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
            sent_event = _latest_production_event(req, _PROD_SEND)
            waiting_minutes = None
            if sent_event and sent_event["changed_at"]:
                waiting_minutes = max(
                    0,
                    int((now - sent_event["changed_at"]).total_seconds() // 60),
                )
            waiting_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    waiting_minutes=waiting_minutes,
                )
            )

        if req.status == RequisitionStatus.EM_PRODUCAO:
            received_event = _latest_production_event(req, _PROD_RECEIVED)
            production_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    received_at=received_event["changed_at"] if received_event else None,
                )
            )

        latest_finished = _latest_finished_cycle(req)
        latest_event = events[-1] if events else None
        if latest_finished:
            production_durations.append(latest_finished["production_time_seconds"])
        if latest_event and latest_event["action"] == _PROD_FINISHED and latest_finished:
            finished_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    status="finalizado",
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=latest_finished["target"] or destination,
                    received_at=latest_finished["received_at"],
                    finished_at=latest_finished["finished_at"],
                    production_time_seconds=latest_finished["production_time_seconds"],
                )
            )

        if req.status == RequisitionStatus.CANCELADA:
            canceled_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    canceled_at=_latest_status_changed_at(req, RequisitionStatus.CANCELADA),
                )
            )

        if req.delivery_date and req.delivery_date < today and _is_open_requisition(req):
            delayed_rows.append(
                OrderCenterItemResponse(
                    id=req.id,
                    ped_number=req.ped_number,
                    client_name=req.client_name,
                    vendor_name=req.vendor_name,
                    status=req.status,
                    emission_date=req.emission_date,
                    delivery_date=req.delivery_date,
                    destination=destination,
                    delay_days=max(0, (today - req.delivery_date).days),
                )
            )

    waiting_rows.sort(key=lambda item: item.waiting_minutes or 0, reverse=True)
    production_rows.sort(key=lambda item: item.received_at or datetime.min, reverse=True)
    finished_rows.sort(key=lambda item: item.finished_at or datetime.min, reverse=True)
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
            pedidos_finalizados=len(finished_rows),
            pedidos_cancelados=len(canceled_rows),
            pedidos_atrasados=len(delayed_rows),
            tempo_medio_producao_segundos=average_seconds,
        ),
        aguardando_recebimento=waiting_rows[:100],
        em_producao=production_rows[:100],
        finalizados=finished_rows[:100],
        cancelados=canceled_rows[:100],
        atrasados=delayed_rows[:100],
    )


def _build_management_dashboard(reqs: list[Requisition]) -> ManagementDashboardResponse:
    now = datetime.utcnow()
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
            RequisitionStatus.EM_PRODUCAO,
        )

        if req.status == RequisitionStatus.EM_PRODUCAO:
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

        received_at: datetime | None = None
        for event in _production_events(req):
            action = event["action"]
            changed_at = event["changed_at"]
            if changed_at is None:
                continue

            if action == _PROD_RECEIVED:
                received_at = changed_at
                continue

            if action == _PROD_FINISHED:
                if received_at is not None:
                    completion_durations.append(
                        max(0, int((changed_at - received_at).total_seconds()))
                    )
                    received_at = None
                if changed_at.date() == today:
                    pedidos_finalizados_hoje += 1
                continue

            if action in (_PROD_SEND, _PROD_CANCELED):
                received_at = None

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

    return ManagementDashboardResponse(
        generated_at=now,
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
    )


@router.get("/", response_model=List[RequisitionResponse])
def list_requisitions(
    req_status: Optional[RequisitionStatus] = Query(None, alias="status"),
    client_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Requisition).options(*_LOAD_OPTS)

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
    reqs = q.order_by(Requisition.created_at.desc()).all()
    visible = _filter_requisitions_for_user(reqs, current_user)
    return visible[skip:skip + limit]


@router.get("/dashboard/summary", response_model=ManagementDashboardResponse)
def get_management_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_manager_or_admin),
):
    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.desc())
        .all()
    )
    return _build_management_dashboard(reqs)


@router.get("/order-center/summary", response_model=OrderCenterResponse)
def get_order_center(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_order_center_access),
):
    reqs = (
        db.query(Requisition)
        .options(*_LOAD_OPTS)
        .order_by(Requisition.created_at.desc())
        .all()
    )
    return _build_order_center(_filter_requisitions_for_user(reqs, current_user))


@router.post("/", response_model=RequisitionResponse, status_code=status.HTTP_201_CREATED)
def create_requisition(
    data: RequisitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    items_data = data.items
    req = Requisition(
        **data.model_dump(exclude={"items", "weight"}),
        vendor_id=current_user.id,
        weight=_sum_item_weights(items_data),
    )
    db.add(req)
    db.flush()

    for item in items_data:
        db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))

    db.add(CanvasData(requisition_id=req.id))
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=None,
        new_status=RequisitionStatus.EM_ANDAMENTO,
        changed_by_id=current_user.id,
    ))
    db.commit()
    return _get_or_404(db, req.id)


@router.get("/{req_id}", response_model=RequisitionResponse)
def get_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    if not _can_view_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para visualizar esta requisicao")
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
        raise HTTPException(status_code=403, detail="Sem permissao para editar esta requisicao")
    _ensure_editable(req)

    for k, v in data.model_dump(exclude_unset=True, exclude={"items", "weight"}).items():
        setattr(req, k, v)

    if data.items is not None:
        for item in list(req.items):
            db.delete(item)
        db.flush()
        for item in data.items:
            db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))
        req.weight = _sum_item_weights(data.items)
    elif data.weight is not None:
        req.weight = data.weight

    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/status", response_model=RequisitionResponse)
def update_status(
    req_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ..services.notification_service import (
        build_production_sent, build_vendor_event, push_all,
    )

    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para atualizar esta requisicao")
    old_status = req.status
    prod = _parse_production_note(data.note)
    if prod:
        _apply_production_transition(req, data)
    else:
        req.status = data.status
    new_status = req.status

    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=current_user.id,
        note=data.note,
    ))

    # Cria notificações dentro da mesma transação
    notifications = []
    if prod:
        action = prod["action"]
        if action == _PROD_SEND:
            notifications.extend(build_production_sent(db, req, prod["target"]))
        elif action == _PROD_RECEIVED:
            n = build_vendor_event(db, req, "em_producao")
            if n:
                notifications.append(n)
        elif action == _PROD_FINISHED:
            n = build_vendor_event(db, req, "finalizada")
            if n:
                notifications.append(n)
        elif action == _PROD_CANCELED:
            n = build_vendor_event(db, req, "prod_cancelada", prod.get("reason", ""))
            if n:
                notifications.append(n)
    elif new_status == RequisitionStatus.AGUARDANDO_RECEBIMENTO:
        # Vendedor enviou para produção direto pelo status — notifica equipe de produção
        notifications.extend(build_production_sent(db, req, ""))
    elif new_status == RequisitionStatus.CANCELADA:
        n = build_vendor_event(db, req, "cancelada")
        if n:
            notifications.append(n)

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
        raise HTTPException(status_code=403, detail="Sem permissao para editar esta requisicao")
    _ensure_editable(req)
    if req.canvas:
        req.canvas.json_data = data.json_data
    else:
        db.add(CanvasData(requisition_id=req.id, json_data=data.json_data))
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
        raise HTTPException(status_code=403, detail="Sem permissao para editar esta requisicao")
    _ensure_editable(req)
    req.nf_attachment = nf_path
    db.commit()
    return _get_or_404(db, req_id)


@router.delete("/{req_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ..services.notification_service import build_vendor_event, push_all

    req = _get_or_404(db, req_id)
    if not _can_edit_requisition(req, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para cancelar esta requisicao")
    old_status = req.status
    req.status = RequisitionStatus.CANCELADA
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=RequisitionStatus.CANCELADA,
        changed_by_id=current_user.id,
    ))

    notifications = []
    if req.vendor_id != current_user.id:
        n = build_vendor_event(db, req, "cancelada")
        if n:
            notifications.append(n)

    db.commit()
    push_all(notifications)
