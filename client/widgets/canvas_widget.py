"""
Canvas de desenho técnico com suporte a:
- Ferramentas: Seleção, Caneta livre, Linha, Retângulo, Elipse, Texto
- Shift: trava linha em 0°/45°/90°
- Inserção de imagem (PNG, JPG, BMP)
- Referência de arquivo PDF (exibe nome, abre externamente)
- Undo / Redo (Ctrl+Z / Ctrl+Y)
- Delete para apagar seleção
- Serialização completa para JSON (salvo no banco)
"""
import json
import math
import os
from enum import Enum

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QEvent
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
    QPixmap, QKeySequence, QAction, QCursor, QTransform,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QGraphicsScene,
    QGraphicsView, QGraphicsLineItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsItem, QInputDialog, QFileDialog,
    QPushButton, QLabel, QColorDialog, QSpinBox, QDoubleSpinBox,
    QSizePolicy, QFrame, QComboBox,
)
from ..core import theme


class Tool(Enum):
    SELECT   = "select"
    PEN      = "pen"
    ERASER   = "eraser"
    LINE     = "line"
    RECT     = "rect"
    ELLIPSE  = "ellipse"
    TEXT     = "text"
    IMAGE    = "image"


# Mapeamento estilo de linha ↔ string JSON
_STYLE_TO_STR = {
    Qt.PenStyle.SolidLine:   "solid",
    Qt.PenStyle.DashLine:    "dash",
    Qt.PenStyle.DotLine:     "dot",
    Qt.PenStyle.DashDotLine: "dashdot",
}
_STR_TO_STYLE = {v: k for k, v in _STYLE_TO_STR.items()}


def build_canvas_item_from_dict(d: dict) -> QGraphicsItem | None:
    t = d.get("type")
    pen_d = d.get("pen", {})
    pen = QPen(QColor(pen_d.get("color", "#000000")), pen_d.get("width", 2))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setStyle(_STR_TO_STYLE.get(pen_d.get("style", "solid"), Qt.PenStyle.SolidLine))
    rot = d.get("rotation", 0.0)

    item = None

    if t == "line":
        item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
        item.setPen(pen)

    elif t == "rect":
        item = QGraphicsRectItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)

    elif t == "ellipse":
        item = QGraphicsEllipseItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)

    elif t == "path":
        path = QPainterPath()
        points = d.get("points", [])
        if points:
            path.moveTo(QPointF(points[0][0], points[0][1]))
            for pt in points[1:]:
                path.lineTo(QPointF(pt[0], pt[1]))
        item = QGraphicsPathItem(path)
        item.setPen(pen)

    elif t == "text":
        item = QGraphicsTextItem(d.get("text", ""))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont(theme.FONT_PRIMARY, d.get("font_size", 12))
        item.setFont(font)

    elif t == "image":
        path = d.get("path", "")
        if path and os.path.exists(path):
            pix = QPixmap(path)
            item = QGraphicsPixmapItem(pix)
            item.setPos(QPointF(d["x"], d["y"]))
            item.setData(0, {"type": "image", "path": path})

    if item is not None and rot:
        item.setRotation(rot)

    return item


def load_canvas_scene(scene: QGraphicsScene, data: str, selectable: bool = False) -> dict:
    scene.clear()
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return {"items": 0, "pdf": ""}

    count = 0
    for item_data in obj.get("items", []):
        item = build_canvas_item_from_dict(item_data)
        if item:
            if selectable:
                item.setFlags(
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                )
            scene.addItem(item)
            count += 1

    return {"items": count, "pdf": obj.get("pdf", "")}


