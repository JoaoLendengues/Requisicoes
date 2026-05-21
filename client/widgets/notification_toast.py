"""
Sistema de toasts de notificação.

NotificationToast  — card flutuante com slide + fade simultâneos,
                     barra de countdown e pausa automática ao hover.
                     Usa os tokens TOAST_* de theme.py (suporte a dark mode).
ToastManager       — empilha múltiplos toasts no canto inferior direito.
"""
from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
    Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from ..core import theme

# ── Constantes ────────────────────────────────────────────────────────────────

DISPLAY_MS  = 6_000
TOAST_WIDTH = 360
MARGIN      = 20
SPACING     = 10

_ICONS: dict[str, str] = {
    "nova_requisicao":   "🏭",
    "em_producao":       "⚙️",
    "finalizada":        "✅",
    "cancelada":         "❌",
    "prod_cancelada":    "⚠️",
    "requisicao_parada": "⏰",
}

_ACCENT: dict[str, str] = {
    "nova_requisicao":   "#2563EB",
    "em_producao":       "#16A34A",
    "finalizada":        "#16A34A",
    "cancelada":         "#DC2626",
    "prod_cancelada":    "#D97706",
    "requisicao_parada": "#D97706",
}

_DEFAULT_ACCENT = "#2563EB"


# ── Toast individual ──────────────────────────────────────────────────────────

class NotificationToast(QFrame):
    """Card flutuante com animação de entrada/saída (slide + fade) e hover-pause."""

    dismissed      = Signal()
    action_clicked = Signal(object)

    def __init__(self, data: dict, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setWindowOpacity(0.0)

        self._req_id    = data.get("requisition_id")
        self._group:    QParallelAnimationGroup | None = None
        self._remaining = DISPLAY_MS

        accent = _ACCENT.get(data.get("type", ""), _DEFAULT_ACCENT)
        self._build(data, accent)
        self._add_shadow()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._slide_out)

    # ── Construção ────────────────────────────────────────────────────────────

    def _build(self, data: dict, accent: str):
        self.setFixedWidth(TOAST_WIDTH)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {theme.TOAST_BG};"
            f"  border: 1px solid {theme.TOAST_BORDER};"
            f"  border-left: 4px solid {accent};"
            f"  border-radius: 12px;"
            f"  font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
            f"}}"
            f"QLabel {{ background: transparent; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 14, 10)
        root.setSpacing(4)

        # ── Cabeçalho: ícone + título + timestamp + fechar ──
        header = QHBoxLayout()
        header.setSpacing(8)
        header.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel(_ICONS.get(data.get("type", ""), "🔔"))
        icon_lbl.setStyleSheet("font-size: 17px;")
        icon_lbl.setFixedWidth(26)
        header.addWidget(icon_lbl)

        title_lbl = QLabel(data.get("title", "Notificação"))
        title_lbl.setStyleSheet(
            f"color: {theme.TOAST_TITLE}; font-size: 9pt; font-weight: 700;"
        )
        title_lbl.setWordWrap(True)
        header.addWidget(title_lbl, 1)

        ts_lbl = QLabel("agora")
        ts_lbl.setStyleSheet(
            f"color: {theme.TOAST_MUTED}; font-size: 7pt; font-weight: 400;"
        )
        header.addWidget(ts_lbl)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {theme.TOAST_CLOSE_FG};"
            f"  border: none; font-size: 10px; border-radius: 10px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {theme.TOAST_CLOSE_HV}; color: {theme.TOAST_TITLE};"
            f"}}"
        )
        close_btn.clicked.connect(self._slide_out)
        header.addWidget(close_btn)
        root.addLayout(header)

        # ── Mensagem ──
        msg = data.get("message", "")
        if msg:
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"color: {theme.TOAST_BODY}; font-size: 8pt; font-weight: 400;"
                f"padding-left: 34px;"
            )
            msg_lbl.setWordWrap(True)
            root.addWidget(msg_lbl)

        # ── Barra de countdown ──
        root.addSpacing(6)
        self._bar = QFrame()
        self._bar.setFixedHeight(2)
        self._bar.setStyleSheet(
            f"background: {accent}; border-radius: 1px; border: none;"
        )
        root.addWidget(self._bar)

        self._bar_anim = QPropertyAnimation(self._bar, b"maximumWidth")
        self._bar_anim.setStartValue(TOAST_WIDTH - 30)
        self._bar_anim.setEndValue(0)
        self._bar_anim.setDuration(DISPLAY_MS)
        self._bar_anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _add_shadow(self):
        # Extrai RGB do token TOAST_SHADOW para usar em QColor
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 44, 109, 30 if not theme.is_dark else 120))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def show_at(self, x: int, y: int):
        self.adjustSize()
        h = self.sizeHint().height()

        start_pos = QPoint(x, y + h + 24)
        end_pos   = QPoint(x, y)

        self.move(start_pos)
        self.show()
        self.raise_()

        slide = QPropertyAnimation(self, b"pos")
        slide.setStartValue(start_pos)
        slide.setEndValue(end_pos)
        slide.setDuration(340)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(340)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(slide)
        self._group.addAnimation(fade)
        self._group.start()

        self._bar_anim.start()
        self._remaining = DISPLAY_MS
        self._dismiss_timer.start(DISPLAY_MS)

    def _slide_out(self):
        self._dismiss_timer.stop()
        self._bar_anim.stop()
        if self._group:
            self._group.stop()

        cur = self.pos()

        slide = QPropertyAnimation(self, b"pos")
        slide.setStartValue(cur)
        slide.setEndValue(QPoint(cur.x(), cur.y() + self.height() + 24))
        slide.setDuration(240)
        slide.setEasingCurve(QEasingCurve.Type.InCubic)

        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0.0)
        fade.setDuration(240)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(slide)
        self._group.addAnimation(fade)
        self._group.finished.connect(self._on_hidden)
        self._group.start()

    def _on_hidden(self):
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    # ── Hover: pausa e retomada ───────────────────────────────────────────────

    def enterEvent(self, event):
        remaining = self._dismiss_timer.remainingTime()
        if remaining > 0:
            self._remaining = remaining
        self._dismiss_timer.stop()
        self._bar_anim.pause()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._bar_anim.resume()
        if self._remaining > 100:
            self._dismiss_timer.start(self._remaining)
        else:
            self._slide_out()
        super().leaveEvent(event)

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
        toast = NotificationToast(data, parent=None)
        toast.dismissed.connect(lambda t=toast: self._remove(t))
        if on_action:
            toast.action_clicked.connect(on_action)
        self._stack.append(toast)
        self._reposition()

    def _reposition(self):
        parent       = self._parent
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
