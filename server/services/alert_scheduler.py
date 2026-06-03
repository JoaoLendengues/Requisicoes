"""
Scheduler asyncio para checagem periódica de alertas operacionais.

Antes (até Jun/2026): `_check_invoice_alerts(db)` era chamado em TODO GET
de `/dashboard/summary`, `/order-center/summary`, `/deliveries/summary`.
Cada chamada disparava 2 queries no banco + iteração sobre reqs em status
"aberto" + criação de notificações.

Como esses endpoints são acessados dezenas de vezes ao dia por 6 perfis,
isso somava sobrecarga no banco e latência em cada GET.

Agora: roda em background a cada 5 minutos. Os endpoints podem ler dados
já preparados sem disparar a checagem. Reduz latência média dos GETs
em ~30-50ms e centraliza o trabalho num único loop.
"""
from __future__ import annotations

import asyncio
import logging

from ..database import SessionLocal
from .notification_service import (
    dispatch as push_all,
    ensure_delivery_deadline_notifications,
    ensure_pending_invoice_notifications,
)

log = logging.getLogger(__name__)

# Intervalo entre execuções. 5 minutos é o sweet spot:
# - curto o bastante pra notificações chegarem em tempo razoável
# - longo o bastante pra não saturar o banco com queries repetidas
_INTERVAL_SECONDS = 300


def run_alert_check_once() -> int:
    """Executa uma checagem de alertas sincronamente.

    Retorna o número de notificações criadas (útil para logs/debug).
    Em caso de erro, registra warning e retorna 0 — não propaga exceção
    para não derrubar o scheduler.
    """
    db = SessionLocal()
    try:
        notifications: list = []
        notifications.extend(ensure_pending_invoice_notifications(db))
        notifications.extend(ensure_delivery_deadline_notifications(db))
        if notifications:
            db.commit()
            push_all(notifications)
        return len(notifications)
    except Exception as exc:  # noqa: BLE001
        log.warning("alert_check falhou: %s", exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()


async def alert_scheduler() -> None:
    """Task asyncio. Inicia no lifespan do FastAPI.

    Executa a primeira checagem após 30 segundos do boot (dá tempo do
    servidor estabilizar) e depois a cada _INTERVAL_SECONDS.
    """
    log.info("Scheduler de alertas operacionais iniciado.")
    await asyncio.sleep(30)  # primeiro ciclo após estabilização

    loop = asyncio.get_event_loop()
    while True:
        try:
            count = await loop.run_in_executor(None, run_alert_check_once)
            if count:
                log.info("Alertas operacionais: %d notificação(ões) criada(s).", count)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert_scheduler tick falhou: %s", exc, exc_info=True)
        await asyncio.sleep(_INTERVAL_SECONDS)
