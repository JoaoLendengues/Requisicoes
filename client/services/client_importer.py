"""
Importação de clientes a partir de arquivo .ods.
Colunas esperadas: Código, Nome, CPF/CNPJ
"""
import os
import re
from dataclasses import dataclass, field

import pandas as pd

from ..api import client as api


# ── Resultado da importação ───────────────────────────────────────────────────
@dataclass
class ImportResult:
    created:  int = 0
    updated:  int = 0
    skipped:  int = 0
    errors:   list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped

    def summary(self) -> str:
        lines = [
            f"✅  Criados:    {self.created}",
            f"🔄  Atualizados: {self.updated}",
            f"⏭️  Ignorados:  {self.skipped}",
        ]
        if self.errors:
            lines.append(f"❌  Erros:     {len(self.errors)}")
            for e in self.errors[:5]:   # mostra no máximo 5
                lines.append(f"   • {e}")
            if len(self.errors) > 5:
                lines.append(f"   ... e mais {len(self.errors)-5} erro(s)")
        return "\n".join(lines)


# ── Normalização de colunas ───────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Remove acentos, espaços e converte para lowercase."""
    replacements = {
        "á":"a","à":"a","â":"a","ã":"a","ä":"a",
        "é":"e","è":"e","ê":"e","ë":"e",
        "í":"i","ì":"i","î":"i","ï":"i",
        "ó":"o","ò":"o","ô":"o","õ":"o","ö":"o",
        "ú":"u","ù":"u","û":"u","ü":"u",
        "ç":"c","ñ":"n",
    }
    result = text.lower().strip()
    for k, v in replacements.items():
        result = result.replace(k, v)
    return re.sub(r"[^a-z0-9/]", "", result)


# Mapeamento de variações de nome de coluna → campo interno
_COL_MAP = {
    "codigo":   "code",
    "cod":      "code",
    "code":     "code",
    "nome":     "name",
    "name":     "name",
    "razaosocial": "name",
    "cpfcnpj":  "cnpj",
    "cpf/cnpj": "cnpj",
    "cnpj":     "cnpj",
    "cpf":      "cnpj",
}


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Retorna {campo_interno: nome_coluna_df} com base nos cabeçalhos."""
    mapping = {}
    for col in df.columns:
        key = _normalize(col)
        internal = _COL_MAP.get(key)
        if internal and internal not in mapping:
            mapping[internal] = col
    return mapping


# ── Leitura do arquivo ────────────────────────────────────────────────────────
def read_ods(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ods":
        return pd.read_excel(path, engine="odf", dtype=str)
    elif ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, dtype=str)
    else:
        raise ValueError(f"Formato não suportado: {ext}")


# ── Importação principal ──────────────────────────────────────────────────────
def import_clients(path: str,
                   on_progress=None) -> ImportResult:
    """
    Lê o arquivo ODS/Excel e sincroniza clientes via API.
    on_progress(current, total, message) — callback opcional para progresso.
    """
    result = ImportResult()

    # 1. Ler arquivo
    df = read_ods(path)
    df = df.dropna(how="all")           # remove linhas totalmente vazias
    total = len(df)

    if total == 0:
        result.errors.append("Planilha vazia ou sem dados.")
        return result

    # 2. Mapear colunas
    col_map = _map_columns(df)
    if "code" not in col_map or "name" not in col_map:
        result.errors.append(
            "Colunas obrigatórias não encontradas. "
            "Esperado: 'Código' e 'Nome'. "
            f"Encontrado: {list(df.columns)}"
        )
        return result

    # 3. Buscar clientes existentes (índice por código)
    try:
        existing = {c["code"]: c for c in api.list_clients()}
    except Exception as e:
        result.errors.append(f"Erro ao buscar clientes existentes: {e}")
        return result

    # 4. Processar cada linha
    for i, (_, row) in enumerate(df.iterrows()):
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()
        cnpj = str(row.get(col_map.get("cnpj", ""), "")).strip() if col_map.get("cnpj") else ""

        if not code or not name or code == "nan" or name == "nan":
            result.skipped += 1
            continue

        # Limpa CNPJ — mantém só dígitos e pontuação relevante
        cnpj = cnpj if cnpj and cnpj != "nan" else None

        payload = {"code": code, "name": name}
        if cnpj:
            payload["cnpj"] = cnpj

        if on_progress:
            on_progress(i + 1, total, f"Processando: {name[:40]}")

        if code in existing:
            # Atualizar
            try:
                api.update_client(existing[code]["id"], {"name": name, "cnpj": cnpj})
                result.updated += 1
            except Exception as e:
                result.errors.append(f"[{code}] {name}: {e}")
        else:
            # Criar
            try:
                api.create_client(payload)
                result.created += 1
            except api.APIError as e:
                if e.status_code == 400:
                    # CNPJ duplicado — tenta sem CNPJ
                    try:
                        api.create_client({"code": code, "name": name})
                        result.created += 1
                    except Exception as e2:
                        result.errors.append(f"[{code}] {name}: {e2}")
                else:
                    result.errors.append(f"[{code}] {name}: {e.detail}")
            except Exception as e:
                result.errors.append(f"[{code}] {name}: {e}")

    return result
