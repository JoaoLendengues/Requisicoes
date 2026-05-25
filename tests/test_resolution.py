"""
Testes unitários para o sistema de resolução adaptativa.

Cobre:
- _ratio_to_scale(): mapeamento de ratio para fator de escala
- Cálculo de ratio para resoluções reais (800×600, 1024×768, etc.)
- SCALE_STEPS / SCALE_FACTOR: consistência das constantes
- Ajuste de layout: sidebar + conteúdo cabem na tela em cada resolução

Não requer Qt — todas as funções testadas são puras.
"""
import sys
import os

# Garante que o pacote client é encontrado sem instalar
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from client.core.resolution import _ratio_to_scale, SCALE_STEPS, SCALE_FACTOR


# ── Helpers ───────────────────────────────────────────────────────────────────

def ratio(w: int, h: int) -> float:
    """Calcula o ratio exatamente como ResolutionManager._calc_auto_scale()."""
    return min(max(1, w) / 1920, max(1, h) / 1080)


def auto_scale(w: int, h: int) -> float:
    return _ratio_to_scale(ratio(w, h))


def sidebar_width(scale: float) -> int:
    return max(140, int(236 * scale))


def stack_min_width(scale: float) -> int:
    return max(480, int(860 * scale))


def content_fits(screen_w: int, scale: float) -> bool:
    """Verifica se sidebar + stack mínimo cabem na largura da tela."""
    used = sidebar_width(scale) + 1 + stack_min_width(scale)  # +1 = separador
    return used <= screen_w


# ── Testes: _ratio_to_scale() ─────────────────────────────────────────────────

class TestRatioToScale:
    """Testa cada faixa de breakpoint da função _ratio_to_scale."""

    # Faixa 60% (ratio ≤ 0.50)
    def test_800x600(self):
        assert auto_scale(800, 600) == 0.60

    def test_960x540(self):
        # Exatamente no limite superior da faixa 60% (ratio ~0.50)
        assert auto_scale(960, 540) == 0.60

    def test_abaixo_de_800x600(self):
        assert auto_scale(640, 480) == 0.60

    # Faixa 75% (0.50 < ratio ≤ 0.60)
    def test_1024x768(self):
        assert auto_scale(1024, 768) == 0.75

    def test_1152x648(self):
        # Próximo ao limite superior da faixa 75% (ratio ~0.60)
        assert auto_scale(1152, 648) == 0.75

    # Faixa 85% (0.60 < ratio ≤ 0.76)
    def test_1280x720(self):
        assert auto_scale(1280, 720) == 0.85

    def test_1366x768(self):
        assert auto_scale(1366, 768) == 0.85

    def test_1440x900(self):
        assert auto_scale(1440, 900) == 0.85

    # Faixa 90% (0.76 < ratio ≤ 0.88)
    def test_1600x900(self):
        assert auto_scale(1600, 900) == 0.90

    def test_1680x1050(self):
        assert auto_scale(1680, 1050) == 0.90

    # Faixa 100% (0.88 < ratio ≤ 1.00)
    def test_1920x1080(self):
        assert auto_scale(1920, 1080) == 1.00

    def test_1920x1200(self):
        # Mais alto que 1080p mas ratio ainda ≤ 1.00
        assert auto_scale(1920, 1200) == 1.00

    # Faixa 110% (1.00 < ratio ≤ 1.12)
    def test_2048x1152(self):
        assert auto_scale(2048, 1152) == 1.10

    # Faixa 125% (1.12 < ratio ≤ 1.32)
    def test_2560x1080_ultrawide(self):
        # Ultrawide 21:9 com altura 1080p: min(2560/1920, 1080/1080) = 1.0 → 100%
        # A altura é o fator limitante, não a largura
        assert auto_scale(2560, 1080) == 1.00

    def test_2560x1080_wide_height(self):
        # Para atingir faixa 125%, a ALTURA precisa ser proporcional
        assert auto_scale(2304, 1296) == 1.25

    # Faixa 150% (1.32 < ratio ≤ 1.62)
    def test_2560x1440(self):
        assert auto_scale(2560, 1440) == 1.50

    def test_3440x1440(self):
        assert auto_scale(3440, 1440) == 1.50

    # Faixa 175% (ratio > 1.62)
    def test_3840x2160(self):
        assert auto_scale(3840, 2160) == 1.75

    def test_5120x2880(self):
        assert auto_scale(5120, 2880) == 1.75


