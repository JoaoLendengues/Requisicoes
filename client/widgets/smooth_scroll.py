"""
SmoothScrollArea  — QScrollArea com scroll suave (wheelEvent override).
SmoothScrollHelper — event-filter reutilizável para qualquer QAbstractScrollArea.
apply_smooth_scroll — função de conveniência: uma linha ativa tudo.

Por que tempo real e não por frame?
  Um timer de N ms dispara em frequências não alinhadas ao refresh do monitor.
  Com lerp por tempo real, o avanço é proporcional ao dt medido com
  time.monotonic(), então cada tick produz exatamente o deslocamento correto
  para aquele intervalo — sem micro-saltos independente do Hz do monitor.

Como funciona:
  - Cada tick da roda acumula delta no _target.
  - O QTimer dispara a cada _FRAME_MS ms como trigger; o dt real é medido.
  - lerp_real = 1 − (1 − BASE_LERP)^(dt / FRAME_REF_S)
  - Quando diff < SNAP_PX, trava no alvo e para o timer.

Constantes de tempo:
  _FRAME_MS    = 8 ms  → trigger do timer (ideal para 120 Hz)
  _FRAME_REF_S = 0.016 → referência de calibração do BASE_LERP (16 ms / 60 fps)
  Os dois são independentes: mudar _FRAME_MS não altera a velocidade percebida.

Uso:
  # Páginas (QScrollArea) — substituir na criação:
  scroll = SmoothScrollArea(parent)

  # Tabelas, listas e qualquer QAbstractScrollArea — uma linha:
  apply_smooth_scroll(table)   # habilita ScrollPerPixel + instala helper
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea, QScrollArea

_FRAME_MS    = 8        # intervalo do timer (ms) — 8 ms = suporte nativo a 120 Hz
_FRAME_REF_S = 0.016    # referência para BASE_LERP — independente do timer
_BASE_LERP   = 0.55     # lerp equivalente a um frame de referência (16 ms)
_SNAP_PX     = 2.0      # trava quando diff < 2 px
_STEP_RATIO  = 0.25     # passo por tick = 25 % do pageStep
_STEP_MIN_PX = 100      # passo mínimo em pixels


# ── Helper reutilizável ───────────────────────────────────────────────────────

class SmoothScrollHelper(QObject):
    """
    Instala scroll suave em qualquer QAbstractScrollArea via event filter.

    Basta chamar apply_smooth_scroll(widget) — não precisa instanciar diretamente.
    O helper mantém referência viva sendo filho do widget (parent=widget).
    """

    def __init__(self, widget: QAbstractScrollArea, parent=None):
        super().__init__(parent or widget)
        self._widget     = widget
        self._target:    float = 0.0
        self._current:   float = 0.0
        self._last_time: float = 0.0

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        # Intercepta eventos de roda antes do handler padrão do Qt
        widget.viewport().installEventFilter(self)

    # ── Event filter ──────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel:
            # Scroll horizontal puro: deixa o Qt tratar normalmente
            if event.angleDelta().y() == 0:
                return False
            bar = self._widget.verticalScrollBar()
            if not bar.isVisible():
                return False
            self._on_wheel(event)
            return True   # consumido — scroll padrão do Qt suprimido
        return False

    # ── Processamento da roda ─────────────────────────────────────────────────

    def _on_wheel(self, event: QWheelEvent) -> None:
        bar = self._widget.verticalScrollBar()

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

    # ── Loop de animação ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()
        dt  = now - self._last_time
        self._last_time = now

        lerp = 1.0 - (1.0 - _BASE_LERP) ** (dt / _FRAME_REF_S)
        bar  = self._widget.verticalScrollBar()
        diff = self._target - self._current

        if abs(diff) < _SNAP_PX:
            val = int(round(self._target))
            bar.setValue(val)
            self._current = float(val)
            self._timer.stop()
            return

        self._current += diff * lerp
        bar.setValue(int(round(self._current)))


# ── Função de conveniência ────────────────────────────────────────────────────

def apply_smooth_scroll(widget: QAbstractScrollArea) -> SmoothScrollHelper:
    """
    Aplica scroll suave a qualquer QAbstractScrollArea em uma linha.

    Para QAbstractItemView (QTableWidget, QListWidget, etc.) habilita
    ScrollPerPixel automaticamente — obrigatório para animação pixel-a-pixel.
    """
    if isinstance(widget, QAbstractItemView):
        widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    return SmoothScrollHelper(widget)


# ── SmoothScrollArea (página inteira) ─────────────────────────────────────────

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

    # ── Loop de animação ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()
        dt  = now - self._last_time
        self._last_time = now

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

    # ── Evento de roda ────────────────────────────────────────────────────────

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
