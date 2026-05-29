from __future__ import annotations
import enum
from datetime import datetime, date
from sqlalchemy import (
    String, Boolean, DateTime, Date, Float, Text,
    ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class RequisitionStatus(str, enum.Enum):
    EM_ANDAMENTO = "em_andamento"
    PRAZO_ALTERADO = "prazo_alterado"
    AGUARDANDO_RECEBIMENTO = "aguardando_recebimento"
    AGUARDANDO_NA_FILA = "aguardando_na_fila"
    AGUARDANDO_FATURAMENTO = "aguardando_faturamento"
    EM_PRODUCAO  = "em_producao"
    FATURADO     = "faturado"
    CANCELADA    = "cancelada"


class Requisition(Base):
    __tablename__ = "requisitions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ped_number: Mapped[str] = mapped_column(String(50), index=True)
    emission_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    os_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    vendor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))

    obra: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nf_attachment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retirada: Mapped[bool] = mapped_column(Boolean, default=False)
    entrega: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    obs: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[RequisitionStatus] = mapped_column(
        SAEnum(RequisitionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=RequisitionStatus.EM_ANDAMENTO,
    )
    production_destination: Mapped[str | None] = mapped_column(String(120), nullable=True)
    production_machine: Mapped[str | None] = mapped_column(String(255), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    vendor: Mapped[User] = relationship("User", foreign_keys=[vendor_id])
    client: Mapped[Client] = relationship("Client", back_populates="requisitions")

    @property
    def client_name(self) -> str | None:
        return self.client.name if self.client else None

    @property
    def client_code(self) -> str | None:
        return self.client.code if self.client else None

    @property
    def vendor_name(self) -> str | None:
        return self.vendor.name if self.vendor else None

    @property
    def vendor_code(self) -> str | None:
        return self.vendor.code if self.vendor else None

    items: Mapped[list[RequisitionItem]] = relationship(
        "RequisitionItem", back_populates="requisition", cascade="all, delete-orphan"
    )
    canvas: Mapped[CanvasData | None] = relationship(
        "CanvasData", back_populates="requisition", uselist=False, cascade="all, delete-orphan"
    )
    status_history: Mapped[list[StatusHistory]] = relationship(
        "StatusHistory", back_populates="requisition", cascade="all, delete-orphan"
    )


class RequisitionItem(Base):
    __tablename__ = "requisition_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("requisitions.id"))
    position: Mapped[str] = mapped_column(String(10))
    product_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    comp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    desenv: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chapa: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tipo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    draw_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    requisition: Mapped[Requisition] = relationship("Requisition", back_populates="items")


class CanvasData(Base):
    __tablename__ = "canvas_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("requisitions.id"), unique=True)
    json_data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    requisition: Mapped[Requisition] = relationship("Requisition", back_populates="canvas")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("requisitions.id"))
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    requisition: Mapped[Requisition] = relationship("Requisition", back_populates="status_history")
    changed_by: Mapped[User] = relationship("User", foreign_keys=[changed_by_id])
