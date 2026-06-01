"""
Formulário principal de requisição — fiel ao mockup fornecido.
"""
import os
import io
import base64
import shutil
import tempfile
import unicodedata
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QCheckBox,
    QFrame, QSplitter, QTextEdit, QFileDialog, QMessageBox, QDialog,
    QGraphicsDropShadowEffect, QSizePolicy, QGraphicsScene, QGraphicsView,
    QListWidget, QListWidgetItem, QStyle, QApplication, QAbstractItemView, QPlainTextEdit,
    QAbstractSpinBox, QToolButton, QDateTimeEdit, QTableWidget, QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import (
    Qt, QDate, Signal, QThread, QObject, QEvent, QTimer, QRegularExpression,
    QRectF, QSize, QPointF, QByteArray, QBuffer, QIODevice,
)
from PySide6.QtGui import (
    QAction, QKeySequence, QPixmap, QColor, QFont, QRegularExpressionValidator,
    QPainter, QImage, QPen,
)

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..core.datetime_utils import local_now
from ..core.dialogs import apply_message_box_theme, ask_confirmation
from ..core.resolution import res
from ..core.session import session
from ..core.text_case import bind_uppercase_line_edit, bind_uppercase_text_edit
from ..api import client as api
from ..widgets.status_badge import StatusBadge
from ..widgets.item_table import ItemTable
from ..widgets.canvas_widget import DrawingCanvas, CanvasPreview, load_canvas_scene, Tool

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_SEND = "ENVIADA"
ALL_DATES_SENTINEL = QDate(2000, 1, 1)
_REQ_CARD_BG_START = theme.PANEL_CARD_BG_START
_REQ_CARD_BG_MID = theme.PANEL_CARD_BG_MID
_REQ_CARD_BG_END = theme.PANEL_CARD_BG_END
_REQ_SURFACE_BG = theme.PANEL_SURFACE_BG
_REQ_SURFACE_ALT = theme.PANEL_SURFACE_ALT
_REQ_BORDER_SOFT = theme.PANEL_BORDER_SOFT
_REQ_TEXT_PRIMARY = theme.PANEL_TEXT_PRIMARY
_REQ_TEXT_MUTED = theme.PANEL_TEXT_MUTED
_REQ_NEON_PRIMARY = theme.PANEL_NEON_PRIMARY
_REQ_NEON_SECONDARY = theme.PANEL_NEON_SECONDARY
_REQ_NEON_TERTIARY = theme.PANEL_NEON_TERTIARY
_REQ_TABLE_HEADER_START = theme.PANEL_TABLE_HEADER_START
_REQ_TABLE_HEADER_END = theme.PANEL_TABLE_HEADER_END


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _req_dialog_style() -> str:
    return (
        f"QDialog {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {_REQ_CARD_BG_START}, stop:0.55 {_REQ_CARD_BG_MID}, stop:1 {_REQ_CARD_BG_END});"
        f"  color:{_REQ_TEXT_PRIMARY}; border:1px solid {_rgba(_REQ_NEON_PRIMARY, 92)}; border-radius:16px;"
        f"}}"
        f"QDialog QWidget {{ color:{_REQ_TEXT_PRIMARY}; }}"
        f"QLabel {{ background:transparent; color:{_REQ_TEXT_PRIMARY}; border:none; }}"
    )


# ── Worker genérico ───────────────────────────────────────────────────────────
class ApiWorker(QObject):
    result   = Signal(object)
    error    = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except api.APIError as e:
            self.error.emit(e.detail)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _Callback(QObject):
    """
    Intermediário criado na thread principal.
    Quando o worker (outra thread) emite result/error, Qt detecta
    a diferença de threads e usa QueuedConnection automaticamente,
    garantindo que os callbacks rodem sempre na thread principal.
    """
    result = Signal(object)
    error  = Signal(str)


def _run_in_thread(fn, *args, on_result=None, on_error=None, **kwargs):
    worker = ApiWorker(fn, *args, **kwargs)
    thread = QThread()

    # _Callback criado aqui (main thread) → tem afinidade com a main thread
    cb = _Callback()

    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    # worker → cb: cross-thread, Qt usa QueuedConnection automaticamente
    worker.result.connect(cb.result)
    worker.error.connect(cb.error)
    worker.finished.connect(thread.quit)

    # cb → callbacks do usuário: cb vive na main thread → roda na main thread
    if on_result:
        cb.result.connect(on_result)
    if on_error:
        cb.error.connect(on_error)

    # Guarda cb no worker para não ser coletado pelo GC antes do término
    worker._cb = cb

    thread.start()
    return thread, worker


def _build_production_note(action: str, destination: str) -> str:
    return f"{PROD_NOTE_PREFIX}|{action}|{destination}"


def _format_phone_text(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    digits = digits[-11:]
    if not digits:
        return ""
    if len(digits) <= 2:
        return f"({digits}"
    formatted = f"({digits[:2]})"
    if len(digits) >= 3:
        formatted += f" {digits[2]}"
    if len(digits) >= 4:
        formatted += f" {digits[3:7]}"
    if len(digits) >= 8:
        formatted += f"-{digits[7:11]}"
    return formatted


def _emphasized_btn_style(base_style: str) -> str:
    return base_style + "QPushButton { font-weight:700; }"


def _req_primary_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{_REQ_NEON_PRIMARY}; color:#04111F; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:800;"
        f"}}"
        f"QPushButton:hover {{ background:#67E8F9; }}"
        f"QPushButton:pressed {{ background:#06B6D4; color:#021019; }}"
        f"QPushButton:disabled {{ background:#164E63; color:#CFFAFE; }}"
    )


def _req_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{_REQ_SURFACE_BG}; color:{_REQ_TEXT_PRIMARY};"
        f"  border:1px solid {_rgba(_REQ_NEON_PRIMARY, 110)}; outline:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{_REQ_SURFACE_ALT}; border-color:{_REQ_NEON_SECONDARY}; }}"
        f"QPushButton:pressed {{ background:{_rgba(_REQ_NEON_PRIMARY, 26)}; }}"
        f"QPushButton:disabled {{ background:{_rgba(_REQ_BORDER_SOFT, 36)}; color:{_REQ_TEXT_MUTED}; border-color:{_REQ_BORDER_SOFT}; }}"
    )


def _req_input_style(scale: float, *, bold: bool = False, accent: str | None = None) -> str:
    fs = max(9, int(10 * scale))
    radius = max(10, int(12 * scale))
    border = accent or _REQ_BORDER_SOFT
    weight = 700 if bold else 600
    return (
        f"QLineEdit, QDateEdit, QComboBox {{"
        f"  background:{_REQ_SURFACE_BG}; color:{_REQ_TEXT_PRIMARY};"
        f"  border:1px solid {border}; border-radius:{radius}px;"
        f"  padding:7px 10px; font-size:{fs}pt; font-weight:{weight};"
        f"  selection-background-color:{_rgba(_REQ_NEON_PRIMARY, 64)}; selection-color:{_REQ_TEXT_PRIMARY};"
        f"}}"
        f"QLineEdit:hover, QDateEdit:hover, QComboBox:hover {{ border-color:{_REQ_NEON_PRIMARY}; }}"
        f"QLineEdit:focus, QDateEdit:focus, QComboBox:focus {{ border-color:{_REQ_NEON_SECONDARY}; }}"
    )


def _req_text_edit_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QTextEdit, QPlainTextEdit {{"
        f"  background:{_REQ_SURFACE_BG}; color:{_REQ_TEXT_PRIMARY};"
        f"  border:1px solid {_REQ_BORDER_SOFT}; border-radius:10px;"
        f"  padding:6px 8px; font-size:{fs}pt;"
        f"  selection-background-color:{_rgba(_REQ_NEON_PRIMARY, 64)}; selection-color:{_REQ_TEXT_PRIMARY};"
        f"}}"
        f"QTextEdit:hover, QPlainTextEdit:hover {{ border-color:{_REQ_NEON_PRIMARY}; }}"
        f"QTextEdit:focus, QPlainTextEdit:focus {{ border-color:{_REQ_NEON_SECONDARY}; }}"
    )


def _req_checkbox_style(scale: float) -> str:
    fs = max(9, int(11 * scale))
    size = max(16, int(18 * scale))
    return (
        f"QCheckBox {{ color:{_REQ_TEXT_PRIMARY}; font-size:{fs}pt; border:none; spacing:8px; }}"
        f"QCheckBox::indicator {{"
        f"  width:{size}px; height:{size}px; border-radius:5px;"
        f"  border:1px solid {_rgba(_REQ_NEON_PRIMARY, 110)}; background:{_REQ_SURFACE_BG};"
        f"}}"
        f"QCheckBox::indicator:checked {{"
        f"  background:{_REQ_NEON_PRIMARY}; border-color:{_REQ_NEON_PRIMARY};"
        f"}}"
    )


def _req_search_drop_style(scale: float) -> str:
    return (
        f"QListWidget {{"
        f"  background:{_REQ_SURFACE_BG};"
        f"  border:2px solid {_REQ_NEON_PRIMARY}; border-radius:0 0 8px 8px;"
        f"  font-size:{max(9,int(10*scale))}pt; outline:none;"
        f"}}"
        f"QListWidget::item {{ padding:7px 12px; color:{_REQ_TEXT_PRIMARY}; }}"
        f"QListWidget::item:hover, QListWidget::item:selected"
        f" {{ background:{_rgba(_REQ_NEON_PRIMARY, 64)}; color:{_REQ_TEXT_PRIMARY}; }}"
    )


def _req_round_icon_btn_style(scale: float, diameter: int) -> str:
    return (
        f"QPushButton {{"
        f"  font-size:{max(10, int(11 * scale))}pt; font-weight:700;"
        f"  color:{_REQ_TEXT_MUTED}; background:{_REQ_SURFACE_BG};"
        f"  border:1px solid {_rgba(_REQ_NEON_PRIMARY, 102)};"
        f"  border-radius:{diameter // 2}px; padding:0;"
        f"}}"
        f"QPushButton:hover {{ color:{_REQ_TEXT_PRIMARY}; border-color:{_REQ_NEON_SECONDARY}; background:{_REQ_SURFACE_ALT}; }}"
        f"QPushButton:pressed {{ background:{_rgba(_REQ_NEON_PRIMARY, 24)}; }}"
    )


def _calendar_btn_style(scale: float) -> str:
    fs = max(11, int(13 * scale))
    return (
        f"QToolButton {{"
        f"  background:{_REQ_NEON_PRIMARY}; color:#04111F; border:none; border-radius:12px;"
        f"  font-size:{fs}pt; font-weight:700; padding:0px 2px;"
        f"}}"
        f"QToolButton:hover {{ background:#67E8F9; }}"
        f"QToolButton:pressed {{ background:#06B6D4; }}"
    )


def _dialog_table_style(scale: float) -> str:
    body_fs = max(8, int(9 * scale))
    head_fs = max(7, int(8 * scale))
    return (
        f"QTableWidget {{"
        f"  background:{_REQ_SURFACE_BG}; color:{_REQ_TEXT_PRIMARY};"
        f"  border:1px solid {_REQ_BORDER_SOFT}; border-radius:8px;"
        f"  alternate-background-color:{_REQ_SURFACE_ALT};"
        f"  font-size:{body_fs}pt; gridline-color:transparent;"
        f"}}"
        f"QTableWidget::item {{ padding:8px 10px; border:none; }}"
        f"QTableWidget::item:selected {{ background:{_rgba(_REQ_NEON_PRIMARY, 56)}; color:{_REQ_TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {_REQ_TABLE_HEADER_START}, stop:1 {_REQ_TABLE_HEADER_END});"
        f"  color:{_REQ_TEXT_PRIMARY};"
        f"  border:none; padding:8px 10px; font-size:{head_fs}pt; font-weight:700;"
        f"}}"
        f"QTableCornerButton::section {{ background:{_REQ_TABLE_HEADER_START}; border:none; }}"
    )


class PeriodDateEdit(QDateEdit):
    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        QTimer.singleShot(0, self._prioritize_day_section)
        QTimer.singleShot(0, self._select_all_text)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        QTimer.singleShot(0, self._prioritize_day_section)
        QTimer.singleShot(0, self._select_all_text)

    def stepBy(self, steps: int) -> None:
        self._prioritize_day_section()
        super().stepBy(steps)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.setDate(self.minimumDate())
            self._prioritize_day_section()
            self._select_all_text()
            return
        if event.modifiers() in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.ShiftModifier,
        ):
            key_text = (event.text() or "").strip().lower()
            if key_text == "h":
                self._set_relative_date(0)
                return
            if key_text == "o":
                self._set_relative_date(-1)
                return
            if key_text == "i":
                self._set_today_anchor(day=1)
                return
            if key_text == "f":
                self._set_end_of_current_month()
                return
            if key_text == "a":
                self._set_today_anchor(month=1, day=1)
                return
        super().keyPressEvent(event)

    def _set_relative_date(self, days: int) -> None:
        today = local_now().date()
        chosen = QDate(today.year, today.month, today.day).addDays(days)
        self.setDate(chosen)
        self._prioritize_day_section()
        self._select_all_text()

    def _set_today_anchor(self, *, month: int | None = None, day: int | None = None) -> None:
        today = local_now().date()
        chosen = QDate(today.year, month or today.month, day or today.day)
        self.setDate(chosen)
        self._prioritize_day_section()
        self._select_all_text()

    def _set_end_of_current_month(self) -> None:
        today = local_now().date()
        chosen = QDate(today.year, today.month, 1)
        chosen = chosen.addMonths(1).addDays(-1)
        self.setDate(chosen)
        self._prioritize_day_section()
        self._select_all_text()

    def _select_all_text(self) -> None:
        editor = self.lineEdit()
        if editor is not None:
            editor.selectAll()

    def _prioritize_day_section(self) -> None:
        self.setCurrentSection(QDateTimeEdit.Section.DaySection)


