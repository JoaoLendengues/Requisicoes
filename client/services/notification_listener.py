import json
import httpx
from PySide6.QtCore import QThread, Signal

from ..core.session import session
from ..core.resolution import res


class NotificationListener(QThread):
    notification_received = Signal(dict)
    connected = Signal()
    disconnected = Signal()

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
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                }
                with self._client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 401:
                        break  # token expirado — para sem retry
                    self.connected.emit()
                    for line in resp.iter_lines():
                        if not self._running:
                            break
                        if line.startswith("data: "):
                            raw = line[6:].strip()
                            try:
                                data = json.loads(raw)
                                if data.get("type") != "connected":
                                    self.notification_received.emit(data)
                            except json.JSONDecodeError:
                                pass
            except Exception:
                if self._running:
                    self.disconnected.emit()
                    self.msleep(3000)  # aguarda antes de reconectar
            finally:
                c = self._client
                self._client = None
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
        self.wait(2000)
