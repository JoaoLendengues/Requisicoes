from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.user import User
from ..schemas.auth import FirstAccessRequest, LoginRequest, Token
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
    )


@router.post("/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    candidate = get_active_user_by_code(db, data.code)
    if candidate and candidate.must_change_password and not (candidate.hashed_password or "").strip():
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
    db.commit()
    db.refresh(user)
    return _build_token(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
