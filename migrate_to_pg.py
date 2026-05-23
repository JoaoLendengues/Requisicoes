"""
migrate_to_pg.py — Migração de dados: SQLite → PostgreSQL
==========================================================
Copia os dados do banco SQLite local para o PostgreSQL dedicado.

Tabelas JÁ importadas no PostgreSQL (ignoradas por este script):
  users, products, clients

Tabelas migradas por este script:
  production_machines, requisitions, requisition_items,
  canvas_data, status_history, notifications, feedbacks

Como usar:

  Primeira execução (ou após limpar dados parciais):
    .venv\\Scripts\\python.exe migrate_to_pg.py --clean

  Re-executar sem apagar o que já existe:
    .venv\\Scripts\\python.exe migrate_to_pg.py

IMPORTANTE: inicie o servidor ao menos uma vez antes de rodar,
para que create_all() e _migrate() criem/atualizem as tabelas no PG.
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

ROOT        = Path(__file__).parent
SQLITE_PATH = ROOT / "requisicoes.db"

_FALLBACK_DB_URL = "postgresql://tipinheiro:Pinheiro123@10.1.1.151:5432/requisicoes"

# Ordem respeitando dependências de FK
TABLES_ORDER = [
    "production_machines",   # sem FK para tabelas migradas
    "requisitions",          # vendor_id → users | client_id → clients
    "requisition_items",     # requisition_id → requisitions
    "canvas_data",           # requisition_id → requisitions
    "status_history",        # requisition_id → requisitions | changed_by_id → users
    "notifications",         # user_id → users
    "feedbacks",             # user_id → users | read_by_id → users (nullable)
]

# Colunas FK que precisam de remapeamento de ID SQLite → PG
# Formato: {tabela: {coluna: "user" | "client"}}
FK_REMAPS: dict[str, dict[str, str]] = {
    "requisitions":   {"vendor_id": "user",  "client_id": "client"},
    "status_history": {"changed_by_id": "user"},
    "notifications":  {"user_id": "user"},
    "feedbacks":      {"user_id": "user",    "read_by_id": "user"},
}


# ── Configuração / conexão ────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
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
    print("  AVISO: nenhum .env encontrado — usando conexão embutida.")
    return {"DATABASE_URL": _FALLBACK_DB_URL, "DATABASE_TYPE": "postgresql"}


def parse_pg_url(url: str) -> dict:
    m = re.match(
        r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@"
        r"(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<dbname>.+)",
        url,
    )
    if not m:
        raise ValueError(f"URL inválida: {url!r}")
    return dict(
        user=m["user"], password=m["password"],
        host=m["host"], port=int(m["port"] or 5432),
        dbname=m["dbname"],
    )


# ── Schema helpers ────────────────────────────────────────────────────────────

def pg_table_exists(pg_cur, table: str) -> bool:
    pg_cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s)", (table,)
    )
    return pg_cur.fetchone()[0]


def get_pg_columns(pg_cur, table: str) -> set[str]:
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s", (table,)
    )
    return {row[0] for row in pg_cur.fetchall()}


def _bool_cols(sq_cur: sqlite3.Cursor, table: str) -> set[str]:
    sq_cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in sq_cur.fetchall() if "BOOL" in (row[2] or "").upper()}


def _date_cols(cols: list[str]) -> set[str]:
    keywords = ("_at", "_date", "date_", "emission", "finalized", "changed")
    return {c for c in cols if any(kw in c.lower() for kw in keywords)}


# ── Mapeamento de IDs ─────────────────────────────────────────────────────────

def _best_match_col(pg_cur, table: str, candidates: list[str]) -> str | None:
    """Retorna o primeiro candidato que existe como coluna na tabela do PG."""
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s", (table,)
    )
    existing = {r[0].lower() for r in pg_cur.fetchall()}
    for col in candidates:
        if col.lower() in existing:
            return col
    return None


def build_id_maps(
    sq_conn: sqlite3.Connection, pg_conn
) -> tuple[dict[int, int], dict[int, int]]:
    """
    Constrói SQLite-ID → PostgreSQL-ID para users e clients.
    Detecta automaticamente qual coluna usar para o match.
    Users  : tenta email → code → name (nessa ordem)
    Clients: tenta code  → name
    """
    sq = sq_conn.cursor()
    pg = pg_conn.cursor()

    # ── Users ──────────────────────────────────────────────────────────────
    user_key = _best_match_col(pg, "users", ["email", "code", "name"])
    if user_key is None:
        print("  AVISO: nenhuma coluna de match encontrada em 'users' — user_map vazio.")
        user_map: dict[int, int] = {}
    else:
        print(f"  Usuários  : usando coluna '{user_key}' para match")
        sq.execute(f"SELECT id, {user_key} FROM users")
        sq_users = {str(v).lower(): sq_id for sq_id, v in sq.fetchall() if v}
        pg.execute(f"SELECT id, {user_key} FROM users")
        pg_users = {str(v).lower(): pg_id for pg_id, v in pg.fetchall() if v}
        user_map = {
            sq_id: pg_users[key]
            for key, sq_id in sq_users.items()
            if key in pg_users
        }
        unmapped = len(sq_users) - len(user_map)
        print(f"             {len(user_map)} mapeados, {unmapped} não encontrados no PG")

    # ── Clients ────────────────────────────────────────────────────────────
    client_key = _best_match_col(pg, "clients", ["code", "name"])
    if client_key is None:
        print("  AVISO: nenhuma coluna de match encontrada em 'clients' — client_map vazio.")
        client_map: dict[int, int] = {}
    else:
        print(f"  Clientes  : usando coluna '{client_key}' para match")
        sq.execute(f"SELECT id, {client_key} FROM clients")
        sq_clients = {str(v): sq_id for sq_id, v in sq.fetchall() if v}
        pg.execute(f"SELECT id, {client_key} FROM clients")
        pg_clients = {str(v): pg_id for pg_id, v in pg.fetchall() if v}
        client_map = {
            sq_id: pg_clients[key]
            for key, sq_id in sq_clients.items()
            if key in pg_clients
        }
        unmapped = len(sq_clients) - len(client_map)
        print(f"             {len(client_map)} mapeados, {unmapped} não encontrados no PG")

    return user_map, client_map


# ── Conversão de tipos ────────────────────────────────────────────────────────

def _parse_dt(value):
    if value is None or isinstance(value, (datetime, date)):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return value  # deixa o PG tentar coagir


def _adapt_row(
    raw: tuple,
    cols: list[str],
    bool_cols: set[str],
    dt_cols: set[str],
    user_map: dict[int, int],
    client_map: dict[int, int],
    table: str,
) -> tuple | None:
    """
    Converte tipos e remapeia FKs.
    Retorna None se FK obrigatória não puder ser resolvida.
    """
    remaps = FK_REMAPS.get(table, {})
    result = []
    for val, col in zip(raw, cols):
        if col in remaps:
            if val is None:          # FK nullable (ex: read_by_id)
                result.append(None)
                continue
            id_map = user_map if remaps[col] == "user" else client_map
            new_id = id_map.get(int(val))
            if new_id is None:
                return None          # FK obrigatória sem match → descarta linha
            result.append(new_id)
        elif col in bool_cols:
            result.append(bool(val) if val is not None else None)
        elif col in dt_cols:
            result.append(_parse_dt(val))
        else:
            result.append(val)
    return tuple(result)


# ── Limpeza (--clean) ─────────────────────────────────────────────────────────

def clean_tables(pg_conn) -> None:
    """Trunca todas as tabelas migradas em ordem inversa, reiniciando sequences."""
    pg_cur = pg_conn.cursor()
    existing = [t for t in reversed(TABLES_ORDER) if pg_table_exists(pg_cur, t)]
    if not existing:
        print("  Nenhuma tabela encontrada para limpar.")
        return
    pg_cur.execute(
        "TRUNCATE TABLE " + ", ".join(existing) + " RESTART IDENTITY CASCADE"
    )
    pg_conn.commit()
    for t in existing:
        print(f"  {t}: limpa.")


# ── Cópia de tabela ───────────────────────────────────────────────────────────

def copy_table(
    sq_conn: sqlite3.Connection,
    pg_conn,
    table: str,
    user_map: dict[int, int],
    client_map: dict[int, int],
) -> None:
    pg_cur = pg_conn.cursor()

    # Tabela existe no PG?
    if not pg_table_exists(pg_cur, table):
        print(f"  {table}: tabela não existe no PostgreSQL.")
        print( "           → Inicie o servidor uma vez para criar as tabelas e tente novamente.")
        return

    # Já populada?
    pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
    if pg_cur.fetchone()[0] > 0:
        print(f"  {table}: já tem dados no PostgreSQL — pulando. (use --clean para refazer)")
        return

    # Lê SQLite
    sq_cur = sq_conn.cursor()
    sq_cur.execute(f"SELECT * FROM {table}")
    sq_cols = [d[0] for d in sq_cur.description]
    rows    = sq_cur.fetchall()

    if not rows:
        print(f"  {table}: vazia no SQLite.")
        return

    # Usa apenas colunas presentes nos dois bancos
    pg_cols  = get_pg_columns(pg_cur, table)
    use_cols = [c for c in sq_cols if c in pg_cols]
    use_idx  = [i for i, c in enumerate(sq_cols) if c in pg_cols]
    missing  = [c for c in sq_cols if c not in pg_cols]
    if missing:
        print(f"  {table}: colunas ausentes no PG (ignoradas): {missing}")
        print( "           → Inicie o servidor para aplicar as migrações e refaça com --clean.")

    b_cols = _bool_cols(sq_cur, table)
    d_cols = _date_cols(use_cols)

    # Adapta e remapeia IDs
    adapted:     list[tuple] = []
    fk_skipped:  int         = 0
    for r in rows:
        row = _adapt_row(
            tuple(r[i] for i in use_idx),
            use_cols, b_cols, d_cols,
            user_map, client_map, table,
        )
        if row is None:
            fk_skipped += 1
        else:
            adapted.append(row)

    if not adapted:
        print(f"  {table}: todas as {fk_skipped} linha(s) descartadas "
              f"(usuário/cliente não encontrado no PG).")
        return

    col_str      = ", ".join(f'"{c}"' for c in use_cols)
    placeholders = ", ".join(["%s"] * len(use_cols))
    sql_single   = f'INSERT INTO {table} ({col_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # Bulk insert; se falhar, row-by-row
    inserted   = 0
    err_skipped = 0
    try:
        execute_values(
            pg_cur,
            f'INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT DO NOTHING',
            adapted, page_size=500,
        )
        pg_conn.commit()
        inserted = len(adapted)
    except Exception:
        pg_conn.rollback()
        for row in adapted:
            try:
                pg_cur.execute(sql_single, row)
                pg_conn.commit()
                inserted += 1
            except Exception:
                pg_conn.rollback()
                err_skipped += 1

    # Reseta sequence
    if "id" in use_cols:
        try:
            pg_cur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))", (table,)
            )
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()

    # Relatório
    parts = [f"{inserted} migrada(s)"]
    if fk_skipped:   parts.append(f"{fk_skipped} sem usuário/cliente no PG")
    if err_skipped:  parts.append(f"{err_skipped} outro erro")
    print(f"  {table}: {', '.join(parts)}. OK")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    clean_mode = "--clean" in sys.argv

    print()
    print("=" * 58)
    print("  Migração de dados: SQLite → PostgreSQL")
    if clean_mode:
        print("  MODO: --clean  (dados parciais serão apagados e refeitos)")
    print("=" * 58)

    if not SQLITE_PATH.exists():
        sys.exit(f"\nERRO: SQLite não encontrado em:\n  {SQLITE_PATH}")

    env    = load_env()
    params = parse_pg_url(env["DATABASE_URL"])

    print(f"\n  PostgreSQL : {params['host']}:{params['port']}/{params['dbname']}")
    print(f"  SQLite     : {SQLITE_PATH}\n")

    try:
        pg_conn = psycopg2.connect(**params)
    except Exception as exc:
        sys.exit(f"ERRO ao conectar no PostgreSQL: {exc}")

    sq_conn = sqlite3.connect(str(SQLITE_PATH))

    if clean_mode:
        print("Limpando dados parciais:")
        clean_tables(pg_conn)
        print()

    print("Mapeando IDs (users por e-mail, clients por código):")
    user_map, client_map = build_id_maps(sq_conn, pg_conn)
    print()

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
            copy_table(sq_conn, pg_conn, table, user_map, client_map)
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
