import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "settings.json")


class ResolutionManager:
    """Detecta resolução/DPI na inicialização e calcula fator de escala."""

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
        self._user_scale   = self._load_setting("font_scale")
        self._server_url   = self._load_setting("server_url") or "http://10.1.1.151:5000"
        self._maximized    = self._load_setting("maximized", True)
        self._ready = True

    def _calc_auto_scale(self) -> float:
        """Escala baseada em DPI, limitada pela altura disponível da tela.

        Garante que todos os itens da sidebar caibam sem corte.
        Sidebar precisa de ~179 px fixo + 9 botões × button_height(S),
        onde button_height(S) = max(40, int(48 × S)).
        """
        dpi_scale = self._logical_dpi / 96.0
        # Altura disponível descontando barra de tarefas + status bar (~64 px)
        available_h = max(500, self._geo.height() - 64)
        # S máximo para que 9 botões + partes fixas caibam
        max_s = (available_h - 179) / (9 * 48)
        return round(max(0.72, min(dpi_scale, max_s, 1.4)), 2)

    # ── Escala ──────────────────────────────────────────────────────────────
    @property
    def scale(self) -> float:
        raw = float(self._user_scale) if self._user_scale else self._auto_scale
        # Aplica o cap de altura mesmo para escala manual, evitando corte da sidebar
        available_h = max(500, self._geo.height() - 64)
        height_cap = max(0.72, (available_h - 179) / (9 * 48))
        return min(raw, round(height_cap, 2))

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
