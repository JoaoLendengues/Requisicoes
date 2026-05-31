"""Modelo de operador — cadastro central de nomes independente de usuários."""
from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class OperatorRole(str, enum.Enum):
    OPERADOR = "operador"
    AJUDANTE = "ajudante"


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[OperatorRole] = mapped_column(
        SAEnum(
            OperatorRole,
            values_callable=lambda values: [item.value for item in values],
            native_enum=False,
        ),
        default=OperatorRole.OPERADOR,
        server_default=OperatorRole.OPERADOR.value,
    )
