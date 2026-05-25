"""
Importacao de usuarios a partir de arquivo .ods / .xlsx.
Colunas esperadas: Codigo, Nome, Contato e Setor.
"""

from ..api import client as api
from .client_importer import ImportResult, _is_blank, _normalize, read_spreadsheet


_COL_MAP = {
    "codigo": "code",
    "cod": "code",
    "code": "code",
    "nome": "name",
    "name": "name",
    "usuario": "name",
    "nomeusuario": "name",
    "contato": "contact",
    "telefone": "contact",
    "celular": "contact",
    "whatsapp": "contact",
    "fone": "contact",
    "setor": "sector",
    "departamento": "sector",
    "area": "sector",
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


def import_users(path: str, on_progress=None) -> ImportResult:
    result = ImportResult()

    if on_progress:
        on_progress(0, 3, "Lendo planilha...")

    df = read_spreadsheet(path)
    df = df.dropna(how="all")

    if len(df) == 0:
        result.errors.append("Planilha vazia ou sem dados.")
        return result

    if on_progress:
        on_progress(1, 3, "Validando usuarios...")

    df, col_map = _prepare_dataframe(df)
    if "code" not in col_map or "name" not in col_map:
        found_columns = [str(col).strip() for col in list(df.columns) if not _is_blank(col)]
        found_text = ", ".join(found_columns[:8]) if found_columns else "nenhuma coluna legível"
        result.errors.append(
            "Colunas obrigatórias não encontradas. "
            "Esperado: 'Código' e 'Nome'. "
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

        item = {"code": code, "name": name}

        if col_map.get("contact"):
            contact = str(row.get(col_map["contact"], "")).strip()
            if contact and contact != "nan":
                item["contact"] = contact

        if col_map.get("sector"):
            sector = str(row.get(col_map["sector"], "")).strip()
            if sector and sector != "nan":
                item["sector"] = sector

        items.append(item)

    if not items:
        result.errors.append("Nenhum usuário válido encontrado na planilha.")
        return result

    if on_progress:
        on_progress(2, 3, f"Enviando {len(items)} usuarios ao servidor...")

    try:
        server_result = api.bulk_import_users(items)
        result.created = server_result.get("created", 0)
        result.updated = server_result.get("updated", 0)
        result.skipped += server_result.get("skipped", 0)
        result.errors.extend(server_result.get("errors", []))
    except api.APIError as exc:
        if exc.status_code == 405:
            result.errors.append(
                "O servidor atual ainda não reconheceu a importação em lote de usuários. "
                "Reinicie o servidor e tente novamente."
            )
        elif exc.status_code == 404:
            result.errors.append(
                "A rota de importação de usuários não foi encontrada no servidor atual. "
                "Reinicie o servidor e tente novamente."
            )
        elif exc.status_code == 403:
            result.errors.append(
                "Seu usuário não tem permissão para importar usuários."
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
