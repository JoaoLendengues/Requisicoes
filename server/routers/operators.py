"""CRUD de operadores — tabela independente, sem vínculo com usuários do sistema."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models.operator import Operator, OperatorRole
from ..models.user import User
from ..services.text_normalizer import normalize_upper_required

router = APIRouter(prefix="/operators", tags=["Operadores"])


def _normalize_operator_role(value: object) -> OperatorRole:
    normalized = str(value or "").strip().casefold()
    if normalized in {"ajudante", OperatorRole.AJUDANTE.value}:
        return OperatorRole.AJUDANTE
    if normalized in {"operador", OperatorRole.OPERADOR.value, ""}:
        return OperatorRole.OPERADOR
    raise ValueError("Função inválida. Use OPERADOR ou AJUDANTE.")


class OperatorResponse(BaseModel):
    id: int
    name: str
    role: OperatorRole
    model_config = {"from_attributes": True}


class OperatorCreate(BaseModel):
    name: str
    role: OperatorRole = OperatorRole.OPERADOR

    @field_validator("name", mode="before")
    @classmethod
    def normalize(cls, v: object) -> str:
        return normalize_upper_required(v)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> OperatorRole:
        return _normalize_operator_role(value)


class OperatorUpdate(OperatorCreate):
    pass


@router.get("/", response_model=list[OperatorResponse])
def list_operators(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Operator).order_by(Operator.name.asc()).all()


@router.post("/", response_model=OperatorResponse, status_code=status.HTTP_201_CREATED)
def create_operator(
    data: OperatorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(Operator).filter(Operator.name == data.name).first():
        raise HTTPException(status_code=400, detail="Já existe um operador com este nome.")
    op = Operator(name=data.name, role=data.role)
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


@router.patch("/{operator_id}", response_model=OperatorResponse)
def update_operator(
    operator_id: int,
    data: OperatorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    op = db.query(Operator).filter(Operator.id == operator_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operador não encontrado.")
    if db.query(Operator).filter(Operator.name == data.name, Operator.id != operator_id).first():
        raise HTTPException(status_code=400, detail="Já existe um operador com este nome.")
    op.name = data.name
    op.role = data.role
    db.commit()
    db.refresh(op)
    return op


@router.delete("/{operator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operator(
    operator_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    op = db.query(Operator).filter(Operator.id == operator_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operador não encontrado.")
    db.delete(op)
    db.commit()
