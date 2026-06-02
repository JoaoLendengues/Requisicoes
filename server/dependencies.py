from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models.user import User, Role
from .services.auth_service import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado"
        )
    user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado"
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return current_user


def require_manager_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (Role.ADMIN, Role.GERENTE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a gerentes e administradores",
        )
    return current_user


def require_order_center_access(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (
        Role.ADMIN, Role.GERENTE, Role.VENDEDOR, Role.PRODUCAO, Role.INDUSTRIA, Role.ENTREGA,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para acessar a Central de Pedidos",
        )
    return current_user


def require_creator(current_user: User = Depends(get_current_user)) -> User:
    # Roles autorizados a criar/editar requisicoes:
    #   - ADMIN, GERENTE: gestao plena
    #   - VENDEDOR: cria pedidos comerciais (caso comum)
    #   - PRODUCAO: cria pedidos de compra para o diretor comercial autorizar
    # Roles REMOVIDOS (Jun/2026):
    #   - INDUSTRIA: so recebe requisicoes ja criadas para fabricar
    #   - ENTREGA: so recebe requisicoes marcadas como "entrega" no form
    if current_user.role not in (
        Role.ADMIN,
        Role.VENDEDOR,
        Role.GERENTE,
        Role.PRODUCAO,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para criar ou editar requisições",
        )
    return current_user
