from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_delivery_handler
from ..models.avulse_delivery import AvulseDelivery
from ..models.client import Client
from ..models.user import User
from ..schemas.avulse_delivery import (
    AvulseCancellation,
    AvulseDeliveryCreate,
    AvulseDeliveryResponse,
)
from ..services.audit_service import log_action

router = APIRouter(prefix="/avulse-deliveries", tags=["Entregas Avulsas"])


def _to_response(rec: AvulseDelivery) -> AvulseDeliveryResponse:
    return AvulseDeliveryResponse.model_validate(rec)


@router.post("/", response_model=AvulseDeliveryResponse)
def create_avulse_delivery(
    data: AvulseDeliveryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    client = db.get(Client, data.client_id)
    if not client:
        raise HTTPException(404, "Cliente não encontrado")

    vendor = db.get(User, data.vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendedor não encontrado")

    rec = AvulseDelivery(
        client_id=data.client_id,
        client_name=client.name,
        vendor_id=data.vendor_id,
        vendor_name=vendor.name,
        delivery_date=data.delivery_date,
        description=data.description,
        weight=data.weight,
        created_by_id=current_user.id,
    )
    db.add(rec)
    db.flush()
    log_action(
        db,
        entity="avulse_delivery",
        entity_id=rec.id,
        action="CREATE",
        changed_by=current_user,
        changes={"client": client.name, "delivery_date": str(data.delivery_date)},
    )
    db.commit()
    db.refresh(rec)
    return _to_response(rec)


@router.get("/", response_model=list[AvulseDeliveryResponse])
def list_avulse_deliveries(
    db: Session = Depends(get_db),
    _: User = Depends(require_delivery_handler),
):
    recs = (
        db.query(AvulseDelivery)
        .order_by(AvulseDelivery.delivery_date.asc(), AvulseDelivery.id.asc())
        .all()
    )
    return [_to_response(r) for r in recs]


@router.patch("/{avulse_id}/mark-delivered", response_model=AvulseDeliveryResponse)
def mark_avulse_delivered(
    avulse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    rec = db.get(AvulseDelivery, avulse_id)
    if not rec:
        raise HTTPException(404, "Entrega avulsa não encontrada")
    if rec.cancelled_at:
        raise HTTPException(400, "Esta entrega está cancelada")
    if rec.delivered_at:
        raise HTTPException(400, "Esta entrega já foi marcada como entregue")

    rec.delivered_at = datetime.utcnow()
    log_action(
        db,
        entity="avulse_delivery",
        entity_id=avulse_id,
        action="UPDATE",
        changed_by=current_user,
        changes={"delivered_at": rec.delivered_at.isoformat()},
    )
    db.commit()
    db.refresh(rec)
    return _to_response(rec)


@router.patch("/{avulse_id}/cancel", response_model=AvulseDeliveryResponse)
def cancel_avulse_delivery(
    avulse_id: int,
    data: AvulseCancellation,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    rec = db.get(AvulseDelivery, avulse_id)
    if not rec:
        raise HTTPException(404, "Entrega avulsa não encontrada")
    if rec.cancelled_at:
        raise HTTPException(400, "Esta entrega já está cancelada")

    rec.cancelled_at = datetime.utcnow()
    rec.cancel_reason = data.reason
    log_action(
        db,
        entity="avulse_delivery",
        entity_id=avulse_id,
        action="UPDATE",
        changed_by=current_user,
        changes={"cancelled_at": rec.cancelled_at.isoformat(), "cancel_reason": data.reason},
    )
    db.commit()
    db.refresh(rec)
    return _to_response(rec)
