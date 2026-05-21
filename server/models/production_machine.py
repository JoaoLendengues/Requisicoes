from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class MachineOperationalStatus(str, enum.Enum):
    FUNCIONANDO = "funcionando"
    MANUTENCAO = "manutencao"


class ProductionMachine(Base):
    __tablename__ = "production_machines"
    __table_args__ = (
        UniqueConstraint(
            "destination",
            "name",
            name="uq_production_machines_destination_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    destination: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[MachineOperationalStatus] = mapped_column(
        SAEnum(
            MachineOperationalStatus,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=MachineOperationalStatus.FUNCIONANDO,
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    updated_by = relationship("User", foreign_keys=[updated_by_id])
