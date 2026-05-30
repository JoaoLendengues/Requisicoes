"""
audit_service.py
================
Funções auxiliares para registro de auditoria.

Nenhuma função aqui faz commit — o chamador é responsável por commitar
junto com as demais mudanças da mesma transação.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from ..models.audit import AuditLog, LoginAttempt

if TYPE_CHECKING:
    from ..models.user import User


def log_action(
    db: Session,
    *,
    entity: str,
    entity_id: int,
    action: str,
    changed_by: "User | None" = None,
    changes: dict | None = None,
) -> None:
    """
    Registra uma ação de auditoria na tabela audit_log.

    Parâmetros:
      entity      — nome da entidade afetada ('requisition', 'user', 'client', …)
      entity_id   — ID do registro
      action      — 'CREATE' | 'UPDATE' | 'DELETE'
      changed_by  — objeto User que realizou a ação (None = ação de sistema)
      changes     — dict com as mudanças, ex:
                    {
                      "delivery_date": {"old": "2025-05-01", "new": "2025-05-10"},
                      "obs": {"old": None, "new": "Urgente"}
                    }
                    Para CREATE/DELETE pode ser um resumo dos campos principais.
    """
    db.add(AuditLog(
        entity=entity,
        entity_id=entity_id,
        action=action,
        changed_by_id=changed_by.id if changed_by else None,
        changed_by_name=changed_by.name if changed_by else None,
        changes=json.dumps(changes, default=str, ensure_ascii=False) if changes else None,
        timestamp=datetime.utcnow(),
    ))


def log_login(
    db: Session,
    *,
    code: str,
    success: bool,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Registra uma tentativa de login na tabela login_attempts.

    Parâmetros:
      code        — código digitado pelo usuário
      success     — True se autenticação bem-sucedida, False se falhou
      user_id     — ID do usuário (apenas quando success=True e usuário existe)
      ip_address  — endereço IP do cliente (pode ser None se não disponível)
    """
    db.add(LoginAttempt(
        user_code=(code or "").strip().upper(),
        user_id=user_id,
        success=success,
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
    ))


def diff_fields(old_obj, new_data: dict, fields: list[str]) -> dict:
    """
    Compara campos de um objeto ORM com novos valores e retorna
    apenas os que mudaram, no formato {campo: {old: x, new: y}}.

    Útil para construir o dict de `changes` antes de aplicar o update.

    Exemplo:
      changes = diff_fields(user, update_data, ["name", "role", "is_active"])
    """
    result = {}
    for field in fields:
        if field not in new_data:
            continue
        old_val = getattr(old_obj, field, None)
        new_val = new_data[field]
        if str(old_val) != str(new_val):
            result[field] = {
                "old": str(old_val) if old_val is not None else None,
                "new": str(new_val) if new_val is not None else None,
            }
    return result
