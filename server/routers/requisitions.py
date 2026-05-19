from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from datetime import datetime
from ..database import get_db
from ..models.client import Client
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

_PROD_NOTE_PREFIX = "PRODUCAO"
_PROD_SEND = "ENVIADA"
_PROD_RECEIVED = "RECEBIDA"
_PROD_FINISHED = "FINALIZADA"
_PROD_CANCELED = "CANCELADA"


def _get_or_404(db: Session, req_id: int) -> Requisition:
    req = db.query(Requisition).options(*_LOAD_OPTS).filter(Requisition.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requisição não encontrada")
    return req


def _sum_item_weights(items: Optional[list]) -> float:
    return sum((item.weight or 0.0) for item in (items or []))


def _parse_production_note(note: Optional[str]) -> dict | None:
    if not note:
        return None

    parts = str(note).split("|", 3)
    if len(parts) < 3 or parts[0] != _PROD_NOTE_PREFIX:
        return None

    data = {
        "action": parts[1].strip(),
        "target": parts[2].strip(),
        "reason": "",
    }
    if len(parts) > 3:
        data["reason"] = parts[3].strip()
    return data


def _is_locked_for_edit(req: Requisition) -> bool:
    return req.finalized_at is not None


def _ensure_editable(req: Requisition):
    if req.status == RequisitionStatus.CANCELADA:
        raise HTTPException(
            status_code=400,
            detail="Requisição cancelada não pode ser editada",
        )
    if _is_locked_for_edit(req):
        raise HTTPException(
            status_code=400,
            detail="Requisição em produção recebida ou finalizada não pode ser editada",
        )


def _apply_production_transition(req: Requisition, status_update: StatusUpdate):
    prod_event = _parse_production_note(status_update.note)
    if not prod_event:
        return

    action = prod_event["action"]
    reason = prod_event["reason"]

    if action == _PROD_SEND:
        req.status = RequisitionStatus.AGUARDANDO_RECEBIMENTO
        req.finalized_at = None
        return

    if action == _PROD_RECEIVED:
        if req.status not in (
            RequisitionStatus.AGUARDANDO_RECEBIMENTO,
            RequisitionStatus.EM_PRODUCAO,
        ):
            raise HTTPException(
                status_code=400,
                detail="Somente requisições aguardando recebimento podem confirmar recebimento",
            )
        if req.finalized_at is not None:
            raise HTTPException(
                status_code=400,
                detail="O recebimento desta requisição já foi confirmado",
            )
        req.status = RequisitionStatus.EM_PRODUCAO
        req.finalized_at = datetime.utcnow()
        return

    if action == _PROD_FINISHED:
        if req.status != RequisitionStatus.EM_PRODUCAO:
            raise HTTPException(
                status_code=400,
                detail="Somente requisições em produção podem ser finalizadas",
            )
        if req.finalized_at is None:
            raise HTTPException(
                status_code=400,
                detail="Confirme o recebimento antes de finalizar a produção",
            )
        req.status = RequisitionStatus.EM_ANDAMENTO
        return

    if action == _PROD_CANCELED:
        if len(reason.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Informe um motivo de cancelamento com pelo menos 10 caracteres",
            )
        req.status = RequisitionStatus.EM_ANDAMENTO
        req.finalized_at = None
        return


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
        search_term = f"%{search.strip()}%"
        q = q.join(Requisition.client).filter(or_(
            Requisition.ped_number.ilike(search_term),
            Requisition.obra.ilike(search_term),
            Client.name.ilike(search_term),
            Client.code.ilike(search_term),
        ))

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
    req = Requisition(
        **data.model_dump(exclude={"items", "weight"}),
        vendor_id=current_user.id,
        weight=_sum_item_weights(items_data),
    )
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
    _ensure_editable(req)

    for k, v in data.model_dump(exclude_unset=True, exclude={"items", "weight"}).items():
        setattr(req, k, v)

    if data.items is not None:
        for item in list(req.items):
            db.delete(item)
        db.flush()
        for item in data.items:
            db.add(RequisitionItem(**item.model_dump(), requisition_id=req.id))
        req.weight = _sum_item_weights(data.items)
    elif data.weight is not None:
        req.weight = data.weight

    db.commit()
    return _get_or_404(db, req_id)


def _build_notifications(
    db: Session,
    req: Requisition,
    old_status: RequisitionStatus,
    new_status: RequisitionStatus,
    note: str | None,
) -> list:
    from ..services.notification_service import build_production_sent, build_vendor_event

    prod = _parse_production_note(note)
    notifs = []

    if prod:
        action = prod["action"]
        if action == _PROD_SEND:
            notifs.extend(build_production_sent(db, req, prod["target"]))
        elif action == _PROD_RECEIVED:
            n = build_vendor_event(db, req, "em_producao")
            if n:
                notifs.append(n)
        elif action == _PROD_FINISHED:
            n = build_vendor_event(db, req, "finalizada")
            if n:
                notifs.append(n)
        elif action == _PROD_CANCELED:
            n = build_vendor_event(db, req, "prod_cancelada", prod.get("reason", ""))
            if n:
                notifs.append(n)
    elif new_status == RequisitionStatus.CANCELADA:
        n = build_vendor_event(db, req, "cancelada")
        if n:
            notifs.append(n)

    return notifs


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
    _apply_production_transition(req, data)
    new_status = req.status

    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=current_user.id,
        note=data.note,
    ))

    notifications = _build_notifications(db, req, old_status, new_status, data.note)
    db.commit()

    from ..services.notification_service import push_all
    push_all(notifications)

    return _get_or_404(db, req_id)


@router.patch("/{req_id}/canvas", response_model=RequisitionResponse)
def update_canvas(
    req_id: int,
    data: CanvasUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_creator),
):
    req = _get_or_404(db, req_id)
    _ensure_editable(req)
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
    _ensure_editable(req)
    req.nf_attachment = nf_path
    db.commit()
    return _get_or_404(db, req_id)


@router.delete("/{req_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_requisition(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from ..services.notification_service import build_vendor_event, push_all

    req = _get_or_404(db, req_id)
    old_status = req.status
    req.status = RequisitionStatus.CANCELADA
    db.add(StatusHistory(
        requisition_id=req.id,
        old_status=old_status,
        new_status=RequisitionStatus.CANCELADA,
        changed_by_id=current_user.id,
    ))

    # Notifica o vendedor somente se quem cancelou não é ele mesmo
    notifs = []
    if req.vendor_id != current_user.id:
        n = build_vendor_event(db, req, "cancelada")
        if n:
            notifs.append(n)

    db.commit()
    push_all(notifs)
