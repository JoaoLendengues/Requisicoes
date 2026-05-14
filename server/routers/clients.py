from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from ..database import get_db
from ..models.client import Client
from ..schemas.client import ClientCreate, ClientUpdate, ClientResponse
from ..dependencies import get_current_user, require_admin

router = APIRouter(prefix="/clients", tags=["Clientes"])


@router.get("/", response_model=List[ClientResponse])
def list_clients(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Client).filter(Client.is_active == True)
    if search:
        q = q.filter(Client.name.ilike(f"%{search}%"))
    return q.order_by(Client.name).all()


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    data: ClientCreate, db: Session = Depends(get_db), _=Depends(require_admin)
):
    if db.query(Client).filter(Client.code == data.code).first():
        raise HTTPException(status_code=400, detail="Código já cadastrado")

    client = Client(**data.model_dump())
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="CNPJ já cadastrado para outro cliente")
    db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: int,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(client, k, v)

    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_client(
    client_id: int, db: Session = Depends(get_db), _=Depends(require_admin)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    client.is_active = False
    db.commit()
