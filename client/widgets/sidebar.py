import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import theme
from ..core.session import session


LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_sidebar.png")

NAV_ITEMS = [
    ("nova", "\U0001F4DD", "NOVA REQUISI\u00c7\u00c3O"),
    ("dashboard", "\U0001F4CA", "PAINEL GERENCIAL"),
    ("pedidos", "\U0001F4E6", "CENTRAL DE PEDIDOS"),
    ("producao", "\U0001F3ED", "PRODU\u00c7\u00c3O"),
    ("historico", "\U0001F558", "HIST\u00d3RICO / BUSCA"),
    ("usuarios", "\U0001F465", "CENTRAL DE USU\u00c1RIOS"),
]

BOTTOM_NAV_ITEMS = [
    ("config", "\u2699\ufe0f", "CONFIGURA\u00c7\u00d5ES"),
]


class Sidebar(QWidget):
    nav_clicked = Signal(str)
    logout_clicked = Signal()

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("SidebarPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

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

        for key, icon, label in NAV_ITEMS:
            btn = self._make_btn(icon, label, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            panel_layout.addWidget(btn)

        panel_layout.addStretch()
        panel_layout.addWidget(self._separator())

        for key, icon, label in BOTTOM_NAV_ITEMS:
            btn = self._make_btn(icon, label, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            panel_layout.addWidget(btn)

        panel_layout.addWidget(self._separator())

        self.user_label = QLabel(f"\U0001F464 USU\u00c1RIO: {session.user_name}")
        self.user_label.setStyleSheet(
            f"color:rgba(255,255,255,0.78); font-size:{max(8, int(9 * self.scale))}pt; padding:10px 18px;"
        )
        self.user_label.setWordWrap(True)
        panel_layout.addWidget(self.user_label)

        btn_sair = self._make_btn("\U0001F6AA", "SAIR")
        btn_sair.clicked.connect(self.logout_clicked.emit)
        panel_layout.addWidget(btn_sair)
        panel_layout.addSpacing(12)

        layout.addWidget(panel)

        self._highlight(self._active)

    def _make_btn(self, icon: str, label: str, nav_key: str = "") -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
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
        self.user_label.setText(f"\U0001F464 USU\u00c1RIO: {session.user_name}")

    def set_actions_visible(self, visible: bool):
        pass
