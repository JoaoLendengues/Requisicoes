"""
Sistema de toasts de notificação.

NotificationToast  — card flutuante com slide (da direita) + fade simultâneos,
                     barra de countdown e pausa automática ao hover.
                     Usa os tokens TOAST_* de theme.py (suporte a dark mode).
ToastManager       — fila sequencial: um toast de cada vez, com pausa entre eles.
"""
from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
    Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor, QPainterPath, QRegion
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from ..core import theme
from ..core.resolution import res

# ── Constantes ────────────────────────────────────────────────────────────────

DISPLAY_MS   = 6_000   # tempo que o toast fica visível
TOAST_WIDTH  = 360
MARGIN       = 20      # margem do canto da tela
_SLIDE_OVER  = 70      # deslocamento inicial fora do canto (entrada da direita)
_DRAG_START_PX = 10
_DRAG_DISMISS_RATIO = 0.28

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

_ACCENT_HOVER: dict[str, str] = {
    "nova_requisicao":   "#1D4ED8",
    "em_producao":       "#15803D",
    "finalizada":        "#15803D",
    "cancelada":         "#B91C1C",
    "prod_cancelada":    "#B45309",
    "requisicao_parada": "#B45309",
}

_ICONS.update({
    "faturado": "💰",
    "finalizado": "✅",
    "machine_status": "🛠️",
})

_ACCENT.update({
    "faturado": "#16A34A",
    "finalizado": "#10B981",
    "machine_status": "#2563EB",
})

_ACCENT_HOVER.update({
    "faturado": "#15803D",
    "finalizado": "#059669",
    "machine_status": "#1D4ED8",
})

_DEFAULT_ACCENT       = "#2563EB"
_DEFAULT_ACCENT_HOVER = "#1D4ED8"


# ── Toast individual ──────────────────────────────────────────────────────────

