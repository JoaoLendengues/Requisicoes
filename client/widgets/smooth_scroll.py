"""
SmoothScrollArea — QScrollArea com scroll suave via QPropertyAnimation (60 fps).

Substitui o scroll abrupto padrão por uma animação com easing OutCubic.
Acumula corretamente múltiplos eventos de roda antes da animação terminar.
"""
from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QWheelEvent

_DURATION_MS = 220          # duração da animação de scroll
_TICKS_PER_STEP = 3         # multiplicador do singleStep por tick de roda


class SmoothScrollArea(QScrollArea):
    """QScrollArea com scroll vertical suave."""

    def __init__(self, parent=None):
        super().__init__(parent)
        bar = self.verticalScrollBar()
        self._anim = QPropertyAnimation(bar, b"value", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setDuration(_DURATION_MS)
        self._target: int | None = None
        self._anim.finished.connect(self._sync_target)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _sync_target(self) -> None:
        self._target = self.verticalScrollBar().value()

    def _current_target(self) -> int:
        if (
            self._anim.state() == QAbstractAnimation.State.Running
            and self._target is not None
        ):
            return self._target
        return self.verticalScrollBar().value()

    # ── eventos ──────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        bar = self.verticalScrollBar()
        if not bar.isVisible():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        step = max(40, bar.singleStep() * _TICKS_PER_STEP)
        direction = -1 if delta > 0 else 1

        new_target = max(
            bar.minimum(),
            min(bar.maximum(), self._current_target() + direction * step),
        )
        self._target = new_target

        self._anim.stop()
        self._anim.setStartValue(bar.value())
        self._anim.setEndValue(new_target)
        self._anim.start()
        event.accept()
