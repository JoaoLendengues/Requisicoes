from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import or_
from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models.product import Product
from ..schemas.product import (
    ProductBulkImportResult,
    ProductBulkItem,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from ..services.text_normalizer import normalize_upper_required

router = APIRouter(prefix="/products", tags=["Produtos"])


@router.get("/", response_model=List[ProductResponse])
def list_products(
    search: Optional[str] = None,
    code: Optional[str] = None,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Product).filter(Product.is_active == True)

    if code:
        q = q.filter(Product.code == normalize_upper_required(code))
    elif search:
        search_term = f"%{search.strip()}%"
        q = q.filter(or_(
            Product.code.ilike(search_term),
            Product.name.ilike(search_term),
        ))

    return q.order_by(Product.name).limit(limit).all()


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if db.query(Product).filter(Product.code == data.code).first():
        raise HTTPException(status_code=400, detail="Código já cadastrado")

    product = Product(**data.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Erro ao salvar produto")
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return product


@router.post("/import/bulk", response_model=ProductBulkImportResult)
def bulk_import_products(
    items: List[ProductBulkItem],
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    result = ProductBulkImportResult()
    existing: dict[str, Product] = {
        product.code: product for product in db.query(Product).all()
    }

    for item in items:
        code = item.code.strip()
        name = item.name.strip()

        if not code or not name:
            result.skipped += 1
            continue

        if code in existing:
            existing[code].name = name
            existing[code].is_active = True
            result.updated += 1
        else:
            product = Product(code=code, name=name)
            db.add(product)
            existing[code] = product
            result.created += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        result.errors.append(f"Erro ao salvar no banco: {exc}")
        result.created = 0
        result.updated = 0

    return result