# ── Card helper ───────────────────────────────────────────────────────────────
def _make_card(parent=None) -> QFrame:
    card = QFrame(parent)
    card.setObjectName("reqCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card")
    card.setStyleSheet(
        f"QFrame#reqCard {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {_REQ_CARD_BG_START}, stop:0.55 {_REQ_CARD_BG_MID}, stop:1 {_REQ_CARD_BG_END});"
        f"  border:1px solid {_rgba(_REQ_NEON_PRIMARY, 82)};"
        f"  border-radius:18px;"
        f"}}"
        f"QFrame#reqCard:hover {{ border-color:{_rgba(_REQ_NEON_SECONDARY, 180)}; }}"
    )
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 5)
    glow = QColor(theme.PANEL_SHADOW)
    glow.setAlpha(52)
    shadow.setColor(glow)
    card.setGraphicsEffect(shadow)
    return card


def _field_label(text: str, scale: float) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("accent", "1")
    lbl.setStyleSheet(
        f"font-size:{max(7, int(8*scale))}pt; "
        f"font-weight:700; text-transform:uppercase; border:none; color:{_REQ_TEXT_MUTED};"
    )
    return lbl


def _value_label(text: str = "—", scale: float = 1.0) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size:{max(9, int(11*scale))}pt; font-weight:800; border:none; color:{_REQ_TEXT_PRIMARY};"
    )
    return lbl


# ── Campo de busca de cliente ─────────────────────────────────────────────────
class ClientSearchBox(QWidget):
    """
    Busca de cliente em tempo real — sempre via servidor.

    Adequada para bases com 100k+ clientes: nenhum pré-carregamento.
    Cada keystroke reinicia um debounce de 250 ms; ao disparar, envia o
    termo ao servidor que retorna os 100 resultados mais relevantes usando
    índices GIN de trigrama (busca por nome, código e CPF/CNPJ).
    """
    client_selected = Signal(object)   # dict do cliente ou None

    _DEBOUNCE_MS  = 250   # ms de espera após o último keystroke
    _SERVER_LIMIT = 100   # máximo de resultados por busca

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._selected: dict | None = None
        self._threads: list = []
        self._search_seq = 0

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self._DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_search)

        self._setup_ui()

    # ── Interface ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        s = self.scale
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Nome, código ou CPF/CNPJ...")
        self.input.setFixedHeight(max(30, int(36 * s)))
        self.input.setStyleSheet(_req_input_style(s))
        self.input.textChanged.connect(self._on_text)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        # Dropdown flutuante
        self._drop = QListWidget()
        self._drop.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        self._drop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drop.setStyleSheet(_req_search_drop_style(s))
        self._drop.itemClicked.connect(self._pick)
        self._drop.installEventFilter(self)
        self._drop.hide()

    # ── Digitação → debounce → servidor ───────────────────────────────────────

    def _on_text(self, text: str):
        # Se o texto atual é o cliente já selecionado, ignora
        if self._selected:
            expected = f"{self._selected['code']} — {self._selected['name']}"
            if text == expected:
                return
            self._selected = None

        term = text.strip()
        if len(term) < 2:
            self._debounce.stop()
            self._drop.hide()
            return

        self._debounce.start(self._DEBOUNCE_MS)

    def _do_search(self):
        term = self.input.text().strip()
        if len(term) < 2:
            return

        self._search_seq += 1
        search_id = self._search_seq

        # Indicador de carregamento enquanto aguarda o servidor
        self._drop.clear()
        loading = QListWidgetItem("  Buscando...")
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        loading.setForeground(QColor(_REQ_TEXT_MUTED))
        self._drop.addItem(loading)
        self._reposition()
        self._drop.show()

        t, w = _run_in_thread(
            api.list_clients, term, self._SERVER_LIMIT,
            on_result=lambda clients, sid=search_id: self._on_results(sid, clients),
            on_error=lambda _, sid=search_id: self._on_search_error(sid),
        )
        self._track_thread(t, w)

    def _on_results(self, search_id: int, clients: list):
        if search_id != self._search_seq:
            return
        if not isinstance(clients, list):
            clients = []
        self._render_results(clients)

    def _on_search_error(self, search_id: int):
        if search_id != self._search_seq:
            return
        self._drop.clear()
        it = QListWidgetItem("  Erro ao buscar — verifique a conexão")
        it.setFlags(Qt.ItemFlag.NoItemFlags)
        it.setForeground(QColor(_REQ_NEON_SECONDARY))
        self._drop.addItem(it)
        self._reposition()
        self._drop.show()

    # ── Renderização ──────────────────────────────────────────────────────────

    def _render_results(self, clients: list):
        self._drop.clear()

        if not clients:
            it = QListWidgetItem("  Nenhum cliente encontrado")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setForeground(QColor(_REQ_TEXT_MUTED))
            self._drop.addItem(it)
        else:
            for c in clients:
                cnpj = c.get("cnpj") or ""
                label = f"{c['code']}  —  {c['name']}"
                if cnpj:
                    label += f"    ({cnpj})"
                it = QListWidgetItem(label)
                it.setData(Qt.ItemDataRole.UserRole, c)
                self._drop.addItem(it)
        self._reposition()
        self._drop.show()

    def _reposition(self):
        s = self.scale
        gpos = self.input.mapToGlobal(self.input.rect().bottomLeft())
        row_h = max(30, int(34 * s))
        # Ocupa todo o espaço disponível abaixo do campo na tela
        screen = QApplication.primaryScreen().availableGeometry()
        available_h = screen.bottom() - gpos.y() - 10
        max_by_screen = max(4, available_h // row_h)
        rows = min(max(self._drop.count(), 1), max_by_screen)
        self._drop.move(gpos)
        self._drop.resize(self.input.width(), rows * row_h + 6)

    # ── Seleção ───────────────────────────────────────────────────────────────

    def _pick(self, item: QListWidgetItem):
        client = item.data(Qt.ItemDataRole.UserRole)
        if not client:
            return
        self._selected = client
        self.input.blockSignals(True)
        self.input.setText(f"{client['code']} — {client['name']}")
        self.input.blockSignals(False)
        self._drop.hide()
        self.client_selected.emit(client)

    def _first_selectable(self) -> QListWidgetItem | None:
        """Retorna o primeiro item com dado de cliente (pula itens não-selecionáveis)."""
        for i in range(self._drop.count()):
            it = self._drop.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) is not None:
                return it
        return None

    def _first_selectable_row(self) -> int:
        for i in range(self._drop.count()):
            it = self._drop.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) is not None:
                return i
        return -1

    def _next_selectable_row(self, start_row: int, step: int) -> int:
        if self._drop.count() <= 0:
            return -1
        row = start_row
        for _ in range(self._drop.count()):
            row += step
            if row < 0:
                row = self._drop.count() - 1
            elif row >= self._drop.count():
                row = 0
            it = self._drop.item(row)
            if it and it.data(Qt.ItemDataRole.UserRole) is not None:
                return row
        return -1

    # ── Navegação por teclado ─────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if obj is self.input:
                if key == Qt.Key.Key_Escape:
                    self._drop.hide()
                    return True
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._drop.isVisible():
                    step = 1 if key == Qt.Key.Key_Down else -1
                    current_row = self._drop.currentRow()
                    if current_row < 0:
                        target_row = self._first_selectable_row()
                    else:
                        target_row = self._next_selectable_row(current_row, step)
                    if target_row >= 0:
                        self._drop.setCurrentRow(target_row)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self._drop.isVisible() and self._drop.count():
                        cur = self._drop.currentItem()
                        if cur and cur.data(Qt.ItemDataRole.UserRole) is not None:
                            self._pick(cur)
                        else:
                            first = self._first_selectable()
                            if first:
                                self._pick(first)
                    return True

            elif obj is self._drop:
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    cur = self._drop.currentItem()
                    if cur:
                        self._pick(cur)
                    return True
                if key == Qt.Key.Key_Escape:
                    self._drop.hide()
                    self.input.setFocus()
                    return True

        if obj is self.input and event.type() == QEvent.Type.FocusOut:
            QTimer.singleShot(180, self._drop.hide)

        return super().eventFilter(obj, event)

    # ── Utilitários internos ──────────────────────────────────────────────────

    def _track_thread(self, thread: QThread, worker: QObject) -> None:
        pair = (thread, worker)
        self._threads.append(pair)

        def _cleanup():
            try:
                self._threads.remove(pair)
            except ValueError:
                pass
            worker.deleteLater()
            thread.deleteLater()

        thread.finished.connect(_cleanup)

    # ── API pública ───────────────────────────────────────────────────────────

    def set_clients(self, clients: list):
        """Mantido por compatibilidade — não é mais necessário."""
        pass

    def get_client_id(self) -> int | None:
        return self._selected["id"] if self._selected else None

    def get_selected(self) -> dict | None:
        return self._selected

    def set_client_by_id(self, client_id: int):
        """Carrega o cliente pelo ID ao abrir uma requisição existente."""
        t, w = _run_in_thread(
            api.get_client, client_id,
            on_result=self._on_client_loaded_by_id,
            on_error=lambda _: None,
        )
        self._track_thread(t, w)

    def _on_client_loaded_by_id(self, client: dict):
        if not client:
            return
        self._selected = client
        self.input.blockSignals(True)
        self.input.setText(f"{client['code']} — {client['name']}")
        self.input.blockSignals(False)

    def clear(self):
        self._selected = None
        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self._drop.hide()

    def apply_theme(self, scale: float | None = None) -> None:
        s = scale if scale is not None else self.scale
        self.input.setStyleSheet(_req_input_style(s))
        self._drop.setStyleSheet(_req_search_drop_style(s))


