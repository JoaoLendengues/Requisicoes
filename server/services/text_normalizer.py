from __future__ import annotations

import json

from ..database import SessionLocal
from ..models.client import Client
from ..models.product import Product
from ..models.requisition import CanvasData, Requisition, RequisitionItem
from ..models.user import User


def normalize_upper_text(value: object | None, *, empty_as_none: bool = True) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None if empty_as_none else ""
    return text.upper()


def normalize_upper_optional(value: object | None) -> str | None:
    return normalize_upper_text(value, empty_as_none=True)


def normalize_upper_required(value: object | None) -> str:
    return normalize_upper_text(value, empty_as_none=False) or ""


def normalize_canvas_json_text(json_data: str | None) -> str | None:
    if json_data is None:
        return None

    try:
        payload = json.loads(json_data)
    except (TypeError, ValueError, json.JSONDecodeError):
        return json_data

    changed = False
    for item in payload.get("items", []):
        if not isinstance(item, dict) or item.get("type") != "text":
            continue

        current = item.get("text", "")
        normalized = normalize_upper_required(current)
        if normalized != current:
            item["text"] = normalized
            changed = True

    if not changed:
        return json_data
    return json.dumps(payload, ensure_ascii=False)


def _normalize_attr(instance: object, field_name: str, *, required: bool) -> bool:
    current = getattr(instance, field_name)
    normalized = (
        normalize_upper_required(current)
        if required
        else normalize_upper_optional(current)
    )
    if normalized == current:
        return False
    setattr(instance, field_name, normalized)
    return True


def normalize_existing_user_written_data() -> int:
    changes = 0

    with SessionLocal() as db:
        for req in db.query(Requisition).all():
            for field_name in ("os_number", "obra", "delivery_address", "obs"):
                changes += int(_normalize_attr(req, field_name, required=False))

        for item in db.query(RequisitionItem).all():
            changes += int(_normalize_attr(item, "position", required=True))
            for field_name in (
                "product_code",
                "product_name",
                "comp",
                "desenv",
                "chapa",
                "tipo",
                "draw_ref",
            ):
                changes += int(_normalize_attr(item, field_name, required=False))

        for canvas in db.query(CanvasData).all():
            normalized_json = normalize_canvas_json_text(canvas.json_data)
            if normalized_json != canvas.json_data:
                canvas.json_data = normalized_json or "{}"
                changes += 1

        for user in db.query(User).all():
            changes += int(_normalize_attr(user, "code", required=True))
            changes += int(_normalize_attr(user, "name", required=True))
            changes += int(_normalize_attr(user, "sector", required=False))

        for client in db.query(Client).all():
            changes += int(_normalize_attr(client, "code", required=True))
            changes += int(_normalize_attr(client, "name", required=True))
            for field_name in ("address", "city", "state"):
                changes += int(_normalize_attr(client, field_name, required=False))

        for product in db.query(Product).all():
            changes += int(_normalize_attr(product, "code", required=True))
            changes += int(_normalize_attr(product, "name", required=True))

        if changes:
            db.commit()

    return changes
