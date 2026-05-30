from __future__ import annotations
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id:             Mapped[int]      = mapped_column(primary_key=True, index=True)
    user_id:        Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    type:           Mapped[str]      = mapped_column(String(50),  nullable=False)
    title:          Mapped[str]      = mapped_column(String(200), nullable=False)
    message:        Mapped[str]      = mapped_column(Text,        nullable=False)
    requisition_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    read:           Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    created_at:     Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
