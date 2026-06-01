from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.feedback import (
    Feedback,
    FeedbackCategory,
    FeedbackReaction,
    FeedbackRead,
    FeedbackStatus,
)
from ..models.notification import Notification
from ..models.user import Role, User
from ..schemas.feedback import (
    FeedbackCreate,
    FeedbackOut,
    FeedbackReactionUpdate,
    FeedbackStatusUpdate,
    FeedbackUnreadCount,
)
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reaction_counts(db: Session, feedback_ids: list[int]) -> dict[int, tuple[int, int]]:
    """Retorna {feedback_id: (likes, dislikes)} em uma única query."""
    if not feedback_ids:
        return {}
    rows = (
        db.query(
            FeedbackReaction.feedback_id,
            func.sum(case((FeedbackReaction.reaction == "like", 1), else_=0)).label("likes"),
            func.sum(case((FeedbackReaction.reaction == "dislike", 1), else_=0)).label("dislikes"),
        )
        .filter(FeedbackReaction.feedback_id.in_(feedback_ids))
        .group_by(FeedbackReaction.feedback_id)
        .all()
    )
    return {row.feedback_id: (int(row.likes or 0), int(row.dislikes or 0)) for row in rows}


def _my_reactions(db: Session, feedback_ids: list[int], user_id: int) -> dict[int, str]:
    """Retorna {feedback_id: 'like'|'dislike'} para o user_id atual."""
    if not feedback_ids:
        return {}
    rows = (
        db.query(FeedbackReaction.feedback_id, FeedbackReaction.reaction)
        .filter(
            FeedbackReaction.feedback_id.in_(feedback_ids),
            FeedbackReaction.user_id == user_id,
        )
        .all()
    )
    return {row.feedback_id: row.reaction for row in rows}


def _serialize_list(db: Session, rows: list[Feedback], current_user: User) -> list[FeedbackOut]:
    if not rows:
        return []

    # Mapas auxiliares em batch
    user_ids = {fb.user_id for fb in rows} | {fb.read_by_id for fb in rows if fb.read_by_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    ids = [fb.id for fb in rows]
    counts = _reaction_counts(db, ids)
    mine = _my_reactions(db, ids, current_user.id)

    out: list[FeedbackOut] = []
    for fb in rows:
        likes, dislikes = counts.get(fb.id, (0, 0))
        u = users.get(fb.user_id)
        rb = users.get(fb.read_by_id) if fb.read_by_id else None
        out.append(
            FeedbackOut(
                id=fb.id,
                user_id=fb.user_id,
                user_name=(u.name if u else f"Usuario #{fb.user_id}"),
                message=fb.message,
                category=fb.category,
                status=fb.status,
                is_public=bool(fb.is_public),
                created_at=fb.created_at,
                read_at=fb.read_at,
                read_by_id=fb.read_by_id,
                read_by_name=(rb.name if rb else None),
                likes=likes,
                dislikes=dislikes,
                my_reaction=mine.get(fb.id),
            )
        )
    return out


# ── Criação ───────────────────────────────────────────────────────────────────

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
        is_public=bool(data.is_public),
    )
    db.add(fb)
    db.flush()

    # Notifica todos os admins ativos (exceto o próprio remetente, se for admin)
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
    return _serialize_list(db, [fb], current_user)[0]


# ── Listagens ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[FeedbackOut])
def list_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista TODOS os feedbacks (público + privado). Apenas admin."""
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
    return _serialize_list(db, rows, current_user)


@router.get("/mine", response_model=list[FeedbackOut])
def list_my_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de feedbacks enviados pelo próprio usuário."""
    rows = (
        db.query(Feedback)
        .filter(Feedback.user_id == current_user.id)
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .all()
    )
    return _serialize_list(db, rows, current_user)


@router.get("/public", response_model=list[FeedbackOut])
def list_public_feedbacks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Feed público — qualquer usuário autenticado vê os feedbacks marcados como públicos."""
    rows = (
        db.query(Feedback)
        .filter(Feedback.is_public.is_(True))
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .all()
    )
    return _serialize_list(db, rows, current_user)


# ── Reações ───────────────────────────────────────────────────────────────────

@router.post("/{feedback_id}/react", response_model=FeedbackOut)
def react_feedback(
    feedback_id: int,
    data: FeedbackReactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback não encontrado.")
    # Autor não pode reagir no próprio feedback
    if fb.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode reagir no próprio feedback.",
        )

    existing = (
        db.query(FeedbackReaction)
        .filter(
            FeedbackReaction.feedback_id == feedback_id,
            FeedbackReaction.user_id == current_user.id,
        )
        .first()
    )
    new_value = data.reaction

    if new_value is None:
        if existing:
            db.delete(existing)
    elif existing:
        if existing.reaction == new_value:
            # Clicou no mesmo botão de novo → remove (toggle off)
            db.delete(existing)
        else:
            existing.reaction = new_value
    else:
        db.add(FeedbackReaction(
            feedback_id=feedback_id,
            user_id=current_user.id,
            reaction=new_value,
        ))

    db.commit()
    db.refresh(fb)
    return _serialize_list(db, [fb], current_user)[0]


# ── Contador e marcação de leitura ────────────────────────────────────────────

@router.get("/unread-count", response_model=FeedbackUnreadCount)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Conta feedbacks PÚBLICOS que o usuário ainda não marcou como lidos.
    Exclui os próprios feedbacks do usuário (não conta como novidade).
    """
    # feedback_id que o usuário já leu
    read_ids = db.query(FeedbackRead.feedback_id).filter(
        FeedbackRead.user_id == current_user.id
    ).subquery()

    count = (
        db.query(func.count(Feedback.id))
        .filter(
            Feedback.is_public.is_(True),
            Feedback.user_id != current_user.id,
            ~Feedback.id.in_(read_ids),
        )
        .scalar()
        or 0
    )
    return FeedbackUnreadCount(unread=int(count))


@router.post("/mark-read", response_model=FeedbackUnreadCount)
def mark_feedbacks_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca todos os feedbacks públicos visíveis como lidos para o usuário atual."""
    # IDs públicos que ainda não foram lidos
    already_read = db.query(FeedbackRead.feedback_id).filter(
        FeedbackRead.user_id == current_user.id
    ).subquery()

    pending = (
        db.query(Feedback.id)
        .filter(
            Feedback.is_public.is_(True),
            Feedback.user_id != current_user.id,
            ~Feedback.id.in_(already_read),
        )
        .all()
    )

    now = datetime.utcnow()
    for (fb_id,) in pending:
        db.add(FeedbackRead(feedback_id=int(fb_id), user_id=current_user.id, read_at=now))

    db.commit()
    return FeedbackUnreadCount(unread=0)


# ── Mudança de status (admin) ─────────────────────────────────────────────────

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
        return _serialize_list(db, [fb], current_user)[0]

    fb.status = new_status
    if new_status != FeedbackStatus.NOVA and fb.read_at is None:
        fb.read_at = datetime.utcnow()
        fb.read_by_id = current_user.id

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
    return _serialize_list(db, [fb], current_user)[0]


# ── Compatibilidade: endpoint antigo /ack ─────────────────────────────────────

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
