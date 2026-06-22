from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models.user import User
from ..schemas.auth import (
    ChangePasswordRequest,
    FirstAccessRequest,
    FirstAccessStatusResponse,
    LoginRequest,
    Token,
)
from ..schemas.user import UserResponse
from ..services.audit_service import log_login
from ..services.auth_service import (
    authenticate_user,
    create_access_token,
    get_active_user_by_code,
    hash_password,
    verify_password,
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
        found=bool(user),
        user_name=(user.name if user else None),
        first_access_required=_requires_first_access(user),
    )


@router.post("/login", response_model=Token)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    candidate = get_active_user_by_code(db, data.code)

    if _requires_first_access(candidate):
        log_login(db, code=data.code, success=False, ip_address=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Primeiro acesso pendente. Cadastre sua senha antes de entrar.",
        )

    user = authenticate_user(db, data.code, data.password)
    if not user:
        log_login(db, code=data.code, success=False, ip_address=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Codigo ou senha invalidos",
        )

    user.last_login_at = datetime.utcnow()
    log_login(db, code=data.code, success=True, user_id=user.id, ip_address=ip)
    db.commit()
    db.refresh(user)
    return _build_token(user)


@router.post("/first-access", response_model=Token)
def first_access(data: FirstAccessRequest, db: Session = Depends(get_db)):
    user = get_active_user_by_code(db, data.code)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado para primeiro acesso",
        )

    if not user.must_change_password and (user.hashed_password or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esse usuário já possui senha cadastrada. Use o login normal.",
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


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_pwd = (data.current_password or "").strip()
    new_pwd     = (data.new_password     or "").strip()

    if not current_pwd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Informe a senha atual.")
    if len(new_pwd) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="A nova senha precisa ter pelo menos 6 caracteres.")
    if not verify_password(current_pwd, current_user.hashed_password or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Senha atual incorreta.")

    current_user.hashed_password    = hash_password(new_pwd)
    current_user.must_change_password = False
    db.commit()
    return {"message": "Senha alterada com sucesso."}
