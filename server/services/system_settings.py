from __future__ import annotations

import json
from pathlib import Path


_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "system_settings.json"
_DEFAULTS = {
    "pending_invoice_alert_days": 1,
    "min_delivery_business_days": 0,
    "cancel_reasons": [
        {"code": "C01", "reason": "Cliente desistiu do pedido"},
        {"code": "C02", "reason": "Cliente alterou o projeto"},
        {"code": "C03", "reason": "Pedido duplicado"},
        {"code": "C04", "reason": "Medidas incorretas"},
        {"code": "C05", "reason": "Quantidade incorreta"},
        {"code": "C06", "reason": "Desenho técnico incorreto"},
        {"code": "C07", "reason": "Falta de informações técnicas"},
        {"code": "C08", "reason": "Material indisponível"},
        {"code": "C09", "reason": "Equipamento indisponível"},
        {"code": "C10", "reason": "Obra cancelada"},
        {"code": "C11", "reason": "Requisição enviada incorretamente"},
        {"code": "C12", "reason": "Falta de aprovação interna"},
        {"code": "C13", "reason": "Problema logístico"},
        {"code": "C14", "reason": "Produção inviável"},
    ],
    "delivery_cancel_reasons": [
        {"code": "CE001", "reason": "Cliente alterou o pedido"},
        {"code": "CE002", "reason": "Cliente nao estava disponivel para recebimento"},
        {"code": "CE003", "reason": "Endereco informado incorretamente"},
        {"code": "CE004", "reason": "Solicitacao de adiamento da entrega"},
        {"code": "CE005", "reason": "Producao nao finalizada no prazo"},
        {"code": "CE006", "reason": "Produto com defeito identificado antes da entrega"},
        {"code": "CE007", "reason": "Material indisponivel para conclusao do pedido"},
        {"code": "CE008", "reason": "Necessidade de retrabalho na producao"},
        {"code": "CE009", "reason": "Divergencia entre pedido e produto fabricado"},
        {"code": "CE010", "reason": "Falta de veiculo disponivel"},
        {"code": "CE011", "reason": "Problema mecanico no transporte"},
        {"code": "CE012", "reason": "Rota interrompida por condicoes externas"},
        {"code": "CE013", "reason": "Erro no planejamento da entrega"},
        {"code": "CE014", "reason": "Excesso de carga programada"},
        {"code": "CE015", "reason": "Pedido duplicado"},
        {"code": "CE016", "reason": "Falha de comunicacao com o cliente"},
        {"code": "CE017", "reason": "Dados da entrega incompletos"},
        {"code": "CE018", "reason": "Falta de aprovacao interna"},
        {"code": "CE019", "reason": "Documento obrigatorio nao anexado"},
        {"code": "CE020", "reason": "Cancelamento por decisao da gerencia"},
        {"code": "CE021", "reason": "Requisicao aberta indevidamente"},
        {"code": "CE022", "reason": "Mudanca de prioridade da producao"},
        {"code": "CE023", "reason": "Erro de integracao do sistema"},
        {"code": "CE024", "reason": "Cliente solicitou retirada no local"},
        {"code": "CE025", "reason": "Cliente reagendou a entrega"},
        {"code": "CE026", "reason": "Falta de contato com o cliente"},
        {"code": "CE027", "reason": "Horario de recebimento indisponivel"},
        {"code": "CE028", "reason": "Equipe de entrega indisponivel"},
        {"code": "CE029", "reason": "Endereco fora da rota de entrega"},
        {"code": "CE030", "reason": "Veiculo em manutencao"},
        {"code": "CE031", "reason": "Aguardando liberacao de acesso no local"},
        {"code": "CE032", "reason": "Aguardando confirmacao do cliente"},
        {"code": "CE033", "reason": "Produto indisponivel em estoque"},
        {"code": "CE034", "reason": "Divergencia de informacoes do pedido"},
        {"code": "CE035", "reason": "Entrega unificada com outro pedido"},
    ],
    "delivery_deadline_change_reasons": [
        {"code": "AP001", "reason": "Cliente solicitou alteracao da data"},
        {"code": "AP002", "reason": "Cliente nao disponivel na data programada"},
        {"code": "AP003", "reason": "Alteracao no pedido pelo cliente"},
        {"code": "AP004", "reason": "Inclusao de itens no pedido"},
        {"code": "AP005", "reason": "Mudanca de endereco de entrega"},
        {"code": "AP006", "reason": "Aguardando confirmacao do cliente"},
        {"code": "AP007", "reason": "Producao em atraso"},
        {"code": "AP008", "reason": "Necessidade de retrabalho na producao"},
        {"code": "AP009", "reason": "Material em falta"},
        {"code": "AP010", "reason": "Aguardando materia-prima"},
        {"code": "AP011", "reason": "Equipamento de producao em manutencao"},
        {"code": "AP012", "reason": "Capacidade produtiva comprometida"},
        {"code": "AP013", "reason": "Priorizacao de pedidos urgentes"},
        {"code": "AP014", "reason": "Ajustes tecnicos no produto"},
        {"code": "AP015", "reason": "Necessidade de aprovacao interna"},
        {"code": "AP016", "reason": "Veiculo indisponivel"},
        {"code": "AP017", "reason": "Problema mecanico no transporte"},
        {"code": "AP018", "reason": "Reorganizacao da rota de entrega"},
        {"code": "AP019", "reason": "Excesso de entregas programadas"},
        {"code": "AP020", "reason": "Falta de motorista"},
        {"code": "AP021", "reason": "Condicoes climaticas adversas"},
        {"code": "AP022", "reason": "Bloqueios ou interdicoes na rota"},
        {"code": "AP023", "reason": "Problemas operacionais na logistica"},
        {"code": "AP024", "reason": "Aguardando documentacao"},
        {"code": "AP025", "reason": "Divergencia de informacoes do pedido"},
        {"code": "AP026", "reason": "Erro de programacao da entrega"},
        {"code": "AP027", "reason": "Necessidade de conferencia adicional"},
        {"code": "AP028", "reason": "Falha no sistema"},
        {"code": "AP029", "reason": "Solicitacao da gerencia"},
        {"code": "AP030", "reason": "Replanejamento operacional"},
        {"code": "AP031", "reason": "Aguardando liberacao financeira"},
        {"code": "AP032", "reason": "Integracao com outro pedido"},
        {"code": "AP033", "reason": "Necessidade de carga complementar"},
        {"code": "AP034", "reason": "Ajuste de cronograma da obra"},
        {"code": "AP035", "reason": "Solicitacao do responsavel pela obra"},
    ],
}


