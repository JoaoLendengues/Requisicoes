"""
Gerenciador de conexões SSE (Server-Sent Events).

Cada usuário conectado tem uma ou mais asyncio.Queue associadas.
push_to_user() pode ser chamado de contexto síncrono (thread pool do FastAPI)
e usa call_soon_threadsafe para enfileirar eventos no loop asyncio correto.
"""
import asyncio
import json
from collections import defaultdict
from typing import AsyncIterator

# user_id → lista de filas (uma por aba / instância conectada)
_queues: dict[int, list[asyncio.Queue]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def connected_user_ids() -> list[int]:
    return list(_queues.keys())


def push_to_user(user_id: int, data: dict) -> None:
    """Envia um evento SSE para todas as conexões ativas do usuário."""
    if _loop is None or not _loop.is_running():
        return
    for q in list(_queues.get(user_id, [])):
        _loop.call_soon_threadsafe(q.put_nowait, data)


async def event_stream(
    user_id: int,
    initial_events: list[dict] | None = None,
) -> AsyncIterator[str]:
    """
    Gerador assíncrono de eventos SSE para um usuário.

    Ao conectar:
    1. Envia evento 'connected' de confirmação
    2. Entrega todos os eventos iniciais (notificações não lidas do banco)
    3. Fica aguardando novos eventos em tempo real
    4. Envia heartbeat a cada 25s para manter a conexão viva
    """
    global _loop
    _loop = asyncio.get_running_loop()

    queue: asyncio.Queue = asyncio.Queue()
    _queues[user_id].append(queue)

    try:
        # Confirmação de conexão
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        # Entrega eventos iniciais (não lidas do banco)
        for evt in (initial_events or []):
            yield f"data: {json.dumps(evt, default=str)}\n\n"

        # Loop principal: aguarda novos eventos
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {json.dumps(data, default=str)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    finally:
        try:
            _queues[user_id].remove(queue)
        except ValueError:
            pass
        if not _queues.get(user_id):
            _queues.pop(user_id, None)
