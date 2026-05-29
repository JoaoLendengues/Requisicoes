"""CRUD de operadores — tabela independente, sem vínculo com usuários do sistema."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models.operator import Operator
from ..models.user import User
from ..services.text_normalizer import normalize_upper_required

router = APIRouter(prefix="/operators", tags=["Operadores"])


class OperatorResponse(BaseModel):
    id: int
    name: str
    model_config = {"from_attributes": True}


class OperatorCreate(BaseModel):
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def normalize(cls, v: object) -> str:
        return normalize_upper_required(v)


class OperatorUpdate(OperatorCreate):
    pass


@router.get("/", response_model=list[OperatorResponse])
def list_operators(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
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
    op = Operator(name=data.name)
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
