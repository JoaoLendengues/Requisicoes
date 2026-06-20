"""
Cache in-memory simples com TTL.

Usado nos endpoints de leitura mais acessados (Dashboard, Central de
Pedidos, Central de Entregas) onde o mesmo usuário fica clicando
"Atualizar" várias vezes seguidas — não faz sentido recomputar tudo
em 2 segundos se nada mudou.

Por que in-memory e não Redis:
- Pinheiro Indústria roda em UM único servidor (uvicorn)
- Não precisa de cache compartilhado entre processos
- Zero dependência externa
- TTLs curtos (15-60s) limitam o risco de inconsistência

Por que com TTL e não invalidação por evento:
- Invalidação por evento é mais complexa (tem que mapear quais writes
  afetam quais caches)
- TTL curto (30s) é "auto-correção" — máximo 30s de defasagem
- Em troca de aceitar esse atraso curto, eliminamos 90%+ dos GETs
  caros (clique em "Atualizar" 5x em 30s = 1 query + 4 cache hits)

Concorrência: dict do Python tem operações atomicas thread-safe para
gets/sets de chaves individuais (CPython GIL). Não precisamos de
Lock — em pior caso 2 threads recomputam ao mesmo tempo logo após
expiração (raro e inofensivo).
"""
from __future__ import annotations

import time
from typing import Any, Callable


_cache: dict[str, tuple[float, Any]] = {}


def get_or_set(key: str, ttl_seconds: float, compute: Callable[[], Any]) -> Any:
    """Retorna valor cacheado se ainda valido, senao recomputa via `compute()`.

    Uso típico:
        result = get_or_set(
            f"dashboard:{user_id}:{period}",
            ttl_seconds=30,
            compute=lambda: _build_management_dashboard(...),
        )
    """
    now = time.monotonic()
    entry = _cache.get(key)
    if entry is not None and entry[0] > now:
        return entry[1]

    value = compute()
    _cache[key] = (now + ttl_seconds, value)
    return value


def invalidate(prefix: str = "") -> int:
    """Remove entradas que começam com o prefixo (ou TUDO se prefix='').

    Útil em writes que afetam várias entradas:
        # ao criar/atualizar requisicao
        invalidate("order_center:")
        invalidate("delivery_center:")
        invalidate("dashboard:")

    Retorna quantas entradas foram removidas.
    """
    if not prefix:
        n = len(_cache)
        _cache.clear()
        return n
    to_remove = [k for k in _cache if k.startswith(prefix)]
    for k in to_remove:
        del _cache[k]
    return len(to_remove)


def stats() -> dict:
    """Diagnostico do cache para o painel tecnico ou debug."""
    now = time.monotonic()
    total = len(_cache)
    expired = sum(1 for _, (exp, _) in _cache.items() if exp <= now)
    return {"total": total, "valid": total - expired, "expired": expired}


# ── Invalidacao automatica em commits ────────────────────────────────────────
# Registra listener no SQLAlchemy Session: a cada commit que tenha alterado
# tabelas relacionadas a requisicoes, invalida os caches de leitura.
#
# Por que assim: mais robusto que chamada manual em cada endpoint de escrita.
# Mesmo que esqueçamos de invalidar em um novo endpoint, o listener pega.
#
# Custo: a cada commit no app, executa um check rapido nos objetos da session.
# Se nao ha mudanca em Requisition/RequisitionItem/RequisitionProductionSplit/
# StatusHistory, nao invalida nada.
def _install_session_listener() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    # Tabelas que disparam invalidacao quando alteradas
    _RELEVANT_TABLES = {
        "requisitions",
        "requisition_items",
        "requisition_production_splits",
        "status_history",
        "canvas_data",
        "deliveries",
    }

    @event.listens_for(Session, "before_commit")
    def _invalidate_on_relevant_commit(session: Session) -> None:  # type: ignore[no-untyped-def]
        # Usamos before_commit em vez de after_commit porque after_commit
        # esvazia session.new/dirty/deleted antes de chamar o listener.
        # Se o commit falhar, o cache ja foi invalidado — impacto e apenas
        # 1 cache miss no proximo read, irrelevante.
        try:
            for obj in list(session.new) + list(session.dirty) + list(session.deleted):
                table_name = getattr(getattr(obj, "__table__", None), "name", None)
                if table_name in _RELEVANT_TABLES:
                    invalidate("order_center:")
                    invalidate("delivery_center:")
                    invalidate("dashboard:")
                    invalidate("production_summary:")
                    return  # uma invalidacao basta por commit
        except Exception:
            # Nunca derruba o commit por causa de cache
            pass


# Instala o listener na importacao do modulo. Idempotente — SQLAlchemy permite
# registrar o mesmo listener varias vezes mas executa uma vez por evento.
_install_session_listener()
