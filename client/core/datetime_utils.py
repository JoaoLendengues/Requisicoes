from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


try:
    LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo or timezone.utc


def local_now() -> datetime:
    return datetime.now(LOCAL_TIMEZONE)


def parse_datetime(value: object, *, assume_utc_for_naive: bool = True) -> datetime | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        if _is_date_only(value):
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
        elif assume_utc_for_naive:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)

    return parsed.astimezone(LOCAL_TIMEZONE)


def format_datetime(value: object) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "-"
    return parsed.strftime("%d/%m/%Y %H:%M")


def format_date(value: object) -> str:
    if value is None or value == "":
        return "-"

    if isinstance(value, datetime):
        return format_datetime(value)[:10]

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    text = str(value).strip()
    if not text:
        return "-"

    if "T" in text or " " in text:
        formatted = format_datetime(text)
        return formatted[:10] if formatted != "-" else "-"

    try:
        parsed_date = date.fromisoformat(text)
    except ValueError:
        return text[:10]
    return parsed_date.strftime("%d/%m/%Y")


def format_header_date(value: object | None = None) -> str:
    current = parse_datetime(value) if value is not None else local_now()
    if current is None:
        current = local_now()
    return current.strftime("%d/%m/%Y")


def _is_date_only(value: object) -> bool:
    if isinstance(value, date) and not isinstance(value, datetime):
        return True
    text = str(value).strip()
    return "T" not in text and " " not in text and len(text) <= 10
