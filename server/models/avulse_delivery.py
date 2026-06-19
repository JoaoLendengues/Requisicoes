from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AvulseDelivery(Base):
    __tablename__ = "avulse_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
