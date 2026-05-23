"""
SmoothScrollArea — scroll suave com lerp baseado em tempo real.

Por que tempo real e não por frame?
  Um timer de 16 ms dispara a ~62.5 fps, mas o monitor roda a 60 Hz (16.67 ms).
  A cada segundo o timer "ultrapassa" o refresh ~2-3 vezes: alguns frames recebem
  dois updates de posição, outros nenhum — causando o efeito de pixel quebrado
  (micro-saltos visíveis). Com lerp por tempo real, o avanço é proporcional ao
  dt medido, então cada tick produz exatamente o deslocamento correto para aquele
  intervalo, independente de quantas vezes o timer disparou entre dois refreshes.

Como funciona:
  - Cada tick do roda acumula um delta no _target.
  - O QTimer dispara a cada ~16 ms como referência; o dt real é medido com
    time.monotonic() entre ticks consecutivos.
  - O lerp é normalizado: lerp_real = 1 − (1 − BASE_LERP)^(dt / FRAME_REF_S)
  - Quando diff < SNAP_PX, trava no alvo e para o timer.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QScrollArea

_FRAME_MS    = 16       # intervalo do timer (ms) — referência, não é o divisor
_FRAME_REF_S = _FRAME_MS / 1000.0
_BASE_LERP   = 0.38     # lerp equivalente a um frame de 16 ms
_SNAP_PX     = 1.5      # trava quando diff < 1.5 px
_STEP_RATIO  = 0.20     # passo por tick = 20 % do pageStep
_STEP_MIN_PX = 80       # passo mínimo em pixels


class SmoothScrollArea(QScrollArea):
    """QScrollArea com scroll suave via lerp exponencial baseado em tempo real."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        self._target:    float = 0.0
        self._current:   float = 0.0
        self._last_time: float = 0.0

    # ── loop de animação ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()
        dt  = now - self._last_time
        self._last_time = now

        # Normaliza o lerp pelo tempo real decorrido.
        # Se dt > esperado (frame lento), avança mais; se dt < esperado, avança menos.
        # Resultado: posição sempre proporcional ao tempo, sem micro-saltos.
        lerp = 1.0 - (1.0 - _BASE_LERP) ** (dt / _FRAME_REF_S)

        bar  = self.verticalScrollBar()
        diff = self._target - self._current

        if abs(diff) < _SNAP_PX:
            val = int(round(self._target))
            bar.setValue(val)
            self._current = float(val)
            self._timer.stop()
            return

        self._current += diff * lerp
        bar.setValue(int(round(self._current)))

    # ── evento de roda ────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        bar = self.verticalScrollBar()
        if not bar.isVisible():
            super().wheelEvent(event)
            return

        if not self._timer.isActive():
            self._current   = float(bar.value())
            self._target    = self._current
            self._last_time = time.monotonic()

        delta     = event.angleDelta().y()
        step      = max(_STEP_MIN_PX, int(bar.pageStep() * _STEP_RATIO))
        direction = -1 if delta > 0 else 1

        self._target = max(
            float(bar.minimum()),
            min(float(bar.maximum()), self._target + direction * step),
        )

        if not self._timer.isActive():
            self._last_time = time.monotonic()
            self._timer.start()

        event.accept()
