from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from ..core.theme import STATUS_COLORS, STATUS_LABELS


class StatusBadge(QLabel):
    def __init__(self, status: str = "em_andamento", scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str):
        self._status = status
        color = STATUS_COLORS.get(status, "#6B778C")
        label = STATUS_LABELS.get(status, status.upper())
        fs = max(8, int(10 * self.scale))
        self.setText(label.upper())
        self.setStyleSheet(
            f"background:{color}; color:#fff; border-radius:8px;"
            f"padding:4px 12px; font-size:{fs}pt; font-weight:600;"
        )
        self.setFixedHeight(max(24, int(28 * self.scale)))
