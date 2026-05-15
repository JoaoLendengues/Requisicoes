from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from ..database import get_db
from ..models.client import Client
from ..schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientBulkItem, BulkImportResult
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


@router.post("/bulk-import", response_model=BulkImportResult)
def bulk_import_clients(
    items: List[ClientBulkItem],
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Importa uma lista de clientes de uma vez.
    Clientes com código já existente são atualizados; os demais são criados.
    Tudo ocorre numa única transação — muito mais rápido que chamadas individuais.
    """
    result = BulkImportResult()

    # Carrega todos os clientes existentes indexados por código (uma só query)
    existing: dict[str, Client] = {
        c.code: c for c in db.query(Client).all()
    }

    cnpj_seen: set[str] = {
        c.cnpj for c in existing.values() if c.cnpj
    }

    for item in items:
        code = item.code.strip()
        name = item.name.strip()
        cnpj = item.cnpj.strip() if item.cnpj else None

        if not code or not name:
            result.skipped += 1
            continue

        if code in existing:
            # Atualiza nome e CNPJ (só sobrescreve CNPJ se não conflitar)
            cli = existing[code]
            cli.name = name
            if cnpj and (cnpj == cli.cnpj or cnpj not in cnpj_seen):
                if cli.cnpj and cli.cnpj in cnpj_seen:
                    cnpj_seen.discard(cli.cnpj)
                cli.cnpj = cnpj
                cnpj_seen.add(cnpj)
            result.updated += 1
        else:
            # Cria novo cliente; pula CNPJ se duplicado
            if cnpj and cnpj in cnpj_seen:
                cnpj = None
            new_cli = Client(code=code, name=name, cnpj=cnpj)
            db.add(new_cli)
            existing[code] = new_cli
            if cnpj:
                cnpj_seen.add(cnpj)
            result.created += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        result.errors.append(f"Erro ao salvar no banco: {str(e)}")
        result.created = 0
        result.updated = 0

    return result


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_client(
    client_id: int, db: Session = Depends(get_db), _=Depends(require_admin)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    client.is_active = False
    db.commit()
