"""
Mapeamento código de usuário → subpasta no servidor de PDFs.

Chave  : código do usuário (string, exatamente como está no banco)
Valor  : nome da pasta em VENDEDORES\<pasta>
"""

_VENDOR_FOLDER_MAP: dict[str, str] = {
    # Vendedores
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
    # Gerentes (usados como fallback quando a requisição não tem vendor_code)
    "95":  "EDUARDO",
    "2":   "LUIZ ALBERTO",
    "49":  "JHONATAN",
    "265": "RAYFFER",
}

# Roles que redirecionam para a pasta do vendedor da requisição
_MANAGER_ROLES = {"gerente", "admin"}


def vendor_subfolder(
    user_code: str,
    user_name: str,
    user_role: str = "",
    req_vendor_code: str = "",
    req_vendor_name: str = "",
) -> str:
    """Retorna o nome da subpasta de destino do PDF.

    Regras:
    - Vendedor  → pasta mapeada pelo próprio código.
    - Gerente / Admin → pasta mapeada pelo código do vendedor da requisição;
                        se não encontrar, usa o nome do vendedor da requisição.
    - Fallback  → primeiro nome limpo do usuário logado.
    """
    import re

    role = str(user_role or "").strip().lower()

    if role in _MANAGER_ROLES:
        # Usa o vendedor dono da requisição
        code = str(req_vendor_code or "").strip()
        if code and code in _VENDOR_FOLDER_MAP:
            return _VENDOR_FOLDER_MAP[code]
        # Fallback: primeiro nome do vendedor da requisição
        first = str(req_vendor_name or "").strip().split()[0] if req_vendor_name else ""
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", first).upper()
        if clean:
            return clean

    # Vendedor / outros: usa o próprio código
    code = str(user_code or "").strip()
    if code in _VENDOR_FOLDER_MAP:
        return _VENDOR_FOLDER_MAP[code]

    # Último fallback: primeiro nome do usuário logado
    first = str(user_name or "").strip().split()[0] if user_name else ""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", first).upper()
    return clean or "VENDEDOR"
