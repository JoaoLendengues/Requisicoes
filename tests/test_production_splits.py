from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException

from server.models.client import Client
from server.models.production_machine import MachineOperationalStatus, ProductionMachine
from server.models.requisition import (
    Requisition,
    RequisitionProductionSplit,
    RequisitionStatus,
    StatusHistory,
)
from server.models.user import Role, User
from server.schemas.production import ProductionItemResponse
from server.routers.requisitions import (
    _DESTINATION_AR,
    _PROD_SEND,
    _PROD_STARTED,
    _build_order_center,
    _build_production_summary,
    _ensure_production_fifo_item,
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
    operators: list[str] | None = None,
    helpers: list[str] | None = None,
) -> str:
    parts = ["PRODUCAO", action, destination]
    if machine:
        parts.append(f"machine={machine}")
    if operators:
        parts.append(f"operators={';'.join(operators)}")
    if helpers:
        parts.append(f"helpers={';'.join(helpers)}")
    return "|".join(parts)


def _status_entry(
    req_id: int,
    *,
    entry_id: int,
    old_status: str | None,
    new_status: str,
    changed_at: datetime,
    note: str,
    split_id: int | None = None,
) -> StatusHistory:
    return StatusHistory(
        id=entry_id,
        requisition_id=req_id,
        production_split_id=split_id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=1,
        changed_at=changed_at,
        note=note,
    )


def _partial_req() -> tuple[Requisition, ProductionMachine]:
    now = datetime.utcnow().replace(microsecond=0)
    vendor = _vendor(1, "ALICE")
    client = _client(1, "CLIENTE A")
    machine = ProductionMachine(
        id=10,
        destination=_DESTINATION_AR,
        name="LASER 01",
        sort_order=1,
        status=MachineOperationalStatus.FUNCIONANDO,
    )

    split = RequisitionProductionSplit(
        id=101,
        requisition_id=1,
        sequence=1,
        weight=4.0,
        status=RequisitionStatus.EM_PRODUCAO,
        destination=_DESTINATION_AR,
        production_machine="LASER 01",
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
    )
    split.status_history = [
        _status_entry(
            1,
            split_id=101,
            entry_id=2,
            old_status=RequisitionStatus.AGUARDANDO_NA_FILA.value,
            new_status=RequisitionStatus.EM_PRODUCAO.value,
            changed_at=now - timedelta(hours=2),
            note=_prod_note(
                _PROD_STARTED,
                _DESTINATION_AR,
                machine="LASER 01",
                operators=["JOAO"],
                helpers=["MARIO"],
            ),
        )
    ]

    req = Requisition(
        id=1,
        ped_number="1001",
        vendor_id=vendor.id,
        vendor=vendor,
        client_id=client.id,
        client=client,
        status=RequisitionStatus.AGUARDANDO_NA_FILA,
        weight=10.0,
        delivery_date=(now + timedelta(days=2)).date(),
        production_destination=_DESTINATION_AR,
        emission_date=now - timedelta(days=1),
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(hours=1),
        status_history=[
            _status_entry(
                1,
                entry_id=1,
                old_status=RequisitionStatus.EM_ANDAMENTO.value,
                new_status=RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                changed_at=now - timedelta(hours=3),
                note=_prod_note(_PROD_SEND, _DESTINATION_AR),
            )
        ],
        production_splits=[split],
    )
    split.requisition = req
    return req, machine


def _production_response_item(
    *,
    item_id: int,
    ped_number: str,
    waiting_since: datetime,
    source_requisition_id: int | None = None,
    split_id: int | None = None,
) -> ProductionItemResponse:
    return ProductionItemResponse(
        id=item_id,
        source_requisition_id=source_requisition_id,
        production_split_id=split_id,
        ped_number=ped_number,
        client_name="CLIENTE A",
        vendor_name="ALICE",
        obra="OBRA A",
        weight=10.0,
        total_weight=10.0,
        status=RequisitionStatus.AGUARDANDO_NA_FILA.value,
        emission_date=waiting_since,
        created_at=waiting_since,
        destination=_DESTINATION_AR,
        waiting_since=waiting_since,
    )


def test_build_production_summary_keeps_remaining_weight_pending():
    req, machine = _partial_req()

    summary = _build_production_summary([req], [machine], _DESTINATION_AR)

    assert summary.stats.aguardando_na_fila == 1
    assert summary.stats.em_producao == 1
    assert len(summary.waiting_queue) == 1
    assert summary.waiting_queue[0].ped_number == "1001"
    assert summary.waiting_queue[0].weight == 6.0
    assert summary.waiting_queue[0].total_weight == 10.0

    assert len(summary.machines) == 1
    rows = summary.machines[0].rows
    assert len(rows) == 1
    assert rows[0].ped_number == "1001/P01"
    assert rows[0].production_split_id == 101
    assert rows[0].source_requisition_id == 1
    assert rows[0].weight == 4.0
    assert rows[0].total_weight == 10.0


def test_build_order_center_lists_split_and_remaining_rows():
    req, _machine = _partial_req()

    payload = _build_order_center([req])

    assert len(payload.em_producao) == 2

    remaining_row = next(row for row in payload.em_producao if row.production_split_id is None)
    split_row = next(row for row in payload.em_producao if row.production_split_id == 101)

    assert remaining_row.ped_number == "1001"
    assert remaining_row.weight == 6.0
    assert remaining_row.total_weight == 10.0

    assert split_row.ped_number == "1001/P01"
    assert split_row.source_requisition_id == 1
    assert split_row.weight == 4.0
    assert split_row.total_weight == 10.0
    assert split_row.machine_name == "LASER 01"
    assert split_row.operator_names == ["JOAO"]
    assert split_row.helper_names == ["MARIO"]


def test_production_fifo_blocks_newer_waiting_receipt_requisition():
    now = datetime.utcnow().replace(microsecond=0)
    first_item = _production_response_item(
        item_id=1,
        source_requisition_id=1,
        ped_number="1001",
        waiting_since=now - timedelta(days=2),
    )

    try:
        _ensure_production_fifo_item(
            first_item,
            stage="waiting_receipt",
            requisition_id=2,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "PED 1001" in str(exc.detail)
        assert "aguardando recebimento" in str(exc.detail)
    else:
        raise AssertionError("Era esperado bloquear a requisicao mais nova em aguardando recebimento.")


def test_production_fifo_blocks_newer_waiting_queue_split():
    now = datetime.utcnow().replace(microsecond=0)
    first_item = _production_response_item(
        item_id=101,
        source_requisition_id=1,
        split_id=101,
        ped_number="1001/P01",
        waiting_since=now - timedelta(hours=5),
    )

    try:
        _ensure_production_fifo_item(
            first_item,
            stage="waiting_queue",
            split_id=202,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "PED 1001/P01" in str(exc.detail)
        assert "na fila" in str(exc.detail)
    else:
        raise AssertionError("Era esperado bloquear a parcela mais nova em aguardando na fila.")


def test_production_fifo_allows_oldest_waiting_queue_requisition():
    now = datetime.utcnow().replace(microsecond=0)
    first_item = _production_response_item(
        item_id=1,
        source_requisition_id=1,
        ped_number="1001",
        waiting_since=now - timedelta(hours=3),
    )

    _ensure_production_fifo_item(
        first_item,
        stage="waiting_queue",
        requisition_id=1,
    )
