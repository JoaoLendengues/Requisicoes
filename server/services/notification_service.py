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
        "faturado": (
            "Pedido Faturado",
            f"PED #{req.ped_number} foi marcado como faturado.",
        ),
        "prod_cancelada": (
            "Produção Cancelada ⚠️",
            f"PED #{req.ped_number} — produção cancelada. Motivo: {reason}",
        ),
        "prazo_alterado": (
            "Prazo de Entrega Alterado 📅",
            (
                f"PED #{req.ped_number} teve o prazo de entrega alterado pela produção."
                + (f" Motivo: {reason}" if reason else "")
            ),
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


# NOTA: ensure_pending_invoice_notifications foi removida (Jun/2026).
# O status AGUARDANDO_FATURAMENTO foi descontinuado — pedidos passam direto
# de produção para FATURADO/FINALIZADO, então não há mais "espera por
# faturamento" para alertar. Stub mantido para compatibilidade temporaria
# com chamadores que ainda nao foram atualizados.
def ensure_pending_invoice_notifications(db: Session) -> list[Notification]:
    return []


_DEADLINE_OPEN_STATUSES = (
    RequisitionStatus.EM_ANDAMENTO,
    RequisitionStatus.PRAZO_ALTERADO,
    RequisitionStatus.AGUARDANDO_RECEBIMENTO,
    RequisitionStatus.AGUARDANDO_NA_FILA,
    RequisitionStatus.EM_PRODUCAO,
)


def ensure_delivery_deadline_notifications(db: Session) -> list[Notification]:
    """Notifica vendedor + gerentes/admins quando o prazo de entrega está
    próximo (hoje ou amanhã) ou já vencido. Idempotente por (tipo, usuário, req)."""
    from datetime import date as _date

    today = _date.today()
    soon_limit = today + timedelta(days=1)  # hoje ou amanhã = "próximo"

    requisitions = (
        db.query(Requisition)
        .options(selectinload(Requisition.client))
        .filter(
            Requisition.status.in_(_DEADLINE_OPEN_STATUSES),
            Requisition.delivery_date.isnot(None),
            Requisition.delivery_date <= soon_limit,
        )
        .all()
    )
    if not requisitions:
        return []

    managers = (
        db.query(User)
        .filter(
            User.role.in_([Role.ADMIN, Role.GERENTE]),
            User.is_active == True,
        )
        .all()
    )

    requisition_ids = [req.id for req in requisitions]
    existing_pairs = {
        (str(type_), int(user_id), int(req_id))
        for type_, user_id, req_id in (
            db.query(Notification.type, Notification.user_id, Notification.requisition_id)
            .filter(
                Notification.type.in_(["prazo_proximo", "prazo_vencido"]),
                Notification.requisition_id.in_(requisition_ids),
            )
            .all()
        )
        if user_id is not None and req_id is not None
    }

    notifications: list[Notification] = []
    for req in requisitions:
        overdue = req.delivery_date < today
        type_ = "prazo_vencido" if overdue else "prazo_proximo"
        if overdue:
            title = "Prazo de Entrega Vencido ⏰"
            message = (
                f"PED #{req.ped_number} - {req.client_name or 'CLIENTE'} "
                f"está com o prazo de entrega vencido ({req.delivery_date.strftime('%d/%m/%Y')})."
            )
        else:
            title = "Prazo de Entrega Próximo 📅"
            message = (
                f"PED #{req.ped_number} - {req.client_name or 'CLIENTE'} "
                f"tem entrega prevista para {req.delivery_date.strftime('%d/%m/%Y')}."
            )

        recipients: dict[int, None] = {}
        if req.vendor_id:
            recipients[req.vendor_id] = None
        for manager in managers:
            recipients[manager.id] = None

        for user_id in recipients:
            key = (type_, int(user_id), int(req.id))
            if key in existing_pairs:
                continue
            notifications.append(
                _create(db, user_id, type_, title, message, req.id)
            )
            existing_pairs.add(key)

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
