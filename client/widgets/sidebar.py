import os
import unicodedata

from PySide6.QtCore import Qt, Signal, QSize, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor, QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..core import theme
from ..core.session import session
from .smooth_scroll import apply_smooth_scroll


LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_sidebar.png")

SIDEBAR_ICON_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "assets", "sidebar_icons"),
]

# ── Caches de ícones ───────────────────────────────────────────────────────────
# Sobrevivem ao longo de toda a sessão para que rebuilds (toggle de tema,
# troca de escala) não repitam scans de rede bloqueantes.
_dir_listing_cache: dict[str, list[str] | None] = {}   # dir -> nomes de arquivos (ou None se falhou)
_icon_path_cache:   dict[str, str]              = {}   # icon_key -> caminho absoluto (ou "")
_pixmap_cache:      dict[tuple, "QPixmap"]      = {}   # (icon_key, side_px) -> QPixmap

SIDEBAR_ICON_ALIASES = {
    "notificacoes": ["notificacoes", "notificações", "notificacao", "notificação", "sino", "bell"],
    "nova":         ["nova requisicao", "nova requisição", "requisicao", "requisição", "nova"],
    "dashboard":    ["painel gerencial", "dashboard", "painel"],
    "pedidos":      ["central de pedidos", "pedidos", "pedido"],
    "entregas":     ["entregas", "entrega", "agenda de entregas"],
    "producao":     ["producao", "produção"],
    "historico":    ["historico", "histórico", "busca", "historico busca", "histórico busca"],
    "usuarios":     ["usuarios", "usuários", "usuario", "usuário", "central de usuarios", "central de usuários"],
    "config":       ["configuracoes", "configurações", "config", "ajustes"],
    "feedback":     ["feedback", "feedbacks", "sugestao", "sugestoes", "bugs", "elogios", "problemas"],
    "usuario":      ["usuario", "usuário", "perfil"],
    "trocar_usuario": ["trocar usuario", "trocar usuário", "alternar usuario", "alternar usuário", "switch user"],
    "sair":         ["sair", "logout"],
}

NAV_ITEMS = [
    ("nova",      "NOVA REQUISIÇÃO",    "nova"),
    ("dashboard", "PAINEL GERENCIAL",   "dashboard"),
    ("pedidos",   "CENTRAL DE PEDIDOS", "pedidos"),
    ("entregas",  "ENTREGAS",           "pedidos"),
    ("pinheiro_industria", "PINHEIRO INDÚSTRIA", "pinheiro_industria"),
    ("ar",        "A&&R",               "ar"),
    ("historico", "HISTÓRICO / BUSCA",  "historico"),
    ("feedback",  "FEEDBACKS",          "feedback"),
]

BOTTOM_NAV_ITEMS = [
    ("feedback", "FEEDBACKS", "feedback"),
    ("config", "CONFIGURAÇÕES", "config"),
]

NAV_GROUPS = [
    [
        ("nova", "NOVA REQUISIÇÃO", "nova"),
        ("pedidos", "CENTRAL DE PEDIDOS", "pedidos"),
        ("entregas", "ENTREGAS", "pedidos"),
        ("ar", "A&&R", "ar"),
        ("pinheiro_industria", "PINHEIRO INDÚSTRIA", "pinheiro_industria"),
    ],
    [
        ("dashboard", "PAINEL GERENCIAL", "dashboard"),
        ("historico", "HISTÓRICO / BUSCA", "historico"),
    ],
]


def _normalize_icon_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(
        "".join(ch if ch.isalnum() else " " for ch in stripped.lower()).split()
    )


