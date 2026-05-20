"""
Migração SQLite → PostgreSQL
Execute na raiz do projeto:
    .venv/Scripts/python migrar.py
"""
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = "requisicoes.db"
PG_DSN = "postgresql://tipinheiro:Pinheiro123@10.1.1.151:5432/requisicoes"

# Ordem respeitando foreign keys
TABLES = [
    "users",
    "clients",
    "products",
    "requisitions",
    "requisition_items",
    "canvas_data",
    "status_history",
    "notifications",
]


def migrate():
    print("Conectando ao SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    print("Conectando ao PostgreSQL...")
    pg_conn = psycopg2.connect(PG_DSN)
    pg_cursor = pg_conn.cursor()

    # Desabilita checagem de FK durante a migração
    pg_cursor.execute("SET session_replication_role = 'replica';")

    try:
        for table in TABLES:
            _migrate_table(sqlite_conn, pg_cursor, table)

        # Reabilita FK
        pg_cursor.execute("SET session_replication_role = 'origin';")
        pg_conn.commit()
        print("\nMigração concluída com sucesso!")

    except Exception as exc:
        pg_conn.rollback()
        print(f"\nErro durante a migração: {exc}")
        raise

    finally:
        sqlite_conn.close()
        pg_conn.close()


def _migrate_table(sqlite_conn, pg_cursor, table: str):
    cur = sqlite_conn.cursor()

    # Verifica se a tabela existe no SQLite
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cur.fetchone():
        print(f"  {table}: não existe no SQLite, pulando")
        return

    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()

    if not rows:
        print(f"  {table}: vazia, pulando")
        return

    columns = [desc[0] for desc in cur.description]
    values = [tuple(row[col] for col in columns) for row in rows]

    # Limpa tabela no PostgreSQL antes de inserir
    pg_cursor.execute(f'TRUNCATE TABLE "{table}" CASCADE')

    cols_str = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))

    execute_values(
        pg_cursor,
        f'INSERT INTO "{table}" ({cols_str}) VALUES %s',
        values,
        template=f"({placeholders})",
    )

    # Reinicia a sequência do ID para o valor máximo atual
    if "id" in columns:
        pg_cursor.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM "{table}"), 1)
            )
        """)

    print(f"  {table}: {len(rows)} registros migrados")


if __name__ == "__main__":
    migrate()
