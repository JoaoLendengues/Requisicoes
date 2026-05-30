"""
Testes unitários para o resumo da Central de Pedidos.

Cobre:
- novos campos operacionais do payload (peso, máquina, operadores e datas)
- cálculo de prazo atendido para pedidos finalizados
- montagem das listas de aguardando recebimento, em produção, cancelados e atrasados
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.models.client import Client
from server.models.requisition import Requisition, RequisitionStatus, StatusHistory
from server.models.user import Role, User
from server.routers.requisitions import (
    _DESTINATION_AR,
    _DESTINATION_PINHEIRO,
    _PROD_CANCELED,
    _PROD_FINISHED,
    _PROD_SEND,
    _PROD_STARTED,
    _build_order_center,
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
    reason: str | None = None,
) -> str:
    parts = ["PRODUCAO", action, destination]
    if machine:
        parts.append(f"machine={machine}")
    if operators:
        parts.append(f"operators={';'.join(operators)}")
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
    ped: str,
    status: RequisitionStatus,
    *,
    vendor_name: str,
    client_name: str,
    weight: float,
    delivery_date: date | None,
    destination: str | None,
    history: list[StatusHistory],
    cancel_reason: str | None = None,
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
        weight=weight,
        delivery_date=delivery_date,
        production_destination=destination,
        cancel_reason=cancel_reason,
        emission_date=datetime.utcnow() - timedelta(days=5),
        status_history=history,
    )


def _row_by_ped(rows: list, ped_number: str):
    return next(row for row in rows if row.ped_number == ped_number)


def test_order_center_summary_includes_new_operational_columns():
    now = datetime.utcnow().replace(microsecond=0)
    today = now.date()

    waiting_sent_at = now - timedelta(hours=2, minutes=15)
    in_production_sent_at = now - timedelta(hours=6)
    in_production_started_at = now - timedelta(hours=3)
    finished_sent_at = now - timedelta(days=3)
    finished_started_at = now - timedelta(days=2, hours=6)
    finished_at = now - timedelta(days=2, hours=1)
    canceled_sent_at = now - timedelta(days=1, hours=6)
    canceled_at = now - timedelta(days=1)
    delayed_sent_at = now - timedelta(days=4)
    delayed_started_at = now - timedelta(days=2, hours=8)

    waiting_req = _req(
        1,
        "1001",
        RequisitionStatus.AGUARDANDO_RECEBIMENTO,
        vendor_name="ADLER",
        client_name="CLIENTE A",
        weight=10.5,
        delivery_date=today + timedelta(days=2),
        destination=_DESTINATION_AR,
        history=[
            _status_entry(
                1,
                RequisitionStatus.EM_ANDAMENTO.value,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                waiting_sent_at,
                _prod_note(_PROD_SEND, _DESTINATION_AR),
                1,
            )
        ],
    )

    in_production_req = _req(
        2,
        "1002",
        RequisitionStatus.EM_PRODUCAO,
        vendor_name="LUCAS",
        client_name="CLIENTE B",
        weight=18.2,
        delivery_date=today + timedelta(days=1),
        destination=_DESTINATION_AR,
        history=[
            _status_entry(
                2,
                RequisitionStatus.EM_ANDAMENTO.value,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                in_production_sent_at,
                _prod_note(_PROD_SEND, _DESTINATION_AR),
                2,
            ),
            _status_entry(
                2,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                RequisitionStatus.EM_PRODUCAO.value,
                in_production_started_at,
                _prod_note(
                    _PROD_STARTED,
                    _DESTINATION_AR,
                    machine="LASER 01",
                    operators=["ALICE", "BRUNO"],
                ),
                3,
            ),
        ],
    )

    finished_req = _req(
        3,
        "1003",
        RequisitionStatus.FATURADO,
        vendor_name="RONNY",
        client_name="CLIENTE C",
        weight=27.35,
        delivery_date=finished_at.date(),
        destination=_DESTINATION_PINHEIRO,
        history=[
            _status_entry(
                3,
                RequisitionStatus.EM_ANDAMENTO.value,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                finished_sent_at,
                _prod_note(_PROD_SEND, _DESTINATION_PINHEIRO),
                4,
            ),
            _status_entry(
                3,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                RequisitionStatus.EM_PRODUCAO.value,
                finished_started_at,
                _prod_note(
                    _PROD_STARTED,
                    _DESTINATION_PINHEIRO,
                    machine="PRENSA 02",
                    operators=["JOAO"],
                ),
                5,
            ),
            _status_entry(
                3,
                RequisitionStatus.EM_PRODUCAO.value,
                RequisitionStatus.FATURADO.value,
                finished_at,
                _prod_note(
                    _PROD_FINISHED,
                    _DESTINATION_PINHEIRO,
                    machine="PRENSA 02",
                ),
                6,
            ),
        ],
    )

    canceled_req = _req(
        4,
        "1004",
        RequisitionStatus.CANCELADA,
        vendor_name="IGOR",
        client_name="CLIENTE D",
        weight=7.0,
        delivery_date=today + timedelta(days=4),
        destination=_DESTINATION_AR,
        history=[
            _status_entry(
                4,
                RequisitionStatus.EM_ANDAMENTO.value,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                canceled_sent_at,
                _prod_note(_PROD_SEND, _DESTINATION_AR),
                7,
            ),
            _status_entry(
                4,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                RequisitionStatus.CANCELADA.value,
                canceled_at,
                _prod_note(
                    _PROD_CANCELED,
                    _DESTINATION_AR,
                    reason="CLIENTE DESISTIU",
                ),
                8,
            ),
        ],
        cancel_reason="CLIENTE DESISTIU",
    )

    delayed_req = _req(
        5,
        "1005",
        RequisitionStatus.EM_PRODUCAO,
        vendor_name="RODRIGO",
        client_name="CLIENTE E",
        weight=14.4,
        delivery_date=today - timedelta(days=1),
        destination=_DESTINATION_AR,
        history=[
            _status_entry(
                5,
                RequisitionStatus.EM_ANDAMENTO.value,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                delayed_sent_at,
                _prod_note(_PROD_SEND, _DESTINATION_AR),
                9,
            ),
            _status_entry(
                5,
                RequisitionStatus.AGUARDANDO_RECEBIMENTO.value,
                RequisitionStatus.EM_PRODUCAO.value,
                delayed_started_at,
                _prod_note(
                    _PROD_STARTED,
                    _DESTINATION_AR,
                    machine="DOBRA 03",
                    operators=["MARIA"],
                ),
                10,
            ),
        ],
    )

    summary = _build_order_center(
        [waiting_req, in_production_req, finished_req, canceled_req, delayed_req]
    )

    assert summary.stats.pedidos_aguardando_recebimento == 1
    assert summary.stats.pedidos_em_producao == 2
    assert summary.stats.pedidos_faturados == 1
    assert summary.stats.pedidos_cancelados == 1
    assert summary.stats.pedidos_atrasados == 1

    waiting_row = _row_by_ped(summary.aguardando_recebimento, "1001")
    assert waiting_row.weight == 10.5
    assert waiting_row.sent_to_production_at == waiting_sent_at
    assert waiting_row.waiting_minutes is not None and waiting_row.waiting_minutes >= 135

    production_row = _row_by_ped(summary.em_producao, "1002")
    assert production_row.weight == 18.2
    assert production_row.received_at == in_production_started_at
    assert production_row.destination == _DESTINATION_AR
    assert production_row.machine_name == "LASER 01"
    assert production_row.operator_names == ["ALICE", "BRUNO"]

    finished_row = summary.faturados[0]
    assert finished_row.vendor_name == "RONNY"
    assert finished_row.weight == 27.35
    assert finished_row.invoiced_at == finished_at
    assert finished_row.finished_at == finished_at
    assert finished_row.machine_name == "PRENSA 02"
    assert finished_row.operator_names == ["JOAO"]
    assert finished_row.deadline_met is True

    canceled_row = summary.cancelados[0]
    assert canceled_row.weight == 7.0
    assert canceled_row.canceled_at == canceled_at
    assert canceled_row.cancel_reason == "CLIENTE DESISTIU"

    delayed_row = summary.atrasados[0]
    assert delayed_row.vendor_name == "RODRIGO"
    assert delayed_row.weight == 14.4
    assert delayed_row.delay_days == 1
    assert delayed_row.destination == _DESTINATION_AR
    assert delayed_row.machine_name == "DOBRA 03"
    assert delayed_row.operator_names == ["MARIA"]
