import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QSpacerItem,
    QSizePolicy,
)
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtCore import Qt, Signal
from ..core import theme
from ..core.session import session

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")

NAV_ITEMS = [
    ("nova",        "📋",  "NOVA REQUISIÇÃO"),
    ("historico",   "🕐",  "HISTÓRICO"),
    ("buscar",      "🔍",  "BUSCAR PEDIDO"),
    ("dashboard",   "📊",  "DASHBOARD"),
    ("config",      "⚙️",  "CONFIGURAÇÕES"),
]

# Ações (não mudam de view, disparam sinais)
ACTION_ITEMS = [
    ("salvar",      "💾",  "SALVAR"),
    ("pdf",         "📄",  "GERAR PDF"),
    ("whatsapp",    "💬",  "ENVIAR WHATSAPP"),
]


class Sidebar(QWidget):
    nav_clicked    = Signal(str)    # ex: "nova", "historico" ...
    action_clicked = Signal(str)    # ex: "salvar", "pdf", "whatsapp"
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

        # ── Logo ─────────────────────────────────────────────────────────────
        logo_container = QWidget()
        logo_container.setStyleSheet(f"background:{theme.SIDEBAR_BG};")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(16, 20, 16, 16)

        logo_label = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            w = max(140, int(160 * self.scale))
            pix = pix.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:#fff; font-size:{max(11, int(13*self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.addWidget(logo_label)
        layout.addWidget(logo_container)

        # ── Separador ────────────────────────────────────────────────────────
        layout.addWidget(self._separator())

        # ── Ações do formulário ───────────────────────────────────────────────
        for key, icon, label in ACTION_ITEMS:
            btn = self._make_btn(icon, label, action=True)
            btn.clicked.connect(lambda checked=False, k=key: self.action_clicked.emit(k))
            layout.addWidget(btn)

        layout.addWidget(self._separator())

        # ── Navegação ─────────────────────────────────────────────────────────
        for key, icon, label in NAV_ITEMS:
            btn = self._make_btn(icon, label, nav_key=key)
            self._nav_btns[key] = btn
            btn.clicked.connect(lambda checked=False, k=key: self._on_nav(k))
            layout.addWidget(btn)

        layout.addStretch()
        layout.addWidget(self._separator())

        # ── Usuário logado ────────────────────────────────────────────────────
        self.user_label = QLabel(f"👤  {session.user_name}")
        self.user_label.setStyleSheet(
            f"color:#94A3B8; font-size:{max(8, int(9*self.scale))}pt; padding:8px 16px;"
        )
        self.user_label.setWordWrap(True)
        layout.addWidget(self.user_label)

        # ── Sair ─────────────────────────────────────────────────────────────
        btn_sair = self._make_btn("🚪", "SAIR", action=True)
        btn_sair.setStyleSheet(btn_sair.styleSheet().replace(
            theme.SIDEBAR_BG,
            theme.SIDEBAR_BG,
        ))
        btn_sair.clicked.connect(self.logout_clicked.emit)
        layout.addWidget(btn_sair)
        layout.addSpacing(8)

        self._highlight(self._active)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _make_btn(self, icon: str, label: str, nav_key: str = "",
                  action: bool = False) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setCheckable(bool(nav_key))
        h = max(38, int(44 * self.scale))
        btn.setFixedHeight(h)
        fs = max(8, int(10 * self.scale))
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:transparent; color:#CBD5E1;"
            f"  text-align:left; padding-left:12px; border:none;"
            f"  font-size:{fs}pt; border-left:3px solid transparent;"
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
        for k, btn in self._nav_btns.items():
            btn.setChecked(k == key)

    def refresh_user(self):
        self.user_label.setText(f"👤  {session.user_name}")

    def set_actions_visible(self, visible: bool):
        """Mostra/esconde ações de formulário conforme a view ativa."""
        pass  # Implementado via CSS enable/disable
