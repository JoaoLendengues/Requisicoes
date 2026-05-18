import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QPixmap, QColor, QFont
from PySide6.QtCore import Qt, Signal, QThread, QObject

from ..core import theme
from ..core.resolution import res
from ..core.session import session
from ..api import client as api

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")


# ── Worker de login (não bloqueia UI) ─────────────────────────────────────────
class LoginWorker(QObject):
    success = Signal(dict)
    error   = Signal(str)
    finished = Signal()

    def __init__(self, code: str, password: str):
        super().__init__()
        self.code = code
        self.password = password

    def run(self):
        try:
            data = api.login(self.code, self.password)
            self.success.emit(data)
        except api.APIError as e:
            self.error.emit(e.detail)
        except Exception as e:
            self.error.emit(f"Sem conexão com o servidor.\n{e}")
        finally:
            self.finished.emit()


# ── Tela de Login ─────────────────────────────────────────────────────────────
class LoginView(QWidget):
    login_success = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = res.scale
        self._thread: QThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        # Fundo degradê azul escuro
        self.setStyleSheet(
            f"background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:1,"
            f"stop:0 #0f1e3d, stop:1 #1B2B4B);"
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Card central ──────────────────────────────────────────────────────
        card = QFrame()
        card.setFixedWidth(max(340, int(400 * self.scale)))
        card.setStyleSheet(
            "background:#fff; border-radius:16px; padding:8px;"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 80))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            max(24, int(32 * self.scale)),
            max(24, int(32 * self.scale)),
            max(24, int(32 * self.scale)),
            max(24, int(32 * self.scale)),
        )
        card_layout.setSpacing(max(12, int(16 * self.scale)))

        # Logo
        logo_label = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            w = max(160, int(200 * self.scale))
            pix = pix.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:{theme.PRIMARY}; font-size:{max(14, int(16*self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(logo_label)

        # Título
        title = QLabel("📋 Sistema de Requisições")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(10, int(12*self.scale))}pt;"
        )
        card_layout.addWidget(title)

        card_layout.addSpacing(max(4, int(8 * self.scale)))

        # Campo Código
        lbl_code = QLabel("Código de acesso")
        lbl_code.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11*self.scale))}pt; font-weight:bold;"
        )
        card_layout.addWidget(lbl_code)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("Ex: 1")
        self.input_code.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_code.setStyleSheet(theme.input_style(self.scale))
        self.input_code.returnPressed.connect(self._do_login)
        card_layout.addWidget(self.input_code)

        # Campo Senha
        lbl_pass = QLabel("Senha")
        lbl_pass.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11*self.scale))}pt; font-weight:bold;"
        )
        card_layout.addWidget(lbl_pass)

        pass_row = QHBoxLayout()
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("••••••••")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_pass.setStyleSheet(theme.input_style(self.scale))
        self.input_pass.returnPressed.connect(self._do_login)

        self.btn_show = QPushButton("👁")
        self.btn_show.setFixedSize(max(36, int(42 * self.scale)),
                                    max(36, int(42 * self.scale)))
        self.btn_show.setCheckable(True)
        self.btn_show.setStyleSheet(
            f"QPushButton {{ background:{theme.INPUT_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:5px; color:{theme.TEXT_MEDIUM}; }}"
            f"QPushButton:checked {{ background:{theme.SIDEBAR_ACTIVE}; color:#fff; }}"
        )
        self.btn_show.toggled.connect(
            lambda v: self.input_pass.setEchoMode(
                QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password
            )
        )
        pass_row.addWidget(self.input_pass)
        pass_row.addWidget(self.btn_show)
        card_layout.addLayout(pass_row)

        # Mensagem de erro
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet(
            f"color:{theme.DANGER}; font-size:{max(8, int(10*self.scale))}pt; background:#3b0f0f;"
            f"border-radius:6px; padding:6px;"
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        # Botão entrar
        self.btn_login = QPushButton("ENTRAR")
        self.btn_login.setFixedHeight(max(40, int(46 * self.scale)))
        self.btn_login.setStyleSheet(theme.primary_btn_style(self.scale))
        self.btn_login.clicked.connect(self._do_login)
        card_layout.addWidget(self.btn_login)

        card_layout.addSpacing(4)

        # Rodapé do card
        footer_card = QLabel("Ferragens Pinheiro · SIA e Taguatinga")
        footer_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_card.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(9*self.scale))}pt;"
        )
        card_layout.addWidget(footer_card)

        outer.addWidget(card)

        # Rodapé da tela
        footer = QLabel("pinheiroferragens.com.br")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color:{theme.TEXT_LABEL}; font-size:{max(7, int(9*self.scale))}pt; margin-top:16px;"
        )
        outer.addWidget(footer)

    # ── Login ─────────────────────────────────────────────────────────────────
    def _do_login(self):
        code = self.input_code.text().strip()
        pwd  = self.input_pass.text()
        if not code or not pwd:
            self._show_error("Preencha o código e a senha.")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Aguarde...")
        self.error_label.setVisible(False)

        self._worker = LoginWorker(code, pwd)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.success.connect(self._on_success)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._restore_btn)
        self._thread.start()

    def _on_success(self, data: dict):
        session.login(data)
        self.login_success.emit()

    def _on_error(self, msg: str):
        self._show_error(msg)

    def _restore_btn(self):
        self.btn_login.setEnabled(True)
        self.btn_login.setText("ENTRAR")

    def _show_error(self, msg: str):
        self.error_label.setText(msg)
        self.error_label.setVisible(True)
