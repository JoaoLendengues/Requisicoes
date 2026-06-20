from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Delivery(Base):
    """Entrega avulsa criada diretamente pela Central de Entregas."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    city: Mapped[str] = mapped_column(String(120))
    truck_name: Mapped[str] = mapped_column(String(120))
    loaded_by: Mapped[str] = mapped_column(String(150))
    delivery_date: Mapped[date] = mapped_column(Date, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deadline_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline_change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    client = relationship("Client", foreign_keys=[client_id])
    vendor = relationship("User", foreign_keys=[vendor_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

