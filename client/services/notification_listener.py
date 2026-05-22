"""
QThread que mantém uma conexão SSE aberta com o servidor.

Emite notification_received(dict) para cada evento recebido,
ignorando apenas o evento de controle 'connected'.
Reconecta automaticamente a cada 3s em caso de falha.
Para definitivamente ao receber 401 (token expirado/inválido).
"""
import json

import httpx
from PySide6.QtCore import QThread, Signal

from ..core.resolution import res
from ..core.session import session


class NotificationListener(QThread):
    notification_received = Signal(dict)
    connected             = Signal()
    disconnected          = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._client: httpx.Client | None = None

    def run(self):
        url = f"{res.server_url.rstrip('/')}/notifications/stream"

        while self._running:
            self._client = None
            try:
                self._client = httpx.Client(
                    timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
                )
                headers = {
                    "Authorization": f"Bearer {session.token}",
                    "Accept":        "text/event-stream",
                    "Cache-Control": "no-cache",
                }
                with self._client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 401:
                        break  # token inválido — para sem retry

                    self.connected.emit()

                    for line in resp.iter_lines():
                        if not self._running:
                            break
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if data.get("type") == "connected":
                            continue  # evento de controle interno
                        self.notification_received.emit(data)

            except Exception:
                if self._running:
                    self.disconnected.emit()
                    self.msleep(3_000)   # aguarda 3s antes de reconectar
            finally:
                c, self._client = self._client, None
                if c:
                    try:
                        c.close()
                    except Exception:
                        pass

    def stop(self):
        self._running = False
        c = self._client
        if c:
            try:
                c.close()
            except Exception:
                pass
        self.quit()
        self.wait(2_000)
