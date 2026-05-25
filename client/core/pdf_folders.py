"""
Mapeamento código de usuário → subpasta no servidor de PDFs.

Chave  : código do usuário (string, exatamente como está no banco)
Valor  : nome da pasta em VENDEDORES\<pasta>
"""

_VENDOR_FOLDER_MAP: dict[str, str] = {
    "412": "ADLER",
    "293": "EDIVAN",
    "16":  "FAUSTO",
    "17":  "FREDERICO",
    "325": "IGOR",
    "481": "ISLANE",
    "364": "JOHNATA",
    "64":  "JHALLISON",
    "223": "LUCAS",
    "103": "LUIZ",
    "22":  "RODOLFO",
    "23":  "RODRIGO",
    "25":  "RONNY",
}


def vendor_subfolder(user_code: str, user_name: str) -> str:
    """Retorna o nome da subpasta do vendedor.

    Prioridade:
    1. Mapeamento explícito pelo código do usuário.
    2. Fallback: primeiro nome do usuário em maiúsculas (sem caracteres inválidos).
    """
    import re

    code = str(user_code or "").strip()
    if code in _VENDOR_FOLDER_MAP:
        return _VENDOR_FOLDER_MAP[code]

    # Fallback: primeiro nome limpo
    first = str(user_name or "").strip().split()[0] if user_name else ""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", first).upper()
    return clean or "VENDEDOR"
