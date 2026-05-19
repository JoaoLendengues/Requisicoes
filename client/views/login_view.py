import os

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.resolution import res
from ..core.session import session

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")


class LoginWorker(QObject):
    success = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, code: str, password: str):
        super().__init__()
        self.code = code
        self.password = password

    def run(self):
        try:
            self.success.emit(api.login(self.code, self.password))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(f"Sem conexao com o servidor.\n{exc}")
        finally:
            self.finished.emit()


class FirstAccessWorker(QObject):
    success = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, code: str, password: str):
        super().__init__()
        self.code = code
        self.password = password

    def run(self):
        try:
            self.success.emit(api.first_access(self.code, self.password))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(f"Sem conexao com o servidor.\n{exc}")
        finally:
            self.finished.emit()


class FirstAccessDialog(QDialog):
    def __init__(self, scale: float, code: str = "", parent=None):
        super().__init__(parent)
        self.scale = scale
        self.setWindowTitle("Primeiro acesso")
        self.setModal(True)
        self.setStyleSheet(f"background:{theme.CARD_BG}; color:{theme.TEXT_DARK};")
        self._setup_ui(code)

    def _setup_ui(self, code: str):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(18, int(22 * s)), max(18, int(22 * s)),
                                  max(18, int(22 * s)), max(18, int(22 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        title = QLabel("PRIMEIRO ACESSO")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(12, int(14 * s))}pt; font-weight:bold;"
        )
        helper = QLabel(
            "Informe seu codigo e cadastre uma senha para entrar no sistema."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        layout.addWidget(title)
        layout.addWidget(helper)

        form = QFormLayout()
        form.setHorizontalSpacing(max(10, int(12 * s)))
        form.setVerticalSpacing(max(10, int(12 * s)))

        self.input_code = QLineEdit(code)
        self.input_code.setStyleSheet(theme.input_style(s))
        self.input_code.setFixedHeight(max(34, int(40 * s)))

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setStyleSheet(theme.input_style(s))
        self.input_password.setFixedHeight(max(34, int(40 * s)))

        self.input_confirm = QLineEdit()
        self.input_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_confirm.setStyleSheet(theme.input_style(s))
        self.input_confirm.setFixedHeight(max(34, int(40 * s)))

        form.addRow("Codigo", self.input_code)
        form.addRow("Nova senha", self.input_password)
        form.addRow("Confirmar senha", self.input_confirm)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"color:{theme.DANGER}; background:#3b0f0f; border-radius:6px; padding:6px;"
        )
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_btn = QPushButton("CANCELAR")
        cancel_btn.setStyleSheet(theme.secondary_btn_style(s))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        confirm_btn = QPushButton("CONFIRMAR")
        confirm_btn.setStyleSheet(theme.primary_btn_style(s))
        confirm_btn.clicked.connect(self._validate_and_accept)
        buttons.addWidget(confirm_btn)
        layout.addLayout(buttons)

    def _validate_and_accept(self):
        code = self.input_code.text().strip()
        password = self.input_password.text().strip()
        confirm = self.input_confirm.text().strip()

        if not code or not password:
            self._show_error("Informe o codigo e a nova senha.")
            return
        if len(password) < 6:
            self._show_error("A senha precisa ter pelo menos 6 caracteres.")
            return
        if password != confirm:
            self._show_error("A confirmacao da senha nao confere.")
            return

        self.error_label.hide()
        self.accept()

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    def values(self) -> tuple[str, str]:
        return self.input_code.text().strip(), self.input_password.text().strip()


