import threading

import httpx
from ..core.session import session
from ..core.resolution import res


def _url() -> str:
    return res.server_url.rstrip("/")


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if session.token:
        headers["Authorization"] = f"Bearer {session.token}"
    return headers


def _cli() -> httpx.Client:
    return httpx.Client(base_url=_url(), headers=_headers(), timeout=15.0)


# ── Pool de conexão persistente ───────────────────────────────────────────────
# httpx.Client é thread-safe para requisições concorrentes.  Reutilizar a
# conexão TCP elimina o handshake a cada keystroke (~5–20 ms numa LAN).
# Usado em list_clients/get_client (hot path da busca).  Outras funções
# continuam usando _cli() (curta duração, headers embutidos no construtor).

_pool_lock:     threading.Lock = threading.Lock()
_pool:          httpx.Client | None = None
_pool_base_url: str = ""


def _get_pool() -> httpx.Client:
    """Retorna o httpx.Client persistente, recriando se a URL do servidor mudou."""
    global _pool, _pool_base_url
    url = _url()
    # Fast path — sem adquirir lock se já está OK
    if _pool is not None and _pool_base_url == url and not _pool.is_closed:
        return _pool
    with _pool_lock:
        # Verifica de novo dentro do lock (outro thread pode ter recriado)
        if _pool is None or _pool_base_url != url or _pool.is_closed:
            if _pool is not None:
                try:
                    _pool.close()
                except Exception:
                    pass
            _pool = httpx.Client(base_url=url, timeout=10.0)
            _pool_base_url = url
    return _pool


class APIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _check(resp: httpx.Response):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise APIError(resp.status_code, str(detail))
    if resp.status_code == 204:
        return {}
    return resp.json()


def login(code: str, password: str) -> dict:
    with _cli() as client:
        return _check(client.post("/auth/login", json={"code": code, "password": password}))


def first_access(code: str, password: str) -> dict:
    with _cli() as client:
        return _check(client.post("/auth/first-access", json={"code": code, "password": password}))


def get_first_access_status(code: str) -> dict:
    with _cli() as client:
        return _check(client.get("/auth/first-access-status", params={"code": code}))


def get_me() -> dict:
    with _cli() as client:
        return _check(client.get("/auth/me"))


def list_users() -> list:
    with _cli() as client:
        return _check(client.get("/users/"))


def create_user(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/users/", json=data))


def bulk_import_users(items: list) -> dict:
    with _cli() as client:
        return _check(client.post("/users/import/bulk", json=items, timeout=120))


def update_user(user_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/users/{user_id}", json=data))


def deactivate_user(user_id: int):
    with _cli() as client:
        _check(client.delete(f"/users/{user_id}"))


def list_clients(search: str = "", limit: int = 30) -> list:
    # Pool persistente: sem handshake TCP por keystroke
    params: dict = {"limit": limit}
    if search:
        params["search"] = search
    return _check(_get_pool().get("/clients/", params=params, headers=_headers()))


def get_client(client_id: int) -> dict:
    return _check(_get_pool().get(f"/clients/{client_id}", headers=_headers()))


def bulk_import_clients(items: list) -> dict:
    with _cli() as client:
        return _check(client.post("/clients/import/bulk", json=items, timeout=120))


def list_products(search: str = "", code: str = "", limit: int = 30) -> list:
    with _cli() as client:
        params: dict = {"limit": limit}
        if search:
            params["search"] = search
        if code:
            params["code"] = code
        return _check(client.get("/products/", params=params))


def bulk_import_products(items: list) -> dict:
    with _cli() as client:
        return _check(client.post("/products/import/bulk", json=items, timeout=120))


def list_requisitions(
    status: str = "",
    search: str = "",
    skip: int = 0,
    limit: int = 50,
    emission_date_start: str = "",
    emission_date_end: str = "",
    production_destination: str = "",
    production_machine: str = "",
    invoiced: bool | None = None,
) -> list:
    with _cli() as client:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if emission_date_start:
            params["emission_date_start"] = emission_date_start
        if emission_date_end:
            params["emission_date_end"] = emission_date_end
        if production_destination:
            params["production_destination"] = production_destination
        if production_machine:
            params["production_machine"] = production_machine
        if invoiced is not None:
            params["invoiced"] = invoiced
        return _check(client.get("/requisitions/", params=params))


def get_management_dashboard() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/dashboard/summary"))


def get_technical_panel_summary() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/technical-panel/summary"))


def get_order_center() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/order-center/summary"))


def get_operational_settings() -> dict:
    with _cli() as client:
        return _check(client.get("/system-settings/operational"))


def update_operational_settings(data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch("/system-settings/operational", json=data))


def get_production_summary(destination: str) -> dict:
    with _cli() as client:
        return _check(
            client.get(
                "/requisitions/production/summary",
                params={"destination": destination},
            )
        )


def get_production_machines(destination: str) -> list:
    with _cli() as client:
        return _check(
            client.get(
                "/requisitions/production/machines",
                params={"destination": destination},
            )
        )


def get_requisition(req_id: int) -> dict:
    with _cli() as client:
        return _check(client.get(f"/requisitions/{req_id}"))


def create_requisition(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/requisitions/", json=data))


def update_requisition(req_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/requisitions/{req_id}", json=data))


def update_status(req_id: int, status: str, note: str = "") -> dict:
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/status",
            json={"status": status, "note": note},
        ))


def update_production_machine_status(machine_id: int, status: str) -> dict:
    with _cli() as client:
        return _check(
            client.patch(
                f"/requisitions/production/machines/{machine_id}/status",
                json={"status": status},
            )
        )


def update_canvas(req_id: int, json_data: str) -> dict:
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/canvas",
            json={"json_data": json_data},
        ))


def notification_unread_count() -> dict:
    with _cli() as client:
        return _check(client.get("/notifications/count"))


def list_notifications() -> list:
    with _cli() as client:
        return _check(client.get("/notifications/"))


def mark_all_notifications_read() -> dict:
    with _cli() as client:
        return _check(client.patch("/notifications/read-all"))


def mark_one_notification_read(notif_id: int) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/notifications/{notif_id}/read"))


def create_feedback(message: str) -> dict:
    with _cli() as client:
        return _check(client.post("/feedbacks/", json={"message": message}))


def list_feedbacks() -> list:
    with _cli() as client:
        return _check(client.get("/feedbacks/"))


def acknowledge_feedback(feedback_id: int) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/feedbacks/{feedback_id}/ack"))


def health_check(server_url: str) -> bool:
    try:
        resp = httpx.get(f"{server_url.rstrip('/')}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


# ── Backup ────────────────────────────────────────────────────────────────────

def trigger_backup() -> dict:
    """Dispara backup manual no servidor. Retorna o resultado do run_backup."""
    with _cli() as client:
        return _check(client.post("/backup/run"))


def list_backups() -> list:
    """Retorna lista de backups existentes no servidor."""
    with _cli() as client:
        return _check(client.get("/backup/list"))
