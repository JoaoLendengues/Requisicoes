from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.database import Base
from server.models.client import Client
from server.models.delivery import Delivery
from server.models.user import Role, User
from server.routers.deliveries import (
    cancel_delivery_delivered,
    create_delivery,
    mark_delivery_delivered,
    update_delivery_schedule,
)
from server.schemas.delivery import (
    DeliveryCancellationUpdate,
    DeliveryCreate,
    DeliveryScheduleUpdate,
)


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _records(db):
    creator = User(
        code="E1",
        name="ENTREGAS",
        hashed_password="secret",
        role=Role.ENTREGA,
        is_active=True,
    )
    vendor = User(
        code="V1",
        name="VENDEDOR UM",
        hashed_password="secret",
        role=Role.VENDEDOR,
        is_active=True,
    )
    client = Client(code="C1", name="CLIENTE UM", is_active=True)
    db.add_all([creator, vendor, client])
    db.commit()
    return creator, vendor, client


def test_create_standalone_delivery_normalizes_operational_fields():
    db = _database()
    creator, vendor, client = _records(db)

    response = create_delivery(
        DeliveryCreate(
            client_id=client.id,
            vendor_id=vendor.id,
            city="campinas",
            truck_name="caminhao 07",
            loaded_by="joao",
            delivery_date=date.today(),
        ),
        db,
        creator,
    )

    assert response.client_code == "C1"
    assert response.client_name == "CLIENTE UM"
    assert response.vendor_name == "VENDEDOR UM"
    assert response.city == "CAMPINAS"
    assert response.truck_name == "CAMINHAO 07"
    assert response.loaded_by == "JOAO"
    assert db.query(Delivery).count() == 1


def test_standalone_delivery_supports_schedule_completion_and_reopening():
    db = _database()
    creator, vendor, client = _records(db)
    created = create_delivery(
        DeliveryCreate(
            client_id=client.id,
            vendor_id=vendor.id,
            city="campinas",
            truck_name="caminhao 07",
            loaded_by="joao",
            delivery_date=date.today(),
        ),
        db,
        creator,
    )

    new_date = date.today() + timedelta(days=1)
    updated = update_delivery_schedule(
        created.id,
        DeliveryScheduleUpdate(delivery_date=new_date, reason="ajuste de rota"),
        db,
        creator,
    )
    assert updated.delivery_date == new_date
    assert updated.deadline_change_reason == "AJUSTE DE ROTA"

    completed = mark_delivery_delivered(created.id, db, creator)
    assert completed.delivered_at is not None

    reopened = cancel_delivery_delivered(
        created.id,
        DeliveryCancellationUpdate(reason="lancamento incorreto"),
        db,
        creator,
    )
    assert reopened.delivered_at is None

