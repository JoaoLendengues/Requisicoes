import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "settings.json")

# ── Passos de escala disponíveis (referência: PROJECT_PARALLELv2) ─────────────
# Cada entrada: (label exibida na UI, fator numérico ou None para automático)
SCALE_STEPS: list[tuple[str, float | None]] = [
    ("Automática", None),
    ("90%",  0.90),
    ("100%", 1.00),
    ("110%", 1.10),
    ("125%", 1.25),
    ("150%", 1.50),
    ("175%", 1.75),
]

# Mapa label → fator (exclui "Automática")
SCALE_FACTOR: dict[str, float] = {
    label: f for label, f in SCALE_STEPS if f is not None
}


def _ratio_to_scale(ratio: float) -> float:
    """Mapeia ratio de resolução (vs 1920×1080) para o fator de escala discreto."""
    if ratio <= 0.88:
        return 0.90
    if ratio <= 1.00:
        return 1.00
    if ratio <= 1.12:
        return 1.10
    if ratio <= 1.32:
        return 1.25
    if ratio <= 1.62:
        return 1.50
    return 1.75


class ResolutionManager:
    """Detecta resolução na inicialização e calcula fator de escala adaptativo."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._ready = False
        return cls._instance

    def init(self, app):
        """Deve ser chamado após QApplication ser criada."""
        if self._ready:
            return
        screen = app.primaryScreen()
        self._logical_dpi  = screen.logicalDotsPerInch()
        self._geo          = screen.availableGeometry()
        self._auto_scale   = self._calc_auto_scale()
        self._user_scale   = self._load_setting("font_scale")   # None ou label "90%"/"100%"/…
        self._server_url   = self._load_setting("server_url") or "http://10.1.1.151:5000"
        self._maximized    = self._load_setting("maximized", True)
        self._ready = True

    # ── Cálculo automático ───────────────────────────────────────────────────
    def _calc_auto_scale(self) -> float:
        """Escala automática por ratio de resolução (referência: 1920×1080).

        Mapeia a resolução real a um dos passos discretos:
        0.90 / 1.00 / 1.10 / 1.25 / 1.50 / 1.75.
        Overflow de conteúdo é tratado por scrollbars na sidebar e nas views.
        """
        w = max(1, self._geo.width())
        h = max(1, self._geo.height())
        ratio = min(w / 1920, h / 1080)
        return _ratio_to_scale(ratio)

    # ── Escala ───────────────────────────────────────────────────────────────
    @property
    def scale(self) -> float:
        """Fator de escala ativo (automático ou escolhido pelo usuário).

        Aceita tanto o novo formato (label string, ex.: '100%') quanto o
        formato legado (float, ex.: 0.95) para compatibilidade retroativa.
        """
        us = self._user_scale
        if us is None:
            return self._auto_scale
        if isinstance(us, str) and us in SCALE_FACTOR:
            return SCALE_FACTOR[us]
        if isinstance(us, (int, float)):
            return round(float(us), 2)
        return self._auto_scale

    @property
    def scale_label(self) -> str:
        """Label atual exibida na UI ('Automática', '90%', '100%', …)."""
        us = self._user_scale
        if us is None:
            return "Automática"
        if isinstance(us, str) and us in SCALE_FACTOR:
            return us
        # Formato legado (float): encontra o passo discreto mais próximo
        if isinstance(us, (int, float)):
            closest = min(SCALE_FACTOR.items(), key=lambda kv: abs(kv[1] - float(us)))
            return closest[0]
        return "Automática"

    @property
    def recommended_label(self) -> str:
        """Label do passo recomendado para a resolução atual."""
        raw = _ratio_to_scale(min(
            max(1, self._geo.width()) / 1920,
            max(1, self._geo.height()) / 1080,
        ))
        for label, f in SCALE_STEPS:
            if f is not None and abs(f - raw) < 0.01:
                return label
        return "100%"

    def font(self, base_pt: int) -> int:
        return max(8, round(base_pt * self.scale))

    def px(self, base_px: int) -> int:
        return max(1, round(base_px * self.scale))

    # ── Informações de tela ─────────────────────────────────────────────────
    @property
    def screen_width(self) -> int:
        return self._geo.width()

    @property
    def screen_height(self) -> int:
        return self._geo.height()

    @property
    def dpi(self) -> float:
        return self._logical_dpi

    @property
    def auto_scale(self) -> float:
        return self._auto_scale

    # ── Configurações persistentes ──────────────────────────────────────────
    @property
    def server_url(self) -> str:
        return self._server_url

    @property
    def start_maximized(self) -> bool:
        return bool(self._maximized)

    @property
    def pdf_folder(self) -> str:
        return r"Z:\REQUISIÇÕES (VENDAS)\PDF"

    def save(self, **kwargs):
        data = self._read_file()
        for k, v in kwargs.items():
            data[k] = v
            if k == "font_scale":
                self._user_scale = v
            if k == "server_url":
                self._server_url = v
            if k == "maximized":
                self._maximized = v
            if k == "pdf_folder":
                self._pdf_folder = v
        self._write_file(data)

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _load_setting(self, key: str, default=None):
        return self._read_file().get(key, default)

    def _read_file(self) -> dict:
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_file(self, data: dict):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


res = ResolutionManager()
