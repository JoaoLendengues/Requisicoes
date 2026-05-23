"""
migrate_to_pg.py — Migração de dados: SQLite → PostgreSQL
==========================================================
Copia os dados do banco SQLite local para o PostgreSQL dedicado.

Tabelas JÁ importadas no PostgreSQL (ignoradas por este script):
  users, products, clients

Tabelas migradas por este script:
  production_machines, requisitions, requisition_items,
  canvas_data, status_history, notifications, feedbacks

Pré-requisito: inicie o servidor ao menos uma vez com o .env apontando
para o PostgreSQL para que o create_all() crie as tabelas vazias lá.

Uso:
  .venv\\Scripts\\python.exe migrate_to_pg.py
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    sys.exit("ERRO: psycopg2 não instalado. Ative o venv e tente novamente.")


# ── Configuração ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
SQLITE_PATH = ROOT / "requisicoes.db"
ENV_PATH = ROOT / ".env"

# Ordem respeitando dependências de chave estrangeira
TABLES_ORDER = [
    "production_machines",   # sem FK para tabelas migradas
    "requisitions",          # FK → users, clients (já no PG)
    "requisition_items",     # FK → requisitions
    "canvas_data",           # FK → requisitions
    "status_history",        # FK → requisitions, users
    "notifications",         # FK → users
    "feedbacks",             # FK → users
]


# ── Utilitários ───────────────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def parse_pg_url(url: str) -> dict:
    m = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@"
        r"(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<dbname>.+)",
        url,
    )
    if not m:
        raise ValueError(f"URL de banco inválida: {url!r}")
    return dict(
        user=m["user"],
        password=m["password"],
        host=m["host"],
        port=int(m["port"] or 5432),
        dbname=m["dbname"],
    )


def _bool_cols(sq_cur: sqlite3.Cursor, table: str) -> set[str]:
    """Retorna nomes das colunas declaradas como BOOLEAN no SQLite."""
    sq_cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in sq_cur.fetchall() if "BOOL" in (row[2] or "").upper()}


def _date_cols(cols: list[str]) -> set[str]:
    """Heurística: colunas de data/hora pelo nome."""
    keywords = ("_at", "_date", "date_", "emission", "finalized", "changed")
    return {c for c in cols if any(kw in c.lower() for kw in keywords)}


def _parse_dt(value):
    """Converte string de data/hora do SQLite para objeto Python datetime."""
    if value is None or isinstance(value, (datetime, date)):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return value  # devolve string — PostgreSQL tentará coagir


def _adapt_row(
    row: tuple,
    cols: list[str],
    bool_cols: set[str],
    dt_cols: set[str],
) -> tuple:
    result = []
    for val, col in zip(row, cols):
        if col in bool_cols:
            result.append(bool(val) if val is not None else None)
        elif col in dt_cols:
            result.append(_parse_dt(val))
        else:
            result.append(val)
    return tuple(result)


# ── Cópia de tabela ───────────────────────────────────────────────────────────

def copy_table(sq_conn: sqlite3.Connection, pg_conn, table: str) -> None:
    pg_cur = pg_conn.cursor()

    # Verifica se a tabela existe no PostgreSQL
    pg_cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s)",
        (table,),
    )
    if not pg_cur.fetchone()[0]:
        print(f"  {table}: tabela não existe no PostgreSQL — inicie o servidor"
              " primeiro para criar as tabelas (create_all).")
        return

    # Pula se já tiver dados
    pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
    pg_count = pg_cur.fetchone()[0]
    if pg_count > 0:
        print(f"  {table}: já tem {pg_count} linha(s) no PostgreSQL — pulando.")
        return

    # Lê do SQLite
    sq_cur = sq_conn.cursor()
    sq_cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in sq_cur.description]
    rows = sq_cur.fetchall()

    if not rows:
        print(f"  {table}: vazia no SQLite — nada a migrar.")
        return

    # Converte tipos problemáticos (bool, datetime)
    b_cols = _bool_cols(sq_cur, table)
    d_cols = _date_cols(cols)
    adapted = [_adapt_row(r, cols, b_cols, d_cols) for r in rows]

    col_str = ", ".join(f'"{c}"' for c in cols)
    execute_values(
        pg_cur,
        f'INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT DO NOTHING',
        adapted,
        page_size=500,
    )
    pg_conn.commit()

    # Reseta a sequence do id para evitar conflito em novos inserts
    if "id" in cols:
        pg_cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM " + table + "), 1))",
            (table,),
        )
        pg_conn.commit()

    print(f"  {table}: {len(rows)} linha(s) migrada(s). OK")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("=" * 58)
    print("  Migração de dados: SQLite → PostgreSQL")
    print("=" * 58)

    # Validações iniciais
    if not SQLITE_PATH.exists():
        sys.exit(f"\nERRO: arquivo SQLite não encontrado em:\n  {SQLITE_PATH}")
    if not ENV_PATH.exists():
        sys.exit(f"\nERRO: arquivo .env não encontrado em:\n  {ENV_PATH}")

    env = load_env()
    if env.get("DATABASE_TYPE") != "postgresql":
        print("\nAVISO: DATABASE_TYPE no .env não é 'postgresql'. Continuando...")

    params = parse_pg_url(env["DATABASE_URL"])
    print(f"\n  PostgreSQL : {params['host']}:{params['port']}/{params['dbname']}")
    print(f"  SQLite     : {SQLITE_PATH}")
    print()

    # Conecta
    try:
        pg_conn = psycopg2.connect(**params)
    except Exception as exc:
        sys.exit(f"ERRO ao conectar no PostgreSQL: {exc}")

    sq_conn = sqlite3.connect(str(SQLITE_PATH))

    # Tabelas disponíveis no SQLite
    sq_cur = sq_conn.cursor()
    sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    sq_tables = {r[0] for r in sq_cur.fetchall()}

    # Migra cada tabela na ordem correta
    print("Migrando tabelas:")
    errors: list[str] = []
    for table in TABLES_ORDER:
        if table not in sq_tables:
            print(f"  {table}: não existe no SQLite — pulando.")
            continue
        try:
            copy_table(sq_conn, pg_conn, table)
        except Exception as exc:
            pg_conn.rollback()
            msg = f"  ERRO em '{table}': {exc}"
            print(msg)
            errors.append(msg)

    sq_conn.close()
    pg_conn.close()

    print()
    if errors:
        print(f"Concluído com {len(errors)} erro(s):")
        for e in errors:
            print(e)
    else:
        print("Migração concluída sem erros!")
    print()


if __name__ == "__main__":
    main()
