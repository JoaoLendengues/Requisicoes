from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from datetime import datetime
from ..database import get_db
from ..models.requisition import (
    Requisition, RequisitionItem, CanvasData, StatusHistory, RequisitionStatus,
)
from ..models.user import User, Role
from ..schemas.requisition import (
    RequisitionCreate, RequisitionUpdate, RequisitionResponse,
    StatusUpdate, CanvasUpdate,
)
from ..dependencies import get_current_user, require_creator

router = APIRouter(prefix="/requisitions", tags=["Requisições"])

_LOAD_OPTS = [
    selectinload(Requisition.items),
    selectinload(Requisition.status_history),
    selectinload(Requisition.canvas),
    selectinload(Requisition.client),
    selectinload(Requisition.vendor),
]


def _get_or_404(db: Session, req_id: int) -> Requisition:
    req = db.query(Requisition).options(*_LOAD_OPTS).filter(Requisition.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requisição não encontrada")
    return req


@router.get("/", response_model=List[RequisitionResponse])
def list_requisitions(
    req_status: Optional[RequisitionStatus] = Query(None, alias="status"),
    client_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Requisition).options(*_LOAD_OPTS)

    if req_status:
        q = q.filter(Requisition.status == req_status)
    if client_id:
        q = q.filter(Requisition.client_id == client_id)
    if vendor_id:
        q = q.filter(Requisition.vendor_id == vendor_id)
    if search:
        q = q.filter(Requisition.ped_number.ilike(f"%{search}%"))

    # Vendedor e gerente só veem as próprias requisições
    if current_user.role in (Role.VENDEDOR, Role.GERENTE):
        q = q.filter(Requisition.vendor_id == current_user.id)

    return q.order_by(Requisition.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=RequisitionResponse, status_code=status.HTTP_201_CREATED)
def create_requisition(
    data: RequisitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_creator),
):
    items_data = data.items
    req = Requisition(**data.model_dump(exclude={"items"}), vendor_id=current_user.id)
    db.add(req)
    db.flush()

    for item in items_data:
        db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))

    db.add(CanvasData(requisition_id=req.id))
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=None,
        new_status=RequisitionStatus.EM_ANDAMENTO,
        changed_by_id=current_user.id,
    ))
    db.commit()
    return _get_or_404(db, req.id)


@router.get("/{req_id}", response_model=RequisitionResponse)
def get_requisition(
    req_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    return _get_or_404(db, req_id)


@router.patch("/{req_id}", response_model=RequisitionResponse)
def update_requisition(
    req_id: int,
    data: RequisitionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Requisição cancelada não pode ser editada",
        )

    for k, v in data.model_dump(exclude_unset=True, exclude={"items"}).items():
        setattr(req, k, v)

    if data.items is not None:
        for item in list(req.items):
            db.delete(item)
        db.flush()
        for item in data.items:
            db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))

    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/status", response_model=RequisitionResponse)
def update_status(
    req_id: int,
    data: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    old_status = req.status
    req.status = data.status

    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=data.status,
        changed_by_id=current_user.id,
        note=data.note,
    ))
    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/canvas", response_model=RequisitionResponse)
def update_canvas(
    req_id: int,
    data: CanvasUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    if req.canvas:
        req.canvas.json_data = data.json_data
    else:
        db.add(CanvasData(requisition_id=req.id, json_data=data.json_data))
    db.commit()
    return _get_or_404(db, req_id)


@router.patch("/{req_id}/nf", response_model=RequisitionResponse)
def attach_nf(
    req_id: int,
    nf_path: str,
    db: Session = Depends(get_db),
    _=Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    req.nf_attachment = nf_path
    db.commit()
    return _get_or_404(db, req_id)


@router.delete("/{req_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _get_or_404(db, req_id)
    old_status = req.status
    req.status = RequisitionStatus.CANCELADA
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=RequisitionStatus.CANCELADA,
        changed_by_id=current_user.id,
    ))
    db.commit()
