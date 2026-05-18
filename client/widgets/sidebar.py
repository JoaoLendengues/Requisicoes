import os

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal

from ..core import theme
from ..core.session import session


LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")

NAV_ITEMS = [
    ("nova", "📝", "NOVA REQUISIÇÃO"),
    ("dashboard", "📊", "DASHBOARD"),
    ("producao", "🏭", "PRODUÇÃO"),
    ("historico", "🕘", "HISTÓRICO / BUSCA"),
]

BOTTOM_NAV_ITEMS = [
    ("config", "⚙️", "CONFIGURAÇÕES"),
]


class Sidebar(QWidget):
    nav_clicked = Signal(str)
    logout_clicked = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._nav_btns: dict[str, QPushButton] = {}
        self._active = "nova"
        self._setup_ui()
        self.setFixedWidth(max(200, int(220 * scale)))

    def _setup_ui(self):
        self.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo_container = QWidget()
        logo_container.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 20, 16, 16)

        logo_label = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            width = max(140, int(160 * self.scale))
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:#fff; font-size:{max(11, int(13 * self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.addWidget(logo_label)
        layout.addWidget(logo_container)

        layout.addWidget(self._separator())

        for key, icon, label in NAV_ITEMS:
            btn = self._make_btn(icon, label, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            layout.addWidget(btn)

        layout.addStretch()
        layout.addWidget(self._separator())

        for key, icon, label in BOTTOM_NAV_ITEMS:
            btn = self._make_btn(icon, label, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            layout.addWidget(btn)

        layout.addWidget(self._separator())

        self.user_label = QLabel(f"👤 USUÁRIO: {session.user_name}")
        self.user_label.setStyleSheet(
            f"color:#94A3B8; font-size:{max(8, int(9 * self.scale))}pt; padding:8px 16px;"
        )
        self.user_label.setWordWrap(True)
        layout.addWidget(self.user_label)

        btn_sair = self._make_btn("🚪", "SAIR")
        btn_sair.clicked.connect(self.logout_clicked.emit)
        layout.addWidget(btn_sair)
        layout.addSpacing(8)

        self._highlight(self._active)

    def _make_btn(self, icon: str, label: str, nav_key: str = "") -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setCheckable(bool(nav_key))
        height = max(38, int(44 * self.scale))
        font_size = max(8, int(10 * self.scale))
        btn.setFixedHeight(height)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:transparent; color:#CBD5E1;"
            f"  text-align:left; padding-left:12px; border:none;"
            f"  font-size:{font_size}pt; border-left:3px solid transparent;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{theme.SIDEBAR_HOVER}; color:#fff;"
            f"}}"
            f"QPushButton:checked {{"
            f"  background:{theme.SIDEBAR_ACTIVE}; color:#fff;"
            f"  border-left:3px solid {theme.SIDEBAR_INDICATOR};"
            f"}}"
        )
        return btn

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2d3f63; margin:0 12px;")
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
        self.user_label.setText(f"👤 USUÁRIO: {session.user_name}")

    def set_actions_visible(self, visible: bool):
        pass
