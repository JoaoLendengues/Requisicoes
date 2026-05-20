import os
import unicodedata

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..core import theme
from ..core.session import session


LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_sidebar.png")

SIDEBAR_ICON_DIRS = [
    r"Z:\REQUISIÇÕES (VENDAS)\ícones\PAINEL GERENCIAL\emoji\barral_lateral",
    r"\\data04tg\TI\REQUISIÇÕES (VENDAS)\ícones\PAINEL GERENCIAL\emoji\barral_lateral",
    os.path.join(os.path.dirname(__file__), "..", "assets", "sidebar_icons"),
]

SIDEBAR_ICON_ALIASES = {
    "notificacoes": ["notificacoes", "notificações", "notificacao", "notificação", "sino", "bell"],
    "nova":         ["nova requisicao", "nova requisição", "requisicao", "requisição", "nova"],
    "dashboard":    ["painel gerencial", "dashboard", "painel"],
    "pedidos":      ["central de pedidos", "pedidos", "pedido"],
    "producao":     ["producao", "produção"],
    "historico":    ["historico", "histórico", "busca", "historico busca", "histórico busca"],
    "usuarios":     ["usuarios", "usuários", "usuario", "usuário", "central de usuarios", "central de usuários"],
    "config":       ["configuracoes", "configurações", "config", "ajustes"],
    "usuario":      ["usuario", "usuário", "perfil"],
    "sair":         ["sair", "logout"],
}

NAV_ITEMS = [
    ("nova",      "NOVA REQUISIÇÃO",    "nova"),
    ("dashboard", "PAINEL GERENCIAL",   "dashboard"),
    ("pedidos",   "CENTRAL DE PEDIDOS", "pedidos"),
    ("producao",  "PRODUÇÃO",           "producao"),
    ("historico", "HISTÓRICO / BUSCA",  "historico"),
    ("usuarios",  "CENTRAL DE USUÁRIOS","usuarios"),
]

BOTTOM_NAV_ITEMS = [
    ("config", "CONFIGURAÇÕES", "config"),
]


def _normalize_icon_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(
        "".join(ch if ch.isalnum() else " " for ch in stripped.lower()).split()
    )


def _find_sidebar_icon_path(icon_key: str) -> str:
    aliases = [_normalize_icon_name(a) for a in SIDEBAR_ICON_ALIASES.get(icon_key, [icon_key])]

    for directory in SIDEBAR_ICON_DIRS:
        try:
            filenames = os.listdir(directory)
        except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
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
                    return full_path
                if alias and alias in normalized_name:
                    fallback = fallback or full_path
        if fallback:
            return fallback

    return ""


def _load_sidebar_pixmap(icon_key: str, scale: float, size: int | None = None) -> QPixmap:
    path = _find_sidebar_icon_path(icon_key)
    if not path:
        return QPixmap()
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    side = size or max(18, int(20 * scale))
    return pixmap.scaled(
        side, side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _apply_sidebar_icon(button: QPushButton, icon_key: str, scale: float):
    pixmap = _load_sidebar_pixmap(icon_key, scale)
    if pixmap.isNull():
        button.setIcon(QIcon())
        return
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(pixmap.width(), pixmap.height()))


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
        self._badge.setFixedSize(20, 20)
        self._badge.setStyleSheet(
            "background:#EF4444; color:#fff; border-radius:10px;"
            "font-size:8pt; font-weight:bold;"
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
    nav_clicked = Signal(str)
    logout_clicked = Signal()
    bell_clicked = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._nav_btns: dict[str, QPushButton] = {}
        self._active = "nova"
        self.setObjectName("SidebarColumn")
        self._setup_ui()
        self.setFixedWidth(max(212, int(236 * scale)))

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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
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
            width = max(152, int(176 * self.scale))
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
        for key, label, icon_key in NAV_ITEMS:
            btn = self._make_btn(label, icon_key, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            panel_layout.addWidget(btn)

        # Espaço flexível — empurra o rodapé para baixo quando há espaço sobrando
        panel_layout.addStretch(1)

        # ── Rodapé: config + notificações + usuário + sair ────────────────────
        panel_layout.addWidget(self._separator())

        for key, label, icon_key in BOTTOM_NAV_ITEMS:
            btn = self._make_btn(label, icon_key, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            panel_layout.addWidget(btn)

        panel_layout.addWidget(self._separator())

        self._bell = _BellButton(self.scale)
        self._bell.clicked.connect(self.bell_clicked.emit)
        panel_layout.addWidget(self._bell)

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

        btn_sair = self._make_btn("SAIR", "sair")
        btn_sair.clicked.connect(self.logout_clicked.emit)
        panel_layout.addWidget(btn_sair)
        panel_layout.addSpacing(12)

        scroll.setWidget(panel)
        root_layout.addWidget(scroll)

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

    def _refresh_user_icon(self):
        pixmap = _load_sidebar_pixmap("usuario", self.scale, size=max(16, int(18 * self.scale)))
        if pixmap.isNull():
            self.user_icon_label.clear()
            self.user_icon_label.setFixedWidth(0)
            return
        self.user_icon_label.setPixmap(pixmap)
        self.user_icon_label.setFixedWidth(max(18, pixmap.width()))
