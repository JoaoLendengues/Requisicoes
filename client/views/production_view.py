from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QColor

from ..api import client as api
from ..core import theme


COLS = ["PED", "CLIENTE", "OBRA", "VENDEDOR", "DATA"]


class ProductionWorker(QObject):
    result = Signal(list)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.list_requisitions("em_producao", limit=200))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


def _make_card(scale: float) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
    )
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(12)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    card.setGraphicsEffect(shadow)
    return card


class ProductionView(QWidget):
    open_requisition = Signal(int)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list = []
        self._rows_by_table: dict[str, list[dict]] = {
            "A&R": [],
            "Pinheiro Indústria": [],
            "Sem destino": [],
        }
        self._count_labels: dict[str, QLabel] = {}
        self._tables: dict[str, QTableWidget] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12, int(16 * s)), max(12, int(16 * s)),
                                  max(12, int(16 * s)), max(12, int(16 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("PRODUÇÃO")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(14, int(17 * s))}pt; font-weight:bold;"
        )
        subtitle = QLabel("Requisições enviadas para A&R, Pinheiro Indústria e pendências de destino.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        btn_refresh = QPushButton("ATUALIZAR")
        btn_refresh.setFixedHeight(max(32, int(36 * s)))
        btn_refresh.setStyleSheet(theme.secondary_btn_style(s))
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        counts = QGridLayout()
        counts.setSpacing(max(8, int(10 * s)))
        for index, label in enumerate(("A&R", "Pinheiro Indústria", "Sem destino")):
            card = _make_card(s)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(max(12, int(14 * s)), max(10, int(12 * s)),
                                           max(12, int(14 * s)), max(10, int(12 * s)))
            lbl_title = QLabel(label.upper())
            lbl_title.setStyleSheet(
                f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-weight:bold;"
            )
            lbl_value = QLabel("0")
            lbl_value.setStyleSheet(
                f"color:{theme.TEXT_DARK}; font-size:{max(18, int(24 * s))}pt; font-weight:bold;"
            )
            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_value)
            self._count_labels[label] = lbl_value
            counts.addWidget(card, 0, index)
        layout.addLayout(counts)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(max(10, int(12 * s)))
        tables_row.addWidget(self._build_table_card("A&R"), 1)
        tables_row.addWidget(self._build_table_card("Pinheiro Indústria"), 1)
        layout.addLayout(tables_row, 1)

        layout.addWidget(self._build_table_card("Sem destino"), 1)

        hint = QLabel("Duplo clique para abrir a requisição.")
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

    def _build_table_card(self, title: str) -> QFrame:
        s = self.scale
        card = _make_card(s)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(12, int(14 * s)), max(12, int(14 * s)),
                                  max(12, int(14 * s)), max(12, int(14 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(10, int(12 * s))}pt; font-weight:bold;"
        )
        layout.addWidget(lbl_title)

        table = QTableWidget(0, len(COLS))
        table.setHorizontalHeaderLabels(COLS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(9, int(10 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:8px;"
            f"  font-weight:bold; font-size:{max(8, int(9 * s))}pt; border:none;"
            f"  border-right:1px solid {theme.TABLE_BORDER};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )
        table.doubleClicked.connect(lambda index, key=title: self._open_from_table(key, index.row()))
        layout.addWidget(table, 1)
        self._tables[title] = table
        return card

    def refresh(self):
        worker = ProductionWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.finished.connect(thread.quit)
        thread.start()
        self._threads.append((thread, worker))

    def _populate(self, requisitions: list):
        grouped = {"A&R": [], "Pinheiro Indústria": [], "Sem destino": []}
        for req in requisitions:
            grouped[self._target_for(req)].append(req)

        self._rows_by_table = grouped

        for key, rows in grouped.items():
            self._count_labels[key].setText(str(len(rows)))
            table = self._tables[key]
            table.setRowCount(0)
            for req in rows:
                row = table.rowCount()
                table.insertRow(row)
                values = [
                    str(req.get("ped_number", "")),
                    req.get("client_name") or str(req.get("client_id", "")),
                    req.get("obra") or "—",
                    req.get("vendor_name") or str(req.get("vendor_id", "")),
                    str(req.get("emission_date", ""))[:10],
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, col, item)

    def _target_for(self, req: dict) -> str:
        history = req.get("status_history") or []
        for entry in reversed(history):
            if entry.get("new_status") != "em_producao":
                continue
            note = (entry.get("note") or "").strip()
            if not note:
                return "Sem destino"
            if note.lower().startswith("a&r"):
                return "A&R"
            if "pinheiro" in note.lower():
                return "Pinheiro Indústria"
        return "Sem destino"

    def _open_from_table(self, table_key: str, row: int):
        rows = self._rows_by_table.get(table_key, [])
        if 0 <= row < len(rows):
            self.open_requisition.emit(rows[row]["id"])
