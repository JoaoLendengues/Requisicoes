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

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
    QPixmap, QKeySequence, QAction,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QGraphicsScene,
    QGraphicsView, QGraphicsLineItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsItem, QInputDialog, QFileDialog,
    QPushButton, QLabel, QColorDialog, QSpinBox, QSizePolicy,
    QFrame,
)
from ..core import theme


class Tool(Enum):
    SELECT   = "select"
    PEN      = "pen"
    LINE     = "line"
    RECT     = "rect"
    ELLIPSE  = "ellipse"
    TEXT     = "text"
    IMAGE    = "image"


def build_canvas_item_from_dict(d: dict) -> QGraphicsItem | None:
    t = d.get("type")
    pen_d = d.get("pen", {})
    pen = QPen(QColor(pen_d.get("color", "#000000")), pen_d.get("width", 2))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)

    if t == "line":
        item = QGraphicsLineItem(d["x1"], d["y1"], d["x2"], d["y2"])
        item.setPen(pen)
        return item

    if t == "rect":
        item = QGraphicsRectItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)
        return item

    if t == "ellipse":
        item = QGraphicsEllipseItem(d["x"], d["y"], d["w"], d["h"])
        item.setPen(pen)
        return item

    if t == "path":
        path = QPainterPath()
        points = d.get("points", [])
        if points:
            path.moveTo(QPointF(points[0][0], points[0][1]))
            for pt in points[1:]:
                path.lineTo(QPointF(pt[0], pt[1]))
        item = QGraphicsPathItem(path)
        item.setPen(pen)
        return item

    if t == "text":
        item = QGraphicsTextItem(d.get("text", ""))
        item.setPos(QPointF(d["x"], d["y"]))
        item.setDefaultTextColor(QColor(d.get("color", "#000000")))
        font = QFont("Segoe UI", d.get("font_size", 12))
        item.setFont(font)
        return item

    if t == "image":
        path = d.get("path", "")
        if path and os.path.exists(path):
            pix = QPixmap(path)
            item = QGraphicsPixmapItem(pix)
            item.setPos(QPointF(d["x"], d["y"]))
            item.setData(0, {"type": "image", "path": path})
            return item

    return None


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

    def _pen(self) -> QPen:
        p = QPen(QColor(self.cw.color), self.cw.pen_width)
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return p

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

        if tool == Tool.SELECT:
            super().mousePressEvent(event)
            return

        if tool == Tool.TEXT:
            text, ok = QInputDialog.getText(None, "Texto", "Digite o texto:")
            if ok and text:
                item = QGraphicsTextItem(text)
                item.setPos(pos)
                item.setDefaultTextColor(QColor(self.cw.color))
                font = QFont("Segoe UI", self.cw.pen_width * 4)
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


