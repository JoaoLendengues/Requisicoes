from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from ..core import theme

COLUMNS = ["POSIÇÃO", "QUANT", "COMP", "DESENV.", "CHAPA", "TIPO", "PESO (KG)"]
POSITIONS = [chr(i) for i in range(ord("A"), ord("Z") + 1)]


class ItemTable(QWidget):
    weight_changed = Signal(float)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Título
        title = QLabel("ITENS DA REQUISIÇÃO")
        fs_title = max(9, int(11 * self.scale))
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{fs_title}pt; font-weight:bold;"
        )
        layout.addWidget(title)

        # Tabela
        self.table = QTableWidget(10, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:6px;"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(8, int(10 * self.scale))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff;"
            f"  padding:6px; font-weight:bold; font-size:{max(8, int(9 * self.scale))}pt;"
            f"  border:none; border-right:1px solid #2d3f63;"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )

        # Popula coluna Posição
        for row in range(10):
            self._set_position_item(row)

        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Rodapé: botão + peso total
        footer = QHBoxLayout()
        self.btn_add = QPushButton("＋  ADICIONAR ITEM")
        self.btn_add.setStyleSheet(theme.secondary_btn_style(self.scale))
        self.btn_add.clicked.connect(self._add_row)
        footer.addWidget(self.btn_add)
        footer.addStretch()

        peso_label = QLabel("PESO TOTAL:")
        peso_label.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * self.scale))}pt; font-weight:bold;"
        )
        self.total_label = QLabel("0,00")
        self.total_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(10, int(12 * self.scale))}pt; font-weight:bold;"
        )
        footer.addWidget(peso_label)
        footer.addWidget(self.total_label)
        layout.addLayout(footer)

    def _set_position_item(self, row: int):
        pos = POSITIONS[row] if row < len(POSITIONS) else f"#{row+1}"
        item = QTableWidgetItem(pos)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setBackground(QColor(theme.TABLE_HEADER_BG))
        item.setForeground(QColor("#ffffff"))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, item)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_position_item(row)

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() == 6:  # Peso
            self._recalculate_total()

    def _recalculate_total(self):
        total = 0.0
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, 6)
            if cell and cell.text():
                try:
                    total += float(cell.text().replace(",", "."))
                except ValueError:
                    pass
        self.total_label.setText(f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.weight_changed.emit(total)

    # ── API pública ──────────────────────────────────────────────────────────
    def get_items(self) -> list[dict]:
        items = []
        for row in range(self.table.rowCount()):
            pos_item = self.table.item(row, 0)
            row_data = {
                "position": pos_item.text() if pos_item else POSITIONS[row],
                "quantity":  self._cell_float(row, 1),
                "comp":      self._cell_text(row, 2),
                "desenv":    self._cell_text(row, 3),
                "chapa":     self._cell_text(row, 4),
                "tipo":      self._cell_text(row, 5),
                "weight":    self._cell_float(row, 6),
            }
            if any(v for v in list(row_data.values())[1:]):
                items.append(row_data)
        return items

    def set_items(self, items: list[dict]):
        self.table.blockSignals(True)
        self.table.setRowCount(max(10, len(items)))
        for row in range(self.table.rowCount()):
            self._set_position_item(row)
        for row, item in enumerate(items):
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("quantity") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("comp") or ""))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("desenv") or ""))
            self.table.setItem(row, 4, QTableWidgetItem(item.get("chapa") or ""))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("tipo") or ""))
            w = item.get("weight")
            self.table.setItem(row, 6, QTableWidgetItem(f"{w:.2f}".replace(".", ",") if w else ""))
        self.table.blockSignals(False)
        self._recalculate_total()

    def _cell_text(self, row: int, col: int) -> str:
        cell = self.table.item(row, col)
        return cell.text().strip() if cell else ""

    def _cell_float(self, row: int, col: int) -> float | None:
        txt = self._cell_text(row, col).replace(",", ".")
        try:
            return float(txt) if txt else None
        except ValueError:
            return None
