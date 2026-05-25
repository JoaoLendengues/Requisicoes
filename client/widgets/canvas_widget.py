"""
Canvas de desenho técnico com suporte a:
- Ferramentas: Seleção, Caneta livre, Linha, Retângulo, Elipse, Texto
- Shift: trava linha em 0°/45°/90°
- Inserção de imagem (PNG, JPG, BMP)
- Referência de arquivo PDF (exibe nome, abre externamente)
- Undo / Redo (Ctrl+Z / Ctrl+Y)
- Ctrl+T: Free Transform (bounding box + arrastar cantos para girar)
- Delete para apagar seleção
- Serialização completa para JSON (salvo no banco)
"""
import json
import math
import os
from enum import Enum

from PySide6.QtCore import (
    Qt, QPointF, QRectF, Signal, QEvent,
    QByteArray, QBuffer, QIODevice, QMimeData,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
    QPixmap, QKeySequence, QAction, QCursor, QTransform, QGuiApplication,
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
from ..core.text_case import normalize_upper_text


class Tool(Enum):
    SELECT   = "select"
    PEN      = "pen"
    ERASER   = "eraser"
    LINE     = "line"
    RULER    = "ruler"
    ARROW    = "arrow"
    CURVE    = "curve"
    TRIANGLE = "triangle"
    PENTAGON = "pentagon"
    HEXAGON  = "hexagon"
    RECT     = "rect"
    ELLIPSE  = "ellipse"
    TEXT     = "text"
    IMAGE    = "image"


# Mapeamento estilo de linha -> string JSON
_STYLE_TO_STR = {
    Qt.PenStyle.SolidLine:   "solid",
    Qt.PenStyle.DashLine:    "dash",
    Qt.PenStyle.DotLine:     "dot",
    Qt.PenStyle.DashDotLine: "dashdot",
}
_STR_TO_STYLE = {v: k for k, v in _STYLE_TO_STR.items()}
_CANVAS_CLIPBOARD_MIME = "application/x-requisicoes-canvas-items"


def _pixmap_to_base64(pixmap: QPixmap) -> str:
    if pixmap.isNull():
        return ""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data().toBase64()).decode("ascii")
    buffer.close()
    return data


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

    elif t == "ruler_measure_line":
        item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
        item.setPen(pen)
        item.setData(0, {"type": "ruler_measure_line"})

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
        item = QGraphicsTextItem(normalize_upper_text(d.get("text", "")))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont(theme.FONT_PRIMARY, d.get("font_size", 12))
        item.setFont(font)

    elif t == "ruler_measure_text":
        item = QGraphicsTextItem(d.get("text", ""))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont(theme.FONT_PRIMARY, d.get("font_size", 12))
        item.setFont(font)
        item.setData(0, {"type": "ruler_measure_text"})

    elif t == "image":
        path = d.get("path", "")
        image_data = d.get("image_data", "")
        pix = QPixmap()
        if path and os.path.exists(path):
            pix = QPixmap(path)
        elif image_data:
            pix.loadFromData(QByteArray.fromBase64(image_data.encode("ascii")), "PNG")
        if not pix.isNull():
            display_w = int(d.get("display_w", 0) or 0)
            display_h = int(d.get("display_h", 0) or 0)
            if display_w > 0 and display_h > 0 and (
                pix.width() != display_w or pix.height() != display_h
            ):
                pix = pix.scaled(
                    display_w,
                    display_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            item = QGraphicsPixmapItem(pix)
            item.setPos(QPointF(d["x"], d["y"]))
            item.setData(0, {
                "type": "image",
                "path": path,
                "image_data": image_data,
                "display_w": pix.width(),
                "display_h": pix.height(),
            })

    if item is not None and ("pos_x" in d or "pos_y" in d):
        item.setPos(QPointF(d.get("pos_x", 0.0), d.get("pos_y", 0.0)))
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


# Cena personalizada
class DrawingScene(QGraphicsScene):
    def __init__(self, canvas_widget):
        super().__init__()
        self.cw = canvas_widget
        self._start: QPointF | None = None
        self._ruler_line_item: QGraphicsLineItem | None = None
        self._ruler_text_item: QGraphicsTextItem | None = None
        self._preview_item: QGraphicsItem | None = None
        self._path_item: QGraphicsPathItem | None = None
        self._painter_path: QPainterPath | None = None
        self._curve_source_item: QGraphicsItem | None = None
        self._curve_points_scene: list[QPointF] = []
        self._curve_segment_index: int = -1
        self._ruler_commit_on_release: bool = False
        self.setBackgroundBrush(QBrush(QColor("#ffffff")))

        # Estado do Free Transform (Ctrl+T)
        self._ft_active: bool = False
        self._ft_items: list = []
        self._ft_is_rotating: bool = False
        self._ft_rotate_pivot: QPointF | None = None
        self._ft_rotate_start: float = 0.0
        self._ft_start_rotations: list = []

        # Snap to endpoints
        self._snap_point: QPointF | None = None

        self.selectionChanged.connect(self._on_selection_changed)

    # Grade de fundo (somente visual, não serializada)
    GRID_MINOR = 20
    GRID_MAJOR = 100
    # Tamanho dos handles do bounding box do Free Transform
    FT_HANDLE_SIZE = 5     # metade do lado do quadradinho (px viewport)
    FT_CORNER_ZONE = 22    # distância máxima do canto para ativar rotação (px viewport)
    # Snap to endpoints
    SNAP_RADIUS    = 30    # raio de detecção em px de tela (constante com zoom)
    RULER_PX_PER_MM = 3.78

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        pen_minor = QPen(QColor("#E0E8F4"), 0.7)
        pen_minor.setCosmetic(True)
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

    # Free Transform
    def _view(self):
        views = self.views()
        return views[0] if views else None

    def _ft_bounding_rect_vp(self) -> QRectF:
        """Bounding rect combinado de _ft_items em coordenadas de viewport."""
        view = self._view()
        if not view or not self._ft_items:
            return QRectF()
        combined = QRectF()
        for item in self._ft_items:
            sr = item.mapToScene(item.boundingRect()).boundingRect()
            combined = sr if combined.isNull() else combined.united(sr)
        tl = view.mapFromScene(combined.topLeft())
        br = view.mapFromScene(combined.bottomRight())
        return QRectF(tl, br).normalized()

    def _in_rotation_zone_vp(self, vp_pos: QPointF) -> bool:
        """True se vp_pos está na zona de rotação (perto de um canto, fora do rect)."""
        vp_rect = self._ft_bounding_rect_vp()
        if vp_rect.isNull():
            return False
        inner = vp_rect.adjusted(
            -self.FT_HANDLE_SIZE, -self.FT_HANDLE_SIZE,
             self.FT_HANDLE_SIZE,  self.FT_HANDLE_SIZE
        )
        corners = [vp_rect.topLeft(), vp_rect.topRight(),
                   vp_rect.bottomLeft(), vp_rect.bottomRight()]
        for c in corners:
            dist = math.hypot(vp_pos.x() - c.x(), vp_pos.y() - c.y())
            if dist <= self.FT_CORNER_ZONE and not inner.contains(vp_pos):
                return True
        return False

    def _enter_ft(self):
        """Ativa o Free Transform (Ctrl+T) para os itens selecionados."""
        if self._ft_active:
            self._exit_ft()
            return
        items = self.selectedItems()
        if not items:
            return
        if self.cw.tool != Tool.SELECT:
            self.cw._set_tool(Tool.SELECT)
        self._ft_items = list(items)
        # Pivot de rotação = centro do bounding rect de cada item
        for item in self._ft_items:
            item.setTransformOriginPoint(item.boundingRect().center())
        self._ft_active = True
        self._ft_is_rotating = False
        self.update()

    def _exit_ft(self):
        """Sai do Free Transform."""
        self._ft_active = False
        self._ft_items = []
        self._ft_is_rotating = False
        self._ft_rotate_pivot = None
        self.update()
        self.cw.changed.emit()

    # Snap to endpoints
    def _collect_snap_points(self) -> list:
        """Retorna todos os endpoints de itens existentes em coordenadas de cena."""
        points = []
        for item in self.items():
            if isinstance(item, QGraphicsLineItem):
                ln = item.line()
                points.append(item.mapToScene(ln.p1()))
                points.append(item.mapToScene(ln.p2()))
            elif isinstance(item, QGraphicsRectItem):
                r = item.rect()
                for c in [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()]:
                    points.append(item.mapToScene(c))
            elif isinstance(item, QGraphicsPathItem):
                path = item.path()
                if path.elementCount() > 0:
                    e0 = path.elementAt(0)
                    en = path.elementAt(path.elementCount() - 1)
                    points.append(item.mapToScene(QPointF(e0.x, e0.y)))
                    points.append(item.mapToScene(QPointF(en.x, en.y)))
        return points

    def _find_snap(self, scene_pos: QPointF) -> QPointF | None:
        """
        Retorna o endpoint mais próximo de scene_pos se estiver dentro de
        SNAP_RADIUS pixels de tela. Usa distância de viewport para que o
        raio seja constante independente do zoom.
        """
        view = self._view()
        if not view:
            return None
        vp_pos = QPointF(view.mapFromScene(scene_pos))
        best_pt = None
        best_dist = self.SNAP_RADIUS
        for pt in self._collect_snap_points():
            vp_pt = QPointF(view.mapFromScene(pt))
            d = math.hypot(vp_pos.x() - vp_pt.x(), vp_pos.y() - vp_pt.y())
            if d < best_dist:
                best_dist = d
                best_pt = pt
        return best_pt

    def _on_selection_changed(self):
        """Sincroniza spin_font; remove edição inline de textos deselecionados."""
        selected = set(self.selectedItems())
        for item in self.items():
            if isinstance(item, QGraphicsTextItem) and item not in selected:
                normalized_text = normalize_upper_text(item.toPlainText())
                if normalized_text != item.toPlainText():
                    item.setPlainText(normalized_text)
                item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        for item in selected:
            if isinstance(item, QGraphicsTextItem):
                size = item.font().pointSize()
                if size > 0:
                    self.cw.spin_font.blockSignals(True)
                    self.cw.spin_font.setValue(size)
                    self.cw.spin_font.blockSignals(False)
                return

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Desenha o bounding box do Free Transform quando ativo."""
        super().drawForeground(painter, rect)
        if not self._ft_active or not self._ft_items:
            return
        view = self._view()
        if view is None:
            return

        painter.save()
        painter.resetTransform()   # coords de viewport (px fixos)

        vp_rect = self._ft_bounding_rect_vp()
        if vp_rect.isNull():
            painter.restore()
            return

        vr = vp_rect.adjusted(-2, -2, 2, 2)

        # Bounding box
        painter.setPen(QPen(QColor("#1A73E8"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(vr)

        # Handles nos 4 cantos (quadradinhos brancos com borda azul)
        hs = self.FT_HANDLE_SIZE
        painter.setPen(QPen(QColor("#1A73E8"), 1.5))
        painter.setBrush(QBrush(QColor("#ffffff")))
        for c in [vr.topLeft(), vr.topRight(), vr.bottomLeft(), vr.bottomRight()]:
            painter.drawRect(QRectF(c.x() - hs, c.y() - hs, hs * 2, hs * 2))

        # Cruz central
        cx, cy = vr.center().x(), vr.center().y()
        painter.setPen(QPen(QColor("#1A73E8"), 1))
        painter.drawLine(QPointF(cx - 8, cy), QPointF(cx + 8, cy))
        painter.drawLine(QPointF(cx, cy - 8), QPointF(cx, cy + 8))

        painter.restore()

        # Indicador de snap (círculo laranja no ponto de conexão)
        if self._snap_point is not None:
            view = self._view()
            if view:
                painter.save()
                painter.resetTransform()
                vp = view.mapFromScene(self._snap_point)
                r = 8
                painter.setPen(QPen(QColor("#FF6B35"), 2))
                painter.setBrush(QBrush(QColor(255, 107, 53, 50)))
                painter.drawEllipse(QPointF(vp), r, r)
                painter.setPen(QPen(QColor("#FF6B35"), 1.5))
                painter.drawLine(QPointF(vp.x() - r, vp.y()), QPointF(vp.x() + r, vp.y()))
                painter.drawLine(QPointF(vp.x(), vp.y() - r), QPointF(vp.x(), vp.y() + r))
                painter.restore()

    def _pen(self) -> QPen:
        p = QPen(QColor(self.cw.color), self.cw.pen_width)
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setStyle(self.cw.pen_style)
        return p

    def _erase_at(self, pos: QPointF):
        for item in self.items(pos):
            if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem,
                                  QGraphicsEllipseItem, QGraphicsPathItem,
                                  QGraphicsTextItem, QGraphicsPixmapItem)):
                self.removeItem(item)
                if item in self.cw._undo_stack:
                    self.cw._undo_stack.remove(item)
                self.cw.changed.emit()

    def _constrain(self, start: QPointF, end: QPointF) -> QPointF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        angle = math.degrees(math.atan2(dy, dx))
        dist  = math.hypot(dx, dy)
        snap  = round(angle / 45) * 45
        rad   = math.radians(snap)
        return QPointF(start.x() + dist * math.cos(rad),
                       start.y() + dist * math.sin(rad))

    def _pick_curve_source_item(self, scene_pos: QPointF) -> QGraphicsItem | None:
        """Escolhe forma selecionada para curvar; fallback para item sob o cursor."""
        for item in self.selectedItems():
            if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem)):
                return item
        for item in self.items(scene_pos):
            if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem)):
                item.setSelected(True)
                return item
        return None

    def _item_curve_points_scene(self, item: QGraphicsItem) -> tuple[list[QPointF], bool]:
        """Extrai os pontos em coordenadas de cena para curvar um segmento."""
        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            return [item.mapToScene(ln.p1()), item.mapToScene(ln.p2())], False

        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            pts = [
                item.mapToScene(r.topLeft()),
                item.mapToScene(r.topRight()),
                item.mapToScene(r.bottomRight()),
                item.mapToScene(r.bottomLeft()),
                item.mapToScene(r.topLeft()),
            ]
            return pts, True

        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            pts: list[QPointF] = []
            samples = 40
            for i in range(samples):
                ang = (2.0 * math.pi * i) / samples
                x = r.center().x() + (r.width() / 2.0) * math.cos(ang)
                y = r.center().y() + (r.height() / 2.0) * math.sin(ang)
                pts.append(item.mapToScene(QPointF(x, y)))
            pts.append(pts[0])
            return pts, True

        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            pts: list[QPointF] = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                pts.append(item.mapToScene(QPointF(el.x, el.y)))
            if len(pts) < 2:
                return [], False
            closed = math.hypot(pts[0].x() - pts[-1].x(), pts[0].y() - pts[-1].y()) < 0.01
            return pts, closed

        return [], False

    def _points_to_path_scene(self, points: list[QPointF]) -> QPainterPath:
        path = QPainterPath(points[0])
        for p in points[1:]:
            path.lineTo(p)
        return path

    def _distance_point_segment(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        if denom <= 1e-9:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / denom
        t = max(0.0, min(1.0, t))
        qx, qy = ax + t * dx, ay + t * dy
        return math.hypot(px - qx, py - qy)

    def _closest_curve_segment_index(self, points: list[QPointF], scene_pos: QPointF) -> int:
        if len(points) < 2:
            return -1
        best_i = -1
        best_d = float("inf")
        for i in range(len(points) - 1):
            d = self._distance_point_segment(scene_pos, points[i], points[i + 1])
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    def _apply_curve_on_segment(self, points: list[QPointF], segment_index: int, control: QPointF, steps: int = 18) -> list[QPointF]:
        """Substitui um segmento por uma curva quadrática."""
        if segment_index < 0 or segment_index >= len(points) - 1:
            return points
        p0 = points[segment_index]
        p1 = points[segment_index + 1]
        curved: list[QPointF] = []
        for i in range(steps + 1):
            t = i / steps
            u = 1.0 - t
            x = (u * u * p0.x()) + (2 * u * t * control.x()) + (t * t * p1.x())
            y = (u * u * p0.y()) + (2 * u * t * control.y()) + (t * t * p1.y())
            curved.append(QPointF(x, y))
        return points[:segment_index] + curved + points[segment_index + 2:]

    def _triangle_path(self, start: QPointF, end: QPointF) -> QPainterPath:
        """Triangulo isosceles dentro do retangulo definido por start/end."""
        r = QRectF(start, end).normalized()
        top = QPointF(r.center().x(), r.top())
        left = QPointF(r.left(), r.bottom())
        right = QPointF(r.right(), r.bottom())
        path = QPainterPath(top)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        return path

    def _regular_polygon_path(self, start: QPointF, end: QPointF, sides: int) -> QPainterPath:
        """Poligono regular inscrito no retangulo definido por start/end."""
        if sides < 3:
            return QPainterPath()
        r = QRectF(start, end).normalized()
        cx, cy = r.center().x(), r.center().y()
        rx = max(1.0, r.width() / 2.0)
        ry = max(1.0, r.height() / 2.0)

        pts = []
        for i in range(sides):
            ang = -math.pi / 2.0 + (2.0 * math.pi * i / sides)
            pts.append(QPointF(cx + rx * math.cos(ang), cy + ry * math.sin(ang)))

        path = QPainterPath(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        path.closeSubpath()
        return path

    def _arrow_path(self, start: QPointF, end: QPointF) -> QPainterPath:
        """Seta predefinida: haste + duas abas na ponta final."""
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return QPainterPath(start)

        ux, uy = dx / dist, dy / dist
        head_len = max(10.0, float(self.cw.pen_width) * 4.0)
        head_ang = math.radians(28.0)
        cos_a = math.cos(head_ang)
        sin_a = math.sin(head_ang)

        lx = (ux * cos_a) - (uy * sin_a)
        ly = (ux * sin_a) + (uy * cos_a)
        rx = (ux * cos_a) + (uy * sin_a)
        ry = (-ux * sin_a) + (uy * cos_a)

        left = QPointF(end.x() - (lx * head_len), end.y() - (ly * head_len))
        right = QPointF(end.x() - (rx * head_len), end.y() - (ry * head_len))

        path = QPainterPath(start)
        path.lineTo(end)
        path.moveTo(end)
        path.lineTo(left)
        path.moveTo(end)
        path.lineTo(right)
        return path

    def _ruler_pen(self, cosmetic: bool = True) -> QPen:
        pen = QPen(QColor(theme.PRIMARY), float(max(1, self.cw.pen_width)))
        pen.setCosmetic(cosmetic)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def _ruler_label_pos(self, start: QPointF, end: QPointF) -> QPointF:
        mid_x = (start.x() + end.x()) / 2.0
        mid_y = (start.y() + end.y()) / 2.0
        # Quanto maior a espessura, mais sobe a label para não ficar tampada.
        y_offset = 22.0 + (float(max(1, self.cw.pen_width)) * 0.9)
        return QPointF(mid_x + 8.0, mid_y - y_offset)

    def _format_ruler_text(self, start: QPointF, end: QPointF) -> tuple[str, float]:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        dist = math.hypot(dx, dy)
        dx_mm = dx / self.RULER_PX_PER_MM
        dy_mm = dy / self.RULER_PX_PER_MM
        dist_mm = dist / self.RULER_PX_PER_MM
        dx_cm = dx_mm / 10.0
        dy_cm = dy_mm / 10.0
        dist_cm = dist_mm / 10.0
        dx_m = dx_mm / 1000.0
        dy_m = dy_mm / 1000.0
        dist_m = dist_mm / 1000.0
        text = (
            f"Dist: {dist_mm:.1f} mm ({dist_cm:.2f} cm | {dist_m:.3f} m)   "
            f"dX: {dx_mm:.1f} mm ({dx_cm:.2f} cm | {dx_m:.3f} m)   "
            f"dY: {dy_mm:.1f} mm ({dy_cm:.2f} cm | {dy_m:.3f} m)"
        )
        return text, dist_mm

    @staticmethod
    def _format_fixed_measure(dist_mm: float) -> str:
        abs_dist = abs(dist_mm)
        if abs_dist >= 1000.0:
            return f"{(dist_mm / 1000.0):.3f} m"
        if abs_dist >= 10.0:
            return f"{(dist_mm / 10.0):.2f} cm"
        return f"{dist_mm:.1f} mm"

    def _commit_ruler_measure(self, start: QPointF, end: QPointF):
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 1e-6:
            return
        text, dist_mm = self._format_ruler_text(start, end)
        _ = text  # mantém o cálculo completo centralizado para régua dinâmica.

        line_item = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
        line_item.setPen(self._ruler_pen(cosmetic=True))
        line_item.setZValue(9000)
        line_item.setData(0, {"type": "ruler_measure_line"})
        line_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(line_item)

        label = self._format_fixed_measure(dist_mm)
        text_item = QGraphicsTextItem(label)
        text_item.setDefaultTextColor(QColor(theme.PRIMARY_HOVER))
        text_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
        text_item.setZValue(9001)
        text_item.setData(0, {"type": "ruler_measure_text"})
        text_item.setPos(self._ruler_label_pos(start, end))
        text_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(text_item)

        self.cw._push_undo(line_item)
        self.cw._push_undo(text_item)
        self.cw.changed.emit()

    def commit_ruler_overlay(self):
        if self._ruler_line_item is None:
            return
        line = self._ruler_line_item.line()
        start = QPointF(line.x1(), line.y1())
        end = QPointF(line.x2(), line.y2())
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 1e-6:
            return
        self._commit_ruler_measure(start, end)

    def _sync_ruler_visuals(self):
        if self._ruler_line_item is not None:
            self._ruler_line_item.setPen(self._ruler_pen(cosmetic=True))
        for item in self.items():
            meta = item.data(0) or {}
            if isinstance(meta, dict) and meta.get("type") == "ruler_measure_line" and isinstance(item, QGraphicsLineItem):
                item.setPen(self._ruler_pen(cosmetic=True))

    def _ensure_ruler_items(self):
        if self._ruler_line_item is None:
            self._ruler_line_item = self.addLine(0, 0, 0, 0, self._ruler_pen(cosmetic=True))
            self._ruler_line_item.setZValue(10000)
            self._ruler_line_item.setData(0, {"type": "ruler_overlay"})
        else:
            self._ruler_line_item.setPen(self._ruler_pen(cosmetic=True))

        if self._ruler_text_item is None:
            self._ruler_text_item = QGraphicsTextItem("")
            self._ruler_text_item.setDefaultTextColor(QColor(theme.PRIMARY_HOVER))
            self._ruler_text_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
            self._ruler_text_item.setZValue(10001)
            self._ruler_text_item.setData(0, {"type": "ruler_overlay"})
            self.addItem(self._ruler_text_item)

    def _update_ruler(self, start: QPointF, end: QPointF):
        self._ensure_ruler_items()
        if self._ruler_line_item is None or self._ruler_text_item is None:
            return

        self._ruler_line_item.setLine(start.x(), start.y(), end.x(), end.y())
        text, _dist_mm = self._format_ruler_text(start, end)
        self._ruler_text_item.setPlainText(text)
        self._ruler_text_item.setPos(self._ruler_label_pos(start, end))

    def mousePressEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()
        self.cw._last_click_scene_pos = QPointF(pos.x(), pos.y())

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # Free Transform ativo: verificar zona de rotação nos cantos
        if self._ft_active and event.button() == Qt.MouseButton.LeftButton:
            view = self._view()
            if view:
                vp_pos = QPointF(view.mapFromScene(pos))
                if self._in_rotation_zone_vp(vp_pos):
                    # Calcular pivot (centro do bounding box em scene coords)
                    vp_rect = self._ft_bounding_rect_vp()
                    pivot_vp = vp_rect.center()
                    self._ft_rotate_pivot = view.mapToScene(pivot_vp.toPoint())
                    self._ft_rotate_start = math.atan2(
                        pos.y() - self._ft_rotate_pivot.y(),
                        pos.x() - self._ft_rotate_pivot.x(),
                    )
                    self._ft_start_rotations = [item.rotation() for item in self._ft_items]
                    self._ft_is_rotating = True
                    event.accept()
                    return
                # Clique fora da área do bounding box -> sair do FT
                outer = self._ft_bounding_rect_vp().adjusted(-20, -20, 20, 20)
                if not outer.contains(vp_pos):
                    self._exit_ft()
                    # Não retorna: deixa a seleção normal acontecer

        if tool == Tool.SELECT:
            super().mousePressEvent(event)
            return

        if tool == Tool.ERASER:
            self._erase_at(pos)
            return

        if tool == Tool.TEXT:
            text, ok = QInputDialog.getText(self.cw, "Texto", "Digite o texto:")
            text = normalize_upper_text(text).strip()
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

        self._snap_point = None
        self._start = QPointF(pos.x(), pos.y())
        self._ruler_commit_on_release = (
            tool == Tool.RULER
            and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        )

        if tool == Tool.PEN:
            self._painter_path = QPainterPath(pos)
            self._path_item = QGraphicsPathItem()
            self._path_item.setPen(self._pen())
            self.addItem(self._path_item)

        elif tool == Tool.LINE:
            self._start = QPointF(pos.x(), pos.y())
            # Pequeno segmento inicial para feedback visual instantâneo no primeiro clique.
            self._preview_item = self.addLine(
                self._start.x(), self._start.y(),
                self._start.x() + 0.01, self._start.y(), self._pen()
            )

        elif tool == Tool.RULER:
            self._update_ruler(self._start, self._start)

        elif tool == Tool.ARROW:
            self._start = QPointF(pos.x(), pos.y())
            self._preview_item = QGraphicsPathItem(self._arrow_path(self._start, self._start))
            self._preview_item.setPen(self._pen())
            self.addItem(self._preview_item)

        elif tool == Tool.CURVE:
            source_item = self._pick_curve_source_item(pos)
            if not source_item:
                self._start = None
                return

            self._curve_source_item = source_item
            self._curve_points_scene, _closed = self._item_curve_points_scene(source_item)
            if len(self._curve_points_scene) < 2:
                self._curve_source_item = None
                self._start = None
                return
            self._curve_segment_index = self._closest_curve_segment_index(self._curve_points_scene, pos)
            if self._curve_segment_index < 0:
                self._curve_source_item = None
                self._curve_points_scene = []
                self._start = None
                return

            source_pen = source_item.pen()
            source_item.setVisible(False)

            curved_points = self._apply_curve_on_segment(
                self._curve_points_scene,
                self._curve_segment_index,
                pos,
            )
            path = self._points_to_path_scene(curved_points)
            curve_item = QGraphicsPathItem(path)
            curve_item.setPen(source_pen)
            self.addItem(curve_item)
            self._preview_item = curve_item

        elif tool == Tool.TRIANGLE:
            self._preview_item = QGraphicsPathItem(self._triangle_path(self._start, pos))
            self._preview_item.setPen(self._pen())
            self.addItem(self._preview_item)

        elif tool == Tool.PENTAGON:
            self._preview_item = QGraphicsPathItem(self._regular_polygon_path(self._start, pos, 5))
            self._preview_item.setPen(self._pen())
            self.addItem(self._preview_item)

        elif tool == Tool.HEXAGON:
            self._preview_item = QGraphicsPathItem(self._regular_polygon_path(self._start, pos, 6))
            self._preview_item.setPen(self._pen())
            self.addItem(self._preview_item)

        elif tool == Tool.RECT:
            self._preview_item = self.addRect(QRectF(pos, pos), self._pen())

        elif tool == Tool.ELLIPSE:
            self._preview_item = self.addEllipse(QRectF(pos, pos), self._pen())

        event.accept()

    def mouseMoveEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()

        # Free Transform: rotação fluida
        if self._ft_is_rotating and self._ft_rotate_pivot is not None:
            angle = math.atan2(
                pos.y() - self._ft_rotate_pivot.y(),
                pos.x() - self._ft_rotate_pivot.x(),
            )
            delta = math.degrees(angle - self._ft_rotate_start)
            for item, start_rot in zip(self._ft_items, self._ft_start_rotations):
                item.setRotation(start_rot + delta)
            self.update()
            event.accept()
            return

        if tool == Tool.ERASER and event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at(pos)
            return

        if self._start is None:
            # Limpa indicador se o mouse saiu sem estar desenhando
            if self._snap_point is not None:
                self._snap_point = None
                self.update()
            super().mouseMoveEvent(event)
            return

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if tool == Tool.PEN and self._painter_path and self._path_item:
            self._painter_path.lineTo(pos)
            self._path_item.setPath(self._painter_path)

        elif tool == Tool.LINE and self._preview_item:
            snap = self._find_snap(pos)
            if snap is not None:
                end = snap
                self._snap_point = snap
            else:
                end = self._constrain(self._start, pos) if shift else pos
                self._snap_point = None
            self._preview_item.setLine(self._start.x(), self._start.y(),
                                       end.x(), end.y())
            self.update()

        elif tool == Tool.RULER:
            end = self._constrain(self._start, pos) if shift else pos
            self._update_ruler(self._start, end)

        elif tool == Tool.ARROW and self._preview_item:
            end = self._constrain(self._start, pos) if shift else pos
            self._preview_item.setPath(self._arrow_path(self._start, end))

        elif tool == Tool.CURVE and self._preview_item and self._curve_points_scene:
            curved_points = self._apply_curve_on_segment(
                self._curve_points_scene,
                self._curve_segment_index,
                pos,
            )
            self._preview_item.setPath(self._points_to_path_scene(curved_points))

        elif tool == Tool.TRIANGLE and self._preview_item:
            self._preview_item.setPath(self._triangle_path(self._start, pos))

        elif tool == Tool.PENTAGON and self._preview_item:
            self._preview_item.setPath(self._regular_polygon_path(self._start, pos, 5))

        elif tool == Tool.HEXAGON and self._preview_item:
            self._preview_item.setPath(self._regular_polygon_path(self._start, pos, 6))

        elif tool == Tool.RECT and self._preview_item:
            self._preview_item.setRect(QRectF(self._start, pos).normalized())

        elif tool == Tool.ELLIPSE and self._preview_item:
            self._preview_item.setRect(QRectF(self._start, pos).normalized())

    def mouseReleaseEvent(self, event):
        # Free Transform: fim da rotação (mantém ft ativo para mais ajustes)
        if self._ft_is_rotating:
            self._ft_is_rotating = False
            self._ft_rotate_pivot = None
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

        elif tool in (Tool.LINE, Tool.RECT, Tool.ELLIPSE, Tool.ARROW) and self._preview_item:
            if tool == Tool.LINE:
                snap = self._find_snap(pos)
                if snap is not None:
                    end = snap
                elif shift:
                    end = self._constrain(self._start, pos)
                else:
                    end = pos
                self._preview_item.setLine(self._start.x(), self._start.y(),
                                           end.x(), end.y())
                self._snap_point = None
                self.update()
            elif tool == Tool.ARROW:
                end = self._constrain(self._start, pos) if shift else pos
                self._preview_item.setPath(self._arrow_path(self._start, end))
            item = self._preview_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.cw._push_undo(item)
            self._preview_item = None

        elif tool == Tool.RULER:
            end = self._constrain(self._start, pos) if shift else pos
            self._update_ruler(self._start, end)
            if self._ruler_commit_on_release:
                self._commit_ruler_measure(self._start, end)
            self._ruler_commit_on_release = False

        elif tool == Tool.CURVE and self._preview_item and self._curve_source_item:
            old_item = self._curve_source_item
            self.removeItem(old_item)
            if old_item in self.cw._undo_stack:
                self.cw._undo_stack.remove(old_item)

            item = self._preview_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            item.setSelected(True)
            self.cw._push_undo(item)

            self._preview_item = None
            self._curve_source_item = None
            self._curve_points_scene = []
            self._curve_segment_index = -1

        elif tool == Tool.TRIANGLE and self._preview_item:
            item = self._preview_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.cw._push_undo(item)
            self._preview_item = None

        elif tool in (Tool.PENTAGON, Tool.HEXAGON) and self._preview_item:
            item = self._preview_item
            item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                          QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.cw._push_undo(item)
            self._preview_item = None

        self._start = None
        self._ruler_commit_on_release = False

    def keyPressEvent(self, event):
        # Enter ou Escape confirmam/saem do Free Transform
        if self._ft_active:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                self._exit_ft()
                event.accept()
                return

        focus_item = self.focusItem()
        if (
            isinstance(focus_item, QGraphicsTextItem)
            and focus_item.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction
        ):
            super().keyPressEvent(event)
            return

        step = 10.0 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1.0
        dx = 0.0
        dy = 0.0
        if event.key() == Qt.Key.Key_Left:
            dx = -step
        elif event.key() == Qt.Key.Key_Right:
            dx = step
        elif event.key() == Qt.Key.Key_Up:
            dy = -step
        elif event.key() == Qt.Key.Key_Down:
            dy = step

        if dx or dy:
            selected = self.selectedItems()
            if selected:
                for item in selected:
                    item.setPos(item.pos() + QPointF(dx, dy))
                self.cw.changed.emit()
                event.accept()
                return

        if event.key() == Qt.Key.Key_Delete:
            for item in self.selectedItems():
                self.removeItem(item)
            self.cw.changed.emit()
            event.accept()
            return
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Duplo clique em texto -> ativa edição inline."""
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


# View com pan por botão do meio + Space + arraste
class DrawingView(QGraphicsView):
    """
    QGraphicsView com zoom por scroll e pan por botão do meio ou Space+drag.
    Também gerencia o cursor de rotação quando Free Transform está ativo.
    """

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self._panning    = False
        self._pan_start  = None
        self._space_held = False
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # AnchorViewCenter: mantém o centro ao redimensionar (AnchorUnderMouse causava
        # scroll incorreto no primeiro show, pois o mouse ainda não está no canvas)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        vp = self.viewport()
        vp.installEventFilter(self)
        vp.setMouseTracking(True)   # receber MouseMove sem botão pressionado

    # Event filter no viewport
    def eventFilter(self, obj, event):
        if obj is not self.viewport():
            return super().eventFilter(obj, event)

        t = event.type()

        # Zoom por scroll
        if t == QEvent.Type.Wheel:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            return True

        # Início do pan
        if t == QEvent.Type.MouseButtonPress:
            mid        = event.button() == Qt.MouseButton.MiddleButton
            space_left = (event.button() == Qt.MouseButton.LeftButton
                          and self._space_held)
            if mid or space_left:
                self._start_pan(event.position().toPoint())
                return True

        # Arraste do pan
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

        # Fim do pan
        if t == QEvent.Type.MouseButtonRelease and self._panning:
            if event.button() in (Qt.MouseButton.MiddleButton,
                                   Qt.MouseButton.LeftButton):
                self._stop_pan()
                return True

        # Cursor de rotação no Free Transform (hover sem botão)
        if t == QEvent.Type.MouseMove and not self._panning:
            sc = self.scene()
            if hasattr(sc, "_ft_active") and sc._ft_active:
                vp_pos = event.position()
                if sc._in_rotation_zone_vp(vp_pos):
                    self.viewport().setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif sc._ft_bounding_rect_vp().adjusted(-20, -20, 20, 20).contains(vp_pos):
                    self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

        return super().eventFilter(obj, event)

    # Space + arrastar
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

    # Helpers
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


# Widget principal
class DrawingCanvas(QWidget):
    changed = Signal()

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
        self._clipboard_signature = ""
        self._paste_serial = 0
        self._last_click_scene_pos: QPointF | None = None
        self._setup_ui()

    # UI
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("🎨 DESENHO / REFERÊNCIA")
        fs = max(9, int(11 * self.scale))
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{fs}pt; font-weight:bold;"
        )
        layout.addWidget(title)

        s  = self.scale
        fh = max(28, int(34 * s))
        fs = max(8, int(9 * s))
        lbl_style = f"color:{theme.TEXT_MEDIUM}; font-size:{fs}pt;"

        def _lbl(txt):
            l = QLabel(txt)
            l.setStyleSheet(lbl_style)
            l.setMinimumHeight(fh)
            l.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            return l

        self._tool_btns: dict[Tool, QPushButton] = {}

        tools = [
            (Tool.SELECT,   "🖱️ Selec.",   "S"),
            (Tool.PEN,      "✏️ Caneta",   "P"),
            (Tool.ERASER,   "🧹 Borracha", "X"),
            (Tool.LINE,     "📏 Linha",    "L"),
            (Tool.RULER,    "📐 Régua",    "U"),
            (Tool.ARROW,    "➡ Seta",      "A"),
            (Tool.CURVE,    "〰 Curva",    "C"),
            (Tool.TRIANGLE, "△ Triang.",  "G"),
            (Tool.PENTAGON, "⬟ Penta",    "N"),
            (Tool.HEXAGON,  "⬢ Hexa",     "H"),
            (Tool.RECT,     "⬛ Ret.",     "R"),
            (Tool.ELLIPSE,  "⭕ Elipse",   "E"),
            (Tool.TEXT,     "T Texto",     "T"),
        ]

        # Linha 1a: Ferramentas (separado das propriedades para não cortar nomes)
        row_tools = QHBoxLayout()
        row_tools.setSpacing(4)
        for t, label, key in tools:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(fh)
            btn.setToolTip(f"Atalho: {key}")
            btn.clicked.connect(lambda checked, tool=t: self._set_tool(tool))
            btn.setStyleSheet(self._tool_btn_style())
            self._tool_btns[t] = btn
            row_tools.addWidget(btn)
        row_tools.addStretch()
        layout.addLayout(row_tools)

        # Linha 1b: Propriedades do traço
        row_props = QHBoxLayout()
        row_props.setSpacing(4)

        # Cor
        self.btn_color = QPushButton("🎨")
        self.btn_color.setFixedSize(fh, fh)
        self.btn_color.setToolTip("Cor do traço")
        self.btn_color.setStyleSheet(
            f"background:{self.color}; border-radius:8px; border:2px solid {theme.BORDER_COLOR};"
            f"font-size:{fs}pt;"
        )
        self.btn_color.clicked.connect(self._pick_color)
        row_props.addWidget(self.btn_color)

        row_props.addSpacing(8)

        # Espessura
        row_props.addWidget(_lbl("Esp.:"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 26)
        self.spin_width.setValue(self.pen_width)
        self.spin_width.setFixedWidth(max(56, int(68 * s)))
        self.spin_width.setFixedHeight(fh)
        self.spin_width.valueChanged.connect(self._on_pen_width_changed)
        row_props.addWidget(self.spin_width)

        row_props.addSpacing(8)

        # Estilo de linha
        row_props.addWidget(_lbl("Linha:"))
        self.combo_style = QComboBox()
        self.combo_style.setFixedHeight(fh)
        self.combo_style.setFixedWidth(max(126, int(152 * s)))
        self.combo_style.addItem("─── Sólida",     Qt.PenStyle.SolidLine)
        self.combo_style.addItem("- - Tracejada",  Qt.PenStyle.DashLine)
        self.combo_style.addItem("··· Pontilhada", Qt.PenStyle.DotLine)
        self.combo_style.addItem("-·- Misto",      Qt.PenStyle.DashDotLine)
        self.combo_style.currentIndexChanged.connect(
            lambda i: setattr(self, "pen_style", self.combo_style.itemData(i))
        )
        row_props.addWidget(self.combo_style)

        row_props.addSpacing(8)

        # Tamanho da fonte
        row_props.addWidget(_lbl("Fonte:"))
        self.spin_font = QSpinBox()
        self.spin_font.setRange(6, 180)
        self.spin_font.setValue(self.font_size)
        self.spin_font.setSuffix(" pt")
        self.spin_font.setFixedWidth(max(76, int(92 * s)))
        self.spin_font.setFixedHeight(fh)
        self.spin_font.valueChanged.connect(self._on_font_size_changed)
        row_props.addWidget(self.spin_font)

        row_props.addStretch()
        layout.addLayout(row_props)

        # Linha 2: Ações
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

        # Rotação via toolbar (mantida para precisão numérica)
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

        # Dica de teclado
        hint = QLabel(
            "✨ U = régua  |  Ctrl+Clique = fixar medição  |  F1 = fixar medição atual  |  Shift = traço reto  |  A = seta  |  C = curva na linha/curva selecionada  |  G = triângulo  |  N = pentágono  |  H = hexágono  |  Del = apagar  |  Scroll = zoom  |  "
            "Botão do meio / Space+drag = mover  |  "
            "Ctrl+C / Ctrl+V = duplicar e colar  |  "
            "Ctrl+T = Free Transform (arrastar fora dos cantos = girar)  |  "
            "Enter / Esc = confirmar  |  2x clique = editar texto"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8*s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

        # Cena + View
        self.scene = DrawingScene(self)
        # sceneRect fixo: impede que o viewport role quando o primeiro item é
        # adicionado (sem rect fixo, Qt recalcula os limites e causa um scroll
        # que faz o ponto inicial aparecer deslocado em relação ao clique)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.view  = DrawingView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:8px; background:#fff;"
        )
        self.view.setMinimumHeight(max(250, int(300 * self.scale)))
        # Garante que a origem (0,0) da cena começa centralizada no viewport
        self.view.centerOn(QPointF(0, 0))
        layout.addWidget(self.view)

        # Painel de PDF
        self.pdf_panel = QFrame()
        self.pdf_panel.setStyleSheet(
            f"background:{theme.SELECTION_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
        )
        pdf_layout = QHBoxLayout(self.pdf_panel)
        pdf_layout.setContentsMargins(10, 6, 10, 6)
        self.pdf_label = QLabel("Nenhum PDF anexado")
        self.pdf_label.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8,int(10*self.scale))}pt;")
        btn_open_pdf = QPushButton("📂 Abrir")
        btn_open_pdf.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_open_pdf.clicked.connect(self._open_pdf)
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

        self._set_tool(Tool.SELECT)
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
            Qt.Key.Key_U: Tool.RULER,
            Qt.Key.Key_A: Tool.ARROW,
            Qt.Key.Key_C: Tool.CURVE,
            Qt.Key.Key_G: Tool.TRIANGLE,
            Qt.Key.Key_N: Tool.PENTAGON,
            Qt.Key.Key_H: Tool.HEXAGON,
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

        copy_action = QAction(self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_action.triggered.connect(self._copy_selection_to_clipboard)
        self.addAction(copy_action)

        paste_action = QAction(self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        paste_action.triggered.connect(self._paste_from_clipboard)
        self.addAction(paste_action)

        # Ctrl+T -> Free Transform (estilo Photoshop)
        ft_action = QAction(self)
        ft_action.setShortcut(QKeySequence("Ctrl+T"))
        ft_action.triggered.connect(self.scene._enter_ft)
        self.addAction(ft_action)

        fix_measure_action = QAction(self)
        fix_measure_action.setShortcut(QKeySequence(Qt.Key.Key_F1))
        fix_measure_action.triggered.connect(self.scene.commit_ruler_overlay)
        self.addAction(fix_measure_action)

    # Ferramentas
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
        """Rotaciona os itens selecionados pelo ângulo do spin (precisão numérica)."""
        angle = self.spin_rotate.value()
        for item in self.scene.selectedItems():
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setRotation(item.rotation() + angle)
        self.changed.emit()

    def _on_font_size_changed(self, v: int):
        self.font_size = v
        if not hasattr(self, "scene"):
            return
        for item in self.scene.selectedItems():
            if isinstance(item, QGraphicsTextItem):
                f = item.font()
                f.setPointSize(v)
                item.setFont(f)
        self.changed.emit()

    def _on_pen_width_changed(self, v: int):
        self.pen_width = v
        if hasattr(self, "scene"):
            self.scene._sync_ruler_visuals()
        self.changed.emit()

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self.color),
            self,
            "Escolha a cor",
            options=QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            self.color = color.name()
            self.btn_color.setStyleSheet(
                f"background:{self.color}; border-radius:8px; border:1px solid {theme.BORDER_COLOR};"
            )

    # Undo / Redo
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

    # Imagem
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
        self._insert_image_from_pixmap(pixmap, pos=pos, path=path)

    # PDF
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

    # Limpar
    def _clear(self):
        self.scene.clear()
        # Restaura o sceneRect fixo (scene.clear() o remove)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.scene._ruler_line_item = None
        self.scene._ruler_text_item = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.changed.emit()

    def _copy_selection_to_clipboard(self):
        if self._text_editor_active():
            return

        items = []
        for item in self.scene.selectedItems():
            item_data = self._item_to_dict(item)
            if item_data:
                items.append(item_data)
        if not items:
            return

        payload = json.dumps({"version": 1, "items": items}, ensure_ascii=False)
        mime = QMimeData()
        mime.setData(_CANVAS_CLIPBOARD_MIME, QByteArray(payload.encode("utf-8")))
        mime.setText(payload)
        QGuiApplication.clipboard().setMimeData(mime)
        self._clipboard_signature = payload
        self._paste_serial = 0

    def _paste_from_clipboard(self):
        if self._text_editor_active():
            return

        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is None:
            return

        payload_text = ""
        if mime.hasFormat(_CANVAS_CLIPBOARD_MIME):
            payload_text = bytes(mime.data(_CANVAS_CLIPBOARD_MIME)).decode("utf-8", errors="ignore")
        elif mime.hasText():
            payload_text = mime.text()

        if payload_text:
            try:
                payload = json.loads(payload_text)
            except (json.JSONDecodeError, TypeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                self._paste_canvas_items(payload.get("items", []), payload_text)
                return

        pixmap = clipboard.pixmap()
        if pixmap.isNull():
            image = clipboard.image()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)

        if not pixmap.isNull():
            image_data = _pixmap_to_base64(pixmap)
            insert_pos = self._default_insert_pos(pixmap)
            self.scene.clearSelection()
            item = self._insert_image_from_pixmap(
                pixmap,
                pos=insert_pos,
                image_data=image_data,
            )
            if item:
                item.setSelected(True)
                self.changed.emit()

    def _paste_canvas_items(self, items_data: list[dict], signature: str):
        if not items_data:
            return

        if signature == self._clipboard_signature:
            serial = self._paste_serial
            self._paste_serial += 1
        else:
            self._clipboard_signature = signature
            self._paste_serial = 1
            serial = 0
        offset = QPointF(20 * serial, 20 * serial)

        self.scene.clearSelection()
        created = []
        for item_data in items_data:
            item = self._item_from_dict(item_data)
            if not item:
                continue
            created.append(item)

        if not created:
            return

        bounds = QRectF()
        for item in created:
            sr = item.mapToScene(item.boundingRect()).boundingRect()
            bounds = sr if bounds.isNull() else bounds.united(sr)

        target = self._last_click_scene_pos or self.view.mapToScene(self.view.viewport().rect().center())
        move = QPointF(
            target.x() - bounds.center().x() + offset.x(),
            target.y() - bounds.center().y() + offset.y(),
        )

        pasted = []
        for item in created:
            item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            item.moveBy(move.x(), move.y())
            self.scene.addItem(item)
            item.setSelected(True)
            self._undo_stack.append(item)
            pasted.append(item)

        if pasted:
            self._redo_stack.clear()
            self.changed.emit()

    def _insert_image_from_pixmap(
        self,
        pixmap: QPixmap,
        pos: QPointF | None = None,
        path: str = "",
        image_data: str = "",
    ) -> QGraphicsPixmapItem | None:
        if pixmap.isNull():
            return None

        display_pixmap = pixmap
        max_w = min(600, self.view.width() - 40)
        if max_w > 0 and display_pixmap.width() > max_w:
            display_pixmap = display_pixmap.scaledToWidth(
                max_w,
                Qt.TransformationMode.SmoothTransformation,
            )

        item = QGraphicsPixmapItem(display_pixmap)
        item.setPos(pos or self._default_insert_pos(display_pixmap))
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        item.setData(0, {
            "type": "image",
            "path": path,
            "image_data": image_data,
            "display_w": display_pixmap.width(),
            "display_h": display_pixmap.height(),
        })
        self.scene.addItem(item)
        self._push_undo(item)
        return item

    def _default_insert_pos(self, pixmap: QPixmap | None = None) -> QPointF:
        center = self.view.mapToScene(self.view.viewport().rect().center())
        if pixmap is not None and not pixmap.isNull():
            return QPointF(
                center.x() - (pixmap.width() / 2),
                center.y() - (pixmap.height() / 2),
            )
        return QPointF(center.x() - 20, center.y() - 20)

    def _text_editor_active(self) -> bool:
        item = self.scene.focusItem()
        return (
            isinstance(item, QGraphicsTextItem)
            and item.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction
        )

    # Serialização
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
        meta = item.data(0) or {}
        if isinstance(meta, dict) and meta.get("type") == "ruler_overlay":
            return None

        pen_data = lambda p: {
            "color": p.color().name(),
            "width": p.width(),
            "style": _STYLE_TO_STR.get(p.style(), "solid"),
        }

        rot = item.rotation()

        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            if isinstance(meta, dict) and meta.get("type") == "ruler_measure_line":
                return {"type": "ruler_measure_line",
                        "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                        "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                        "pen": pen_data(item.pen()), "rotation": rot}
            return {"type": "line",
                    "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            return {"type": "rect",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            return {"type": "ellipse",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append([el.x, el.y])
            return {"type": "path", "points": points,
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot}

        if isinstance(item, QGraphicsTextItem):
            if isinstance(meta, dict) and meta.get("type") == "ruler_measure_text":
                return {"type": "ruler_measure_text",
                        "x": item.pos().x(), "y": item.pos().y(),
                        "text": item.toPlainText(),
                        "color": item.defaultTextColor().name(),
                        "font_size": item.font().pointSize(),
                        "rotation": rot}
            return {"type": "text",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "text": normalize_upper_text(item.toPlainText()),
                    "color": item.defaultTextColor().name(),
                    "font_size": item.font().pointSize(),
                    "rotation": rot}

        if isinstance(item, QGraphicsPixmapItem):
            meta = item.data(0) or {}
            return {"type": "image",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "path": meta.get("path", ""),
                    "image_data": meta.get("image_data", ""),
                    "display_w": meta.get("display_w", item.pixmap().width()),
                    "display_h": meta.get("display_h", item.pixmap().height()),
                    "rotation": rot}

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
            placeholder = self._scene.addText("🖼️ Nenhum desenho salvo")
            placeholder.setDefaultTextColor(QColor(theme.TEXT_LIGHT))
            font = QFont(theme.FONT_PRIMARY, max(9, int(10 * self.scale_factor)))
            placeholder.setFont(font)
            placeholder.setPos(20, 20)
        self._fit_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_scene()

    def _fit_scene(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 100, 80)
        self.fitInView(rect.adjusted(-10, -10, 10, 10), Qt.AspectRatioMode.KeepAspectRatio)
