from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditLog(Base):
    """
    Registro genérico de auditoria para CREATE / UPDATE / DELETE em qualquer entidade.

    Campos:
      entity        — nome da tabela afetada (ex: 'requisition', 'user', 'client')
      entity_id     — ID do registro afetado
      action        — 'CREATE' | 'UPDATE' | 'DELETE'
      changed_by_id — FK para users (nullable: ações automáticas do sistema)
      changed_by_name — nome desnormalizado (preserva histórico após deleção de usuário)
      changes       — JSON com {campo: {old: valor, new: valor}} para UPDATE;
                      resumo de campos relevantes para CREATE/DELETE
      timestamp     — quando ocorreu
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    entity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    changed_by_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class LoginAttempt(Base):
    """
    Registro de todas as tentativas de login — bem-sucedidas e com falha.

    Permite detectar ataques de força bruta, auditar acessos
    e rastrear o histórico completo de autenticação por usuário.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
