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
        term = search.strip()
        plain = (
            term.replace(".", "")
            .replace("-", "")
            .replace("/", "")
            .replace(" ", "")
        )
        plain_nozero = plain.lstrip("0")
        term_upper = term.upper()

        s = f"%{term}%"
        plain_s = f"%{plain}%"

        clean_code = func.replace(Client.code, ".", "")
        clean_cnpj = func.replace(
            func.replace(
                func.replace(Client.cnpj, ".", ""),
                "-",
                "",
            ),
            "/",
            "",
        )

        filters = [
            Client.name.ilike(s),
            Client.code.ilike(s),
            Client.cnpj.ilike(s),
        ]
        if plain:
            filters.extend([
                clean_code.ilike(plain_s),
                clean_cnpj.ilike(plain_s),
            ])
            if plain_nozero:
                filters.append(func.ltrim(clean_code, "0").ilike(f"%{plain_nozero}%"))

        q = q.filter(or_(*filters))

        rank_rules = [
            (func.upper(Client.code) == term_upper, 0),
            (func.upper(Client.code).like(f"{term_upper}%"), 1),
            (func.upper(Client.name).like(f"{term_upper}%"), 4),
        ]
        if plain:
            plain_upper = plain.upper()
            rank_rules.extend([
                (func.upper(clean_code) == plain_upper, 2),
                (func.upper(clean_cnpj) == plain_upper, 2),
                (func.upper(clean_code).like(f"{plain_upper}%"), 3),
                (func.upper(clean_cnpj).like(f"{plain_upper}%"), 3),
            ])
            if plain_nozero:
                plain_nozero_upper = plain_nozero.upper()
                rank_rules.append(
                    (func.upper(func.ltrim(clean_code, "0")) == plain_nozero_upper, 2)
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
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
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
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(client, k, v)

    db.commit()
    db.refresh(client)
    return client


@router.post("/import/bulk", response_model=BulkImportResult)
@router.post("/bulk-import", response_model=BulkImportResult)
def bulk_import_clients(
    items: List[ClientBulkItem],
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Importa uma lista de clientes de uma vez.
    Clientes com codigo ja existente sao atualizados; os demais sao criados.
    Tudo ocorre numa unica transacao - muito mais rapido que chamadas individuais.
    """
    result = BulkImportResult()

    # Carrega todos os clientes existentes indexados por codigo (uma so query)
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
            # Atualiza nome e CNPJ (so sobrescreve CNPJ se nao conflitar)
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
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    client.is_active = False
    db.commit()
