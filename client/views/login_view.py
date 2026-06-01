import os

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
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
from ..core import login_backgrounds
from ..core.resolution import res
from ..core.session import session

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_login.png")


def _login_input_style(scale: float) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QLineEdit {{"
        f"  background:{theme.SURFACE_SOFT}; color:{theme.TEXT_DARK};"
        f"  border:none; outline:none; border-radius:8px;"
        f"  padding:8px 12px; font-size:{fs}pt;"
        f"  selection-background-color:{theme.SELECTION_BG}; selection-color:{theme.TEXT_DARK};"
        f"}}"
        f"QLineEdit:focus {{ border:none; outline:none; }}"
    )


def _login_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.SURFACE_SOFT}; color:{theme.PRIMARY};"
        f"  border:none; outline:none; border-radius:8px;"
        f"  padding:8px 16px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.SELECTION_BG}; }}"
        f"QPushButton:pressed {{ background:#CFE0FF; }}"
    )


def _login_toggle_btn_style(scale: float) -> str:
    fs = max(8, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.SURFACE_SOFT}; color:{theme.PRIMARY};"
        f"  border:none; outline:none; border-radius:8px;"
        f"  font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.SELECTION_BG}; }}"
        f"QPushButton:checked {{ background:{theme.PRIMARY_HOVER}; color:{theme.TEXT_WHITE}; }}"
    )


class LoginWorker(QObject):
    success = Signal(dict)
    error = Signal(str)
    first_access_required = Signal(str)
    finished = Signal()

    def __init__(self, code: str, password: str):
        super().__init__()
        self.code = code
        self.password = password

    def run(self):
        try:
            self.success.emit(api.login(self.code, self.password))
        except api.APIError as exc:
            detail = str(exc.detail)
            if exc.status_code == 403 and "Primeiro acesso pendente" in detail:
                self.first_access_required.emit(self.code)
            else:
                self.error.emit(detail)
        except Exception as exc:
            self.error.emit(f"Sem conexão com o servidor.\n{exc}")
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
            self.error.emit(f"Sem conexão com o servidor.\n{exc}")
        finally:
            self.finished.emit()


class FirstAccessStatusWorker(QObject):
    pending = Signal(str)
    finished = Signal()

    def __init__(self, code: str):
        super().__init__()
        self.code = code

    def run(self):
        try:
            result = api.get_first_access_status(self.code)
            if bool(result.get("first_access_required")):
                self.pending.emit(self.code)
        except Exception:
            pass
        finally:
            self.finished.emit()


