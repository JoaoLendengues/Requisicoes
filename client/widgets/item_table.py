from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView,
)
<<<<<<< HEAD
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from ..core import theme

COLUMNS = ["POSIÇÃO", "QUANT", "COMP", "LARGURA", "CHAPA", "TIPO", "PESO CALC. (KG)"]
=======
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from ..core import theme

POSITION_COL = 0
PRODUCT_CODE_COL = 1
PRODUCT_NAME_COL = 2
QUANTITY_COL = 3
COMP_COL = 4
DESENV_COL = 5
CHAPA_COL = 6
TIPO_COL = 7
WEIGHT_COL = 8

COLUMNS = [
    "POSIÇÃO",
    "CÓD. PROD.",
    "PRODUTO",
    "QUANT",
    "COMP",
    "DESENV.",
    "CHAPA",
    "TIPO",
    "PESO (KG)",
]
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
POSITIONS = [chr(i) for i in range(ord("A"), ord("Z") + 1)]
CALC_FACTOR = 7.865
CALC_INPUT_COLUMNS = {1, 2, 3, 4}
CALC_WEIGHT_COLUMN = 6


class ItemTable(QWidget):
<<<<<<< HEAD
=======
    weight_changed = Signal(float)
    product_lookup_requested = Signal(int, str)

>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._updating_calc = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("ITENS DA REQUISIÇÃO")
        fs_title = max(9, int(11 * self.scale))
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{fs_title}pt; font-weight:bold;"
        )
        layout.addWidget(title)

<<<<<<< HEAD
        note = QLabel("Cálculo local para conferência do vendedor. Não é salvo nem impresso.")
        note.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8 * self.scale))}pt; font-style:italic;"
        )
        layout.addWidget(note)

=======
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
        self.table = QTableWidget(10, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(PRODUCT_NAME_COL, QHeaderView.ResizeMode.Stretch)
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

        for row in range(10):
            self._set_position_item(row)
            self._ensure_calc_item(row)

        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        footer = QHBoxLayout()
        self.btn_add = QPushButton("+  ADICIONAR ITEM")
        self.btn_add.setStyleSheet(theme.secondary_btn_style(self.scale))
        self.btn_add.clicked.connect(self._add_row)
        footer.addWidget(self.btn_add)
        footer.addStretch()

        peso_label = QLabel("PESO CALCULADO:")
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

<<<<<<< HEAD
    def _set_position_item(self, row: int):
        pos = POSITIONS[row] if row < len(POSITIONS) else f"#{row + 1}"
        item = QTableWidgetItem(pos)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
=======
    def _default_position(self, row: int) -> str:
        return POSITIONS[row] if row < len(POSITIONS) else f"#{row + 1}"

    def _set_position_item(self, row: int, value: str | None = None):
        text = (value or self._default_position(row)).strip().upper() or self._default_position(row)
        item = QTableWidgetItem(text)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsEditable
        )
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
        item.setBackground(QColor(theme.TABLE_HEADER_BG))
        item.setForeground(QColor("#ffffff"))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, POSITION_COL, item)

    def _ensure_calc_item(self, row: int) -> QTableWidgetItem:
        item = self.table.item(row, CALC_WEIGHT_COLUMN)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, CALC_WEIGHT_COLUMN, item)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(theme.PRIMARY))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        return item

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_position_item(row)
        self._ensure_calc_item(row)

    def _ensure_cell(self, row: int, col: int) -> QTableWidgetItem:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, col, item)
        return item

    def _on_item_changed(self, item: QTableWidgetItem):
<<<<<<< HEAD
        if self._updating_calc:
            return
        if item.column() in CALC_INPUT_COLUMNS:
            self._recalculate_row(item.row())
