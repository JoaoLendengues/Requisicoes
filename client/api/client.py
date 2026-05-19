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


def get_me() -> dict:
    with _cli() as client:
        return _check(client.get("/auth/me"))


def list_users() -> list:
    with _cli() as client:
        return _check(client.get("/users/"))


def create_user(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/users/", json=data))


def update_user(user_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/users/{user_id}", json=data))


def deactivate_user(user_id: int):
    with _cli() as client:
        _check(client.delete(f"/users/{user_id}"))


def list_clients(search: str = "", limit: int = 30) -> list:
    with _cli() as client:
        params: dict = {"limit": limit}
        if search:
            params["search"] = search
        return _check(client.get("/clients/", params=params))


def get_client(client_id: int) -> dict:
    with _cli() as client:
        return _check(client.get(f"/clients/{client_id}"))


def create_client(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/clients/", json=data))


def update_client(client_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/clients/{client_id}", json=data))


def bulk_import_clients(items: list) -> dict:
    with _cli() as client:
        return _check(client.post("/clients/bulk-import", json=items, timeout=120))


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
        return _check(client.post("/products/bulk-import", json=items, timeout=120))


def list_requisitions(status: str = "", search: str = "",
                      skip: int = 0, limit: int = 50) -> list:
    with _cli() as client:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return _check(client.get("/requisitions/", params=params))


def get_management_dashboard() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/dashboard/summary"))


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


def update_canvas(req_id: int, json_data: str) -> dict:
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/canvas",
            json={"json_data": json_data},
        ))


def health_check(server_url: str) -> bool:
    try:
        resp = httpx.get(f"{server_url.rstrip('/')}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False
