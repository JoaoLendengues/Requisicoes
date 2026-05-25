"""
Testes unitários para client/core/pdf_folders.py

Cobre:
- Todos os 13 vendedores mapeados (código → subpasta)
- Os 4 gerentes mapeados
- Gerente/admin → redireciona para pasta do vendedor da requisição
- Fallback por nome quando código não está no mapa
- Caracteres inválidos em nomes são removidos
- Valores vazios/None retornam "VENDEDOR"
- vendor_subfolder() integrada com vendor_pdf_folder() de main_window

Não requer Qt — todas as funções testadas são puras.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from client.core.pdf_folders import vendor_subfolder, _VENDOR_FOLDER_MAP, _MANAGER_ROLES


# ── Helpers ───────────────────────────────────────────────────────────────────

def subfolder(user_code="", user_name="", role="vendedor",
              req_vendor_code="", req_vendor_name=""):
    return vendor_subfolder(user_code, user_name, role, req_vendor_code, req_vendor_name)


# ── Testes: vendedores mapeados ───────────────────────────────────────────────

class TestVendedoresMapeados:
    """Todos os 13 vendedores devem resolver para a pasta correta pelo código."""

    @pytest.mark.parametrize("code,expected", [
        ("412", "ADLER"),
        ("293", "EDIVAN"),
        ("16",  "FAUSTO"),
        ("17",  "FREDERICO"),
        ("325", "IGOR"),
        ("481", "ISLANE"),
        ("364", "JOHNATA"),
        ("64",  "JHALLISON"),
        ("223", "LUCAS"),
        ("103", "LUIZ"),
        ("22",  "RODOLFO"),
        ("23",  "RODRIGO"),
        ("25",  "RONNY"),
    ])
    def test_vendedor_codigo(self, code, expected):
        assert subfolder(user_code=code, user_name="qualquer") == expected

    def test_todos_os_vendedores_no_mapa(self):
        """Garante que nenhum vendedor foi removido acidentalmente do mapa."""
        vendedores = ["412","293","16","17","325","481","364","64","223","103","22","23","25"]
        for code in vendedores:
            assert code in _VENDOR_FOLDER_MAP, f"Código {code} ausente do mapa"

    def test_total_de_entradas_no_mapa(self):
        """13 vendedores + 4 gerentes = 17 entradas."""
        assert len(_VENDOR_FOLDER_MAP) == 17


# ── Testes: gerentes mapeados ─────────────────────────────────────────────────

class TestGerentesMapeados:
    """Os 4 gerentes devem estar no mapa (usado como fallback)."""

    @pytest.mark.parametrize("code,expected", [
        ("95",  "EDUARDO"),
        ("2",   "LUIZ ALBERTO"),
        ("49",  "JHONATAN"),
        ("265", "RAYFFER"),
    ])
    def test_gerente_no_mapa(self, code, expected):
        assert _VENDOR_FOLDER_MAP[code] == expected


# ── Testes: lógica de redirecionamento do gerente ────────────────────────────

class TestGerenteRedirecionamento:
    """Gerente/admin deve ir para a pasta do VENDEDOR da requisição."""

    def test_gerente_req_vendedor_mapeado(self):
        """Gerente salvando req do ADLER → pasta ADLER."""
        assert subfolder(
            user_code="95", user_name="EDUARDO MARRA", role="gerente",
            req_vendor_code="412", req_vendor_name="ADLER EDUARDO"
        ) == "ADLER"

    def test_admin_req_vendedor_mapeado(self):
        """Admin salvando req do LUCAS → pasta LUCAS."""
        assert subfolder(
            user_code="1", user_name="Administrador", role="admin",
            req_vendor_code="223", req_vendor_name="LUCAS GABRIEL"
        ) == "LUCAS"

    @pytest.mark.parametrize("gerente_code,gerente_name", [
        ("95",  "EDUARDO MARRA"),
        ("2",   "LUIZ ALBERTO"),
        ("49",  "JHONATAN SALAZAR"),
        ("265", "RAYFFER ROBERTO"),
    ])
    @pytest.mark.parametrize("vendor_code,expected_folder", [
        ("412", "ADLER"),
        ("293", "EDIVAN"),
        ("16",  "FAUSTO"),
        ("17",  "FREDERICO"),
        ("325", "IGOR"),
        ("481", "ISLANE"),
        ("364", "JOHNATA"),
        ("64",  "JHALLISON"),
        ("223", "LUCAS"),
        ("103", "LUIZ"),
        ("22",  "RODOLFO"),
        ("23",  "RODRIGO"),
        ("25",  "RONNY"),
    ])
    def test_todos_gerentes_todos_vendedores(self, gerente_code, gerente_name,
                                            vendor_code, expected_folder):
        """Qualquer gerente + qualquer vendedor mapeado → pasta certa."""
        assert subfolder(
            user_code=gerente_code, user_name=gerente_name, role="gerente",
            req_vendor_code=vendor_code
        ) == expected_folder

    def test_gerente_vendor_code_nao_mapeado_usa_nome(self):
        """Gerente com vendor_code desconhecido → primeiro nome do vendedor."""
        assert subfolder(
            user_code="95", user_name="EDUARDO MARRA", role="gerente",
            req_vendor_code="999", req_vendor_name="CARLOS HENRIQUE"
        ) == "CARLOS"

    def test_gerente_sem_vendor_code_usa_nome(self):
        """Gerente sem vendor_code → primeiro nome do vendedor da req."""
        assert subfolder(
            user_code="95", user_name="EDUARDO MARRA", role="gerente",
            req_vendor_code="", req_vendor_name="PATRICIA SOUZA"
        ) == "PATRICIA"

    def test_gerente_sem_nenhuma_info_vendor_cai_no_fallback(self):
        """Gerente sem info de vendedor → primeiro nome do próprio gerente."""
        assert subfolder(
            user_code="95", user_name="EDUARDO MARRA", role="gerente",
            req_vendor_code="", req_vendor_name=""
        ) == "EDUARDO"

    def test_role_case_insensitive(self):
        """Role em maiúsculo/misto deve funcionar igual."""
        assert subfolder(
            user_code="95", user_name="EDUARDO", role="GERENTE",
            req_vendor_code="412"
        ) == "ADLER"
        assert subfolder(
            user_code="1", user_name="Admin", role="Admin",
            req_vendor_code="223"
        ) == "LUCAS"


# ── Testes: roles que NÃO redirecionam ───────────────────────────────────────

class TestRolesNaoGerente:
    """Vendedor, producao, industria, entrega → usa o próprio código."""

    @pytest.mark.parametrize("role", ["vendedor", "producao", "industria", "entrega", ""])
    def test_role_nao_gerente_usa_proprio_codigo(self, role):
        assert subfolder(
            user_code="412", user_name="ADLER EDUARDO", role=role,
            req_vendor_code="223"  # deve ser ignorado
        ) == "ADLER"

    def test_manager_roles_set(self):
        """Apenas 'gerente' e 'admin' estão em _MANAGER_ROLES."""
        assert _MANAGER_ROLES == {"gerente", "admin"}


# ── Testes: fallbacks ────────────────────────────────────────────────────────

class TestFallbacks:
    """Cobre todos os caminhos de fallback."""

    def test_codigo_desconhecido_usa_primeiro_nome(self):
        assert subfolder(user_code="999", user_name="PAULO HENRIQUE") == "PAULO"

    def test_nome_composto_usa_primeiro(self):
        assert subfolder(user_code="999", user_name="JOAO DA SILVA") == "JOAO"

    def test_codigo_vazio_usa_primeiro_nome(self):
        assert subfolder(user_code="", user_name="MARIA") == "MARIA"

    def test_tudo_vazio_retorna_vendedor(self):
        assert subfolder(user_code="", user_name="") == "VENDEDOR"

    def test_none_equivalente_a_vazio(self):
        # None coercido para string
        result = vendor_subfolder(None, None)  # type: ignore[arg-type]
        assert result == "VENDEDOR"

    def test_caracteres_invalidos_no_nome_sao_removidos(self):
        assert subfolder(user_code="999", user_name='JO<AO:SILVA\\TEST') == "JOAOSILVATEST"

    def test_nome_so_com_caracteres_invalidos_retorna_vendedor(self):
        assert subfolder(user_code="", user_name='<>:"/\\|?*') == "VENDEDOR"

    def test_espacos_extras_no_codigo_sao_ignorados(self):
        """Código com espaço em volta ainda deve resolver corretamente."""
        # A função faz strip() no código
        assert subfolder(user_code=" 412 ", user_name="X") == "ADLER"


# ── Testes: integração com caminho completo ──────────────────────────────────

class TestCaminhoCompleto:
    """Simula o que main_window._vendor_pdf_folder() faz."""

    def _full_path(self, base, user_code, user_name, role="vendedor",
                   req_vendor_code="", req_vendor_name=""):
        import os
        sub = vendor_subfolder(user_code, user_name, role, req_vendor_code, req_vendor_name)
        return os.path.join(base, sub)

    BASE = r"\\10.1.1.140\ti\REQUISIÇÕES (VENDAS)\PDF\VENDEDORES"

    def test_vendedor_adler(self):
        path = self._full_path(self.BASE, "412", "ADLER EDUARDO")
        assert path.endswith("ADLER")

    def test_gerente_req_do_igor(self):
        path = self._full_path(
            self.BASE, "95", "EDUARDO MARRA", role="gerente",
            req_vendor_code="325"
        )
        assert path.endswith("IGOR")

    def test_base_folder_preservada(self):
        path = self._full_path(self.BASE, "223", "LUCAS GABRIEL")
        assert path.startswith(self.BASE)
        assert "LUCAS" in path
