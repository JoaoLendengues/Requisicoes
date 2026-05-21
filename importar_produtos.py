"""
Importação de produtos da planilha produtos.ods para o PostgreSQL.
Execute na raiz do projeto NO SERVIDOR:
    .venv\Scripts\python importar_produtos.py

Colunas esperadas: Código, Nome
"""

import re
import unicodedata

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Configurações ─────────────────────────────────────────────────────────────
PG_DSN   = "postgresql://tipinheiro:Pinheiro123@localhost:5432/requisicoes"
ODS_PATH = r"Z:\REQUISIÇÕES (VENDAS)\produtos.ods"

# ── Mapeamento de colunas ─────────────────────────────────────────────────────
COL_MAP = {
    "codigo":           "code", "cod":  "code", "code": "code",
    "codigoproduto":    "code", "codproduto": "code",
    "codigodoproduto":  "code",
    "nome":             "name", "name": "name",
    "produto":          "name", "descricao": "name",
    "nomedoproduto":    "name", "descricaoproduto": "name",
    "descricaodoproduto": "name", "item": "name",
}


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


def _map_columns(labels) -> dict:
    result = {}
    for col in labels:
        if _is_blank(col):
            continue
        key = _normalize(str(col))
        internal = COL_MAP.get(key)
        if internal and internal not in result:
            result[internal] = str(col).strip()
    return result


def _scan_header(df: pd.DataFrame):
    """Tenta encontrar o cabeçalho real nas primeiras 5 linhas."""
    col_map = _map_columns(df.columns)
    if "code" in col_map and "name" in col_map:
        return df, col_map

    for i in range(min(5, len(df))):
        candidate = _map_columns(df.iloc[i].tolist())
        if "code" in candidate and "name" in candidate:
            new_df = df.iloc[i + 1:].copy().reset_index(drop=True)
            new_df.columns = [
                str(v).strip() if not _is_blank(v) else f"COL_{j}"
                for j, v in enumerate(df.iloc[i].tolist())
            ]
            return new_df, _map_columns(new_df.columns)

    return df, col_map


# ── Importação ────────────────────────────────────────────────────────────────
def importar_produtos():
    print(f"Lendo planilha: {ODS_PATH}")
    df = _read_ods(ODS_PATH).dropna(how="all")
    df, col_map = _scan_header(df)

    if "code" not in col_map or "name" not in col_map:
        print("❌ Colunas obrigatórias não encontradas.")
        print(f"   Colunas disponíveis: {list(df.columns[:10])}")
        return

    print(f"   Colunas detectadas: {col_map}")

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
        print("❌ Nenhum produto válido encontrado na planilha.")
        return

    print(f"\n   {len(rows)} produtos prontos para importar  |  {skipped} linhas ignoradas")
    print("Conectando ao PostgreSQL...")

    conn = psycopg2.connect(PG_DSN)
    try:
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
        print(f"✅ {len(rows)} produtos importados com sucesso  |  {skipped} linhas ignoradas")
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    importar_produtos()
