from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.datetime_utils import (
    format_date as _format_date,
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)


DASH_BG = "#F4F7FB"
DASH_SURFACE = "#FFFFFF"
DASH_PRIMARY = "#1E3A5F"
DASH_SECONDARY = "#27496D"
DASH_DANGER = "#DC2626"
DASH_WARNING = "#F59E0B"
DASH_SLATE = "#334155"
DASH_TEXT = "#0F172A"
DASH_MUTED = "#64748B"
DASH_BORDER = "#E2E8F0"
DASH_ROW_ALT = "#F8FBFF"

COLS = ["PED", "CLIENTE", "OBRA", "VENDEDOR", "DATA", "STATUS"]


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(DASH_TEXT)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


def _make_card(
    scale: float,
    background: str | None = None,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    card = QFrame()
    card.setObjectName("historyCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    bg = background or DASH_SURFACE
    border = f"1px solid {border_color}" if border_color else "none"
    hover = hover_background or bg
    card.setStyleSheet(
        f"QFrame#historyCard {{"
        f"  background:{bg}; border:{border}; border-radius:{radius}px;"
        f"}}"
        f"QFrame#historyCard:hover {{"
        f"  background:{hover}; border:{border};"
        f"}}"
    )
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DASH_SURFACE}; color:{DASH_PRIMARY};"
        f"  border:1px solid {DASH_BORDER}; outline:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{DASH_ROW_ALT}; border-color:{_rgba(DASH_PRIMARY, 70)}; }}"
        f"QPushButton:pressed {{ background:#E7EEF7; }}"
        f"QPushButton:disabled {{ background:#E5EAF2; color:#97A3B6; border-color:#E5EAF2; }}"
    )


def _primary_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DASH_PRIMARY}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{DASH_SECONDARY}; }}"
        f"QPushButton:pressed {{ background:#152D49; }}"
        f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
    )