class FirstAccessDialog(QDialog):
    def __init__(self, scale: float, code: str = "", parent=None):
        super().__init__(parent)
        self.scale = scale
        self.setWindowTitle("Primeiro acesso")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QDialog {{"
            f"  background-color:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"}}"
            f"QDialog QWidget {{ background-color:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background-color:transparent; }}"
        )
        self._setup_ui(code)

    def _setup_ui(self, code: str):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(18, int(22 * s)), max(18, int(22 * s)),
                                  max(18, int(22 * s)), max(18, int(22 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        title = QLabel("PRIMEIRO ACESSO")
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(12, int(14 * s))}pt; font-weight:bold;"
        )
        helper = QLabel(
            "Informe seu código e cadastre uma senha para entrar no sistema."
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
        self.input_code.returnPressed.connect(self._validate_and_accept)
        self.input_password.returnPressed.connect(self._validate_and_accept)
        self.input_confirm.returnPressed.connect(self._validate_and_accept)

        form.addRow("Código", self.input_code)
        form.addRow("Nova senha", self.input_password)
        form.addRow("Confirmar senha", self.input_confirm)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"color:{theme.DANGER}; background-color:#FDEEEF; border:1px solid #F4C7CC; border-radius:8px; padding:8px;"
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
            self._show_error("Informe o código e a nova senha.")
            return
        if len(password) < 6:
            self._show_error("A senha precisa ter pelo menos 6 caracteres.")
            return
        if password.casefold() != confirm.casefold():
            self._show_error("A confirmação da senha não confere.")
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
        self._status_threads: list[tuple[QThread, QObject]] = []
        self._auto_prompted_codes: set[str] = set()
        self._pending_first_access_code: str | None = None
        # background sazonal
        self._bg_path:  str | None    = login_backgrounds.get_active_background()
        self._bg_cache: QPixmap | None = None
        # garantir que paintEvent() cubra o widget inteiro (sem flicker)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._setup_ui()

    def _setup_ui(self):
        # fundo é pintado no paintEvent; sem stylesheet de background aqui
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(max(340, int(410 * self.scale)))
        card.setStyleSheet(
            f"background:{theme.CARD_BG}; border:none; outline:none; border-radius:8px; padding:8px;"
        )

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
            width = max(180, int(228 * self.scale))
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        else:
            logo_label.setText("PINHEIRO FERRAGENS")
            logo_label.setStyleSheet(
                f"color:{theme.PRIMARY}; font-size:{max(14, int(16 * self.scale))}pt; font-weight:bold;"
            )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(logo_label)

        title = QLabel("Sistema de Requisições")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(10, int(12 * self.scale))}pt; font-weight:600;"
        )
        card_layout.addWidget(title)
        card_layout.addSpacing(max(4, int(8 * self.scale)))

        lbl_code = QLabel("CODIGO DE ACESSO")
        lbl_code.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(9, int(11 * self.scale))}pt; font-weight:700;"
        )
        card_layout.addWidget(lbl_code)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("Ex: 1")
        self.input_code.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_code.setStyleSheet(_login_input_style(self.scale))
        self.input_code.returnPressed.connect(self._focus_password_from_code)
        self.input_code.editingFinished.connect(self._check_first_access_for_code)
        card_layout.addWidget(self.input_code)

        lbl_pass = QLabel("SENHA")
        lbl_pass.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(9, int(11 * self.scale))}pt; font-weight:700;"
        )
        card_layout.addWidget(lbl_pass)

        pass_row = QHBoxLayout()
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("••••••••")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setFixedHeight(max(36, int(42 * self.scale)))
        self.input_pass.setStyleSheet(_login_input_style(self.scale))
        self.input_pass.returnPressed.connect(self._do_login)

        self.btn_show = QPushButton("VER")
        self.btn_show.setFixedSize(max(52, int(60 * self.scale)), max(36, int(42 * self.scale)))
        self.btn_show.setCheckable(True)
        self.btn_show.setStyleSheet(_login_toggle_btn_style(self.scale))
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
            f"color:{theme.DANGER}; font-size:{max(8, int(10 * self.scale))}pt; background:#FDEEEF;"
            f"border:none; border-radius:8px; padding:8px;"
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
        self.btn_first_access.setStyleSheet(_login_secondary_btn_style(self.scale))
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
            f"color:{theme.TEXT_WHITE}; font-size:{max(7, int(9 * self.scale))}pt; margin-top:18px; font-weight:600;"
        )
        outer.addWidget(footer)

    # ── Fundo sazonal ────────────────────────────────────────────────────────

    def fade_in(self, duration: int = 260) -> None:
        """Anima windowOpacity 0 → 1 para entrada suave (troca de usuário)."""
        self._fade_in_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in_anim.setDuration(duration)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in_anim.start()

    def reload_background(self) -> None:
        """Recarrega a campanha ativa (chamada após salvar configurações)."""
        self._bg_path = login_backgrounds.get_active_background()
        self._bg_cache = None
        self._update_bg_cache()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_bg_cache()

    def _update_bg_cache(self) -> None:
        """Redimensiona a imagem de fundo para cobrir o widget (cover)."""
        if self._bg_path and os.path.isfile(self._bg_path):
            pix = QPixmap(self._bg_path)
            if not pix.isNull():
                self._bg_cache = pix.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                return
        self._bg_cache = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._bg_cache and not self._bg_cache.isNull():
            # centraliza (KeepAspectRatioByExpanding pode exceder o tamanho)
            x = (self.width()  - self._bg_cache.width())  // 2
            y = (self.height() - self._bg_cache.height()) // 2
            painter.drawPixmap(x, y, self._bg_cache)
        else:
            painter.fillRect(self.rect(), QColor(theme.PRIMARY))
        painter.end()

    # ── Login ─────────────────────────────────────────────────────────────────

    def _focus_password_from_code(self):
        # Enter no código apenas avança para a senha; não tenta autenticar.
        self.error_label.hide()
        self.input_pass.setFocus()
        self.input_pass.selectAll()

    def _do_login(self):
        code = self.input_code.text().strip()
        password = self.input_pass.text()
        if not code or not password:
            self._show_error("Preencha o código e a senha.")
            return
        self._start_worker(LoginWorker(code, password), "Aguarde...")

    def _open_first_access_dialog(self, code: str | None = None):
        dialog = FirstAccessDialog(self.scale, code or self.input_code.text().strip(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        code, password = dialog.values()
        self.input_code.setText(code)
        self.input_pass.clear()
        self._start_worker(FirstAccessWorker(code, password), "Preparando acesso...")

    def _check_first_access_for_code(self):
        code = self.input_code.text().strip()
        if not code or code in self._auto_prompted_codes:
            return

        worker = FirstAccessStatusWorker(code)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.pending.connect(self._on_first_access_required)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_status_thread(t, w))
        thread.start()
        self._status_threads.append((thread, worker))

    def _cleanup_status_thread(self, thread: QThread, worker: QObject):
        self._status_threads = [pair for pair in self._status_threads if pair != (thread, worker)]

    def _start_worker(self, worker: QObject, button_text: str):
        self._worker = worker
        self._thread = QThread()
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.success.connect(self._on_success)
        worker.error.connect(self._on_error)
        if isinstance(worker, LoginWorker):
            worker.first_access_required.connect(self._on_first_access_required_from_login)
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

    def _on_first_access_required(self, code: str):
        code = (code or "").strip()
        if not code or code in self._auto_prompted_codes:
            return
        self._auto_prompted_codes.add(code)
        self._open_first_access_dialog(code)

    def _on_first_access_required_from_login(self, code: str):
        code = (code or "").strip()
        if not code:
            return
        self._auto_prompted_codes.add(code)
        self._pending_first_access_code = code

    def _restore_buttons(self):
        self.btn_login.setEnabled(True)
        self.btn_first_access.setEnabled(True)
        self.btn_login.setText("ENTRAR")
        if self._pending_first_access_code:
            code = self._pending_first_access_code
            self._pending_first_access_code = None
            self._open_first_access_dialog(code)

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
