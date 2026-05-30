import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case, func, or_
from typing import List, Optional
from ..database import get_db
from ..models.client import Client
from ..schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientBulkItem, BulkImportResult
from ..dependencies import get_current_user, require_admin

router = APIRouter(prefix="/clients", tags=["Clientes"])


@router.get("/", response_model=List[ClientResponse])
def list_clients(
    search: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Client).filter(Client.is_active == True)

    if search:
        term       = search.strip()
        plain      = re.sub(r"[^0-9]", "", term)   # somente dígitos (para busca por CNPJ/código)
        plain_nzero = plain.lstrip("0")
        term_upper  = term.upper()

        s = f"%{term}%"

        # Filtros de busca por nome/código/CNPJ
        filters = [
            Client.name.ilike(s),
            Client.code.ilike(s),
            Client.cnpj.ilike(s),
        ]
        if plain:
            clean_code = func.replace(Client.code, ".", "")
            # CNPJ sem separadores — calculado em runtime via replace aninhado
            cnpj_raw = func.replace(
                func.replace(
                    func.replace(
                        func.replace(func.coalesce(Client.cnpj, ""), ".", ""),
                        "-", ""),
                    "/", ""),
                " ", "")
            filters.extend([
                clean_code.ilike(f"%{plain}%"),
                cnpj_raw.ilike(f"%{plain}%"),
            ])
            if plain_nzero:
                filters.append(func.ltrim(clean_code, "0").ilike(f"%{plain_nzero}%"))

        q = q.filter(or_(*filters))

        # Ordenação por relevância: correspondência exata primeiro
        rank_rules: list = [
            (func.upper(Client.code) == term_upper, 0),
            (func.upper(Client.code).like(f"{term_upper}%"), 1),
            (func.upper(Client.name).like(f"{term_upper}%"), 4),
        ]
        if plain:
            cnpj_raw = func.replace(
                func.replace(
                    func.replace(
                        func.replace(func.coalesce(Client.cnpj, ""), ".", ""),
                        "-", ""),
                    "/", ""),
                " ", "")
            rank_rules.extend([
                (cnpj_raw == plain, 2),
                (cnpj_raw.like(f"{plain}%"), 3),
            ])
            plain_upper = plain.upper()
            clean_code_upper = func.upper(func.replace(Client.code, ".", ""))
            rank_rules.extend([
                (clean_code_upper == plain_upper, 2),
                (clean_code_upper.like(f"{plain_upper}%"), 3),
            ])
            if plain_nzero:
                rank_rules.append(
                    (func.upper(func.ltrim(func.replace(Client.code, ".", ""), "0")) == plain_nzero.upper(), 2)
                )

        relevance = case(*rank_rules, else_=9)
        return q.order_by(relevance, Client.name).limit(limit).all()

    return q.order_by(Client.name).limit(limit).all()


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    data: ClientCreate, db: Session = Depends(get_db), _=Depends(require_admin)
):
    if db.query(Client).filter(Client.code == data.code).first():
        raise HTTPException(status_code=400, detail="Codigo ja cadastrado")

    client = Client(**data.model_dump())
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="CNPJ ja cadastrado para outro cliente")
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

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(client, k, v)

    db.commit()
    db.refresh(client)
    return client


@router.post("/import/bulk", response_model=BulkImportResult)
def bulk_import_clients(
    items: List[ClientBulkItem],
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Importa uma lista de clientes de uma vez.
    Clientes com código já existente são atualizados; os demais são criados.
    Tudo ocorre numa única transação - muito mais rápido que chamadas individuais.
    """
    result = BulkImportResult()

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
            cli = existing[code]
            cli.name = name
            if cnpj and (cnpj == cli.cnpj or cnpj not in cnpj_seen):
                if cli.cnpj and cli.cnpj in cnpj_seen:
                    cnpj_seen.discard(cli.cnpj)
                cli.cnpj = cnpj
                cnpj_seen.add(cnpj)
            result.updated += 1
        else:
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
