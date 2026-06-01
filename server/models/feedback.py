from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class FeedbackCategory(str, enum.Enum):
    BUG      = "bug"
    PROBLEMA = "problema"
    SUGESTAO = "sugestao"
    ELOGIO   = "elogio"


class FeedbackStatus(str, enum.Enum):
    NOVA        = "nova"
    EM_ANALISE  = "em_analise"
    RESOLVIDA   = "resolvida"
    DESCARTADA  = "descartada"


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)

    category: Mapped[FeedbackCategory] = mapped_column(
        SAEnum(
            FeedbackCategory,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
        ),
        default=FeedbackCategory.SUGESTAO,
        server_default=FeedbackCategory.SUGESTAO.value,
        nullable=False,
        index=True,
    )
    status: Mapped[FeedbackStatus] = mapped_column(
        SAEnum(
            FeedbackStatus,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
        ),
        default=FeedbackStatus.NOVA,
        server_default=FeedbackStatus.NOVA.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
