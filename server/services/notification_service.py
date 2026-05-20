from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..models.notification import Notification
from ..models.user import User, Role
from ..models.requisition import Requisition, RequisitionStatus
from . import sse_manager


def _make(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    message: str,
    req_id: int | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        requisition_id=req_id,
    )
    db.add(n)
    db.flush()
    return n


def _as_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "requisition_id": n.requisition_id,
        "read": False,
        "created_at": (n.created_at or datetime.utcnow()).isoformat(),
    }


def push_all(notifications: list[Notification]):
    for n in notifications:
        sse_manager.push_to_user(n.user_id, _as_dict(n))


def build_production_sent(
    db: Session, req: Requisition, destino: str
) -> list[Notification]:
    dest_upper = destino.upper()
    if "A&R" in dest_upper or dest_upper.startswith("A R"):
        roles = [Role.PRODUCAO]
    elif "PINHEIRO" in dest_upper or "IND" in dest_upper:
        roles = [Role.INDUSTRIA]
    else:
        roles = [Role.PRODUCAO, Role.INDUSTRIA]

    users = (
        db.query(User)
        .filter(User.role.in_(roles), User.is_active == True)
        .all()
    )
    return [
        _make(
            db,
            u.id,
            "nova_requisicao",
            "Nova Requisição para Produção",
            f"PED #{req.ped_number} — {req.client_name or 'cliente'} encaminhado para {destino}.",
            req.id,
        )
        for u in users
    ]


def build_vendor_event(
    db: Session,
    req: Requisition,
    event: str,
    reason: str = "",
) -> Notification | None:
    _map = {
        "em_producao": (
            "Requisição Recebida em Produção",
            f"Sua requisição PED #{req.ped_number} foi recebida e está em produção.",
        ),
        "finalizada": (
            "Produção Finalizada ✅",
            f"Sua requisição PED #{req.ped_number} foi finalizada em produção.",
        ),
        "prod_cancelada": (
            "Produção Cancelada ⚠️",
            f"Produção da PED #{req.ped_number} cancelada. Motivo: {reason}",
        ),
        "cancelada": (
            "Requisição Cancelada",
            f"Sua requisição PED #{req.ped_number} foi cancelada.",
        ),
    }
    if event not in _map:
        return None
    title, msg = _map[event]
    return _make(db, req.vendor_id, event, title, msg, req.id)


def stuck_requisition_events(db: Session) -> list[dict]:
    """Retorna eventos (não persistidos) de requisições paradas há >48h."""
    threshold = datetime.utcnow() - timedelta(hours=48)
    stuck = (
        db.query(Requisition)
        .filter(
            Requisition.status == RequisitionStatus.EM_ANDAMENTO,
            Requisition.created_at < threshold,
            Requisition.finalized_at == None,
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
            "message": (
                f"PED #{r.ped_number} ({r.client_name or ''}) "
                f"está em andamento há mais de 48 horas."
            ),
            "requisition_id": r.id,
            "read": False,
            "created_at": now,
        }
        for r in stuck
    ]