# ── Cena personalizada ────────────────────────────────────────────────────────
class DrawingScene(QGraphicsScene):
    def __init__(self, canvas_widget):
        super().__init__()
        self.cw = canvas_widget          # referência ao widget pai
        self._start: QPointF | None = None
        self._preview_item: QGraphicsItem | None = None
        self._path_item: QGraphicsPathItem | None = None
        self._painter_path: QPainterPath | None = None
        self.setBackgroundBrush(QBrush(QColor("#ffffff")))
        # Estado da alça de rotação livre
        self._rotating_item: QGraphicsItem | None = None
        self._rotate_start_angle: float = 0.0
        self._rotate_start_rotation: float = 0.0
        self.selectionChanged.connect(self._on_selection_changed)

    # ── Grade de fundo (visual only — não serializada) ───────────────────────
    GRID_MINOR = 20          # espaçamento da grade fina (px)
    GRID_MAJOR = 100         # espaçamento da grade grossa (a cada 5 linhas)
    HANDLE_R   = 8           # raio da alça de rotação (px tela)
    HANDLE_OFF = 28          # distância acima do item (px tela)
    HANDLE_HIT = 14          # raio de clique da alça (px tela)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        # Linhas menores
        pen_minor = QPen(QColor("#E0E8F4"), 0.7)
        pen_minor.setCosmetic(True)          # não escala com zoom
        # Linhas maiores (a cada 5 células)
        pen_major = QPen(QColor("#B8CCE8"), 1.2)
        pen_major.setCosmetic(True)

        step = self.GRID_MINOR
        left  = int(rect.left())  - (int(rect.left())  % step)
        top   = int(rect.top())   - (int(rect.top())   % step)

        x = left
        while x <= rect.right():
            painter.setPen(pen_major if (x % self.GRID_MAJOR == 0) else pen_minor)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step

        y = top
        while y <= rect.bottom():
            painter.setPen(pen_major if (y % self.GRID_MAJOR == 0) else pen_minor)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    # ── Alça de rotação livre ─────────────────────────────────────────────────
    def _view(self):
        """Retorna a primeira view associada à cena."""
        views = self.views()
        return views[0] if views else None

    def _handle_screen_pos(self, item: QGraphicsItem) -> QPointF:
        """Posição da alça de rotação em coordenadas de viewport (px fixos)."""
        view = self._view()
        if view is None:
            return QPointF()
        br = item.boundingRect()
        top_center = item.mapToScene(QPointF(br.center().x(), br.top()))
        vp = view.mapFromScene(top_center)
        return QPointF(vp.x(), vp.y() - self.HANDLE_OFF)

    def _rotation_item_at(self, pos_scene: QPointF) -> QGraphicsItem | None:
        """Retorna o item selecionado cuja alça de rotação cobre pos_scene."""
        if self.cw.tool != Tool.SELECT:
            return None
        view = self._view()
        if view is None:
            return None
        vp = QPointF(view.mapFromScene(pos_scene))
        for item in self.selectedItems():
            hp = self._handle_screen_pos(item)
            if math.hypot(vp.x() - hp.x(), vp.y() - hp.y()) <= self.HANDLE_HIT:
                return item
        return None

    def _on_selection_changed(self):
        """Sincroniza spin_font; remove edição inline de textos deselecionados."""
        selected = set(self.selectedItems())
        # Remove modo de edição inline de textos que saíram da seleção
        for item in self.items():
            if isinstance(item, QGraphicsTextItem) and item not in selected:
                item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Sincroniza tamanho da fonte com o primeiro texto selecionado
        for item in selected:
            if isinstance(item, QGraphicsTextItem):
                size = item.font().pointSize()
                if size > 0:
                    self.cw.spin_font.blockSignals(True)
                    self.cw.spin_font.setValue(size)
                    self.cw.spin_font.blockSignals(False)
                return

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Desenha alças de rotação sobre os itens selecionados (coords de tela)."""
        super().drawForeground(painter, rect)
        if self.cw.tool != Tool.SELECT:
            return
        selected = self.selectedItems()
        if not selected:
            return
        view = self._view()
        if view is None:
            return

        painter.save()
        painter.resetTransform()   # agora em coords de viewport (px fixos, sem zoom)

        r = self.HANDLE_R
        for item in selected:
            br = item.boundingRect()
            top_center = item.mapToScene(QPointF(br.center().x(), br.top()))
            anchor = QPointF(view.mapFromScene(top_center))
            hp = QPointF(anchor.x(), anchor.y() - self.HANDLE_OFF)

            # Braço tracejado do item até a alça
            arm_pen = QPen(QColor("#2D7FF9"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(arm_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(anchor, hp)

            # Círculo azul
            painter.setPen(QPen(QColor("#1A5FC8"), 1.5))
            painter.setBrush(QBrush(QColor(45, 127, 249, 200)))
            painter.drawEllipse(hp, r, r)

            # Símbolo ↻ no centro
            painter.setPen(QPen(QColor("#ffffff")))
            icon_font = QFont()
            icon_font.setPointSize(7)
            icon_font.setBold(True)
            painter.setFont(icon_font)
            painter.drawText(
                QRectF(hp.x() - r, hp.y() - r, r * 2, r * 2),
                Qt.AlignmentFlag.AlignCenter,
                "↻",
            )

        painter.restore()

    def _pen(self) -> QPen:
        p = QPen(QColor(self.cw.color), self.cw.pen_width)
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setStyle(self.cw.pen_style)
        return p

    def _erase_at(self, pos: QPointF):
        """Remove todos os itens desenhados na posição dada."""
        for item in self.items(pos):
            if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem,
                                  QGraphicsEllipseItem, QGraphicsPathItem,
                                  QGraphicsTextItem, QGraphicsPixmapItem)):
                self.removeItem(item)
                if item in self.cw._undo_stack:
                    self.cw._undo_stack.remove(item)
                self.cw.changed.emit()

    def _constrain(self, start: QPointF, end: QPointF) -> QPointF:
        """Restringe a 0°/45°/90° quando Shift está pressionado."""
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        angle = math.degrees(math.atan2(dy, dx))
        dist  = math.hypot(dx, dy)
        snap  = round(angle / 45) * 45
        rad   = math.radians(snap)
        return QPointF(start.x() + dist * math.cos(rad),
                       start.y() + dist * math.sin(rad))

    def mousePressEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()

        # Verificar alça de rotação antes de qualquer outra lógica (SELECT)
        if tool == Tool.SELECT and event.button() == Qt.MouseButton.LeftButton:
            hit = self._rotation_item_at(pos)
            if hit:
                self._rotating_item = hit
                center = hit.mapToScene(hit.boundingRect().center())
                self._rotate_start_angle = math.atan2(
                    pos.y() - center.y(), pos.x() - center.x()
                )
                self._rotate_start_rotation = hit.rotation()
                event.accept()
                return

        if tool == Tool.SELECT:
            super().mousePressEvent(event)
            return

        if tool == Tool.ERASER:
            self._erase_at(pos)
            return

        if tool == Tool.TEXT:
            text, ok = QInputDialog.getText(self.cw, "Texto", "Digite o texto:")
            if ok and text:
                item = QGraphicsTextItem(text)
                item.setPos(pos)
                item.setDefaultTextColor(QColor(self.cw.color))
                font = QFont(theme.FONT_PRIMARY, self.cw.font_size)
                item.setFont(font)
                item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                              QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self.addItem(item)
                self.cw._push_undo(item)
            return

        if tool == Tool.IMAGE:
            self.cw._insert_image(pos)
            return

        self._start = pos

        if tool == Tool.PEN:
            self._painter_path = QPainterPath(pos)
            self._path_item = QGraphicsPathItem()
            self._path_item.setPen(self._pen())
            self.addItem(self._path_item)

        elif tool == Tool.LINE:
            self._preview_item = self.addLine(pos.x(), pos.y(), pos.x(), pos.y(), self._pen())

        elif tool == Tool.RECT:
            self._preview_item = self.addRect(QRectF(pos, pos), self._pen())

        elif tool == Tool.ELLIPSE:
            self._preview_item = self.addEllipse(QRectF(pos, pos), self._pen())

    def mouseMoveEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()

        # Arrastar alça → rotação livre
        if self._rotating_item is not None:
            center = self._rotating_item.mapToScene(
                self._rotating_item.boundingRect().center()
            )
            angle = math.atan2(pos.y() - center.y(), pos.x() - center.x())
            delta = math.degrees(angle - self._rotate_start_angle)
            self._rotating_item.setRotation(self._rotate_start_rotation + delta)
            self.update()
            event.accept()
            return

        if tool == Tool.ERASER and event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at(pos)
            return

        if self._start is None:
            super().mouseMoveEvent(event)
            return

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if tool == Tool.PEN and self._painter_path and self._path_item:
            self._painter_path.lineTo(pos)
            self._path_item.setPath(self._painter_path)

        elif tool == Tool.LINE and self._preview_item:
            end = self._constrain(self._start, pos) if shift else pos
            self._preview_item.setLine(self._start.x(), self._start.y(),
                                       end.x(), end.y())

        elif tool == Tool.RECT and self._preview_item:
            self._preview_item.setRect(QRectF(self._start, pos).normalized())

        elif tool == Tool.ELLIPSE and self._preview_item:
            self._preview_item.setRect(QRectF(self._start, pos).normalized())

    def mouseReleaseEvent(self, event):
        # Finalizar rotação livre
        if self._rotating_item is not None:
            self._rotating_item = None
            self.cw.changed.emit()
            self.update()
            event.accept()
            return

        tool = self.cw.tool
        pos  = event.scenePos()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self._start is None:
            super().mouseReleaseEvent(event)
            return

        if tool == Tool.PEN and self._path_item:
            item = self._path_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.cw._push_undo(item)
            self._path_item = None
            self._painter_path = None

        elif tool in (Tool.LINE, Tool.RECT, Tool.ELLIPSE) and self._preview_item:
            if tool == Tool.LINE and shift:
                end = self._constrain(self._start, pos)
                self._preview_item.setLine(self._start.x(), self._start.y(),
                                           end.x(), end.y())
            item = self._preview_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.cw._push_undo(item)
            self._preview_item = None

        self._start = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            for item in self.selectedItems():
                self.removeItem(item)
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Duplo clique em texto → ativa edição inline."""
        if (self.cw.tool == Tool.SELECT
                and event.button() == Qt.MouseButton.LeftButton):
            item = self.itemAt(event.scenePos(), QTransform())
            if isinstance(item, QGraphicsTextItem):
                item.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextEditorInteraction
                )
                item.setFocus()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