def _field_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QLineEdit, QComboBox {{"
        f"  background:{DASH_SURFACE}; border:1px solid {DASH_BORDER}; border-radius:14px;"
        f"  padding:9px 12px; font-size:{fs}pt; color:{DASH_TEXT};"
        f"  selection-background-color:{_rgba(DASH_PRIMARY, 24)}; selection-color:{DASH_TEXT};"
        f"}}"
        f"QLineEdit {{ placeholder-text-color:{DASH_MUTED}; }}"
        f"QLineEdit:focus, QComboBox:focus {{ border:1px solid {_rgba(DASH_PRIMARY, 88)}; }}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{DASH_SURFACE}; color:{DASH_TEXT}; border:1px solid {DASH_BORDER};"
        f"  selection-background-color:{_rgba(DASH_PRIMARY, 18)}; selection-color:{DASH_TEXT};"
        f"}}"
    )


class HistoryWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, status: str = "", search: str = ""):
        super().__init__()
        self.status = status
        self.search = search

    def run(self):
        try:
            if self.status == "aguardando_recebimento":
                reqs = api.list_requisitions("", self.search, limit=100)
                reqs = [
                    req for req in reqs
                    if isinstance(req, dict) and req.get("status") == "aguardando_recebimento"
                ]
                self.result.emit(reqs)
            else:
                self.result.emit(api.list_requisitions(self.status, self.search, limit=100))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class HistoryView(QWidget):
    open_requisition = Signal(int)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._reqs: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = DASH_BG
        self.setObjectName("historyView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#historyView {{ background:{page_bg}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Histórico / Busca")
        title.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Consulta operacional de requisições por status, pedido, cliente, obra e vendedor."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = _make_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(16, int(18 * s)),
            hover_background=DASH_SURFACE,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.updated_label = QLabel("Pronto para consultar")
        self.updated_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        right_col.addWidget(info_card)
        right_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(right_col)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(DASH_DANGER, 18)}; color:{DASH_DANGER};"
            f"border:1px solid {_rgba(DASH_DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        root.addWidget(self.error_label)

        filter_card = _make_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
        )
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                         max(16, int(20 * s)), max(14, int(18 * s)))
        filter_layout.setSpacing(max(10, int(12 * s)))

        filter_accent = QFrame()
        filter_accent.setFixedHeight(max(4, int(5 * s)))
        filter_accent.setStyleSheet(
            f"background:{DASH_SECONDARY}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        filter_layout.addWidget(filter_accent)

        filter_title = QLabel("Filtros de Busca")
        filter_title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{DASH_TEXT}; background:transparent;"
        )
        filter_subtitle = QLabel(
            "Refine a consulta por status e pesquise por pedido, cliente ou obra."
        )
        filter_subtitle.setWordWrap(True)
        filter_subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; color:{DASH_MUTED}; background:transparent;"
        )
        filter_layout.addWidget(filter_title)
        filter_layout.addWidget(filter_subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(max(12, int(16 * s)))

        status_col = QVBoxLayout()
        status_col.setSpacing(max(6, int(8 * s)))
        status_label = QLabel("STATUS")
        status_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
        )
        self.combo_status = QComboBox()
        self.combo_status.addItem("Todos os status", "")
        for key, label in theme.STATUS_LABELS.items():
            self.combo_status.addItem(label, key)
        self.combo_status.setFixedHeight(max(38, int(44 * s)))
        self.combo_status.setStyleSheet(_field_style(s))
        status_col.addWidget(status_label)
        status_col.addWidget(self.combo_status)

        search_col = QVBoxLayout()
        search_col.setSpacing(max(6, int(8 * s)))
        search_label = QLabel("BUSCA")
        search_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
        )
        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar por PED, cliente ou obra...")
        self.input_search.setFixedHeight(max(38, int(44 * s)))
        self.input_search.setStyleSheet(_field_style(s))
        self.input_search.returnPressed.connect(self.refresh)
        search_col.addWidget(search_label)
        search_col.addWidget(self.input_search)

        buttons_col = QVBoxLayout()
        buttons_col.setSpacing(max(6, int(8 * s)))
        buttons_col.addWidget(QLabel(""))
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(max(8, int(10 * s)))
        self.search_btn = QPushButton("BUSCAR")
        self.search_btn.setFixedHeight(max(38, int(44 * s)))
        self.search_btn.setStyleSheet(_primary_action_btn_style(s))
        self.search_btn.clicked.connect(self.refresh)

        self.clear_btn = QPushButton("LIMPAR")
        self.clear_btn.setFixedHeight(max(38, int(44 * s)))
        self.clear_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.clear_btn.clicked.connect(self._clear_filters)

        buttons_row.addWidget(self.search_btn)
        buttons_row.addWidget(self.clear_btn)
        buttons_col.addLayout(buttons_row)

        controls.addLayout(status_col, 1)
        controls.addLayout(search_col, 2)
        controls.addLayout(buttons_col)
        filter_layout.addLayout(controls)
        root.addWidget(filter_card)

        results_card = _make_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
        )
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                          max(16, int(20 * s)), max(14, int(18 * s)))
        results_layout.setSpacing(max(10, int(12 * s)))

        results_accent = QFrame()
        results_accent.setFixedHeight(max(4, int(5 * s)))
        results_accent.setStyleSheet(
            f"background:{DASH_PRIMARY}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        results_layout.addWidget(results_accent)

        results_title = QLabel("Resultados")
        results_title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{DASH_TEXT}; background:transparent;"
        )
        results_subtitle = QLabel("Duplo clique para abrir a requisição selecionada.")
        results_subtitle.setWordWrap(True)
        results_subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; color:{DASH_MUTED}; background:transparent;"
        )
        results_layout.addWidget(results_title)
        results_layout.addWidget(results_subtitle)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header_widget = self.table.horizontalHeader()
        stretch_columns = {2, 3}
        for col in range(len(COLS)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header_widget.setSectionResizeMode(col, mode)
        header_widget.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header_widget.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header_widget.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header_widget.setMinimumHeight(max(34, int(40 * s)))
        self.table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        self.table.setColumnWidth(1, max(180, int(220 * s)))
        self.table.setColumnWidth(5, max(150, int(180 * s)))
        self.table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{DASH_SURFACE};"
            f"  alternate-background-color:{DASH_ROW_ALT}; color:{DASH_TEXT};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{DASH_PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{DASH_SURFACE}; color:{DASH_TEXT};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(DASH_PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{DASH_ROW_ALT}; color:{DASH_TEXT}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(DASH_PRIMARY, 18)}; color:{DASH_TEXT}; }}"
        )
        pal = self.table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(DASH_SURFACE))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(DASH_ROW_ALT))
        pal.setColor(QPalette.ColorRole.Text, QColor(DASH_TEXT))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(DASH_TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(DASH_PRIMARY, 40)))
        self.table.setPalette(pal)
        self.table.viewport().setAutoFillBackground(True)
        self.table.setMinimumHeight(max(300, int(360 * s)))
        self.table.doubleClicked.connect(self._on_double_click)
        results_layout.addWidget(self.table, 1)
        root.addWidget(results_card, 1)

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()
        status = self.combo_status.currentData() or ""
        search = self.input_search.text().strip()

        worker = HistoryWorker(status, search)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        self.refresh_btn.setEnabled(not loading)
        self.search_btn.setEnabled(not loading)
        self.clear_btn.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.updated_label.setText("Falha ao atualizar")
        self.error_label.setText(f"Não foi possível carregar o histórico.\n\n{message}")
        self.error_label.show()

    def _populate(self, reqs: object):
        if not isinstance(reqs, list):
            self._show_error("Resposta inválida do servidor.")
            self._set_empty_message("Nenhuma requisição encontrada.")
            return

        self._reqs = [req for req in reqs if isinstance(req, dict)]
        self.table.clearSpans()
        self.table.setRowCount(0)

        if not self._reqs:
            self._set_empty_message("Nenhuma requisição encontrada.")
        else:
            for req in self._reqs:
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = [
                    str(req.get("ped_number") or "-"),
                    str(req.get("client_name") or req.get("client_id") or "-"),
                    str(req.get("obra") or "-"),
                    str(req.get("vendor_name") or req.get("vendor_id") or "-"),
                    _format_date(req.get("emission_date")),
                    str(req.get("status") or "-"),
                ]
                for col, value in enumerate(values):
                    if col == 5:
                        status = str(req.get("status") or "")
                        badge = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        color_map = {
                            "em_andamento": DASH_SECONDARY,
                            "aguardando_recebimento": DASH_WARNING,
                            "em_producao": DASH_PRIMARY,
                            "cancelada": DASH_DANGER,
                        }
                        color = color_map.get(status, DASH_SLATE)
                        badge.setStyleSheet(
                            f"background:{_rgba(color, 30)}; color:{color}; border-radius:999px;"
                            f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                        )
                        self.table.setCellWidget(row, col, badge)
                    else:
                        item = QTableWidgetItem(value)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.table.setItem(row, col, item)

        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

    def _set_empty_message(self, message: str):
        self.table.setRowCount(1)
        self.table.setSpan(0, 0, 1, len(COLS))
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(0, 0, item)

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._reqs):
            self.open_requisition.emit(self._reqs[row]["id"])

    def _clear_filters(self):
        self.combo_status.setCurrentIndex(0)
        self.input_search.clear()
        self.refresh()
