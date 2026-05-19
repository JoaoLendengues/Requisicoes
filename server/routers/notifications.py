from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models.notification import Notification
from ..models.user import User, Role
from ..schemas.notification import NotificationResponse
from ..dependencies import get_current_user
from ..services import sse_manager
from ..services.notification_service import stuck_requisition_events

router = APIRouter(prefix="/notifications", tags=["Notificações"])


@router.get("/stream")
async def stream_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initial: list[dict] = []
    if current_user.role in (Role.ADMIN, Role.GERENTE):
        initial = stuck_requisition_events(db)

    return StreamingResponse(
        sse_manager.event_stream(current_user.id, initial),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read == False)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read == False)
        .count()
    )
    return {"count": count}


@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.read == False,
    ).update({"read": True})
    db.commit()
    return {"ok": True}


@router.patch("/{notif_id}/read")
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id,
    ).first()
    if n:
        n.read = True
        db.commit()
    return {"ok": True}
