from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QComboBox, QLineEdit, QPushButton, QHeaderView,
    QAbstractItemView, QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor

from ..core import theme
from ..core.resolution import res
from ..api import client as api
from ..widgets.status_badge import StatusBadge


class HistoryWorker(QObject):
    result   = Signal(list)
    error    = Signal(str)
    finished = Signal()

    def __init__(self, status="", search=""):
        super().__init__()
        self.status = status
        self.search = search

    def run(self):
        try:
            self.result.emit(api.list_requisitions(self.status, self.search, limit=100))
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


COLS = ["PED", "CLIENTE", "OBRA", "VENDEDOR", "DATA", "STATUS"]


class HistoryView(QWidget):
    open_requisition = Signal(int)   # emite o id da requisição selecionada

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list = []
        self._reqs: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12,int(16*s)), max(12,int(16*s)),
                                   max(12,int(16*s)), max(12,int(16*s)))
        layout.setSpacing(max(10,int(12*s)))

        # Título
        title = QLabel("◷ HISTÓRICO / BUSCA DE REQUISIÇÕES")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(12,int(15*s))}pt; font-weight:bold;"
        )
        layout.addWidget(title)

        # Filtros
        filter_row = QHBoxLayout()

        self.combo_status = QComboBox()
        self.combo_status.addItem("Todos os status", "")
        for k, v in theme.STATUS_LABELS.items():
            self.combo_status.addItem(v, k)
        self.combo_status.setFixedHeight(max(30,int(34*s)))
        self.combo_status.setStyleSheet(theme.input_style(s))

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Buscar por nº PED, cliente ou obra...")
        self.input_search.setFixedHeight(max(30,int(34*s)))
        self.input_search.setStyleSheet(theme.input_style(s))

        btn_search = QPushButton("⌕ Buscar")
        btn_search.setFixedHeight(max(30,int(34*s)))
        btn_search.setStyleSheet(theme.primary_btn_style(s))
        btn_search.clicked.connect(self.refresh)

        btn_clear = QPushButton("✕ Limpar")
        btn_clear.setFixedHeight(max(30,int(34*s)))
        btn_clear.setStyleSheet(theme.secondary_btn_style(s))
        btn_clear.clicked.connect(self._clear_filters)

        filter_row.addWidget(QLabel("Status:"))
        filter_row.addWidget(self.combo_status)
        filter_row.addWidget(self.input_search)
        filter_row.addWidget(btn_search)
        filter_row.addWidget(btn_clear)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Tabela
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(9,int(10*s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:8px;"
            f"  font-weight:bold; font-size:{max(8,int(9*s))}pt; border:none;"
            f"  border-right:1px solid {theme.TABLE_BORDER};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )
        layout.addWidget(self.table)

        # Dica
        hint = QLabel("Duplo clique para abrir a requisição")
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8,int(9*s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

    def refresh(self):
        status = self.combo_status.currentData() or ""
        search = self.input_search.text().strip()
        worker = HistoryWorker(status, search)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.finished.connect(thread.quit)
        thread.start()
        self._threads.append((thread, worker))

    def _populate(self, reqs: list):
        self._reqs = reqs
        self.table.setRowCount(0)
        for req in reqs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vals = [
                str(req.get("ped_number", "")),
                req.get("client_name") or str(req.get("client_id", "")),
                req.get("obra") or "—",
                req.get("vendor_name") or str(req.get("vendor_id", "")),
                str(req.get("emission_date", ""))[:10],
                req.get("status", ""),
            ]
            for col, val in enumerate(vals):
                if col == 5:   # Status — badge colorido
                    lbl = QLabel(theme.STATUS_LABELS.get(val, val))
                    color = theme.STATUS_COLORS.get(val, "#6B7280")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl.setStyleSheet(
                        f"background:{color}; color:#fff; border-radius:4px;"
                        f"font-weight:bold; font-size:{max(8,int(9*self.scale))}pt;"
                        f"padding:2px 6px;"
                    )
                    self.table.setCellWidget(row, col, lbl)
                else:
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, item)

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._reqs):
            self.open_requisition.emit(self._reqs[row]["id"])

    def _clear_filters(self):
        self.combo_status.setCurrentIndex(0)
        self.input_search.clear()
        self.refresh()
