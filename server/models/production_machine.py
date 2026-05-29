from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class MachineOperationalStatus(str, enum.Enum):
    FUNCIONANDO = "funcionando"
    MANUTENCAO = "manutencao"


production_machine_operators = Table(
    "production_machine_operators",
    Base.metadata,
    Column("machine_id", ForeignKey("production_machines.id", ondelete="CASCADE"), primary_key=True),
    Column("operator_id", ForeignKey("operators.id", ondelete="CASCADE"), primary_key=True),
)


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
            native_enum=False,
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
    operators = relationship(
        "Operator",
        secondary=production_machine_operators,
        order_by="Operator.name",
    )
