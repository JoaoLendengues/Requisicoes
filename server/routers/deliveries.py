from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..dependencies import require_delivery_handler
from ..models.client import Client
from ..models.delivery import Delivery
from ..models.user import Role, User
from ..schemas.delivery import (
    DeliveryCancellationUpdate,
    DeliveryCreate,
    DeliveryResponse,
    DeliveryScheduleUpdate,
    DeliveryVendorResponse,
)
from ..models.notification import Notification
from ..services.audit_service import log_action
from ..services import sse_manager


router = APIRouter(prefix="/deliveries", tags=["Entregas"])


def _is_active_vendor(user: User | None) -> bool:
    if user is None or not bool(user.is_active):
        return False
    role_value = str(getattr(user.role, "value", user.role) or "").strip().lower()
    return role_value == Role.VENDEDOR.value


def _response(delivery: Delivery) -> DeliveryResponse:
    return DeliveryResponse(
        id=delivery.id,
        client_id=delivery.client_id,
        client_code=delivery.client.code,
        client_name=delivery.client.name,
        vendor_id=delivery.vendor_id,
        vendor_name=delivery.vendor.name,
        city=delivery.city,
        truck_name=delivery.truck_name,
        loaded_by=delivery.loaded_by,
        weight=delivery.weight,
        delivery_date=delivery.delivery_date,
        delivered_at=delivery.delivered_at,
        deadline_changed_at=delivery.deadline_changed_at,
        deadline_change_reason=delivery.deadline_change_reason,
        created_at=delivery.created_at,
    )


def _get_delivery(db: Session, delivery_id: int) -> Delivery:
    delivery = (
        db.query(Delivery)
        .options(selectinload(Delivery.client), selectinload(Delivery.vendor))
        .filter(Delivery.id == delivery_id)
        .first()
    )
    if delivery is None:
        raise HTTPException(status_code=404, detail="Entrega nao encontrada")
    return delivery


def _ensure_can_edit(delivery: Delivery, current_user: User) -> None:
    if current_user.role in (Role.ADMIN, Role.GERENTE, Role.ENTREGA, Role.ENTREGAS):
        return
    if current_user.role == Role.VENDEDOR and delivery.vendor_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Sem permissao para alterar esta entrega")


@router.get("/vendors", response_model=list[DeliveryVendorResponse])
def list_delivery_vendors(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_delivery_handler),
):
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    vendors = [user for user in users if _is_active_vendor(user)]
    vendors.sort(key=lambda user: (str(user.name or "").casefold(), str(user.code or "").casefold()))
    return vendors


@router.post("/", response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(
    data: DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    client = (
        db.query(Client)
        .filter(Client.id == data.client_id, Client.is_active == True)  # noqa: E712
        .first()
    )
    if client is None:
        raise HTTPException(status_code=400, detail="Cliente nao encontrado ou inativo")

    vendor = (
        db.query(User)
        .filter(
            User.id == data.vendor_id,
            User.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not _is_active_vendor(vendor):
        raise HTTPException(status_code=400, detail="Vendedor nao encontrado ou inativo")

    delivery = Delivery(
        client_id=client.id,
        vendor_id=vendor.id,
        created_by_id=current_user.id,
        city=data.city,
        truck_name=data.truck_name,
        loaded_by=data.loaded_by,
        weight=data.weight,
        delivery_date=data.delivery_date,
    )
    delivery.client = client
    delivery.vendor = vendor
    db.add(delivery)
    db.flush()
    log_action(
        db,
        entity="delivery",
        entity_id=delivery.id,
        action="CREATE",
        changed_by=current_user,
        changes={
            "client_code": client.code,
            "vendor": vendor.name,
            "city": delivery.city,
            "truck_name": delivery.truck_name,
            "loaded_by": delivery.loaded_by,
            "weight": delivery.weight,
            "delivery_date": delivery.delivery_date.isoformat(),
        },
    )
    db.commit()
    db.refresh(delivery)

    # Notifica o vendedor que uma entrega foi criada para o cliente dele
    date_str = delivery.delivery_date.strftime("%d/%m/%Y") if delivery.delivery_date else "data a definir"
    notif = Notification(
        user_id=vendor.id,
        type="delivery_created",
        title="Entrega Agendada 🚚",
        message=f"Uma entrega para {client.name} foi agendada para {date_str}.",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    sse_manager.push_to_user(vendor.id, {
        "id": notif.id,
        "type": notif.type,
        "title": notif.title,
        "message": notif.message,
        "requisition_id": None,
        "read": False,
        "created_at": notif.created_at.isoformat(),
    })

    return _response(delivery)


@router.patch("/{delivery_id}/schedule", response_model=DeliveryResponse)
def update_delivery_schedule(
    delivery_id: int,
    data: DeliveryScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    delivery = _get_delivery(db, delivery_id)
    _ensure_can_edit(delivery, current_user)
    if delivery.delivered_at is not None:
        raise HTTPException(status_code=400, detail="Esta entrega ja foi concluida")
    if data.delivery_date == delivery.delivery_date:
        raise HTTPException(status_code=400, detail="A nova data deve ser diferente da data atual")

    old_date = delivery.delivery_date
    delivery.delivery_date = data.delivery_date
    delivery.deadline_changed_at = datetime.utcnow()
    delivery.deadline_change_reason = data.reason
    log_action(
        db,
        entity="delivery",
        entity_id=delivery.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivery_date": {"old": old_date.isoformat(), "new": data.delivery_date.isoformat()},
            "reason": data.reason,
        },
    )
    db.commit()
    db.refresh(delivery)
    return _response(delivery)


@router.patch("/{delivery_id}/mark-delivered", response_model=DeliveryResponse)
def mark_delivery_delivered(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    delivery = _get_delivery(db, delivery_id)
    _ensure_can_edit(delivery, current_user)
    if delivery.delivered_at is not None:
        raise HTTPException(status_code=400, detail="Esta entrega ja foi concluida")

    delivery.delivered_at = datetime.utcnow()
    log_action(
        db,
        entity="delivery",
        entity_id=delivery.id,
        action="UPDATE",
        changed_by=current_user,
        changes={"delivered_at": {"old": None, "new": delivery.delivered_at.isoformat()}},
    )
    db.commit()
    db.refresh(delivery)
    return _response(delivery)


@router.patch("/{delivery_id}/cancel-delivered", response_model=DeliveryResponse)
def cancel_delivery_delivered(
    delivery_id: int,
    data: DeliveryCancellationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_delivery_handler),
):
    delivery = _get_delivery(db, delivery_id)
    _ensure_can_edit(delivery, current_user)
    if delivery.delivered_at is None:
        raise HTTPException(status_code=400, detail="Esta entrega ainda nao foi concluida")

    old_delivered_at = delivery.delivered_at
    delivery.delivered_at = None
    log_action(
        db,
        entity="delivery",
        entity_id=delivery.id,
        action="UPDATE",
        changed_by=current_user,
        changes={
            "delivered_at": {"old": old_delivered_at.isoformat(), "new": None},
            "reason": data.reason,
        },
    )
    db.commit()
    db.refresh(delivery)
    return _response(delivery)
