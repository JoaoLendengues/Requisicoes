import httpx
from ..core.session import session
from ..core.resolution import res


def _url() -> str:
    return res.server_url.rstrip("/")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if session.token:
        h["Authorization"] = f"Bearer {session.token}"
    return h


def _cli() -> httpx.Client:
    return httpx.Client(base_url=_url(), headers=_headers(), timeout=15.0)


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


# ── Auth ──────────────────────────────────────────────────────────────────────
def login(code: str, password: str) -> dict:
    with _cli() as c:
        return _check(c.post("/auth/login", json={"code": code, "password": password}))


def get_me() -> dict:
    with _cli() as c:
        return _check(c.get("/auth/me"))


# ── Usuários ──────────────────────────────────────────────────────────────────
def list_users() -> list:
    with _cli() as c:
        return _check(c.get("/users/"))


def create_user(data: dict) -> dict:
    with _cli() as c:
        return _check(c.post("/users/", json=data))


def update_user(user_id: int, data: dict) -> dict:
    with _cli() as c:
        return _check(c.patch(f"/users/{user_id}", json=data))


def deactivate_user(user_id: int):
    with _cli() as c:
        _check(c.delete(f"/users/{user_id}"))


# ── Clientes ──────────────────────────────────────────────────────────────────
def list_clients(search: str = "", limit: int = 30) -> list:
    with _cli() as c:
        params: dict = {"limit": limit}
        if search:
            params["search"] = search
        return _check(c.get("/clients/", params=params))


def get_client(client_id: int) -> dict:
    with _cli() as c:
        return _check(c.get(f"/clients/{client_id}"))


def create_client(data: dict) -> dict:
    with _cli() as c:
        return _check(c.post("/clients/", json=data))


def update_client(client_id: int, data: dict) -> dict:
    with _cli() as c:
        return _check(c.patch(f"/clients/{client_id}", json=data))


def bulk_import_clients(items: list) -> dict:
    """Importa uma lista de clientes em lote (uma única chamada HTTP)."""
    with _cli() as c:
        return _check(c.post("/clients/bulk-import", json=items,
                             timeout=120))   # planilhas grandes podem demorar


# ── Requisições ───────────────────────────────────────────────────────────────
def list_requisitions(status: str = "", search: str = "",
                      skip: int = 0, limit: int = 50) -> list:
    with _cli() as c:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return _check(c.get("/requisitions/", params=params))


def get_requisition(req_id: int) -> dict:
    with _cli() as c:
        return _check(c.get(f"/requisitions/{req_id}"))


def create_requisition(data: dict) -> dict:
    with _cli() as c:
        return _check(c.post("/requisitions/", json=data))


def update_requisition(req_id: int, data: dict) -> dict:
    with _cli() as c:
        return _check(c.patch(f"/requisitions/{req_id}", json=data))


def update_status(req_id: int, status: str, note: str = "") -> dict:
    with _cli() as c:
        return _check(c.patch(
            f"/requisitions/{req_id}/status",
            json={"status": status, "note": note},
        ))


def update_canvas(req_id: int, json_data: str) -> dict:
    with _cli() as c:
        return _check(c.patch(
            f"/requisitions/{req_id}/canvas",
            json={"json_data": json_data},
        ))


def health_check(server_url: str) -> bool:
    try:
        resp = httpx.get(f"{server_url.rstrip('/')}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False
