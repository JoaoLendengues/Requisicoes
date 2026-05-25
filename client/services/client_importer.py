"""
Importação de clientes a partir de arquivo .ods / .xlsx.
Colunas esperadas: Código, Nome, CPF/CNPJ

Estratégia de performance:
  - Toda a planilha é lida e validada localmente com pandas (rápido).
  - Os registros válidos são enviados ao servidor numa única chamada HTTP
    (POST /clients/bulk-import). O servidor resolve tudo numa transação.
  - Resultado: segundos em vez de minutos, independente do tamanho da planilha.
"""
import os
import re
import unicodedata
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
            f"Criados:      {self.created}",
            f"Atualizados:  {self.updated}",
            f"Ignorados:   {self.skipped}",
        ]
        if self.errors:
            lines.append(f"Erros:        {len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"   • {e}")
            if len(self.errors) > 5:
                lines.append(f"   ... e mais {len(self.errors) - 5} erro(s)")
        return "\n".join(lines)


# ── Normalização de colunas ───────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Remove acentos, espaços e converte para lowercase."""
    normalized = unicodedata.normalize("NFKD", str(text).strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", normalized)


def _is_blank(value) -> bool:
    """Retorna True se o valor é vazio, NaN ou None."""
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.lower() in {"nan", "none"}


_COL_MAP = {
    "codigo":      "code",
    "cod":         "code",
    "code":        "code",
    "nome":        "name",
    "name":        "name",
    "razaosocial": "name",
    "cpfcnpj":     "cnpj",
    "cnpj":        "cnpj",
    "cpf":         "cnpj",
}


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Retorna {campo_interno: nome_coluna_df}."""
    mapping: dict[str, str] = {}
    for col in df.columns:
        key = _normalize(str(col))
        internal = _COL_MAP.get(key)
        if internal and internal not in mapping:
            mapping[internal] = col
    return mapping


# ── Leitura do arquivo ────────────────────────────────────────────────────────
def read_spreadsheet(path: str) -> pd.DataFrame:
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
def import_clients(path: str, on_progress=None) -> ImportResult:
    """
    Lê o arquivo, valida as linhas localmente e envia tudo ao servidor
    em uma única requisição HTTP.

    on_progress(current, total, message) — callback para barra de progresso.
    """
    result = ImportResult()

    # ── 1. Ler arquivo ────────────────────────────────────────────────────────
    if on_progress:
        on_progress(0, 3, "Lendo planilha...")

    df = read_spreadsheet(path)
    df = df.dropna(how="all")
    total_rows = len(df)

    if total_rows == 0:
        result.errors.append("Planilha vazia ou sem dados.")
        return result

    # ── 2. Mapear colunas ─────────────────────────────────────────────────────
    col_map = _map_columns(df)
    if "code" not in col_map or "name" not in col_map:
        result.errors.append(
            "Colunas obrigatórias não encontradas. "
            "Esperado: 'Código' e 'Nome'. "
            f"Encontrado: {list(df.columns)}"
        )
        return result

    # ── 3. Montar lista de itens válidos ──────────────────────────────────────
    if on_progress:
        on_progress(1, 3, f"Validando {total_rows} registros...")

    items: list[dict] = []
    for _, row in df.iterrows():
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()

        if not code or not name or code == "nan" or name == "nan":
            result.skipped += 1
            continue

        item: dict = {"code": code, "name": name}

        if col_map.get("cnpj"):
            cnpj = str(row.get(col_map["cnpj"], "")).strip()
            if cnpj and cnpj != "nan":
                item["cnpj"] = cnpj

        items.append(item)

    if not items:
        result.errors.append("Nenhum registro válido encontrado na planilha.")
        return result

    # ── 4. Enviar em lote ao servidor (uma única chamada HTTP) ────────────────
    if on_progress:
        on_progress(2, 3, f"Enviando {len(items)} clientes ao servidor...")

    try:
        server_result = api.bulk_import_clients(items)
        result.created = server_result.get("created", 0)
        result.updated = server_result.get("updated", 0)
        result.skipped += server_result.get("skipped", 0)
        result.errors.extend(server_result.get("errors", []))
    except Exception as e:
        result.errors.append(f"Erro na comunicação com o servidor: {e}")
        return result

    if on_progress:
        on_progress(3, 3, "Concluído!")

    return result
