"""Tela de Feedbacks com categorias, status workflow e histórico do usuário."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.session import session
from ..widgets.smooth_scroll import apply_smooth_scroll

MAX_FEEDBACK_LEN = 1000

CATEGORY_OPTIONS = (
    ("🐛 Bug", "bug"),
    ("⚠️ Problema", "problema"),
    ("💡 Sugestão", "sugestao"),
    ("👍 Elogio", "elogio"),
)
CATEGORY_LABELS = {value: label for label, value in CATEGORY_OPTIONS}

STATUS_OPTIONS = (
    ("Nova",        "nova"),
    ("Em análise",  "em_analise"),
    ("Resolvida",   "resolvida"),
    ("Descartada",  "descartada"),
)
STATUS_LABELS = {value: label for label, value in STATUS_OPTIONS}

# Filtros (admin) — incluem opção "Todos"
CATEGORY_FILTER_OPTIONS = (("Todas as categorias", ""),) + CATEGORY_OPTIONS
STATUS_FILTER_OPTIONS   = (("Todos os status", ""),)     + STATUS_OPTIONS


def _rgba(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _status_color(status_value: str) -> str:
    return {
        "nova":       theme.PRIMARY_HOVER,
        "em_analise": theme.WARNING,
        "resolvida":  theme.SUCCESS,
        "descartada": theme.TEXT_MEDIUM,
    }.get(status_value, theme.BORDER_COLOR)


def _category_color(category_value: str) -> str:
    return {
        "bug":      theme.DANGER,
        "problema": theme.WARNING,
        "sugestao": theme.PRIMARY,
        "elogio":   theme.SUCCESS,
    }.get(category_value, theme.BORDER_COLOR)


def _fmt_datetime(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return text


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
        self._admin_rows: list[dict] = []
        self._admin_filtered: list[dict] = []
        self._mine_rows: list[dict] = []
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        s = self.scale
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.root_layout.setSpacing(10)

        self.title = QLabel("FEEDBACKS")
        self.root_layout.addWidget(self.title)

        self.subtitle = QLabel("Reporte bugs, problemas, sugestões e elogios para melhorar o sistema.")
        self.subtitle.setWordWrap(True)
        self.root_layout.addWidget(self.subtitle)

        # ── Card de envio ────────────────────────────────────────────────────
        self.compose_card = QFrame()
        self.compose_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        compose_lay = QVBoxLayout(self.compose_card)
        compose_lay.setContentsMargins(14, 14, 14, 14)
        compose_lay.setSpacing(8)

        self.compose_title = QLabel("Enviar feedback")
        compose_lay.addWidget(self.compose_title)

        # Linha da categoria
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)
        cat_lbl = QLabel("CATEGORIA")
        cat_lbl.setProperty("muted", "1")
        cat_lbl.setFixedWidth(max(80, int(95 * s)))
        cat_lbl.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        self.combo_category = QComboBox()
        self.combo_category.setFixedHeight(max(32, int(36 * s)))
        for label, value in CATEGORY_OPTIONS:
            self.combo_category.addItem(label, value)
        self.combo_category.setCurrentIndex(2)  # "Sugestão" default
        cat_row.addWidget(cat_lbl)
        cat_row.addWidget(self.combo_category, 1)
        compose_lay.addLayout(cat_row)

        # Textarea
        self.input_feedback = QTextEdit()
        self.input_feedback.setPlaceholderText("Descreva o feedback com detalhes — o que aconteceu, em qual tela, etc.")
        self.input_feedback.textChanged.connect(self._on_text_changed)
        self.input_feedback.setMinimumHeight(max(120, int(150 * s)))
        self.input_feedback.setMaximumHeight(max(180, int(220 * s)))
        compose_lay.addWidget(self.input_feedback)

        # Rodapé do card: contador + botão enviar
        bottom_row = QHBoxLayout()
        self.counter = QLabel(f"0/{MAX_FEEDBACK_LEN}")
        bottom_row.addWidget(self.counter)
        bottom_row.addStretch(1)
        self.btn_send = QPushButton("ENVIAR")
        self.btn_send.clicked.connect(self._send_feedback)
        bottom_row.addWidget(self.btn_send)
        compose_lay.addLayout(bottom_row)

        self.root_layout.addWidget(self.compose_card)

        # ── Card "Meus feedbacks" (visível pra todos os perfis) ──────────────
        self.mine_card = QFrame()
        mine_lay = QVBoxLayout(self.mine_card)
        mine_lay.setContentsMargins(14, 14, 14, 14)
        mine_lay.setSpacing(8)

        mine_header = QHBoxLayout()
        self.mine_title = QLabel("Meus feedbacks")
        mine_header.addWidget(self.mine_title)
        mine_header.addStretch(1)
        self.btn_refresh_mine = QPushButton("ATUALIZAR")
        self.btn_refresh_mine.clicked.connect(self._load_my_feedbacks)
        mine_header.addWidget(self.btn_refresh_mine)
        mine_lay.addLayout(mine_header)

        self.mine_table = QTableWidget(0, 4)
        self.mine_table.setHorizontalHeaderLabels(["CATEGORIA", "MENSAGEM", "STATUS", "ENVIADO EM"])
        self._setup_table(self.mine_table, stretch_col=1)
        mine_lay.addWidget(self.mine_table)

        self.root_layout.addWidget(self.mine_card, 1)

        # ── Card admin: caixa de entrada ─────────────────────────────────────
        self.admin_card = QFrame()
        admin_lay = QVBoxLayout(self.admin_card)
        admin_lay.setContentsMargins(14, 14, 14, 14)
        admin_lay.setSpacing(8)

        admin_header = QHBoxLayout()
        self.admin_title = QLabel("Caixa de entrada (admin)")
        admin_header.addWidget(self.admin_title)
        admin_header.addStretch(1)
        self.btn_refresh_admin = QPushButton("ATUALIZAR")
        self.btn_refresh_admin.clicked.connect(self._load_admin_feedbacks)
        admin_header.addWidget(self.btn_refresh_admin)
        admin_lay.addLayout(admin_header)

        # Filtros
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.combo_filter_cat = QComboBox()
        for label, value in CATEGORY_FILTER_OPTIONS:
            self.combo_filter_cat.addItem(label, value)
        self.combo_filter_cat.currentIndexChanged.connect(self._apply_admin_filters)

        self.combo_filter_status = QComboBox()
        for label, value in STATUS_FILTER_OPTIONS:
            self.combo_filter_status.addItem(label, value)
        self.combo_filter_status.currentIndexChanged.connect(self._apply_admin_filters)

        filters.addWidget(self.combo_filter_cat, 1)
        filters.addWidget(self.combo_filter_status, 1)
        filters.addStretch(2)
        admin_lay.addLayout(filters)

        # Tabela de feedbacks
        self.admin_table = QTableWidget(0, 6)
        self.admin_table.setHorizontalHeaderLabels(
            ["AUTOR", "CATEGORIA", "MENSAGEM", "STATUS", "ENVIADO EM", "RESOLVIDO POR"]
        )
        self._setup_table(self.admin_table, stretch_col=2)
        self.admin_table.itemSelectionChanged.connect(self._on_admin_selection_changed)
        admin_lay.addWidget(self.admin_table, 1)

        # Ações sobre o feedback selecionado
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_lbl = QLabel("MUDAR STATUS PARA:")
        action_lbl.setProperty("muted", "1")
        action_lbl.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        action_row.addWidget(action_lbl)

        self.combo_new_status = QComboBox()
        for label, value in STATUS_OPTIONS:
            self.combo_new_status.addItem(label, value)
        action_row.addWidget(self.combo_new_status, 1)

        self.btn_apply_status = QPushButton("APLICAR")
        self.btn_apply_status.clicked.connect(self._apply_status_change)
        action_row.addWidget(self.btn_apply_status)
        admin_lay.addLayout(action_row)

        self.root_layout.addWidget(self.admin_card, 1)

        self._apply_role_visibility()
        self.apply_theme()

    def _setup_table(self, table: QTableWidget, stretch_col: int):
        s = self.scale
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_smooth_scroll(table)
        head = table.horizontalHeader()
        for col in range(table.columnCount()):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col == stretch_col
                else QHeaderView.ResizeMode.ResizeToContents
            )
            head.setSectionResizeMode(col, mode)
        head.setMinimumHeight(max(32, int(38 * s)))
        table.verticalHeader().setDefaultSectionSize(max(30, int(36 * s)))
        table.setMinimumHeight(max(220, int(260 * s)))

    # ── Lógica ────────────────────────────────────────────────────────────────
    def _apply_role_visibility(self):
        is_admin = session.is_admin
        self.admin_card.setVisible(is_admin)
        self.btn_apply_status.setEnabled(False)
        self.combo_new_status.setEnabled(False)

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
            QMessageBox.warning(self, "Feedbacks", f"O limite é de {MAX_FEEDBACK_LEN} caracteres.")
            return

        category = self.combo_category.currentData() or "sugestao"
        self.btn_send.setEnabled(False)
        thread, worker = _run_in_thread(
            api.create_feedback,
            text, category,
            on_result=self._on_feedback_sent,
            on_error=self._on_feedback_send_error,
        )
        self._threads.append((thread, worker))

    def _on_feedback_sent(self, _data: dict):
        self.btn_send.setEnabled(True)
        self.input_feedback.clear()
        self.counter.setText(f"0/{MAX_FEEDBACK_LEN}")
        QMessageBox.information(self, "Feedbacks", "Feedback enviado com sucesso.")
        self._load_my_feedbacks()
        if session.is_admin:
            self._load_admin_feedbacks()

    def _on_feedback_send_error(self, msg: str):
        self.btn_send.setEnabled(True)
        QMessageBox.critical(self, "Feedbacks", msg)

    # ── Meus feedbacks ────────────────────────────────────────────────────────
    def _load_my_feedbacks(self):
        self.btn_refresh_mine.setEnabled(False)
        thread, worker = _run_in_thread(
            api.list_my_feedbacks,
            on_result=self._on_my_feedbacks_loaded,
            on_error=lambda msg: (
                self.btn_refresh_mine.setEnabled(True),
                QMessageBox.warning(self, "Feedbacks", msg),
            ),
        )
        self._threads.append((thread, worker))

    def _on_my_feedbacks_loaded(self, rows: list[dict]):
        self.btn_refresh_mine.setEnabled(True)
        self._mine_rows = [r for r in (rows or []) if isinstance(r, dict)]
        self._fill_mine_table()

    def _fill_mine_table(self):
        self.mine_table.setRowCount(0)
        for row in self._mine_rows:
            r = self.mine_table.rowCount()
            self.mine_table.insertRow(r)
            cat = str(row.get("category") or "sugestao")
            stt = str(row.get("status") or "nova")
            self.mine_table.setItem(r, 0, self._badge_item(CATEGORY_LABELS.get(cat, cat), _category_color(cat)))
            self.mine_table.setItem(r, 1, self._text_item(row.get("message"), left=True))
            self.mine_table.setItem(r, 2, self._badge_item(STATUS_LABELS.get(stt, stt), _status_color(stt)))
            self.mine_table.setItem(r, 3, self._text_item(_fmt_datetime(row.get("created_at"))))

    # ── Admin: caixa de entrada ───────────────────────────────────────────────
    def _load_admin_feedbacks(self):
        if not session.is_admin:
            return
        self.btn_refresh_admin.setEnabled(False)
        thread, worker = _run_in_thread(
            api.list_feedbacks,
            on_result=self._on_admin_feedbacks_loaded,
            on_error=lambda msg: (
                self.btn_refresh_admin.setEnabled(True),
                QMessageBox.warning(self, "Feedbacks", msg),
            ),
        )
        self._threads.append((thread, worker))

    def _on_admin_feedbacks_loaded(self, rows: list[dict]):
        self.btn_refresh_admin.setEnabled(True)
        self._admin_rows = [r for r in (rows or []) if isinstance(r, dict)]
        self._apply_admin_filters()

    def _apply_admin_filters(self):
        cat = self.combo_filter_cat.currentData() or ""
        stt = self.combo_filter_status.currentData() or ""
        self._admin_filtered = [
            r for r in self._admin_rows
            if (not cat or str(r.get("category") or "") == cat)
            and (not stt or str(r.get("status") or "") == stt)
        ]
        self._fill_admin_table()

    def _fill_admin_table(self):
        self.admin_table.setRowCount(0)
        for row in self._admin_filtered:
            r = self.admin_table.rowCount()
            self.admin_table.insertRow(r)
            cat = str(row.get("category") or "sugestao")
            stt = str(row.get("status") or "nova")
            self.admin_table.setItem(r, 0, self._text_item(row.get("user_name") or "-", left=True))
            self.admin_table.setItem(r, 1, self._badge_item(CATEGORY_LABELS.get(cat, cat), _category_color(cat)))
            self.admin_table.setItem(r, 2, self._text_item(row.get("message"), left=True))
            self.admin_table.setItem(r, 3, self._badge_item(STATUS_LABELS.get(stt, stt), _status_color(stt)))
            self.admin_table.setItem(r, 4, self._text_item(_fmt_datetime(row.get("created_at"))))
            self.admin_table.setItem(r, 5, self._text_item(row.get("read_by_name") or "-"))
        self.btn_apply_status.setEnabled(False)
        self.combo_new_status.setEnabled(False)

    def _on_admin_selection_changed(self):
        idx = self.admin_table.currentRow()
        ok = 0 <= idx < len(self._admin_filtered)
        self.combo_new_status.setEnabled(ok)
        self.btn_apply_status.setEnabled(ok)
        if ok:
            current_status = str(self._admin_filtered[idx].get("status") or "nova")
            i = self.combo_new_status.findData(current_status)
            if i >= 0:
                self.combo_new_status.setCurrentIndex(i)

    def _apply_status_change(self):
        idx = self.admin_table.currentRow()
        if not (0 <= idx < len(self._admin_filtered)):
            return
        row = self._admin_filtered[idx]
        fb_id = int(row.get("id") or 0)
        new_status = self.combo_new_status.currentData() or "nova"
        if not fb_id:
            return
        if str(row.get("status") or "") == new_status:
            QMessageBox.information(self, "Feedbacks", "O feedback já está nesse status.")
            return

        self.btn_apply_status.setEnabled(False)
        thread, worker = _run_in_thread(
            api.update_feedback_status,
            fb_id, new_status,
            on_result=lambda _r: self._on_status_change_done(),
            on_error=self._on_status_change_error,
        )
        self._threads.append((thread, worker))

    def _on_status_change_done(self):
        QMessageBox.information(
            self,
            "Feedbacks",
            "Status atualizado com sucesso. O autor recebeu uma notificação.",
        )
        self._load_admin_feedbacks()

    def _on_status_change_error(self, msg: str):
        QMessageBox.critical(self, "Feedbacks", msg)
        self.btn_apply_status.setEnabled(True)

    # ── Helpers de tabela ─────────────────────────────────────────────────────
    def _text_item(self, value: object, left: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(str(value or "-"))
        if left:
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _badge_item(self, text: str, color: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        bg = QColor(color)
        bg.setAlpha(30)
        item.setBackground(bg)
        return item

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    def refresh(self):
        self._apply_role_visibility()
        self._load_my_feedbacks()
        if session.is_admin:
            self._load_admin_feedbacks()

    def apply_theme(self):
        s = self.scale
        self.title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        self.subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * s))}pt;"
        )
        self.counter.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(10 * s))}pt;"
        )
        for lbl in (self.compose_title, self.mine_title, self.admin_title):
            lbl.setStyleSheet(
                f"background:transparent; border:none; color:{theme.TEXT_DARK};"
                f"font-size:{max(10, int(12 * s))}pt; font-weight:700;"
            )

        self.compose_card.setStyleSheet(theme.card_style())
        self.mine_card.setStyleSheet(theme.card_style())
        self.admin_card.setStyleSheet(theme.card_style())
        self.input_feedback.setStyleSheet(theme.input_style(s))
        self.combo_category.setStyleSheet(theme.input_style(s))
        self.combo_filter_cat.setStyleSheet(theme.input_style(s))
        self.combo_filter_status.setStyleSheet(theme.input_style(s))
        self.combo_new_status.setStyleSheet(theme.input_style(s))
        self.btn_send.setStyleSheet(theme.primary_btn_style(s))
        self.btn_apply_status.setStyleSheet(theme.primary_btn_style(s))
        self.btn_refresh_mine.setStyleSheet(theme.secondary_btn_style(s))
        self.btn_refresh_admin.setStyleSheet(theme.secondary_btn_style(s))

        for tbl in (self.mine_table, self.admin_table):
            tbl.setStyleSheet(
                f"QTableWidget {{"
                f"  border:none; outline:none; background:{theme.CARD_BG};"
                f"  alternate-background-color:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK};"
                f"  border-radius:10px; gridline-color:transparent;"
                f"  font-size:{max(8, int(9 * s))}pt;"
                f"}}"
                f"QHeaderView::section {{"
                f"  background:{theme.PRIMARY}; color:#fff; padding:7px 10px;"
                f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
                f"}}"
                f"QTableWidget::item {{"
                f"  padding:6px 8px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
                f"}}"
                f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
            )
            pal = tbl.palette()
            pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
            tbl.setPalette(pal)
