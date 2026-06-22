from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.database import Base
from server.models.user import Role, User
from server.routers.auth import first_access_status


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_first_access_status_returns_registered_name_for_active_user():
    db = _database()
    user = User(
        code="123",
        name="JOAO SILVA",
        hashed_password="",
        role=Role.VENDEDOR,
        must_change_password=True,
        is_active=True,
    )
    db.add(user)
    db.commit()

    response = first_access_status("123", db)

    assert response.code == "123"
    assert response.found is True
    assert response.user_name == "JOAO SILVA"
    assert response.first_access_required is True


def test_first_access_status_does_not_expose_inactive_or_unknown_user():
    db = _database()
    inactive_user = User(
        code="321",
        name="USUARIO INATIVO",
        hashed_password="secret",
        role=Role.VENDEDOR,
        must_change_password=False,
        is_active=False,
    )
    db.add(inactive_user)
    db.commit()

    inactive_response = first_access_status("321", db)
    missing_response = first_access_status("999", db)

    assert inactive_response.found is False
    assert inactive_response.user_name is None
    assert inactive_response.first_access_required is False

    assert missing_response.found is False
    assert missing_response.user_name is None
    assert missing_response.first_access_required is False