# ── Testes: layout cabe na tela ───────────────────────────────────────────────

class TestLayoutFit:
    """
    Garante que sidebar + conteúdo mínimo cabem na largura de cada
    resolução típica sem gerar scroll horizontal.
    """

    @pytest.mark.parametrize("w,h", [
        (800,  600),
        (1024, 768),
        (1280, 720),
        (1280, 1024),
        (1366, 768),
        (1440, 900),
        (1600, 900),
        (1920, 1080),
        (2560, 1440),
    ])
    def test_sem_scroll_horizontal(self, w, h):
        scale = auto_scale(w, h)
        assert content_fits(w, scale), (
            f"{w}×{h}: sidebar {sidebar_width(scale)}px + "
            f"stack {stack_min_width(scale)}px = "
            f"{sidebar_width(scale) + 1 + stack_min_width(scale)}px "
            f"> tela {w}px"
        )

    def test_800x600_valores_exatos(self):
        """Validação detalhada do cenário crítico do projetor."""
        scale = auto_scale(800, 600)
        assert scale == 0.60
        sb = sidebar_width(scale)
        st = stack_min_width(scale)
        available = 800 - sb - 1  # -1 do separador
        assert available >= st, (
            f"Sidebar={sb}px, Stack mín={st}px, Disponível={available}px"
        )

    def test_scale_60_conteudo_disponivel(self):
        """A escala 60% deve deixar pelo menos 480px de conteúdo em 800px."""
        available = 800 - sidebar_width(0.60) - 1
        assert available >= 480


# ── Testes: constantes SCALE_STEPS / SCALE_FACTOR ────────────────────────────

class TestScaleConstants:

    def test_scale_steps_ordenados(self):
        """Os passos devem estar em ordem crescente de fator."""
        factors = [f for _, f in SCALE_STEPS if f is not None]
        assert factors == sorted(factors)

    def test_scale_factor_contem_todos_os_steps(self):
        """Todo label de SCALE_STEPS deve estar em SCALE_FACTOR."""
        for label, factor in SCALE_STEPS:
            if factor is not None:
                assert label in SCALE_FACTOR
                assert SCALE_FACTOR[label] == factor

    def test_60_percent_presente(self):
        assert "60%" in SCALE_FACTOR
        assert SCALE_FACTOR["60%"] == 0.60

    def test_75_percent_presente(self):
        assert "75%" in SCALE_FACTOR
        assert SCALE_FACTOR["75%"] == 0.75

    def test_100_percent_presente(self):
        assert "100%" in SCALE_FACTOR
        assert SCALE_FACTOR["100%"] == 1.00

    def test_escala_minima_e_60(self):
        """O menor passo disponível deve ser 60%."""
        min_scale = min(SCALE_FACTOR.values())
        assert min_scale == 0.60


# ── Testes: breakpoints exatos ────────────────────────────────────────────────

class TestBreakpoints:
    """Testa os valores exatamente nas fronteiras de cada faixa."""

    def test_limite_60_75(self):
        # ratio = 0.50 → ainda 60%
        assert _ratio_to_scale(0.50) == 0.60
        # ratio = 0.501 → já 75%
        assert _ratio_to_scale(0.501) == 0.75

    def test_limite_75_85(self):
        # ratio = 0.60 → ainda 75%
        assert _ratio_to_scale(0.60) == 0.75
        # ratio = 0.601 → já 85%
        assert _ratio_to_scale(0.601) == 0.85

    def test_limite_85_90(self):
        # ratio = 0.76 → ainda 85%
        assert _ratio_to_scale(0.76) == 0.85
        # ratio = 0.761 → já 90%
        assert _ratio_to_scale(0.761) == 0.90

    def test_limite_90_100(self):
        # ratio = 0.88 → ainda 90%
        assert _ratio_to_scale(0.88) == 0.90
        # ratio = 0.881 → já 100%
        assert _ratio_to_scale(0.881) == 1.00

    def test_limite_100_110(self):
        assert _ratio_to_scale(1.00) == 1.00
        assert _ratio_to_scale(1.001) == 1.10

    def test_limite_175(self):
        assert _ratio_to_scale(1.62) == 1.50
        assert _ratio_to_scale(1.621) == 1.75
        assert _ratio_to_scale(999.0) == 1.75
