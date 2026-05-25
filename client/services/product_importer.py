"""
Importacao de produtos a partir de arquivo .ods / .xlsx.
Colunas esperadas: Codigo e Produto.
"""
from ..api import client as api
from .client_importer import ImportResult, _is_blank, _normalize, read_spreadsheet


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


def _map_columns(labels) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in labels:
        if _is_blank(col):
            continue
        label = str(col).strip()
        internal = _COL_MAP.get(_normalize(label))
        if internal and internal not in mapping:
            mapping[internal] = label
    return mapping


def _rebuild_header_from_row(df, row_index: int):
    header_values: list[str] = []
    for idx, value in enumerate(df.iloc[row_index].tolist()):
        text = "" if _is_blank(value) else str(value).strip()
        header_values.append(text or f"COL_{idx + 1}")

    rebuilt = df.iloc[row_index + 1:].copy().reset_index(drop=True)
    rebuilt.columns = header_values
    return rebuilt


def _prepare_dataframe(df):
    col_map = _map_columns(df.columns)
    if "code" in col_map and "name" in col_map:
        return df, col_map

    scan_limit = min(len(df), 5)
    for row_index in range(scan_limit):
        candidate_map = _map_columns(df.iloc[row_index].tolist())
        if "code" in candidate_map and "name" in candidate_map:
            rebuilt = _rebuild_header_from_row(df, row_index)
            return rebuilt, _map_columns(rebuilt.columns)

    return df, col_map


def import_products(path: str, on_progress=None) -> ImportResult:
    result = ImportResult()

    if on_progress:
        on_progress(0, 3, "Lendo planilha...")

    df = read_spreadsheet(path)
    df = df.dropna(how="all")

    if len(df) == 0:
        result.errors.append("Planilha vazia ou sem dados.")
        return result

    if on_progress:
        on_progress(1, 3, "Validando registros...")

    df, col_map = _prepare_dataframe(df)
    if "code" not in col_map or "name" not in col_map:
        found_columns = [str(col).strip() for col in list(df.columns) if not _is_blank(col)]
        found_text = ", ".join(found_columns[:8]) if found_columns else "nenhuma coluna legível"
        result.errors.append(
            "Colunas obrigatórias não encontradas. "
            "Esperado: 'Código' e 'Produto'. "
            f"Encontrado: {found_text}."
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
        on_progress(2, 3, f"Enviando {len(items)} produtos ao servidor...")

    try:
        server_result = api.bulk_import_products(items)
        result.created = server_result.get("created", 0)
        result.updated = server_result.get("updated", 0)
        result.skipped += server_result.get("skipped", 0)
        result.errors.extend(server_result.get("errors", []))
    except api.APIError as exc:
        if exc.status_code == 403:
            result.errors.append(
                "Seu usuário não tem permissão para importar produtos."
            )
        elif exc.status_code == 404:
            result.errors.append(
                "O servidor atual não reconheceu a rota de produtos. "
                "Reinicie o servidor e tente novamente."
            )
        elif exc.status_code == 401:
            result.errors.append(
                "Sua sessão expirou. Faça login novamente e repita a importação."
            )
        else:
            result.errors.append(str(exc))
        return result
    except Exception as exc:
        result.errors.append(f"Erro na comunicação com o servidor: {exc}")
        return result

    if on_progress:
        on_progress(3, 3, "Concluido!")

    return result
