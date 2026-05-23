from __future__ import annotations

from collections import deque
from datetime import date
from threading import Lock


_MAX_DURATION_SAMPLES = 1000
_lock = Lock()
_current_day = date.today()
_durations_ms: deque[int] = deque(maxlen=_MAX_DURATION_SAMPLES)
_error_count_today = 0


def _rollover_if_needed() -> None:
    global _current_day, _error_count_today

    today = date.today()
    if today == _current_day:
        return

    _current_day = today
    _durations_ms.clear()
    _error_count_today = 0


def record_request(duration_ms: float, status_code: int) -> None:
    global _error_count_today

    with _lock:
        _rollover_if_needed()
        _durations_ms.append(max(0, int(duration_ms)))
        if status_code >= 400:
            _error_count_today += 1


def record_exception() -> None:
    global _error_count_today

    with _lock:
        _rollover_if_needed()
        _error_count_today += 1


def snapshot() -> dict[str, int | None]:
    with _lock:
        _rollover_if_needed()
        average_response_ms = None
        if _durations_ms:
            average_response_ms = int(sum(_durations_ms) / len(_durations_ms))

        return {
            "average_response_ms": average_response_ms,
            "error_count_today": _error_count_today,
            "request_count_today": len(_durations_ms),
        }
