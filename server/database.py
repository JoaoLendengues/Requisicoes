from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


def _build_engine():
    if settings.DATABASE_TYPE == "sqlite":
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")   # melhor concorrência de leitura
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    # Oracle / PostgreSQL — só muda a URL no .env
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
