"""
Tour guiado com spotlight — estilo Android.

Fluxo:
  SpotlightOverlay(main_window, steps, scale, role)
    .start()          → exibe o overlay, vai para o passo 0
    .finished         → signal emitido ao concluir ou pular

Pintura:
  QPainterPath.subtracted() cria o "recorte" sem precisar de
  WA_TranslucentBackground. O conteúdo do pai aparece no spotlight
  porque o overlay simplesmente não pinta aquela área.

Animação:
  Timer de 16 ms com easing OutCubic manual — sem dependência de
  QVariantAnimation (mais portável entre versões do PySide6).
"""
from __future__ import annotations

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
        Chave de navegação da sidebar a executar antes de exibir o passo
        (ex.: "nova", "config"). None → sem navegação.
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
    """Cartão flutuante com título, corpo e botões de navegação."""

    next_clicked = Signal()
    prev_clicked = Signal()
    skip_clicked = Signal()

    def __init__(self, scale: float, parent: QWidget) -> None:
        super().__init__(parent)
        self._scale = scale
        self._build()
        self.setAutoFillBackground(False)

    def _build(self) -> None:
        s = self._scale
        bw = max(280, int(320 * s))
        self.setFixedWidth(bw)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background:{theme.CARD_BG}; border-radius:{max(12, int(14 * s))}px;"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(max(22, int(30 * s)))
        shadow.setOffset(0, max(5, int(7 * s)))
        sc = QColor(0, 0, 0)
        sc.setAlpha(70)
        shadow.setColor(sc)
        self.setGraphicsEffect(shadow)

        pad = max(16, int(20 * s))
        root = QVBoxLayout(self)
        root.setContentsMargins(pad, pad, pad, pad)
        root.setSpacing(max(8, int(10 * s)))

        # ── Cabeçalho: título + contador ──────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(10, int(12 * s))}pt;"
            f"font-weight:800; background:transparent;"
        )
        hdr.addWidget(self._title, 1)

        self._counter = QLabel()
        self._counter.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt;"
            f"font-weight:600; background:transparent;"
        )
        hdr.addWidget(self._counter)
        root.addLayout(hdr)

        # ── Corpo ─────────────────────────────────────────────────────────────
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(9 * s))}pt;"
            f"font-weight:500; line-height:160%; background:transparent;"
        )
        root.addWidget(self._body)

        # ── Separador ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{theme.BORDER_COLOR}; border:none;")
        root.addWidget(sep)

        # ── Rodapé: pular + anterior + próximo ────────────────────────────────
        ftr = QHBoxLayout()
        ftr.setSpacing(max(6, int(8 * s)))
        btn_h = max(30, int(34 * s))

        self._btn_skip = QPushButton("Pular tour")
        self._btn_skip.setFixedHeight(btn_h)
        self._btn_skip.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{theme.TEXT_MEDIUM};"
            f"  border:none; font-size:{max(7, int(8 * s))}pt; font-weight:600; }}"
            f"QPushButton:hover {{ color:{theme.TEXT_DARK}; }}"
        )
        self._btn_skip.clicked.connect(self.skip_clicked)
        ftr.addWidget(self._btn_skip)
        ftr.addStretch()

        px = max(10, int(14 * s))
        sec_style = (
            f"QPushButton {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  padding:0 {px}px;"
            f"  font-size:{max(8, int(9 * s))}pt; font-weight:700; }}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; }}"
            f"QPushButton:disabled {{ color:{theme.TEXT_MEDIUM};"
            f"  border-color:{theme.BORDER_COLOR}; }}"
        )
        pri_style = (
            f"QPushButton {{ background:{theme.PRIMARY}; color:#FFF; border:none;"
            f"  border-radius:8px; padding:0 {px}px;"
            f"  font-size:{max(8, int(9 * s))}pt; font-weight:700; }}"
            f"QPushButton:hover {{ background:{theme.PRIMARY_HOVER}; }}"
        )

        self._btn_prev = QPushButton("← Ant.")
        self._btn_prev.setFixedHeight(btn_h)
        self._btn_prev.setStyleSheet(sec_style)
        self._btn_prev.clicked.connect(self.prev_clicked)
        ftr.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Próximo →")
        self._btn_next.setFixedHeight(btn_h)
        self._btn_next.setStyleSheet(pri_style)
        self._btn_next.clicked.connect(self.next_clicked)
        ftr.addWidget(self._btn_next)

        root.addLayout(ftr)

    # ── Conteúdo ──────────────────────────────────────────────────────────────

    def set_content(
        self,
        title: str,
        body: str,
        step: int,
        total: int,
    ) -> None:
        self._title.setText(title)
        self._body.setText(body)
        self._counter.setText(f"{step} / {total}")
        self._btn_prev.setEnabled(step > 1)
        is_last = step == total
        self._btn_next.setText("Concluir ✓" if is_last else "Próximo →")
        self.adjustSize()

    # ── Posicionamento ────────────────────────────────────────────────────────

    def reposition(self, spot: QRectF, side: str, bounds: QRectF) -> None:
        """Posiciona o balão adjacente ao spotlight, sem sair dos limites."""
        bw = self.width()
        bh = self.height()
        mg = 14  # margem mínima das bordas

        if side == "center" or spot.isNull():
            x = (bounds.width() - bw) / 2
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

        # Garante que o balão fica dentro do overlay
        x = max(mg, min(float(x), bounds.width() - bw - mg))
        y = max(mg, min(float(y), bounds.height() - bh - mg))
        self.move(int(x), int(y))


