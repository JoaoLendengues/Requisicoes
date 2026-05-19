from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import Base, engine
from .models import client, product, requisition, user  # garante registro dos modelos no SQLAlchemy
from .routers import auth, clients, products, requisitions, users
from .seed import seed_admin


def _migrate():
    """Aplica migracoes de colunas adicionadas apos criacao inicial do banco."""
    stmts = [
        "ALTER TABLE users ADD COLUMN sector TEXT",
        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0",
        "ALTER TABLE requisitions ADD COLUMN obs TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_code TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_name TEXT",
        "UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL",
        "UPDATE requisitions SET status = 'em_andamento' WHERE UPPER(status) IN "
        "('RASCUNHO','EMITIDA','RECEBIDA_PRODUCAO','PRONTA','EM_ROTA','AGUARDANDO_RETIRADA','CONCLUIDA')",
        "UPDATE requisitions SET status = 'em_producao' WHERE UPPER(status) = 'EM_FABRICACAO'",
        "UPDATE requisitions SET status = 'aguardando_recebimento' "
        "WHERE status = 'em_producao' AND finalized_at IS NULL",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate()
    seed_admin()
    yield


app = FastAPI(
    title="Ferragens Pinheiro - API de Requisicoes",
    version="1.0.0",
    description="API REST para gestao de requisicoes de obras.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(products.router)
app.include_router(requisitions.router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "service": "Ferragens Pinheiro API"}
