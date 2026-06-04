import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin, require_manager_or_admin
from ..models.user import Role, User
from ..schemas.user import (
    UserBulkImportResult,
    UserBulkItem,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from ..services.audit_service import diff_fields, log_action
from ..services.auth_service import hash_password
from ..services.text_normalizer import natural_sort_key, normalize_upper_required

router = APIRouter(prefix="/users", tags=["Usuarios"])


def _normalize_code(code: str) -> str:
    return normalize_upper_required(code)


def _auto_email(code: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", ".", _normalize_code(code).lower()).strip(".")
    if not normalized:
        normalized = "usuario"
    return f"{normalized}@usuarios.local"


def _resolve_email(code: str, email: str | None) -> str:
    text = (email or "").strip().lower()
    return text or _auto_email(code)


def _normalize_role_for_storage(role: Role | None) -> Role | None:
    if role == Role.ENTREGAS:
        return Role.ENTREGA
    return role


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


def _ensure_unique_identity(
    db: Session,
    *,
    code: str,
    email: str | None,
    ignore_user_id: int | None = None,
):
    code_query = db.query(User).filter(User.code == code)
    if ignore_user_id is not None:
        code_query = code_query.filter(User.id != ignore_user_id)
    if code_query.first():
        raise HTTPException(status_code=400, detail="Codigo ja cadastrado")

    if email:
        email_query = db.query(User).filter(User.email == email)
        if ignore_user_id is not None:
            email_query = email_query.filter(User.id != ignore_user_id)
        if email_query.first():
            raise HTTPException(status_code=400, detail="Email ja cadastrado")


@router.get("/", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), _=Depends(require_manager_or_admin)):
    users = db.query(User).all()
    users.sort(
        key=lambda user: (
            natural_sort_key(getattr(user, "code", "")),
            natural_sort_key(getattr(user, "name", "")),
            int(getattr(user, "id", 0) or 0),
        )
    )
    return users


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    code = _normalize_code(data.code)
    if not code:
        raise HTTPException(status_code=400, detail="Informe o codigo do usuario")

    email = _resolve_email(code, data.email)
    _ensure_unique_identity(db, code=code, email=email)

    password = (data.password or "").strip()
    user = User(
        code=code,
        name=(data.name or "").strip(),
        email=email,
        hashed_password=hash_password(password) if password else "",
        role=_normalize_role_for_storage(data.role),
        whatsapp=(data.whatsapp or "").strip() or None,
        sector=(data.sector or "").strip() or None,
        must_change_password=not bool(password),
        is_active=bool(data.is_active),
    )
    db.add(user)
    db.flush()
    log_action(
        db,
        entity="user",
        entity_id=user.id,
        action="CREATE",
        changed_by=current_user,
        changes={"code": code, "name": user.name, "role": str(data.role)},
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/import/bulk", response_model=UserBulkImportResult)
def bulk_import_users(
    items: List[UserBulkItem],
    db: Session = Depends(get_db),
    _=Depends(require_manager_or_admin),
):
    result = UserBulkImportResult()
    existing = {user.code: user for user in db.query(User).all()}

    for item in items:
        code = _normalize_code(item.code)
        name = str(item.name or "").strip()
        contact = str(item.contact or "").strip() or None
        sector = str(item.sector or "").strip() or None

        if not code or not name:
            result.skipped += 1
            continue

        if code in existing:
            user = existing[code]
            user.name = name
            user.whatsapp = contact
            user.sector = sector
            user.email = user.email or _auto_email(code)
            user.is_active = True
            if not (user.hashed_password or "").strip():
                user.must_change_password = True
            result.updated += 1
            continue

        new_user = User(
            code=code,
            name=name,
            email=_auto_email(code),
            hashed_password="",
            role=Role.VENDEDOR,
            whatsapp=contact,
            sector=sector,
            must_change_password=True,
            is_active=True,
        )
        db.add(new_user)
        existing[code] = new_user
        result.created += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        result.errors.append(f"Erro ao salvar usuarios: {exc}")
        result.created = 0
        result.updated = 0
    return result


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), _=Depends(require_manager_or_admin)):
    return _get_user_or_404(db, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    user = _get_user_or_404(db, user_id)
    update_data = data.model_dump(exclude_unset=True)

    new_code = _normalize_code(update_data.get("code", user.code))
    if not new_code:
        raise HTTPException(status_code=400, detail="Informe o codigo do usuario")

    email = _resolve_email(new_code, update_data.get("email", user.email))
    _ensure_unique_identity(db, code=new_code, email=email, ignore_user_id=user.id)

    # Captura mudanças antes de aplicar
    changes = diff_fields(user, update_data, ["name", "role", "whatsapp", "sector", "is_active"])
    if new_code != user.code:
        changes["code"] = {"old": user.code, "new": new_code}
    if update_data.get("password"):
        changes["password"] = {"old": "***", "new": "*** (alterada)"}

    user.code = new_code
    user.email = email

    if "name" in update_data:
        user.name = (update_data["name"] or "").strip()
    if "role" in update_data and update_data["role"] is not None:
        user.role = _normalize_role_for_storage(update_data["role"])
    if "whatsapp" in update_data:
        user.whatsapp = (update_data["whatsapp"] or "").strip() or None
    if "sector" in update_data:
        user.sector = (update_data["sector"] or "").strip() or None
    if "is_active" in update_data and update_data["is_active"] is not None:
        user.is_active = bool(update_data["is_active"])

    password = update_data.get("password")
    if password is not None:
        password = str(password).strip()
        if password:
            user.hashed_password = hash_password(password)
            user.must_change_password = False
        elif not (user.hashed_password or "").strip():
            user.must_change_password = True

    if changes:
        log_action(db, entity="user", entity_id=user.id, action="UPDATE",
                   changed_by=current_user, changes=changes)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    user = _get_user_or_404(db, user_id)
    user.is_active = False
    log_action(
        db,
        entity="user",
        entity_id=user.id,
        action="DELETE",
        changed_by=current_user,
        changes={"code": user.code, "name": user.name, "is_active": {"old": "True", "new": "False"}},
    )
    db.commit()
