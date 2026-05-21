"""
Sistema de toasts de notificação estilo Samsung One UI.

NotificationToast  — card flutuante com slide-in, barra de countdown e slide-out
ToastManager       — empilha múltiplos toasts no canto inferior direito
"""
from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

# ── Constantes ────────────────────────────────────────────────────────────────

DISPLAY_MS   = 5_500   # tempo de exibição antes do auto-dismiss
TOAST_WIDTH  = 360
MARGIN       = 20      # distância das bordas da janela
SPACING      = 10      # espaço vertical entre toasts empilhados

_ICONS: dict[str, str] = {
    "nova_requisicao":   "🏭",
    "em_producao":       "⚙️",
    "finalizada":        "✅",
    "cancelada":         "❌",
    "prod_cancelada":    "⚠️",
    "requisicao_parada": "⏰",
}

_ACCENT: dict[str, str] = {
    "nova_requisicao":   "#3B82F6",   # azul
    "em_producao":       "#22C55E",   # verde
    "finalizada":        "#22C55E",   # verde
    "cancelada":         "#EF4444",   # vermelho
    "prod_cancelada":    "#EAB308",   # amarelo
    "requisicao_parada": "#EAB308",   # amarelo
}

_DEFAULT_ACCENT = "#3B82F6"


# ── Toast individual ──────────────────────────────────────────────────────────

class NotificationToast(QFrame):
    """Card flutuante de notificação com animação de entrada/saída."""

    dismissed     = Signal()
    action_clicked = Signal(object)   # emite requisition_id (int ou None)

    def __init__(self, data: dict, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._req_id   = data.get("requisition_id")
        self._anim: QPropertyAnimation | None = None
        accent         = _ACCENT.get(data.get("type", ""), _DEFAULT_ACCENT)

        self._build(data, accent)
        self._add_shadow()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._slide_out)

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build(self, data: dict, accent: str):
        self.setFixedWidth(TOAST_WIDTH)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: #1E293B;"
            f"  border: 1px solid #334155;"
            f"  border-left: 4px solid {accent};"
            f"  border-radius: 14px;"
            f"}}"
            f"QLabel {{ background: transparent; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 12, 10)
        root.setSpacing(6)

        # Cabeçalho: ícone + título + fechar
        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel(_ICONS.get(data.get("type", ""), "🔔"))
        icon_lbl.setStyleSheet("font-size: 18px;")
        header.addWidget(icon_lbl)

        title_lbl = QLabel(data.get("title", "Notificação"))
        title_lbl.setStyleSheet(
            "color: #F1F5F9; font-size: 10pt; font-weight: bold;"
        )
        title_lbl.setWordWrap(True)
        header.addWidget(title_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #64748B;"
            "  border: none; font-size: 11px; border-radius: 11px;"
            "}"
            "QPushButton:hover { background: #334155; color: #F1F5F9; }"
        )
        close_btn.clicked.connect(self._slide_out)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Mensagem
        msg_lbl = QLabel(data.get("message", ""))
        msg_lbl.setStyleSheet("color: #94A3B8; font-size: 9pt;")
        msg_lbl.setWordWrap(True)
        root.addWidget(msg_lbl)

        # Barra de countdown
        root.addSpacing(4)
        self._bar = QFrame()
        self._bar.setFixedHeight(3)
        self._bar.setStyleSheet(
            f"background: {accent}; border-radius: 2px; border: none;"
        )
        root.addWidget(self._bar)

        self._bar_anim = QPropertyAnimation(self._bar, b"maximumWidth")
        self._bar_anim.setStartValue(TOAST_WIDTH - 28)
        self._bar_anim.setEndValue(0)
        self._bar_anim.setDuration(DISPLAY_MS)
        self._bar_anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _add_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def show_at(self, x: int, y: int):
        """Exibe o toast animado a partir de (x, y)."""
        self.adjustSize()
        h = self.sizeHint().height()

        start = QPoint(x, y + h + 30)
        end   = QPoint(x, y)
        self.move(start)
        self.show()
        self.raise_()

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        self._bar_anim.start()
        self._dismiss_timer.start(DISPLAY_MS)

    def _slide_out(self):
        self._dismiss_timer.stop()
        self._bar_anim.stop()
        if self._anim:
            self._anim.stop()

        cur = self.pos()
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setStartValue(cur)
        self._anim.setEndValue(QPoint(cur.x(), cur.y() + self.height() + 30))
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._on_hidden)
        self._anim.start()

    def _on_hidden(self):
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    # ── Interação ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.action_clicked.emit(self._req_id)
            self._slide_out()
        super().mousePressEvent(event)


# ── Gerenciador de pilha ──────────────────────────────────────────────────────

class ToastManager:
    """Empilha toasts no canto inferior direito da janela pai."""

    def __init__(self, parent):
        self._parent = parent
        self._stack: list[NotificationToast] = []

    def show(self, data: dict, on_action=None):
        """Cria e exibe um toast para os dados de notificação fornecidos."""
        toast = NotificationToast(data, parent=None)
        toast.dismissed.connect(lambda t=toast: self._remove(t))
        if on_action:
            toast.action_clicked.connect(on_action)
        self._stack.append(toast)
        self._reposition()

    def _reposition(self):
        """Recalcula a posição de todos os toasts da pilha."""
        parent     = self._parent
        bottom_right = parent.mapToGlobal(parent.rect().bottomRight())
        x = bottom_right.x() - TOAST_WIDTH - MARGIN
        y = bottom_right.y() - MARGIN

        for toast in reversed(self._stack):
            toast.adjustSize()
            h = toast.sizeHint().height()
            y -= h
            if not toast.isVisible():
                toast.show_at(x, y)
            else:
                toast.move(x, y)
            y -= SPACING

    def _remove(self, toast: NotificationToast):
        if toast in self._stack:
            self._stack.remove(toast)
        self._reposition()
