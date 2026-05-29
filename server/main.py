import asyncio
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import Base, engine
from .models import audit, client, feedback, notification, operator, product, production_machine, requisition, user  # garante registro dos modelos no SQLAlchemy
from .routers import (
    auth,
    backup,
    clients,
    feedbacks,
    notifications,
    operators,
    production_machines,
    products,
    requisitions,
    system_settings,
    users,
)
from .seed import seed_admin, seed_production_machines
from .services.backup_service import backup_scheduler
from .services.runtime_monitor import record_exception, record_request
from .services.text_normalizer import normalize_existing_user_written_data


def _migrate():
    """Aplica migracoes de colunas adicionadas apos criacao inicial do banco.
    Cada statement roda em sua propria transacao para evitar que uma falha
    (ex: coluna ja existe) aborte as demais — necessario no PostgreSQL.
    """
    stmts = [
        "ALTER TABLE users ADD COLUMN sector TEXT",
        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP",
        "ALTER TABLE requisitions ADD COLUMN obs TEXT",
        "ALTER TABLE requisitions ADD COLUMN production_destination TEXT",
        "ALTER TABLE requisitions ADD COLUMN production_machine TEXT",
        "ALTER TABLE requisitions ADD COLUMN cancel_reason TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_code TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_name TEXT",
        "UPDATE users SET must_change_password = FALSE WHERE must_change_password IS NULL",
        "UPDATE users SET role = 'industria' WHERE role = 'entrega'",
        "UPDATE requisitions SET status = 'em_andamento' WHERE UPPER(status) IN "
        "('RASCUNHO','EMITIDA','RECEBIDA_PRODUCAO','PRONTA','EM_ROTA','AGUARDANDO_RETIRADA','CONCLUIDA')",
        "UPDATE requisitions SET status = 'em_producao' WHERE UPPER(status) = 'EM_FABRICACAO'",
        "UPDATE requisitions SET status = 'aguardando_recebimento' "
        "WHERE status = 'em_producao' AND finalized_at IS NULL",
        "UPDATE requisitions SET status = 'aguardando_na_fila' "
        "WHERE status = 'em_producao' AND production_machine IS NULL AND finalized_at IS NOT NULL",

        # ── Índices de busca rápida de clientes (pg_trgm) ─────────────────────
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "ALTER TABLE clients ADD COLUMN cnpj_digits VARCHAR(20)",
        # Backfill PostgreSQL: usa regexp_replace (roda uma vez, fica no histórico)
        "UPDATE clients SET cnpj_digits = regexp_replace(coalesce(cnpj, ''), '[^0-9]', '', 'g') "
        "WHERE cnpj IS NOT NULL AND cnpj_digits IS NULL",
        # Backfill compatível com SQLite e PostgreSQL: re-executa a cada boot
        # para corrigir registros que ficaram com cnpj_digits NULL ou vazio.
        # replace() aninhado remove os separadores típicos de CPF/CNPJ (.  -  /  espaço).
        "UPDATE clients SET cnpj_digits = replace(replace(replace(replace("
        "coalesce(cnpj,''),'.',''),'-',''),'/',''),' ','') "
        "WHERE cnpj IS NOT NULL AND (cnpj_digits IS NULL OR cnpj_digits = '')",
        "CREATE INDEX IF NOT EXISTS idx_clients_name_trgm  ON clients USING GIN (name  gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_clients_code_trgm  ON clients USING GIN (code  gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_clients_cnpj_trgm  ON clients USING GIN (cnpj  gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_clients_cnpj_digits_trgm ON clients USING GIN (cnpj_digits gin_trgm_ops)",

        # ── Índices de performance para requisições ───────────────────────────
        # PostgreSQL NÃO cria índice automático em colunas FK — apenas em PK/UNIQUE.
        # Estas colunas aparecem em filtros e ORDER BY em quase todos os endpoints.
        "CREATE INDEX IF NOT EXISTS idx_requisitions_status          ON requisitions (status)",
        "CREATE INDEX IF NOT EXISTS idx_requisitions_vendor_id       ON requisitions (vendor_id)",
        "CREATE INDEX IF NOT EXISTS idx_requisitions_client_id       ON requisitions (client_id)",
        "CREATE INDEX IF NOT EXISTS idx_requisitions_created_at      ON requisitions (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_requisitions_prod_destination ON requisitions (production_destination)",
        "CREATE INDEX IF NOT EXISTS idx_req_items_requisition_id     ON requisition_items (requisition_id)",
        "CREATE INDEX IF NOT EXISTS idx_status_history_requisition_id ON status_history (requisition_id)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread    ON notifications (user_id, read)",
    ]
    for stmt in stmts:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate()
    seed_admin()
    seed_production_machines()
    try:
        normalize_existing_user_written_data()
    except Exception:
        pass
    asyncio.create_task(backup_scheduler())
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


@app.middleware("http")
async def monitor_runtime(request: Request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        record_exception()
        raise

    duration_ms = (perf_counter() - started_at) * 1000.0
    record_request(duration_ms, response.status_code)
    return response

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(operators.router)
app.include_router(clients.router)
app.include_router(products.router)
app.include_router(production_machines.router)
app.include_router(requisitions.router)
app.include_router(notifications.router)
app.include_router(system_settings.router)
app.include_router(feedbacks.router)
app.include_router(backup.router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "service": "Ferragens Pinheiro API"}
