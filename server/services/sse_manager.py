import asyncio
import json
from collections import defaultdict
from typing import AsyncIterator

# user_id → lista de asyncio.Queue (uma por conexão SSE ativa)
_connections: dict[int, list] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def push_to_user(user_id: int, data: dict):
    """Envia notificação do contexto síncrono para as filas SSE do usuário."""
    if _loop is None or not _loop.is_running():
        print(f"[SSE] push_to_user: loop não disponível (loop={_loop})")
        return
    queues = list(_connections.get(user_id, []))
    print(f"[SSE] push_to_user: user_id={user_id} conexoes_ativas={len(queues)}")
    for q in queues:
        _loop.call_soon_threadsafe(q.put_nowait, data)


async def event_stream(
    user_id: int,
    initial_events: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Gerador assíncrono que produz eventos SSE formatados para o usuário."""
    global _loop
    _loop = asyncio.get_running_loop()

    queue: asyncio.Queue = asyncio.Queue()

    if initial_events:
        for evt in initial_events:
            await queue.put(evt)

    _connections[user_id].append(queue)
    try:
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {json.dumps(data, default=str)}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        try:
            _connections[user_id].remove(queue)
        except ValueError:
            pass
        if not _connections.get(user_id):
            _connections.pop(user_id, None)
