from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.feedback import Feedback, FeedbackCategory, FeedbackStatus
from ..models.notification import Notification
from ..models.user import Role, User
from ..schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackStatusUpdate
from ..services.notification_service import dispatch as push_all

router = APIRouter(prefix="/feedbacks", tags=["Feedbacks"])


_STATUS_LABEL = {
    FeedbackStatus.NOVA:       "Nova",
    FeedbackStatus.EM_ANALISE: "Em análise",
    FeedbackStatus.RESOLVIDA:  "Resolvida",
    FeedbackStatus.DESCARTADA: "Descartada",
}

_CATEGORY_LABEL = {
    FeedbackCategory.BUG:      "Bug",
    FeedbackCategory.PROBLEMA: "Problema",
    FeedbackCategory.SUGESTAO: "Sugestão",
    FeedbackCategory.ELOGIO:   "Elogio",
}


def _feedback_to_out(db: Session, fb: Feedback) -> FeedbackOut:
    user = db.query(User).filter(User.id == fb.user_id).first()
    read_by = db.query(User).filter(User.id == fb.read_by_id).first() if fb.read_by_id else None
    return FeedbackOut(
        id=fb.id,
        user_id=fb.user_id,
        user_name=(user.name if user else f"Usuario #{fb.user_id}"),
        message=fb.message,
        category=fb.category,
        status=fb.status,
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
    if len(text) > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Limite de 1000 caracteres.")

    fb = Feedback(
        user_id=current_user.id,
        message=text,
        category=data.category,
        status=FeedbackStatus.NOVA,
    )
    db.add(fb)
    db.flush()  # garante fb.id antes das notificações

    # Notifica TODOS os admins ativos (exceto o próprio remetente, se for admin)
    admins = (
        db.query(User)
        .filter(User.role == Role.ADMIN, User.is_active.is_(True), User.id != current_user.id)
        .all()
    )
    cat_label = _CATEGORY_LABEL.get(data.category, str(data.category))
    sender_name = current_user.name or f"Usuário #{current_user.id}"
    preview = text if len(text) <= 80 else text[:77] + "..."
    notifications: list[Notification] = []
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            type="feedback_new",
            title=f"Novo feedback ({cat_label})",
            message=f"{sender_name}: {preview}",
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


@router.get("/", response_model=list[FeedbackOut])
def list_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos os feedbacks. Apenas admin."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    rows = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .all()
    )
    return [_feedback_to_out(db, row) for row in rows]


@router.get("/mine", response_model=list[FeedbackOut])
def list_my_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de feedbacks enviados pelo próprio usuário autenticado."""
    rows = (
        db.query(Feedback)
        .filter(Feedback.user_id == current_user.id)
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .all()
    )
    return [_feedback_to_out(db, row) for row in rows]


@router.patch("/{feedback_id}/status", response_model=FeedbackOut)
def update_feedback_status(
    feedback_id: int,
    data: FeedbackStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin muda o status. A cada mudança o autor é notificado."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )

    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback não encontrado.")

    new_status = data.status
    if fb.status == new_status:
        return _feedback_to_out(db, fb)

    fb.status = new_status

    # Marca a 1ª "leitura" do admin quando deixar de ser "nova"
    if new_status != FeedbackStatus.NOVA and fb.read_at is None:
        fb.read_at = datetime.utcnow()
        fb.read_by_id = current_user.id

    # Notifica o autor a cada mudança de status
    notifications: list[Notification] = []
    if fb.user_id and fb.user_id != current_user.id:
        label = _STATUS_LABEL.get(new_status, str(new_status))
        notif = Notification(
            user_id=fb.user_id,
            type="feedback_status",
            title=f"Feedback: {label}",
            message=f"Seu feedback foi marcado como {label.lower()}.",
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


# ── Compatibilidade: mantém o endpoint antigo /ack mapeando para o novo ──────
@router.patch("/{feedback_id}/ack", response_model=FeedbackOut)
def acknowledge_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Endpoint legado — mapeia "marcar como lido" para status = EM_ANALISE."""
    return update_feedback_status(
        feedback_id,
        FeedbackStatusUpdate(status=FeedbackStatus.EM_ANALISE),
        db,
        current_user,
    )