# ── Overlay principal ─────────────────────────────────────────────────────────

class SpotlightOverlay(QWidget):
    """
    Overlay que escurece a janela inteira deixando um recorte iluminado
    em torno do widget-alvo de cada passo do tour.
    """

    finished = Signal()

    # Mapeamento de chaves de nav para índices do QStackedWidget
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
    }

    def __init__(
        self,
        main_window: QWidget,
        steps: list[TourStep],
        scale: float,
        role: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent or main_window)
        self._mw      = main_window
        self._steps   = steps
        self._scale   = scale
        self._role    = role
        self._current = 0

        # Estado do spotlight animado
        self._spot_rect:   QRectF = QRectF()
        self._spot_start:  QRectF = QRectF()
        self._spot_target: QRectF = QRectF()
        self._anim_t: float = 1.0   # 0.0 → 1.0

        # Timer de animação ~60 fps
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick)

        # Sem fundo automático — a pintura customizada cuida de tudo
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        # Cobre toda a janela principal
        self.setGeometry(main_window.rect())
        main_window.installEventFilter(self)

        # Balão flutuante
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
        self._go_to(0)

    def _go_to(self, index: int) -> None:
        if index < 0 or index >= len(self._steps):
            self._finish()
            return

        self._current = index
        step = self._steps[index]

        if step.navigate_key:
            self._navigate(step.navigate_key)
            # Aguarda a view renderizar antes de mostrar o passo
            QTimer.singleShot(220, lambda: self._show_step(index))
        else:
            self._show_step(index)

    def _show_step(self, index: int) -> None:
        """Resolve o widget-alvo, anima o spotlight e posiciona o balão."""
        if index != self._current:
            return  # passo foi alterado enquanto aguardávamos o timer

        step = self._steps[index]
        n = len(self._steps)

        # Atualiza conteúdo do balão
        self._bubble.set_content(step.title, step.body, index + 1, n)

        # Calcula o rect-alvo em coordenadas do overlay
        target = self._resolve_rect(step)

        # Primeiro passo: aparece direto (sem animação de movimento)
        if self._spot_rect.isNull():
            self._spot_rect = target
            self._anim_t    = 1.0
            self.update()
        else:
            self._spot_start  = QRectF(self._spot_rect)
            self._spot_target = target
            self._anim_t      = 0.0
            self._anim_timer.start()

        # Posiciona o balão e o exibe
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
        res.mark_guide_shown(self._role)
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ── Animação ──────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._anim_t = min(1.0, self._anim_t + 0.055)  # ~18 frames ≈ 300 ms
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
            # Reposiciona o balão na posição final correta
            step = self._steps[self._current]
            self._bubble.reposition(
                self._spot_rect, step.tooltip_side, QRectF(self.rect())
            )

    # ── Pintura ───────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Caminho escuro = overlay inteiro menos o recorte do spotlight
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))

        if not self._spot_rect.isNull():
            hole = QPainterPath()
            hole.addRoundedRect(self._spot_rect, 14, 14)
            path = path.subtracted(hole)

        p.fillPath(path, QColor(0, 0, 0, 195))

        # Anel de luz ao redor do recorte
        if not self._spot_rect.isNull():
            pen = QPen(QColor(255, 255, 255, 80))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            glow = self._spot_rect.adjusted(-1, -1, 1, 1)
            p.drawRoundedRect(glow, 15, 15)

        p.end()

    # ── Interação ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Clique na área escura avança para o próximo passo."""
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
        """Navega para uma seção sem acionar guards/confirmações."""
        page = self._PAGE.get(key)
        if page is not None:
            self._mw.stack.setCurrentIndex(page)
            self._mw.sidebar._highlight(key)

    def _resolve_rect(self, step: TourStep) -> QRectF:
        """Converte a posição do widget-alvo para coordenadas do overlay."""
        try:
            widget = step.widget_getter()
        except Exception:
            widget = None

        if widget is None or not widget.isVisible():
            return QRectF()  # spotlight centralizado

        pad = step.padding
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
