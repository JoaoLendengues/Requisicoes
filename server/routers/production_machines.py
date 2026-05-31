from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..dependencies import require_admin
from ..models.operator import Operator, OperatorRole
from ..models.production_machine import MachineOperationalStatus, ProductionMachine
from ..models.user import User
from ..schemas.production_machine_registry import (
    OperatorWrite,
    ProductionMachineRegistryCreate,
    ProductionMachineRegistryResponse,
    ProductionMachineRegistryUpdate,
)
from ..services.audit_service import log_action
from ..services.text_normalizer import normalize_upper_required

router = APIRouter(prefix="/production-machines", tags=["Cadastro de Maquinas"])

_DESTINATION_AR = "A&R"
_DESTINATION_PINHEIRO = "Pinheiro Indústria"


def _canonical_destination(value: object) -> str:
    text = normalize_upper_required(value)
    compact = text.replace(" ", "")
    if text in {"A&R", "A/R"} or compact in {"AR", "A&R", "A/R"}:
        return _DESTINATION_AR
    if text in {"PINHEIRO INDÚSTRIA", "PINHEIRO INDUSTRIA"}:
        return _DESTINATION_PINHEIRO
    raise HTTPException(
        status_code=400,
        detail="Destino de produção inválido. Use A&R ou Pinheiro Indústria.",
    )


def _upsert_operators(db: Session, entries: list[OperatorWrite]) -> list[Operator]:
    """Para cada nome: devolve o Operator existente ou cria um novo."""
    result: list[Operator] = []
    for entry in entries:
        op = db.query(Operator).filter(Operator.name == entry.name).first()
        if op is None:
            op = Operator(name=entry.name, role=entry.role)
            db.add(op)
            db.flush()
        elif getattr(op, "role", OperatorRole.OPERADOR) != entry.role:
            op.role = entry.role
        result.append(op)
    return result


def _load_machine_or_404(db: Session, machine_id: int) -> ProductionMachine:
    machine = (
        db.query(ProductionMachine)
        .options(selectinload(ProductionMachine.operators))
        .filter(ProductionMachine.id == machine_id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return machine


def _ensure_unique_machine_name(
    db: Session,
    *,
    destination: str,
    name: str,
    ignore_machine_id: int | None = None,
) -> None:
    query = db.query(ProductionMachine).filter(
        ProductionMachine.destination == destination,
        ProductionMachine.name == name,
    )
    if ignore_machine_id is not None:
        query = query.filter(ProductionMachine.id != ignore_machine_id)
    if query.first():
        raise HTTPException(
            status_code=400,
            detail="Já existe uma máquina cadastrada com este nome nesta produção.",
        )


def _next_sort_order(
    db: Session,
    destination: str,
    *,
    ignore_machine_id: int | None = None,
) -> int:
    query = db.query(func.max(ProductionMachine.sort_order)).filter(
        ProductionMachine.destination == destination
    )
    if ignore_machine_id is not None:
        query = query.filter(ProductionMachine.id != ignore_machine_id)
    current = query.scalar()
    return int(current or 0) + 1


def _serialize_machine(machine: ProductionMachine) -> ProductionMachineRegistryResponse:
    return ProductionMachineRegistryResponse.model_validate(machine)


@router.get("/", response_model=list[ProductionMachineRegistryResponse])
def list_production_machines_registry(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    machines = (
        db.query(ProductionMachine)
        .options(selectinload(ProductionMachine.operators))
        .order_by(ProductionMachine.destination.asc(), ProductionMachine.sort_order.asc(), ProductionMachine.id.asc())
        .all()
    )
    machines.sort(
        key=lambda machine: (
            0 if machine.destination == _DESTINATION_AR else 1,
            int(machine.sort_order or 0),
            int(machine.id or 0),
        )
    )
    return [_serialize_machine(machine) for machine in machines]


@router.post("/", response_model=ProductionMachineRegistryResponse, status_code=status.HTTP_201_CREATED)
def create_production_machine_registry(
    data: ProductionMachineRegistryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    destination = _canonical_destination(data.destination)
    name = normalize_upper_required(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Informe o nome da máquina")

    _ensure_unique_machine_name(db, destination=destination, name=name)
    operators = _upsert_operators(db, data.operators)

    machine = ProductionMachine(
        destination=destination,
        name=name,
        sort_order=_next_sort_order(db, destination),
        status=MachineOperationalStatus.FUNCIONANDO,
        updated_by_id=current_user.id,
        updated_at=datetime.utcnow(),
    )
    machine.operators = operators
    db.add(machine)
    db.flush()
    log_action(
        db,
        entity="production_machine",
        entity_id=machine.id,
        action="CREATE",
        changed_by=current_user,
        changes={
            "destination": destination,
            "name": name,
            "operators": [
                {"name": op.name, "role": getattr(op.role, "value", op.role)}
                for op in operators
            ],
        },
    )
    db.commit()
    return _serialize_machine(_load_machine_or_404(db, machine.id))


@router.patch("/{machine_id}", response_model=ProductionMachineRegistryResponse)
def update_production_machine_registry(
    machine_id: int,
    data: ProductionMachineRegistryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    machine = _load_machine_or_404(db, machine_id)

    destination = _canonical_destination(data.destination)
    name = normalize_upper_required(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Informe o nome da máquina")

    _ensure_unique_machine_name(
        db,
        destination=destination,
        name=name,
        ignore_machine_id=machine.id,
    )
    operators = _upsert_operators(db, data.operators)

    old_destination = machine.destination
    old_name = machine.name
    old_operators = [
        {"name": op.name, "role": getattr(op.role, "value", op.role)}
        for op in machine.operators
    ]

    if destination != machine.destination:
        machine.destination = destination
        machine.sort_order = _next_sort_order(db, destination, ignore_machine_id=machine.id)

    machine.name = name
    machine.operators = operators
    machine.updated_by_id = current_user.id
    machine.updated_at = datetime.utcnow()

    changes: dict[str, object] = {}
    if old_destination != machine.destination:
        changes["destination"] = {"old": old_destination, "new": machine.destination}
    if old_name != machine.name:
        changes["name"] = {"old": old_name, "new": machine.name}

    new_operators = [
        {"name": op.name, "role": getattr(op.role, "value", op.role)}
        for op in operators
    ]
    if old_operators != new_operators:
        changes["operators"] = {"old": old_operators, "new": new_operators}

    if changes:
        log_action(
            db,
            entity="production_machine",
            entity_id=machine.id,
            action="UPDATE",
            changed_by=current_user,
            changes=changes,
        )

    db.commit()
    return _serialize_machine(_load_machine_or_404(db, machine.id))
