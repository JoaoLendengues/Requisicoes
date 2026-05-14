from .database import SessionLocal
from .models.user import User, Role
from .services.auth_service import hash_password


def seed_admin() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.code == "1").first():
            return
        db.add(User(
            code="1",
            name="Administrador",
            email="admin@pinheiroferragens.com.br",
            hashed_password=hash_password("admin123"),
            role=Role.ADMIN,
            is_active=True,
        ))
        db.commit()
        print("[seed] Admin criado — código: 1 / senha: admin123")
    finally:
        db.close()
