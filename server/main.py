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
        "ALTER TABLE requisitions ADD COLUMN signature_png_b64 TEXT",
        "ALTER TABLE requisitions ADD COLUMN production_destination TEXT",
        "ALTER TABLE requisitions ADD COLUMN production_machine TEXT",
        "ALTER TABLE requisitions ADD COLUMN cancel_reason TEXT",
        "ALTER TABLE requisitions ADD COLUMN delivered_at TIMESTAMP",
        "ALTER TABLE requisitions ADD COLUMN delivery_deadline_changed_at TIMESTAMP",
        "ALTER TABLE requisitions ADD COLUMN delivery_deadline_change_reason TEXT",
        "ALTER TABLE operators ADD COLUMN role TEXT DEFAULT 'operador'",
        "ALTER TABLE requisition_items ADD COLUMN product_code TEXT",
        "ALTER TABLE requisition_items ADD COLUMN product_name TEXT",
        "UPDATE users SET must_change_password = FALSE WHERE must_change_password IS NULL",
        "UPDATE users SET role = 'industria' WHERE role = 'entrega'",
        "UPDATE operators SET role = 'operador' WHERE role IS NULL OR TRIM(role) = ''",
        "UPDATE requisitions SET status = 'em_andamento' WHERE UPPER(status) IN "
        "('RASCUNHO','EMITIDA','RECEBIDA_PRODUCAO','PRONTA','EM_ROTA','AGUARDANDO_RETIRADA','CONCLUIDA')",
        "UPDATE requisitions SET status = 'em_producao' WHERE UPPER(status) = 'EM_FABRICACAO'",
        "UPDATE requisitions SET status = 'aguardando_recebimento' "
        "WHERE status = 'em_producao' AND finalized_at IS NULL",
        "UPDATE requisitions SET status = 'aguardando_na_fila' "
        "WHERE status = 'em_producao' AND production_machine IS NULL AND finalized_at IS NOT NULL",

        # ── Índices de busca rápida de clientes (pg_trgm) ─────────────────────
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS idx_clients_name_trgm  ON clients USING GIN (name  gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_clients_code_trgm  ON clients USING GIN (code  gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_clients_cnpj_trgm  ON clients USING GIN (cnpj  gin_trgm_ops)",

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

        # ── Feedbacks: novas colunas (category/status) + mensagem ate 1000 ──
        "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'sugestao'",
        "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS status   TEXT NOT NULL DEFAULT 'nova'",
        "ALTER TABLE feedbacks ALTER COLUMN message TYPE VARCHAR(1000)",
        # Backfill: feedbacks ja lidos pelo admin viram "resolvida"
        "UPDATE feedbacks SET status = 'resolvida' WHERE read_at IS NOT NULL AND status = 'nova'",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_user_id    ON feedbacks (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_status     ON feedbacks (status)",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_category   ON feedbacks (category)",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_created_at ON feedbacks (created_at DESC)",

        # ── Feedbacks: campo de publicacao (default TRUE) ──────────────────
        "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE",
        "CREATE INDEX IF NOT EXISTS idx_feedbacks_is_public ON feedbacks (is_public)",

        # ── Feedbacks: tabela de reacoes (like / dislike) ──────────────────
        "CREATE TABLE IF NOT EXISTS feedback_reactions ("
        " feedback_id INTEGER NOT NULL,"
        " user_id     INTEGER NOT NULL,"
        " reaction    TEXT    NOT NULL CHECK (reaction IN ('like', 'dislike')),"
        " created_at  TIMESTAMP NOT NULL DEFAULT NOW(),"
        " PRIMARY KEY (feedback_id, user_id),"
        " CONSTRAINT fk_feedback_reactions_feedback FOREIGN KEY (feedback_id)"
        "     REFERENCES feedbacks(id) ON DELETE CASCADE,"
        " CONSTRAINT fk_feedback_reactions_user FOREIGN KEY (user_id)"
        "     REFERENCES users(id) ON DELETE CASCADE"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_feedback_reactions_feedback ON feedback_reactions (feedback_id)",

        # ── Feedbacks: leituras por usuario (contador 'nao lido') ───────────
        "CREATE TABLE IF NOT EXISTS feedback_reads ("
        " feedback_id INTEGER NOT NULL,"
        " user_id     INTEGER NOT NULL,"
        " read_at     TIMESTAMP NOT NULL DEFAULT NOW(),"
        " PRIMARY KEY (feedback_id, user_id),"
        " CONSTRAINT fk_feedback_reads_feedback FOREIGN KEY (feedback_id)"
        "     REFERENCES feedbacks(id) ON DELETE CASCADE,"
        " CONSTRAINT fk_feedback_reads_user FOREIGN KEY (user_id)"
        "     REFERENCES users(id) ON DELETE CASCADE"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_feedback_reads_user ON feedback_reads (user_id)",
    ]
    for stmt in stmts:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            pass


def _migrate_ped_unique():
    """Garante UNIQUE em requisitions.ped_number.

    Idempotente e ciente de duplicatas: se já existir índice/constraint único
    cobrindo ped_number, não faz nada; se houver PEDs duplicados pré-existentes,
    NÃO cria o índice (evita falha) e loga um aviso claro para limpeza manual;
    caso contrário, cria o índice único.
    """
    try:
        from sqlalchemy import inspect as _inspect

        insp = _inspect(engine)

        # Já protegido por índice único?
        for ix in insp.get_indexes("requisitions"):
            if ix.get("unique") and ix.get("column_names") == ["ped_number"]:
                return
        # ...ou por unique constraint?
        try:
            for uc in insp.get_unique_constraints("requisitions"):
                if uc.get("column_names") == ["ped_number"]:
                    return
        except Exception:
            pass

        # Há duplicatas? Se sim, não cria (constraint falharia) e avisa.
        with engine.connect() as conn:
            dups = conn.execute(text(
                "SELECT ped_number FROM requisitions "
                "GROUP BY ped_number HAVING COUNT(*) > 1"
            )).fetchall()
        if dups:
            sample = [str(d[0]) for d in dups[:20]]
            print(
                f"[MIGRATION][PED] {len(dups)} PED(s) duplicado(s) no banco — "
                f"indice unico NAO criado. Limpe as duplicatas e reinicie. "
                f"Exemplos: {sample}"
            )
            return

        with engine.begin() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_requisitions_ped_number_unique "
                "ON requisitions (ped_number)"
            ))
        print("[MIGRATION][PED] indice unico garantido em requisitions.ped_number")
    except Exception as exc:
        print(f"[MIGRATION][PED] falhou ao aplicar UNIQUE em ped_number: {exc}")


def _migrate_production_machine_operators():
    """
    Migra production_machine_operators de user_id para operator_id.
    Detecta automaticamente a estrutura atual e corrige se necessário.
    Funciona tanto em SQLite quanto em PostgreSQL.
    """
    try:
        from sqlalchemy import inspect as sa_inspect
        from .models.production_machine import production_machine_operators as _pmo

        inspector = sa_inspect(engine)
        if "production_machine_operators" not in inspector.get_table_names():
            return  # create_all criará com a estrutura correta

        cols = {c["name"] for c in inspector.get_columns("production_machine_operators")}
        if "user_id" in cols and "operator_id" not in cols:
            # Tabela antiga — dropa e recria com operator_id
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE production_machine_operators"))
            with engine.begin() as conn:
                _pmo.create(conn)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_production_machine_operators()
    _migrate()
    _migrate_ped_unique()
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