=======
        row = item.row()
        col = item.column()

        if col == POSITION_COL:
            text = item.text().strip().upper() or self._default_position(row)
            self.table.blockSignals(True)
            item.setText(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.blockSignals(False)
            return

        if col == PRODUCT_CODE_COL:
            code = item.text().strip()
            if code:
                self.table.blockSignals(True)
                self._ensure_cell(row, PRODUCT_NAME_COL).setText("")
                self.table.blockSignals(False)
                self.product_lookup_requested.emit(row, code)
            return

        if col == WEIGHT_COL:
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
            self._recalculate_total()

    def _recalculate_row(self, row: int):
        self._set_calculated_weight(row, self._calculate_row_weight(row))

    def _calculate_row_weight(self, row: int) -> float | None:
        qty = self._cell_float(row, 1)
        comp = self._cell_float(row, 2)
        largura = self._cell_float(row, 3)
        chapa = self._cell_float(row, 4)
        if None in (qty, comp, largura, chapa):
            return None
        return qty * comp * largura * chapa * CALC_FACTOR

    def _set_calculated_weight(self, row: int, value: float | None):
        item = self._ensure_calc_item(row)
        self._updating_calc = True
        try:
            item.setText(self._fmt_decimal(value) if value is not None else "")
        finally:
            self._updating_calc = False

    def _recalculate_total(self):
        total = 0.0
        for row in range(self.table.rowCount()):
<<<<<<< HEAD
            value = self._calculate_row_weight(row)
            if value is not None:
                total += value
        self.total_label.setText(self._fmt_decimal(total))

=======
            cell = self.table.item(row, WEIGHT_COL)
            if cell and cell.text():
                try:
                    total += float(cell.text().replace(",", "."))
                except ValueError:
                    pass
        self.total_label.setText(f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.weight_changed.emit(total)

    def get_total_weight(self) -> float:
        total = 0.0
        for row in range(self.table.rowCount()):
            value = self._cell_float(row, WEIGHT_COL)
            if value is not None:
                total += value
        return total

    def get_product_code(self, row: int) -> str:
        return self._cell_text(row, PRODUCT_CODE_COL)

    def apply_product_lookup(self, row: int, product: dict):
        self.table.blockSignals(True)
        self._ensure_cell(row, PRODUCT_CODE_COL).setText(product.get("code", ""))
        self._ensure_cell(row, PRODUCT_NAME_COL).setText(product.get("name", ""))
        self.table.blockSignals(False)

>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
    def get_items(self) -> list[dict]:
        items = []
        for row in range(self.table.rowCount()):
            pos_item = self.table.item(row, POSITION_COL)
            row_data = {
<<<<<<< HEAD
                "position": pos_item.text() if pos_item else POSITIONS[row],
                "quantity": self._cell_float(row, 1),
                "comp": self._cell_text(row, 2),
                "desenv": self._cell_text(row, 3),
                "chapa": self._cell_text(row, 4),
                "tipo": self._cell_text(row, 5),
=======
                "position": pos_item.text() if pos_item else self._default_position(row),
                "product_code": self._cell_text(row, PRODUCT_CODE_COL) or None,
                "product_name": self._cell_text(row, PRODUCT_NAME_COL) or None,
                "quantity": self._cell_float(row, QUANTITY_COL),
                "comp": self._cell_text(row, COMP_COL),
                "desenv": self._cell_text(row, DESENV_COL),
                "chapa": self._cell_text(row, CHAPA_COL),
                "tipo": self._cell_text(row, TIPO_COL),
                "weight": self._cell_float(row, WEIGHT_COL),
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
            }
            if any(v for v in list(row_data.values())[1:]):
                items.append(row_data)
        return items

    def set_items(self, items: list[dict]):
        self.table.blockSignals(True)
        self.table.setRowCount(max(10, len(items)))
        for row in range(self.table.rowCount()):
            self._set_position_item(row)
<<<<<<< HEAD
            self._ensure_calc_item(row)
        for row, item in enumerate(items):
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("quantity") or "")))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("comp") or ""))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("desenv") or ""))
            self.table.setItem(row, 4, QTableWidgetItem(item.get("chapa") or ""))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("tipo") or ""))
=======

        for row, item in enumerate(items):
            self._set_position_item(row, item.get("position"))
            self.table.setItem(row, PRODUCT_CODE_COL, QTableWidgetItem(item.get("product_code") or ""))
            self.table.setItem(row, PRODUCT_NAME_COL, QTableWidgetItem(item.get("product_name") or ""))
            self.table.setItem(row, QUANTITY_COL, QTableWidgetItem(str(item.get("quantity") or "")))
            self.table.setItem(row, COMP_COL, QTableWidgetItem(item.get("comp") or ""))
            self.table.setItem(row, DESENV_COL, QTableWidgetItem(item.get("desenv") or ""))
            self.table.setItem(row, CHAPA_COL, QTableWidgetItem(item.get("chapa") or ""))
            self.table.setItem(row, TIPO_COL, QTableWidgetItem(item.get("tipo") or ""))
            weight = item.get("weight")
            self.table.setItem(
                row,
                WEIGHT_COL,
                QTableWidgetItem(f"{weight:.2f}".replace(".", ",") if weight else "")
            )
>>>>>>> beb6ecc00acaa3cfe550bd2218527dedd259b0dd
        self.table.blockSignals(False)
        for row in range(self.table.rowCount()):
            self._recalculate_row(row)
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

    def _fmt_decimal(self, value: float) -> str:
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
