from __future__ import annotations

import json
from pathlib import Path


_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "system_settings.json"
_DEFAULTS = {
    "pending_invoice_alert_days": 1,
}


def _sanitize_pending_invoice_alert_days(value: object) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = int(_DEFAULTS["pending_invoice_alert_days"])
    return max(1, min(days, 3650))


def load_operational_settings() -> dict:
    data = dict(_DEFAULTS)
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        raw = {}

    data["pending_invoice_alert_days"] = _sanitize_pending_invoice_alert_days(
        raw.get("pending_invoice_alert_days", data["pending_invoice_alert_days"])
    )
    return data


def save_operational_settings(*, pending_invoice_alert_days: int) -> dict:
    data = {
        "pending_invoice_alert_days": _sanitize_pending_invoice_alert_days(
            pending_invoice_alert_days
        ),
    }
    _SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return data


def get_pending_invoice_alert_days() -> int:
    return int(load_operational_settings()["pending_invoice_alert_days"])
