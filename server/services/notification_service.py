"""
Serviço de notificações.

Responsabilidades:
- Criar e persistir notificações no banco (dentro da transação do caller)
- Converter notificações ORM em dicts para SSE
- Enviar eventos SSE após commit
- Definir quem recebe cada tipo de notificação
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..models.notification import Notification
from ..models.requisition import Requisition, RequisitionStatus
from ..models.user import User, Role
from . import sse_manager


# ── Helpers internos ──────────────────────────────────────────────────────────

def _to_dict(n: Notification) -> dict:
    return {
        "id":             n.id,
        "type":           n.type,
        "title":          n.title,
        "message":        n.message,
        "requisition_id": n.requisition_id,
        "read":           False,
        "created_at":     (n.created_at or datetime.utcnow()).isoformat(),
    }


def _create(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    message: str,
    req_id: int | None = None,
) -> Notification:
    """Cria uma notificação e faz flush (sem commit — responsabilidade do caller)."""
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        requisition_id=req_id,
    )
    db.add(n)
    db.flush()   # garante que n.id seja preenchido antes do return
    return n


# ── API pública ───────────────────────────────────────────────────────────────

def dispatch(notifications: list[Notification]) -> None:
    """
    Envia notificações via SSE para os usuários conectados.
    Deve ser chamado APÓS db.commit() para que os IDs estejam confirmados.
    """
    for n in notifications:
        sse_manager.push_to_user(n.user_id, _to_dict(n))


def notify_production_team(
    db: Session,
    req: Requisition,
    destino: str,
) -> list[Notification]:
    """
    Notifica a equipe de produção quando uma requisição é enviada.
    Roteia para PRODUCAO, INDUSTRIA ou ambos conforme o destino.
    """
    dest = destino.upper()
    if "A&R" in dest or dest.startswith("A R"):
        roles = [Role.PRODUCAO]
    elif "PINHEIRO" in dest or "IND" in dest:
        roles = [Role.INDUSTRIA]
    else:
        roles = [Role.PRODUCAO, Role.INDUSTRIA]

    usuarios = (
        db.query(User)
        .filter(User.role.in_(roles), User.is_active == True)
        .all()
    )

    destino_label = destino.strip() or "Produção"
    return [
        _create(
            db, u.id,
            "nova_requisicao",
            "Nova Requisição para Produção",
            f"PED #{req.ped_number} — {req.client_name or 'cliente'} → {destino_label}.",
            req.id,
        )
        for u in usuarios
    ]


def notify_vendor(
    db: Session,
    req: Requisition,
    event: str,
    reason: str = "",
) -> Notification | None:
    """
    Notifica o vendedor da requisição sobre uma mudança de status.
    Retorna None se o vendedor não estiver definido ou o evento for desconhecido.
    """
    if not req.vendor_id:
        return None

    _eventos = {
        "em_producao": (
            "Requisição em Produção ⚙️",
            f"PED #{req.ped_number} foi recebida pela produção.",
        ),
        "finalizada": (
            "Produção Finalizada ✅",
            f"PED #{req.ped_number} foi finalizada em produção.",
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

    if event not in _eventos:
        return None

    title, msg = _eventos[event]
    return _create(db, req.vendor_id, event, title, msg, req.id)


def stuck_requisition_events(db: Session) -> list[dict]:
    """
    Retorna eventos (sem persistir) de requisições paradas há mais de 48h.
    Destinado a admin e gerente no evento inicial do SSE.
    """
    limite = datetime.utcnow() - timedelta(hours=48)
    paradas = (
        db.query(Requisition)
        .filter(
            Requisition.status == RequisitionStatus.EM_ANDAMENTO,
            Requisition.created_at < limite,
            Requisition.finalized_at.is_(None),
        )
        .limit(10)
        .all()
    )
    agora = datetime.utcnow().isoformat()
    return [
        {
            "id":             None,
            "type":           "requisicao_parada",
            "title":          "Requisição Parada ⏰",
            "message":        f"PED #{r.ped_number} ({r.client_name or ''}) está parada há mais de 48h.",
            "requisition_id": r.id,
            "read":           False,
            "created_at":     agora,
        }
        for r in paradas
    ]
