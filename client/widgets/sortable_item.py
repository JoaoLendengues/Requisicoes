"""
QTableWidgetItem com chave de ordenação customizada.

Uso:
    from .sortable_item import SortableItem

    # Coluna numérica (PED, dias de atraso, etc.)
    item = SortableItem("42", sort_key=42)

    # Coluna de data exibida como DD/MM/YYYY mas ordenada pela ISO raw
    item = SortableItem("25/05/2026", sort_key="2026-05-25")

Quando sort_key não é informado, a ordenação cai para o texto padrão do
QTableWidgetItem (idêntico ao comportamento original).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem


class SortableItem(QTableWidgetItem):
    """QTableWidgetItem que ordena pelo UserRole quando disponível."""

    def __init__(self, text: str = "", sort_key=None) -> None:
        super().__init__(text)
        if sort_key is not None:
            self.setData(Qt.ItemDataRole.UserRole, sort_key)

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        my_key    = self.data(Qt.ItemDataRole.UserRole)
        other_key = other.data(Qt.ItemDataRole.UserRole)
        if my_key is not None and other_key is not None:
            try:
                return my_key < other_key  # type: ignore[operator]
            except TypeError:
                pass
        return super().__lt__(other)
