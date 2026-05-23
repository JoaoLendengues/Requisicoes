"""
migrate_to_pg.py — Migração de dados: SQLite → PostgreSQL
==========================================================
Copia os dados do banco SQLite local para o PostgreSQL dedicado.

Tabelas JÁ importadas no PostgreSQL (ignoradas por este script):
  users, products, clients

Tabelas migradas por este script:
  production_machines, requisitions, requisition_items,
  canvas_data, status_history, notifications, feedbacks

IMPORTANTE: inicie o servidor ao menos uma vez antes de rodar este script,
para que o create_all() e o _migrate() criem e atualizem as tabelas no PG.

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

# Conexão de fallback usada quando não há .env nem .env.example
_FALLBACK_DB_URL = "postgresql://tipinheiro:Pinheiro123@10.1.1.151:5432/requisicoes"

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


# ── Utilitários de configuração ───────────────────────────────────────────────

def load_env() -> dict[str, str]:
    """Carrega variáveis de .env, .env.example ou usa fallback embutido."""
    for candidate in (".env", ".env.example"):
        path = ROOT / candidate
        if path.exists():
            env: dict[str, str] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
            return env
    print("  AVISO: nenhum .env encontrado — usando conexão embutida no script.")
    return {"DATABASE_URL": _FALLBACK_DB_URL, "DATABASE_TYPE": "postgresql"}


def parse_pg_url(url: str) -> dict:
    m = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@"
        r"(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<dbname>.+)",
        url,
    )
    if not m:
        raise ValueError(f"URL de banco inválida: {url!r}")
    return dict(
        user=m["user"], password=m["password"],
        host=m["host"], port=int(m["port"] or 5432),
        dbname=m["dbname"],
    )


# ── Utilitários de schema ─────────────────────────────────────────────────────

def pg_table_exists(pg_cur, table: str) -> bool:
    pg_cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s)",
        (table,),
    )
    return pg_cur.fetchone()[0]


def get_pg_columns(pg_cur, table: str) -> set[str]:
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    return {row[0] for row in pg_cur.fetchall()}


def _bool_cols(sq_cur: sqlite3.Cursor, table: str) -> set[str]:
    sq_cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in sq_cur.fetchall() if "BOOL" in (row[2] or "").upper()}


def _date_cols(cols: list[str]) -> set[str]:
    keywords = ("_at", "_date", "date_", "emission", "finalized", "changed")
    return {c for c in cols if any(kw in c.lower() for kw in keywords)}


# ── Conversão de tipos SQLite → Python ───────────────────────────────────────

def _parse_dt(value):
    if value is None or isinstance(value, (datetime, date)):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return value  # devolve como está — PostgreSQL tentará coagir


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

    # 1. Tabela existe no PostgreSQL?
    if not pg_table_exists(pg_cur, table):
        print(f"  {table}: tabela não existe no PostgreSQL.")
        print( "           → Inicie o servidor uma vez para criar as tabelas e tente novamente.")
        return

    # 2. Já tem dados? Pula.
    pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
    pg_count = pg_cur.fetchone()[0]
    if pg_count > 0:
        print(f"  {table}: já tem {pg_count} linha(s) no PostgreSQL — pulando.")
        return

    # 3. Lê todos os dados do SQLite
    sq_cur = sq_conn.cursor()
    sq_cur.execute(f"SELECT * FROM {table}")
    sq_cols = [d[0] for d in sq_cur.description]
    rows = sq_cur.fetchall()

    if not rows:
        print(f"  {table}: vazia no SQLite — nada a migrar.")
        return

    # 4. Usa somente as colunas que existem nos DOIS bancos
    #    (resolve colunas adicionadas por _migrate que ainda não estão no PG)
    pg_cols = get_pg_columns(pg_cur, table)
    use_cols = [c for c in sq_cols if c in pg_cols]
    use_idx  = [i for i, c in enumerate(sq_cols) if c in pg_cols]
    missing  = [c for c in sq_cols if c not in pg_cols]

    if missing:
        print(f"  {table}: colunas ausentes no PG, serão ignoradas: {missing}")
        print( "           → Inicie o servidor para aplicar as migrações e re-execute o script.")

    # 5. Adapta tipos (bool, datetime)
    b_cols = _bool_cols(sq_cur, table)
    d_cols = _date_cols(use_cols)
    adapted = [
        _adapt_row(tuple(r[i] for i in use_idx), use_cols, b_cols, d_cols)
        for r in rows
    ]

    col_str      = ", ".join(f'"{c}"' for c in use_cols)
    placeholders = ", ".join(["%s"] * len(use_cols))
    sql_single   = f'INSERT INTO {table} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # 6. Tenta bulk insert; se falhar por FK, cai em row-by-row tolerante
    inserted = 0
    skipped  = 0
    try:
        execute_values(
            pg_cur,
            f'INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT DO NOTHING',
            adapted,
            page_size=500,
        )
        pg_conn.commit()
        inserted = len(adapted)

    except Exception:
        pg_conn.rollback()
        # Insere linha a linha, pulando as que violam FK ou outra restrição
        for row in adapted:
            try:
                pg_cur.execute(sql_single, row)
                pg_conn.commit()
                inserted += 1
            except Exception:
                pg_conn.rollback()
                skipped += 1

    # 7. Reseta a sequence do id
    if "id" in use_cols:
        try:
            pg_cur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))",
                (table,),
            )
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()

    # 8. Relatório
    if skipped:
        print(f"  {table}: {inserted} migrada(s), {skipped} pulada(s) (FK ausente no PG). OK")
    else:
        print(f"  {table}: {inserted} linha(s) migrada(s). OK")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("=" * 58)
    print("  Migração de dados: SQLite → PostgreSQL")
    print("=" * 58)

    if not SQLITE_PATH.exists():
        sys.exit(f"\nERRO: arquivo SQLite não encontrado em:\n  {SQLITE_PATH}")

    env    = load_env()
    params = parse_pg_url(env["DATABASE_URL"])

    print(f"\n  PostgreSQL : {params['host']}:{params['port']}/{params['dbname']}")
    print(f"  SQLite     : {SQLITE_PATH}\n")

    try:
        pg_conn = psycopg2.connect(**params)
    except Exception as exc:
        sys.exit(f"ERRO ao conectar no PostgreSQL: {exc}")

    sq_conn = sqlite3.connect(str(SQLITE_PATH))

    sq_cur = sq_conn.cursor()
    sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    sq_tables = {r[0] for r in sq_cur.fetchall()}

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
            msg = f"  ERRO inesperado em '{table}': {exc}"
            print(msg)
            errors.append(msg)

    sq_conn.close()
    pg_conn.close()

    print()
    if errors:
        print(f"Concluído com {len(errors)} erro(s) inesperado(s):")
        for e in errors:
            print(e)
    else:
        print("Migração concluída!")
    print()


if __name__ == "__main__":
    main()
