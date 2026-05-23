from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import QModelIndex, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette

from ..core import theme
from ..core.text_case import normalize_upper_text


POSITION_COL = 0
PRODUCT_CODE_COL = 1
PRODUCT_NAME_COL = 2
QUANTITY_COL = 3
COMP_COL = 4
DESENV_COL = 5
CHAPA_COL = 6
TIPO_COL = 7
WEIGHT_COL = 8
EDITABLE_FLOW_COLS = [
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QUANTITY_COL,
    COMP_COL,
    DESENV_COL,
    CHAPA_COL,
    TIPO_COL,
    WEIGHT_COL,
]

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

POSITIONS = [chr(i) for i in range(ord("A"), ord("Z") + 1)]
UPPERCASE_COLS = {
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    COMP_COL,
    DESENV_COL,
    CHAPA_COL,
    TIPO_COL,
}


class ItemTable(QWidget):
    weight_changed = Signal(float)
    product_lookup_requested = Signal(int, str)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = QLabel("ITENS DA REQUISIÇÃO")
        fs_title = max(9, int(11 * self.scale))
        self.title_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{fs_title}pt; font-weight:bold;"
        )
        layout.addWidget(self.title_label)

        self.table = _ItemGridTable(10, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setAlternatingRowColors(True)
        self.table.setTabKeyNavigation(True)
        self.table.horizontalHeader().setSectionResizeMode(
            PRODUCT_NAME_COL, QHeaderView.ResizeMode.Stretch
        )
        self._apply_table_stylesheet()
        self._apply_table_palette()

        for row in range(10):
            self._set_position_item(row)

        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        footer = QHBoxLayout()

        self.btn_add = QPushButton("+  ADICIONAR ITEM")
        self.btn_add.setStyleSheet(theme.secondary_btn_style(self.scale))
        self.btn_add.clicked.connect(self._add_row)
        footer.addWidget(self.btn_add)

        self.btn_clear_selected = QPushButton("LIMPAR LINHA SELECIONADA")
        self.btn_clear_selected.setStyleSheet(theme.secondary_btn_style(self.scale))
        self.btn_clear_selected.clicked.connect(self._clear_selected_row)
        footer.addWidget(self.btn_clear_selected)

        footer.addStretch()

        self.peso_label = QLabel("PESO TOTAL:")
        self.peso_label.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * self.scale))}pt; font-weight:bold;"
        )
        self.total_label = QLabel("0,00")
        self.total_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(10, int(12 * self.scale))}pt; font-weight:bold;"
        )
        footer.addWidget(self.peso_label)
        footer.addWidget(self.total_label)
        layout.addLayout(footer)

    def _apply_table_stylesheet(self) -> None:
        s = self.scale
        self.table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  background:{theme.CARD_BG};"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(8, int(10 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff;"
            f"  padding:6px; font-weight:bold; font-size:{max(8, int(9 * s))}pt;"
            f"  border:none;"
            f"}}"
            f"QTableWidget::item {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK}; }}"
        )
        self.table.viewport().setStyleSheet(f"background:{theme.CARD_BG};")

    def _apply_table_palette(self) -> None:
        pal = self.table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        self.table.setPalette(pal)

    def apply_theme(self) -> None:
        s = self.scale
        self._apply_table_stylesheet()
        self._apply_table_palette()
        self.title_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(9, int(11 * s))}pt; font-weight:bold;"
        )
        self.peso_label.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * s))}pt; font-weight:bold;"
        )
        self.total_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(10, int(12 * s))}pt; font-weight:bold;"
        )
        self.btn_add.setStyleSheet(theme.secondary_btn_style(s))
        self.btn_clear_selected.setStyleSheet(theme.secondary_btn_style(s))

    def _default_position(self, row: int) -> str:
        return POSITIONS[row] if row < len(POSITIONS) else f"#{row + 1}"

    def _set_position_item(self, row: int, value: str | None = None):
        text = normalize_upper_text(value or self._default_position(row)).strip() or self._default_position(row)
        item = QTableWidgetItem(text)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, POSITION_COL, item)

    def _clear_row(self, row: int):
        self.table.blockSignals(True)
        for col in range(PRODUCT_CODE_COL, WEIGHT_COL + 1):
            self.table.takeItem(row, col)

        pos_item = self.table.item(row, POSITION_COL)
        if pos_item is not None:
            pos_item.setText(pos_item.text().strip().upper() or self._default_position(row))
            pos_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._set_position_item(row)

        self.table.blockSignals(False)
        self._recalculate_total()

    def _clear_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self._clear_row(row)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_position_item(row)

    def _ensure_cell(self, row: int, col: int) -> QTableWidgetItem:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, col, item)
        return item

    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()

        if col == POSITION_COL:
            text = normalize_upper_text(item.text()).strip() or self._default_position(row)
            self.table.blockSignals(True)
            item.setText(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.blockSignals(False)
            return

        if col in UPPERCASE_COLS:
            normalized = normalize_upper_text(item.text())
            if normalized != item.text():
                self.table.blockSignals(True)
                item.setText(normalized)
                self.table.blockSignals(False)

        if col == PRODUCT_CODE_COL:
            code = item.text().strip()
            self.table.blockSignals(True)
            self._ensure_cell(row, PRODUCT_NAME_COL).setText("")
            self.table.blockSignals(False)
            if code:
                self.product_lookup_requested.emit(row, code)
            return

        if col == WEIGHT_COL:
            self._recalculate_total()

    def _recalculate_total(self):
        total = 0.0
        for row in range(self.table.rowCount()):
            cell = self.table.item(row, WEIGHT_COL)
            if cell and cell.text():
                try:
                    total += float(cell.text().replace(",", "."))
                except ValueError:
                    pass

        self.total_label.setText(
            f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
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
        self._ensure_cell(row, PRODUCT_CODE_COL).setText(normalize_upper_text(product.get("code", "")))
        self._ensure_cell(row, PRODUCT_NAME_COL).setText(normalize_upper_text(product.get("name", "")))
        self.table.blockSignals(False)

    def get_items(self) -> list[dict]:
        items = []
        for row in range(self.table.rowCount()):
            pos_item = self.table.item(row, POSITION_COL)
            row_data = {
                "position": pos_item.text() if pos_item else self._default_position(row),
                "product_code": self._cell_text(row, PRODUCT_CODE_COL) or None,
                "product_name": self._cell_text(row, PRODUCT_NAME_COL) or None,
                "quantity": self._cell_float(row, QUANTITY_COL),
                "comp": self._cell_text(row, COMP_COL),
                "desenv": self._cell_text(row, DESENV_COL),
                "chapa": self._cell_text(row, CHAPA_COL),
                "tipo": self._cell_text(row, TIPO_COL),
                "weight": self._cell_float(row, WEIGHT_COL),
            }
            if any(v for v in list(row_data.values())[1:]):
                items.append(row_data)
        return items

    def set_items(self, items: list[dict]):
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(max(10, len(items)))

        for row in range(self.table.rowCount()):
            self._set_position_item(row)

        for row, item in enumerate(items):
            self._set_position_item(row, item.get("position"))
            self.table.setItem(
                row, PRODUCT_CODE_COL, QTableWidgetItem(normalize_upper_text(item.get("product_code") or ""))
            )
            self.table.setItem(
                row, PRODUCT_NAME_COL, QTableWidgetItem(normalize_upper_text(item.get("product_name") or ""))
            )
            self.table.setItem(
                row, QUANTITY_COL, QTableWidgetItem(str(item.get("quantity") or ""))
            )
            self.table.setItem(row, COMP_COL, QTableWidgetItem(normalize_upper_text(item.get("comp") or "")))
            self.table.setItem(
                row, DESENV_COL, QTableWidgetItem(normalize_upper_text(item.get("desenv") or ""))
            )
            self.table.setItem(row, CHAPA_COL, QTableWidgetItem(normalize_upper_text(item.get("chapa") or "")))
            self.table.setItem(row, TIPO_COL, QTableWidgetItem(normalize_upper_text(item.get("tipo") or "")))
            weight = item.get("weight")
            self.table.setItem(
                row,
                WEIGHT_COL,
                QTableWidgetItem(f"{weight:.2f}".replace(".", ",") if weight else ""),
            )

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


class _ItemGridTable(QTableWidget):
    """QTableWidget com fluxo de Tab lateral para os itens da requisição."""

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and self.state() != QAbstractItemView.State.EditingState
        ):
            self._clear_selected_cells()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Tab and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            current = self.currentIndex()
            if self._is_last_weight_cell(current):
                event.accept()
                self.focusNextPrevChild(True)
                return
        super().keyPressEvent(event)

    def moveCursor(self, action, modifiers):
        if action in (
            QAbstractItemView.CursorAction.MoveNext,
            QAbstractItemView.CursorAction.MovePrevious,
        ):
            current = self.currentIndex()
            if current.isValid():
                if (
                    action == QAbstractItemView.CursorAction.MoveNext
                    and self._is_last_weight_cell(current)
                ):
                    QTimer.singleShot(0, lambda: self.focusNextPrevChild(True))
                    return current
                next_index = self._next_flow_index(current, action)
                if next_index.isValid():
                    return next_index
        return super().moveCursor(action, modifiers)

    def _is_last_weight_cell(self, index: QModelIndex) -> bool:
        return (
            index.isValid()
            and index.column() == WEIGHT_COL
            and index.row() >= self.rowCount() - 1
        )

    def _next_flow_index(self, current: QModelIndex, action) -> QModelIndex:
        row = current.row()
        col = current.column()

        if col not in EDITABLE_FLOW_COLS:
            fallback_col = PRODUCT_CODE_COL if action == QAbstractItemView.CursorAction.MoveNext else WEIGHT_COL
            fallback_row = row
            if action == QAbstractItemView.CursorAction.MovePrevious and row > 0:
                fallback_row = row - 1
            return self.model().index(fallback_row, fallback_col)

        idx = EDITABLE_FLOW_COLS.index(col)
        if action == QAbstractItemView.CursorAction.MoveNext:
            if idx < len(EDITABLE_FLOW_COLS) - 1:
                return self.model().index(row, EDITABLE_FLOW_COLS[idx + 1])
            if row < self.rowCount() - 1:
                return self.model().index(row + 1, PRODUCT_CODE_COL)
            return current

        if idx > 0:
            return self.model().index(row, EDITABLE_FLOW_COLS[idx - 1])
        if row > 0:
            return self.model().index(row - 1, WEIGHT_COL)
        return self.model().index(row, PRODUCT_CODE_COL)

    def _clear_selected_cells(self) -> None:
        indexes = sorted(self.selectedIndexes(), key=lambda idx: (idx.row(), idx.column()))
        if not indexes:
            return

        model = self.model()
        for idx in indexes:
            row, col = idx.row(), idx.column()
            if col == POSITION_COL:
                continue
            model.setData(idx, "")
