"""
Importação de usuários da planilha usuarios.ods para o PostgreSQL.
Execute na raiz do projeto NO SERVIDOR:
    .venv\Scripts\python importar_usuarios.py

Colunas esperadas: Código, Nome, Contato, Setor, Acesso, Status

Senha inicial de todos os usuários: Pinheiro123
(must_change_password = TRUE — o sistema pedirá troca no primeiro login)
"""

import re
import unicodedata

import bcrypt
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Configurações ─────────────────────────────────────────────────────────────
PG_DSN      = "postgresql://tipinheiro:Pinheiro123@localhost:5432/requisicoes"
ODS_PATH    = r"Z:\REQUISIÇÕES (VENDAS)\usuarios.ods"
SENHA_PADRAO = "Pinheiro123"   # Será hasheada com bcrypt + casefold

# ── Mapeamento de colunas ─────────────────────────────────────────────────────
COL_MAP = {
    "codigo": "code", "cod": "code", "code": "code",
    "nome":   "name", "name": "name",
    "contato": "whatsapp", "telefone": "whatsapp", "celular": "whatsapp", "whatsapp": "whatsapp",
    "setor":  "sector",   "sector": "sector",
    "acesso": "role",     "perfil": "role",  "role": "role", "cargo": "role",
    "status": "status",   "situacao": "status", "ativo": "status",
}

# ── Mapeamento de papéis ──────────────────────────────────────────────────────
ROLE_MAP = {
    "admin":          "admin",
    "administrador":  "admin",
    "gerente":        "gerente",
    "vendedor":       "vendedor",
    "producao":       "producao",
    "producção":      "producao",
    "industria":      "industria",
    "indústria":      "industria",
    "entrega":        "industria",   # legado → industria
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    n = unicodedata.normalize("NFKD", str(text).strip().lower())
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", n)


def _is_blank(v) -> bool:
    return v is None or str(v).strip().lower() in {"", "nan", "none"}


def _hash(password: str) -> str:
    """Mesmo algoritmo usado pelo sistema: strip + casefold + bcrypt."""
    normalized = password.strip().casefold()
    return bcrypt.hashpw(normalized.encode(), bcrypt.gensalt()).decode()


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


def _resolve_role(value: str) -> str:
    return ROLE_MAP.get(_normalize(value), "vendedor")


def _resolve_status(value: str) -> bool:
    v = _normalize(str(value))
    return v not in {"inativo", "inative", "nao", "0", "false", "inactive", "desativado"}


def _make_email(code: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", ".", _normalize(name))
    slug = re.sub(r"\.+", ".", slug).strip(".")
    return f"{slug or code}@pinheiroferragens.com.br"


# ── Importação ────────────────────────────────────────────────────────────────
def importar_usuarios():
    print(f"Lendo planilha: {ODS_PATH}")
    ext = ODS_PATH.rsplit(".", 1)[-1].lower()
    df = pd.read_excel(ODS_PATH, engine="odf" if ext == "ods" else None, dtype=str)
    df = df.dropna(how="all")

    col_map = _map_columns(df.columns)

    # Tenta encontrar cabeçalho nas primeiras 5 linhas
    if "code" not in col_map or "name" not in col_map:
        for i in range(min(5, len(df))):
            candidate = _map_columns(df.iloc[i].tolist())
            if "code" in candidate and "name" in candidate:
                df.columns = [str(v).strip() if not _is_blank(v) else f"COL_{j}"
                              for j, v in enumerate(df.iloc[i].tolist())]
                df = df.iloc[i + 1:].reset_index(drop=True)
                col_map = _map_columns(df.columns)
                break

    if "code" not in col_map or "name" not in col_map:
        print(f"❌ Colunas obrigatórias não encontradas.")
        print(f"   Colunas disponíveis: {list(df.columns[:10])}")
        return

    print(f"   Colunas detectadas: {col_map}")
    print(f"   Gerando hash da senha padrão '{SENHA_PADRAO}'... (pode demorar alguns segundos)")
    senha_hash = _hash(SENHA_PADRAO)

    usuarios = []
    skipped  = 0

    for _, row in df.iterrows():
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()

        if _is_blank(code) or _is_blank(name):
            skipped += 1
            continue

        whatsapp = None
        if col_map.get("whatsapp"):
            val = str(row.get(col_map["whatsapp"], "")).strip()
            whatsapp = val if not _is_blank(val) else None

        sector = None
        if col_map.get("sector"):
            val = str(row.get(col_map["sector"], "")).strip()
            sector = val if not _is_blank(val) else None

        role = "vendedor"
        if col_map.get("role"):
            role = _resolve_role(str(row.get(col_map["role"], "")))

        is_active = True
        if col_map.get("status"):
            is_active = _resolve_status(str(row.get(col_map["status"], "ativo")))

        email = _make_email(code, name)

        usuarios.append((code, name, email, senha_hash, role, whatsapp, sector, is_active))

    if not usuarios:
        print("❌ Nenhum usuário válido encontrado na planilha.")
        return

    print(f"\nConectando ao PostgreSQL...")
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor()
        execute_values(
            cur,
            """
            INSERT INTO users
                (code, name, email, hashed_password, role, whatsapp, sector,
                 is_active, must_change_password, created_at, updated_at)
            VALUES %s
            ON CONFLICT (code) DO UPDATE
                SET name                 = EXCLUDED.name,
                    role                 = EXCLUDED.role,
                    whatsapp             = COALESCE(EXCLUDED.whatsapp, users.whatsapp),
                    sector               = COALESCE(EXCLUDED.sector,   users.sector),
                    is_active            = EXCLUDED.is_active,
                    updated_at           = NOW()
            """,
            usuarios,
            template="(%s, %s, %s, %s, %s::role, %s, %s, %s, TRUE, NOW(), NOW())",
        )
        conn.commit()
        print(f"✅ {len(usuarios)} usuários importados  |  {skipped} linhas ignoradas")
        print(f"\nSenha inicial de todos: '{SENHA_PADRAO}'")
        print("O sistema pedirá a troca de senha no primeiro login de cada usuário.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    importar_usuarios()
