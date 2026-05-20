"""
Importação direta das planilhas para o PostgreSQL.
Execute na raiz do projeto:
    .venv\Scripts\python importar_planilhas.py

Planilhas lidas:
    Z:\REQUISIÇÕES (VENDAS)\relacao_cadastros.ods  → tabela clients
    Z:\REQUISIÇÕES (VENDAS)\produtos.ods           → tabela products
"""

import re
import unicodedata

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Configurações ─────────────────────────────────────────────────────────────
PG_DSN = "postgresql://tipinheiro:Pinheiro123@localhost:5432/requisicoes"

CLIENTES_PATH = r"Z:\REQUISIÇÕES (VENDAS)\relacao_cadastros.ods"
PRODUTOS_PATH = r"Z:\REQUISIÇÕES (VENDAS)\produtos.ods"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text).strip().lower())
    norm = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", norm)


def _is_blank(value) -> bool:
    return value is None or str(value).strip().lower() in {"", "nan", "none"}


def _read_ods(path: str) -> pd.DataFrame:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "ods":
        return pd.read_excel(path, engine="odf", dtype=str)
    return pd.read_excel(path, dtype=str)


def _map_columns(labels, col_map: dict) -> dict:
    result = {}
    for col in labels:
        if _is_blank(col):
            continue
        key = _normalize(str(col))
        internal = col_map.get(key)
        if internal and internal not in result:
            result[internal] = str(col).strip()
    return result


def _scan_header(df: pd.DataFrame, col_map: dict):
    """Tenta encontrar o cabeçalho real nas primeiras 5 linhas."""
    mapping = _map_columns(df.columns, col_map)
    if mapping:
        return df, mapping

    for i in range(min(5, len(df))):
        candidate = _map_columns(df.iloc[i].tolist(), col_map)
        if candidate:
            new_df = df.iloc[i + 1:].copy().reset_index(drop=True)
            new_df.columns = [str(v).strip() if not _is_blank(v) else f"COL_{j}"
                              for j, v in enumerate(df.iloc[i].tolist())]
            return new_df, _map_columns(new_df.columns, col_map)

    return df, mapping


# ── Importar clientes ─────────────────────────────────────────────────────────
CLIENTES_COL_MAP = {
    "codigo": "code", "cod": "code", "code": "code",
    "nome": "name", "name": "name", "razaosocial": "name",
    "cpfcnpj": "cnpj", "cnpj": "cnpj", "cpf": "cnpj",
}


def importar_clientes(conn):
    print(f"\n📋 Lendo clientes: {CLIENTES_PATH}")
    df = _read_ods(CLIENTES_PATH).dropna(how="all")
    df, col_map = _scan_header(df, CLIENTES_COL_MAP)

    if "code" not in col_map or "name" not in col_map:
        print(f"   ❌ Colunas não encontradas. Colunas disponíveis: {list(df.columns[:8])}")
        return

    rows = []
    skipped = 0
    for _, row in df.iterrows():
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()
        if _is_blank(code) or _is_blank(name):
            skipped += 1
            continue
        cnpj = None
        if col_map.get("cnpj"):
            val = str(row.get(col_map["cnpj"], "")).strip()
            cnpj = val if not _is_blank(val) else None
        rows.append((code, name, cnpj))

    if not rows:
        print("   ❌ Nenhum registro válido encontrado.")
        return

    cur = conn.cursor()
    execute_values(
        cur,
        """
        INSERT INTO clients (code, name, cnpj, is_active, created_at, updated_at)
        VALUES %s
        ON CONFLICT (code) DO UPDATE
            SET name       = EXCLUDED.name,
                cnpj       = COALESCE(EXCLUDED.cnpj, clients.cnpj),
                updated_at = NOW()
        """,
        [(code, name, cnpj, True, "NOW()", "NOW()") for code, name, cnpj in rows],
        template="(%s, %s, %s, %s, NOW(), NOW())",
    )
    conn.commit()
    print(f"   ✅ {len(rows)} clientes importados  |  {skipped} ignorados")


# ── Importar produtos ─────────────────────────────────────────────────────────
PRODUTOS_COL_MAP = {
    "codigo": "code", "cod": "code", "code": "code",
    "codigoproduto": "code", "codigodoproduto": "code", "codproduto": "code",
    "produto": "name", "nome": "name", "name": "name",
    "nomedoproduto": "name", "descricao": "name",
    "descricaoproduto": "name", "descricaodoproduto": "name",
    "descricaoitem": "name", "item": "name",
}


def importar_produtos(conn):
    print(f"\n📦 Lendo produtos: {PRODUTOS_PATH}")
    df = _read_ods(PRODUTOS_PATH).dropna(how="all")
    df, col_map = _scan_header(df, PRODUTOS_COL_MAP)

    if "code" not in col_map or "name" not in col_map:
        print(f"   ❌ Colunas não encontradas. Colunas disponíveis: {list(df.columns[:8])}")
        return

    rows = []
    skipped = 0
    for _, row in df.iterrows():
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()
        if _is_blank(code) or _is_blank(name):
            skipped += 1
            continue
        rows.append((code, name))

    if not rows:
        print("   ❌ Nenhum produto válido encontrado.")
        return

    cur = conn.cursor()
    execute_values(
        cur,
        """
        INSERT INTO products (code, name, is_active, created_at, updated_at)
        VALUES %s
        ON CONFLICT (code) DO UPDATE
            SET name       = EXCLUDED.name,
                updated_at = NOW()
        """,
        rows,
        template="(%s, %s, TRUE, NOW(), NOW())",
    )
    conn.commit()
    print(f"   ✅ {len(rows)} produtos importados  |  {skipped} ignorados")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Conectando ao PostgreSQL...")
    conn = psycopg2.connect(PG_DSN)
    try:
        importar_clientes(conn)
        importar_produtos(conn)
        print("\nImportação concluída!")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Erro: {e}")
        raise
    finally:
        conn.close()