# ── Dialog do editor de desenho ───────────────────────────────────────────────
class CanvasDialog(QDialog):
    """Janela modal com o editor de desenho técnico."""

    def __init__(self, json_data: str, scale: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editor de Desenho")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_req_dialog_style())

        # Dimensiona na tela primária (posição definitiva aplicada no showEvent)
        self._pin_to_primary_screen()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.canvas = DrawingCanvas(scale)
        layout.addWidget(self.canvas, 1)

        # Botões inferiores
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("✕ Descartar alterações")
        btn_cancel.setFixedHeight(max(34, int(38 * scale)))
        btn_cancel.setStyleSheet(_req_secondary_btn_style(scale))
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("✓ Salvar desenho e fechar")
        btn_ok.setFixedHeight(max(34, int(38 * scale)))
        btn_ok.setStyleSheet(_req_primary_btn_style(scale))
        btn_ok.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        # Carrega dados existentes
        if json_data and json_data not in ("{}", ""):
            self.canvas.from_json(json_data)

    def get_json(self) -> str:
        return self.canvas.to_json()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc desmarca a ferramenta ativa; não fecha o editor."""
        if event.key() == Qt.Key.Key_Escape:
            if self.canvas.tool != Tool.SELECT:
                # Tinha ferramenta selecionada → volta para cursor de seleção
                self.canvas._set_tool(Tool.SELECT)
            # Em ambos os casos consome o evento — QDialog não vai chamar reject()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Contenção de monitor: sempre exibe na tela primária, sem vazar
    # ------------------------------------------------------------------
    def _pin_to_primary_screen(self) -> None:
        """Dimensiona e posiciona o diálogo inteiramente na tela primária."""
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QLayout
        geo = QGuiApplication.primaryScreen().availableGeometry()
        w = int(geo.width()  * 0.90)
        h = int(geo.height() * 0.88)
        # Impede que o layout force a janela a crescer além dos limites da tela.
        # SetNoConstraint: o layout para de propagar minimumSizeHint para a janela.
        # setMinimumSize(1,1): remove qualquer mínimo explícito que o Qt tiver fixado.
        if self.layout():
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(1, 1)
        self.setMaximumSize(geo.width(), geo.height())
        self.setGeometry(
            geo.x() + (geo.width()  - w) // 2,
            geo.y() + (geo.height() - h) // 2,
            w,
            h,
        )

    def showEvent(self, event) -> None:
        """Após o Windows terminar de posicionar a janela, força a posição correta."""
        super().showEvent(event)
        # QTimer.singleShot(0) garante que o reposicionamento ocorre DEPOIS
        # que o gerenciador de janelas do Windows terminar qualquer ajuste próprio.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._pin_to_primary_screen)


class _CanvasReadOnlyView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, scale: float, parent=None):
        super().__init__(scene, parent)
        self._zoom_level = 0
        self._scale_factor = scale
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setStyleSheet(
            f"border:1px solid {_rgba(_REQ_NEON_PRIMARY, 96)}; border-radius:12px; background:#fff;"
        )
        self.setMinimumHeight(max(300, int(420 * scale)))

    def zoom_in(self):
        self._apply_zoom(1.2, 1)

    def zoom_out(self):
        self._apply_zoom(1 / 1.2, -1)

    def fit_scene(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 100, 80)
        self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = 0

    def _apply_zoom(self, factor: float, step: int):
        next_level = self._zoom_level + step
        if next_level < -12 or next_level > 20:
            return
        self._zoom_level = next_level
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_level == 0:
            self.fit_scene()


class CanvasViewerDialog(QDialog):
    """Janela modal para visualizar o desenho sem permitir edição."""

    def __init__(self, json_data: str, scale: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visualizar Desenho")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_req_dialog_style())

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.90), int(screen.height() * 0.88))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        helper = QLabel("Visualização somente leitura. Use Ctrl + rolagem para zoom.")
        helper.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9 * scale))}pt;"
        )
        toolbar.addWidget(helper)
        toolbar.addStretch()

        btn_zoom_out = QPushButton("Zoom -")
        btn_zoom_out.setFixedHeight(max(30, int(34 * scale)))
        btn_zoom_out.setStyleSheet(_req_secondary_btn_style(scale))
        toolbar.addWidget(btn_zoom_out)

        btn_zoom_in = QPushButton("Zoom +")
        btn_zoom_in.setFixedHeight(max(30, int(34 * scale)))
        btn_zoom_in.setStyleSheet(_req_secondary_btn_style(scale))
        toolbar.addWidget(btn_zoom_in)

        btn_fit = QPushButton("Ajustar")
        btn_fit.setFixedHeight(max(30, int(34 * scale)))
        btn_fit.setStyleSheet(_req_secondary_btn_style(scale))
        toolbar.addWidget(btn_fit)
        layout.addLayout(toolbar)

        scene = QGraphicsScene(self)
        self.canvas_view = _CanvasReadOnlyView(scene, scale, self)
        layout.addWidget(self.canvas_view, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(max(34, int(38 * scale)))
        btn_close.setStyleSheet(_req_primary_btn_style(scale))
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

        result = load_canvas_scene(scene, json_data, selectable=False)
        if result.get("items", 0) == 0:
            placeholder = scene.addText("Nenhum desenho salvo para visualizar.")
            placeholder.setDefaultTextColor(QColor(_REQ_TEXT_MUTED))
            placeholder.setFont(QFont(theme.FONT_PRIMARY, max(9, int(10 * scale))))
            placeholder.setPos(20, 20)
        self.canvas_view.fit_scene()

        btn_zoom_in.clicked.connect(self.canvas_view.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas_view.zoom_out)
        btn_fit.clicked.connect(self.canvas_view.fit_scene)


class SignaturePad(QWidget):
    changed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._pen = QPen(QColor("#0F172A"), max(2, int(2.4 * scale)))
        self._pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self._pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._image = QImage()
        self._last_point = QPointF()
        self._drawing = False
        self._has_strokes = False

        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(max(260, int(320 * scale)), max(120, int(160 * scale)))

    def _ensure_canvas(self) -> None:
        width = max(1, self.width())
        height = max(1, self.height())
        if (
            not self._image.isNull()
            and self._image.width() == width
            and self._image.height() == height
        ):
            return

        previous = self._image
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)

        if not previous.isNull():
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawImage(0, 0, previous)
            painter.end()

        self._image = image

    def clear(self, emit_signal: bool = True) -> None:
        self._ensure_canvas()
        self._image.fill(Qt.GlobalColor.transparent)
        self._has_strokes = False
        self.update()
        if emit_signal:
            self.changed.emit()

    def set_signature_png_bytes(self, signature_png_bytes: bytes | None) -> None:
        if not signature_png_bytes:
            self.clear()
            return

        loaded = QImage.fromData(signature_png_bytes, "PNG")
        if loaded.isNull():
            self.clear()
            return

        self._ensure_canvas()
        self._image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        max_w = max(1, self.width() - 12)
        max_h = max(1, self.height() - 12)
        scaled = loaded.scaled(
            max_w,
            max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) / 2
        y = (self.height() - scaled.height()) / 2
        painter.drawImage(QPointF(x, y), scaled)
        painter.end()

        self._has_strokes = True
        self.update()
        self.changed.emit()

    def _trimmed_image(self) -> QImage:
        if self._image.isNull() or not self._has_strokes:
            return QImage()

        width = self._image.width()
        height = self._image.height()
        left = width
        top = height
        right = -1
        bottom = -1

        for y in range(height):
            for x in range(width):
                alpha = (self._image.pixel(x, y) >> 24) & 0xFF
                if alpha:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)

        if right < left or bottom < top:
            return QImage()

        padding = 4
        start_x = max(0, left - padding)
        start_y = max(0, top - padding)
        end_x = min(width - 1, right + padding)
        end_y = min(height - 1, bottom + padding)
        return self._image.copy(start_x, start_y, end_x - start_x + 1, end_y - start_y + 1)

    def is_empty(self) -> bool:
        return not self._has_strokes

    def to_png_bytes(self) -> bytes:
        image = self._trimmed_image()
        if image.isNull():
            return b""

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        return bytes(data)

    def _stroke_to(self, point: QPointF) -> None:
        self._ensure_canvas()
        start = QPointF(self._last_point)
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self._pen)
        painter.drawLine(start, point)
        painter.end()
        self._last_point = QPointF(point)
        self._has_strokes = True
        margin = max(2.0, self._pen.widthF() + 2.0)
        dirty_rect = QRectF(start, point).normalized().adjusted(-margin, -margin, margin, margin)
        self.update(dirty_rect.toRect())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._last_point = QPointF(event.position())
            self._stroke_to(QPointF(event.position()))
            self.changed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drawing and (event.buttons() & Qt.MouseButton.LeftButton):
            self._stroke_to(QPointF(event.position()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._stroke_to(QPointF(event.position()))
            self._drawing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._ensure_canvas()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._ensure_canvas()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.drawImage(0, 0, self._image)

        border_style = (
            Qt.PenStyle.SolidLine
            if self._has_strokes
            else Qt.PenStyle.DashLine
        )
        painter.setPen(QPen(QColor(_REQ_NEON_PRIMARY), 1, border_style))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)

        if not self._has_strokes:
            painter.setPen(QColor(_REQ_TEXT_MUTED))
            painter.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self._scale))))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Assine com mouse ou caneta digital",
            )
        painter.end()


class SignatureDialog(QDialog):
    def __init__(self, scale: float, signature_png_bytes: bytes | None = None, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._signature_png_bytes: bytes | None = signature_png_bytes

        self.setWindowTitle("Assinatura do Cliente")
        self.setModal(True)
        self.setMinimumSize(max(460, int(600 * scale)), max(320, int(420 * scale)))
        self.setStyleSheet(_req_dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12, int(14 * scale)), max(12, int(14 * scale)),
                                  max(12, int(14 * scale)), max(12, int(14 * scale)))
        layout.setSpacing(max(8, int(10 * scale)))

        hint = QLabel("Desenhe a assinatura abaixo com mouse ou caneta da mesa digitalizadora.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size:{max(8, int(9 * scale))}pt; color:{_REQ_TEXT_MUTED};")
        layout.addWidget(hint)

        self.pad = SignaturePad(scale, self)
        layout.addWidget(self.pad, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        btn_clear = QPushButton("Limpar")
        btn_clear.setFixedHeight(max(30, int(34 * scale)))
        btn_clear.setStyleSheet(_req_secondary_btn_style(scale))
        btn_clear.clicked.connect(lambda _checked=False: self.pad.clear())
        buttons.addWidget(btn_clear)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(max(30, int(34 * scale)))
        btn_cancel.setStyleSheet(_req_secondary_btn_style(scale))
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)

        self.btn_apply = QPushButton("Aplicar Assinatura")
        self.btn_apply.setFixedHeight(max(30, int(34 * scale)))
        self.btn_apply.setStyleSheet(_req_primary_btn_style(scale))
        self.btn_apply.clicked.connect(self._apply_signature)
        buttons.addWidget(self.btn_apply)
        layout.addLayout(buttons)

        self.pad.changed.connect(self._sync_apply_state)
        if signature_png_bytes:
            self.pad.set_signature_png_bytes(signature_png_bytes)
        self._sync_apply_state()

    def _sync_apply_state(self) -> None:
        self.btn_apply.setEnabled(not self.pad.is_empty())

    def _apply_signature(self) -> None:
        png = self.pad.to_png_bytes()
        if not png:
            QMessageBox.warning(self, "Assinatura", "Faça uma assinatura antes de aplicar.")
            return
        self._signature_png_bytes = png
        self.accept()

    def signature_png_bytes(self) -> bytes | None:
        return self._signature_png_bytes


# ── View principal ────────────────────────────────────────────────────────────
class RequisitionForm(QWidget):
    saved           = Signal(dict)
    save_requested  = Signal()          # emitido pelo botão Salvar do formulário
    guide_requested = Signal()          # emitido pelo botão ? de ajuda
    req_id: int | None = None

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._clients: list[dict] = []
        self._threads: list = []
        self._canvas_json: str = "{}"   # armazena o JSON do desenho
        self._signature_png_bytes: bytes | None = None
        self._loaded_updated_at = None  # versão carregada (trava otimista)
        self._setup_ui()
        self._setup_hidden_shortcuts()
        self._load_clients()
        self._update_canvas_preview()

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setObjectName("requisitionFormView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#requisitionFormView {{ background:{theme.CONTENT_BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ScrollArea
        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}"
        )
        self._page_scroll.viewport().setStyleSheet(f"background:{theme.CONTENT_BG}; border:none;")
        root.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setObjectName("requisitionFormContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(f"QWidget#requisitionFormContent {{ background:{theme.CONTENT_BG}; }}")
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        s = self.scale
        margin = max(12, int(16 * s))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(10, int(12 * s)))

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_info_bar())
        layout.addWidget(self._build_client_section())
        layout.addWidget(self._build_items_section())
        layout.addWidget(self._build_bottom_section())

        # ── Botões Salvar + WhatsApp ──────────────────────────────────────────
        s = self.scale
        save_row = QHBoxLayout()
        save_row.addStretch()

        btn_calc = QPushButton("🧮 CALCULADORA DE PESO")
        btn_calc.setFixedHeight(max(42, int(48 * s)))
        btn_calc.setMinimumWidth(max(200, int(230 * s)))
        btn_calc.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        btn_calc.clicked.connect(self._open_weight_calculator)
        save_row.addWidget(btn_calc)
        self.btn_calc = btn_calc

        save_row.addSpacing(max(8, int(10 * s)))

        btn_production = QPushButton("ENVIAR PARA PRODUÇÃO")
        btn_production.setFixedHeight(max(42, int(48 * s)))
        btn_production.setMinimumWidth(max(220, int(250 * s)))
        btn_production.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        btn_production.clicked.connect(self._send_to_production)
        save_row.addWidget(btn_production)
        self.btn_production = btn_production
        self.btn_production.setText("🏭 ENVIAR PARA PRODUÇÃO")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_whatsapp = QPushButton("ENVIAR WHATSAPP")
        btn_whatsapp.setFixedHeight(max(42, int(48 * s)))
        btn_whatsapp.setMinimumWidth(max(180, int(210 * s)))
        btn_whatsapp.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        btn_whatsapp.clicked.connect(self._send_whatsapp_client)
        save_row.addWidget(btn_whatsapp)
        self.btn_whatsapp = btn_whatsapp
        self.btn_whatsapp.setText("📲 ENVIAR WHATSAPP")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_print = QPushButton("IMPRIMIR")
        btn_print.setFixedHeight(max(42, int(48 * s)))
        btn_print.setMinimumWidth(max(180, int(210 * s)))
        btn_print.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        self.btn_print = btn_print
        self._update_print_button_visual()
        btn_print.clicked.connect(self._print_requisition_pdf)
        save_row.addWidget(btn_print)

        save_row.addSpacing(max(8, int(10 * s)))

        btn_save = QPushButton("SALVAR REQUISIÇÃO")
        btn_save.setFixedHeight(max(42, int(48 * s)))
        btn_save.setMinimumWidth(max(220, int(260 * s)))
        btn_save.setStyleSheet(_emphasized_btn_style(_req_primary_btn_style(s)))
        btn_save.clicked.connect(self.save_requested.emit)
        save_row.addWidget(btn_save)
        self.btn_save = btn_save
        self.btn_save.setText("💾 SALVAR REQUISIÇÃO")
        layout.addLayout(save_row)

        self.lock_label = QLabel("")
        self.lock_label.setVisible(False)
        self.lock_label.setWordWrap(True)
        self.lock_label.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; font-style:italic; border:none;"
        )
        layout.addWidget(self.lock_label)

        self._editable_widgets = [
            self.client_search,
            self.input_ped,
            self.input_prazo,
            self.chk_retirada,
            self.chk_entrega,
            self.input_obra,
            self.input_fone,
            self.input_address,
            self.item_table,
            self.input_obs,
            self.btn_canvas,
            self.btn_sign,
            self.btn_clear_signature,
            self.btn_production,
            self.btn_save,
        ]
        self._set_form_locked(False)

        layout.addStretch()

    def _setup_hidden_shortcuts(self) -> None:
        """Atalhos escondidos da tela Nova Requisição (letras simples)."""
        shortcuts = {
            "C": self._shortcut_open_calculator,
            "P": self._shortcut_send_production,
            "S": self._shortcut_save,
            "W": self._shortcut_send_whatsapp,
            "D": self._shortcut_open_drawing_editor,
            "V": self._shortcut_open_drawing_viewer,
            "N": self._shortcut_prompt_ped_action,
            "E": self._shortcut_set_delivery,
            "R": self._shortcut_set_pickup,
        }

        self._hidden_shortcut_actions: list[QAction] = []
        for sequence, callback in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(
                lambda _checked=False, cb=callback: self._run_hidden_shortcut(cb)
            )
            self.addAction(action)
            self._hidden_shortcut_actions.append(action)

    def _run_hidden_shortcut(self, callback) -> None:
        if not self._can_process_hidden_shortcut():
            return
        callback()

    def _can_process_hidden_shortcut(self) -> bool:
        if not self.isVisible():
            return False

        if QApplication.activeModalWidget() is not None:
            return False

        focus = QApplication.focusWidget()
        if focus is None:
            return True

        editable_types = (
            QLineEdit,
            QTextEdit,
            QPlainTextEdit,
            QComboBox,
            QDateEdit,
            QAbstractItemView,
        )
        widget = focus
        while widget is not None:
            if isinstance(widget, editable_types):
                return False
            widget = widget.parentWidget()
        return True

    def _shortcut_open_calculator(self) -> None:
        if hasattr(self, "btn_calc") and self.btn_calc.isEnabled():
            self.btn_calc.click()

    def _shortcut_send_production(self) -> None:
        if hasattr(self, "btn_production") and self.btn_production.isEnabled():
            self.btn_production.click()

    def _shortcut_save(self) -> None:
        if hasattr(self, "btn_save") and self.btn_save.isEnabled():
            self.btn_save.click()

    def _shortcut_send_whatsapp(self) -> None:
        if hasattr(self, "btn_whatsapp") and self.btn_whatsapp.isEnabled():
            self.btn_whatsapp.click()

    def _shortcut_open_drawing_editor(self) -> None:
        if hasattr(self, "btn_canvas") and self.btn_canvas.isEnabled():
            self.btn_canvas.click()

    def _shortcut_open_drawing_viewer(self) -> None:
        if hasattr(self, "btn_canvas_view") and self.btn_canvas_view.isEnabled():
            self.btn_canvas_view.click()

    def _shortcut_prompt_ped_action(self) -> None:
        action = self._ask_ped_shortcut_action()
        if not action:
            return

        ped_number = self._ask_ped_number()
        if not ped_number:
            return

        if action == "fill":
            self.input_ped.setText(ped_number)
            self.input_ped.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.input_ped.selectAll()
            return

        self._open_requisition_by_ped(ped_number)

    def _ask_ped_shortcut_action(self) -> str | None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Pedido")
        msg.setText("O que deseja fazer com o número do PED?")
        btn_fill = msg.addButton("Preencher PED", QMessageBox.ButtonRole.AcceptRole)
        btn_open = msg.addButton("Abrir por pedido", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

        # Atalhos locais do diálogo: P=Preencher, A=Abrir, C=Cancelar
        for key, button in (("P", btn_fill), ("A", btn_open), ("C", btn_cancel)):
            action = QAction(msg)
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(button.click)
            msg.addAction(action)

        apply_message_box_theme(msg)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_fill:
            return "fill"
        if clicked == btn_open:
            return "open"
        return None

    @staticmethod
    def _normalize_ped_number(value: str | None) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if not digits:
            return ""
        normalized = digits.lstrip("0")
        return normalized or "0"

    def _ask_ped_number(self) -> str | None:
        default_value = (self.input_ped.text() or "").strip()
        dialog = QDialog(self)
        dialog.setWindowTitle("Pedido")
        dialog.setModal(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setStyleSheet(_req_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl = QLabel("Digite o número do PED:")
        lbl.setStyleSheet(
            f"font-size:{max(8, int(10 * self.scale))}pt; font-weight:700; color:{_REQ_TEXT_PRIMARY};"
        )
        layout.addWidget(lbl)

        input_ped = QLineEdit(default_value)
        input_ped.setPlaceholderText("Ex.: 123456")
        input_ped.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*")))
        input_ped.setStyleSheet(_req_input_style(self.scale, bold=True, accent=_REQ_NEON_PRIMARY))
        input_ped.setMinimumWidth(max(240, int(280 * self.scale)))
        layout.addWidget(input_ped)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(_req_primary_btn_style(self.scale))
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(_req_secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dialog.reject)
        buttons.addWidget(btn_ok)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)
        input_ped.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        input_ped.selectAll()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        ped_number = (input_ped.text() or "").strip()
        if not ped_number:
            return None
        if not ped_number.isdigit():
            QMessageBox.warning(self, "PED", "Digite apenas números no campo PED.")
            return None
        if self._normalize_ped_number(ped_number) == "0":
            QMessageBox.warning(self, "PED", "Informe um número de PED válido.")
            return None
        return ped_number

    def _open_requisition_by_ped(self, ped_number: str) -> None:
        if self.has_unsaved_data():
            if not ask_confirmation(
                self,
                "Abrir requisição por PED",
                "Existem dados no formulário atual que serão substituídos.\n\nDeseja continuar?",
                yes_text="Sim",
                no_text="Não",
            ):
                return

        normalized_target = self._normalize_ped_number(ped_number)
        thread, worker = _run_in_thread(
            api.list_requisitions,
            search=ped_number,
            limit=200,
            on_result=lambda data, target=normalized_target: self._on_requisition_search_by_ped(data, target),
            on_error=lambda msg: QMessageBox.critical(self, "PED", msg),
        )
        self._threads.append((thread, worker))

    def _on_requisition_search_by_ped(self, results: list, normalized_target: str) -> None:
        matches = []
        for req in (results or []):
            req_norm = self._normalize_ped_number(str(req.get("ped_number") or ""))
            if req_norm == normalized_target:
                matches.append(req)

        if not matches:
            QMessageBox.warning(self, "PED", "PED não encontrado.")
            return

        matches.sort(key=lambda req: int(req.get("id") or 0), reverse=True)
        req_id = int(matches[0].get("id") or 0)
        if not req_id:
            QMessageBox.warning(self, "PED", "PED não encontrado.")
            return
        self._load_requisition_by_id(req_id)

    def _load_requisition_by_id(self, req_id: int) -> None:
        """Busca o registro COMPLETO (a listagem é enxuta) e popula o formulário."""
        read_only = session.should_open_requisition_read_only("history")
        thread, worker = _run_in_thread(
            api.get_requisition,
            req_id,
            on_result=lambda full, ro=read_only: self.load_requisition(full, read_only=ro),
            on_error=lambda msg: QMessageBox.critical(self, "Requisição", msg),
        )
        self._threads.append((thread, worker))

    def _open_requisition_search(self) -> None:
        """Abre uma janela de busca de requisições (cliente, obra ou nº do
        pedido). O vendedor vê as próprias; admin/gerente veem todas. Clicar em
        um resultado reabre a requisição no formulário."""
        if self.has_unsaved_data():
            if not ask_confirmation(
                self,
                "Buscar requisição",
                "Há dados no formulário atual que serão substituídos ao abrir "
                "outra requisição.\n\nDeseja continuar?",
                yes_text="Sim",
                no_text="Não",
            ):
                return

        s = self.scale
        dialog = QDialog(self)
        dialog.setWindowTitle("Buscar requisição")
        dialog.setModal(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setStyleSheet(_req_dialog_style())
        dialog.setMinimumWidth(max(860, int(980 * s)))

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        filters_grid = QGridLayout()
        filters_grid.setHorizontalSpacing(max(10, int(12 * s)))
        filters_grid.setVerticalSpacing(max(6, int(8 * s)))

        lbl = QLabel("BUSCA POR PED, CLIENTE OU OBRA")
        lbl.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:800; color:{_REQ_TEXT_PRIMARY};"
        )
        search = QLineEdit()
        search.setPlaceholderText("Ex.: nome do cliente, obra ou 123456")
        search.setStyleSheet(_req_input_style(s))
        search.setMinimumHeight(max(30, int(36 * s)))
        filters_grid.addWidget(lbl, 0, 0)
        filters_grid.addWidget(search, 1, 0)

        vendor_label = QLabel("VENDEDOR")
        vendor_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:800; color:{_REQ_TEXT_PRIMARY};"
        )
        vendor_search = QLineEdit()
        vendor_search.setPlaceholderText("Nome ou código do vendedor")
        vendor_search.setStyleSheet(_req_input_style(s))
        vendor_search.setMinimumHeight(max(30, int(36 * s)))
        filters_grid.addWidget(vendor_label, 0, 1)
        filters_grid.addWidget(vendor_search, 1, 1)
        layout.addLayout(filters_grid)

        period_label = QLabel("Período de emissão")
        period_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:800; color:{_REQ_TEXT_PRIMARY};"
        )
        layout.addWidget(period_label)

        shortcuts = QLabel(
            "Atalhos do período: h = hoje | o = ontem | i = início do mês | f = final do mês | a = início do ano"
        )
        shortcuts.setWordWrap(True)
        shortcuts.setStyleSheet(
            f"color:{_REQ_NEON_PRIMARY}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
        )
        layout.addWidget(shortcuts)

        period_hint = QLabel("Filtro opcional. Use Delete para limpar a data do campo selecionado.")
        period_hint.setProperty("muted", "1")
        period_hint.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; color:{_REQ_TEXT_MUTED};")
        layout.addWidget(period_hint)

        today = local_now().date()
        today_qdate = QDate(today.year, today.month, today.day)

        def _focus_date_field(field: QDateEdit) -> None:
            field.setFocus(Qt.FocusReason.MouseFocusReason)
            if isinstance(field, PeriodDateEdit):
                field._prioritize_day_section()
            field.selectAll()

        def _set_date_today(field: QDateEdit) -> None:
            field.setDate(today_qdate)
            _focus_date_field(field)

        period_row = QHBoxLayout()
        period_row.setSpacing(max(6, int(8 * s)))

        date_from = PeriodDateEdit(ALL_DATES_SENTINEL)
        date_from.setMinimumDate(ALL_DATES_SENTINEL)
        date_from.setDate(today_qdate)
        date_from.setSpecialValueText("Data inicial")
        date_from.setDisplayFormat("dd/MM/yyyy")
        date_from.setCalendarPopup(False)
        date_from.setMinimumHeight(max(30, int(36 * s)))
        date_from.setStyleSheet(_req_input_style(s))

        btn_date_from = QToolButton()
        btn_date_from.setText("📅")
        btn_date_from.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_date_from.setToolTip("Usar a data de hoje")
        btn_date_from.setFixedSize(max(32, int(36 * s)), max(30, int(36 * s)))
        btn_date_from.setStyleSheet(_calendar_btn_style(s))
        btn_date_from.clicked.connect(lambda: _set_date_today(date_from))

        until_label = QLabel("ATÉ")
        until_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700; color:{_REQ_TEXT_MUTED};"
        )
        until_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        date_to = PeriodDateEdit(ALL_DATES_SENTINEL)
        date_to.setMinimumDate(ALL_DATES_SENTINEL)
        date_to.setDate(today_qdate)
        date_to.setSpecialValueText("Data final")
        date_to.setDisplayFormat("dd/MM/yyyy")
        date_to.setCalendarPopup(False)
        date_to.setMinimumHeight(max(30, int(36 * s)))
        date_to.setStyleSheet(_req_input_style(s))

        btn_date_to = QToolButton()
        btn_date_to.setText("📅")
        btn_date_to.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_date_to.setToolTip("Usar a data de hoje")
        btn_date_to.setFixedSize(max(32, int(36 * s)), max(30, int(36 * s)))
        btn_date_to.setStyleSheet(_calendar_btn_style(s))
        btn_date_to.clicked.connect(lambda: _set_date_today(date_to))

        period_row.addWidget(date_from, 1)
        period_row.addWidget(btn_date_from)
        period_row.addWidget(until_label)
        period_row.addWidget(date_to, 1)
        period_row.addWidget(btn_date_to)
        layout.addLayout(period_row)

        results = QTableWidget(0, 6)
        results.setHorizontalHeaderLabels(["PED", "CLIENTE", "OBRA", "VENDEDOR", "STATUS", "EMISSÃO"])
        results.verticalHeader().setVisible(False)
        results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        results.setAlternatingRowColors(True)
        results.setShowGrid(False)
        results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        results.setWordWrap(False)
        results.setStyleSheet(_dialog_table_style(s))
        results.setMinimumHeight(max(260, int(320 * s)))
        apply_smooth_scroll(results)

        head = results.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(results, 1)

        hint = QLabel("Digite ao menos 2 caracteres na busca principal, filtre por vendedor e/ou informe um período.")
        hint.setProperty("muted", "1")
        hint.setStyleSheet(f"font-size:{max(7, int(9 * s))}pt; color:{_REQ_TEXT_MUTED};")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        btn_open = QPushButton("Abrir")
        btn_open.setStyleSheet(_req_primary_btn_style(s))
        btn_close = QPushButton("Fechar")
        btn_close.setStyleSheet(_req_secondary_btn_style(s))
        buttons.addWidget(btn_open)
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

        state = {"counter": 0}
        timer = QTimer(dialog)
        timer.setSingleShot(True)
        timer.setInterval(350)

        def _selected_emission_period() -> tuple[str, str] | None:
            start = date_from.date()
            end = date_to.date()
            has_start = start != ALL_DATES_SENTINEL
            has_end = end != ALL_DATES_SENTINEL
            if has_start and has_end and start > end:
                return None
            return (
                start.toString("yyyy-MM-dd") if has_start else "",
                end.toString("yyyy-MM-dd") if has_end else "",
            )

        def _render(data):
            results.setRowCount(0)
            items = data if isinstance(data, list) else []
            if not items:
                hint.setText("Nenhuma requisição encontrada.")
                return
            hint.setText(f"{len(items)} resultado(s). Dê duplo clique para abrir.")
            for r in items:
                row = results.rowCount()
                results.insertRow(row)

                ped = str(r.get("ped_number") or "?").strip()
                cli = str(r.get("client_name") or r.get("client_id") or "")
                obra = str(r.get("obra") or "").strip()
                vendor = str(r.get("vendor_name") or r.get("vendor_code") or r.get("vendor_id") or "")
                status = theme.STATUS_LABELS.get(str(r.get("status") or ""), "")
                raw = str(r.get("emission_date") or r.get("created_at") or "")[:10]
                dt = f"{raw[8:10]}/{raw[5:7]}/{raw[0:4]}" if len(raw) == 10 and raw[4] == "-" else ""
                values = [
                    f"#{ped.zfill(6)}" if ped.isdigit() else ped,
                    cli or "-",
                    obra or "-",
                    vendor or "-",
                    status or "-",
                    dt or "-",
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, int(r.get("id") or 0))
                    if col in (1, 2, 3):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if value != "-":
                        item.setToolTip(value)
                    results.setItem(row, col, item)

        def _do_search():
            term = search.text().strip()
            vendor_term = vendor_search.text().strip()
            period = _selected_emission_period()
            if period is None:
                results.setRowCount(0)
                hint.setText("A data inicial não pode ser maior que a data final.")
                return
            emission_date_start, emission_date_end = period
            has_period = bool(emission_date_start or emission_date_end)
            has_vendor = bool(vendor_term)
            search_term = term if len(term) >= 2 else ""
            if not search_term and not has_period and not has_vendor:
                results.setRowCount(0)
                hint.setText("Digite ao menos 2 caracteres na busca principal, filtre por vendedor e/ou informe um período.")
                return
            state["counter"] += 1
            sid = state["counter"]
            hint.setText("Buscando...")

            def _on_result(data, _sid=sid):
                if _sid != state["counter"]:
                    return  # resultado obsoleto — ignora
                _render(data)

            thread, worker = _run_in_thread(
                api.list_requisitions,
                search=search_term,
                vendor_search=vendor_term,
                limit=50,
                emission_date_start=emission_date_start,
                emission_date_end=emission_date_end,
                on_result=_on_result,
                on_error=lambda msg: hint.setText(f"Erro na busca: {msg}"),
            )
            self._threads.append((thread, worker))

        def _open_selected():
            row = results.currentRow()
            if row < 0:
                hint.setText("Selecione uma requisição na tabela.")
                return
            item = results.item(row, 0)
            req_id = int(item.data(Qt.ItemDataRole.UserRole) or 0) if item is not None else 0
            if not req_id:
                return
            dialog.accept()
            self._load_requisition_by_id(req_id)

        timer.timeout.connect(_do_search)
        search.textChanged.connect(lambda _t: timer.start())
        vendor_search.textChanged.connect(lambda _t: timer.start())
        date_from.dateChanged.connect(lambda _d: timer.start())
        date_to.dateChanged.connect(lambda _d: timer.start())
        search.returnPressed.connect(_do_search)
        vendor_search.returnPressed.connect(_do_search)
        results.cellDoubleClicked.connect(lambda _row, _col: _open_selected())
        btn_open.clicked.connect(_open_selected)
        btn_close.clicked.connect(dialog.reject)

        search.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        dialog.exec()

    def _shortcut_set_delivery(self) -> None:
        if hasattr(self, "chk_entrega") and self.chk_entrega.isEnabled():
            self.chk_entrega.setChecked(True)

    def _shortcut_set_pickup(self) -> None:
        if hasattr(self, "chk_retirada") and self.chk_retirada.isEnabled():
            self.chk_retirada.setChecked(True)

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        card = _make_card()
        layout = QHBoxLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12, int(16*s)), max(8, int(12*s)),
                                   max(12, int(16*s)), max(8, int(12*s)))
        layout.setSpacing(max(12, int(16*s)))

        # Título Requisição + número
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        lbl_req = QLabel("REQUISIÇÃO")
        lbl_req.setProperty("accent", "1")
        lbl_req.setStyleSheet(
            f"font-size:{max(10,int(12*s))}pt; font-weight:700; border:none; color:{_REQ_TEXT_MUTED};"
        )
        self.lbl_req_title = lbl_req
        self.lbl_ped_num = QLabel("#000000")
        self.lbl_ped_num.setProperty("accent", "1")
        self.lbl_ped_num.setStyleSheet(
            f"font-size:{max(16,int(20*s))}pt; font-weight:800; border:none; color:{_REQ_NEON_PRIMARY};"
        )
        title_col.addWidget(lbl_req)
        title_col.addWidget(self.lbl_ped_num)
        layout.addLayout(title_col)

        layout.addStretch()

        # Data
        date_col = QVBoxLayout()
        date_col.setSpacing(2)
        date_col.addWidget(_field_label("📅 DATA", s))
        self.lbl_date = _value_label(date.today().strftime("%d/%m/%Y"), s)
        date_col.addWidget(self.lbl_date)
        layout.addLayout(date_col)

        # Vendedor
        vend_col = QVBoxLayout()
        vend_col.setSpacing(2)
        vend_col.addWidget(_field_label("👤 VENDEDOR", s))
        self.lbl_vendor = _value_label(session.user_name.upper(), s)
        vend_col.addWidget(self.lbl_vendor)
        layout.addLayout(vend_col)

        # Status
        status_col = QVBoxLayout()
        status_col.setSpacing(2)
        status_col.addWidget(_field_label("STATUS", s))
        self.status_badge = StatusBadge("em_andamento", s)
        status_col.addWidget(self.status_badge)
        layout.addLayout(status_col)

        # PED
        ped_col = QVBoxLayout()
        ped_col.setSpacing(2)
        ped_col.addWidget(_field_label("PED:", s))
        self.input_ped = QLineEdit()
        self.input_ped.setPlaceholderText("Nº pedido")
        self._ped_min_width = max(80, int(100*s))
        self._ped_max_width = max(180, int(240*s))
        self.input_ped.setFixedWidth(self._ped_min_width)
        self.input_ped.setFixedHeight(max(30, int(36*s)))
        self.input_ped.setStyleSheet(_req_input_style(s, bold=True, accent=_REQ_NEON_PRIMARY))
        # Apenas dígitos permitidos
        self.input_ped.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d*"))
        )
        def _resize_ped_field_width():
            text = self.input_ped.text().strip()
            sample = text if text else self.input_ped.placeholderText()
            target = self.input_ped.fontMetrics().horizontalAdvance(sample) + max(18, int(24 * s))
            target = max(self._ped_min_width, min(self._ped_max_width, target))
            self.input_ped.setFixedWidth(target)

        def _on_ped_changed(t: str):
            self.lbl_ped_num.setText(f"#{t.zfill(6)}" if t else "#000000")
            _resize_ped_field_width()

        self.input_ped.textChanged.connect(_on_ped_changed)
        _resize_ped_field_width()
        ped_col.addWidget(self.input_ped)
        layout.addLayout(ped_col)

        # Coluna de ações redondas: "?" (guia) em cima, lupa (buscar) embaixo
        sz_g = max(24, int(28 * s))
        _round_btn_style = _req_round_icon_btn_style(s, sz_g)

        self.btn_guide = QPushButton("?")
        self.btn_guide.setToolTip("Abrir guia rápido")
        self.btn_guide.setFixedSize(sz_g, sz_g)
        self.btn_guide.setStyleSheet(_round_btn_style)
        self.btn_guide.clicked.connect(self.guide_requested)

        # Lupa — busca de requisições (por cliente, obra ou nº do pedido)
        self.btn_search_req = QPushButton("🔍")
        self.btn_search_req.setToolTip("Buscar requisição (cliente, obra ou nº do pedido)")
        self.btn_search_req.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search_req.setFixedSize(sz_g, sz_g)
        self.btn_search_req.setStyleSheet(_round_btn_style)
        self.btn_search_req.clicked.connect(self._open_requisition_search)

        actions_col = QVBoxLayout()
        actions_col.setSpacing(max(4, int(6 * s)))
        actions_col.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignHCenter)
        actions_col.addWidget(self.btn_search_req, 0, Qt.AlignmentFlag.AlignHCenter)
        actions_col.addStretch()
        layout.addLayout(actions_col)

        return card

    # ── Barra de informações ───────────────────────────────────────────────────
    def _build_info_bar(self) -> QFrame:
        card = _make_card()
        layout = QHBoxLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12,int(16*s)), max(8,int(10*s)),
                                   max(12,int(16*s)), max(8,int(10*s)))
        layout.setSpacing(max(16,int(20*s)))

        def add_field(icon, label, widget):
            col = QVBoxLayout()
            col.setSpacing(2)
            title = f"{icon}  {label}".strip() if icon else label
            col.addWidget(_field_label(title, s))
            col.addWidget(widget)
            layout.addLayout(col)

        # Prazo de entrega
        self.input_prazo = QDateEdit(self._default_delivery_qdate())
        self.input_prazo.setDisplayFormat("dd/MM/yyyy")
        self.input_prazo.setCalendarPopup(False)
        self.input_prazo.setReadOnly(True)
        self.input_prazo.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.input_prazo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input_prazo.setFixedHeight(max(28,int(32*s)))
        self.input_prazo.setStyleSheet(_req_input_style(s))
        add_field("📦", "PRAZO DE ENTREGA", self.input_prazo)
        self._apply_min_delivery_constraint()

        # Retirada — mutuamente exclusivo com Entrega
        chk_style = _req_checkbox_style(s)

        self.chk_retirada = QCheckBox("NÃO")
        self.chk_retirada.setStyleSheet(chk_style)
        add_field("🏪", "RETIRADA", self.chk_retirada)

        self.chk_entrega = QCheckBox("NÃO")
        self.chk_entrega.setStyleSheet(chk_style)
        add_field("🚚", "ENTREGA", self.chk_entrega)

        # Mutuamente exclusivos + texto dinâmico SIM / NÃO
        def _on_retirada(checked: bool):
            self.chk_retirada.setText("SIM" if checked else "NÃO")
            if checked:
                self.chk_entrega.setChecked(False)

        def _on_entrega(checked: bool):
            self.chk_entrega.setText("SIM" if checked else "NÃO")
            if checked:
                self.chk_retirada.setChecked(False)

        self.chk_retirada.toggled.connect(_on_retirada)
        self.chk_entrega.toggled.connect(_on_entrega)

        layout.addStretch()

        return card

    # ── Prazo mínimo de entrega (dias úteis) ──────────────────────────────────
    @staticmethod
    def _earliest_delivery_qdate(min_days: int) -> QDate:
        """Retorna a data mais cedo permitida, somando `min_days` dias úteis
        (segunda a sexta) a partir de hoje. Sábado e domingo não contam."""
        current = QDate.currentDate()
        if min_days <= 0:
            return current
        added = 0
        while added < min_days:
            current = current.addDays(1)
            if current.dayOfWeek() <= 5:  # 1=seg ... 5=sex
                added += 1
        return current

    @classmethod
    def _default_delivery_qdate(cls) -> QDate:
        """Data padrão do prazo de entrega: sempre 5 dias úteis à frente."""
        return cls._earliest_delivery_qdate(5)

    def _apply_min_delivery_constraint(self) -> None:
        """Aplica a data mínima de entrega ao seletor de prazo.
        Admin/gerente podem gravar abaixo do mínimo, então não recebem trava."""
        if getattr(session, "is_manager_or_admin", False):
            return
        try:
            min_days = int(res._read_file().get("min_delivery_business_days", 0) or 0)
        except Exception:
            min_days = 0
        if min_days <= 0:
            return
        earliest = self._earliest_delivery_qdate(min_days)
        self.input_prazo.setMinimumDate(earliest)
        if self.input_prazo.date() < earliest:
            self.input_prazo.setDate(earliest)
        self.input_prazo.setToolTip(
            f"Prazo mínimo de entrega: {min_days} dia(s) útil(eis) "
            f"(a partir de {earliest.toString('dd/MM/yyyy')})"
        )

    # ── Seção Cliente ─────────────────────────────────────────────────────────
    def _build_client_section(self) -> QFrame:
        card = _make_card()
        layout = QGridLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12,int(16*s)), max(10,int(12*s)),
                                   max(12,int(16*s)), max(10,int(12*s)))
        layout.setHorizontalSpacing(max(16,int(20*s)))
        layout.setVerticalSpacing(max(6,int(8*s)))

        # Cliente (busca em tempo real por nome, código ou CPF/CNPJ)
        layout.addWidget(_field_label("👤 CLIENTE", s), 0, 0)
        self.client_search = ClientSearchBox(s, self)
        self.client_search.client_selected.connect(self._on_client_selected)
        layout.addWidget(self.client_search, 1, 0)

        # Obra
        layout.addWidget(_field_label("🏗️ OBRA", s), 0, 1)
        self.input_obra = QLineEdit()
        self.input_obra.setPlaceholderText("Nome da obra")
        self.input_obra.setFixedHeight(max(30,int(36*s)))
        self.input_obra.setStyleSheet(_req_input_style(s))
        bind_uppercase_line_edit(self.input_obra)
        layout.addWidget(self.input_obra, 1, 1)

        # Fone
        layout.addWidget(_field_label("📞 FONE", s), 2, 0)
        self.input_fone = QLineEdit()
        self.input_fone.setPlaceholderText("(61) 9 9999-9999")
        self.input_fone.setFixedHeight(max(30,int(36*s)))
        self.input_fone.setStyleSheet(_req_input_style(s))
        self.input_fone.setMaxLength(16)
        self.input_fone.textEdited.connect(self._on_phone_edited)
        layout.addWidget(self.input_fone, 3, 0)

        # Endereço
        layout.addWidget(_field_label("📍 ENDEREÇO A ENTREGAR", s), 2, 1)
        self.input_address = QLineEdit()
        self.input_address.setPlaceholderText("Endereço completo de entrega")
        self.input_address.setFixedHeight(max(30,int(36*s)))
        self.input_address.setStyleSheet(_req_input_style(s))
        bind_uppercase_line_edit(self.input_address)
        layout.addWidget(self.input_address, 3, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return card

    # ── Itens (largura total) ─────────────────────────────────────────────────
    def _build_items_section(self) -> QFrame:
        s = self.scale
        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent; border:none;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(max(10, int(12 * s)))

        items_card = _make_card()
        items_layout = QVBoxLayout(items_card)
        items_layout.setContentsMargins(max(10, int(12*s)), max(10, int(12*s)),
                                         max(10, int(12*s)), max(10, int(12*s)))
        items_layout.setSpacing(max(8, int(10*s)))

        self.item_table = ItemTable(s)
        self.item_table.product_lookup_requested.connect(self._lookup_product_by_code)
        items_layout.addWidget(self.item_table)
        row.addWidget(items_card, 2)

        preview_card = _make_card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(max(10, int(12*s)), max(10, int(12*s)),
                                          max(10, int(12*s)), max(10, int(12*s)))
        preview_layout.setSpacing(max(8, int(10*s)))

        lbl_preview = QLabel("🎨 EDITOR DE DESENHO")
        lbl_preview.setStyleSheet(
            f"color:{_REQ_NEON_PRIMARY}; font-size:{max(9, int(11*s))}pt; font-weight:800; border:none;"
        )
        preview_layout.addWidget(lbl_preview)
        self.lbl_preview_title = lbl_preview

        lbl_preview_hint = QLabel("Prévia do desenho salvo na requisição.")
        lbl_preview_hint.setWordWrap(True)
        lbl_preview_hint.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; border:none;"
        )
        preview_layout.addWidget(lbl_preview_hint)
        self.lbl_preview_hint = lbl_preview_hint

        self.canvas_preview = CanvasPreview(s)
        preview_layout.addWidget(self.canvas_preview, 1)

        self.lbl_canvas_info = QLabel("Nenhum desenho salvo ainda.")
        self.lbl_canvas_info.setWordWrap(True)
        self.lbl_canvas_info.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; border:none;"
        )
        preview_layout.addWidget(self.lbl_canvas_info)
        self.lbl_canvas_info.setText("🖼️ Nenhum desenho salvo ainda.")

        btn_canvas = QPushButton("✏️ Abrir Editor de Desenho")
        btn_canvas.setFixedHeight(max(28, int(32*s)))
        btn_canvas.setStyleSheet(_req_secondary_btn_style(s))
        btn_canvas.clicked.connect(self._open_canvas_dialog)
        self.btn_canvas = btn_canvas

        btn_canvas_view = QPushButton("🖼️ Visualizar Desenho")
        btn_canvas_view.setFixedHeight(max(28, int(32*s)))
        btn_canvas_view.setStyleSheet(_req_secondary_btn_style(s))
        btn_canvas_view.clicked.connect(self._open_canvas_viewer)
        self.btn_canvas_view = btn_canvas_view

        btn_canvas_row = QHBoxLayout()
        btn_canvas_row.setContentsMargins(0, 0, 0, 0)
        btn_canvas_row.setSpacing(max(8, int(10 * s)))
        btn_canvas_row.addWidget(btn_canvas, 1)
        btn_canvas_row.addWidget(btn_canvas_view, 1)
        preview_layout.addLayout(btn_canvas_row)

        row.addWidget(preview_card, 1)
        return wrapper

    # ── Rodapé: Observação + Assinatura + QR ─────────────────────────────────
    def _build_bottom_section(self) -> QFrame:
        s = self.scale
        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent; border:none;")
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(10,int(12*s)))

        # Observação
        obs_card = _make_card()
        obs_layout = QVBoxLayout(obs_card)
        obs_layout.setContentsMargins(max(10,int(12*s)), max(10,int(12*s)),
                                       max(10,int(12*s)), max(10,int(12*s)))
        obs_layout.addWidget(_field_label("📝 OBSERVAÇÃO", s))
        self.input_obs = QTextEdit()
        self.input_obs.setPlaceholderText("Observações adicionais...")
        self.input_obs.setMaximumHeight(max(100,int(120*s)))
        self.input_obs.setStyleSheet(_req_text_edit_style(s))
        bind_uppercase_text_edit(self.input_obs)
        obs_layout.addWidget(self.input_obs)
        layout.addWidget(obs_card, 2)

        # Assinatura + QR
        sig_card = _make_card()
        sig_layout = QHBoxLayout(sig_card)
        sig_layout.setContentsMargins(max(10,int(12*s)), max(10,int(12*s)),
                                       max(10,int(12*s)), max(10,int(12*s)))

        sig_col = QVBoxLayout()
        sig_col.addWidget(_field_label("✍️ ASSINATURA DO CLIENTE", s))
        self.signature_preview = QLabel("Sem assinatura digital")
        self.signature_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signature_preview.setMinimumHeight(max(72, int(90 * s)))
        self.signature_preview.setStyleSheet(
            f"background:#fff; border:1px dashed {_REQ_NEON_PRIMARY}; border-radius:10px;"
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9 * s))}pt; font-style:italic;"
        )
        sig_col.addWidget(self.signature_preview, 1)

        sig_btn_row = QHBoxLayout()
        sig_btn_row.setContentsMargins(0, 0, 0, 0)
        sig_btn_row.setSpacing(max(8, int(10 * s)))

        self.btn_sign = QPushButton("Assinar")
        self.btn_sign.setFixedHeight(max(28, int(32 * s)))
        self.btn_sign.setStyleSheet(_req_secondary_btn_style(s))
        self.btn_sign.clicked.connect(self._open_signature_dialog)
        sig_btn_row.addWidget(self.btn_sign, 1)

        self.btn_clear_signature = QPushButton("Limpar assinatura")
        self.btn_clear_signature.setFixedHeight(max(28, int(32 * s)))
        self.btn_clear_signature.setStyleSheet(_req_secondary_btn_style(s))
        self.btn_clear_signature.clicked.connect(self._clear_signature)
        sig_btn_row.addWidget(self.btn_clear_signature, 1)

        sig_col.addLayout(sig_btn_row)
        sig_layout.addLayout(sig_col, 2)

        # QR Code
        qr_col = QVBoxLayout()
        qr_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(max(80,int(90*s)), max(80,int(90*s)))
        self.qr_label.setStyleSheet(
            f"border:1px solid {_rgba(_REQ_NEON_PRIMARY, 96)}; border-radius:10px; background:#fff;"
        )
        lbl_qr_txt = QLabel("🔳 QR CODE\nVendedor")
        lbl_qr_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_qr_txt.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(7,int(8*s))}pt; border:none;"
        )
        self.lbl_qr_title = lbl_qr_txt
        self.lbl_qr_contact = QLabel("")
        self.lbl_qr_contact.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_contact.setWordWrap(True)
        self.lbl_qr_contact.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(7,int(8*s))}pt; border:none;"
        )
        qr_col.addWidget(self.qr_label)
        qr_col.addWidget(lbl_qr_txt)
        qr_col.addWidget(self.lbl_qr_contact)
        sig_layout.addLayout(qr_col, 1)

        layout.addWidget(sig_card, 1)
        self._refresh_signature_preview()
        self._generate_qr()
        return wrapper

    # ── QR Code ───────────────────────────────────────────────────────────────
    def _generate_qr(self):
        if hasattr(self, "lbl_qr_contact"):
            self.lbl_qr_contact.setText(_format_phone_text(session.whatsapp) or "Sem contato cadastrado")
        if not hasattr(self, "qr_label"):
            return
        self.qr_label.clear()
        if not HAS_QR or not session.whatsapp:
            return
        try:
            phone = self._normalize_whatsapp_number(session.whatsapp)
            if not phone:
                return
            url = f"https://wa.me/{phone}"
            qr = qrcode.make(url)
            buf = io.BytesIO()
            qr.save(buf, format="PNG")
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.read())
            size = max(80, int(90 * self.scale))
            pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            self.qr_label.setPixmap(pix)
        except Exception:
            pass

    @staticmethod
    def _decode_signature_payload(value) -> bytes | None:
        if isinstance(value, (bytes, bytearray)):
            return bytes(value) if value else None
        if not isinstance(value, str):
            return None

        raw = value.strip()
        if not raw:
            return None

        if raw.lower().startswith("data:image"):
            parts = raw.split(",", 1)
            raw = parts[1] if len(parts) > 1 else ""

        raw = raw.replace("\n", "").replace("\r", "")
        if not raw:
            return None

        try:
            decoded = base64.b64decode(raw, validate=False)
        except Exception:
            return None
        return decoded or None

    def _extract_signature_from_requisition(self, data: dict | None) -> bytes | None:
        if not isinstance(data, dict):
            return None

        candidates = [
            data.get("signature_png"),
            data.get("signature_png_b64"),
            data.get("signature_base64"),
            data.get("client_signature"),
            data.get("client_signature_b64"),
        ]
        nested = data.get("signature")
        if isinstance(nested, dict):
            candidates.extend(
                [
                    nested.get("png"),
                    nested.get("png_b64"),
                    nested.get("base64"),
                ]
            )
        elif nested is not None:
            candidates.append(nested)

        for candidate in candidates:
            decoded = self._decode_signature_payload(candidate)
            if decoded:
                return decoded
        return None

    def _set_signature_png(self, signature_png_bytes: bytes | None) -> None:
        self._signature_png_bytes = signature_png_bytes if signature_png_bytes else None
        self._refresh_signature_preview()

    def _refresh_signature_preview(self) -> None:
        if not hasattr(self, "signature_preview"):
            return

        label = self.signature_preview
        label.setPixmap(QPixmap())
        if not self._signature_png_bytes:
            label.setText("Imprimir e assinar")
            label.setStyleSheet(
                f"background:#fff; border:1px dashed {_REQ_NEON_PRIMARY}; border-radius:10px;"
                f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9 * self.scale))}pt; font-style:italic;"
            )
            if hasattr(self, "btn_clear_signature"):
                self.btn_clear_signature.setEnabled(False)
            return

        pix = QPixmap()
        if not pix.loadFromData(self._signature_png_bytes, "PNG"):
            label.setText("Assinatura inválida")
            if hasattr(self, "btn_clear_signature"):
                self.btn_clear_signature.setEnabled(True)
            return

        target_w = max(1, label.width() - 12)
        target_h = max(1, label.height() - 12)
        scaled = pix.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setText("")
        label.setPixmap(scaled)
        label.setStyleSheet(
            f"background:#fff; border:1px solid {_rgba(_REQ_NEON_PRIMARY, 96)}; border-radius:10px;"
        )
        if hasattr(self, "btn_clear_signature"):
            self.btn_clear_signature.setEnabled(True)

    def _open_signature_dialog(self) -> None:
        dialog = SignatureDialog(self.scale, self._signature_png_bytes, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_signature_png(dialog.signature_png_bytes())

    def _clear_signature(self) -> None:
        if not self._signature_png_bytes:
            return
        self._set_signature_png(None)

    def showEvent(self, event):
        super().showEvent(event)
        self._generate_qr()
        self._refresh_signature_preview()

    def refresh_logged_user(self):
        if hasattr(self, "lbl_vendor"):
            self.lbl_vendor.setText((session.user_name or "--").upper())
        self._generate_qr()

    # ── WhatsApp do cliente ───────────────────────────────────────────────────
    def _send_whatsapp_client(self):
        if not self.req_id:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Salve a requisição antes de enviar o PDF pelo WhatsApp.",
            )
            return

        self._set_whatsapp_busy(True)
        thread, worker = _run_in_thread(
            api.get_requisition,
            self.req_id,
            on_result=self._open_saved_pdf_for_whatsapp,
            on_error=self._on_whatsapp_error,
        )
        self._threads.append((thread, worker))

    def _set_whatsapp_busy(self, busy: bool):
        if not hasattr(self, "btn_whatsapp"):
            return

        self.btn_whatsapp.setEnabled(not busy)
        self.btn_whatsapp.setText("⏳ PREPARANDO PDF..." if busy else "📲 ENVIAR WHATSAPP")

    def _set_print_busy(self, busy: bool):
        if not hasattr(self, "btn_print"):
            return

        self.btn_print.setEnabled(not busy)
        self.btn_print.setText("PREPARANDO IMPRESSÃO..." if busy else "IMPRIMIR")

    def _update_print_button_visual(self) -> None:
        if not hasattr(self, "btn_print"):
            return

        icon = None
        for icon_name in ("SP_DialogPrintButton", "SP_PrinterIcon"):
            std_icon = getattr(QStyle.StandardPixmap, icon_name, None)
            if std_icon is None:
                continue
            candidate = self.style().standardIcon(std_icon)
            if not candidate.isNull():
                icon = candidate
                break

        if icon and not icon.isNull():
            side = max(16, int(18 * self.scale))
            self.btn_print.setIcon(icon)
            self.btn_print.setIconSize(QSize(side, side))

    def _print_requisition_pdf(self):
        self._set_print_busy(True)
        try:
            pdf_path = self._find_saved_pdf_for_print()
            self._print_pdf_file(pdf_path)
        except Exception as exc:
            QMessageBox.critical(self, "Impressão", str(exc))
        finally:
            self._set_print_busy(False)

    def _on_whatsapp_error(self, msg: str):
        self._set_whatsapp_busy(False)
        QMessageBox.critical(self, "WhatsApp", msg)

    def _open_saved_pdf_for_whatsapp(self, req: dict):
        try:
            digits = self._normalize_whatsapp_number(req.get("phone") or self.input_fone.text())
            if not digits:
                QMessageBox.warning(
                    self,
                    "WhatsApp",
                    "A requisição salva não possui um telefone válido para envio.",
                )
                return

            pdf_path = self._generate_saved_pdf(req)

            import os
            import webbrowser

            try:
                os.startfile(os.path.dirname(pdf_path))
            except Exception:
                pass

            webbrowser.open(f"https://wa.me/{digits}")
            QMessageBox.information(
                self,
                "WhatsApp",
                "O PDF salvo foi gerado e a conversa do cliente foi aberta.\n\n"
                f"Arquivo pronto:\n{pdf_path}\n\n"
                "O anexo ainda precisa ser enviado manualmente porque o projeto "
                "não tem uma integração configurada de envio de documentos pelo WhatsApp.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "WhatsApp", str(exc))
        finally:
            self._set_whatsapp_busy(False)

    def _normalize_whatsapp_number(self, raw: str | None) -> str:
        import re

        digits = re.sub(r"\D", "", (raw or "").strip())
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = "55" + digits
        return digits

    def _build_current_pdf_payload(self) -> tuple[dict, dict, str, str, bytes | None]:
        data = self.get_form_data()
        ped_number = (data.get("ped_number") or "").strip()
        client = self.client_search.get_selected()

        if not ped_number or not ped_number.isdigit() or int(ped_number) == 0:
            raise RuntimeError("Informe um número de PED válido antes de imprimir.")

        if not data.get("client_id") or not client:
            raise RuntimeError("Selecione um cliente antes de imprimir.")

        req = dict(data)
        if self.req_id:
            req["id"] = self.req_id
        req["client_name"] = client.get("name") or ""
        req["client_code"] = client.get("code") or ""
        req["vendor_name"] = session.user_name or ""
        req["vendor_whatsapp"] = session.whatsapp or ""
        req["emission_date"] = local_now().isoformat()

        client_payload = {
            "id": client.get("id"),
            "code": client.get("code") or "",
            "name": client.get("name") or "",
            "phone": self.input_fone.text().strip() or client.get("phone") or "",
            "cnpj": client.get("cnpj") or "",
        }
        obs = self.input_obs.toPlainText().strip()
        return req, client_payload, obs, self._canvas_json, self._signature_png_bytes

    def _find_saved_pdf_for_print(self) -> str:
        ped_number = self.input_ped.text().strip()
        if not ped_number or not ped_number.isdigit() or int(ped_number) == 0:
            raise RuntimeError("Informe um número de requisição válido antes de imprimir.")

        req_hint = {
            "vendor_code": getattr(self, "_req_vendor_code", ""),
            "vendor_name": getattr(self, "_req_vendor_name", ""),
        }
        folder = self._resolve_pdf_output_folder(require_configured_folder=True, req=req_hint)
        if not os.path.isdir(folder):
            raise RuntimeError("A pasta de PDFs configurada não foi encontrada.")

        ped_file = ped_number.zfill(6)
        prefix = f"REQ-{ped_file}-"

        try:
            pdf_candidates = [
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if name.lower().endswith(".pdf") and name.upper().startswith(prefix.upper())
            ]
        except OSError as exc:
            raise RuntimeError(f"Não foi possível acessar a pasta de PDFs.\n\n{exc}") from exc

        if not pdf_candidates:
            raise RuntimeError(
                "Não foi encontrado um PDF salvo para essa requisição na pasta configurada.\n\n"
                f"Requisição: {ped_file}"
            )

        pdf_candidates.sort(
            key=lambda path: (os.path.getmtime(path), os.path.basename(path).lower()),
            reverse=True,
        )
        return pdf_candidates[0]

    def _resolve_pdf_output_folder(
        self,
        require_configured_folder: bool = True,
        req: dict | None = None,
    ) -> str:
        from ..core.pdf_folders import vendor_subfolder as _vendor_subfolder
        base = res.pdf_folder.strip()
        if base:
            subfolder = _vendor_subfolder(
                session.user_code,
                session.user_name,
                session.role,
                str((req or {}).get("vendor_code") or ""),
                str((req or {}).get("vendor_name") or ""),
            )
            return os.path.join(base, subfolder)

        if require_configured_folder:
            raise RuntimeError(
                "Defina a pasta de PDFs nas Configurações antes de localizar ou gerar o PDF da requisição."
            )

        folder = os.path.join(tempfile.gettempdir(), "requisicoes-pdf")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _generate_pdf_file(
        self,
        req: dict,
        client: dict | None,
        obs: str,
        canvas_json: str,
        signature_png_bytes: bytes | None = None,
        *,
        require_configured_folder: bool,
    ) -> str:
        try:
            from ..services.pdf_generator import generate_pdf, HAS_REPORTLAB
        except ImportError as exc:
            raise RuntimeError("A geração de PDF não está disponível neste ambiente.") from exc

        if not HAS_REPORTLAB:
            raise RuntimeError("A geração de PDF está indisponível porque o ReportLab não está instalado.")

        folder = self._resolve_pdf_output_folder(require_configured_folder=require_configured_folder, req=req)
        return generate_pdf(
            req,
            client,
            obs or req.get("obs") or "",
            folder,
            canvas_json,
            signature_png_bytes=signature_png_bytes,
        )

    def _generate_saved_pdf(self, req: dict) -> str:
        client = {
            "code": req.get("client_code") or "",
            "name": req.get("client_name") or "",
            "phone": req.get("phone") or "",
        }
        canvas_json = (req.get("canvas") or {}).get("json_data") or "{}"
        signature_png = self._signature_png_bytes or self._extract_signature_from_requisition(req)
        return self._generate_pdf_file(
            req,
            client,
            req.get("obs") or "",
            canvas_json,
            signature_png,
            require_configured_folder=True,
        )

    def _generate_current_pdf(self) -> str:
        req, client, obs, canvas_json, signature_png = self._build_current_pdf_payload()
        return self._generate_pdf_file(
            req,
            client,
            obs,
            canvas_json,
            signature_png,
            require_configured_folder=False,
        )

    def _prepare_local_pdf_for_print(self, pdf_path: str) -> str:
        if not os.path.isfile(pdf_path):
            raise RuntimeError("O PDF da requisição não foi encontrado para impressão.")

        temp_dir = os.path.join(tempfile.gettempdir(), "requisicoes-print")
        os.makedirs(temp_dir, exist_ok=True)

        ped_number = self.input_ped.text().strip() or "000000"
        fd, local_pdf_path = tempfile.mkstemp(
            prefix=f"req-{ped_number.zfill(6)}-",
            suffix=".pdf",
            dir=temp_dir,
        )
        os.close(fd)

        try:
            shutil.copyfile(pdf_path, local_pdf_path)
        except OSError as exc:
            try:
                os.remove(local_pdf_path)
            except OSError:
                pass
            raise RuntimeError(
                "Não foi possível preparar uma cópia local do PDF para impressão.\n\n"
                f"{exc}"
            ) from exc

        return local_pdf_path

    def _print_pdf_file(self, pdf_path: str) -> bool:
        try:
            from PySide6.QtCore import QRect, QSize
            from PySide6.QtGui import QPageLayout, QPainter
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError as exc:
            raise RuntimeError("A seleção de impressora não está disponível neste ambiente.") from exc

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(f"Requisicao {self.input_ped.text().strip() or '000000'}")
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setFullPage(True)

        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Imprimir requisição")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        if printer.outputFormat() == QPrinter.OutputFormat.NativeFormat:
            printer.setOutputFileName("")

        local_pdf_path = self._prepare_local_pdf_for_print(pdf_path)
        document = QPdfDocument(self)
        painter = QPainter()
        try:
            load_result = document.load(local_pdf_path)
            if load_result != QPdfDocument.Error.None_:
                raise RuntimeError(
                    f"Não foi possível abrir o PDF da requisição para impressão ({load_result.name})."
                )
            if document.pageCount() <= 0:
                raise RuntimeError("O PDF da requisição não possui páginas para imprimir.")

            if not painter.begin(printer):
                raise RuntimeError("Não foi possível iniciar a impressão na impressora selecionada.")

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            for page_index in range(document.pageCount()):
                if page_index:
                    printer.newPage()

                page_size = document.pagePointSize(page_index)
                target_rect = printer.paperRect(QPrinter.Unit.DevicePixel)
                if target_rect.width() <= 0 or target_rect.height() <= 0:
                    target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                target_x = int(round(target_rect.x()))
                target_y = int(round(target_rect.y()))
                target_width = max(1, int(round(target_rect.width())))
                target_height = max(1, int(round(target_rect.height())))
                painter.fillRect(QRect(target_x, target_y, target_width, target_height), Qt.GlobalColor.white)

                width = max(1, int((page_size.width() / 72.0) * 300))
                height = max(1, int((page_size.height() / 72.0) * 300))
                image = document.render(page_index, QSize(width, height))
                if image.isNull():
                    raise RuntimeError(f"Não foi possível renderizar a página {page_index + 1} para impressão.")

                scaled_size = image.size()
                scaled_size.scale(target_width, target_height, Qt.AspectRatioMode.KeepAspectRatio)
                x = target_x + max(0, (target_width - scaled_size.width()) // 2)
                y = target_y + max(0, (target_height - scaled_size.height()) // 2)
                painter.drawImage(QRect(x, y, scaled_size.width(), scaled_size.height()), image)
        finally:
            if painter.isActive():
                painter.end()
            if hasattr(document, "close"):
                document.close()
            try:
                os.remove(local_pdf_path)
            except OSError:
                pass

        return True

    # ── Calculadora de Peso ───────────────────────────────────────────────────
    def _open_weight_calculator(self):
        s = self.scale
        dlg = QDialog(self)
        dlg.setWindowTitle("Calculadora de Peso")
        dlg.setModal(True)
        dlg.setMinimumWidth(max(340, int(380 * s)))
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(_req_dialog_style())

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(max(20, int(24 * s)), max(20, int(24 * s)),
                                   max(20, int(24 * s)), max(20, int(24 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        # Título
        lbl_title = QLabel("⚖️  Calculadora de Peso")
        lbl_title.setStyleSheet(
            f"color:{_REQ_NEON_PRIMARY}; font-size:{max(11, int(13 * s))}pt; font-weight:800;"
        )
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_REQ_BORDER_SOFT};")
        layout.addWidget(sep)

        # Campos de entrada
        grid = QGridLayout()
        grid.setSpacing(max(8, int(10 * s)))
        grid.setColumnStretch(1, 1)

        fs = max(9, int(10 * s))
        lbl_style = f"font-size:{fs}pt; font-weight:700; color:{_REQ_TEXT_MUTED};"

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(lbl_style)
            return l

        def _input(placeholder="", default=""):
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setText(default)
            inp.setFixedHeight(max(30, int(36 * s)))
            inp.setStyleSheet(_req_input_style(s))
            validator = QRegularExpressionValidator(
                QRegularExpression(r"[0-9]*\.?[0-9]*")
            )
            inp.setValidator(validator)
            return inp

        inp_qnt   = _input("ex: 10", "")
        inp_comp  = _input("mm", "")
        inp_larg  = _input("mm", "")
        inp_chapa = _input("mm", "")
        inp_var   = _input("constante", "7.865")
        inp_var.setReadOnly(True)
        inp_var.setStyleSheet(
            inp_var.styleSheet() +
            f"background-color:{_REQ_SURFACE_ALT}; color:{_REQ_TEXT_MUTED};"
        )

        grid.addWidget(_lbl("QNT:"),          0, 0)
        grid.addWidget(inp_qnt,               0, 1)
        grid.addWidget(_lbl("COMP (mm):"),    1, 0)
        grid.addWidget(inp_comp,              1, 1)
        grid.addWidget(_lbl("LARG. TOTAL (mm):"), 2, 0)
        grid.addWidget(inp_larg,              2, 1)
        grid.addWidget(_lbl("CHAPA (mm):"),   3, 0)
        grid.addWidget(inp_chapa,             3, 1)
        grid.addWidget(_lbl("VARIÁVEL:"),     4, 0)
        grid.addWidget(inp_var,               4, 1)
        layout.addLayout(grid)

        # Separador resultado
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{_REQ_BORDER_SOFT};")
        layout.addWidget(sep2)

        # Label de resultado
        lbl_result = QLabel("PESO = —")
        lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_result.setStyleSheet(
            f"color:{_REQ_NEON_PRIMARY}; font-size:{max(14, int(16 * s))}pt;"
            f"font-weight:800; padding:{max(8, int(10 * s))}px;"
            f"background-color:{_REQ_SURFACE_BG}; border:1px solid {_rgba(_REQ_NEON_PRIMARY, 92)};"
            f"border-radius:12px;"
        )
        layout.addWidget(lbl_result)

        lbl_hint = QLabel("Resultado apenas para consulta — não salvo na requisição.")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(7, int(8 * s))}pt; font-style:italic;"
        )
        layout.addWidget(lbl_hint)

        # Botão fechar
        btn_fechar = QPushButton("Fechar")
        btn_fechar.setFixedHeight(max(34, int(40 * s)))
        btn_fechar.setStyleSheet(_req_secondary_btn_style(s))
        btn_fechar.clicked.connect(dlg.accept)
        layout.addWidget(btn_fechar, alignment=Qt.AlignmentFlag.AlignRight)

        # Lógica de cálculo — recalcula a cada digitação
        def _recalculate():
            try:
                qnt   = float(inp_qnt.text().replace(",", ".") or "0")
                comp  = float(inp_comp.text().replace(",", ".") or "0")
                larg  = float(inp_larg.text().replace(",", ".") or "0")
                chapa = float(inp_chapa.text().replace(",", ".") or "0")
                var   = float(inp_var.text().replace(",", ".") or "7.865")
                peso  = (qnt * comp * larg * chapa * var) / 1_000_000
                txt   = f"{peso:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
                lbl_result.setText(f"PESO = {txt} kg")
            except (ValueError, ZeroDivisionError):
                lbl_result.setText("PESO = —")

        inp_qnt.textChanged.connect(_recalculate)
        inp_comp.textChanged.connect(_recalculate)
        inp_larg.textChanged.connect(_recalculate)
        inp_chapa.textChanged.connect(_recalculate)
        # inp_var é fixo — sem listener necessário

        dlg.exec()

    def _send_to_production(self):
        if not self.req_id:
            QMessageBox.warning(
                self,
                "Produção",
                "Salve a requisição antes de enviar para produção.",
            )
            return

        if not (self.chk_retirada.isChecked() or self.chk_entrega.isChecked()):
            QMessageBox.warning(
                self,
                "Produção",
                "Marque Retirada ou Entrega para enviar para produção.",
            )
            return

        invoice_action = self._confirm_invoice_before_send()
        if invoice_action == "cancel":
            return
        if invoice_action == "save":
            self.save_requested.emit()
            return

        destination = self._pick_production_destination()
        if not destination:
            return

        previous_status = getattr(self.status_badge, "_status", "em_andamento")
        self.status_badge.set_status("aguardando_recebimento")

        thread, worker = _run_in_thread(
            api.update_status,
            self.req_id,
            "aguardando_recebimento",
            _build_production_note(PROD_SEND, destination),
            on_result=lambda req, dest=destination: self._on_sent_to_production(req, dest),
            on_error=lambda msg, prev=previous_status: self._on_send_to_production_error(msg, prev),
        )
        self._threads.append((thread, worker))

    def _confirm_invoice_before_send(self) -> str:
        ped_number = (self.input_ped.text() or "").strip() or "sem PED"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Este pedido foi faturado")
        box.setText(f"Este pedido foi faturado ({ped_number})?")
        box.setTextFormat(Qt.TextFormat.PlainText)

        btn_yes = box.addButton("Sim", QMessageBox.ButtonRole.YesRole)
        btn_save = box.addButton("Apenas salvar", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

        box.setDefaultButton(btn_yes)
        box.setEscapeButton(btn_cancel)
        apply_message_box_theme(box)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_yes:
            return "yes"
        if clicked == btn_save:
            return "save"
        return "cancel"

    def _pick_production_destination(self) -> str | None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Enviar para produção")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText("Para qual produção deseja enviar a requisição?")

        btn_ar = msg.addButton("A&&R", QMessageBox.ButtonRole.AcceptRole)
        btn_pinheiro = msg.addButton("Pinheiro Indústria", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(msg)

        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_ar:
            return "A&R"
        if clicked == btn_pinheiro:
            return "Pinheiro Indústria"
        return None

    def _on_sent_to_production(self, req: dict, destination: str):
        self.status_badge.set_status(req.get("status", "aguardando_recebimento"))
        QMessageBox.information(
            self,
            "Produção",
            f"Requisição enviada para {destination}.",
        )

    def _on_send_to_production_error(self, msg: str, previous_status: str = "em_andamento"):
        self.status_badge.set_status(previous_status)
        friendly = msg
        if "aguardando_recebimento" in msg and "Input should be" in msg:
            friendly = (
                "O servidor ainda não reconhece o novo status de produção.\n\n"
                "Reinicie o servidor da API e tente novamente."
            )
        QMessageBox.critical(self, "Produção", friendly)

    # ── Editor de desenho (modal) ─────────────────────────────────────────────
    def _open_canvas_dialog(self):
        dlg = CanvasDialog(self._canvas_json, self.scale, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._canvas_json = dlg.get_json()
            self._update_canvas_preview()

    def _open_canvas_viewer(self):
        dlg = CanvasViewerDialog(self._canvas_json, self.scale, self)
        dlg.exec()

    # ── Clientes ──────────────────────────────────────────────────────────────
    def _load_clients(self):
        t, w = _run_in_thread(api.list_clients,
                               on_result=self._on_clients_loaded,
                               on_error=lambda e: None)
        self._threads.append((t, w))

    def _on_clients_loaded(self, clients: list):
        self._clients = clients
        self.client_search.set_clients(clients)

    def _on_client_selected(self, client: dict):
        """Preenche Fone e Endereço automaticamente ao selecionar um cliente."""
        if not client:
            return
        self._set_phone_text(client.get("phone") or "")
        addr_parts = [
            client.get("address") or "",
            client.get("city") or "",
            client.get("state") or "",
        ]
        self.input_address.setText(", ".join(p for p in addr_parts if p))

    def _on_phone_edited(self, text: str):
        self._set_phone_text(text)

    def _set_phone_text(self, raw: str):
        formatted = _format_phone_text(raw)
        if self.input_fone.text() == formatted:
            return
        self.input_fone.blockSignals(True)
        self.input_fone.setText(formatted)
        self.input_fone.setCursorPosition(len(formatted))
        self.input_fone.blockSignals(False)

    # ── Eventos ───────────────────────────────────────────────────────────────
    def _lookup_product_by_code(self, row: int, code: str):
        lookup_code = code.strip()
        if not lookup_code:
            return

        t, w = _run_in_thread(
            api.list_products, "", lookup_code, 1,
            on_result=lambda products, r=row, c=lookup_code: self._apply_product_lookup(r, c, products),
            on_error=lambda _: None,
        )
        self._threads.append((t, w))

    def _apply_product_lookup(self, row: int, requested_code: str, products: list):
        if self.item_table.get_product_code(row).strip() != requested_code:
            return
        if products:
            self.item_table.apply_product_lookup(row, products[0])

    def _update_canvas_preview(self):
        if not hasattr(self, "canvas_preview"):
            return

        self.canvas_preview.set_json(self._canvas_json)
        result = self.canvas_preview.last_result
        pdf_path = result.get("pdf") or ""
        dwg_path = result.get("dwg") or ""

        if result.get("items"):
            self.lbl_canvas_info.setText("Prévia atual do desenho técnico.")
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        else:
            self.lbl_canvas_info.setText("Nenhum desenho salvo ainda.")
        if result.get("items"):
            self.lbl_canvas_info.setText("◉ Prévia atual do desenho técnico.")
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"▤ Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        else:
            self.lbl_canvas_info.setText("◌ Nenhum desenho salvo ainda.")

        if result.get("items"):
            self.lbl_canvas_info.setText("🎨 Prévia atual do desenho técnico.")
        elif pdf_path and dwg_path:
            self.lbl_canvas_info.setText(
                f"📎 Referências anexadas: PDF ({os.path.basename(pdf_path)}) | DWG ({os.path.basename(dwg_path)})"
            )
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"📎 Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        elif dwg_path:
            self.lbl_canvas_info.setText(
                f"📎 Anexo DWG: {os.path.basename(dwg_path)}"
            )
        else:
            self.lbl_canvas_info.setText("🖼️ Nenhum desenho salvo ainda.")

    def _set_form_locked(self, locked: bool, message: str = ""):
        for widget in getattr(self, "_editable_widgets", []):
            widget.setEnabled(not locked)

        if hasattr(self, "btn_whatsapp"):
            self.btn_whatsapp.setEnabled(True)
        if hasattr(self, "btn_canvas_view"):
            self.btn_canvas_view.setEnabled(True)

        if hasattr(self, "lock_label"):
            self.lock_label.setVisible(locked)
            self.lock_label.setText(message if locked else "")

    def has_unsaved_data(self) -> bool:
        if self.req_id is not None:
            return True
        if self.input_ped.text().strip():
            return True
        if self.input_obra.text().strip():
            return True
        if self.input_fone.text().strip():
            return True
        if self.input_address.text().strip():
            return True
        if self.input_obs.toPlainText().strip():
            return True
        if self.client_search.get_client_id() is not None:
            return True
        if self.input_prazo.date() != self._default_delivery_qdate():
            return True
        if self.chk_retirada.isChecked() or self.chk_entrega.isChecked():
            return True
        if self.item_table.get_items():
            return True
        if self._canvas_json not in ("", "{}"):
            return True
        return bool(self._signature_png_bytes)

    # ── API pública ──────────────────────────────────────────────────────────
    def get_form_data(self) -> dict:
        client_id = self.client_search.get_client_id()
        prazo = self.input_prazo.date().toString("yyyy-MM-dd")
        total_weight = self.item_table.get_total_weight()
        signature_b64 = None
        if self._signature_png_bytes:
            signature_b64 = base64.b64encode(self._signature_png_bytes).decode("ascii")
        return {
            "ped_number":       self.input_ped.text().strip(),
            "client_id":        client_id,
            "obra":             self.input_obra.text().strip() or None,
            "delivery_date":    prazo,
            "retirada":         self.chk_retirada.isChecked(),
            "entrega":          self.chk_entrega.isChecked(),
            "phone":            self.input_fone.text().strip() or None,
            "delivery_address": self.input_address.text().strip() or None,
            "weight":           total_weight,
            "items":            self.item_table.get_items(),
            "obs":              self.input_obs.toPlainText().strip() or None,
            "signature_png_b64": signature_b64,
            "canvas_json":      self._canvas_json or "{}",
            "expected_updated_at": self._loaded_updated_at,
        }

    def load_requisition(self, data: dict, read_only: bool = False):
        """Popula o formulário com dados de uma requisição existente."""
        self._set_form_locked(False)
        self.req_id = data.get("id")
        # Versão carregada para a trava otimista de concorrência (P1.6)
        self._loaded_updated_at = data.get("updated_at")
        # Guarda info do vendedor para uso em _find_saved_pdf_for_print
        self._req_vendor_code = str(data.get("vendor_code") or "")
        self._req_vendor_name = str(data.get("vendor_name") or "")
        self.input_ped.setText(str(data.get("ped_number") or ""))
        self.input_obra.setText(data.get("obra") or "")
        self._set_phone_text(data.get("phone") or "")
        self.input_address.setText(data.get("delivery_address") or "")

        # Requisição existente: libera a data mínima para exibir o prazo salvo,
        # mesmo que seja anterior ao mínimo vigente.
        self.input_prazo.setMinimumDate(QDate(2000, 1, 1))
        self.input_prazo.setToolTip("")
        delivery = data.get("delivery_date")
        if delivery:
            qd = QDate.fromString(str(delivery)[:10], "yyyy-MM-dd")
            self.input_prazo.setDate(qd)

        self.chk_retirada.setChecked(data.get("retirada", False))
        self.chk_entrega.setChecked(data.get("entrega", False))
        self.status_badge.set_status(data.get("status", "em_andamento"))
        self.lbl_ped_num.setText(f"#{str(data.get('ped_number','0')).zfill(6)}")

        # Cliente
        client_id = data.get("client_id")
        if client_id:
            self.client_search.set_client_by_id(client_id)

        # Itens
        self.item_table.set_items(data.get("items", []))
        self.input_obs.setPlainText(data.get("obs") or "")

        # Canvas — armazena JSON; será carregado no dialog ao abrir
        canvas_data = data.get("canvas")
        self._canvas_json = (canvas_data or {}).get("json_data") or "{}"
        self._update_canvas_preview()
        self._set_signature_png(self._extract_signature_from_requisition(data))

        if read_only:
            self._set_form_locked(
                True,
                "Requisicao aberta em modo somente leitura para este perfil.",
            )
        elif data.get("finalized_at"):
            self._set_form_locked(
                True,
                "🏭 Produção recebida ou finalizada. Esta requisição não pode mais ser editada.",
            )

    def reset(self):
        """Limpa o formulário para nova requisição."""
        self._set_form_locked(False)
        self.req_id = None
        self._loaded_updated_at = None
        self.input_ped.clear()
        self.input_obra.clear()
        self.input_fone.clear()
        self.input_address.clear()
        self.input_obs.clear()
        self.input_prazo.setDate(self._default_delivery_qdate())
        self._apply_min_delivery_constraint()
        self.chk_retirada.setChecked(False)
        self.chk_entrega.setChecked(False)
        self.client_search.clear()
        self.status_badge.set_status("em_andamento")
        self.lbl_ped_num.setText("#000000")
        self.item_table.set_items([])
        self._canvas_json = "{}"
        self._update_canvas_preview()
        self._set_signature_png(None)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self._page_scroll.setStyleSheet(f"QScrollArea {{ background:{bg}; border:none; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#requisitionFormContent {{ background:{bg}; }}")
        self.input_ped.setStyleSheet(_req_input_style(s, bold=True, accent=_REQ_NEON_PRIMARY))
        self.input_obs.setStyleSheet(_req_text_edit_style(s))
        self.input_obra.setStyleSheet(_req_input_style(s))
        self.input_prazo.setStyleSheet(_req_input_style(s))
        self.input_fone.setStyleSheet(_req_input_style(s))
        self.input_address.setStyleSheet(_req_input_style(s))
        chk_style = _req_checkbox_style(s)
        self.chk_retirada.setStyleSheet(chk_style)
        self.chk_entrega.setStyleSheet(chk_style)
        self.client_search.apply_theme(s)
        self.status_badge.apply_theme(s)
        self.item_table.apply_theme()
        self.btn_calc.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        self.btn_production.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        self.btn_whatsapp.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        self.btn_print.setStyleSheet(_emphasized_btn_style(_req_secondary_btn_style(s)))
        self._update_print_button_visual()
        self.btn_save.setStyleSheet(_emphasized_btn_style(_req_primary_btn_style(s)))
        self.btn_canvas.setStyleSheet(_req_secondary_btn_style(s))
        self.btn_canvas_view.setStyleSheet(_req_secondary_btn_style(s))
        if hasattr(self, "btn_sign"):
            self.btn_sign.setStyleSheet(_req_secondary_btn_style(s))
        if hasattr(self, "btn_clear_signature"):
            self.btn_clear_signature.setStyleSheet(_req_secondary_btn_style(s))
        if hasattr(self, "btn_guide"):
            self.btn_guide.setStyleSheet(_req_round_icon_btn_style(s, self.btn_guide.width()))
        if hasattr(self, "btn_search_req"):
            self.btn_search_req.setStyleSheet(_req_round_icon_btn_style(s, self.btn_search_req.width()))
        if hasattr(self, "lbl_req_title"):
            self.lbl_req_title.setStyleSheet(
                f"font-size:{max(10,int(12*s))}pt; font-weight:700; border:none; color:{_REQ_TEXT_MUTED};"
            )
        self.lbl_ped_num.setStyleSheet(
            f"font-size:{max(16,int(20*s))}pt; font-weight:800; border:none; color:{_REQ_NEON_PRIMARY};"
        )
        self.lock_label.setStyleSheet(
            f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; font-style:italic; border:none;"
        )
        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.setStyleSheet(
                f"color:{_REQ_NEON_PRIMARY}; font-size:{max(9, int(11*s))}pt; font-weight:800; border:none;"
            )
        if hasattr(self, "lbl_preview_hint"):
            self.lbl_preview_hint.setStyleSheet(
                f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; border:none;"
            )
        if hasattr(self, "lbl_canvas_info"):
            self.lbl_canvas_info.setStyleSheet(
                f"color:{_REQ_TEXT_MUTED}; font-size:{max(8, int(9*s))}pt; border:none;"
            )
        if hasattr(self, "lbl_qr_title"):
            self.lbl_qr_title.setStyleSheet(
                f"color:{_REQ_TEXT_MUTED}; font-size:{max(7,int(8*s))}pt; border:none;"
            )
        if hasattr(self, "lbl_qr_contact"):
            self.lbl_qr_contact.setStyleSheet(
                f"color:{_REQ_TEXT_MUTED}; font-size:{max(7,int(8*s))}pt; border:none;"
            )
        if hasattr(self, "qr_label"):
            self.qr_label.setStyleSheet(
                f"border:1px solid {_rgba(_REQ_NEON_PRIMARY, 96)}; border-radius:10px; background:#fff;"
            )
        self._refresh_signature_preview()
