"""
Testes unitários do resumo e das ações da tela de entregas.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.models.client import Client
from server.models.requisition import Requisition, RequisitionStatus, StatusHistory
from server.models.user import Role, User
from server.routers import requisitions as requisitions_router
from server.routers.requisitions import _build_delivery_center


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
        RequisitionStatus.FATURADO,
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
        RequisitionStatus.FATURADO,
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
    assert summary.rows[0].status == RequisitionStatus.EM_PRODUCAO.value
    assert summary.rows[0].weight == 8.4
    assert summary.rows[1].delivered_at is not None
    assert summary.rows[2].delivery_date == today
    assert summary.rows[3].deadline_changed_at is not None


def test_mark_delivery_delivered_sets_timestamp_and_history():
    now_before = datetime.utcnow()
    req = _req(
        7,
        "3001",
        RequisitionStatus.FATURADO,
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
    assert "Entrega concluída" in str(db.added[0].note or "")