def _find_sidebar_icon_path(icon_key: str) -> str:
    if icon_key == "feedback":
        forced_feedback_icon = os.path.join(
            os.path.dirname(__file__), "..", "assets", "sidebar_icons", "feedback.png"
        )
        if os.path.exists(forced_feedback_icon):
            _icon_path_cache[icon_key] = forced_feedback_icon
            return forced_feedback_icon

    # Cache de caminho: não re-escaneia diretórios para ícones já resolvidos
    if icon_key in _icon_path_cache:
        return _icon_path_cache[icon_key]

    aliases = [_normalize_icon_name(a) for a in SIDEBAR_ICON_ALIASES.get(icon_key, [icon_key])]
    found = ""

    for directory in SIDEBAR_ICON_DIRS:
        # Cache de listagem: cada diretório é lido no máximo uma vez por sessão
        if directory not in _dir_listing_cache:
            try:
                _dir_listing_cache[directory] = os.listdir(directory)
            except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                _dir_listing_cache[directory] = None

        filenames = _dir_listing_cache[directory]
        if filenames is None:
            continue

        fallback = ""
        for filename in filenames:
            stem, ext = os.path.splitext(filename)
            if ext.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                continue
            normalized_name = _normalize_icon_name(stem)
            full_path = os.path.join(directory, filename)
            for alias in aliases:
                if normalized_name == alias:
                    found = full_path
                    break
                if alias and alias in normalized_name:
                    fallback = fallback or full_path
            if found:
                break
        if found:
            break
        if fallback:
            found = fallback
            break

    _icon_path_cache[icon_key] = found
    return found


def _load_sidebar_pixmap(icon_key: str, scale: float, size: int | None = None) -> QPixmap:
    side = size or max(18, int(20 * scale))
    cache_key = (icon_key, side)

    # Cache de pixmap: não recarrega/reescala imagens já processadas
    if cache_key in _pixmap_cache:
        return _pixmap_cache[cache_key]

    path = _find_sidebar_icon_path(icon_key)
    if not path:
        _pixmap_cache[cache_key] = QPixmap()
        return QPixmap()

    pixmap = QPixmap(path)
    if pixmap.isNull():
        _pixmap_cache[cache_key] = QPixmap()
        return QPixmap()

    result = pixmap.scaled(
        side, side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _pixmap_cache[cache_key] = result
    return result


def _apply_sidebar_icon(button: QPushButton, icon_key: str, scale: float):
    pixmap = _load_sidebar_pixmap(icon_key, scale)
    if pixmap.isNull():
        button.setIcon(QIcon())
        return
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(pixmap.width(), pixmap.height()))


# ── Toggle claro / escuro ──────────────────────────────────────────────────────

_PILL_W    = 38
_PILL_H    = 20
_KNOB_SIZE = 14
_KNOB_PAD  = 3


