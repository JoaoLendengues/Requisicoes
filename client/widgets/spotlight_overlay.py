"""
Tour guiado com spotlight — estilo Android.

Melhorias v2:
  - Balão maior (440 px escalado)
  - Seta no balão apontando para o elemento destacado
  - Anel de luz pulsante ao redor do spotlight (breathing animation)

Fluxo:
  SpotlightOverlay(main_window, steps, scale, role)
    .start()     → exibe o overlay, vai para o passo 0
    .finished    → signal emitido ao concluir ou pular

Pintura do overlay:
  QPainterPath.subtracted() cria o recorte sem WA_TranslucentBackground.
  O conteúdo do pai aparece no spotlight porque o overlay não pinta ali.

Animação do spotlight:
  Timer de 16 ms com easing OutCubic — sem QVariantAnimation.

Pulso:
  Timer dedicado de 16 ms incrementa _pulse_t em onda senoidal contínua.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QFrame,
    QGraphicsDropShadowEffect,
)

from ..core import theme
from ..core.resolution import res


# ── Definição de passo ────────────────────────────────────────────────────────

@dataclass
class TourStep:
    """Um passo do tour guiado.

    Atributos
    ---------
    title : str
        Título curto exibido no balão.
    body : str
        Descrição (aceita HTML simples, ex.: <b>texto</b>).
    widget_getter : Callable[[], QWidget | None]
        Retorna o widget a ser destacado. None → spotlight centralizado.
    tooltip_side : str
        Lado do spotlight onde o balão aparece:
        "top" | "bottom" | "left" | "right" | "center".
    navigate_key : str | None
        Chave de navegação da sidebar a executar antes de exibir o passo.
    padding : int
        Espaço extra em px ao redor do widget no spotlight.
    """
    title: str
    body: str
    widget_getter: Callable[[], Optional[QWidget]] = field(default=lambda: None)
    tooltip_side: str = "bottom"
    navigate_key: Optional[str] = None
    padding: int = 20


# ── Balão de texto ────────────────────────────────────────────────────────────

class _Bubble(QWidget):
    """
    Cartão flutuante com título, corpo e botões de navegação.
    Inclui uma seta que aponta em direção ao elemento destacado.
    """

    next_clicked = Signal()
    prev_clicked = Signal()
    skip_clicked = Signal()

    def __init__(self, scale: float, parent: QWidget) -> None:
        super().__init__(parent)
        self._scale = scale
        self._side  = "center"
        self._arrow = max(10, int(12 * scale))   # tamanho da seta em px
        self._pad   = max(16, int(20 * scale))   # padding do conteúdo
        # Background pintado manualmente no paintEvent
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")
        self._build()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build(self) -> None:
        s   = self._scale
        p   = self._pad
        a   = self._arrow
        bw  = max(360, int(440 * s))
        self.setFixedWidth(bw)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(max(24, int(32 * s)))
        shadow.setOffset(0, max(5, int(7 * s)))
        sc = QColor(0, 0, 0)
        sc.setAlpha(75)
        shadow.setColor(sc)
        self.setGraphicsEffect(shadow)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(p, p, p, p)
        self._root.setSpacing(max(8, int(10 * s)))

        # ── Cabeçalho ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(11, int(13 * s))}pt;"
            f"font-weight:800; background:transparent;"
        )
        hdr.addWidget(self._title, 1)

        self._counter = QLabel()
        self._counter.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt;"
            f"font-weight:600; background:transparent;"
        )
        hdr.addWidget(self._counter)
        self._root.addLayout(hdr)

        # ── Corpo ─────────────────────────────────────────────────────────────
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(10 * s))}pt;"
            f"font-weight:500; line-height:160%; background:transparent;"
        )
        self._root.addWidget(self._body)

        # ── Separador ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{theme.BORDER_COLOR}; border:none;")
        self._root.addWidget(sep)

        # ── Rodapé ────────────────────────────────────────────────────────────
        ftr = QHBoxLayout()
        ftr.setSpacing(max(6, int(8 * s)))
        btn_h = max(32, int(36 * s))
        px    = max(10, int(14 * s))

        self._btn_skip = QPushButton("Pular tour")
        self._btn_skip.setFixedHeight(btn_h)
        self._btn_skip.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{theme.TEXT_MEDIUM};"
            f"  border:none; font-size:{max(8, int(9 * s))}pt; font-weight:600; }}"
            f"QPushButton:hover {{ color:{theme.TEXT_DARK}; }}"
        )
        self._btn_skip.clicked.connect(self.skip_clicked)
        ftr.addWidget(self._btn_skip)
        ftr.addStretch()

        sec = (
            f"QPushButton {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  padding:0 {px}px;"
            f"  font-size:{max(8, int(9 * s))}pt; font-weight:700; }}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; }}"
            f"QPushButton:disabled {{ color:{theme.TEXT_MEDIUM};"
            f"  border-color:{theme.BORDER_COLOR}; }}"
        )
        pri = (
            f"QPushButton {{ background:{theme.PRIMARY}; color:#FFF; border:none;"
            f"  border-radius:8px; padding:0 {px}px;"
            f"  font-size:{max(8, int(9 * s))}pt; font-weight:700; }}"
            f"QPushButton:hover {{ background:{theme.PRIMARY_HOVER}; }}"
        )

        self._btn_prev = QPushButton("← Ant.")
        self._btn_prev.setFixedHeight(btn_h)
        self._btn_prev.setStyleSheet(sec)
        self._btn_prev.clicked.connect(self.prev_clicked)
        ftr.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Próximo →")
        self._btn_next.setFixedHeight(btn_h)
        self._btn_next.setStyleSheet(pri)
        self._btn_next.clicked.connect(self.next_clicked)
        ftr.addWidget(self._btn_next)

        self._root.addLayout(ftr)

    # ── Conteúdo e lado ───────────────────────────────────────────────────────

    def set_content(
        self,
        title: str,
        body: str,
        step: int,
        total: int,
        side: str = "center",
    ) -> None:
        self._title.setText(title)
        self._body.setText(body)
        self._counter.setText(f"{step} / {total}")
        self._btn_prev.setEnabled(step > 1)
        self._btn_next.setText("Concluir ✓" if step == total else "Próximo →")

        # Ajusta margens para que o conteúdo não fique sob a seta
        if side != self._side:
            self._side = side
            p, a = self._pad, self._arrow
            if side == "right":       # seta protrui à esquerda
                self._root.setContentsMargins(p + a, p, p, p)
            elif side == "left":      # seta protrui à direita
                self._root.setContentsMargins(p, p, p + a, p)
            elif side == "bottom":    # seta protrui para cima
                self._root.setContentsMargins(p, p + a, p, p)
            elif side == "top":       # seta protrui para baixo
                self._root.setContentsMargins(p, p, p, p + a)
            else:
                self._root.setContentsMargins(p, p, p, p)
            self.update()

        self.adjustSize()

    # ── Pintura (fundo + seta) ────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = float(max(12, int(14 * self._scale)))
        a = float(self._arrow)
        w = float(self.width())
        h = float(self.height())

        body_path = QPainterPath()
        arrow_path = QPainterPath()

        if self._side == "right":
            # Seta aponta para a esquerda (elemento está à esquerda do balão)
            body_path.addRoundedRect(QRectF(a, 0, w - a, h), r, r)
            mid_y = h / 2
            arrow_path.moveTo(a,   mid_y - a * 0.65)
            arrow_path.lineTo(0.0, mid_y)
            arrow_path.lineTo(a,   mid_y + a * 0.65)
            arrow_path.closeSubpath()

        elif self._side == "left":
            # Seta aponta para a direita
            body_path.addRoundedRect(QRectF(0, 0, w - a, h), r, r)
            mid_y = h / 2
            arrow_path.moveTo(w - a, mid_y - a * 0.65)
            arrow_path.lineTo(w,     mid_y)
            arrow_path.lineTo(w - a, mid_y + a * 0.65)
            arrow_path.closeSubpath()

        elif self._side == "bottom":
            # Seta aponta para cima
            body_path.addRoundedRect(QRectF(0, a, w, h - a), r, r)
            mid_x = w / 2
            arrow_path.moveTo(mid_x - a * 0.65, a)
            arrow_path.lineTo(mid_x,             0.0)
            arrow_path.lineTo(mid_x + a * 0.65,  a)
            arrow_path.closeSubpath()

        elif self._side == "top":
            # Seta aponta para baixo
            body_path.addRoundedRect(QRectF(0, 0, w, h - a), r, r)
            mid_x = w / 2
            arrow_path.moveTo(mid_x - a * 0.65, h - a)
            arrow_path.lineTo(mid_x,             h)
            arrow_path.lineTo(mid_x + a * 0.65,  h - a)
            arrow_path.closeSubpath()

        else:
            body_path.addRoundedRect(QRectF(0, 0, w, h), r, r)

        full_path = body_path.united(arrow_path) if not arrow_path.isEmpty() else body_path
        painter.fillPath(full_path, QColor(theme.CARD_BG))
        painter.end()

    # ── Posicionamento ────────────────────────────────────────────────────────

    def reposition(self, spot: QRectF, side: str, bounds: QRectF) -> None:
        """Posiciona o balão adjacente ao spotlight, sem sair dos limites."""
        bw = self.width()
        bh = self.height()
        mg = 14

        if side == "center" or spot.isNull():
            x = (bounds.width()  - bw) / 2
            y = (bounds.height() - bh) / 2
        elif side == "bottom":
            x = spot.center().x() - bw / 2
            y = spot.bottom() + 14
        elif side == "top":
            x = spot.center().x() - bw / 2
            y = spot.top() - bh - 14
        elif side == "left":
            x = spot.left() - bw - 14
            y = spot.center().y() - bh / 2
        elif side == "right":
            x = spot.right() + 14
            y = spot.center().y() - bh / 2
        else:
            x = spot.center().x() - bw / 2
            y = spot.bottom() + 14

        x = max(mg, min(float(x), bounds.width()  - bw - mg))
        y = max(mg, min(float(y), bounds.height() - bh - mg))
        self.move(int(x), int(y))


# ── Overlay principal ─────────────────────────────────────────────────────────

class SpotlightOverlay(QWidget):
    """
    Overlay que escurece a janela inteira deixando um recorte iluminado
    em torno do widget-alvo de cada passo do tour.
    Inclui anel pulsante ao redor do spotlight.
    """

    finished = Signal()

    _PAGE = {
        "nova":               0,
        "historico":          1,
        "dashboard":          2,
        "tecnico":            3,
        "pedidos":            4,
        "pinheiro_industria": 5,
        "ar":                 6,
        "usuarios":           7,
        "config":             8,
        "feedback":           9,
        "entregas":           10,
    }

    def __init__(
        self,
        main_window: QWidget,
        steps: list[TourStep],
        scale: float,
        role: str = "",
        parent: QWidget | None = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent or main_window)
        self._mw      = main_window
        self._steps   = steps
        self._scale   = scale
        self._role    = role
        self._current = 0
        self._on_finish = on_finish

        # Estado do spotlight animado
        self._spot_rect:   QRectF = QRectF()
        self._spot_start:  QRectF = QRectF()
        self._spot_target: QRectF = QRectF()
        self._anim_t: float = 1.0

        # Timer de animação de movimento (~60 fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick)

        # Timer de pulso — corre sempre enquanto o overlay está visível
        self._pulse_t: float = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(16)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setGeometry(main_window.rect())
        main_window.installEventFilter(self)

        self._bubble = _Bubble(scale, self)
        self._bubble.next_clicked.connect(self._next)
        self._bubble.prev_clicked.connect(self._prev)
        self._bubble.skip_clicked.connect(self._finish)
        self._bubble.hide()

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def start(self) -> None:
        self.setGeometry(self._mw.rect())
        self.raise_()
        self.show()
        self._pulse_timer.start()
        self._go_to(0)

    def _go_to(self, index: int) -> None:
        if index < 0 or index >= len(self._steps):
            self._finish()
            return

        self._current = index
        step = self._steps[index]

        if step.navigate_key:
            self._navigate(step.navigate_key)
            QTimer.singleShot(320, lambda: self._scroll_then_show(index))
        else:
            self._scroll_then_show(index)

    def _scroll_then_show(self, index: int) -> None:
        """Rola o scroll area pai para o widget alvo (se necessário) e exibe o passo."""
        if index != self._current:
            return
        step = self._steps[index]
        try:
            widget = step.widget_getter()
        except Exception:
            widget = None

        if widget is not None and widget.isVisible():
            if self._scroll_to_widget(widget):
                # Pequena pausa para o Qt processar o reposicionamento do conteúdo
                QTimer.singleShot(80, lambda: self._show_step(index))
                return
        self._show_step(index)

    def _scroll_to_widget(self, widget: QWidget) -> bool:
        """
        Percorre a hierarquia de pais procurando o QScrollArea mais próximo.
        Se o widget estiver fora do viewport visível, chama ensureWidgetVisible.
        Retorna True se alguma rolagem foi necessária.
        """
        from PySide6.QtWidgets import QScrollArea
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                viewport = parent.viewport()
                top_in_vp = widget.mapTo(viewport, widget.rect().topLeft())
                bot_in_vp = top_in_vp.y() + widget.height()
                if top_in_vp.y() < 0 or bot_in_vp > viewport.height():
                    parent.ensureWidgetVisible(widget, 40, 40)
                    return True
                return False
            parent = parent.parentWidget()
        return False

    def _show_step(self, index: int) -> None:
        if index != self._current:
            return

        step = self._steps[index]
        n    = len(self._steps)

        self._bubble.set_content(
            step.title, step.body, index + 1, n, step.tooltip_side
        )

        target = self._resolve_rect(step)

        if self._spot_rect.isNull():
            self._spot_rect = target
            self._anim_t    = 1.0
            self.update()
        else:
            self._spot_start  = QRectF(self._spot_rect)
            self._spot_target = target
            self._anim_t      = 0.0
            self._anim_timer.start()

        self._bubble.reposition(target, step.tooltip_side, QRectF(self.rect()))
        self._bubble.show()
        self._bubble.raise_()

    def _next(self) -> None:
        if self._current >= len(self._steps) - 1:
            self._finish()
        else:
            self._go_to(self._current + 1)

    def _prev(self) -> None:
        if self._current > 0:
            self._go_to(self._current - 1)

    def _finish(self) -> None:
        self._anim_timer.stop()
        self._pulse_timer.stop()
        if self._on_finish is not None:
            try:
                self._on_finish()
            except Exception:
                pass
        elif self._role:
            res.mark_guide_shown(self._role)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ── Animação de movimento ─────────────────────────────────────────────────

    def _tick(self) -> None:
        self._anim_t = min(1.0, self._anim_t + 0.055)
        t = _ease_out_cubic(self._anim_t)
        s, e = self._spot_start, self._spot_target
        self._spot_rect = QRectF(
            s.x()      + (e.x()      - s.x())      * t,
            s.y()      + (e.y()      - s.y())      * t,
            s.width()  + (e.width()  - s.width())  * t,
            s.height() + (e.height() - s.height()) * t,
        )
        self.update()

        if self._anim_t >= 1.0:
            self._anim_timer.stop()
            step = self._steps[self._current]
            self._bubble.reposition(
                self._spot_rect, step.tooltip_side, QRectF(self.rect())
            )

    # ── Animação de pulso ─────────────────────────────────────────────────────

    def _pulse_tick(self) -> None:
        self._pulse_t += 0.065          # ~1.6 Hz — respiração suave
        if self._pulse_t > 2 * math.pi:
            self._pulse_t -= 2 * math.pi
        self.update()

    # ── Pintura ───────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Overlay escuro com recorte
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if not self._spot_rect.isNull():
            hole = QPainterPath()
            hole.addRoundedRect(self._spot_rect, 14, 14)
            path = path.subtracted(hole)
        p.fillPath(path, QColor(0, 0, 0, 195))

        if not self._spot_rect.isNull():
            # Anel estático
            pen = QPen(QColor(255, 255, 255, 80))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self._spot_rect.adjusted(-1, -1, 1, 1), 15, 15)

            # Anel pulsante (breathing)
            pulse = math.sin(self._pulse_t) * 0.5 + 0.5     # 0.0 → 1.0
            expand  = pulse * 10.0                            # 0 → 10 px
            alpha   = int(pulse * 110)                        # 0 → 110
            if alpha > 4:
                pulse_pen = QPen(QColor(255, 255, 255, alpha))
                pulse_pen.setWidth(2)
                p.setPen(pulse_pen)
                pr = self._spot_rect.adjusted(-expand, -expand, expand, expand)
                corner_r = 15.0 + expand * 0.4
                p.drawRoundedRect(pr, corner_r, corner_r)

        p.end()

    # ── Interação ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._spot_rect.contains(QPointF(event.pos())):
            self._next()
        super().mousePressEvent(event)

    # ── Redimensionamento ─────────────────────────────────────────────────────

    def eventFilter(self, obj, event):  # noqa: N802
        from PySide6.QtCore import QEvent
        if obj is self._mw and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._mw.rect())
        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _navigate(self, key: str) -> None:
        page = self._PAGE.get(key)
        if page is not None:
            # Garante que a view lazy seja instanciada antes de exibi-la
            if hasattr(self._mw, "_ensure_view"):
                self._mw._ensure_view(page)
            self._mw.stack.setCurrentIndex(page)
            self._mw.sidebar._highlight(key)

    def _resolve_rect(self, step: TourStep) -> QRectF:
        try:
            widget = step.widget_getter()
        except Exception:
            widget = None

        if widget is None or not widget.isVisible():
            return QRectF()

        pad       = step.padding
        global_tl = widget.mapToGlobal(widget.rect().topLeft())
        local_tl  = self.mapFromGlobal(global_tl)
        return QRectF(
            local_tl.x() - pad,
            local_tl.y() - pad,
            widget.width()  + 2 * pad,
            widget.height() + 2 * pad,
        )


# ── Easing ────────────────────────────────────────────────────────────────────

def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3
