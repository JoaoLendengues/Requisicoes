"""
Notification helpers.

Responsibilities:
- create and persist notifications inside the caller transaction
- convert ORM notifications to dict payloads for SSE
- dispatch committed notifications to connected users
- centralize recipients for operational events
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload

from ..models.notification import Notification
from ..models.production_machine import ProductionMachine
from ..models.requisition import Requisition, RequisitionStatus
from ..models.user import Role, User
from . import sse_manager
from .system_settings import get_pending_invoice_alert_days


def _to_dict(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "requisition_id": notification.requisition_id,
        "read": False,
        "created_at": (notification.created_at or datetime.utcnow()).isoformat(),
    }


def _create(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    message: str,
    req_id: int | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        requisition_id=req_id,
    )
    db.add(notification)
    db.flush()
    return notification


def _notify_admins_gerentes(
    db: Session,
    type_: str,
    title: str,
    message: str,
    req_id: int | None,
    exclude_ids: set[int] | None = None,
) -> list[Notification]:
    users = (
        db.query(User)
        .filter(
            User.role.in_([Role.ADMIN, Role.GERENTE]),
            User.is_active == True,
        )
        .all()
    )
    return [
        _create(db, user.id, type_, title, message, req_id)
        for user in users
        if user.id not in (exclude_ids or set())
    ]


def _latest_status_changed_at(
    req: Requisition,
    status_value: RequisitionStatus | str,
) -> datetime | None:
    target = getattr(status_value, "value", status_value)
    history = sorted(
        list(req.status_history or []),
        key=lambda entry: (entry.changed_at or datetime.min, entry.id or 0),
    )
    for entry in reversed(history):
        if str(entry.new_status) == str(target):
            return entry.changed_at
    return None


def dispatch(notifications: list[Notification]) -> None:
    for notification in notifications:
        sse_manager.push_to_user(notification.user_id, _to_dict(notification))


def notify_production_team(
    db: Session,
    req: Requisition,
    destino: str,
) -> list[Notification]:
    destination = destino.upper()
    if "A&R" in destination or destination.startswith("A R"):
        roles = [Role.PRODUCAO]
    elif "PINHEIRO" in destination or "IND" in destination:
        roles = [Role.INDUSTRIA]
    else:
        roles = [Role.PRODUCAO, Role.INDUSTRIA]

    users = (
        db.query(User)
        .filter(User.role.in_(roles), User.is_active == True)
        .all()
    )

    destination_label = destino.strip() or "Produção"
    type_ = "nova_requisicao"
    title = "Nova Requisição para Produção"
    message = f"PED #{req.ped_number} — {req.client_name or 'cliente'} → {destination_label}."

    notifications = [_create(db, user.id, type_, title, message, req.id) for user in users]
    already_notified = {user.id for user in users}
    notifications += _notify_admins_gerentes(
        db,
        type_,
        title,
        message,
        req.id,
        already_notified,
    )
    return notifications


def notify_vendor(
    db: Session,
    req: Requisition,
    event: str,
    reason: str = "",
) -> list[Notification]:
    events = {
        "aguardando_na_fila": (
            "Requisição em Fila",
            f"PED #{req.ped_number} aguardando disponibilidade da produção.",
        ),
        "em_producao": (
            "Requisição em Produção ⚙️",
            f"PED #{req.ped_number} foi recebida pela produção.",
        ),
        "finalizada": (
            "Produção Finalizada ✅",
            f"PED #{req.ped_number} foi finalizada em produção.",
        ),
        "aguardando_faturamento": (
            "Pedido Aguardando Faturamento",
            f"PED #{req.ped_number} finalizado em produção e aguardando faturamento.",
        ),
        "faturado": (
            "Pedido Faturado",
            f"PED #{req.ped_number} foi marcado como faturado.",
        ),
        "prod_cancelada": (
            "Produção Cancelada ⚠️",
            f"PED #{req.ped_number} — produção cancelada. Motivo: {reason}",
        ),
        "cancelada": (
            "Requisição Cancelada ❌",
            f"PED #{req.ped_number} foi cancelada.",
        ),
    }

    if event not in events:
        return []

    title, message = events[event]
    notifications: list[Notification] = []
    already_notified: set[int] = set()

    if req.vendor_id:
        notifications.append(_create(db, req.vendor_id, event, title, message, req.id))
        already_notified.add(req.vendor_id)

    notifications += _notify_admins_gerentes(
        db,
        event,
        title,
        message,
        req.id,
        already_notified,
    )
    return notifications


def notify_machine_status_change(
    db: Session,
    machine: ProductionMachine,
    actor: User,
) -> list[Notification]:
    users = db.query(User).filter(User.is_active == True).all()

    status_value = getattr(machine.status, "value", machine.status)
    status_label = "Funcionando" if str(status_value) == "funcionando" else "Manutenção"
    title = "Status de Máquina Atualizado"
    message = (
        f"{machine.destination} - {machine.name} agora está em {status_label}. "
        f"Alterado por {actor.name}."
    )

    return [
        _create(db, user.id, "machine_status", title, message, None)
        for user in users
    ]


def ensure_pending_invoice_notifications(db: Session) -> list[Notification]:
    threshold_days = get_pending_invoice_alert_days()
    cutoff = datetime.utcnow() - timedelta(days=threshold_days)
    managers = (
        db.query(User)
        .filter(User.role == Role.GERENTE, User.is_active == True)
        .all()
    )
    if not managers:
        return []

    requisitions = (
        db.query(Requisition)
        .options(
            selectinload(Requisition.status_history),
            selectinload(Requisition.client),
        )
        .filter(Requisition.status == RequisitionStatus.AGUARDANDO_FATURAMENTO)
        .all()
    )
    if not requisitions:
        return []

    manager_ids = [manager.id for manager in managers]
    requisition_ids = [req.id for req in requisitions]
    existing_pairs = {
        (int(user_id), int(req_id))
        for user_id, req_id in (
            db.query(Notification.user_id, Notification.requisition_id)
            .filter(
                Notification.type == "faturamento_atrasado",
                Notification.user_id.in_(manager_ids),
                Notification.requisition_id.in_(requisition_ids),
            )
            .all()
        )
        if user_id is not None and req_id is not None
    }

    notifications: list[Notification] = []
    now = datetime.utcnow()
    for req in requisitions:
        waiting_since = (
            _latest_status_changed_at(req, RequisitionStatus.AGUARDANDO_FATURAMENTO)
            or req.updated_at
            or req.created_at
        )
        if waiting_since is None or waiting_since > cutoff:
            continue

        waiting_days = max(
            threshold_days,
            int((now - waiting_since).total_seconds() // 86_400),
        )
        title = "Pedido sem faturamento"
        message = (
            f"PED #{req.ped_number} - {req.client_name or 'CLIENTE'} "
            f"aguarda faturamento há {waiting_days} dia(s)."
        )
        for manager in managers:
            pair = (manager.id, req.id)
            if pair in existing_pairs:
                continue
            notifications.append(
                _create(
                    db,
                    manager.id,
                    "faturamento_atrasado",
                    title,
                    message,
                    req.id,
                )
            )
            existing_pairs.add(pair)

    return notifications


def stuck_requisition_events(db: Session) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(hours=48)
    requisitions = (
        db.query(Requisition)
        .filter(
            Requisition.status == RequisitionStatus.EM_ANDAMENTO,
            Requisition.created_at < cutoff,
            Requisition.finalized_at.is_(None),
        )
        .limit(10)
        .all()
    )
    now = datetime.utcnow().isoformat()
    return [
        {
            "id": None,
            "type": "requisicao_parada",
            "title": "Requisição Parada ⏰",
            "message": f"PED #{req.ped_number} ({req.client_name or ''}) está parada há mais de 48h.",
            "requisition_id": req.id,
            "read": False,
            "created_at": now,
        }
        for req in requisitions
    ]
