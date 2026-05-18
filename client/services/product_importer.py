"""
Importação de produtos a partir de arquivo .ods / .xlsx.
Colunas esperadas: Código e Nome/Descrição.
"""
import re
import unicodedata

from ..api import client as api
from .client_importer import ImportResult, read_spreadsheet


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text).strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", normalized)


_COL_MAP = {
    "codigo": "code",
    "cod": "code",
    "code": "code",
    "codigoproduto": "code",
    "codigodoproduto": "code",
    "codproduto": "code",
    "produto": "name",
    "nome": "name",
    "nomedoproduto": "name",
    "descricao": "name",
    "descricaoproduto": "name",
    "descricaodoproduto": "name",
    "descricaoitem": "name",
    "item": "name",
    "name": "name",
}


def _map_columns(df) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in df.columns:
        internal = _COL_MAP.get(_normalize(col))
        if internal and internal not in mapping:
            mapping[internal] = col
    return mapping


def import_products(path: str, on_progress=None) -> ImportResult:
    result = ImportResult()

    if on_progress:
        on_progress(0, 3, "Lendo planilha...")

    df = read_spreadsheet(path)
    df = df.dropna(how="all")
    total_rows = len(df)

    if total_rows == 0:
        result.errors.append("Planilha vazia ou sem dados.")
        return result

    if on_progress:
        on_progress(1, 3, "Validando registros...")

    col_map = _map_columns(df)
    if "code" not in col_map or "name" not in col_map:
        result.errors.append(
            "Colunas obrigatórias não encontradas. "
            "Esperado: 'Código' e 'Nome/Descrição'."
        )
        return result

    items: list[dict] = []
    for _, row in df.iterrows():
        code = str(row[col_map["code"]]).strip()
        name = str(row[col_map["name"]]).strip()

        if not code or not name or code == "nan" or name == "nan":
            result.skipped += 1
            continue

        items.append({"code": code, "name": name})

    if not items:
        result.errors.append("Nenhum produto válido encontrado na planilha.")
        return result

    if on_progress:
        on_progress(2, 3, "Enviando ao servidor...")

    try:
        server_result = api.bulk_import_products(items)
        result.created = server_result.get("created", 0)
        result.updated = server_result.get("updated", 0)
        result.skipped += server_result.get("skipped", 0)
        result.errors.extend(server_result.get("errors", []))
    except Exception as exc:
        result.errors.append(f"Erro na comunicação com o servidor: {exc}")
        return result

    if on_progress:
        on_progress(3, 3, "Concluído!")

    return result
