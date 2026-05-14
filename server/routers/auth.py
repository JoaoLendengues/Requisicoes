from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas.auth import LoginRequest, Token
from ..schemas.user import UserResponse
from ..services.auth_service import authenticate_user, create_access_token
from ..dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.code, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código ou senha inválidos",
        )
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return Token(
        access_token=token,
        user_id=user.id,
        user_name=user.name,
        user_code=user.code,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
