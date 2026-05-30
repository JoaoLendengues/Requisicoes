"""
Persistência das configurações de backup em backup_settings.json
(mesmo padrão do system_settings_service.py).
"""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "backup_settings.json"

_DEFAULTS: dict = {
    "daily_enabled":     True,
    "weekly_enabled":    True,
    "monthly_enabled":   False,
    "daily_hour":        2,       # 0-23
    "retention_daily":   15,      # arquivos a manter
    "retention_weekly":  8,
    "retention_monthly": 6,
}


def _clamp(value: object, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def load_backup_settings() -> dict:
    data = dict(_DEFAULTS)
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        raw = {}

    data["daily_enabled"]     = bool(raw.get("daily_enabled",     _DEFAULTS["daily_enabled"]))
    data["weekly_enabled"]    = bool(raw.get("weekly_enabled",    _DEFAULTS["weekly_enabled"]))
    data["monthly_enabled"]   = bool(raw.get("monthly_enabled",   _DEFAULTS["monthly_enabled"]))
    data["daily_hour"]        = _clamp(raw.get("daily_hour",        _DEFAULTS["daily_hour"]),        0,  23,  2)
    data["retention_daily"]   = _clamp(raw.get("retention_daily",   _DEFAULTS["retention_daily"]),   1, 365, 15)
    data["retention_weekly"]  = _clamp(raw.get("retention_weekly",  _DEFAULTS["retention_weekly"]),  1,  52,  8)
    data["retention_monthly"] = _clamp(raw.get("retention_monthly", _DEFAULTS["retention_monthly"]), 1,  24,  6)
    return data


def save_backup_settings(payload: dict) -> dict:
    current = load_backup_settings()
    if "daily_enabled"     in payload: current["daily_enabled"]     = bool(payload["daily_enabled"])
    if "weekly_enabled"    in payload: current["weekly_enabled"]    = bool(payload["weekly_enabled"])
    if "monthly_enabled"   in payload: current["monthly_enabled"]   = bool(payload["monthly_enabled"])
    if "daily_hour"        in payload: current["daily_hour"]        = _clamp(payload["daily_hour"],        0,  23,  2)
    if "retention_daily"   in payload: current["retention_daily"]   = _clamp(payload["retention_daily"],   1, 365, 15)
    if "retention_weekly"  in payload: current["retention_weekly"]  = _clamp(payload["retention_weekly"],  1,  52,  8)
    if "retention_monthly" in payload: current["retention_monthly"] = _clamp(payload["retention_monthly"], 1,  24,  6)
    _SETTINGS_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return current
