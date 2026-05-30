from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ..api import client as api
from ..core import theme
from ..core.session import session
from ..widgets.smooth_scroll import apply_smooth_scroll

MAX_FEEDBACK_LEN = 150


class _ApiWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _Callback(QObject):
    result = Signal(object)
    error = Signal(str)


def _run_in_thread(fn, *args, on_result=None, on_error=None, **kwargs):
    worker = _ApiWorker(fn, *args, **kwargs)
    thread = QThread()
    cb = _Callback()

    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.result.connect(cb.result)
    worker.error.connect(cb.error)
    worker.finished.connect(thread.quit)

    if on_result:
        cb.result.connect(on_result)
    if on_error:
        cb.error.connect(on_error)

    worker._cb = cb
    thread.start()
    return thread, worker


class FeedbackView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, object]] = []
        self._admin_feedback_rows: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.root_layout.setSpacing(10)

        self.title = QLabel("FEEDBACKS")
        self.root_layout.addWidget(self.title)

        self.subtitle = QLabel("Problemas, elogios, bugs e sugestoes.")
        self.subtitle.setWordWrap(True)
        self.root_layout.addWidget(self.subtitle)

        self.compose_card = QFrame()
        self.compose_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        compose_layout = QVBoxLayout(self.compose_card)
        compose_layout.setContentsMargins(12, 12, 12, 12)
        compose_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)

        self.compose_title = QLabel("Enviar feedback")
        self.compose_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.compose_title.setFixedHeight(max(18, int(22 * self.scale)))
        self.compose_title.setFixedWidth(max(120, int(145 * self.scale)))
        self.compose_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.compose_title)
        title_row.addStretch(1)
        compose_layout.addLayout(title_row)

        self.input_feedback = QTextEdit()
        self.input_feedback.setPlaceholderText("Digite aqui seu feedback...")
        self.input_feedback.textChanged.connect(self._on_text_changed)
        compose_layout.addWidget(self.input_feedback)

        bottom_row = QHBoxLayout()
        self.counter = QLabel(f"0/{MAX_FEEDBACK_LEN}")
        self.btn_send = QPushButton("ENVIAR")
        self.btn_send.clicked.connect(self._send_feedback)
        bottom_row.addWidget(self.counter)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.btn_send)
        compose_layout.addLayout(bottom_row)

        self.root_layout.addWidget(self.compose_card)

        self.admin_card = QFrame()
        admin_layout = QVBoxLayout(self.admin_card)
        admin_layout.setContentsMargins(12, 12, 12, 12)
        admin_layout.setSpacing(8)

        admin_title_row = QHBoxLayout()
        admin_title_row.setContentsMargins(0, 0, 0, 0)
        admin_title_row.setSpacing(0)

        self.admin_title = QLabel("Mensagens recebidas")
        self.admin_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.admin_title.setFixedHeight(max(18, int(22 * self.scale)))
        self.admin_title.setFixedWidth(max(160, int(190 * self.scale)))
        self.admin_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        admin_title_row.addWidget(self.admin_title)
        admin_title_row.addStretch(1)
        admin_layout.addLayout(admin_title_row)

        self.feedback_list = QListWidget()
        apply_smooth_scroll(self.feedback_list)
        self.feedback_list.setWordWrap(True)
        self.feedback_list.setUniformItemSizes(False)
        self.feedback_list.currentRowChanged.connect(self._on_admin_selection_changed)
        self.feedback_list.setMinimumHeight(max(180, int(230 * self.scale)))
        admin_layout.addWidget(self.feedback_list)

        admin_actions = QHBoxLayout()
        admin_actions.addStretch(1)
        self.btn_ack = QPushButton("CONFIRMAR LEITURA")
        self.btn_ack.clicked.connect(self._ack_selected_feedback)
        admin_actions.addWidget(self.btn_ack)
        admin_layout.addLayout(admin_actions)

        self.root_layout.addWidget(self.admin_card, 1)
        self.root_layout.addStretch(1)
        self._apply_role_visibility()
        self._apply_compose_profile_layout()
        self.apply_theme()

    def _apply_role_visibility(self):
        is_admin = session.is_admin
        self.admin_card.setVisible(is_admin)
        self.root_layout.setStretchFactor(self.admin_card, 1 if is_admin else 0)
        self.btn_ack.setEnabled(False)

    def _apply_compose_profile_layout(self):
        """
        Mantém o formulário de envio no mesmo padrão visual para todos os perfis.
        Apenas a lista de mensagens é exclusiva do administrador.
        """
        min_h = max(110, int(140 * self.scale))
        max_h = max(150, int(170 * self.scale))
        card_max_w = 1200

        self.input_feedback.setMinimumHeight(min_h)
        self.input_feedback.setMaximumHeight(max_h)
        self.compose_card.setMaximumWidth(card_max_w)

    def _on_text_changed(self):
        text = self.input_feedback.toPlainText()
        if len(text) > MAX_FEEDBACK_LEN:
            trimmed = text[:MAX_FEEDBACK_LEN]
            cursor = self.input_feedback.textCursor()
            pos = min(cursor.position(), MAX_FEEDBACK_LEN)
            self.input_feedback.blockSignals(True)
            self.input_feedback.setPlainText(trimmed)
            cursor.setPosition(pos)
            self.input_feedback.setTextCursor(cursor)
            self.input_feedback.blockSignals(False)
            text = trimmed
        self.counter.setText(f"{len(text)}/{MAX_FEEDBACK_LEN}")

    def _send_feedback(self):
        text = self.input_feedback.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Feedbacks", "Escreva uma mensagem antes de enviar.")
            return
        if len(text) > MAX_FEEDBACK_LEN:
            QMessageBox.warning(self, "Feedbacks", f"O limite e de {MAX_FEEDBACK_LEN} caracteres.")
            return

        self.btn_send.setEnabled(False)
        thread, worker = _run_in_thread(
            api.create_feedback,
            text,
            on_result=self._on_feedback_sent,
            on_error=self._on_feedback_send_error,
        )
        self._threads.append((thread, worker))

    def _on_feedback_sent(self, _data: dict):
        self.btn_send.setEnabled(True)
        self.input_feedback.clear()
        self.counter.setText(f"0/{MAX_FEEDBACK_LEN}")
        QMessageBox.information(self, "Feedbacks", "Feedback enviado com sucesso.")
        if session.is_admin:
            self._load_admin_feedbacks()

    def _on_feedback_send_error(self, msg: str):
        self.btn_send.setEnabled(True)
        QMessageBox.critical(self, "Feedbacks", msg)

    def _load_admin_feedbacks(self):
        if not session.is_admin:
            return
        thread, worker = _run_in_thread(
            api.list_feedbacks,
            on_result=self._on_admin_feedbacks_loaded,
            on_error=lambda msg: QMessageBox.warning(self, "Feedbacks", msg),
        )
        self._threads.append((thread, worker))

    def _on_admin_feedbacks_loaded(self, rows: list[dict]):
        self._admin_feedback_rows = list(rows or [])
        self.feedback_list.clear()
        self.btn_ack.setEnabled(False)

        for row in self._admin_feedback_rows:
            sender = str(row.get("user_name") or f"Usuario #{row.get('user_id')}")
            created_at = str(row.get("created_at") or "")
            when = created_at
            try:
                when = datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass
            message = str(row.get("message") or "").strip()
            item = QListWidgetItem(f"{when} • {sender}\n{message}")
            self.feedback_list.addItem(item)

    def _on_admin_selection_changed(self, row_index: int):
        if row_index < 0 or row_index >= len(self._admin_feedback_rows):
            self.btn_ack.setEnabled(False)
            return
        row = self._admin_feedback_rows[row_index]
        self.btn_ack.setEnabled(not bool(row.get("read_at")))

    def _ack_selected_feedback(self):
        idx = self.feedback_list.currentRow()
        if idx < 0 or idx >= len(self._admin_feedback_rows):
            QMessageBox.information(self, "Feedbacks", "Selecione uma mensagem primeiro.")
            return
        row = self._admin_feedback_rows[idx]
        fb_id = int(row.get("id") or 0)
        if not fb_id:
            return

        self.btn_ack.setEnabled(False)
        thread, worker = _run_in_thread(
            api.acknowledge_feedback,
            fb_id,
            on_result=lambda _r: self._on_feedback_ack_done(),
            on_error=self._on_feedback_ack_error,
        )
        self._threads.append((thread, worker))

    def _on_feedback_ack_done(self):
        QMessageBox.information(
            self,
            "Feedbacks",
            "Leitura confirmada. O autor recebeu notificacao de que esta em processo de correcao.",
        )
        self._load_admin_feedbacks()

    def _on_feedback_ack_error(self, msg: str):
        QMessageBox.critical(self, "Feedbacks", msg)
        self.btn_ack.setEnabled(True)

    def refresh(self):
        self._apply_role_visibility()
        self._apply_compose_profile_layout()
        if session.is_admin:
            self._load_admin_feedbacks()

    def apply_theme(self):
        self.title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(18, int(24 * self.scale))}pt; font-weight:800;"
        )
        self.subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * self.scale))}pt;"
        )
        self.counter.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(10 * self.scale))}pt;"
        )
        self.compose_title.setStyleSheet(
            f"background:transparent; border:none; color:{theme.TEXT_DARK};"
            f"font-size:{max(9, int(11 * self.scale))}pt; font-weight:600;"
        )
        self.admin_title.setStyleSheet(
            f"background:transparent; border:none; color:{theme.TEXT_DARK};"
            f"font-size:{max(9, int(11 * self.scale))}pt; font-weight:600;"
        )

        self.compose_card.setStyleSheet(theme.card_style())
        self.admin_card.setStyleSheet(theme.card_style())
        self.input_feedback.setStyleSheet(theme.input_style(self.scale))
        self.feedback_list.setStyleSheet(
            f"QListWidget {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"}}"
            f"QListWidget::item {{ padding:10px 10px; border-bottom:1px solid {theme.BORDER_COLOR}; }}"
            f"QListWidget::item:selected {{ background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK}; }}"
        )
        self.btn_send.setStyleSheet(theme.primary_btn_style(self.scale))
        self.btn_ack.setStyleSheet(theme.primary_btn_style(self.scale))