class LoginView(QWidget):
    login_success = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = res.scale
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            "background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1,"
            "stop:0 #0f1e3d, stop:1 #1B2B4B);"
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(max(340, int(410 * self.scale)))
        card.setStyleSheet("background:#fff; border-radius:16px; padding:8px;")
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

        logo_label = QLabel()
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            width = max(160, int(200 * self.scale))
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:{theme.PRIMARY}; font-size:{max(14, int(16 * self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(logo_label)

        title = QLabel("Sistema de Requisicoes")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(10, int(12 * self.scale))}pt;"
        )
        card_layout.addWidget(title)
        card_layout.addSpacing(max(4, int(8 * self.scale)))

        lbl_code = QLabel("Codigo de acesso")
        lbl_code.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * self.scale))}pt; font-weight:bold;"
        )
        card_layout.addWidget(lbl_code)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("Ex: 1")
        self.input_code.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_code.setStyleSheet(theme.input_style(self.scale))
        self.input_code.returnPressed.connect(self._do_login)
        card_layout.addWidget(self.input_code)

        lbl_pass = QLabel("Senha")
        lbl_pass.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * self.scale))}pt; font-weight:bold;"
        )
        card_layout.addWidget(lbl_pass)

        pass_row = QHBoxLayout()
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("••••••••")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_pass.setStyleSheet(theme.input_style(self.scale))
        self.input_pass.returnPressed.connect(self._do_login)

        self.btn_show = QPushButton("VER")
        self.btn_show.setFixedSize(max(52, int(60 * self.scale)), max(36, int(42 * self.scale)))
        self.btn_show.setCheckable(True)
        self.btn_show.setStyleSheet(
            f"QPushButton {{ background:{theme.INPUT_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:5px; color:{theme.TEXT_MEDIUM}; }}"
            f"QPushButton:checked {{ background:{theme.SIDEBAR_ACTIVE}; color:#fff; }}"
        )
        self.btn_show.toggled.connect(
            lambda checked: self.input_pass.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        pass_row.addWidget(self.input_pass)
        pass_row.addWidget(self.btn_show)
        card_layout.addLayout(pass_row)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet(
            f"color:{theme.DANGER}; font-size:{max(8, int(10 * self.scale))}pt; background:#3b0f0f;"
            f"border-radius:6px; padding:6px;"
        )
        self.error_label.hide()
        card_layout.addWidget(self.error_label)

        self.btn_login = QPushButton("ENTRAR")
        self.btn_login.setFixedHeight(max(40, int(46 * self.scale)))
        self.btn_login.setStyleSheet(theme.primary_btn_style(self.scale))
        self.btn_login.clicked.connect(self._do_login)
        card_layout.addWidget(self.btn_login)

        self.btn_first_access = QPushButton("PRIMEIRO ACESSO")
        self.btn_first_access.setFixedHeight(max(36, int(42 * self.scale)))
        self.btn_first_access.setStyleSheet(theme.secondary_btn_style(self.scale))
        self.btn_first_access.clicked.connect(self._open_first_access_dialog)
        card_layout.addWidget(self.btn_first_access)

        footer_card = QLabel("Ferragens Pinheiro | SIA e Taguatinga")
        footer_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_card.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(9 * self.scale))}pt;"
        )
        card_layout.addWidget(footer_card)

        outer.addWidget(card)

        footer = QLabel("pinheiroferragens.com.br")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color:{theme.TEXT_LABEL}; font-size:{max(7, int(9 * self.scale))}pt; margin-top:16px;"
        )
        outer.addWidget(footer)

    def _do_login(self):
        code = self.input_code.text().strip()
        password = self.input_pass.text()
        if not code or not password:
            self._show_error("Preencha o codigo e a senha.")
            return
        self._start_worker(LoginWorker(code, password), "Aguarde...")

    def _open_first_access_dialog(self):
        dialog = FirstAccessDialog(self.scale, self.input_code.text().strip(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        code, password = dialog.values()
        self.input_code.setText(code)
        self.input_pass.clear()
        self._start_worker(FirstAccessWorker(code, password), "Preparando acesso...")

    def _start_worker(self, worker: QObject, button_text: str):
        self._worker = worker
        self._thread = QThread()
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.success.connect(self._on_success)
        worker.error.connect(self._on_error)
        worker.finished.connect(self._thread.quit)
        worker.finished.connect(self._restore_buttons)
        worker.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

        self.btn_login.setEnabled(False)
        self.btn_first_access.setEnabled(False)
        self.btn_login.setText(button_text)
        self.error_label.hide()

    def _on_success(self, data: dict):
        session.login(data)
        self.login_success.emit()

    def _on_error(self, message: str):
        self._show_error(message)

    def _restore_buttons(self):
        self.btn_login.setEnabled(True)
        self.btn_first_access.setEnabled(True)
        self.btn_login.setText("ENTRAR")

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
