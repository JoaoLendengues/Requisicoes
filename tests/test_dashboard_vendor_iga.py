"""
Testes unitários para o ranking de vendedores do Painel Gerencial.

Cobre:
- soma de requisições e peso por vendedor
- cálculo do IGA com prazo, produção e qualidade
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
    _PROD_FINISHED,
    _PROD_STARTED,
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


def _prod_note(
    action: str,
    destination: str,
    *,
    machine: str | None = None,
    reason: str | None = None,
) -> str:
    parts = ["PRODUCAO", action, destination]
    if machine:
        parts.append(f"machine={machine}")
    if reason:
        parts.append(f"reason={reason}")
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
    vendor_name: str,
    weight: float,
    emission_at: datetime,
    delivery_date: datetime,
    delivered_at: datetime,
    history: list[StatusHistory],
    deadline_change_reason: str | None = None,
) -> Requisition:
    vendor = _vendor(1, vendor_name)
    client = _client(req_id, f"CLIENTE {req_id}")
    return Requisition(
        id=req_id,
        ped_number=f"PED-{req_id}",
        vendor_id=vendor.id,
        vendor=vendor,
        client_id=client.id,
        client=client,
        status=RequisitionStatus.FATURADO,
        weight=weight,
        emission_date=emission_at,
        created_at=emission_at,
        delivery_date=delivery_date.date(),
        delivered_at=delivered_at,
        entrega=True,
        production_destination=_DESTINATION_AR,
        delivery_deadline_change_reason=deadline_change_reason,
        status_history=history,
    )


def test_build_top_vendor_rows_includes_iga_percent():
    now = datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)

    first_start = now - timedelta(days=5)
    first_finish = now - timedelta(days=4)
    second_start = now - timedelta(days=3)
    second_finish = now - timedelta(days=2)

    req_on_time = _req(
        1,
        vendor_name="ALICE",
        weight=10.25,
        emission_at=now - timedelta(days=6),
        delivery_date=first_finish,
        delivered_at=first_finish,
        history=[
            _status_entry(
                1,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                first_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 01"),
                1,
            ),
            _status_entry(
                1,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                first_finish,
                _prod_note(_PROD_FINISHED, _DESTINATION_AR, machine="PRENSA 01"),
                2,
            ),
        ],
    )
    req_rework = _req(
        2,
        vendor_name="ALICE",
        weight=6.25,
        emission_at=now - timedelta(days=4),
        delivery_date=second_start,
        delivered_at=second_finish,
        history=[
            _status_entry(
                2,
                RequisitionStatus.AGUARDANDO_NA_FILA.value,
                RequisitionStatus.EM_PRODUCAO.value,
                second_start,
                _prod_note(_PROD_STARTED, _DESTINATION_AR, machine="PRENSA 02"),
                3,
            ),
            _status_entry(
                2,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                second_finish,
                _prod_note(
                    _PROD_FINISHED,
                    _DESTINATION_AR,
                    machine="PRENSA 02",
                    reason="Necessidade de retrabalho na producao",
                ),
                4,
            ),
        ],
    )

    rows = _build_top_vendor_rows([req_on_time, req_rework], "30d", now)

    assert len(rows) == 1
    assert rows[0].vendor_name == "ALICE"
    assert rows[0].requisition_count == 2
    assert rows[0].total_weight_kg == 16.5
    assert rows[0].iga_percent == 25.0
