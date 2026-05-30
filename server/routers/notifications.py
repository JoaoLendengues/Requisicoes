"""
Endpoints de notificações.

GET  /notifications/stream    → SSE: stream em tempo real + entrega inicial das não lidas
GET  /notifications/          → lista as não lidas do usuário (máx 50)
GET  /notifications/count     → contagem de não lidas
PATCH /notifications/read-all → marca todas como lidas
PATCH /notifications/{id}/read → marca uma como lida
"""
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.notification import Notification
from ..models.user import Role, User
from ..schemas.notification import NotificationOut
from ..services import sse_manager
from ..services.notification_service import (
    dispatch as push_all,
    ensure_pending_invoice_notifications,
    stuck_requisition_events,
)

router = APIRouter(prefix="/notifications", tags=["Notificações"])


def _orm_to_dict(n: Notification) -> dict:
    return {
        "id":             n.id,
        "type":           n.type,
        "title":          n.title,
        "message":        n.message,
        "requisition_id": n.requisition_id,
        "read":           n.read,
        "created_at":     n.created_at.isoformat() if n.created_at else "",
    }


def _ensure_operational_alerts(db: Session):
    notifications = ensure_pending_invoice_notifications(db)
    if notifications:
        db.commit()
        push_all(notifications)


@router.get("/stream")
async def stream_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SSE stream de notificações para o usuário autenticado.

    Ao conectar (ou reconectar após queda), o servidor entrega imediatamente
    todas as notificações não lidas do banco como eventos iniciais — garantindo
    que nenhuma notificação seja perdida mesmo que o push em tempo real tenha
    ocorrido enquanto o cliente estava desconectado.
    """
    # Busca notificações não lidas do banco
    _ensure_operational_alerts(db)
    nao_lidas = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
        .order_by(Notification.created_at.asc())
        .limit(30)
        .all()
    )
    initial = [_orm_to_dict(n) for n in nao_lidas]

    # Admin e gerente recebem alertas de requisições paradas
    if current_user.role in (Role.ADMIN, Role.GERENTE):
        initial.extend(stuck_requisition_events(db))

    # Libera a conexão de banco ANTES de iniciar o stream.
    # O SSE fica aberto enquanto o usuário estiver logado; sem este close()
    # cada usuário conectado seguraria uma conexão do pool indefinidamente,
    # esgotando o pool (pool_size=10) com ~10 usuários simultâneos.
    db.close()

    return StreamingResponse(
        sse_manager.event_stream(current_user.id, initial),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/", response_model=List[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna as 50 notificações não lidas mais recentes do usuário."""
    _ensure_operational_alerts(db)
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna a contagem de notificações não lidas."""
    _ensure_operational_alerts(db)
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.read == False,
        )
        .count()
    )
    return {"count": count}


@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca todas as notificações do usuário como lidas."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.read == False,
    ).update({"read": True})
    db.commit()
    return {"ok": True}


@router.patch("/{notif_id}/read")
def mark_one_read(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca uma notificação específica como lida."""
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id,
    ).first()
    if n:
        n.read = True
        db.commit()
    return {"ok": True}
