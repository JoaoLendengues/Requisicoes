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


def change_password(current_password: str, new_password: str) -> dict:
    with _cli() as client:
        return _check(client.post(
            "/auth/change-password",
            json={"current_password": current_password, "new_password": new_password},
        ))


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


def create_client(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/clients/", json=data))


def update_client(client_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/clients/{client_id}", json=data))


def deactivate_client(client_id: int):
    with _cli() as client:
        _check(client.delete(f"/clients/{client_id}"))


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
    vendor_search: str = "",
    skip: int = 0,
    limit: int = 50,
    emission_date_start: str = "",
    emission_date_end: str = "",
    production_destination: str = "",
    production_machine: str = "",
    production_operator: str = "",
    invoiced: bool | None = None,
) -> list:
    with _cli() as client:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if vendor_search:
            params["vendor_search"] = vendor_search
        if emission_date_start:
            params["emission_date_start"] = emission_date_start
        if emission_date_end:
            params["emission_date_end"] = emission_date_end
        if production_destination:
            params["production_destination"] = production_destination
        if production_machine:
            params["production_machine"] = production_machine
        if production_operator:
            params["production_operator"] = production_operator
        if invoiced is not None:
            params["invoiced"] = invoiced
        return _check(client.get("/requisitions/", params=params))


def list_requisition_history_rows(
    status: str = "",
    search: str = "",
    vendor_search: str = "",
    skip: int = 0,
    limit: int = 100,
    emission_date_start: str = "",
    emission_date_end: str = "",
    production_destination: str = "",
    production_machine: str = "",
    production_operator: str = "",
    invoiced: bool | None = None,
) -> list:
    with _cli() as client:
        params: dict = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if vendor_search:
            params["vendor_search"] = vendor_search
        if emission_date_start:
            params["emission_date_start"] = emission_date_start
        if emission_date_end:
            params["emission_date_end"] = emission_date_end
        if production_destination:
            params["production_destination"] = production_destination
        if production_machine:
            params["production_machine"] = production_machine
        if production_operator:
            params["production_operator"] = production_operator
        if invoiced is not None:
            params["invoiced"] = invoiced
        return _check(client.get("/requisitions/history/rows", params=params))


def get_management_dashboard(
    ar_period: str = "30d",
    industria_period: str = "30d",
    performance_period: str = "month",
    performance_date_start: str | None = None,
    performance_date_end: str | None = None,
    performance_destination: str = "",
    comparison_destination: str = "",
    people_period: str = "30d",
    people_destination: str = "",
) -> dict:
    params = {
        "ar_period": ar_period,
        "industria_period": industria_period,
        "performance_period": performance_period,
        "performance_destination": performance_destination,
        "comparison_destination": comparison_destination,
        "people_period": people_period,
        "people_destination": people_destination,
    }
    if performance_date_start:
        params["performance_date_start"] = performance_date_start
    if performance_date_end:
        params["performance_date_end"] = performance_date_end
    with _cli() as client:
        return _check(
            client.get(
                "/requisitions/dashboard/summary",
                params=params,
            )
        )


def get_technical_panel_summary() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/technical-panel/summary"))


def get_order_center() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/order-center/summary"))


def get_delivery_center() -> dict:
    with _cli() as client:
        return _check(client.get("/requisitions/deliveries/summary"))


def get_operational_settings() -> dict:
    with _cli() as client:
        return _check(client.get("/system-settings/operational"))


def update_operational_settings(data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch("/system-settings/operational", json=data))


def list_production_machine_registry() -> list:
    with _cli() as client:
        return _check(client.get("/production-machines/"))


def create_production_machine(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/production-machines/", json=data))


def update_production_machine(machine_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/production-machines/{machine_id}", json=data))


def list_operators() -> list:
    with _cli() as client:
        return _check(client.get("/operators/"))


def create_operator(data: dict) -> dict:
    with _cli() as client:
        return _check(client.post("/operators/", json=data))


def update_operator(operator_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/operators/{operator_id}", json=data))


def delete_operator(operator_id: int):
    with _cli() as client:
        _check(client.delete(f"/operators/{operator_id}"))


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


def update_requisition_item_development(req_id: int, item_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(
            client.patch(
                f"/requisitions/{req_id}/items/{item_id}/development",
                json=data,
            )
        )


def update_status(req_id: int, status: str, note: str = "") -> dict:
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/status",
            json={"status": status, "note": note},
        ))


def create_production_split(req_id: int, data: dict) -> dict:
    with _cli() as client:
        return _check(client.post(f"/requisitions/{req_id}/production-splits", json=data))


def update_production_split_status(split_id: int, status: str, note: str = "") -> dict:
    with _cli() as client:
        return _check(
            client.patch(
                f"/requisitions/production-splits/{split_id}/status",
                json={"status": status, "note": note},
            )
        )


def regroup_production_splits(req_id: int) -> dict:
    with _cli() as client:
        return _check(client.post(f"/requisitions/{req_id}/production-splits/regroup"))


def update_delivery_date(req_id: int, delivery_date: str, reason: str) -> dict:
    """Produção altera o prazo de entrega com justificativa.
    delivery_date no formato ISO (YYYY-MM-DD)."""
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/delivery-date",
            json={"delivery_date": delivery_date, "reason": reason},
        ))


def update_delivery_date_and_resend(req_id: int, delivery_date: str, reason: str) -> dict:
    """Produção altera o prazo de entrega E reenvia para Aguardando Recebimento
    numa unica transacao no servidor. Substitui o par
    update_delivery_date + update_status que tinha race condition entre
    as duas chamadas HTTP (production_view._update_delivery_date_and_waiting_receipt).
    """
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/delivery-date-and-resend",
            json={"delivery_date": delivery_date, "reason": reason},
        ))