class _ThemeToggle(QWidget):
    """Interruptor ☀️/🌙 embutido no sidebar com animação deslizante."""

    toggled = Signal(bool)   # True = modo escuro

    def __init__(self, is_dark: bool, scale: float, parent=None):
        super().__init__(parent)
        self._dark  = is_dark
        self._scale = scale
        self._build()

    def _build(self):
        height    = max(40, int(48 * self._scale))
        font_size = max(8, int(10 * self._scale))
        self.setFixedHeight(height)
        self.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 16, 0)
        lay.setSpacing(10)

        # ── Pill ──────────────────────────────────────────────────────────────
        self._pill = QWidget()
        self._pill.setFixedSize(_PILL_W, _PILL_H)

        self._knob = QWidget(self._pill)
        self._knob.setFixedSize(_KNOB_SIZE, _KNOB_SIZE)
        self._knob.setStyleSheet("background:#FFFFFF; border-radius:7px;")

        # Posição e cor iniciais (sem animação)
        self._knob.move(self._knob_x(self._dark), _KNOB_PAD)
        self._pill.setStyleSheet(self._pill_style(self._dark))

        lay.addWidget(self._pill)

        # ── Ícone e texto ─────────────────────────────────────────────────────
        self._icon_lbl = QLabel("🌙" if self._dark else "☀️")
        self._icon_lbl.setStyleSheet("font-size:14px; background:transparent;")
        lay.addWidget(self._icon_lbl)

        self._text_lbl = QLabel("MODO ESCURO" if self._dark else "MODO CLARO")
        self._text_lbl.setStyleSheet(
            f"color:rgba(255,255,255,0.82); font-size:{font_size}pt;"
            f"font-weight:700; background:transparent;"
        )
        lay.addWidget(self._text_lbl, 1)

        # ── Animação do knob ──────────────────────────────────────────────────
        self._anim = QPropertyAnimation(self._knob, b"pos")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _knob_x(self, dark: bool) -> int:
        return _PILL_W - _KNOB_SIZE - _KNOB_PAD if dark else _KNOB_PAD

    def _pill_style(self, dark: bool) -> str:
        bg = theme.SIDEBAR_INDICATOR if dark else "rgba(255,255,255,0.22)"
        return f"background:{bg}; border-radius:{_PILL_H // 2}px;"

    def _animate_to(self, dark: bool):
        self._pill.setStyleSheet(self._pill_style(dark))
        self._anim.stop()
        self._anim.setStartValue(self._knob.pos())
        self._anim.setEndValue(QPoint(self._knob_x(dark), _KNOB_PAD))
        self._anim.start()

    def _refresh_labels(self) -> None:
        self._icon_lbl.setText("🌙" if self._dark else "☀️")
        self._text_lbl.setText("MODO ESCURO" if self._dark else "MODO CLARO")

    def set_dark(self, dark: bool, *, animate: bool = False) -> None:
        self._dark = bool(dark)
        if animate:
            self._animate_to(self._dark)
        else:
            self._anim.stop()
            self._pill.setStyleSheet(self._pill_style(self._dark))
            self._knob.move(self._knob_x(self._dark), _KNOB_PAD)
        self._refresh_labels()

    # ── Interação ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_dark(not self._dark, animate=True)
            self.toggled.emit(self._dark)
        super().mousePressEvent(event)


