from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from .database import engine, Base
from .models import user, client, product, requisition  # garante registro dos modelos no SQLAlchemy
from .routers import auth, users, clients, products, requisitions
from .seed import seed_admin


def _migrate():
    """Aplica migrações de colunas adicionadas após criação inicial do banco."""
    stmts = [
        "ALTER TABLE requisitions ADD COLUMN obs TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_code TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_name TEXT",
        # Migração de status — cobre tanto valores minúsculos quanto nomes em maiúsculo
        "UPDATE requisitions SET status = 'em_andamento' WHERE UPPER(status) IN "
        "('RASCUNHO','EMITIDA','RECEBIDA_PRODUCAO','PRONTA','EM_ROTA','AGUARDANDO_RETIRADA','CONCLUIDA')",
        "UPDATE requisitions SET status = 'em_producao' WHERE UPPER(status) = 'EM_FABRICACAO'",
    ]
    with engine.begin() as conn:
        for s in stmts:
            try:
                conn.execute(text(s))
            except Exception:
                pass   # coluna já existe


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate()
    seed_admin()
    yield


app = FastAPI(
    title="Ferragens Pinheiro — API de Requisições",
    version="1.0.0",
    description="API REST para gestão de requisições de obras. Compatível com clientes Java via endpoints padrão.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # restringir em produção
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
