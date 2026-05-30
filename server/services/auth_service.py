from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from ..models.user import User
from ..config import settings
from .text_normalizer import normalize_upper_required


def _normalize_password(password: str) -> str:
    return str(password or "").strip().casefold()


def hash_password(password: str) -> str:
    normalized = _normalize_password(password)
    return bcrypt.hashpw(normalized.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    normalized = _normalize_password(plain)
    return (
        bcrypt.checkpw(normalized.encode(), hashed.encode())
        or bcrypt.checkpw(str(plain).encode(), hashed.encode())
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def authenticate_user(db: Session, code: str, password: str) -> Optional[User]:
    user = get_active_user_by_code(db, code)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def get_active_user_by_code(db: Session, code: str) -> Optional[User]:
    normalized_code = normalize_upper_required(code)
    if not normalized_code:
        return None
    return db.query(User).filter(User.code == normalized_code, User.is_active == True).first()


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
