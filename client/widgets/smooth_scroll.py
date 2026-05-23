"""
SmoothScrollArea — scroll fluido a 60 fps via spring/lerp com PreciseTimer.

Como funciona:
  - Cada tick do roda acumula um delta no _target (sem limite de duração).
  - Um QTimer com PreciseTimer dispara a cada 16 ms (~62.5 fps).
  - A cada tick, o valor atual avança 22% da distância restante (lerp).
  - Quando o restante é < 1 px, trava no alvo — sem oscilação.

Resultado: inércia natural, desaceleração suave, resposta imediata a novos
eventos de roda enquanto o scroll anterior ainda está animando.
"""
from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QWheelEvent

_FRAME_MS    = 16     # intervalo do timer → ~62.5 fps (PreciseTimer garante isso)
_LERP        = 0.22   # fator por frame: 22% da distância restante
_SNAP_PX     = 1.0    # trava quando diff < 1 px
_STEP_RATIO  = 0.13   # passo por tick = 13% do pageStep (sensação natural)
_STEP_MIN_PX = 40     # passo mínimo em pixels


class SmoothScrollArea(QScrollArea):
    """QScrollArea com scroll suave a ~60 fps via lerp exponencial."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)  # resolução máxima
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        self._target:  float = 0.0
        self._current: float = 0.0

    # ── loop de animação ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        bar  = self.verticalScrollBar()
        diff = self._target - self._current

        if abs(diff) < _SNAP_PX:
            # chegou — trava e para o timer
            val = int(round(self._target))
            bar.setValue(val)
            self._current = float(val)
            self._timer.stop()
            return

        self._current += diff * _LERP
        bar.setValue(int(round(self._current)))

    # ── evento de roda ────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        bar = self.verticalScrollBar()
        if not bar.isVisible():
            super().wheelEvent(event)
            return

        # Sincroniza ponto de partida quando o scroll estava parado
        if not self._timer.isActive():
            self._current = float(bar.value())
            self._target  = self._current

        delta     = event.angleDelta().y()
        step      = max(_STEP_MIN_PX, int(bar.pageStep() * _STEP_RATIO))
        direction = -1 if delta > 0 else 1

        self._target = max(
            float(bar.minimum()),
            min(float(bar.maximum()), self._target + direction * step),
        )

        if not self._timer.isActive():
            self._timer.start()

        event.accept()
