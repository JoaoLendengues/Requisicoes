"""
Unit tests for delivery center summary and delivery actions.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.models.client import Client
from server.models.delivery import Delivery
from server.models.requisition import (
    Requisition,
    RequisitionProductionSplit,
    RequisitionStatus,
    StatusHistory,
)
from server.models.user import Role, User
from server.routers import requisitions as requisitions_router
from server.routers.requisitions import _build_delivery_center, _merge_standalone_deliveries


def _vendor(user_id: int, name: str) -> User:
    return User(
        id=user_id,
        code=f"V{user_id}",
        name=name,
        hashed_password="secret",
        role=Role.VENDEDOR,
    )


def _client(client_id: int, name: str) -> Client:
    return Client(
        id=client_id,
        code=f"C{client_id}",
        name=name,
    )


def _status_entry(
    req_id: int,
    old_status: str | None,
    new_status: str,
    changed_at: datetime,
    note: str,
    entry_id: int,
) -> StatusHistory:
    return StatusHistory(
        id=entry_id,
        requisition_id=req_id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=1,
        changed_at=changed_at,
        note=note,
    )


def _req(
    req_id: int,
    ped: str,
    status: RequisitionStatus,
    *,
    entrega: bool,
    vendor_name: str,
    client_name: str,
    weight: float,
    delivery_date: date | None,
    delivered_at: datetime | None = None,
    deadline_changed_at: datetime | None = None,
    history: list[StatusHistory] | None = None,
) -> Requisition:
    vendor = _vendor(req_id, vendor_name)
    client = _client(req_id, client_name)
    return Requisition(
        id=req_id,
        ped_number=ped,
        vendor_id=vendor.id,
        vendor=vendor,
        client_id=client.id,
        client=client,
        status=status,
        entrega=entrega,
        weight=weight,
        delivery_date=delivery_date,
        delivered_at=delivered_at,
        delivery_deadline_changed_at=deadline_changed_at,
        emission_date=datetime.utcnow() - timedelta(days=3),
        status_history=history or [],
    )


def _split(
    split_id: int,
    req_id: int,
    sequence: int,
    status: RequisitionStatus,
    *,
    weight: float,
    delivered_at: datetime | None = None,
    destination: str = "A&R",
) -> RequisitionProductionSplit:
    now = datetime.utcnow().replace(microsecond=0)
    return RequisitionProductionSplit(
        id=split_id,
        requisition_id=req_id,
        sequence=sequence,
        weight=weight,
        status=status,
        destination=destination,
        delivered_at=delivered_at,
        created_at=now - timedelta(hours=3),
        updated_at=now - timedelta(minutes=15),
    )


class _DummyDB:
    def __init__(self):
        self.added: list[object] = []
        self.committed = False

    def add(self, item: object):
        self.added.append(item)

    def commit(self):
        self.committed = True


def test_build_delivery_center_counts_and_orders_rows():
    now = datetime.utcnow().replace(microsecond=0)
    today = now.date()

    req_today = _req(
        1,
        "2001",
        RequisitionStatus.FINALIZADO,
        entrega=True,
        vendor_name="ADLER",
        client_name="CLIENTE A",
        weight=12.5,
        delivery_date=today,
    )
    req_overdue = _req(
        2,
        "2002",
        RequisitionStatus.EM_PRODUCAO,
        entrega=True,
        vendor_name="LUCAS",
        client_name="CLIENTE B",
        weight=8.4,
        delivery_date=today - timedelta(days=2),
        deadline_changed_at=now - timedelta(hours=5),
    )
    req_future = _req(
        3,
        "2003",
        RequisitionStatus.PRAZO_ALTERADO,
        entrega=True,
        vendor_name="RONNY",
        client_name="CLIENTE C",
        weight=30.0,
        delivery_date=today + timedelta(days=4),
        history=[
            _status_entry(
                3,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.PRAZO_ALTERADO.value,
                now - timedelta(days=1),
                "Prazo alterado",
                1,
            )
        ],
    )
    req_done = _req(
        4,
        "2004",
        RequisitionStatus.FINALIZADO,
        entrega=True,
        vendor_name="RODRIGO",
        client_name="CLIENTE D",
        weight=18.75,
        delivery_date=today - timedelta(days=1),
        delivered_at=now - timedelta(hours=2),
    )
    req_without_delivery = _req(
        5,
        "2005",
        RequisitionStatus.FATURADO,
        entrega=False,
        vendor_name="IGOR",
        client_name="CLIENTE E",
        weight=5.0,
        delivery_date=today,
    )

    summary = _build_delivery_center(
        [req_future, req_done, req_today, req_without_delivery, req_overdue]
    )

    assert summary.stats.deliveries_today == 1
    assert summary.stats.delayed_deliveries == 1
    assert summary.stats.changed_delivery_deadlines == 2

    assert [row.ped_number for row in summary.rows] == ["2002", "2004", "2001", "2003"]
    assert summary.rows[0].status == RequisitionStatus.PRAZO_ALTERADO.value
    assert summary.rows[0].weight == 8.4
    assert summary.rows[1].delivered_at is not None
    assert summary.rows[2].delivery_date == today
    assert summary.rows[3].deadline_changed_at is not None


def test_merge_standalone_delivery_adds_operational_fields_and_stats():
    today = date.today()
    vendor = _vendor(80, "VENDEDOR ENTREGA")
    client = _client(80, "CLIENTE ENTREGA")
    delivery = Delivery(
        id=12,
        client_id=client.id,
        client=client,
        vendor_id=vendor.id,
        vendor=vendor,
        created_by_id=1,
        city="CAMPINAS",
        truck_name="CAMINHAO 07",
        loaded_by="JOAO",
        delivery_date=today,
        created_at=datetime.utcnow(),
    )

    summary = _merge_standalone_deliveries(_build_delivery_center([]), [delivery])

    assert summary.stats.deliveries_today == 1
    assert len(summary.rows) == 1
    row = summary.rows[0]
    assert row.ped_number == "ENT-000012"
    assert row.standalone_delivery_id == 12
    assert row.client_code == client.code
    assert row.client_name == client.name
    assert row.vendor_name == vendor.name
    assert row.city == "CAMPINAS"
    assert row.truck_name == "CAMINHAO 07"
    assert row.loaded_by == "JOAO"
    assert row.status == RequisitionStatus.AGUARDANDO_ENTREGA.value


def test_build_delivery_center_expands_split_rows_and_counts_each_parcel():
    now = datetime.utcnow().replace(microsecond=0)
    today = now.date()

    req = _req(
        8,
        "4001",
        RequisitionStatus.EM_PRODUCAO,
        entrega=True,
        vendor_name="LIA",
        client_name="CLIENTE SPLIT",
        weight=10.0,
        delivery_date=today,
    )
    split_1 = _split(801, req.id, 1, RequisitionStatus.FINALIZADO, weight=4.0)
    split_2 = _split(
        802,
        req.id,
        2,
        RequisitionStatus.FINALIZADO,
        weight=3.0,
        delivered_at=now - timedelta(hours=1),
    )
    split_3 = _split(803, req.id, 3, RequisitionStatus.EM_PRODUCAO, weight=3.0)
    req.production_splits = [split_1, split_2, split_3]
    split_1.requisition = req
    split_2.requisition = req
    split_3.requisition = req

    summary = _build_delivery_center([req])

    assert summary.stats.deliveries_today == 2
    assert summary.stats.delayed_deliveries == 0
    assert summary.stats.changed_delivery_deadlines == 0
    assert summary.stats.completed_deliveries == 1
    assert [row.ped_number for row in summary.rows] == ["4001/P01", "4001/P02", "4001/P03"]
    assert summary.rows[0].production_split_id == 801
    assert summary.rows[0].source_requisition_id == req.id
    assert summary.rows[0].status == RequisitionStatus.FINALIZADO.value
    assert summary.rows[1].status == "entregue"
    assert summary.rows[1].delivered_at is not None
    assert summary.rows[2].status == RequisitionStatus.EM_PRODUCAO.value


def test_mark_delivery_delivered_sets_timestamp_and_history():
    now_before = datetime.utcnow()
    req = _req(
        7,
        "3001",
        RequisitionStatus.FINALIZADO,
        entrega=True,
        vendor_name="FAUSTO",
        client_name="CLIENTE X",
        weight=9.9,
        delivery_date=now_before.date(),
    )
    db = _DummyDB()
    current_user = _vendor(99, "OPERADOR")

    old_get_or_404 = requisitions_router._get_or_404
    old_can_edit = requisitions_router._can_edit_requisition
    old_log_action = requisitions_router.log_action
    try:
        requisitions_router._get_or_404 = lambda _db, _req_id: req
        requisitions_router._can_edit_requisition = lambda _req, _user: True
        requisitions_router.log_action = lambda *args, **kwargs: None

        response = requisitions_router.mark_delivery_delivered(
            req_id=req.id,
            db=db,
            current_user=current_user,
        )
    finally:
        requisitions_router._get_or_404 = old_get_or_404
        requisitions_router._can_edit_requisition = old_can_edit
        requisitions_router.log_action = old_log_action

    assert response is req
    assert req.delivered_at is not None
    assert req.delivered_at >= now_before
    assert db.committed is True
    assert len(db.added) == 1
    assert isinstance(db.added[0], StatusHistory)
    assert "Entrega" in str(db.added[0].note or "")


def test_mark_delivery_split_delivered_keeps_parent_open_until_all_parcels_are_delivered():
    now_before = datetime.utcnow()
    req = _req(
        9,
        "5001",
        RequisitionStatus.EM_PRODUCAO,
        entrega=True,
        vendor_name="FAUSTO",
        client_name="CLIENTE SPLIT",
        weight=12.0,
        delivery_date=now_before.date(),
    )
    split_done = _split(901, req.id, 1, RequisitionStatus.FINALIZADO, weight=5.0)
    split_open = _split(902, req.id, 2, RequisitionStatus.EM_PRODUCAO, weight=7.0)
    req.production_splits = [split_done, split_open]
    split_done.requisition = req
    split_open.requisition = req

    db = _DummyDB()
    current_user = _vendor(99, "OPERADOR")

    old_get_or_404 = requisitions_router._get_or_404
    old_get_split_or_404 = requisitions_router._get_split_or_404
    old_can_edit = requisitions_router._can_edit_requisition
    old_log_action = requisitions_router.log_action
    try:
        requisitions_router._get_or_404 = lambda _db, _req_id: req
        requisitions_router._get_split_or_404 = lambda _db, _split_id: split_done
        requisitions_router._can_edit_requisition = lambda _req, _user: True
        requisitions_router.log_action = lambda *args, **kwargs: None

        response = requisitions_router.mark_delivery_split_delivered(
            split_id=split_done.id,
            db=db,
            current_user=current_user,
        )
    finally:
        requisitions_router._get_or_404 = old_get_or_404
        requisitions_router._get_split_or_404 = old_get_split_or_404
        requisitions_router._can_edit_requisition = old_can_edit
        requisitions_router.log_action = old_log_action

    assert response is req
    assert split_done.delivered_at is not None
    assert split_done.delivered_at >= now_before
    assert req.delivered_at is None
    assert db.committed is True
    assert len(db.added) == 1
    assert isinstance(db.added[0], StatusHistory)
    assert db.added[0].production_split_id == split_done.id


def test_mark_last_delivery_split_syncs_parent_delivery_timestamp():
    previous_delivery = datetime.utcnow().replace(microsecond=0) - timedelta(hours=2)
    req = _req(
        10,
        "5002",
        RequisitionStatus.FINALIZADO,
        entrega=True,
        vendor_name="FAUSTO",
        client_name="CLIENTE SPLIT",
        weight=12.0,
        delivery_date=previous_delivery.date(),
    )
    split_done = _split(
        1001,
        req.id,
        1,
        RequisitionStatus.FINALIZADO,
        weight=5.0,
        delivered_at=previous_delivery,
    )
    split_last = _split(1002, req.id, 2, RequisitionStatus.FINALIZADO, weight=7.0)
    req.production_splits = [split_done, split_last]
    split_done.requisition = req
    split_last.requisition = req

    db = _DummyDB()
    current_user = _vendor(98, "OPERADOR")

    old_get_or_404 = requisitions_router._get_or_404
    old_get_split_or_404 = requisitions_router._get_split_or_404
    old_can_edit = requisitions_router._can_edit_requisition
    old_log_action = requisitions_router.log_action
    try:
        requisitions_router._get_or_404 = lambda _db, _req_id: req
        requisitions_router._get_split_or_404 = lambda _db, _split_id: split_last
        requisitions_router._can_edit_requisition = lambda _req, _user: True
        requisitions_router.log_action = lambda *args, **kwargs: None

        requisitions_router.mark_delivery_split_delivered(
            split_id=split_last.id,
            db=db,
            current_user=current_user,
        )
    finally:
        requisitions_router._get_or_404 = old_get_or_404
        requisitions_router._get_split_or_404 = old_get_split_or_404
        requisitions_router._can_edit_requisition = old_can_edit
        requisitions_router.log_action = old_log_action

    assert split_last.delivered_at is not None
    assert req.delivered_at == split_last.delivered_at
