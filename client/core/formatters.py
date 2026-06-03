from __future__ import annotations


def parse_decimal(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None

    text = str(value).strip()
    if not text or text == "-":
        return None

    text = text.replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text:
        dot_parts = text.split(".")
        if len(dot_parts) > 1 and all(part.isdigit() for part in dot_parts) and all(
            len(part) == 3 for part in dot_parts[1:]
        ):
            text = "".join(dot_parts)
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def format_decimal_br(
    value: object,
    *,
    decimals: int = 2,
    fallback: str = "-",
    clamp_min: float | None = None,
    strip_zero_decimals: bool = False,
) -> str:
    parsed = parse_decimal(value)
    if parsed is None:
        return fallback

    if clamp_min is not None and parsed < clamp_min:
        parsed = clamp_min

    decimals = max(0, int(decimals))
    formatted = f"{parsed:,.{decimals}f}"
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")

    if strip_zero_decimals and decimals > 0:
        formatted = formatted.rstrip("0").rstrip(",")
    return formatted


def format_weight_kg(
    value: object,
    *,
    decimals: int = 2,
    fallback: str = "-",
) -> str:
    return format_decimal_br(
        value,
        decimals=decimals,
        fallback=fallback,
        clamp_min=0.0,
    )