# ── View com pan por botão do meio + Space+arraste ───────────────────────────
class DrawingView(QGraphicsView):
    """
    QGraphicsView com zoom por scroll e pan por botão do meio ou Space+drag.

    Os eventos de mouse chegam primeiro no viewport (widget filho interno do
    QGraphicsView), não na view em si. Por isso usamos um event filter
    instalado diretamente no viewport — é a única forma confiável de
    interceptar esses eventos antes do Qt repassar para a cena.
    """

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self._panning    = False
        self._pan_start  = None
        self._space_held = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # Instala filtro no viewport — eventos chegam aqui antes de qualquer
        # processamento interno do QGraphicsView
        self.viewport().installEventFilter(self)

    # ── Event filter no viewport ──────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is not self.viewport():
            return super().eventFilter(obj, event)

        t = event.type()

        # ── Zoom por scroll ───────────────────────────────────────────────────
        if t == QEvent.Type.Wheel:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            return True   # consome — não rola a cena como scroll normal

        # ── Início do pan ─────────────────────────────────────────────────────
        if t == QEvent.Type.MouseButtonPress:
            mid        = event.button() == Qt.MouseButton.MiddleButton
            space_left = (event.button() == Qt.MouseButton.LeftButton
                          and self._space_held)
            if mid or space_left:
                self._start_pan(event.position().toPoint())
                return True   # consome — não chega na cena

        # ── Arraste do pan ────────────────────────────────────────────────────
        if t == QEvent.Type.MouseMove and self._panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            return True

        # ── Fim do pan ────────────────────────────────────────────────────────
        if t == QEvent.Type.MouseButtonRelease and self._panning:
            if event.button() in (Qt.MouseButton.MiddleButton,
                                   Qt.MouseButton.LeftButton):
                self._stop_pan()
                return True

        return super().eventFilter(obj, event)

    # ── Space + arrastar (teclas captadas na view, não no viewport) ───────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _start_pan(self, pos):
        self._panning   = True
        self._pan_start = pos
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _stop_pan(self):
        self._panning   = False
        self._pan_start = None
        cursor = (Qt.CursorShape.OpenHandCursor if self._space_held
                  else Qt.CursorShape.ArrowCursor)
        self.setCursor(cursor)