def update_delivery_schedule(req_id: int, delivery_date: str, reason: str) -> dict:
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/delivery-schedule",
            json={"delivery_date": delivery_date, "reason": reason},
        ))


def schedule_delivery(req_id: int, delivery_date: str) -> dict:
    """Agenda a data de entrega pela primeira vez (sem motivo). Notifica o vendedor."""
    with _cli() as client:
        return _check(client.patch(
            f"/requisitions/{req_id}/schedule-delivery",
            json={"delivery_date": delivery_date},
        ))


def lookup_requisitions_by_ped(search: str) -> list:
    """Busca requisicoes por numero de pedido para agendamento de entrega."""
    with _cli() as client:
        return _check(client.get(
            "/requisitions/history/rows",
            params={"search": search.strip(), "limit": 8},
        ))


def mark_delivery_delivered(req_id: int) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/requisitions/{req_id}/mark-delivered"))


def mark_split_delivery_delivered(split_id: int) -> dict:
    with _cli() as client:
        return _check(client.patch(f"/requisitions/production-splits/{split_id}/mark-delivered"))


def cancel_delivery_delivered(req_id: int, reason: str) -> dict:
    with _cli() as client:
        return _check(
            client.patch(
                f"/requisitions/{req_id}/cancel-delivered",
                json={"reason": reason},
            )
        )


def cancel_split_delivery_delivered(split_id: int, reason: str) -> dict:
    with _cli() as client:
        return _check(
            client.patch(
                f"/requisitions/production-splits/{split_id}/cancel-delivered",
                json={"reason": reason},
            )
        )


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


def delete_notification(notif_id: int) -> dict:
    with _cli() as client:
        return _check(client.delete(f"/notifications/{notif_id}"))


def create_feedback(message: str, category: str = "sugestao", is_public: bool = True) -> dict:
    with _cli() as client:
        return _check(
            client.post(
                "/feedbacks/",
                json={"message": message, "category": category, "is_public": is_public},
            )
        )


def list_feedbacks() -> list:
    """Admin: lista todos os feedbacks (públicos + privados)."""
    with _cli() as client:
        return _check(client.get("/feedbacks/"))


def list_my_feedbacks() -> list:
    """Qualquer usuário: lista os próprios feedbacks."""
    with _cli() as client:
        return _check(client.get("/feedbacks/mine"))


def list_public_feedbacks() -> list:
    """Qualquer usuário: feed público (feedbacks marcados como públicos)."""
    with _cli() as client:
        return _check(client.get("/feedbacks/public"))


def react_feedback(feedback_id: int, reaction: str | None) -> dict:
    """Reage com 'like' / 'dislike'. Passar None remove a reação."""
    with _cli() as client:
        return _check(
            client.post(
                f"/feedbacks/{feedback_id}/react",
                json={"reaction": reaction},
            )
        )


def get_feedback_unread_count() -> dict:
    """Quantidade de feedbacks públicos que o usuário ainda não leu."""
    with _cli() as client:
        return _check(client.get("/feedbacks/unread-count"))


def mark_feedbacks_read() -> dict:
    """Marca todos os feedbacks públicos visíveis como lidos."""
    with _cli() as client:
        return _check(client.post("/feedbacks/mark-read"))


def update_feedback_status(feedback_id: int, new_status: str) -> dict:
    """Admin: muda o status de um feedback (nova/em_analise/resolvida/descartada)."""
    with _cli() as client:
        return _check(
            client.patch(f"/feedbacks/{feedback_id}/status", json={"status": new_status})
        )


def acknowledge_feedback(feedback_id: int) -> dict:
    """Legado: marca feedback como "em análise" (mantido por compatibilidade)."""
    return update_feedback_status(feedback_id, "em_analise")


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


def get_backup_settings() -> dict:
    """Retorna as configurações de agendamento de backup."""
    with _cli() as client:
        return _check(client.get("/backup/settings"))


def update_backup_settings(payload: dict) -> dict:
    """Salva as configurações de agendamento de backup."""
    with _cli() as client:
        return _check(client.patch("/backup/settings", json=payload))
