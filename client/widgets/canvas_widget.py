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
from uuid import uuid4

from PySide6.QtCore import (
    Qt, QPointF, QRectF, Signal, QEvent,
    QByteArray, QBuffer, QIODevice, QMimeData, QUrl,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen, QBrush,
    QPixmap, QKeySequence, QAction, QCursor, QTransform, QGuiApplication,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QGraphicsScene,
    QGraphicsView, QGraphicsLineItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsItem, QInputDialog, QFileDialog,
    QPushButton, QLabel, QColorDialog, QSpinBox, QDoubleSpinBox,
    QSizePolicy, QFrame, QComboBox, QApplication,
)
from ..core import theme
from ..core.text_case import normalize_upper_text


class Tool(Enum):
    SELECT   = "select"
    PEN      = "pen"
    ERASER   = "eraser"
    LINE     = "line"
    ANGLE    = "angle"
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
_IMAGE_FILE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


# Limita a maior dimensão de imagens inseridas/coladas no canvas antes de
# serializar para base64. Evita que prints/fotos inflem o JSON do desenho
# (que é persistido no banco). 1600px fica acima da resolução que o PDF
# consome (o desenho inteiro é rasterizado a ≤2400px), então não há perda
# perceptível no documento final.
_MAX_EMBEDDED_IMAGE_SIDE = 1600


def _pixmap_to_base64(pixmap: QPixmap) -> str:
    if pixmap.isNull():
        return ""
    if max(pixmap.width(), pixmap.height()) > _MAX_EMBEDDED_IMAGE_SIDE:
        pixmap = pixmap.scaled(
            _MAX_EMBEDDED_IMAGE_SIDE,
            _MAX_EMBEDDED_IMAGE_SIDE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data().toBase64()).decode("ascii")
    buffer.close()
    return data


def _serialize_transform(t: QTransform) -> dict | None:
    if t.isIdentity():
        return None
    return {
        "m11": t.m11(),
        "m12": t.m12(),
        "m13": t.m13(),
        "m21": t.m21(),
        "m22": t.m22(),
        "m23": t.m23(),
        "m31": t.m31(),
        "m32": t.m32(),
        "m33": t.m33(),
    }


def _deserialize_transform(data) -> QTransform | None:
    if not data:
        return None
    if isinstance(data, dict):
        return QTransform(
            float(data.get("m11", 1.0)),
            float(data.get("m12", 0.0)),
            float(data.get("m13", 0.0)),
            float(data.get("m21", 0.0)),
            float(data.get("m22", 1.0)),
            float(data.get("m23", 0.0)),
            float(data.get("m31", 0.0)),
            float(data.get("m32", 0.0)),
            float(data.get("m33", 1.0)),
        )
    if isinstance(data, (list, tuple)) and len(data) == 9:
        return QTransform(
            float(data[0]), float(data[1]), float(data[2]),
            float(data[3]), float(data[4]), float(data[5]),
            float(data[6]), float(data[7]), float(data[8]),
        )
    return None


def _serialize_path_segments(path: QPainterPath) -> list[dict]:
    segments: list[dict] = []
    i = 0
    count = path.elementCount()
    while i < count:
        el = path.elementAt(i)
        if el.isMoveTo():
            segments.append({"cmd": "M", "x": el.x, "y": el.y})
            i += 1
            continue
        if el.isLineTo():
            segments.append({"cmd": "L", "x": el.x, "y": el.y})
            i += 1
            continue
        if el.isCurveTo() and (i + 2) < count:
            c1 = el
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            segments.append({
                "cmd": "C",
                "c1": [c1.x, c1.y],
                "c2": [c2.x, c2.y],
                "end": [end.x, end.y],
            })
            i += 3
            continue
        i += 1
    return segments


def _deserialize_path(path_data: dict) -> QPainterPath:
    segments = path_data.get("segments", [])
    if isinstance(segments, list) and segments:
        path = QPainterPath()
        has_current = False
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            cmd = str(seg.get("cmd", "")).upper()
            if cmd == "M":
                path.moveTo(QPointF(float(seg.get("x", 0.0)), float(seg.get("y", 0.0))))
                has_current = True
            elif cmd == "L" and has_current:
                path.lineTo(QPointF(float(seg.get("x", 0.0)), float(seg.get("y", 0.0))))
            elif cmd == "C" and has_current:
                c1 = seg.get("c1", [0.0, 0.0])
                c2 = seg.get("c2", [0.0, 0.0])
                end = seg.get("end", [0.0, 0.0])
                if (
                    isinstance(c1, (list, tuple)) and len(c1) == 2
                    and isinstance(c2, (list, tuple)) and len(c2) == 2
                    and isinstance(end, (list, tuple)) and len(end) == 2
                ):
                    path.cubicTo(
                        QPointF(float(c1[0]), float(c1[1])),
                        QPointF(float(c2[0]), float(c2[1])),
                        QPointF(float(end[0]), float(end[1])),
                    )
        return path

    # Compatibilidade retroativa com payload antigo (lista de pontos em polilinha)
    points = path_data.get("points", [])
    path = QPainterPath()
    if points:
        path.moveTo(QPointF(points[0][0], points[0][1]))
        for pt in points[1:]:
            path.lineTo(QPointF(pt[0], pt[1]))
    return path


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

    elif t == "manual_dimension_line":
        item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
        item.setPen(pen)
        item.setData(0, {"type": "manual_dimension_line"})

    elif t == "angle_dimension_line":
        item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
        item.setPen(pen)
        item.setData(0, {"type": "angle_dimension_line"})

    elif t == "angle_dimension_marker":
        path = _deserialize_path(d)
        item = QGraphicsPathItem(path)
        item.setPen(pen)
        marker_meta = {"type": "angle_dimension_marker"}
        angle_link_id = str(d.get("angle_link_id", "")).strip()
        if angle_link_id:
            marker_meta["angle_link_id"] = angle_link_id
        item.setData(0, marker_meta)

    elif t == "rect":
        item = HollowRectItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)

    elif t == "ellipse":
        item = HollowEllipseItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)

    elif t == "path":
        path = _deserialize_path(d)
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

    elif t == "manual_dimension_text":
        item = QGraphicsTextItem(d.get("text", ""))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont(theme.FONT_PRIMARY, d.get("font_size", 12))
        item.setFont(font)
        item.setData(0, {"type": "manual_dimension_text"})

    elif t == "angle_dimension_text":
        item = QGraphicsTextItem(d.get("text", ""))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont(theme.FONT_PRIMARY, d.get("font_size", 12))
        item.setFont(font)
        text_meta = {"type": "angle_dimension_text"}
        angle_link_id = str(d.get("angle_link_id", "")).strip()
        if angle_link_id:
            text_meta["angle_link_id"] = angle_link_id
        item.setData(0, text_meta)

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
    if item is not None and d.get("transform"):
        t = _deserialize_transform(d.get("transform"))
        if t is not None:
            item.setTransform(t, False)
    if item is not None and rot:
        item.setRotation(rot)

    return item


def load_canvas_scene(scene: QGraphicsScene, data: str, selectable: bool = False) -> dict:
    scene.clear()
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return {"items": 0, "pdf": "", "dwg": ""}

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

    attachments = obj.get("attachments", {}) if isinstance(obj.get("attachments"), dict) else {}
    dwg_path = str(obj.get("dwg") or attachments.get("dwg") or "")
    return {"items": count, "pdf": obj.get("pdf", ""), "dwg": dwg_path}


# ---------------------------------------------------------------------------
# Subclasses para formas ocas (hit-test somente na borda, não no interior)
# ---------------------------------------------------------------------------