class NotificationToast(QFrame):
    """Card flutuante: entra deslizando da direita, sai pelo mesmo lado."""

    dismissed      = Signal()
    action_clicked = Signal(object)

    def __init__(self, data: dict, parent=None, factor: float | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setWindowOpacity(0.0)

        # Fator de tamanho (acessibilidade). None = valor salvo pelo usuario.
        self._factor    = factor if factor is not None else res.notification_factor
        self.toast_width = max(1, round(TOAST_WIDTH * self._factor))

        self._req_id    = data.get("requisition_id")
        self._group:    QParallelAnimationGroup | None = None
        self._remaining = DISPLAY_MS
        self._type      = data.get("type", "")
        self._rest_pos: QPoint | None = None
        self._press_global_pos: QPoint | None = None
        self._press_origin_pos: QPoint | None = None
        self._dragging = False

        accent = _ACCENT.get(self._type, _DEFAULT_ACCENT)
        self._build(data, accent)
        self._add_shadow()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._slide_out)

    # Helpers de escala
    def _sc(self, value: float) -> int:
        return max(1, round(value * self._factor))

    def _pt(self, value: float) -> int:
        return max(7, round(value * self._factor))

    # ── Construção ────────────────────────────────────────────────────────────

    def _build(self, data: dict, accent: str):
        self.setFixedWidth(self.toast_width)
        self.setObjectName("toastCard")
        self._corner_radius = self._sc(12)
        self.setStyleSheet(
            f"QFrame#toastCard {{"
            f"  background: {theme.TOAST_BG};"
            f"  border: none;"
            f"  border-radius: {self._corner_radius}px;"
            f"  font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
            f"}}"
            f"QLabel {{ background: transparent; border: none; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(self._sc(16), self._sc(13), self._sc(14), self._sc(10))
        root.setSpacing(self._sc(4))

        # ── Cabeçalho: ícone + título + timestamp + fechar ──
        header = QHBoxLayout()
        header.setSpacing(self._sc(8))
        header.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel(_ICONS.get(data.get("type", ""), "🔔"))
        icon_lbl.setStyleSheet(f"background:transparent; font-size: {self._sc(17)}px;")
        icon_lbl.setFixedWidth(self._sc(26))
        header.addWidget(icon_lbl)

        title_lbl = QLabel(data.get("title", "Notificação"))
        title_lbl.setStyleSheet(
            f"background:transparent; color: {theme.TOAST_TITLE}; font-size: {self._pt(10)}pt; font-weight: 700;"
        )
        title_lbl.setWordWrap(True)
        header.addWidget(title_lbl, 1)

        ts_lbl = QLabel("agora")
        ts_lbl.setStyleSheet(
            f"background:transparent; color: {theme.TOAST_MUTED}; font-size: {self._pt(8)}pt; font-weight: 400;"
        )
        header.addWidget(ts_lbl)

        close_sz = self._sc(20)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(close_sz, close_sz)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {theme.TOAST_CLOSE_FG};"
            f"  border: none; font-size: {self._sc(10)}px; border-radius: {close_sz // 2}px;"
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
                f"color: {theme.TOAST_BODY}; font-size: {self._pt(9)}pt; font-weight: 400;"
                f"padding-left: {self._sc(34)}px;"
            )
            msg_lbl.setWordWrap(True)
            root.addWidget(msg_lbl)

        # Sem barra inferior para manter o popup limpo/sem linhas.
        self._bar = None
        self._bar_anim = None
        self._apply_rounded_mask()

    def _add_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(self._sc(28))
        shadow.setColor(QColor(0, 44, 109, 26 if not theme.is_dark else 120))
        shadow.setOffset(0, self._sc(6))
        self.setGraphicsEffect(shadow)

    def _apply_rounded_mask(self):
        rect = self.rect()
        if rect.isNull():
            return
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height()),
                            float(self._corner_radius), float(self._corner_radius))
        polygon = path.toFillPolygon().toPolygon()
        if not polygon.isEmpty():
            self.setMask(QRegion(polygon))

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def show_at(self, x: int, y: int):
        """Exibe o toast com animação de entrada: desliza da direita + fade in."""
        self.adjustSize()
        self._apply_rounded_mask()
        h = self.sizeHint().height()

        end_pos   = QPoint(x, y - h)
        start_pos = QPoint(x + _SLIDE_OVER, y - h)
        self._rest_pos = QPoint(end_pos)

        self.move(start_pos)
        self.show()
        self.raise_()

        slide = QPropertyAnimation(self, b"pos")
        slide.setStartValue(start_pos)
        slide.setEndValue(end_pos)
        slide.setDuration(380)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(300)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._group = QParallelAnimationGroup(self)
        self._group.addAnimation(slide)
        self._group.addAnimation(fade)
        self._group.start()

        if self._bar_anim is not None:
            self._bar_anim.start()
        self._remaining = DISPLAY_MS
        self._dismiss_timer.start(DISPLAY_MS)

    def _pause_auto_dismiss(self):
        remaining = self._dismiss_timer.remainingTime()
        if remaining > 0:
            self._remaining = remaining
        self._dismiss_timer.stop()
        if self._bar_anim is not None:
            self._bar_anim.pause()

    def _resume_auto_dismiss(self):
        if self._bar_anim is not None:
            self._bar_anim.resume()
        if self._remaining > 100:
            self._dismiss_timer.start(self._remaining)
        else:
            self._slide_out()

    def _slide_out(self):
        """Saída: desliza para a direita + fade out simultâneos."""
        self._dismiss_timer.stop()
        if self._bar_anim is not None:
            self._bar_anim.stop()
        if self._group:
            self._group.stop()

        cur = self.pos()

        slide = QPropertyAnimation(self, b"pos")
        slide.setStartValue(cur)
        slide.setEndValue(QPoint(cur.x() + _SLIDE_OVER + self.toast_width // 4, cur.y()))
        slide.setDuration(220)
        slide.setEasingCurve(QEasingCurve.Type.InCubic)

        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0.0)
        fade.setDuration(200)
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_rounded_mask()

    # ── Hover: pausa e retomada ───────────────────────────────────────────────

    def enterEvent(self, event):
        self._pause_auto_dismiss()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._dragging:
            self._resume_auto_dismiss()
        super().leaveEvent(event)

    # ── Interação ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pause_auto_dismiss()
            if self._group:
                self._group.stop()
            self._press_global_pos = event.globalPosition().toPoint()
            self._press_origin_pos = QPoint(self.pos())
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_global_pos is None or self._press_origin_pos is None:
            super().mouseMoveEvent(event)
            return

        delta = event.globalPosition().toPoint() - self._press_global_pos
        if not self._dragging and delta.x() >= _DRAG_START_PX:
            self._dragging = True

        if self._dragging:
            new_x = self._press_origin_pos.x() + max(0, delta.x())
            self.move(new_x, self._press_origin_pos.y())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._press_origin_pos is None:
            super().mouseReleaseEvent(event)
            return

        dismiss_threshold = int(self.toast_width * _DRAG_DISMISS_RATIO)
        dragged_distance = max(0, self.pos().x() - self._press_origin_pos.x())
        was_dragging = self._dragging

        self._press_global_pos = None
        self._press_origin_pos = None
        self._dragging = False

        if was_dragging and dragged_distance >= dismiss_threshold:
            self._slide_out()
            event.accept()
            return

        if was_dragging and self._rest_pos is not None:
            restore = QPropertyAnimation(self, b"pos")
            restore.setStartValue(self.pos())
            restore.setEndValue(self._rest_pos)
            restore.setDuration(180)
            restore.setEasingCurve(QEasingCurve.Type.OutCubic)

            self._group = QParallelAnimationGroup(self)
            self._group.addAnimation(restore)
            self._group.finished.connect(self._resume_auto_dismiss)
            self._group.start()
            event.accept()
            return

        self.action_clicked.emit(self._req_id)
        self._slide_out()
        event.accept()


# ── Gerenciador sequencial ────────────────────────────────────────────────────

class ToastManager:
    """
    Fila de toasts sequenciais: exibe um de cada vez no canto inferior direito.
    Aguarda um intervalo entre o fim de um toast e o início do próximo.
    """

    _GAP_MS = 380   # pausa entre toasts consecutivos (ms)

    def __init__(self, parent):
        self._parent   = parent
        self._queue:   list[tuple[dict, object]] = []   # (data, on_action)
        self._current: NotificationToast | None  = None

        self._gap_timer = QTimer()
        self._gap_timer.setSingleShot(True)
        self._gap_timer.timeout.connect(self._show_next)

    # ── API pública ───────────────────────────────────────────────────────────

    def show(self, data: dict, on_action=None):
        """Enfileira um toast; exibe imediatamente se não houver nenhum ativo."""
        self._queue.append((data, on_action))
        if self._current is None and not self._gap_timer.isActive():
            self._show_next()

    def clear(self):
        """Descarta a fila pendente e dispensa o toast atual.

        Usado ao "marcar todas como lidas": interrompe imediatamente os
        pop-ups das notificações não vistas que ainda estavam na fila.
        """
        self._queue.clear()
        self._gap_timer.stop()
        current = self._current
        self._current = None
        if current is not None:
            current._slide_out()

    # ── Internos ──────────────────────────────────────────────────────────────

    def _target_pos(self, toast_width: int) -> tuple[int, int]:
        """Retorna (x, y_bottom) do canto inferior direito da janela pai."""
        parent = self._parent
        br = parent.mapToGlobal(parent.rect().bottomRight())
        x = br.x() - toast_width - MARGIN
        y = br.y() - MARGIN
        return x, y

    def _show_next(self):
        if not self._queue:
            return
        data, on_action = self._queue.pop(0)
        toast = NotificationToast(data, parent=None)
        toast.dismissed.connect(self._on_dismissed)
        if on_action:
            toast.action_clicked.connect(on_action)
        self._current = toast
        x, y = self._target_pos(toast.toast_width)
        toast.show_at(x, y)

    def _on_dismissed(self):
        self._current = None
        if self._queue:
            self._gap_timer.start(self._GAP_MS)
