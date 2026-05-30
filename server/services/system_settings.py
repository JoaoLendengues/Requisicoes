from __future__ import annotations

import json
from pathlib import Path


_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "system_settings.json"
_DEFAULTS = {
    "pending_invoice_alert_days": 1,
    "min_delivery_business_days": 0,
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
    return data


def save_operational_settings(
    *,
    pending_invoice_alert_days: int | None = None,
    min_delivery_business_days: int | None = None,
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
    _SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return data


def get_pending_invoice_alert_days() -> int:
    return int(load_operational_settings()["pending_invoice_alert_days"])


def get_min_delivery_business_days() -> int:
    return int(load_operational_settings()["min_delivery_business_days"])