class HollowRectItem(QGraphicsRectItem):
    """Retângulo selecionável/clicável apenas na borda, não no interior vazio."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 1.0) + 8.0)
        outline = QPainterPath()
        outline.addRect(self.rect())
        return stroker.createStroke(outline)


class HollowEllipseItem(QGraphicsEllipseItem):
    """Elipse selecionável/clicável apenas na borda, não no interior vazio."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 1.0) + 8.0)
        outline = QPainterPath()
        outline.addEllipse(self.rect())
        return stroker.createStroke(outline)


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
        self._curve_committed_points_scene: list[QPointF] = []
        self._curve_session_active: bool = False
        self._curve_dragging: bool = False
        self._curve_bend_count: int = 0
        # Ferramenta Curva (estilo Paint): 0=idle, 1=linha base, 2=ponto controle
        self._curve_draw_phase: int = 0
        self._curve_draw_start: QPointF | None = None
        self._curve_draw_end:   QPointF | None = None
        self._curve_ctrl_1: QPointF | None = None
        self._curve_ctrl_2: QPointF | None = None
        self._ruler_commit_on_release: bool = False
        self._manual_dim_active: bool = False
        self._manual_dim_label: str = ""
        self._manual_dim_start: QPointF | None = None
        self._manual_dim_line_item: QGraphicsLineItem | None = None
        self._manual_dim_text_item: QGraphicsTextItem | None = None
        self._manual_dim_block_release: bool = False
        self._angle_text_preview_item: QGraphicsTextItem | None = None
        self._angle_marker_preview_item: QGraphicsPathItem | None = None
        self._angle_mode_active: bool = False
        self._angle_mode_start: QPointF | None = None
        self._angle_mode_label: str = "90°"
        self._angle_mode_degrees: float = 90.0
        self._angle_mode_style: str = "auto"
        self._angle_mode_block_release: bool = False
        self._mirror_axis_active: bool = False
        self._mirror_axis_start: QPointF | None = None
        self._mirror_axis_line_item: QGraphicsLineItem | None = None
        self._mirror_axis_block_release: bool = False
        self._pen_last_point: QPointF | None = None
        self._pen_shift_anchor: QPointF | None = None
        self._pen_shift_base_path: QPainterPath | None = None
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setBackgroundBrush(QBrush(QColor("#ffffff")))

        # Estado do Free Transform (Ctrl+T)
        self._ft_active: bool = False
        self._ft_items: list = []
        self._ft_is_rotating: bool = False
        self._ft_is_resizing: bool = False
        self._ft_resize_handle: str = ""
        self._ft_resize_start_rect_scene: QRectF = QRectF()
        self._ft_resize_start_transforms: list[QTransform] = []
        self._ft_rotate_pivot: QPointF | None = None
        self._ft_rotate_start: float = 0.0
        self._ft_start_rotations: list = []

        # Snap to endpoints
        self._snap_point: QPointF | None = None
        self._snap_points_cache: list[QPointF] = []
        self._syncing_angle_selection: bool = False

        self.selectionChanged.connect(self._on_selection_changed)

    # Grade de fundo (somente visual, não serializada)
    GRID_MINOR = 20
    GRID_MAJOR = 100
    # Tamanho dos handles do bounding box do Free Transform
    FT_HANDLE_SIZE = 5     # metade do lado do quadradinho (px viewport)
    FT_HANDLE_HIT = 12     # raio de clique dos handles (px viewport)
    FT_CORNER_ZONE = 22    # distância máxima do canto para ativar rotação (px viewport)
    # Snap to endpoints
    SNAP_RADIUS    = 16    # raio de detecção em px de tela (constante com zoom)
    PEN_MIN_STEP   = 0.8   # distância mínima para adicionar ponto no traço livre
    CURVE_MAX_BENDS = 2    # comportamento do Paint clássico: até 2 "dobras"
    RULER_PX_PER_MM = 3.78
    ANGLE_MARKER_SCALE_STEP = 1.1
    ANGLE_MARKER_ROTATE_STEP = 5.0
    ANGLE_MARKER_ROTATE_FAST_STEP = 15.0
    ANGLE_MARKER_MIN_SIZE = 8.0
    ANGLE_MARKER_MAX_SIZE = 4000.0

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

    def _ft_bounding_rect_scene(self) -> QRectF:
        """Bounding rect combinado de _ft_items em coordenadas de cena."""
        if not self._ft_items:
            return QRectF()
        combined = QRectF()
        for item in self._ft_items:
            sr = item.mapToScene(item.boundingRect()).boundingRect()
            combined = sr if combined.isNull() else combined.united(sr)
        return combined.normalized()

    @staticmethod
    def _ft_cursor_for_handle(handle: str) -> Qt.CursorShape:
        if handle in ("n", "s"):
            return Qt.CursorShape.SizeVerCursor
        if handle in ("e", "w"):
            return Qt.CursorShape.SizeHorCursor
        if handle in ("nw", "se"):
            return Qt.CursorShape.SizeFDiagCursor
        if handle in ("ne", "sw"):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _ft_handle_points_vp(self, vp_rect: QRectF) -> dict[str, QPointF]:
        c = vp_rect.center()
        return {
            "nw": vp_rect.topLeft(),
            "n": QPointF(c.x(), vp_rect.top()),
            "ne": vp_rect.topRight(),
            "e": QPointF(vp_rect.right(), c.y()),
            "se": vp_rect.bottomRight(),
            "s": QPointF(c.x(), vp_rect.bottom()),
            "sw": vp_rect.bottomLeft(),
            "w": QPointF(vp_rect.left(), c.y()),
        }

    def _ft_handle_at_vp(self, vp_pos: QPointF) -> str:
        vp_rect = self._ft_bounding_rect_vp()
        if vp_rect.isNull():
            return ""
        handles = self._ft_handle_points_vp(vp_rect)
        for name, pt in handles.items():
            d = math.hypot(vp_pos.x() - pt.x(), vp_pos.y() - pt.y())
            if d <= self.FT_HANDLE_HIT:
                return name
        return ""

    def _apply_ft_resize_to_selected(self, current_scene_pos: QPointF):
        r0 = self._ft_resize_start_rect_scene.normalized()
        if r0.isNull() or r0.width() <= 1e-6 or r0.height() <= 1e-6:
            return
        handle = self._ft_resize_handle
        if not handle:
            return

        min_w = max(12.0, r0.width() * 0.05)
        min_h = max(12.0, r0.height() * 0.05)

        x1, x2 = r0.left(), r0.right()
        y1, y2 = r0.top(), r0.bottom()

        px, py = current_scene_pos.x(), current_scene_pos.y()
        if "e" in handle:
            x2 = max(x1 + min_w, px)
        if "w" in handle:
            x1 = min(x2 - min_w, px)
        if "s" in handle:
            y2 = max(y1 + min_h, py)
        if "n" in handle:
            y1 = min(y2 - min_h, py)

        new_w = max(min_w, x2 - x1)
        new_h = max(min_h, y2 - y1)
        sx = new_w / max(1e-6, r0.width())
        sy = new_h / max(1e-6, r0.height())
        if handle in ("n", "s"):
            sx = 1.0
        if handle in ("e", "w"):
            sy = 1.0

        if handle == "e":
            anchor = QPointF(r0.left(), r0.center().y())
        elif handle == "w":
            anchor = QPointF(r0.right(), r0.center().y())
        elif handle == "n":
            anchor = QPointF(r0.center().x(), r0.bottom())
        elif handle == "s":
            anchor = QPointF(r0.center().x(), r0.top())
        elif handle == "nw":
            anchor = r0.bottomRight()
        elif handle == "ne":
            anchor = r0.bottomLeft()
        elif handle == "sw":
            anchor = r0.topRight()
        else:  # "se"
            anchor = r0.topLeft()

        g = QTransform()
        g.translate(anchor.x(), anchor.y())
        g.scale(sx, sy)
        g.translate(-anchor.x(), -anchor.y())

        for item, start_scene in zip(self._ft_items, self._ft_resize_start_transforms):
            composed = g * start_scene
            item.setPos(QPointF(0.0, 0.0))
            local = QTransform(
                composed.m11(), composed.m12(), composed.m13(),
                composed.m21(), composed.m22(), composed.m23(),
                composed.m31(), composed.m32(), composed.m33(),
            )
            item.setTransform(local, False)

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
        self._ft_is_resizing = False
        self._ft_resize_handle = ""
        self.update()

    def _exit_ft(self):
        """Sai do Free Transform."""
        self._ft_active = False
        self._ft_items = []
        self._ft_is_rotating = False
        self._ft_is_resizing = False
        self._ft_resize_handle = ""
        self._ft_resize_start_rect_scene = QRectF()
        self._ft_resize_start_transforms = []
        self._ft_rotate_pivot = None
        self.update()
        self.cw.changed.emit()

    # Snap to endpoints
    def _collect_snap_points(self, skip_items: set[QGraphicsItem] | None = None) -> list:
        """Retorna todos os endpoints de itens existentes em coordenadas de cena."""
        skip_items = skip_items or set()
        points = []
        for item in self.items():
            if item in skip_items:
                continue
            meta = item.data(0) or {}
            # Ignora overlays/itens transitórios para o snap não "grudar" no próprio preview.
            if isinstance(meta, dict) and meta.get("type") in {
                "ruler_overlay",
                "ruler_measure_line",
                "ruler_measure_text",
                "manual_dimension_overlay",
                "manual_dimension_line",
                "manual_dimension_text",
                "angle_dimension_overlay",
                "angle_dimension_line",
                "angle_dimension_marker",
                "angle_dimension_text",
                "mirror_axis_overlay",
            }:
                continue
            if not item.isVisible():
                continue
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

    def _find_snap(
        self,
        scene_pos: QPointF,
        *,
        candidates: list[QPointF] | None = None,
    ) -> QPointF | None:
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
        source = candidates if candidates is not None else self._collect_snap_points()
        for pt in source:
            vp_pt = QPointF(view.mapFromScene(pt))
            d = math.hypot(vp_pos.x() - vp_pt.x(), vp_pos.y() - vp_pt.y())
            if d < best_dist:
                best_dist = d
                best_pt = pt
        return best_pt

    def _on_selection_changed(self):
        """Sincroniza selecao vinculada de angulo e estado de edicao de texto."""
        if not self._syncing_angle_selection:
            self._sync_angle_pair_selection()
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
                break

        # Mostra alças de redimensionamento automaticamente ao selecionar no modo seleção.
        if self.cw.tool == Tool.SELECT:
            selected_items = self.selectedItems()
            if selected_items:
                self._ft_items = list(selected_items)
                for item in self._ft_items:
                    item.setTransformOriginPoint(item.boundingRect().center())
                self._ft_active = True
            else:
                self._ft_active = False
                self._ft_items = []
                self._ft_is_rotating = False
                self._ft_is_resizing = False
                self._ft_resize_handle = ""
            self.update()

    def _is_angle_marker(self, item: QGraphicsItem) -> bool:
        meta = item.data(0)
        return (
            isinstance(item, QGraphicsPathItem)
            and isinstance(meta, dict)
            and meta.get("type") == "angle_dimension_marker"
        )

    def _is_angle_text(self, item: QGraphicsItem) -> bool:
        meta = item.data(0)
        return (
            isinstance(item, QGraphicsTextItem)
            and isinstance(meta, dict)
            and meta.get("type") == "angle_dimension_text"
        )

    @staticmethod
    def _new_angle_link_id() -> str:
        return f"angle-{uuid4().hex}"

    def _get_angle_link_id(self, item: QGraphicsItem) -> str:
        meta = item.data(0)
        if not isinstance(meta, dict):
            return ""
        value = meta.get("angle_link_id")
        return str(value).strip() if value is not None else ""

    def _set_angle_link_id(self, item: QGraphicsItem, link_id: str):
        meta = item.data(0)
        if not isinstance(meta, dict):
            meta = {}
        meta = dict(meta)
        if "type" not in meta:
            if isinstance(item, QGraphicsPathItem):
                meta["type"] = "angle_dimension_marker"
            elif isinstance(item, QGraphicsTextItem):
                meta["type"] = "angle_dimension_text"
        meta["angle_link_id"] = str(link_id)
        item.setData(0, meta)

    def _angle_marker_scene_center(self, marker: QGraphicsPathItem) -> QPointF:
        return marker.mapToScene(marker.path().boundingRect().center())

    def _find_angle_text_by_link_id(self, link_id: str) -> QGraphicsTextItem | None:
        if not link_id:
            return None
        for item in self.items():
            if not self._is_angle_text(item):
                continue
            if self._get_angle_link_id(item) == link_id:
                return item
        return None

    def _find_closest_angle_text(self, marker: QGraphicsPathItem) -> QGraphicsTextItem | None:
        center = self._angle_marker_scene_center(marker)
        marker_bounds = marker.mapRectToScene(marker.path().boundingRect()).boundingRect()
        max_range = max(60.0, max(marker_bounds.width(), marker_bounds.height()) * 2.5)
        best_text = None
        best_dist = float("inf")
        for item in self.items():
            if not self._is_angle_text(item):
                continue
            text_center = item.sceneBoundingRect().center()
            dist = math.hypot(text_center.x() - center.x(), text_center.y() - center.y())
            if dist < best_dist:
                best_dist = dist
                best_text = item
        if best_text is not None and best_dist <= max_range:
            return best_text
        return None

    def _find_closest_angle_marker(self, text_item: QGraphicsTextItem) -> QGraphicsPathItem | None:
        center = text_item.sceneBoundingRect().center()
        max_range = 240.0
        best_marker = None
        best_dist = float("inf")
        for item in self.items():
            if not self._is_angle_marker(item):
                continue
            marker_center = self._angle_marker_scene_center(item)
            dist = math.hypot(marker_center.x() - center.x(), marker_center.y() - center.y())
            if dist < best_dist:
                best_dist = dist
                best_marker = item
        if best_marker is not None and best_dist <= max_range:
            return best_marker
        return None

    def _ensure_angle_link_for_marker(self, marker: QGraphicsPathItem) -> str:
        link_id = self._get_angle_link_id(marker)
        if link_id:
            return link_id
        text_item = self._find_closest_angle_text(marker)
        if text_item is not None:
            link_id = self._get_angle_link_id(text_item)
        if not link_id:
            link_id = self._new_angle_link_id()
        self._set_angle_link_id(marker, link_id)
        if text_item is not None:
            self._set_angle_link_id(text_item, link_id)
        return link_id

    def _find_linked_angle_text(self, marker: QGraphicsPathItem) -> QGraphicsTextItem | None:
        link_id = self._ensure_angle_link_for_marker(marker)
        text_item = self._find_angle_text_by_link_id(link_id)
        if text_item is not None:
            return text_item
        return self._find_closest_angle_text(marker)

    def _default_angle_text_pos_for_marker(
        self,
        marker: QGraphicsPathItem,
        label: str,
        font_size: int,
    ) -> QPointF:
        scene_bounds = marker.mapRectToScene(marker.path().boundingRect()).boundingRect()
        tw = max(34, int(len(label) * font_size * 0.68 + 10)) if label else 42
        th = int(font_size * 2.0)
        gap = max(4, int(font_size * 0.45))

        candidates = [
            QPointF(scene_bounds.center().x() - (tw / 2.0), scene_bounds.top() - th - gap),      # acima
            QPointF(scene_bounds.right() + gap, scene_bounds.center().y() - (th / 2.0)),          # direita
            QPointF(scene_bounds.center().x() - (tw / 2.0), scene_bounds.bottom() + gap),          # abaixo
            QPointF(scene_bounds.left() - tw - gap, scene_bounds.center().y() - (th / 2.0)),      # esquerda
        ]

        for pos in candidates:
            if not self._has_collision_at(QRectF(pos.x(), pos.y(), tw, th)):
                return pos
        return candidates[0]

    def _pull_angle_text_closer_if_needed(
        self,
        marker: QGraphicsPathItem,
        text_item: QGraphicsTextItem | None,
    ) -> bool:
        if text_item is None:
            return False
        scene_bounds = marker.mapRectToScene(marker.path().boundingRect()).boundingRect()
        marker_center = scene_bounds.center()
        text_center = text_item.sceneBoundingRect().center()
        dist = math.hypot(text_center.x() - marker_center.x(), text_center.y() - marker_center.y())
        max_dist = max(90.0, max(scene_bounds.width(), scene_bounds.height()) * 2.2)
        if dist <= max_dist:
            return False

        label = text_item.toPlainText()
        fs = text_item.font().pointSize()
        if fs <= 0:
            fs = max(8, int(9 * self.cw.scale))
        new_pos = self._default_angle_text_pos_for_marker(marker, label, fs)
        text_item.setPos(new_pos)
        return True

    def _sync_angle_pair_selection(self):
        selected = self.selectedItems()
        angle_link_ids: set[str] = set()
        pulled_any = False

        for item in selected:
            if self._is_angle_marker(item):
                link_id = self._ensure_angle_link_for_marker(item)
                linked_text = self._find_linked_angle_text(item)
                if self._pull_angle_text_closer_if_needed(item, linked_text):
                    pulled_any = True
                if link_id:
                    angle_link_ids.add(link_id)
            elif self._is_angle_text(item):
                link_id = self._get_angle_link_id(item)
                if not link_id:
                    marker = self._find_closest_angle_marker(item)
                    if marker is not None:
                        link_id = self._ensure_angle_link_for_marker(marker)
                        self._set_angle_link_id(item, link_id)
                if link_id:
                    angle_link_ids.add(link_id)

        if not angle_link_ids:
            return

        self._syncing_angle_selection = True
        try:
            for item in self.items():
                if not (self._is_angle_marker(item) or self._is_angle_text(item)):
                    continue
                if self._get_angle_link_id(item) in angle_link_ids and not item.isSelected():
                    item.setSelected(True)
        finally:
            self._syncing_angle_selection = False
        if pulled_any:
            self.cw.changed.emit()

    def _selected_angle_markers(self) -> list[QGraphicsPathItem]:
        markers: list[QGraphicsPathItem] = []
        for item in self.selectedItems():
            if self._is_angle_marker(item):
                self._ensure_angle_link_for_marker(item)
                markers.append(item)
        return markers

    def _resize_selected_angle_markers(self, factor: float) -> bool:
        changed = False
        for marker in self._selected_angle_markers():
            path = marker.path()
            bounds = path.boundingRect()
            max_dim = max(bounds.width(), bounds.height())
            if max_dim <= 1e-6:
                continue
            resized_dim = max_dim * factor
            if resized_dim < self.ANGLE_MARKER_MIN_SIZE or resized_dim > self.ANGLE_MARKER_MAX_SIZE:
                continue
            center = self._angle_marker_scene_center(marker)
            text_item = self._find_linked_angle_text(marker)

            transform = QTransform()
            local_center = bounds.center()
            transform.translate(local_center.x(), local_center.y())
            transform.scale(factor, factor)
            transform.translate(-local_center.x(), -local_center.y())
            marker.setPath(transform.map(path))
            marker.setTransformOriginPoint(marker.path().boundingRect().center())

            if text_item is not None:
                text_pos = text_item.pos()
                vec_x = text_pos.x() - center.x()
                vec_y = text_pos.y() - center.y()
                text_item.setPos(
                    QPointF(center.x() + (vec_x * factor), center.y() + (vec_y * factor))
                )
            changed = True
        return changed

    def _rotate_selected_angle_markers(self, delta_degrees: float) -> bool:
        changed = False
        rad = math.radians(delta_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        for marker in self._selected_angle_markers():
            center = self._angle_marker_scene_center(marker)
            text_item = self._find_linked_angle_text(marker)
            marker.setTransformOriginPoint(marker.path().boundingRect().center())
            marker.setRotation(marker.rotation() + delta_degrees)

            if text_item is not None:
                text_pos = text_item.pos()
                vec_x = text_pos.x() - center.x()
                vec_y = text_pos.y() - center.y()
                rot_x = (vec_x * cos_a) - (vec_y * sin_a)
                rot_y = (vec_x * sin_a) + (vec_y * cos_a)
                text_item.setPos(QPointF(center.x() + rot_x, center.y() + rot_y))
            changed = True
        return changed

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

        # Handles (cantos + laterais)
        hs = self.FT_HANDLE_SIZE
        painter.setPen(QPen(QColor("#1A73E8"), 1.5))
        painter.setBrush(QBrush(QColor("#ffffff")))
        for c in self._ft_handle_points_vp(vr).values():
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

    def _commit_curve_draw(self, ctrl: QPointF):
        """Aplica uma dobra da curva (até CURVE_MAX_BENDS) e finaliza ao atingir o limite."""
        if not self._curve_draw_start or not self._curve_draw_end or not self._preview_item:
            self._cancel_curve_draw()
            return
        if self._curve_bend_count <= 0:
            self._curve_ctrl_1 = QPointF(ctrl.x(), ctrl.y())
            path = QPainterPath(self._curve_draw_start)
            path.quadTo(self._curve_ctrl_1, self._curve_draw_end)
            self._preview_item.setPath(path)
            self._curve_bend_count = 1
            self._curve_draw_phase = 2
            self._curve_dragging = False
            self._start = None
            return

        self._curve_ctrl_2 = QPointF(ctrl.x(), ctrl.y())
        path = QPainterPath(self._curve_draw_start)
        path.cubicTo(self._curve_ctrl_1, self._curve_ctrl_2, self._curve_draw_end)
        self._preview_item.setPath(path)
        self._curve_bend_count = 2

        if self._curve_bend_count >= self.CURVE_MAX_BENDS:
            item = self._preview_item
            item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            item.setSelected(True)
            self.cw._push_undo(item)
            self._preview_item = None
            self._curve_draw_phase = 0
            self._curve_draw_start = None
            self._curve_draw_end = None
            self._curve_ctrl_1 = None
            self._curve_ctrl_2 = None
            self._curve_bend_count = 0
            self._curve_dragging = False
            self._start = None

    def _cancel_curve_draw(self):
        """Cancela qualquer fase da ferramenta Curva em andamento."""
        if self._preview_item:
            self.removeItem(self._preview_item)
            self._preview_item = None
        self._curve_draw_phase = 0
        self._curve_draw_start = None
        self._curve_draw_end = None
        self._curve_ctrl_1 = None
        self._curve_ctrl_2 = None
        self._curve_bend_count = 0
        self._curve_dragging = False
        self._start = None

    def _reset_curve_state(self):
        self._curve_source_item = None
        self._curve_points_scene = []
        self._curve_segment_index = -1
        self._curve_committed_points_scene = []
        self._curve_session_active = False
        self._curve_dragging = False
        self._curve_bend_count = 0
        self._start = None

    def _cancel_curve_session(self):
        if self._curve_source_item:
            self._curve_source_item.setVisible(True)
        if self._curve_session_active and self._preview_item:
            self.removeItem(self._preview_item)
            self._preview_item = None
        self._reset_curve_state()

    def _finalize_curve_session(self):
        if not (self._curve_session_active and self._preview_item and self._curve_source_item):
            self._reset_curve_state()
            return

        old_item = self._curve_source_item
        self.removeItem(old_item)
        if old_item in self.cw._undo_stack:
            self.cw._undo_stack.remove(old_item)

        item = self._preview_item
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        item.setSelected(True)
        self.cw._push_undo(item)

        self._preview_item = None
        self._reset_curve_state()

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

    def _smart_label_pos(self, start: QPointF, end: QPointF, label: str = "") -> QPointF:
        """
        Posiciona o texto da cota evitando sobreposição com outros elementos.

        Linha vertical  → padrão à direita; se houver colisão, vai à esquerda.
        Linha horizontal→ padrão acima;    se houver colisão, vai abaixo.
        """
        mid_x = (start.x() + end.x()) / 2.0
        mid_y = (start.y() + end.y()) / 2.0
        dx    = abs(end.x() - start.x())
        dy    = abs(end.y() - start.y())

        # Estimativa do tamanho do texto em coordenadas de cena
        fs  = max(8, int(9 * self.cw.scale))
        tw  = max(40, int(len(label) * fs * 0.72 + 12)) if label else 60
        th  = int(fs * 2.2)
        gap = max(8, int(fs * 1.3))

        if dy > dx:
            # Linha mais vertical → padrão: texto à DIREITA
            def_x, def_y = mid_x + gap,          mid_y - th / 2
            alt_x, alt_y = mid_x - gap - tw,     mid_y - th / 2
        else:
            # Linha mais horizontal → padrão: texto ACIMA
            def_x, def_y = mid_x - tw / 2,  mid_y - gap - th
            alt_x, alt_y = mid_x - tw / 2,  mid_y + gap

        if self._has_collision_at(QRectF(def_x, def_y, tw, th)):
            return QPointF(alt_x, alt_y)
        return QPointF(def_x, def_y)

    def _angle_label_pos(
        self,
        marker_path: QPainterPath,
        start: QPointF,
        end: QPointF,
        label: str = "",
    ) -> QPointF:
        """Posiciona o texto do ângulo próximo ao marcador, evitando ficar longe da peça."""
        bounds = marker_path.boundingRect()
        if bounds.isNull():
            return self._smart_label_pos(start, end, label)

        fs = max(8, int(9 * self.cw.scale))
        tw = max(34, int(len(label) * fs * 0.68 + 10)) if label else 42
        th = int(fs * 2.0)
        gap = max(4, int(fs * 0.45))
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        if abs(dx) >= abs(dy):
            # Base horizontal: texto acima (alternativa abaixo), sempre próximo do marcador.
            def_x = bounds.center().x() - (tw / 2.0)
            def_y = bounds.top() - th - gap
            alt_x = def_x
            alt_y = bounds.bottom() + gap
        else:
            # Base vertical: texto à direita (alternativa à esquerda), próximo do marcador.
            def_x = bounds.right() + gap
            def_y = bounds.center().y() - (th / 2.0)
            alt_x = bounds.left() - tw - gap
            alt_y = def_y

        def_rect = QRectF(def_x, def_y, tw, th)
        alt_rect = QRectF(alt_x, alt_y, tw, th)
        def_collision = self._has_collision_at(def_rect)
        alt_collision = self._has_collision_at(alt_rect)

        if def_collision and not alt_collision:
            return QPointF(alt_x, alt_y)
        if not def_collision:
            return QPointF(def_x, def_y)
        if not alt_collision:
            return QPointF(alt_x, alt_y)
        return QPointF(def_x, def_y)

    def _has_collision_at(self, rect: QRectF) -> bool:
        """True se há itens de desenho reais (não cota/régua) na área indicada."""
        _ignore = {
            "ruler_overlay", "manual_dimension_overlay",
            "ruler_measure_line", "ruler_measure_text",
            "manual_dimension_line", "manual_dimension_text",
            "angle_dimension_overlay", "angle_dimension_line", "angle_dimension_marker", "angle_dimension_text",
            "mirror_axis_overlay",
        }
        for item in self.items(rect):
            meta = item.data(0)
            if isinstance(meta, dict) and meta.get("type") in _ignore:
                continue
            return True
        return False

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

    @staticmethod
    def _format_angle_label(start: QPointF, end: QPointF) -> str:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if math.hypot(dx, dy) < 1e-6:
            return "0.0°"
        angle_deg = math.degrees(math.atan2(dy, dx))
        return f"{angle_deg:.1f}°"

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
        text_item.setPos(self._smart_label_pos(start, end, label))
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
        if self._manual_dim_line_item is not None:
            self._manual_dim_line_item.setPen(self._ruler_pen(cosmetic=True))
        if self._mirror_axis_line_item is not None:
            self._mirror_axis_line_item.setPen(self._ruler_pen(cosmetic=True))
        for item in self.items():
            meta = item.data(0) or {}
            if (
                isinstance(meta, dict)
                and meta.get("type") in {"ruler_measure_line", "manual_dimension_line"}
                and isinstance(item, QGraphicsLineItem)
            ):
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
        self._ruler_text_item.setPos(self._smart_label_pos(start, end, text))

    def _ensure_manual_dimension_items(self):
        if self._manual_dim_line_item is None:
            self._manual_dim_line_item = self.addLine(0, 0, 0, 0, self._ruler_pen(cosmetic=True))
            self._manual_dim_line_item.setZValue(10000)
            self._manual_dim_line_item.setData(0, {"type": "manual_dimension_overlay"})
        else:
            self._manual_dim_line_item.setPen(self._ruler_pen(cosmetic=True))

        if self._manual_dim_text_item is None:
            self._manual_dim_text_item = QGraphicsTextItem("")
            self._manual_dim_text_item.setDefaultTextColor(QColor(theme.PRIMARY_HOVER))
            self._manual_dim_text_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
            self._manual_dim_text_item.setZValue(10001)
            self._manual_dim_text_item.setData(0, {"type": "manual_dimension_overlay"})
            self.addItem(self._manual_dim_text_item)

    def _update_manual_dimension_preview(self, start: QPointF, end: QPointF):
        self._ensure_manual_dimension_items()
        if self._manual_dim_line_item is None or self._manual_dim_text_item is None:
            return
        self._manual_dim_line_item.setLine(start.x(), start.y(), end.x(), end.y())
        self._manual_dim_text_item.setPlainText(self._manual_dim_label)
        self._manual_dim_text_item.setPos(self._smart_label_pos(start, end, self._manual_dim_label))

    def _clear_manual_dimension_overlay(self):
        if self._manual_dim_line_item is not None:
            self.removeItem(self._manual_dim_line_item)
            self._manual_dim_line_item = None
        if self._manual_dim_text_item is not None:
            self.removeItem(self._manual_dim_text_item)
            self._manual_dim_text_item = None

    def _clear_angle_preview(self):
        if self._angle_text_preview_item is not None:
            self.removeItem(self._angle_text_preview_item)
            self._angle_text_preview_item = None
        if self._angle_marker_preview_item is not None:
            self.removeItem(self._angle_marker_preview_item)
            self._angle_marker_preview_item = None

    @staticmethod
    def _normalize_angle_degrees(value: float) -> float:
        normalized = float(value) % 360.0
        if normalized < 0.0:
            normalized += 360.0
        return normalized

    def _resolve_angle_style(self, degrees: float, style: str | None = None) -> str:
        normalized = self._normalize_angle_degrees(degrees)
        selected = str(style or "auto").strip().lower()
        if selected in {"square", "arc"}:
            return selected
        if abs(normalized - 90.0) < 1e-3:
            return "square"
        return "arc"

    def _build_angle_marker_path(
        self,
        start: QPointF,
        end: QPointF,
        degrees: float,
        style: str,
    ) -> QPainterPath:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return QPainterPath()

        ux, uy = dx / dist, dy / dist
        width_boost = max(0.0, float(self.cw.pen_width) - 1.0)
        marker_len = max(
            12.0 + (width_boost * 1.8),
            min(68.0, (dist * 0.22) + (width_boost * 2.0)),
        )
        perp_x, perp_y = -uy, ux
        base = QPointF(start.x() + (ux * marker_len * 0.2), start.y() + (uy * marker_len * 0.2))
        path = QPainterPath()

        if style == "square":
            p1 = QPointF(base.x() + ux * marker_len, base.y() + uy * marker_len)
            p2 = QPointF(p1.x() + perp_x * marker_len, p1.y() + perp_y * marker_len)
            p3 = QPointF(base.x() + perp_x * marker_len, base.y() + perp_y * marker_len)
            path.moveTo(base)
            path.lineTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            return path

        # Arc (meia-lua e demais ângulos)
        normalized = self._normalize_angle_degrees(degrees)
        if normalized > 359.9:
            normalized = 359.9
        radius = max(
            14.0 + (width_boost * 1.6),
            min(78.0, (dist * 0.3) + (width_boost * 2.4)),
        )
        rect = QRectF(start.x() - radius, start.y() - radius, radius * 2.0, radius * 2.0)
        start_deg = math.degrees(math.atan2(-uy, ux))
        path.arcMoveTo(rect, start_deg)
        path.arcTo(rect, start_deg, normalized)
        return path

    def _update_angle_preview(self, start: QPointF, end: QPointF):
        label = self._angle_mode_label or self._format_angle_label(start, end)
        resolved_style = self._resolve_angle_style(self._angle_mode_degrees, self._angle_mode_style)
        marker_path = self._build_angle_marker_path(start, end, self._angle_mode_degrees, resolved_style)
        if self._angle_marker_preview_item is None:
            self._angle_marker_preview_item = QGraphicsPathItem(marker_path)
            self._angle_marker_preview_item.setPen(self._pen())
            self._angle_marker_preview_item.setZValue(10000)
            self._angle_marker_preview_item.setData(0, {"type": "angle_dimension_overlay"})
            self.addItem(self._angle_marker_preview_item)
        else:
            self._angle_marker_preview_item.setPath(marker_path)
            self._angle_marker_preview_item.setPen(self._pen())
        if self._angle_text_preview_item is None:
            self._angle_text_preview_item = QGraphicsTextItem(label)
            self._angle_text_preview_item.setDefaultTextColor(QColor(self.cw.color))
            self._angle_text_preview_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
            self._angle_text_preview_item.setZValue(10001)
            self._angle_text_preview_item.setData(0, {"type": "angle_dimension_overlay"})
            self.addItem(self._angle_text_preview_item)
        else:
            self._angle_text_preview_item.setPlainText(label)
            self._angle_text_preview_item.setDefaultTextColor(QColor(self.cw.color))
        self._angle_text_preview_item.setPos(self._angle_label_pos(marker_path, start, end, label))

    def _commit_angle_measure(self, start: QPointF, end: QPointF):
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 1e-6:
            return
        label = self._angle_mode_label or self._format_angle_label(start, end)
        resolved_style = self._resolve_angle_style(self._angle_mode_degrees, self._angle_mode_style)
        marker_path = self._build_angle_marker_path(start, end, self._angle_mode_degrees, resolved_style)
        link_id = self._new_angle_link_id()

        marker_item = QGraphicsPathItem(marker_path)
        marker_item.setPen(self._pen())
        marker_item.setZValue(9000)
        marker_item.setData(0, {"type": "angle_dimension_marker", "angle_link_id": link_id})
        marker_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(marker_item)

        text_item = QGraphicsTextItem(label)
        text_item.setDefaultTextColor(QColor(self.cw.color))
        text_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
        text_item.setZValue(9001)
        text_item.setData(0, {"type": "angle_dimension_text", "angle_link_id": link_id})
        text_item.setPos(self._angle_label_pos(marker_path, start, end, label))
        text_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(text_item)

        self.cw._push_undo(marker_item)
        self.cw._push_undo(text_item)
        self.cw.changed.emit()

    def _cancel_angle_draw(self):
        if self._preview_item is not None:
            self.removeItem(self._preview_item)
            self._preview_item = None
        self._clear_angle_preview()
        self._start = None

    def begin_angle_mode(self, degrees: float, label: str, style: str):
        self.cancel_angle_mode()
        self.cancel_manual_dimension()
        self.cancel_mirror_axis()
        if self._ft_active:
            self._exit_ft()
        self._angle_mode_active = True
        self._angle_mode_start = None
        self._angle_mode_label = str(label or "").strip() or f"{float(degrees):.1f}°"
        self._angle_mode_degrees = float(degrees)
        self._angle_mode_style = style

    def cancel_angle_mode(self):
        self._angle_mode_active = False
        self._angle_mode_start = None
        self._angle_mode_block_release = False
        self._cancel_angle_draw()

    def begin_manual_dimension(self, label: str):
        self.cancel_manual_dimension()
        if self._ft_active:
            self._exit_ft()
        self._manual_dim_active = True
        self._manual_dim_label = label
        self._manual_dim_start = None

    def cancel_manual_dimension(self):
        self._manual_dim_active = False
        self._manual_dim_label = ""
        self._manual_dim_start = None
        self._manual_dim_block_release = False
        self._clear_manual_dimension_overlay()

    def _ensure_mirror_axis_item(self):
        if self._mirror_axis_line_item is None:
            self._mirror_axis_line_item = self.addLine(0, 0, 0, 0, self._ruler_pen(cosmetic=True))
            self._mirror_axis_line_item.setZValue(10000)
            self._mirror_axis_line_item.setData(0, {"type": "mirror_axis_overlay"})
        else:
            self._mirror_axis_line_item.setPen(self._ruler_pen(cosmetic=True))

    def _update_mirror_axis_preview(self, start: QPointF, end: QPointF):
        self._ensure_mirror_axis_item()
        if self._mirror_axis_line_item is None:
            return
        self._mirror_axis_line_item.setLine(start.x(), start.y(), end.x(), end.y())

    def _clear_mirror_axis_overlay(self):
        if self._mirror_axis_line_item is not None:
            self.removeItem(self._mirror_axis_line_item)
            self._mirror_axis_line_item = None

    def begin_mirror_axis(self):
        self.cancel_mirror_axis()
        self.cancel_manual_dimension()
        if self._ft_active:
            self._exit_ft()
        self._mirror_axis_active = True
        self._mirror_axis_start = None

    def cancel_mirror_axis(self):
        self._mirror_axis_active = False
        self._mirror_axis_start = None
        self._mirror_axis_block_release = False
        self._clear_mirror_axis_overlay()

    def _commit_manual_dimension(self, start: QPointF, end: QPointF):
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 1e-6:
            return

        line_item = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
        line_item.setPen(self._ruler_pen(cosmetic=True))
        line_item.setZValue(9000)
        line_item.setData(0, {"type": "manual_dimension_line"})
        line_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(line_item)

        text_item = QGraphicsTextItem(self._manual_dim_label)
        text_item.setDefaultTextColor(QColor(theme.PRIMARY_HOVER))
        text_item.setFont(QFont(theme.FONT_PRIMARY, max(8, int(9 * self.cw.scale))))
        text_item.setZValue(9001)
        text_item.setData(0, {"type": "manual_dimension_text"})
        text_item.setPos(self._smart_label_pos(start, end, self._manual_dim_label))
        text_item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.addItem(text_item)

        self.cw._push_undo(line_item)
        self.cw._push_undo(text_item)
        self.cw.changed.emit()

    def mousePressEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()
        self.cw._last_click_scene_pos = QPointF(pos.x(), pos.y())

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        if self._mirror_axis_active:
            self._mirror_axis_block_release = True
            if self._mirror_axis_start is None:
                self._mirror_axis_start = QPointF(pos.x(), pos.y())
                self._update_mirror_axis_preview(self._mirror_axis_start, self._mirror_axis_start)
            else:
                end = (
                    self._constrain(self._mirror_axis_start, pos)
                    if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    else QPointF(pos.x(), pos.y())
                )
                start = self._mirror_axis_start
                self.cw._mirror_selected_about_axis(start, end)
                self.cancel_mirror_axis()
            event.accept()
            return

        if self._manual_dim_active:
            self._manual_dim_block_release = True
            if self._manual_dim_start is None:
                self._manual_dim_start = QPointF(pos.x(), pos.y())
                self._update_manual_dimension_preview(self._manual_dim_start, self._manual_dim_start)
            else:
                end = (
                    self._constrain(self._manual_dim_start, pos)
                    if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    else QPointF(pos.x(), pos.y())
                )
                start = self._manual_dim_start
                self._commit_manual_dimension(start, end)
                self.cancel_manual_dimension()
            event.accept()
            return

        if self._angle_mode_active:
            self._angle_mode_block_release = True
            if self._angle_mode_start is None:
                self._angle_mode_start = QPointF(pos.x(), pos.y())
                self._start = QPointF(pos.x(), pos.y())
                self._update_angle_preview(self._angle_mode_start, self._angle_mode_start)
            else:
                end = (
                    self._constrain(self._angle_mode_start, pos)
                    if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    else QPointF(pos.x(), pos.y())
                )
                self._commit_angle_measure(self._angle_mode_start, end)
                self.cancel_angle_mode()
                self.cw._set_tool(Tool.SELECT)
            event.accept()
            return

        # Free Transform ativo: verificar zona de rotação nos cantos
        if self._ft_active and event.button() == Qt.MouseButton.LeftButton:
            view = self._view()
            if view:
                vp_pos = QPointF(view.mapFromScene(pos))
                handle = self._ft_handle_at_vp(vp_pos)
                if handle:
                    self._ft_is_resizing = True
                    self._ft_resize_handle = handle
                    self._ft_resize_start_rect_scene = self._ft_bounding_rect_scene()
                    self._ft_resize_start_transforms = [item.sceneTransform() for item in self._ft_items]
                    event.accept()
                    return
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
                else:
                    # Com FT ativo, só permite interação pelos 8 handles (e rotação nos cantos).
                    # Evita mover o item arrastando o corpo.
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

        # CURVE fase 2: clique inicia o arraste da dobra
        if tool == Tool.CURVE and self._curve_draw_phase == 2:
            self._curve_draw_phase = 3
            self._curve_dragging = True
            self._start = QPointF(pos.x(), pos.y())
            event.accept()
            return

        self._snap_point = None
        self._snap_points_cache = []
        self._start = QPointF(pos.x(), pos.y())
        self._pen_last_point = None
        self._pen_shift_anchor = None
        self._pen_shift_base_path = None
        self._ruler_commit_on_release = (
            tool == Tool.RULER
            and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        )

        if tool == Tool.PEN:
            self._painter_path = QPainterPath(pos)
            self._path_item = QGraphicsPathItem()
            self._path_item.setPen(self._pen())
            self.addItem(self._path_item)
            self._pen_last_point = QPointF(pos.x(), pos.y())

        elif tool == Tool.LINE:
            self._start = QPointF(pos.x(), pos.y())
            # Cache de snap para a sessão atual de desenho da linha (evita varredura a cada mouse move).
            self._snap_points_cache = self._collect_snap_points()
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
            # Fase 1: início — define ponto inicial da linha base
            self._curve_draw_phase = 1
            self._curve_bend_count = 0
            self._curve_dragging = True
            self._curve_draw_start = QPointF(pos.x(), pos.y())
            self._curve_ctrl_1 = None
            self._curve_ctrl_2 = None
            p = QPainterPath(self._curve_draw_start)
            p.lineTo(self._curve_draw_start)
            self._preview_item = QGraphicsPathItem(p)
            self._preview_item.setPen(self._pen())
            self.addItem(self._preview_item)

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
            r = HollowRectItem(QRectF(pos, pos))
            r.setPen(self._pen())
            self.addItem(r)
            self._preview_item = r

        elif tool == Tool.ELLIPSE:
            e = HollowEllipseItem(QRectF(pos, pos))
            e.setPen(self._pen())
            self.addItem(e)
            self._preview_item = e

        event.accept()

    def mouseMoveEvent(self, event):
        tool = self.cw.tool
        pos  = event.scenePos()

        if self._mirror_axis_active and self._mirror_axis_start is not None:
            end = (
                self._constrain(self._mirror_axis_start, pos)
                if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                else QPointF(pos.x(), pos.y())
            )
            self._update_mirror_axis_preview(self._mirror_axis_start, end)
            event.accept()
            return

        if self._manual_dim_active and self._manual_dim_start is not None:
            end = (
                self._constrain(self._manual_dim_start, pos)
                if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                else QPointF(pos.x(), pos.y())
            )
            self._update_manual_dimension_preview(self._manual_dim_start, end)
            event.accept()
            return

        if self._angle_mode_active and self._angle_mode_start is not None:
            end = (
                self._constrain(self._angle_mode_start, pos)
                if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                else QPointF(pos.x(), pos.y())
            )
            self._update_angle_preview(self._angle_mode_start, end)
            event.accept()
            return

        # Free Transform: redimensionamento fluido
        if self._ft_is_resizing:
            self._apply_ft_resize_to_selected(pos)
            self.update()
            event.accept()
            return

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

        if self._start is None and not (
            tool == Tool.CURVE and self._curve_draw_phase in (2, 3)
        ):
            # Limpa indicador se o mouse saiu sem estar desenhando
            if self._snap_point is not None:
                self._snap_point = None
                self.update()
            super().mouseMoveEvent(event)
            return

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if tool == Tool.PEN and self._painter_path and self._path_item:
            if shift and self._pen_last_point is not None:
                # Shift na caneta: trava em 0°/45°/90° usando âncora estável
                # para manter uma única reta/diagonal limpa durante o arraste.
                if self._pen_shift_anchor is None:
                    self._pen_shift_anchor = QPointF(self._pen_last_point.x(), self._pen_last_point.y())
                    self._pen_shift_base_path = QPainterPath(self._painter_path)
                if self._pen_shift_base_path is not None:
                    constrained = self._constrain(self._pen_shift_anchor, pos)
                    straight_path = QPainterPath(self._pen_shift_base_path)
                    straight_path.lineTo(constrained)
                    self._painter_path = straight_path
                    self._path_item.setPath(self._painter_path)
                    self._pen_last_point = QPointF(constrained.x(), constrained.y())
                    event.accept()
                    return
            else:
                self._pen_shift_anchor = None
                self._pen_shift_base_path = None

            if self._pen_last_point is not None:
                if math.hypot(pos.x() - self._pen_last_point.x(), pos.y() - self._pen_last_point.y()) < self.PEN_MIN_STEP:
                    event.accept()
                    return
            self._painter_path.lineTo(pos)
            self._path_item.setPath(self._painter_path)
            self._pen_last_point = QPointF(pos.x(), pos.y())

        elif tool == Tool.LINE and self._preview_item:
            snap = self._find_snap(pos, candidates=self._snap_points_cache)
            old_snap = self._snap_point
            if snap is not None:
                end = snap
                self._snap_point = snap
            else:
                end = self._constrain(self._start, pos) if shift else pos
                self._snap_point = None
            self._preview_item.setLine(self._start.x(), self._start.y(),
                                       end.x(), end.y())
            if old_snap != self._snap_point:
                self.update()

        elif tool == Tool.RULER:
            end = self._constrain(self._start, pos) if shift else pos
            self._update_ruler(self._start, end)

        elif tool == Tool.ARROW and self._preview_item:
            end = self._constrain(self._start, pos) if shift else pos
            self._preview_item.setPath(self._arrow_path(self._start, end))

        elif tool == Tool.CURVE and self._preview_item:
            if self._curve_draw_phase == 1 and self._curve_draw_start:
                # Atualiza linha reta: o fim segue o mouse
                p = QPainterPath(self._curve_draw_start)
                p.lineTo(pos)
                self._preview_item.setPath(p)
            elif self._curve_draw_phase == 3 and self._curve_draw_start and self._curve_draw_end:
                # Arraste da dobra: preview da curva com controle no mouse.
                p = QPainterPath(self._curve_draw_start)
                if self._curve_bend_count <= 0 or self._curve_ctrl_1 is None:
                    p.quadTo(pos, self._curve_draw_end)
                else:
                    p.cubicTo(self._curve_ctrl_1, pos, self._curve_draw_end)
                self._preview_item.setPath(p)

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
        if self._mirror_axis_block_release and event.button() == Qt.MouseButton.LeftButton:
            self._mirror_axis_block_release = False
            event.accept()
            return
        if self._mirror_axis_active and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return

        if self._manual_dim_block_release and event.button() == Qt.MouseButton.LeftButton:
            self._manual_dim_block_release = False
            event.accept()
            return
        if self._manual_dim_active and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return

        if self._angle_mode_block_release and event.button() == Qt.MouseButton.LeftButton:
            self._angle_mode_block_release = False
            event.accept()
            return
        if self._angle_mode_active and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return

        # Free Transform: fim do redimensionamento (mantém ft ativo para mais ajustes)
        if self._ft_is_resizing:
            self._ft_is_resizing = False
            self._ft_resize_handle = ""
            self._ft_resize_start_rect_scene = QRectF()
            self._ft_resize_start_transforms = []
            self.update()
            self.cw.changed.emit()
            event.accept()
            return

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
            self._pen_last_point = None
            self._pen_shift_anchor = None
            self._pen_shift_base_path = None

        elif tool in (Tool.LINE, Tool.RECT, Tool.ELLIPSE, Tool.ARROW) and self._preview_item:
            if tool == Tool.LINE:
                snap = self._find_snap(pos, candidates=self._snap_points_cache)
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

        elif tool == Tool.CURVE and self._curve_draw_phase == 1:
            # Fim do drag da linha base → transita para fase 2
            if (self._curve_draw_start and
                    math.hypot(pos.x() - self._curve_draw_start.x(),
                               pos.y() - self._curve_draw_start.y()) < 3):
                # Linha muito curta: cancela
                self._cancel_curve_draw()
            else:
                self._curve_draw_end = QPointF(pos.x(), pos.y())
                # Congela a linha reta no preview
                p = QPainterPath(self._curve_draw_start)
                p.lineTo(self._curve_draw_end)
                self._preview_item.setPath(p)
                self._curve_draw_phase = 2
                self._curve_dragging = False
            self._start = None
            return  # não limpa _start nem _snap_points_cache abaixo

        elif tool == Tool.CURVE and self._curve_draw_phase == 3:
            self._commit_curve_draw(pos)
            return

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
        self._snap_points_cache = []
        self._ruler_commit_on_release = False

    def keyPressEvent(self, event):
        # Enter ou Escape confirmam/saem do Free Transform
        if self._ft_active:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                self._exit_ft()
                event.accept()
                return

        if self._mirror_axis_active and event.key() == Qt.Key.Key_Escape:
            self.cancel_mirror_axis()
            event.accept()
            return

        if self._manual_dim_active and event.key() == Qt.Key.Key_Escape:
            self.cancel_manual_dimension()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._curve_session_active:
            self._cancel_curve_session()
            event.accept()
            return

        if self._curve_draw_phase > 0 and event.key() == Qt.Key.Key_Escape:
            self._cancel_curve_draw()
            event.accept()
            return

        focus_item = self.focusItem()
        if (
            isinstance(focus_item, QGraphicsTextItem)
            and focus_item.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction
        ):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        has_selected_angle_marker = bool(self._selected_angle_markers())
        if has_selected_angle_marker:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                if self._resize_selected_angle_markers(self.ANGLE_MARKER_SCALE_STEP):
                    self.cw.changed.emit()
                    event.accept()
                    return
            if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                if self._resize_selected_angle_markers(1.0 / self.ANGLE_MARKER_SCALE_STEP):
                    self.cw.changed.emit()
                    event.accept()
                    return
            if (mods & Qt.KeyboardModifier.AltModifier) and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                rotate_step = (
                    self.ANGLE_MARKER_ROTATE_FAST_STEP
                    if (mods & Qt.KeyboardModifier.ShiftModifier)
                    else self.ANGLE_MARKER_ROTATE_STEP
                )
                delta = -rotate_step if key == Qt.Key.Key_Left else rotate_step
                if self._rotate_selected_angle_markers(delta):
                    self.cw.changed.emit()
                    event.accept()
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

    def __init__(self, scene: QGraphicsScene, canvas_widget=None, parent=None):
        super().__init__(scene, parent)
        self._canvas_widget = canvas_widget
        self._panning    = False
        self._pan_start  = None
        self._space_held = False
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # AnchorViewCenter: mantém o centro ao redimensionar (AnchorUnderMouse causava
        # scroll incorreto no primeiro show, pois o mouse ainda não está no canvas)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        vp = self.viewport()
        vp.installEventFilter(self)
        vp.setMouseTracking(True)   # receber MouseMove sem botão pressionado
        vp.setAcceptDrops(True)

    def _can_accept_image_mime(self, mime: QMimeData | None) -> bool:
        if mime is None:
            return False
        if mime.hasImage():
            return True
        if mime.hasUrls():
            return True
        if mime.hasText():
            return True
        return False

    def dragEnterEvent(self, event):
        if self._can_accept_image_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._can_accept_image_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self._canvas_widget is None:
            super().dropEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        inserted = self._canvas_widget._handle_external_image_mime(event.mimeData(), scene_pos)
        if inserted:
            event.acceptProposedAction()
            return
        super().dropEvent(event)

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
                handle = sc._ft_handle_at_vp(vp_pos)
                if handle:
                    self.viewport().setCursor(sc._ft_cursor_for_handle(handle))
                elif sc._in_rotation_zone_vp(vp_pos):
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
        self._attached_dwg: str = ""
        self._clipboard_signature = ""
        self._paste_serial = 0
        self._last_click_scene_pos: QPointF | None = None
        self._pen_dot_cursor: QCursor | None = None
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
            (Tool.ANGLE,    "∠ Ângulo",    "U"),
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
        self.combo_style.currentIndexChanged.connect(self._on_pen_style_changed)
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

        btn_mirror_h = QPushButton("Horizontal")
        btn_mirror_h.setFixedHeight(fh)
        btn_mirror_h.setToolTip("Espelhar com cópia na horizontal (Ctrl+Shift+H)")
        btn_mirror_h.clicked.connect(self._mirror_selected_horizontal)
        btn_mirror_h.setStyleSheet(self._tool_btn_style())
        row2.addWidget(btn_mirror_h)

        btn_mirror_v = QPushButton("Vertical")
        btn_mirror_v.setFixedHeight(fh)
        btn_mirror_v.setToolTip("Espelhar com cópia na vertical (Ctrl+J)")
        btn_mirror_v.clicked.connect(self._mirror_selected_vertical)
        btn_mirror_v.setStyleSheet(self._tool_btn_style())
        row2.addWidget(btn_mirror_v)

        row2.addSpacing(8)

        btn_img = QPushButton("🖼️ Imagem")
        btn_img.setFixedHeight(fh)
        btn_img.clicked.connect(lambda: self._insert_image())
        btn_img.setStyleSheet(self._tool_btn_style())

        btn_pdf = QPushButton("📎 PDF")
        btn_pdf.setFixedHeight(fh)
        btn_pdf.clicked.connect(self._attach_pdf)
        btn_pdf.setStyleSheet(self._tool_btn_style())

        btn_attachments = QPushButton("Anexos")
        btn_attachments.setFixedHeight(fh)
        btn_attachments.setToolTip("Anexar arquivo DWG")
        btn_attachments.clicked.connect(self._attach_dwg)
        btn_attachments.setStyleSheet(self._tool_btn_style())

        btn_3d = QPushButton("3D")
        btn_3d.setFixedHeight(fh)
        btn_3d.setToolTip("Inserir desenho 3D pre-definido")
        btn_3d.clicked.connect(self._open_3d_preset_popup)
        btn_3d.setStyleSheet(self._tool_btn_style())

        btn_dim = QPushButton("📏 MM")
        btn_dim.setFixedHeight(fh)
        btn_dim.setToolTip("Adicionar/editar cota manual, atalho M")
        btn_dim.clicked.connect(self._add_or_edit_manual_dimension)
        btn_dim.setStyleSheet(self._tool_btn_style())

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
        row2.addWidget(btn_attachments)
        row2.addWidget(btn_3d)
        row2.addWidget(btn_dim)
        row2.addWidget(btn_clear)
        row2.addStretch()
        layout.addLayout(row2)

        # Dica de teclado
        hint = QLabel(
            "✨ Shift = traço reto  |  U = ângulo  |  A = seta  |  C = curva na linha/curva selecionada  |  G = triângulo  |  N = pentágono  |  H = hexágono  |  Del = apagar  |  Scroll = zoom  |  "
            "Botão do meio / Space+drag = mover  |  "
            "Ctrl+C / Ctrl+V = duplicar e colar  |  "
            "Ctrl+Shift+H = espelhar com cópia horizontal  |  Ctrl+J = espelhar com cópia vertical  |  "
            "Ctrl+T = Free Transform (arrastar fora dos cantos = girar)  |  M = cota manual, 2 cliques na linha  |  Angulo selecionado: +/- = tamanho  |  Alt+<-/> = girar (Shift = 15 deg)  |  "
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
        self.view  = DrawingView(self.scene, canvas_widget=self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        # Rubber-band respeita shape() de cada item (borda de rects/elipses ocas)
        self.view.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
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

        # Painel de anexos (DWG)
        self.attachment_panel = QFrame()
        self.attachment_panel.setStyleSheet(
            f"background:{theme.SELECTION_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
        )
        attachment_layout = QHBoxLayout(self.attachment_panel)
        attachment_layout.setContentsMargins(10, 6, 10, 6)
        self.attachment_label = QLabel("Nenhum anexo DWG")
        self.attachment_label.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8,int(10*self.scale))}pt;")
        btn_open_attachment = QPushButton("Abrir")
        btn_open_attachment.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_open_attachment.clicked.connect(self._open_dwg)
        btn_rm_attachment = QPushButton("X")
        btn_rm_attachment.setFixedWidth(28)
        btn_rm_attachment.setStyleSheet(theme.danger_btn_style(self.scale))
        btn_rm_attachment.clicked.connect(self._remove_dwg)
        attachment_layout.addWidget(QLabel("Anexos"))
        attachment_layout.addWidget(self.attachment_label, 1)
        attachment_layout.addWidget(btn_open_attachment)
        attachment_layout.addWidget(btn_rm_attachment)
        self.attachment_panel.setVisible(False)
        layout.addWidget(self.attachment_panel)

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
            Qt.Key.Key_U: Tool.ANGLE,
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

        mirror_h_action = QAction(self)
        mirror_h_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        mirror_h_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        mirror_h_action.triggered.connect(self._mirror_selected_horizontal)
        self.addAction(mirror_h_action)

        mirror_v_action = QAction(self)
        mirror_v_action.setShortcut(QKeySequence("Ctrl+J"))
        mirror_v_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        mirror_v_action.triggered.connect(self._mirror_selected_vertical)
        self.addAction(mirror_v_action)

        manual_dimension_action = QAction(self)
        manual_dimension_action.setShortcut(QKeySequence(Qt.Key.Key_M))
        manual_dimension_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        manual_dimension_action.triggered.connect(self._trigger_manual_dimension_shortcut)
        self.addAction(manual_dimension_action)

        scale_up_action = QAction(self)
        scale_up_action.setShortcut(QKeySequence("Ctrl++"))
        scale_up_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        scale_up_action.triggered.connect(lambda: self._scale_selected_items(1.10))
        self.addAction(scale_up_action)

        scale_up_alt_action = QAction(self)
        scale_up_alt_action.setShortcut(QKeySequence("Ctrl+="))
        scale_up_alt_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        scale_up_alt_action.triggered.connect(lambda: self._scale_selected_items(1.10))
        self.addAction(scale_up_alt_action)

        scale_down_action = QAction(self)
        scale_down_action.setShortcut(QKeySequence("Ctrl+-"))
        scale_down_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        scale_down_action.triggered.connect(lambda: self._scale_selected_items(1.0 / 1.10))
        self.addAction(scale_down_action)

    def _trigger_manual_dimension_shortcut(self):
        if not self.isVisible():
            return
        focus = QApplication.focusWidget()
        if focus and (
            focus.inherits("QLineEdit")
            or focus.inherits("QTextEdit")
            or focus.inherits("QPlainTextEdit")
            or focus.inherits("QAbstractSpinBox")
            or focus.inherits("QComboBox")
        ):
            return
        self._add_or_edit_manual_dimension()

    def _add_or_edit_manual_dimension(self):
        """
        Cota manual:
        - Se houver texto selecionado, edita o conteúdo.
        - Caso contrário, inicia o modo de cota manual (2 cliques para posicionar a linha).
        """
        selected = self.scene.selectedItems()
        target_text = None
        for item in selected:
            if isinstance(item, QGraphicsTextItem):
                target_text = item
                break

        default_value = target_text.toPlainText() if target_text else "Ø 12 mm"
        text, ok = QInputDialog.getText(
            self,
            "Cota manual",
            "Informe a cota (ex.: Ø 12 mm, 350 mm, 1.20 m):",
            text=default_value,
        )
        if not ok:
            return

        label = normalize_upper_text(text)
        label = (label or "").strip()
        if not label:
            return

        if target_text is not None:
            target_text.setPlainText(label)
            self.changed.emit()
            return
        self._set_tool(Tool.SELECT)
        self.scene.begin_manual_dimension(label)

    def _ask_angle_mode_config(self) -> tuple[float, str, str] | None:
        preset, ok = QInputDialog.getItem(
            self,
            "Ângulo",
            "Selecione o valor do ângulo:",
            ["90°", "180°", "Personalizado..."],
            0,
            False,
        )
        if not ok:
            return None

        if preset == "90°":
            degrees = 90.0
        elif preset == "180°":
            degrees = 180.0
        else:
            value, ok = QInputDialog.getDouble(
                self,
                "Ângulo personalizado",
                "Informe o valor em graus:",
                45.0,
                0.1,
                359.9,
                1,
            )
            if not ok:
                return None
            degrees = float(value)

        style_label, ok = QInputDialog.getItem(
            self,
            "Forma do ângulo",
            "Escolha o marcador visual:",
            ["Automático", "Meia lua", "Quadrado"],
            0,
            False,
        )
        if not ok:
            return None

        style_map = {
            "Automático": "auto",
            "Meia lua": "arc",
            "Quadrado": "square",
        }
        style = style_map.get(style_label, "auto")
        label = f"{degrees:.1f}°"
        return degrees, label, style

    def _get_pen_dot_cursor(self) -> QCursor:
        """Cursor em formato de ponto para a ferramenta Caneta."""
        if self._pen_dot_cursor is not None:
            return self._pen_dot_cursor

        size = 12
        center = size // 2
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Anel externo branco com borda preta para contraste em fundos claros/escuros.
        painter.setPen(QPen(QColor("#000000"), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawEllipse(QPointF(center, center), 3.6, 3.6)

        # Centro sólido (ponto de precisão visual).
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#000000")))
        painter.drawEllipse(QPointF(center, center), 1.3, 1.3)
        painter.end()

        self._pen_dot_cursor = QCursor(pix, center, center)
        return self._pen_dot_cursor

    # Ferramentas
    def _set_tool(self, tool: Tool):
        if hasattr(self, "scene") and self.scene._mirror_axis_active:
            self.scene.cancel_mirror_axis()
        if hasattr(self, "scene") and self.scene._manual_dim_active:
            self.scene.cancel_manual_dimension()
        if hasattr(self, "scene") and self.scene._curve_draw_phase > 0:
            self.scene._cancel_curve_draw()
        if hasattr(self, "scene") and self.tool == Tool.ANGLE and tool != Tool.ANGLE:
            self.scene.cancel_angle_mode()
        if tool == Tool.ANGLE:
            config = self._ask_angle_mode_config()
            if config is None:
                tool = Tool.SELECT
            else:
                degrees, label, style = config
                self.scene.begin_angle_mode(degrees, label, style)
        self.tool = tool
        for t, btn in self._tool_btns.items():
            btn.setChecked(t == tool)
        if tool == Tool.SELECT:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, "scene") and self.scene.selectedItems():
                self.scene._ft_items = list(self.scene.selectedItems())
                for item in self.scene._ft_items:
                    item.setTransformOriginPoint(item.boundingRect().center())
                self.scene._ft_active = True
                self.scene.update()
        elif tool == Tool.PEN:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(self._get_pen_dot_cursor())
        elif tool == Tool.ERASER:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            if hasattr(self, "scene"):
                self.scene._ft_active = False
                self.scene._ft_items = []
                self.scene._ft_is_rotating = False
                self.scene._ft_is_resizing = False
                self.scene._ft_resize_handle = ""
                self.scene.update()
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.CrossCursor)

    def _rotate_selected(self):
        """Rotaciona os itens selecionados pelo ângulo do spin (precisão numérica)."""
        angle = self.spin_rotate.value()
        for item in self.scene.selectedItems():
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setRotation(item.rotation() + angle)
        self.changed.emit()

    def _mirror_selected(self, horizontal: bool):
        if self._text_editor_active():
            return
        selected = self.scene.selectedItems()
        if not selected:
            return
        mirror_items = [item for item in selected if not isinstance(item, QGraphicsTextItem)]
        if not mirror_items:
            return

        source_rect = QRectF()
        has_rect = False
        for item in mirror_items:
            item_scene_rect = item.mapToScene(item.boundingRect()).boundingRect()
            if not has_rect:
                source_rect = item_scene_rect
                has_rect = True
            else:
                source_rect = source_rect.united(item_scene_rect)
        if not has_rect:
            return

        clones: list[QGraphicsItem] = []
        for item in mirror_items:
            item_dict = self._item_to_dict(item)
            if not item_dict:
                continue
            clone = self._item_from_dict(item_dict)
            if clone is None:
                continue
            clone.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            clone.setZValue(item.zValue())
            self.scene.addItem(clone)

            center = item.boundingRect().center()
            mirror = QTransform()
            mirror.translate(center.x(), center.y())
            if horizontal:
                mirror.scale(-1.0, 1.0)
            else:
                mirror.scale(1.0, -1.0)
            mirror.translate(-center.x(), -center.y())
            clone.setTransform(mirror, True)
            clones.append(clone)

        if not clones:
            return

        gap = 20.0
        source_center = source_rect.center()
        if horizontal:
            target_center = QPointF(source_center.x() + source_rect.width() + gap, source_center.y())
        else:
            target_center = QPointF(source_center.x(), source_center.y() + source_rect.height() + gap)
        delta = target_center - source_center

        for item in selected:
            item.setSelected(False)
        for clone in clones:
            clone.setPos(clone.pos() + delta)
            clone.setSelected(True)
            self._push_undo(clone)

        self.changed.emit()

    def _mirror_selected_horizontal(self):
        self._mirror_selected(horizontal=True)

    def _mirror_selected_vertical(self):
        self._mirror_selected(horizontal=False)

    def _start_manual_mirror_axis(self):
        if self._text_editor_active():
            return
        selected = self.scene.selectedItems()
        mirror_items = [item for item in selected if not isinstance(item, QGraphicsTextItem)]
        if not mirror_items:
            return
        self._set_tool(Tool.SELECT)
        self.scene.begin_mirror_axis()

    def _mirror_selected_about_axis(self, axis_start: QPointF, axis_end: QPointF):
        if self._text_editor_active():
            return
        if math.hypot(axis_end.x() - axis_start.x(), axis_end.y() - axis_start.y()) < 1e-6:
            return

        selected = self.scene.selectedItems()
        if not selected:
            return
        mirror_items = [item for item in selected if not isinstance(item, QGraphicsTextItem)]
        if not mirror_items:
            return

        clones: list[QGraphicsItem] = []
        for item in mirror_items:
            item_dict = self._item_to_dict(item)
            if not item_dict:
                continue
            clone = self._item_from_dict(item_dict)
            if clone is None:
                continue
            clone.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            clone.setZValue(item.zValue())
            self.scene.addItem(clone)

            p1_local = clone.mapFromScene(axis_start)
            p2_local = clone.mapFromScene(axis_end)
            dx = p2_local.x() - p1_local.x()
            dy = p2_local.y() - p1_local.y()
            if math.hypot(dx, dy) < 1e-6:
                self.scene.removeItem(clone)
                continue

            angle_deg = math.degrees(math.atan2(dy, dx))
            mirror = QTransform()
            mirror.translate(p1_local.x(), p1_local.y())
            mirror.rotate(angle_deg)
            mirror.scale(1.0, -1.0)
            mirror.rotate(-angle_deg)
            mirror.translate(-p1_local.x(), -p1_local.y())
            clone.setTransform(mirror, True)
            clones.append(clone)

        if not clones:
            return

        for item in selected:
            item.setSelected(False)
        for clone in clones:
            clone.setSelected(True)
            self._push_undo(clone)
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
            for item in self.scene.selectedItems():
                if not isinstance(
                    item,
                    (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem),
                ):
                    continue
                meta = item.data(0) or {}
                if isinstance(meta, dict) and meta.get("type") in {
                    "ruler_overlay",
                    "ruler_measure_line",
                    "manual_dimension_overlay",
                    "manual_dimension_line",
                    "angle_dimension_overlay",
                    "mirror_axis_overlay",
                }:
                    continue
                pen = item.pen()
                pen.setWidth(v)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                item.setPen(pen)
            self.scene._sync_ruler_visuals()
        self.changed.emit()

    def _on_pen_style_changed(self, index: int):
        self.pen_style = self.combo_style.itemData(index)
        if not hasattr(self, "scene"):
            return

        for item in self.scene.selectedItems():
            if not isinstance(
                item,
                (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem),
            ):
                continue
            meta = item.data(0) or {}
            if isinstance(meta, dict) and meta.get("type") in {
                "ruler_overlay",
                "ruler_measure_line",
                "manual_dimension_overlay",
                "manual_dimension_line",
                "angle_dimension_overlay",
            }:
                continue
            pen = item.pen()
            pen.setStyle(self.pen_style)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            item.setPen(pen)

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

    # Anexos (DWG)
    def _attach_dwg(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar anexo DWG",
            "",
            "Desenho CAD (*.dwg)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self._attached_dwg = path
            self.attachment_label.setText(os.path.basename(path))
            self.attachment_panel.setVisible(True)
            self.changed.emit()

    def _open_dwg(self):
        if self._attached_dwg and os.path.exists(self._attached_dwg):
            import subprocess
            subprocess.Popen(["start", "", self._attached_dwg], shell=True)

    def _remove_dwg(self):
        self._attached_dwg = ""
        self.attachment_panel.setVisible(False)
        self.changed.emit()

    # 3D pre-definido
    def _open_3d_preset_popup(self):
        options = [
            "quadrado",
            "retangulo",
            "triangulo",
            "prisma",
            "cilindro",
        ]
        selected, ok = QInputDialog.getItem(
            self,
            "Inserir 3D",
            "Escolha um desenho pre-definido:",
            options,
            0,
            False,
        )
        if not ok or not selected:
            return
        self._insert_3d_preset(str(selected).strip().lower())

    def _base_insert_pos(self) -> QPointF:
        if self._last_click_scene_pos is not None:
            return QPointF(self._last_click_scene_pos.x(), self._last_click_scene_pos.y())
        return self.view.mapToScene(self.view.viewport().rect().center())

    def _new_current_pen(self) -> QPen:
        pen = QPen(QColor(self.color), self.pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setStyle(self.pen_style)
        return pen

    def _add_preset_item(self, item: QGraphicsItem):
        if isinstance(item, QGraphicsPathItem):
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.scene.addItem(item)
        item.setSelected(True)
        self._undo_stack.append(item)

    def _scale_selected_items(self, factor: float):
        selected = self.scene.selectedItems()
        if not selected:
            return
        for item in selected:
            current_scale = float(item.scale())
            new_scale = max(0.10, min(20.0, current_scale * factor))
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setScale(new_scale)
        self.changed.emit()

    def _insert_3d_preset(self, preset: str):
        base = self._base_insert_pos()
        pen = self._new_current_pen()
        path = QPainterPath()

        def _draw_polygon(points: list[QPointF]) -> None:
            if not points:
                return
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            path.lineTo(points[0])

        def _offset(points: list[QPointF], dx: float, dy: float) -> list[QPointF]:
            return [QPointF(pt.x() + dx, pt.y() + dy) for pt in points]

        if preset == "quadrado":
            # Cubo isometrico
            side = 130.0
            dx, dy = 48.0, -38.0
            front = [
                QPointF(-side / 2, -side / 2),
                QPointF(side / 2, -side / 2),
                QPointF(side / 2, side / 2),
                QPointF(-side / 2, side / 2),
            ]
            back = _offset(front, dx, dy)
            _draw_polygon(front)
            _draw_polygon(back)
            for i in range(4):
                path.moveTo(front[i])
                path.lineTo(back[i])
        elif preset == "retangulo":
            # Paralelepipedo
            w, h = 190.0, 110.0
            dx, dy = 56.0, -40.0
            front = [
                QPointF(-w / 2, -h / 2),
                QPointF(w / 2, -h / 2),
                QPointF(w / 2, h / 2),
                QPointF(-w / 2, h / 2),
            ]
            back = _offset(front, dx, dy)
            _draw_polygon(front)
            _draw_polygon(back)
            for i in range(4):
                path.moveTo(front[i])
                path.lineTo(back[i])
        elif preset == "triangulo":
            # Prisma triangular
            front = [
                QPointF(0.0, -90.0),
                QPointF(-88.0, 70.0),
                QPointF(88.0, 70.0),
            ]
            back = _offset(front, 52.0, -38.0)
            _draw_polygon(front)
            _draw_polygon(back)
            for i in range(3):
                path.moveTo(front[i])
                path.lineTo(back[i])
        elif preset == "prisma":
            # Prisma pentagonal
            front = [
                QPointF(0.0, -96.0),
                QPointF(88.0, -30.0),
                QPointF(56.0, 74.0),
                QPointF(-56.0, 74.0),
                QPointF(-88.0, -30.0),
            ]
            back = _offset(front, 48.0, -34.0)
            _draw_polygon(front)
            _draw_polygon(back)
            for i in range(5):
                path.moveTo(front[i])
                path.lineTo(back[i])
        elif preset == "cilindro":
            # Cilindro completo em um unico item
            w = 176.0
            ellipse_h = 46.0
            body_h = 132.0
            top_y = -body_h / 2
            bottom_y = body_h / 2
            path.addEllipse(QRectF(-w / 2, top_y - ellipse_h / 2, w, ellipse_h))
            path.addEllipse(QRectF(-w / 2, bottom_y - ellipse_h / 2, w, ellipse_h))
            path.moveTo(QPointF(-w / 2, top_y))
            path.lineTo(QPointF(-w / 2, bottom_y))
            path.moveTo(QPointF(w / 2, top_y))
            path.lineTo(QPointF(w / 2, bottom_y))
        else:
            return

        item = QGraphicsPathItem(path)
        item.setPen(pen)
        item.setPos(base)
        self.scene.clearSelection()
        self._add_preset_item(item)
        self._redo_stack.clear()
        self.changed.emit()

    # Limpar
    def _clear(self):
        self.scene.cancel_angle_mode()
        self.scene.cancel_mirror_axis()
        self.scene.cancel_manual_dimension()
        self.scene.clear()
        # Restaura o sceneRect fixo (scene.clear() o remove)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.scene._ruler_line_item = None
        self.scene._ruler_text_item = None
        self.scene._manual_dim_line_item = None
        self.scene._manual_dim_text_item = None
        self.scene._angle_text_preview_item = None
        self.scene._angle_marker_preview_item = None
        self.scene._mirror_axis_line_item = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.changed.emit()

    def _image_paths_from_mime(self, mime: QMimeData) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()

        def _push(path: str):
            norm = os.path.normpath(str(path or "").strip().strip('"'))
            if not norm:
                return
            ext = os.path.splitext(norm)[1].lower()
            if ext not in _IMAGE_FILE_EXTENSIONS:
                return
            if not os.path.isfile(norm):
                return
            key = os.path.normcase(norm)
            if key in seen:
                return
            seen.add(key)
            paths.append(norm)

        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    _push(url.toLocalFile())

        if mime.hasText():
            raw = str(mime.text() or "")
            for line in raw.replace("\r", "\n").split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("file://"):
                    _push(QUrl(line).toLocalFile())
                else:
                    _push(line)

        return paths

    def _insert_image_files(self, paths: list[str], scene_pos: QPointF | None = None) -> int:
        if not paths:
            return 0
        inserted = 0
        self.scene.clearSelection()
        for idx, path in enumerate(paths):
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            pos = None
            if scene_pos is not None:
                offset = 24.0 * idx
                pos = QPointF(scene_pos.x() + offset, scene_pos.y() + offset)
            item = self._insert_image_from_pixmap(pixmap, pos=pos, path=path)
            if item:
                item.setSelected(True)
                inserted += 1
        return inserted

    def _handle_external_image_mime(self, mime: QMimeData, scene_pos: QPointF | None = None) -> bool:
        paths = self._image_paths_from_mime(mime)
        if paths:
            return self._insert_image_files(paths, scene_pos=scene_pos) > 0

        if mime.hasImage():
            image = mime.imageData()
            pixmap = QPixmap()
            if isinstance(image, QPixmap):
                pixmap = image
            else:
                try:
                    pixmap = QPixmap.fromImage(image)
                except Exception:
                    pixmap = QPixmap()
            if not pixmap.isNull():
                self.scene.clearSelection()
                item = self._insert_image_from_pixmap(
                    pixmap,
                    pos=scene_pos,
                    image_data=_pixmap_to_base64(pixmap),
                )
                if item:
                    item.setSelected(True)
                    return True
        return False

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

        if self._handle_external_image_mime(mime):
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

        # Evita que pares de angulo colados compartilhem o mesmo vinculo do original.
        angle_link_remap: dict[str, str] = {}
        for item in created:
            meta = item.data(0)
            if not isinstance(meta, dict):
                continue
            if meta.get("type") not in {"angle_dimension_marker", "angle_dimension_text"}:
                continue
            old_link_id = str(meta.get("angle_link_id", "")).strip()
            if not old_link_id:
                continue
            if old_link_id not in angle_link_remap:
                angle_link_remap[old_link_id] = self.scene._new_angle_link_id()
            new_meta = dict(meta)
            new_meta["angle_link_id"] = angle_link_remap[old_link_id]
            item.setData(0, new_meta)

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
            "dwg": self._attached_dwg,
            "attachments": {
                "dwg": self._attached_dwg,
            },
        }, ensure_ascii=False)

    def from_json(self, data: str):
        self._clear()
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        self._attached_pdf = obj.get("pdf", "")
        attachments = obj.get("attachments", {}) if isinstance(obj.get("attachments"), dict) else {}
        self._attached_dwg = str(obj.get("dwg") or attachments.get("dwg") or "")
        self.pdf_panel.setVisible(False)
        self.attachment_panel.setVisible(False)
        if self._attached_pdf:
            self.pdf_label.setText(os.path.basename(self._attached_pdf))
            self.pdf_panel.setVisible(True)
        if self._attached_dwg:
            self.attachment_label.setText(os.path.basename(self._attached_dwg))
            self.attachment_panel.setVisible(True)
        load_canvas_scene(self.scene, data, selectable=True)

    def _item_to_dict(self, item: QGraphicsItem) -> dict | None:
        meta = item.data(0) or {}
        if isinstance(meta, dict) and meta.get("type") in {
            "ruler_overlay",
            "manual_dimension_overlay",
            "angle_dimension_overlay",
            "mirror_axis_overlay",
        }:
            return None

        pen_data = lambda p: {
            "color": p.color().name(),
            "width": p.width(),
            "style": _STYLE_TO_STR.get(p.style(), "solid"),
        }

        rot = item.rotation()
        transform_data = _serialize_transform(item.transform())

        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            if isinstance(meta, dict) and meta.get("type") == "ruler_measure_line":
                return {"type": "ruler_measure_line",
                        "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                        "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                        "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}
            if isinstance(meta, dict) and meta.get("type") == "manual_dimension_line":
                return {"type": "manual_dimension_line",
                        "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                        "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                        "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}
            if isinstance(meta, dict) and meta.get("type") == "angle_dimension_line":
                return {"type": "angle_dimension_line",
                        "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                        "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                        "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}
            return {"type": "line",
                    "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}

        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            return {"type": "rect",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}

        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            return {"type": "ellipse",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}

        if isinstance(item, QGraphicsPathItem):
            if isinstance(meta, dict) and meta.get("type") == "angle_dimension_marker":
                path = item.path()
                angle_link_id = str(meta.get("angle_link_id", "")).strip()
                return {
                    "type": "angle_dimension_marker",
                    "segments": _serialize_path_segments(path),
                    "pos_x": item.pos().x(),
                    "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()),
                    "rotation": rot,
                    "transform": transform_data,
                    "angle_link_id": angle_link_id,
                }
            path = item.path()
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append([el.x, el.y])
            return {"type": "path", "points": points, "segments": _serialize_path_segments(path),
                    "pos_x": item.pos().x(), "pos_y": item.pos().y(),
                    "pen": pen_data(item.pen()), "rotation": rot, "transform": transform_data}

        if isinstance(item, QGraphicsTextItem):
            if isinstance(meta, dict) and meta.get("type") == "ruler_measure_text":
                return {"type": "ruler_measure_text",
                        "x": item.pos().x(), "y": item.pos().y(),
                        "text": item.toPlainText(),
                        "color": item.defaultTextColor().name(),
                        "font_size": item.font().pointSize(),
                        "rotation": rot, "transform": transform_data}
            if isinstance(meta, dict) and meta.get("type") == "manual_dimension_text":
                return {"type": "manual_dimension_text",
                        "x": item.pos().x(), "y": item.pos().y(),
                        "text": item.toPlainText(),
                        "color": item.defaultTextColor().name(),
                        "font_size": item.font().pointSize(),
                        "rotation": rot, "transform": transform_data}
            if isinstance(meta, dict) and meta.get("type") == "angle_dimension_text":
                angle_link_id = str(meta.get("angle_link_id", "")).strip()
                return {"type": "angle_dimension_text",
                        "x": item.pos().x(), "y": item.pos().y(),
                        "text": item.toPlainText(),
                        "color": item.defaultTextColor().name(),
                        "font_size": item.font().pointSize(),
                        "rotation": rot, "transform": transform_data,
                        "angle_link_id": angle_link_id}
            return {"type": "text",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "text": normalize_upper_text(item.toPlainText()),
                    "color": item.defaultTextColor().name(),
                    "font_size": item.font().pointSize(),
                    "rotation": rot, "transform": transform_data}

        if isinstance(item, QGraphicsPixmapItem):
            meta = item.data(0) or {}
            return {"type": "image",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "path": meta.get("path", ""),
                    "image_data": meta.get("image_data", ""),
                    "display_w": meta.get("display_w", item.pixmap().width()),
                    "display_h": meta.get("display_h", item.pixmap().height()),
                    "rotation": rot, "transform": transform_data}

        return None

    def _item_from_dict(self, d: dict) -> QGraphicsItem | None:
        return build_canvas_item_from_dict(d)


class CanvasPreview(QGraphicsView):
    def __init__(self, scale: float = 1.0, parent=None):
        scene = QGraphicsScene(parent)
        super().__init__(scene, parent)
        self.scale_factor = scale
        self._scene = scene
        self._last_result = {"items": 0, "pdf": "", "dwg": ""}
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
