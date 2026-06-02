"""
Testes unitários para o KPI IAR do Painel Gerencial.

Cobre:
- cálculo do IAR geral com prazo, produtividade e cancelamentos
- ranking de vendedores ordenado pelo maior IAR
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.models.client import Client
from server.models.requisition import Requisition, RequisitionStatus, StatusHistory
from server.models.user import Role, User
from server.routers.requisitions import (
    _DESTINATION_AR,
    _PROD_CANCELED,
    _PROD_FINISHED,
    _PROD_STARTED,
    _build_iar_general,
    _build_top_vendor_rows,
)


def _vendor(vendor_id: int, name: str) -> User:
    return User(
        id=vendor_id,
        code=f"V{vendor_id}",
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


def _prod_note(action: str, destination: str, *, machine: str | None = None) -> str:
    parts = ["PRODUCAO", action, destination]
    if machine:
        parts.append(f"machine={machine}")
    return "|".join(parts)


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
    *,
    vendor_id: int,
    vendor_name: str,
    weight: float,
    emission_at: datetime,
    delivery_date: datetime,
    status: RequisitionStatus,
    history: list[StatusHistory],
) -> Requisition:
    vendor = _vendor(vendor_id, vendor_name)
    client = _client(req_id, f"CLIENTE {req_id}")
    return Requisition(
        id=req_id,
        ped_number=f"PED-{req_id}",
        vendor_id=vendor.id,
        vendor=vendor,
        client_id=client.id,
        client=client,
        status=status,
        weight=weight,
        emission_date=emission_at,
        created_at=emission_at,
        delivery_date=delivery_date.date(),
        production_destination=_DESTINATION_AR,
        status_history=history,
    )


def test_build_iar_general_uses_deadline_productivity_and_cancelation_weights():
    now = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)

    on_time_start = now - timedelta(days=5)
    on_time_finish = now - timedelta(days=4)
    late_start = now - timedelta(days=4)
    late_finish = now - timedelta(days=2)
    open_start = now - timedelta(days=1)
    canceled_at = now - timedelta(days=1, hours=3)

    req_on_time = _req(
        1,
        vendor_id=1,
        vendor_name="ALICE",
        weight=8.2,
        emission_at=now - timedelta(days=6),
        delivery_date=on_time_finish,
        status=RequisitionStatus.FATURADO,
        history=[
            _status_entry(
                1,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                on_time_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 01"),
                1,
            ),
            _status_entry(
                1,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                on_time_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="PRENSA 01"),
                2,
            ),
        ],
    )
    req_late = _req(
        2,
        vendor_id=1,
        vendor_name="ALICE",
        weight=5.1,
        emission_at=now - timedelta(days=5),
        delivery_date=late_start,
        status=RequisitionStatus.FATURADO,
        history=[
            _status_entry(
                2,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                late_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 02"),
                3,
            ),
            _status_entry(
                2,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                late_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="PRENSA 02"),
                4,
            ),
        ],
    )
    req_open = _req(
        3,
        vendor_id=2,
        vendor_name="BOB",
        weight=3.4,
        emission_at=now - timedelta(days=2),
        delivery_date=now + timedelta(days=1),
        status=RequisitionStatus.EM_PRODUCAO,
        history=[
            _status_entry(
                3,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                open_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="LASER 01"),
                5,
            ),
        ],
    )
    req_canceled = _req(
        4,
        vendor_id=3,
        vendor_name="CARLA",
        weight=2.0,
        emission_at=now - timedelta(days=2),
        delivery_date=now + timedelta(days=2),
        status=RequisitionStatus.CANCELADA,
        history=[
            _status_entry(
                4,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.CANCELADA.value,
                canceled_at,
                _prod_note(_PROD_CANCELED, _DESTINATION_AR, machine="DOBRA 01"),
                6,
            ),
        ],
    )

    summary = _build_iar_general([req_on_time, req_late, req_open, req_canceled], "year", None, None, now)

    assert summary.received_count == 4
    assert summary.finalized_count == 2
    assert summary.on_time_count == 1
    assert summary.canceled_count == 1
    assert summary.prazo_percent == 50.0
    assert summary.produtividade_percent == 50.0
    assert summary.cancelamentos_percent == 75.0
    assert summary.iar_percent == 55.0


def test_build_top_vendor_rows_orders_by_iar_percent():
    now = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)

    alice_first_start = now - timedelta(days=5)
    alice_first_finish = now - timedelta(days=4)
    alice_second_start = now - timedelta(days=4)
    alice_second_finish = now - timedelta(days=2)
    bob_start = now - timedelta(days=3)
    bob_finish = now - timedelta(days=2)

    req_alice_on_time = _req(
        10,
        vendor_id=1,
        vendor_name="ALICE",
        weight=7.0,
        emission_at=now - timedelta(days=6),
        delivery_date=alice_first_finish,
        status=RequisitionStatus.FATURADO,
        history=[
            _status_entry(
                10,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                alice_first_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 03"),
                10,
            ),
            _status_entry(
                10,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                alice_first_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="PRENSA 03"),
                11,
            ),
        ],
    )
    req_alice_late = _req(
        11,
        vendor_id=1,
        vendor_name="ALICE",
        weight=6.5,
        emission_at=now - timedelta(days=5),
        delivery_date=alice_second_start,
        status=RequisitionStatus.FATURADO,
        history=[
            _status_entry(
                11,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                alice_second_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 04"),
                12,
            ),
            _status_entry(
                11,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                alice_second_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="PRENSA 04"),
                13,
            ),
        ],
    )
    req_bob_perfect = _req(
        12,
        vendor_id=2,
        vendor_name="BOB",
        weight=4.0,
        emission_at=now - timedelta(days=4),
        delivery_date=bob_finish,
        status=RequisitionStatus.FATURADO,
        history=[
            _status_entry(
                12,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                bob_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="LASER 02"),
                14,
            ),
            _status_entry(
                12,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                bob_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="LASER 02"),
                15,
            ),
        ],
    )

    rows = _build_top_vendor_rows(
        [req_alice_on_time, req_alice_late, req_bob_perfect],
        "year",
        None,
        None,
        now,
    )

    assert [row.vendor_name for row in rows] == ["BOB", "ALICE"]
    assert rows[0].iar_percent == 100.0
    assert rows[0].prazo_percent == 100.0
    assert rows[0].produtividade_percent == 100.0
    assert rows[0].cancelamentos_percent == 100.0

    assert rows[1].requisition_count == 2
    assert rows[1].total_weight_kg == 13.5
    assert rows[1].prazo_percent == 50.0
    assert rows[1].produtividade_percent == 100.0
    assert rows[1].cancelamentos_percent == 100.0
    assert rows[1].iar_percent == 75.0