def _sanitize_pending_invoice_alert_days(value: object) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = int(_DEFAULTS["pending_invoice_alert_days"])
    return max(1, min(days, 3650))


def _sanitize_min_delivery_business_days(value: object) -> int:
    """Prazo mínimo de entrega em dias úteis. 0 = sem restrição."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = int(_DEFAULTS["min_delivery_business_days"])
    return max(0, min(days, 365))


def _sanitize_cancel_reasons(value: object) -> list[dict[str, str]]:
    raw_items = value if isinstance(value, list) else _DEFAULTS["cancel_reasons"]
    cleaned: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = " ".join(str(item.get("code") or "").upper().split())
        reason = " ".join(str(item.get("reason") or "").split())
        if not code or not reason or code in seen_codes:
            continue
        seen_codes.add(code)
        cleaned.append({"code": code, "reason": reason})

    if cleaned:
        return cleaned
    return [dict(entry) for entry in _DEFAULTS["cancel_reasons"]]


def _sanitize_delivery_cancel_reasons(value: object) -> list[dict[str, str]]:
    raw_items = (
        value if isinstance(value, list) else _DEFAULTS["delivery_cancel_reasons"]
    )
    custom_by_code: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = " ".join(str(item.get("code") or "").upper().split())
        reason = " ".join(str(item.get("reason") or "").split())
        if code and reason:
            custom_by_code[code] = reason

    ordered: list[dict[str, str]] = []
    for default_item in _DEFAULTS["delivery_cancel_reasons"]:
        code = str(default_item.get("code") or "").strip().upper()
        if not code:
            continue
        reason = custom_by_code.get(code) or str(default_item.get("reason") or "").strip()
        if not reason:
            continue
        ordered.append({"code": code, "reason": reason})
    return ordered


def _sanitize_delivery_deadline_change_reasons(value: object) -> list[dict[str, str]]:
    raw_items = (
        value if isinstance(value, list) else _DEFAULTS["delivery_deadline_change_reasons"]
    )
    custom_by_code: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = " ".join(str(item.get("code") or "").upper().split())
        reason = " ".join(str(item.get("reason") or "").split())
        if code and reason:
            custom_by_code[code] = reason

    ordered: list[dict[str, str]] = []
    for default_item in _DEFAULTS["delivery_deadline_change_reasons"]:
        code = str(default_item.get("code") or "").strip().upper()
        if not code:
            continue
        reason = custom_by_code.get(code) or str(default_item.get("reason") or "").strip()
        if not reason:
            continue
        ordered.append({"code": code, "reason": reason})
    return ordered


def load_operational_settings() -> dict:
    data = dict(_DEFAULTS)
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        raw = {}

    data["pending_invoice_alert_days"] = _sanitize_pending_invoice_alert_days(
        raw.get("pending_invoice_alert_days", data["pending_invoice_alert_days"])
    )
    data["min_delivery_business_days"] = _sanitize_min_delivery_business_days(
        raw.get("min_delivery_business_days", data["min_delivery_business_days"])
    )
    data["cancel_reasons"] = _sanitize_cancel_reasons(
        raw.get("cancel_reasons", data["cancel_reasons"])
    )
    data["delivery_cancel_reasons"] = _sanitize_delivery_cancel_reasons(
        raw.get("delivery_cancel_reasons", data["delivery_cancel_reasons"])
    )
    data["delivery_deadline_change_reasons"] = _sanitize_delivery_deadline_change_reasons(
        raw.get(
            "delivery_deadline_change_reasons",
            data["delivery_deadline_change_reasons"],
        )
    )
    return data


def save_operational_settings(
    *,
    pending_invoice_alert_days: int | None = None,
    min_delivery_business_days: int | None = None,
    cancel_reasons: list[dict[str, str]] | None = None,
    delivery_cancel_reasons: list[dict[str, str]] | None = None,
    delivery_deadline_change_reasons: list[dict[str, str]] | None = None,
) -> dict:
    """Atualiza apenas os campos informados, preservando os demais."""
    data = load_operational_settings()
    if pending_invoice_alert_days is not None:
        data["pending_invoice_alert_days"] = _sanitize_pending_invoice_alert_days(
            pending_invoice_alert_days
        )
    if min_delivery_business_days is not None:
        data["min_delivery_business_days"] = _sanitize_min_delivery_business_days(
            min_delivery_business_days
        )
    if cancel_reasons is not None:
        data["cancel_reasons"] = _sanitize_cancel_reasons(cancel_reasons)
    if delivery_cancel_reasons is not None:
        data["delivery_cancel_reasons"] = _sanitize_delivery_cancel_reasons(
            delivery_cancel_reasons
        )
    if delivery_deadline_change_reasons is not None:
        data["delivery_deadline_change_reasons"] = _sanitize_delivery_deadline_change_reasons(
            delivery_deadline_change_reasons
        )
    _SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return data


def get_pending_invoice_alert_days() -> int:
    return int(load_operational_settings()["pending_invoice_alert_days"])


def get_min_delivery_business_days() -> int:
    return int(load_operational_settings()["min_delivery_business_days"])