# ── Widget principal ──────────────────────────────────────────────────────────
class DrawingCanvas(QWidget):
    changed = Signal()     # emitido quando o canvas é modificado

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale      = scale
        self.tool       = Tool.SELECT
        self.color      = "#000000"
        self.pen_width  = 2
        self.pen_style  = Qt.PenStyle.SolidLine
        self.font_size  = 12
        self._undo_stack: list[QGraphicsItem] = []
        self._redo_stack: list[QGraphicsItem] = []
        self._attached_pdf: str = ""
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("DESENHO / REFERÊNCIA")
        fs = max(9, int(11 * self.scale))
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{fs}pt; font-weight:bold;"
        )
        layout.addWidget(title)
        title.setText("🎨 DESENHO / REFERÊNCIA")

        s  = self.scale
        fh = max(24, int(28 * s))   # altura padrão dos botões
        fs = max(8, int(9 * s))     # fonte padrão
        lbl_style = f"color:{theme.TEXT_MEDIUM}; font-size:{fs}pt;"

        def _lbl(txt):
            l = QLabel(txt)
            l.setStyleSheet(lbl_style)
            return l

        # ── Linha 1: Ferramentas + Cor + Estilo + Fonte ───────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self._tool_btns: dict[Tool, QPushButton] = {}

        tools = [
            (Tool.SELECT,  "🖱️ Selec.",   "S"),
            (Tool.PEN,     "✏️ Caneta",   "P"),
            (Tool.ERASER,  "🧹 Borracha", "X"),
            (Tool.LINE,    "📏 Linha",    "L"),
            (Tool.RECT,    "⬛ Ret.",     "R"),
            (Tool.ELLIPSE, "⭕ Elipse",   "E"),
            (Tool.TEXT,    "T Texto",     "T"),
        ]
        for t, label, key in tools:
            btn = QPushButton(f"{label} [{key}]")
            btn.setCheckable(True)
            btn.setFixedHeight(fh)
            btn.clicked.connect(lambda checked, tool=t: self._set_tool(tool))
            btn.setStyleSheet(self._tool_btn_style())
            self._tool_btns[t] = btn
            row1.addWidget(btn)

        row1.addSpacing(8)

        # Cor
        self.btn_color = QPushButton("🎨")
        self.btn_color.setFixedSize(fh, fh)
        self.btn_color.setStyleSheet(
            f"background:{self.color}; border-radius:8px; border:2px solid {theme.BORDER_COLOR};"
            f"font-size:{fs}pt;"
        )
        self.btn_color.clicked.connect(self._pick_color)
        row1.addWidget(self.btn_color)

        row1.addSpacing(8)

        # Espessura
        row1.addWidget(_lbl("Esp.:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 20)
        self.spin_width.setValue(self.pen_width)
        self.spin_width.setFixedWidth(max(44, int(52 * s)))
        self.spin_width.setFixedHeight(fh)
        self.spin_width.valueChanged.connect(lambda v: setattr(self, "pen_width", v))
        row1.addWidget(self.spin_width)

        row1.addSpacing(8)

        # Estilo de linha
        row1.addWidget(_lbl("Linha:"))
        self.combo_style = QComboBox()
        self.combo_style.setFixedHeight(fh)
        self.combo_style.setFixedWidth(max(110, int(130 * s)))
        self.combo_style.addItem("─── Sólida",    Qt.PenStyle.SolidLine)
        self.combo_style.addItem("- - Tracejada", Qt.PenStyle.DashLine)
        self.combo_style.addItem("··· Pontilhada", Qt.PenStyle.DotLine)
        self.combo_style.addItem("-·- Misto",     Qt.PenStyle.DashDotLine)
        self.combo_style.currentIndexChanged.connect(
            lambda i: setattr(self, "pen_style",
                               self.combo_style.itemData(i))
        )
        row1.addWidget(self.combo_style)

        row1.addSpacing(8)

        # Tamanho da fonte
        row1.addWidget(_lbl("Fonte:"))
        self.spin_font = QSpinBox()
        self.spin_font.setRange(6, 96)
        self.spin_font.setValue(self.font_size)
        self.spin_font.setSuffix(" pt")
        self.spin_font.setFixedWidth(max(58, int(68 * s)))
        self.spin_font.setFixedHeight(fh)
        self.spin_font.valueChanged.connect(self._on_font_size_changed)
        row1.addWidget(self.spin_font)

        row1.addStretch()
        layout.addLayout(row1)

        # ── Linha 2: Ações ────────────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        btn_undo = QPushButton("↩️ Desfazer")
        btn_undo.setFixedHeight(fh)
        btn_undo.clicked.connect(self._undo)
        btn_undo.setStyleSheet(self._tool_btn_style())

        btn_redo = QPushButton("↪️ Refazer")
        btn_redo.setFixedHeight(fh)
        btn_redo.clicked.connect(self._redo)
        btn_redo.setStyleSheet(self._tool_btn_style())

        row2.addWidget(btn_undo)
        row2.addWidget(btn_redo)
        row2.addSpacing(8)

        # Rotação
        row2.addWidget(_lbl("↻ Girar:"))
        self.spin_rotate = QDoubleSpinBox()
        self.spin_rotate.setRange(-360, 360)
        self.spin_rotate.setValue(45)
        self.spin_rotate.setSingleStep(15)
        self.spin_rotate.setSuffix("°")
        self.spin_rotate.setFixedWidth(max(68, int(80 * s)))
        self.spin_rotate.setFixedHeight(fh)
        row2.addWidget(self.spin_rotate)

        btn_rotate = QPushButton("Aplicar")
        btn_rotate.setFixedHeight(fh)
        btn_rotate.clicked.connect(self._rotate_selected)
        btn_rotate.setStyleSheet(self._tool_btn_style())
        row2.addWidget(btn_rotate)

        row2.addSpacing(8)

        btn_img = QPushButton("🖼️ Imagem")
        btn_img.setFixedHeight(fh)
        btn_img.clicked.connect(lambda: self._insert_image())
        btn_img.setStyleSheet(self._tool_btn_style())

        btn_pdf = QPushButton("📎 PDF")
        btn_pdf.setFixedHeight(fh)
        btn_pdf.clicked.connect(self._attach_pdf)
        btn_pdf.setStyleSheet(self._tool_btn_style())

        btn_clear = QPushButton("🗑️ Limpar")
        btn_clear.setFixedHeight(fh)
        btn_clear.clicked.connect(self._clear)
        btn_clear.setStyleSheet(
            f"QPushButton {{ background:#FDEEEF; color:{theme.DANGER};"
            f"border:1px solid #F4C7CC; border-radius:8px; padding:2px 8px;"
            f"font-size:{fs}pt; font-weight:600; }}"
            f"QPushButton:hover {{ background:#FBE1E4; }}"
        )
        row2.addWidget(btn_img)
        row2.addWidget(btn_pdf)
        row2.addWidget(btn_clear)
        row2.addStretch()
        layout.addLayout(row2)

        # ── Dica de teclado ──────────────────────────────────────────────────
        hint = QLabel(
            "✨ Shift = traço reto  |  Del = apagar seleção  |  "
            "Scroll = zoom  |  Botão do meio / Space+drag = mover  |  "
            "Selecionar → alça ↻ azul = girar livremente  |  2× clique = editar texto"
        )
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8*s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

        # ── Cena + View ──────────────────────────────────────────────────────
        self.scene = DrawingScene(self)
        self.view  = DrawingView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:8px; background:#fff;"
        )
        self.view.setMinimumHeight(max(250, int(300 * self.scale)))
        layout.addWidget(self.view)

        # ── Painel de PDF ────────────────────────────────────────────────────
        self.pdf_panel = QFrame()
        self.pdf_panel.setStyleSheet(
            f"background:{theme.SELECTION_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
        )
        pdf_layout = QHBoxLayout(self.pdf_panel)
        pdf_layout.setContentsMargins(10, 6, 10, 6)
        self.pdf_label = QLabel("Nenhum arquivo anexado")
        self.pdf_label.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8,int(10*self.scale))}pt;")
        self.pdf_label.setText("Nenhum PDF anexado")
        btn_open_pdf = QPushButton("Abrir")
        btn_open_pdf.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_open_pdf.clicked.connect(self._open_pdf)
        btn_open_pdf.setText("📂 Abrir")
        btn_rm_pdf = QPushButton("X")
        btn_rm_pdf.setFixedWidth(28)
        btn_rm_pdf.setStyleSheet(theme.danger_btn_style(self.scale))
        btn_rm_pdf.clicked.connect(self._remove_pdf)
        pdf_layout.addWidget(QLabel("📎 PDF"))
        pdf_layout.addWidget(self.pdf_label, 1)
        pdf_layout.addWidget(btn_open_pdf)
        pdf_layout.addWidget(btn_rm_pdf)
        self.pdf_panel.setVisible(False)
        layout.addWidget(self.pdf_panel)

        # Selecionar ferramenta inicial
        self._set_tool(Tool.SELECT)

        # Atalhos de teclado
        self._setup_shortcuts()

    def _tool_btn_style(self) -> str:
        fs = max(8, int(9 * self.scale))
        return (
            f"QPushButton {{ background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:8px; padding:2px 8px; font-size:{fs}pt; color:{theme.TEXT_DARK}; font-weight:600; }}"
            f"QPushButton:checked {{ background:{theme.PRIMARY}; color:#fff; border-color:{theme.PRIMARY}; }}"
            f"QPushButton:hover:!checked {{ background:{theme.SELECTION_BG}; border-color:{theme.PRIMARY_LIGHT}; }}"
        )

    def _setup_shortcuts(self):
        shortcuts = {
            Qt.Key.Key_S: Tool.SELECT,
            Qt.Key.Key_P: Tool.PEN,
            Qt.Key.Key_X: Tool.ERASER,
            Qt.Key.Key_L: Tool.LINE,
            Qt.Key.Key_R: Tool.RECT,
            Qt.Key.Key_E: Tool.ELLIPSE,
            Qt.Key.Key_T: Tool.TEXT,
        }
        for key, tool in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(lambda checked=False, t=tool: self._set_tool(t))
            self.addAction(action)

        undo_action = QAction(self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        self.addAction(undo_action)

        redo_action = QAction(self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        self.addAction(redo_action)

    # ── Ferramentas ──────────────────────────────────────────────────────────
    def _set_tool(self, tool: Tool):
        self.tool = tool
        for t, btn in self._tool_btns.items():
            btn.setChecked(t == tool)
        if tool == Tool.SELECT:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
        elif tool == Tool.ERASER:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.CrossCursor)

    def _rotate_selected(self):
        """Rotaciona todos os itens selecionados pelo ângulo definido no spin."""
        angle = self.spin_rotate.value()
        for item in self.scene.selectedItems():
            item.setRotation(item.rotation() + angle)
        self.changed.emit()

    def _on_font_size_changed(self, v: int):
        """Atualiza font_size e aplica nos textos selecionados em tempo real."""
        self.font_size = v
        if not hasattr(self, "scene"):
            return
        for item in self.scene.selectedItems():
            if isinstance(item, QGraphicsTextItem):
                f = item.font()
                f.setPointSize(v)
                item.setFont(f)
        self.changed.emit()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Escolha a cor")
        if color.isValid():
            self.color = color.name()
            self.btn_color.setStyleSheet(
                f"background:{self.color}; border-radius:8px; border:1px solid {theme.BORDER_COLOR};"
            )

    # ── Undo / Redo ──────────────────────────────────────────────────────────
    def _push_undo(self, item: QGraphicsItem):
        self._undo_stack.append(item)
        self._redo_stack.clear()
        self.changed.emit()

    def _undo(self):
        if self._undo_stack:
            item = self._undo_stack.pop()
            self.scene.removeItem(item)
            self._redo_stack.append(item)
            self.changed.emit()

    def _redo(self):
        if self._redo_stack:
            item = self._redo_stack.pop()
            self.scene.addItem(item)
            self._undo_stack.append(item)
            self.changed.emit()

    # ── Imagem ───────────────────────────────────────────────────────────────
    def _insert_image(self, pos: QPointF = None):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar imagem",
            "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        # Limita tamanho ao canvas
        max_w = min(600, self.view.width() - 40)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)

        item = QGraphicsPixmapItem(pixmap)
        p = pos or QPointF(10, 10)
        item.setPos(p)
        item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        item.setData(0, {"type": "image", "path": path})
        self.scene.addItem(item)
        self._push_undo(item)

    # ── PDF ──────────────────────────────────────────────────────────────────
    def _attach_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar PDF",
            "",
            "PDF (*.pdf)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self._attached_pdf = path
            self.pdf_label.setText(os.path.basename(path))
            self.pdf_panel.setVisible(True)
            self.changed.emit()

    def _open_pdf(self):
        if self._attached_pdf and os.path.exists(self._attached_pdf):
            import subprocess
            subprocess.Popen(["start", "", self._attached_pdf], shell=True)

    def _remove_pdf(self):
        self._attached_pdf = ""
        self.pdf_panel.setVisible(False)
        self.changed.emit()

    # ── Limpar ───────────────────────────────────────────────────────────────
    def _clear(self):
        self.scene.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.changed.emit()

    # ── Serialização ─────────────────────────────────────────────────────────
    def to_json(self) -> str:
        items = []
        for item in self.scene.items():
            d = self._item_to_dict(item)
            if d:
                items.append(d)
        return json.dumps({
            "version": 1,
            "items": items,
            "pdf": self._attached_pdf,
        }, ensure_ascii=False)

    def from_json(self, data: str):
        self._clear()
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        self._attached_pdf = obj.get("pdf", "")
        if self._attached_pdf:
            self.pdf_label.setText(os.path.basename(self._attached_pdf))
            self.pdf_panel.setVisible(True)
        load_canvas_scene(self.scene, data, selectable=True)

    def _item_to_dict(self, item: QGraphicsItem) -> dict | None:
        pen_data = lambda p: {
            "color": p.color().name(),
            "width": p.width(),
            "style": _STYLE_TO_STR.get(p.style(), "solid"),
        }

        rot = item.rotation()   # 0.0 quando não rotacionado

        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            return {"type": "line",
                    "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            return {"type": "rect",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            return {"type": "ellipse",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append([el.x, el.y])
            return {"type": "path", "points": points,
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsTextItem):
            return {"type": "text",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "text": item.toPlainText(),
                    "color": item.defaultTextColor().name(),
                    "font_size": item.font().pointSize(),
                    "rotation": rot}

        if isinstance(item, QGraphicsPixmapItem):
            meta = item.data(0) or {}
            return {"type": "image",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "path": meta.get("path", ""), "rotation": rot}

        return None

    def _item_from_dict(self, d: dict) -> QGraphicsItem | None:
        return build_canvas_item_from_dict(d)


class CanvasPreview(QGraphicsView):
    def __init__(self, scale: float = 1.0, parent=None):
        scene = QGraphicsScene(parent)
        super().__init__(scene, parent)
        self.scale_factor = scale
        self._scene = scene
        self._last_result = {"items": 0, "pdf": ""}
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:8px; background:#fff;"
        )
        self.setMinimumHeight(max(220, int(260 * scale)))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)

    @property
    def last_result(self) -> dict:
        return self._last_result

    def set_json(self, data: str):
        self._last_result = load_canvas_scene(self._scene, data, selectable=False)
        if self._last_result["items"] == 0:
            placeholder = self._scene.addText("Sem desenho salvo")
            placeholder.setDefaultTextColor(QColor(theme.TEXT_LIGHT))
            font = QFont(theme.FONT_PRIMARY, max(9, int(10 * self.scale_factor)))
            placeholder.setFont(font)
            placeholder.setPos(20, 20)
            placeholder.setPlainText("🖼️ Nenhum desenho salvo")
        self._fit_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_scene()

    def _fit_scene(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 100, 80)
        self.fitInView(rect.adjusted(-10, -10, 10, 10), Qt.AspectRatioMode.KeepAspectRatio)
