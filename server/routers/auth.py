from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.user import User
from ..schemas.auth import (
    FirstAccessRequest,
    FirstAccessStatusResponse,
    LoginRequest,
    Token,
)
from ..schemas.user import UserResponse
from ..services.auth_service import (
    authenticate_user,
    create_access_token,
    get_active_user_by_code,
    hash_password,
)

router = APIRouter(prefix="/auth", tags=["Autenticacao"])


def _build_token(user: User) -> Token:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return Token(
        access_token=token,
        user_id=user.id,
        user_name=user.name,
        user_code=user.code,
        role=user.role,
        whatsapp=user.whatsapp or "",
    )


def _requires_first_access(user: User | None) -> bool:
    if not user:
        return False
    return bool(user.must_change_password and not (user.hashed_password or "").strip())


@router.get("/first-access-status", response_model=FirstAccessStatusResponse)
def first_access_status(code: str, db: Session = Depends(get_db)):
    user = get_active_user_by_code(db, code)
    return FirstAccessStatusResponse(
        code=(code or "").strip(),
        first_access_required=_requires_first_access(user),
    )


@router.post("/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    candidate = get_active_user_by_code(db, data.code)
    if _requires_first_access(candidate):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Primeiro acesso pendente. Cadastre sua senha antes de entrar.",
        )

    user = authenticate_user(db, data.code, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Codigo ou senha invalidos",
        )
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return _build_token(user)


@router.post("/first-access", response_model=Token)
def first_access(data: FirstAccessRequest, db: Session = Depends(get_db)):
    user = get_active_user_by_code(db, data.code)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado para primeiro acesso",
        )

    if not user.must_change_password and (user.hashed_password or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esse usuario ja possui senha cadastrada. Use o login normal.",
        )

    password = (data.password or "").strip()
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha precisa ter pelo menos 6 caracteres.",
        )

    user.hashed_password = hash_password(password)
    user.must_change_password = False
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return _build_token(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
