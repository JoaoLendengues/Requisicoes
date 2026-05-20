from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, Signal,
)
from PySide6.QtGui import QColor, QCursor


_ICONS = {
    "nova_requisicao":   "🏭",
    "em_producao":       "⚙️",
    "finalizada":        "✅",
    "cancelada":         "❌",
    "prod_cancelada":    "⚠️",
    "requisicao_parada": "⏰",
}

_ACCENT = {
    "nova_requisicao":   "#3B82F6",
    "em_producao":       "#22C55E",
    "finalizada":        "#22C55E",
    "cancelada":         "#EF4444",
    "prod_cancelada":    "#EAB308",
    "requisicao_parada": "#EAB308",
}

DISPLAY_MS = 5500
TOAST_WIDTH = 350


class NotificationToast(QFrame):
    """Toast flutuante estilo Samsung One UI."""

    dismissed = Signal()
    action_clicked = Signal(object)

    def __init__(self, data: dict, parent=None):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._req_id = data.get("requisition_id")
        self._slide_anim: QPropertyAnimation | None = None

        accent = _ACCENT.get(data.get("type", ""), "#3B82F6")
        self._build_ui(data, accent)
        self._apply_shadow()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._slide_out)

    def _build_ui(self, data: dict, accent: str):
        self.setFixedWidth(TOAST_WIDTH)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background:#1E293B;"
            f"  border:1px solid #334155;"
            f"  border-left:4px solid {accent};"
            f"  border-radius:14px;"
            f"}}"
            f"QLabel {{ background:transparent; }}"
        )
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 12, 10)
        outer.setSpacing(6)

        # cabeçalho
        header = QHBoxLayout()
        header.setSpacing(10)

        icon = QLabel(_ICONS.get(data.get("type", ""), "🔔"))
        icon.setStyleSheet("font-size:18px;")
        header.addWidget(icon)

        title = QLabel(data.get("title", "Notificação"))
        title.setStyleSheet("color:#F1F5F9; font-size:10pt; font-weight:bold;")
        title.setWordWrap(True)
        header.addWidget(title, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#64748B; border:none;"
            "  font-size:11px; border-radius:11px; }"
            "QPushButton:hover { background:#334155; color:#F1F5F9; }"
        )
        close_btn.clicked.connect(self._slide_out)
        header.addWidget(close_btn)
        outer.addLayout(header)

        # mensagem
        msg = QLabel(data.get("message", ""))
        msg.setStyleSheet("color:#94A3B8; font-size:9pt;")
        msg.setWordWrap(True)
        outer.addWidget(msg)

        # barra de progresso (countdown)
        self._bar = QFrame()
        self._bar.setFixedHeight(3)
        self._bar.setStyleSheet(
            f"background:{accent}; border-radius:2px; border:none;"
        )
        outer.addSpacing(4)
        outer.addWidget(self._bar)

        self._bar_anim = QPropertyAnimation(self._bar, b"maximumWidth")
        self._bar_anim.setStartValue(TOAST_WIDTH - 28)
        self._bar_anim.setEndValue(0)
        self._bar_anim.setDuration(DISPLAY_MS)
        self._bar_anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _apply_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

    def show_at(self, x: int, y: int):
        self.adjustSize()
        h = self.sizeHint().height()

        start = QPoint(x, y + h + 30)
        self.move(start)
        self.show()
        self.raise_()

        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setStartValue(start)
        self._slide_anim.setEndValue(QPoint(x, y))
        self._slide_anim.setDuration(380)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.start()

        self._bar_anim.start()
        self._timer.start(DISPLAY_MS)

    def _slide_out(self):
        self._timer.stop()
        self._bar_anim.stop()
        if self._slide_anim:
            self._slide_anim.stop()

        current = self.pos()
        end = QPoint(current.x(), current.y() + self.height() + 30)

        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setStartValue(current)
        self._slide_anim.setEndValue(end)
        self._slide_anim.setDuration(260)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._slide_anim.finished.connect(self._on_gone)
        self._slide_anim.start()

    def _on_gone(self):
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.action_clicked.emit(self._req_id)
            self._slide_out()
        super().mousePressEvent(event)


class ToastManager:
    """Empilha toasts no canto inferior direito da janela pai."""

    MARGIN = 20
    SPACING = 12

    def __init__(self, parent):
        self._parent = parent
        self._stack: list[NotificationToast] = []

    def show(self, data: dict, on_action=None):
        toast = NotificationToast(data, parent=None)
        toast.dismissed.connect(lambda t=toast: self._on_dismissed(t))
        if on_action:
            toast.action_clicked.connect(on_action)
        self._stack.append(toast)
        self._reposition()

    def _reposition(self):
        pw = self._parent
        br = pw.mapToGlobal(pw.rect().bottomRight())
        x = br.x() - TOAST_WIDTH - self.MARGIN
        y = br.y() - self.MARGIN

        for toast in reversed(self._stack):
            toast.adjustSize()
            h = toast.sizeHint().height()
            y -= h
            if not toast.isVisible():
                toast.show_at(x, y)
            else:
                toast.move(x, y)
            y -= self.SPACING

    def _on_dismissed(self, toast: NotificationToast):
        if toast in self._stack:
            self._stack.remove(toast)
        self._reposition()