# ── Widget principal ──────────────────────────────────────────────────────────
class DrawingCanvas(QWidget):
    changed = Signal()     # emitido quando o canvas é modificado

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale      = scale
        self.tool       = Tool.SELECT
        self.color      = "#000000"
        self.pen_width  = 2
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
        title.setText("✎ DESENHO / REFERÊNCIA")

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self._tool_btns: dict[Tool, QPushButton] = {}

        tools = [
            (Tool.SELECT,  "↖ Selec.", "S"),
            (Tool.PEN,     "Caneta", "P"),
            (Tool.LINE,    "╱ Linha",  "L"),
            (Tool.RECT,    "▭ Ret.",   "R"),
            (Tool.ELLIPSE, "○ Elipse", "E"),
            (Tool.TEXT,    "T Texto",  "T"),
        ]
        for t, label, key in tools:
            btn = QPushButton(f"{label} [{key}]")
            btn.setCheckable(True)
            btn.setFixedHeight(max(24, int(28 * self.scale)))
            btn.clicked.connect(lambda checked, tool=t: self._set_tool(tool))
            btn.setStyleSheet(self._tool_btn_style())
            self._tool_btns[t] = btn
            toolbar.addWidget(btn)

        toolbar.addSpacing(8)
        self._tool_btns[Tool.SELECT].setText("↖ Selec. [S]")
        self._tool_btns[Tool.PEN].setText("⌁ Caneta [P]")
        self._tool_btns[Tool.LINE].setText("╱ Linha [L]")
        self._tool_btns[Tool.RECT].setText("▭ Ret. [R]")
        self._tool_btns[Tool.ELLIPSE].setText("◯ Elipse [E]")
        self._tool_btns[Tool.TEXT].setText("T Texto [T]")

        # Cor
        self.btn_color = QPushButton("")
        self.btn_color.setFixedSize(max(24, int(28 * self.scale)),
                                    max(24, int(28 * self.scale)))
        self.btn_color.setStyleSheet(
            f"background:{self.color}; border-radius:4px; border:1px solid #ccc;"
        )
        self.btn_color.clicked.connect(self._pick_color)
        toolbar.addWidget(self.btn_color)

        # Espessura
        lbl_esp = QLabel("Esp:")
        lbl_esp.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(9*self.scale))}pt;")
        lbl_esp.setText("◉ Esp.:")
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 20)
        self.spin_width.setValue(self.pen_width)
        self.spin_width.setFixedWidth(max(40, int(50 * self.scale)))
        self.spin_width.setFixedHeight(max(24, int(28 * self.scale)))
        self.spin_width.valueChanged.connect(lambda v: setattr(self, "pen_width", v))
        toolbar.addWidget(lbl_esp)
        toolbar.addWidget(self.spin_width)

        toolbar.addSpacing(8)
        # Undo / Redo
        btn_undo = QPushButton("↩ Undo")
        btn_undo.setFixedHeight(max(24, int(28 * self.scale)))
        btn_undo.clicked.connect(self._undo)
        btn_undo.setStyleSheet(self._tool_btn_style())

        btn_redo = QPushButton("↪ Redo")
        btn_redo.setFixedHeight(max(24, int(28 * self.scale)))
        btn_redo.clicked.connect(self._redo)
        btn_redo.setStyleSheet(self._tool_btn_style())

        toolbar.addWidget(btn_undo)
        toolbar.addWidget(btn_redo)
        btn_undo.setText("↺ Desfazer")
        btn_redo.setText("↻ Refazer")

        toolbar.addSpacing(8)
        # Imagem e PDF
        btn_img = QPushButton("Imagem")
        btn_img.setFixedHeight(max(24, int(28 * self.scale)))
        btn_img.clicked.connect(lambda: self._insert_image())
        btn_img.setStyleSheet(self._tool_btn_style())

        btn_pdf = QPushButton("PDF")
        btn_pdf.setFixedHeight(max(24, int(28 * self.scale)))
        btn_pdf.clicked.connect(self._attach_pdf)
        btn_pdf.setStyleSheet(self._tool_btn_style())

        btn_clear = QPushButton("Limpar")
        btn_clear.setFixedHeight(max(24, int(28 * self.scale)))
        btn_clear.clicked.connect(self._clear)
        btn_clear.setStyleSheet(
            f"QPushButton {{ background:#FEF2F2; color:{theme.DANGER}; border:1px solid #fca5a5;"
            f"border-radius:4px; padding:2px 8px; font-size:{max(8, int(9*self.scale))}pt; }}"
            f"QPushButton:hover {{ background:#fee2e2; }}"
        )
        toolbar.addWidget(btn_img)
        toolbar.addWidget(btn_pdf)
        toolbar.addWidget(btn_clear)
        btn_img.setText("▣ Imagem")
        btn_pdf.setText("▤ PDF")
        btn_clear.setText("✕ Limpar")
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Dica de teclado ──────────────────────────────────────────────────
        hint = QLabel("Shift = traço reto  |  Del = apagar seleção  |  Scroll = zoom")
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8*self.scale))}pt; font-style:italic;"
        )
        layout.addWidget(hint)
        hint.setText("⌁ Shift = traço reto  |  Del = apagar seleção  |  Scroll = zoom")

        # ── Cena + View ──────────────────────────────────────────────────────
        self.scene = DrawingScene(self)
        self.view  = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:6px; background:#fff;"
        )
        self.view.setMinimumHeight(max(250, int(300 * self.scale)))
        self.view.wheelEvent = self._zoom_event
        layout.addWidget(self.view)

        # ── Painel de PDF ────────────────────────────────────────────────────
        self.pdf_panel = QFrame()
        self.pdf_panel.setStyleSheet(
            f"background:#F0F9FF; border:1px solid #BAE6FD; border-radius:6px;"
        )
        pdf_layout = QHBoxLayout(self.pdf_panel)
        pdf_layout.setContentsMargins(10, 6, 10, 6)
        self.pdf_label = QLabel("Nenhum arquivo anexado")
        self.pdf_label.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8,int(10*self.scale))}pt;")
        self.pdf_label.setText("Nenhum PDF anexado")
        btn_open_pdf = QPushButton("Abrir")
        btn_open_pdf.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_open_pdf.clicked.connect(self._open_pdf)
        btn_open_pdf.setText("↗ Abrir")
        btn_rm_pdf = QPushButton("X")
        btn_rm_pdf.setFixedWidth(28)
        btn_rm_pdf.setStyleSheet(theme.danger_btn_style(self.scale))
        btn_rm_pdf.clicked.connect(self._remove_pdf)
        pdf_layout.addWidget(QLabel("▤ PDF"))
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
            f"QPushButton {{ background:#F1F5F9; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:4px; padding:2px 8px; font-size:{fs}pt; color:{theme.TEXT_DARK}; }}"
            f"QPushButton:checked {{ background:{theme.PRIMARY}; color:#fff; border-color:{theme.PRIMARY}; }}"
            f"QPushButton:hover:!checked {{ background:#E2E8F0; }}"
        )

    def _setup_shortcuts(self):
        shortcuts = {
            Qt.Key.Key_S: Tool.SELECT,
            Qt.Key.Key_P: Tool.PEN,
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
        else:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "Escolha a cor")
        if color.isValid():
            self.color = color.name()
            self.btn_color.setStyleSheet(
                f"background:{self.color}; border-radius:4px; border:1px solid #ccc;"
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
            self, "Selecionar imagem", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
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
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar PDF", "", "PDF (*.pdf)")
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

    # ── Zoom ─────────────────────────────────────────────────────────────────
    def _zoom_event(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.view.scale(factor, factor)

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
        pen_data = lambda p: {"color": p.color().name(), "width": p.width()}

        if isinstance(item, QGraphicsLineItem):
            ln = item.line()
            return {"type": "line",
                    "x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                    "pen": pen_data(item.pen())}

        if isinstance(item, QGraphicsRectItem):
            r = item.rect()
            return {"type": "rect",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pen": pen_data(item.pen())}

        if isinstance(item, QGraphicsEllipseItem):
            r = item.rect()
            return {"type": "ellipse",
                    "x": r.x(), "y": r.y(), "w": r.width(), "h": r.height(),
                    "pen": pen_data(item.pen())}

        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append([el.x, el.y])
            return {"type": "path", "points": points, "pen": pen_data(item.pen())}

        if isinstance(item, QGraphicsTextItem):
            return {"type": "text",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "text": item.toPlainText(),
                    "color": item.defaultTextColor().name(),
                    "font_size": item.font().pointSize()}

        if isinstance(item, QGraphicsPixmapItem):
            meta = item.data(0) or {}
            return {"type": "image",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "path": meta.get("path", "")}

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
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:6px; background:#fff;"
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
            font = QFont("Segoe UI", max(9, int(10 * self.scale_factor)))
            placeholder.setFont(font)
            placeholder.setPos(20, 20)
            placeholder.setPlainText("◌ Nenhum desenho salvo")
        self._fit_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_scene()

    def _fit_scene(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 100, 80)
        self.fitInView(rect.adjusted(-10, -10, 10, 10), Qt.AspectRatioMode.KeepAspectRatio)