class _BellButton(QWidget):
    """Sininho com badge de contagem de não lidas."""

    clicked = Signal()

    def __init__(self, scale: float, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._setup()

    def _setup(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        height = max(40, int(48 * self._scale))
        font_size = max(9, int(11 * self._scale))

        self._btn = QPushButton("NOTIFICAÇÕES")
        self._btn.setFixedHeight(height)
        self._btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:transparent; color:rgba(255,255,255,0.88);"
            f"  text-align:left; padding-left:16px; border:1px solid transparent;"
            f"  margin:4px 12px; border-radius:8px; font-size:{font_size}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:rgba(45, 127, 249, 0.16); color:#fff;"
            f"  border-color:rgba(255,255,255,0.08);"
            f"}}"
        )
        _apply_sidebar_icon(self._btn, "notificacoes", self._scale)
        self._btn.clicked.connect(self.clicked.emit)
        lay.addWidget(self._btn, 1)

        self._badge = QLabel("")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(24, 24)
        self._badge.setStyleSheet(
            "background:#EF4444; color:#fff; border-radius:12px;"
            "font-size:9pt; font-weight:bold;"
        )
        self._badge.hide()
        lay.addWidget(self._badge)
        lay.addSpacing(16)

        self.setFixedHeight(height)
        self.setStyleSheet(f"background:{theme.SIDEBAR_BG};")

    def set_count(self, count: int):
        if count > 0:
            self._badge.setText(str(min(count, 99)))
            self._badge.show()
        else:
            self._badge.hide()


class Sidebar(QWidget):
    nav_clicked    = Signal(str)
    logout_clicked = Signal()
    switch_user_clicked = Signal()
    bell_clicked   = Signal()
    theme_toggled  = Signal(bool)   # True = modo escuro

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._nav_btns: dict[str, QPushButton] = {}
        self._active = "nova"
        self.setObjectName("SidebarColumn")
        self._setup_ui()
        self.setFixedWidth(max(140, int(236 * scale)))

    def _setup_ui(self):
        self.setStyleSheet(
            f"QWidget#SidebarColumn {{ background:{theme.SIDEBAR_BG}; }}"
            f"QWidget#SidebarPanel {{ background:{theme.SIDEBAR_BG}; }}"
            f"QWidget#SidebarPanel QLabel {{ background:transparent; }}"
        )
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── ScrollArea que envolve TODO o conteúdo da sidebar ─────────────────
        # Barra fina e discreta aparece automaticamente quando a escala for grande.
        self._sidebar_scroll = QScrollArea()
        apply_smooth_scroll(self._sidebar_scroll)
        self._sidebar_scroll.setWidgetResizable(True)
        self._sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sidebar_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.SIDEBAR_BG}; border:none; }}"
            f"QScrollBar:vertical {{"
            f"  width:4px; background:transparent; margin:0;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background:rgba(255,255,255,0.22); border-radius:2px; min-height:24px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background:rgba(255,255,255,0.40); }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:none; }}"
        )

        panel = QWidget()
        panel.setObjectName("SidebarPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # ── Logo ──────────────────────────────────────────────────────────────
        logo_container = QWidget()
        logo_container.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 20, 16, 18)

        logo_label = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            width = max(100, int(176 * self.scale))
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:{theme.TEXT_WHITE}; font-size:{max(11, int(13 * self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.addWidget(logo_label)
        panel_layout.addWidget(logo_container)
        panel_layout.addWidget(self._separator())

        # ── Navegação principal ───────────────────────────────────────────────
        self._group_separators: list[tuple[int, QFrame]] = []
        for group_index, nav_group in enumerate(NAV_GROUPS):
            for key, label, icon_key in nav_group:
                btn = self._make_btn(label, icon_key, nav_key=key)
                self._nav_btns[key] = btn
                btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
                panel_layout.addWidget(btn)
            if group_index < len(NAV_GROUPS) - 1:
                sep = self._separator()
                self._group_separators.append((group_index, sep))
                panel_layout.addWidget(sep)

        # Espaço flexível — empurra o rodapé para baixo quando há espaço sobrando
        panel_layout.addStretch(1)

        # ── Rodapé: config + notificações + usuário + sair ────────────────────
        panel_layout.addWidget(self._separator())

        self._bell = _BellButton(self.scale)
        self._bell.clicked.connect(self.bell_clicked.emit)
        panel_layout.addWidget(self._bell)

        for key, label, icon_key in BOTTOM_NAV_ITEMS:
            btn = self._make_btn(label, icon_key, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            panel_layout.addWidget(btn)

        # ── Toggle claro / escuro ─────────────────────────────────────────────
        panel_layout.addWidget(self._separator())

        self._theme_toggle = _ThemeToggle(theme.is_dark, self.scale)
        self._theme_toggle.toggled.connect(self.theme_toggled.emit)
        panel_layout.addWidget(self._theme_toggle)

        panel_layout.addWidget(self._separator())

        # Linha do usuário: ícone + nome
        user_row = QWidget()
        user_row.setStyleSheet("background:transparent;")
        user_layout = QHBoxLayout(user_row)
        user_layout.setContentsMargins(18, 10, 18, 10)
        user_layout.setSpacing(8)

        self.user_icon_label = QLabel()
        self.user_icon_label.setStyleSheet("background:transparent;")
        user_layout.addWidget(self.user_icon_label, 0, Qt.AlignmentFlag.AlignTop)

        self.user_label = QLabel(f"USUÁRIO: {session.user_name}")
        self.user_label.setStyleSheet(
            f"color:rgba(255,255,255,0.78); font-size:{max(8, int(9 * self.scale))}pt;"
        )
        self.user_label.setWordWrap(True)
        user_layout.addWidget(self.user_label, 1)
        panel_layout.addWidget(user_row)
        self._refresh_user_icon()

        btn_switch_user = self._make_btn("TROCAR USUÁRIO", "usuario")
        btn_switch_user.clicked.connect(self.switch_user_clicked.emit)
        panel_layout.addWidget(btn_switch_user)

        btn_sair = self._make_btn("SAIR", "sair")
        btn_sair.clicked.connect(self.logout_clicked.emit)
        panel_layout.addWidget(btn_sair)
        panel_layout.addSpacing(12)

        self._sidebar_scroll.setWidget(panel)
        root_layout.addWidget(self._sidebar_scroll)

        self._highlight(self._active)

    def _make_btn(self, label: str, icon_key: str, nav_key: str = "") -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(bool(nav_key))
        height = max(40, int(48 * self.scale))
        font_size = max(9, int(11 * self.scale))
        btn.setFixedHeight(height)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:transparent; color:rgba(255,255,255,0.88);"
            f"  text-align:left; padding-left:16px; border:1px solid transparent;"
            f"  margin:4px 12px; border-radius:8px; font-size:{font_size}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:rgba(45, 127, 249, 0.16); color:#fff; border-color:rgba(255,255,255,0.08);"
            f"}}"
            f"QPushButton:checked {{"
            f"  background:{theme.SIDEBAR_ACTIVE}; color:#fff;"
            f"  border:1px solid {theme.SIDEBAR_INDICATOR};"
            f"}}"
        )
        _apply_sidebar_icon(btn, icon_key, self.scale)
        return btn

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:rgba(255,255,255,0.12); margin:6px 12px;")
        sep.setFixedHeight(1)
        return sep

    def _on_nav(self, key: str):
        self._highlight(key)
        self.nav_clicked.emit(key)

    def _highlight(self, key: str):
        self._active = key
        for nav_key, btn in self._nav_btns.items():
            btn.setChecked(nav_key == key)

    def refresh_user(self):
        self.user_label.setText(f"USUÁRIO: {session.user_name}")
        self._refresh_user_icon()

    def set_notification_count(self, count: int):
        self._bell.set_count(count)

    def set_actions_visible(self, visible: bool):
        pass

    def refresh_separators(self) -> None:
        """Oculta separadores cujo grupo seguinte ficou completamente invisível."""
        for group_index, sep in self._group_separators:
            next_group = NAV_GROUPS[group_index + 1]
            next_visible = any(
                self._nav_btns.get(key) is not None and self._nav_btns[key].isVisible()
                for key, _, _ in next_group
            )
            sep.setVisible(next_visible)

    def _refresh_user_icon(self):
        pixmap = _load_sidebar_pixmap("usuario", self.scale, size=max(16, int(18 * self.scale)))
        if pixmap.isNull():
            self.user_icon_label.clear()
            self.user_icon_label.setFixedWidth(0)
            return
        self.user_icon_label.setPixmap(pixmap)
        self.user_icon_label.setFixedWidth(max(18, pixmap.width()))

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"QWidget#SidebarColumn {{ background:{theme.SIDEBAR_BG}; }}"
            f"QWidget#SidebarPanel {{ background:{theme.SIDEBAR_BG}; }}"
            f"QWidget#SidebarPanel QLabel {{ background:transparent; }}"
        )
        self._sidebar_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.SIDEBAR_BG}; border:none; }}"
            f"QScrollBar:vertical {{"
            f"  width:4px; background:transparent; margin:0;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background:rgba(255,255,255,0.22); border-radius:2px; min-height:24px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background:rgba(255,255,255,0.40); }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:none; }}"
        )
        font_size = max(9, int(11 * self.scale))
        for btn in self._nav_btns.values():
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background:transparent; color:rgba(255,255,255,0.88);"
                f"  text-align:left; padding-left:16px; border:1px solid transparent;"
                f"  margin:4px 12px; border-radius:8px; font-size:{font_size}pt; font-weight:700;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background:rgba(45, 127, 249, 0.16); color:#fff;"
                f"  border-color:rgba(255,255,255,0.08);"
                f"}}"
                f"QPushButton:checked {{"
                f"  background:{theme.SIDEBAR_ACTIVE}; color:#fff;"
                f"  border:1px solid {theme.SIDEBAR_INDICATOR};"
                f"}}"
            )
        self._theme_toggle.set_dark(theme.is_dark, animate=False)
        self._theme_toggle.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        self._bell.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
