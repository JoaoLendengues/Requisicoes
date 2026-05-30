from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.feedback import Feedback
from ..models.notification import Notification
from ..models.user import Role, User
from ..schemas.feedback import FeedbackCreate, FeedbackOut
from ..services.notification_service import dispatch as push_all

router = APIRouter(prefix="/feedbacks", tags=["Feedbacks"])


def _feedback_to_out(db: Session, fb: Feedback) -> FeedbackOut:
    user = db.query(User).filter(User.id == fb.user_id).first()
    read_by = db.query(User).filter(User.id == fb.read_by_id).first() if fb.read_by_id else None
    return FeedbackOut(
        id=fb.id,
        user_id=fb.user_id,
        user_name=(user.name if user else f"Usuario #{fb.user_id}"),
        message=fb.message,
        created_at=fb.created_at,
        read_at=fb.read_at,
        read_by_id=fb.read_by_id,
        read_by_name=(read_by.name if read_by else None),
    )


@router.post("/", response_model=FeedbackOut)
def create_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    text = (data.message or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe uma mensagem.")
    if len(text) > 150:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Limite de 150 caracteres.")

    fb = Feedback(
        user_id=current_user.id,
        message=text,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return _feedback_to_out(db, fb)


@router.get("/", response_model=list[FeedbackOut])
def list_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    rows = db.query(Feedback).order_by(Feedback.created_at.asc(), Feedback.id.asc()).all()
    return [_feedback_to_out(db, row) for row in rows]


@router.patch("/{feedback_id}/ack", response_model=FeedbackOut)
def acknowledge_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )

    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback não encontrado.")

    can_notify_author = fb.read_at is None
    if can_notify_author:
        fb.read_at = datetime.utcnow()
        fb.read_by_id = current_user.id

    notifications: list[Notification] = []
    if can_notify_author and fb.user_id:
        notif = Notification(
            user_id=fb.user_id,
            type="feedback_read",
            title="Feedback em andamento",
            message="Seu feedback foi lido e está em processo de correção.",
            requisition_id=None,
        )
        db.add(notif)
        notifications.append(notif)

    db.commit()
    for notif in notifications:
        db.refresh(notif)
    push_all(notifications)

    db.refresh(fb)
    return _feedback_to_out(db, fb)
