from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ..core.theme import STATUS_COLORS, STATUS_LABELS


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


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
            f"background:{_rgba(color, 48)}; color:#F8FAFC;"
            f"border:1px solid {_rgba(color, 155)}; border-radius:12px;"
            f"padding:4px 12px; font-size:{fs}pt; font-weight:700;"
        )
        self.setFixedHeight(max(24, int(28 * self.scale)))

    def apply_theme(self, scale: float | None = None) -> None:
        if scale is not None:
            self.scale = scale
        self.set_status(getattr(self, "_status", "em_andamento"))
