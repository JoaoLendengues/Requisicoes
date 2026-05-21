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
from ..models.production_machine import ProductionMachine
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
    print(f"[NOTIF] _create → user_id={user_id} type={type_!r} req_id={req_id}")
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        requisition_id=req_id,
    )
    db.add(n)
    try:
        db.flush()
        print(f"[NOTIF] _create → flush OK, id={n.id}")
    except Exception as exc:
        print(f"[NOTIF] _create → flush FALHOU: {exc}")
        raise
    return n


# ── Helpers internos ─────────────────────────────────────────────────────────

def _notify_admins_gerentes(
    db: Session,
    type_: str,
    title: str,
    message: str,
    req_id: int | None,
    exclude_ids: set[int] | None = None,
) -> list[Notification]:
    """Cria notificações para todos os admins e gerentes ativos."""
    usuarios = (
        db.query(User)
        .filter(
            User.role.in_([Role.ADMIN, Role.GERENTE]),
            User.is_active == True,
        )
        .all()
    )
    return [
        _create(db, u.id, type_, title, message, req_id)
        for u in usuarios
        if u.id not in (exclude_ids or set())
    ]


# ── API pública ───────────────────────────────────────────────────────────────

def dispatch(notifications: list[Notification]) -> None:
    """
    Envia notificações via SSE para os usuários conectados.
    Deve ser chamado APÓS db.commit() para que os IDs estejam confirmados.
    """
    print(f"[NOTIF] dispatch → {len(notifications)} notificação(ões)")
    for n in notifications:
        sse_manager.push_to_user(n.user_id, _to_dict(n))


def notify_production_team(
    db: Session,
    req: Requisition,
    destino: str,
) -> list[Notification]:
    """
    Notifica a equipe de produção + admins/gerentes quando uma requisição é enviada.
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
    print(f"[NOTIF] notify_production_team → destino={destino!r} roles={roles} usuarios={[u.name for u in usuarios]}")

    destino_label = destino.strip() or "Produção"
    type_   = "nova_requisicao"
    title   = "Nova Requisição para Produção"
    message = f"PED #{req.ped_number} — {req.client_name or 'cliente'} → {destino_label}."

    notifs = [_create(db, u.id, type_, title, message, req.id) for u in usuarios]

    # Admins e gerentes também recebem
    ids_ja_notificados = {u.id for u in usuarios}
    notifs += _notify_admins_gerentes(db, type_, title, message, req.id, ids_ja_notificados)

    return notifs


def notify_vendor(
    db: Session,
    req: Requisition,
    event: str,
    reason: str = "",
) -> list[Notification]:
    """
    Notifica o vendedor + admins/gerentes sobre uma mudança de status.
    Retorna lista vazia se o evento for desconhecido.
    """
    _eventos = {
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
        return []

    title, msg = _eventos[event]
    notifs: list[Notification] = []
    ids_ja_notificados: set[int] = set()

    # Notifica o vendedor se definido
    if req.vendor_id:
        notifs.append(_create(db, req.vendor_id, event, title, msg, req.id))
        ids_ja_notificados.add(req.vendor_id)

    # Admins e gerentes também recebem
    notifs += _notify_admins_gerentes(db, event, title, msg, req.id, ids_ja_notificados)

    return notifs


def notify_machine_status_change(
    db: Session,
    machine: ProductionMachine,
    actor: User,
) -> list[Notification]:
    usuarios = (
        db.query(User)
        .filter(User.is_active == True)
        .all()
    )

    status_value = getattr(machine.status, "value", machine.status)
    status_label = "Funcionando" if str(status_value) == "funcionando" else "Manutenção"
    title = "Status de Máquina Atualizado"
    message = (
        f"{machine.destination} - {machine.name} agora está em {status_label}. "
        f"Alterado por {actor.name}."
    )

    return [
        _create(db, user.id, "machine_status", title, message, None)
        for user in usuarios
    ]


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
