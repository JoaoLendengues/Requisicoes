"""
Formulário principal de requisição — fiel ao mockup fornecido.
"""
import os
import io
import shutil
import tempfile
import unicodedata
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QCheckBox,
    QFrame, QSplitter, QTextEdit, QFileDialog, QMessageBox, QDialog,
    QGraphicsDropShadowEffect, QSizePolicy, QGraphicsScene, QGraphicsView,
    QListWidget, QListWidgetItem, QStyle, QApplication, QAbstractItemView, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QDate, Signal, QThread, QObject, QEvent, QTimer, QRegularExpression, QRectF, QSize
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QColor, QFont, QRegularExpressionValidator, QPainter

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea
from ..core.datetime_utils import local_now
from ..core.dialogs import apply_message_box_theme, ask_confirmation
from ..core.resolution import res
from ..core.session import session
from ..core.text_case import bind_uppercase_line_edit, bind_uppercase_text_edit
from ..api import client as api
from ..widgets.status_badge import StatusBadge
from ..widgets.item_table import ItemTable
from ..widgets.canvas_widget import DrawingCanvas, CanvasPreview, load_canvas_scene, Tool

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_SEND = "ENVIADA"


# ── Worker genérico ───────────────────────────────────────────────────────────
class ApiWorker(QObject):
    result   = Signal(object)
    error    = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except api.APIError as e:
            self.error.emit(e.detail)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _Callback(QObject):
    """
    Intermediário criado na thread principal.
    Quando o worker (outra thread) emite result/error, Qt detecta
    a diferença de threads e usa QueuedConnection automaticamente,
    garantindo que os callbacks rodem sempre na thread principal.
    """
    result = Signal(object)
    error  = Signal(str)


def _run_in_thread(fn, *args, on_result=None, on_error=None, **kwargs):
    worker = ApiWorker(fn, *args, **kwargs)
    thread = QThread()

    # _Callback criado aqui (main thread) → tem afinidade com a main thread
    cb = _Callback()

    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    # worker → cb: cross-thread, Qt usa QueuedConnection automaticamente
    worker.result.connect(cb.result)
    worker.error.connect(cb.error)
    worker.finished.connect(thread.quit)

    # cb → callbacks do usuário: cb vive na main thread → roda na main thread
    if on_result:
        cb.result.connect(on_result)
    if on_error:
        cb.error.connect(on_error)

    # Guarda cb no worker para não ser coletado pelo GC antes do término
    worker._cb = cb

    thread.start()
    return thread, worker


def _build_production_note(action: str, destination: str) -> str:
    return f"{PROD_NOTE_PREFIX}|{action}|{destination}"


def _format_phone_text(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    digits = digits[-11:]
    if not digits:
        return ""
    if len(digits) <= 2:
        return f"({digits}"
    formatted = f"({digits[:2]})"
    if len(digits) >= 3:
        formatted += f" {digits[2]}"
    if len(digits) >= 4:
        formatted += f" {digits[3:7]}"
    if len(digits) >= 8:
        formatted += f"-{digits[7:11]}"
    return formatted


def _emphasized_btn_style(base_style: str) -> str:
    return base_style + "QPushButton { font-weight:700; }"


# ── Card helper ───────────────────────────────────────────────────────────────
def _make_card(parent=None) -> QFrame:
    card = QFrame(parent)
    card.setObjectName("reqCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setProperty("theme_bg", "card_bordered")
    card.setStyleSheet("QFrame#reqCard { border-radius:8px; }")
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(10)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    card.setGraphicsEffect(shadow)
    return card


def _field_label(text: str, scale: float) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("accent", "1")
    lbl.setStyleSheet(
        f"font-size:{max(7, int(8*scale))}pt; "
        f"font-weight:bold; text-transform:uppercase; border:none;"
    )
    return lbl


def _value_label(text: str = "—", scale: float = 1.0) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size:{max(9, int(11*scale))}pt; font-weight:bold; border:none;"
    )
    return lbl


# ── Campo de busca de cliente ─────────────────────────────────────────────────
class ClientSearchBox(QWidget):
    """
    Busca de cliente em tempo real — sempre via servidor.

    Adequada para bases com 100k+ clientes: nenhum pré-carregamento.
    Cada keystroke reinicia um debounce de 250 ms; ao disparar, envia o
    termo ao servidor que retorna os 100 resultados mais relevantes usando
    índices GIN de trigrama (busca por nome, código e CPF/CNPJ).
    """
    client_selected = Signal(object)   # dict do cliente ou None

    _DEBOUNCE_MS  = 250   # ms de espera após o último keystroke
    _SERVER_LIMIT = 100   # máximo de resultados por busca

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._selected: dict | None = None
        self._threads: list = []
        self._search_seq = 0

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self._DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_search)

        self._setup_ui()

    # ── Interface ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        s = self.scale
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Nome, código ou CPF/CNPJ...")
        self.input.setFixedHeight(max(30, int(36 * s)))
        self.input.setStyleSheet(theme.input_style(s))
        self.input.textChanged.connect(self._on_text)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        # Dropdown flutuante
        self._drop = QListWidget()
        self._drop.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        self._drop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drop.setStyleSheet(
            f"QListWidget {{ background:{theme.CARD_BG};"
            f"border:2px solid {theme.PRIMARY}; border-radius:0 0 6px 6px;"
            f"font-size:{max(9,int(10*s))}pt; outline:none; }}"
            f"QListWidget::item {{ padding:7px 12px; color:{theme.TEXT_DARK}; }}"
            f"QListWidget::item:hover, QListWidget::item:selected"
            f" {{ background:{theme.PRIMARY}; color:#fff; }}"
        )
        self._drop.itemClicked.connect(self._pick)
        self._drop.installEventFilter(self)
        self._drop.hide()

    # ── Digitação → debounce → servidor ───────────────────────────────────────

    def _on_text(self, text: str):
        # Se o texto atual é o cliente já selecionado, ignora
        if self._selected:
            expected = f"{self._selected['code']} — {self._selected['name']}"
            if text == expected:
                return
            self._selected = None

        term = text.strip()
        if len(term) < 2:
            self._debounce.stop()
            self._drop.hide()
            return

        self._debounce.start(self._DEBOUNCE_MS)

    def _do_search(self):
        term = self.input.text().strip()
        if len(term) < 2:
            return

        self._search_seq += 1
        search_id = self._search_seq

        # Indicador de carregamento enquanto aguarda o servidor
        self._drop.clear()
        loading = QListWidgetItem("  Buscando...")
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        loading.setForeground(QColor(theme.TEXT_LIGHT))
        self._drop.addItem(loading)
        self._reposition()
        self._drop.show()

        t, w = _run_in_thread(
            api.list_clients, term, self._SERVER_LIMIT,
            on_result=lambda clients, sid=search_id: self._on_results(sid, clients),
            on_error=lambda _, sid=search_id: self._on_search_error(sid),
        )
        self._track_thread(t, w)

    def _on_results(self, search_id: int, clients: list):
        if search_id != self._search_seq:
            return
        if not isinstance(clients, list):
            clients = []
        self._render_results(clients)

    def _on_search_error(self, search_id: int):
        if search_id != self._search_seq:
            return
        self._drop.clear()
        it = QListWidgetItem("  Erro ao buscar — verifique a conexão")
        it.setFlags(Qt.ItemFlag.NoItemFlags)
        it.setForeground(QColor(theme.TEXT_LIGHT))
        self._drop.addItem(it)
        self._reposition()
        self._drop.show()

    # ── Renderização ──────────────────────────────────────────────────────────

    def _render_results(self, clients: list):
        self._drop.clear()

        if not clients:
            it = QListWidgetItem("  Nenhum cliente encontrado")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setForeground(QColor(theme.TEXT_LIGHT))
            self._drop.addItem(it)
        else:
            for c in clients:
                cnpj = c.get("cnpj") or ""
                label = f"{c['code']}  —  {c['name']}"
                if cnpj:
                    label += f"    ({cnpj})"
                it = QListWidgetItem(label)
                it.setData(Qt.ItemDataRole.UserRole, c)
                self._drop.addItem(it)
        self._reposition()
        self._drop.show()

    def _reposition(self):
        s = self.scale
        gpos = self.input.mapToGlobal(self.input.rect().bottomLeft())
        row_h = max(30, int(34 * s))
        # Ocupa todo o espaço disponível abaixo do campo na tela
        screen = QApplication.primaryScreen().availableGeometry()
        available_h = screen.bottom() - gpos.y() - 10
        max_by_screen = max(4, available_h // row_h)
        rows = min(max(self._drop.count(), 1), max_by_screen)
        self._drop.move(gpos)
        self._drop.resize(self.input.width(), rows * row_h + 6)

    # ── Seleção ───────────────────────────────────────────────────────────────

    def _pick(self, item: QListWidgetItem):
        client = item.data(Qt.ItemDataRole.UserRole)
        if not client:
            return
        self._selected = client
        self.input.blockSignals(True)
        self.input.setText(f"{client['code']} — {client['name']}")
        self.input.blockSignals(False)
        self._drop.hide()
        self.client_selected.emit(client)

    def _first_selectable(self) -> QListWidgetItem | None:
        """Retorna o primeiro item com dado de cliente (pula itens não-selecionáveis)."""
        for i in range(self._drop.count()):
            it = self._drop.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) is not None:
                return it
        return None

    # ── Navegação por teclado ─────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if obj is self.input:
                if key == Qt.Key.Key_Escape:
                    self._drop.hide()
                    return True
                if key == Qt.Key.Key_Down and self._drop.isVisible():
                    first = self._first_selectable()
                    if first:
                        self._drop.setFocus()
                        self._drop.setCurrentItem(first)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self._drop.isVisible() and self._drop.count():
                        first = self._first_selectable()
                        if first:
                            self._pick(first)
                    return True

            elif obj is self._drop:
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    cur = self._drop.currentItem()
                    if cur:
                        self._pick(cur)
                    return True
                if key == Qt.Key.Key_Escape:
                    self._drop.hide()
                    self.input.setFocus()
                    return True

        if obj is self.input and event.type() == QEvent.Type.FocusOut:
            QTimer.singleShot(180, self._drop.hide)

        return super().eventFilter(obj, event)

    # ── Utilitários internos ──────────────────────────────────────────────────

    def _track_thread(self, thread: QThread, worker: QObject) -> None:
        pair = (thread, worker)
        self._threads.append(pair)

        def _cleanup():
            try:
                self._threads.remove(pair)
            except ValueError:
                pass
            worker.deleteLater()
            thread.deleteLater()

        thread.finished.connect(_cleanup)

    # ── API pública ───────────────────────────────────────────────────────────

    def set_clients(self, clients: list):
        """Mantido por compatibilidade — não é mais necessário."""
        pass

    def get_client_id(self) -> int | None:
        return self._selected["id"] if self._selected else None

    def get_selected(self) -> dict | None:
        return self._selected

    def set_client_by_id(self, client_id: int):
        """Carrega o cliente pelo ID ao abrir uma requisição existente."""
        t, w = _run_in_thread(
            api.get_client, client_id,
            on_result=self._on_client_loaded_by_id,
            on_error=lambda _: None,
        )
        self._track_thread(t, w)

    def _on_client_loaded_by_id(self, client: dict):
        if not client:
            return
        self._selected = client
        self.input.blockSignals(True)
        self.input.setText(f"{client['code']} — {client['name']}")
        self.input.blockSignals(False)

    def clear(self):
        self._selected = None
        self.input.blockSignals(True)
        self.input.clear()
        self.input.blockSignals(False)
        self._drop.hide()

    def apply_theme(self, scale: float | None = None) -> None:
        s = scale if scale is not None else self.scale
        self.input.setStyleSheet(theme.input_style(s))
        self._drop.setStyleSheet(
            f"QListWidget {{ background:{theme.CARD_BG};"
            f"border:2px solid {theme.PRIMARY}; border-radius:0 0 6px 6px;"
            f"font-size:{max(9,int(10*s))}pt; outline:none; }}"
            f"QListWidget::item {{ padding:7px 12px; color:{theme.TEXT_DARK}; }}"
            f"QListWidget::item:hover, QListWidget::item:selected"
            f" {{ background:{theme.PRIMARY}; color:#fff; }}"
        )


# ── Dialog do editor de desenho ───────────────────────────────────────────────
class CanvasDialog(QDialog):
    """Janela modal com o editor de desenho técnico."""

    def __init__(self, json_data: str, scale: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editor de Desenho")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QDialog {{ background-color:{theme.CONTENT_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background-color:{theme.CONTENT_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background-color:transparent; }}"
        )

        # Dimensiona na tela primária (posição definitiva aplicada no showEvent)
        self._pin_to_primary_screen()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.canvas = DrawingCanvas(scale)
        layout.addWidget(self.canvas, 1)

        # Botões inferiores
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("✕ Descartar alterações")
        btn_cancel.setFixedHeight(max(34, int(38 * scale)))
        btn_cancel.setStyleSheet(theme.secondary_btn_style(scale))
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("✓ Salvar desenho e fechar")
        btn_ok.setFixedHeight(max(34, int(38 * scale)))
        btn_ok.setStyleSheet(theme.primary_btn_style(scale))
        btn_ok.clicked.connect(self.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        # Carrega dados existentes
        if json_data and json_data not in ("{}", ""):
            self.canvas.from_json(json_data)

    def get_json(self) -> str:
        return self.canvas.to_json()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc desmarca a ferramenta ativa; não fecha o editor."""
        if event.key() == Qt.Key.Key_Escape:
            if self.canvas.tool != Tool.SELECT:
                # Tinha ferramenta selecionada → volta para cursor de seleção
                self.canvas._set_tool(Tool.SELECT)
            # Em ambos os casos consome o evento — QDialog não vai chamar reject()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Contenção de monitor: sempre exibe na tela primária, sem vazar
    # ------------------------------------------------------------------
    def _pin_to_primary_screen(self) -> None:
        """Dimensiona e posiciona o diálogo inteiramente na tela primária."""
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QLayout
        geo = QGuiApplication.primaryScreen().availableGeometry()
        w = int(geo.width()  * 0.90)
        h = int(geo.height() * 0.88)
        # Impede que o layout force a janela a crescer além dos limites da tela.
        # SetNoConstraint: o layout para de propagar minimumSizeHint para a janela.
        # setMinimumSize(1,1): remove qualquer mínimo explícito que o Qt tiver fixado.
        if self.layout():
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(1, 1)
        self.setMaximumSize(geo.width(), geo.height())
        self.setGeometry(
            geo.x() + (geo.width()  - w) // 2,
            geo.y() + (geo.height() - h) // 2,
            w,
            h,
        )

    def showEvent(self, event) -> None:
        """Após o Windows terminar de posicionar a janela, força a posição correta."""
        super().showEvent(event)
        # QTimer.singleShot(0) garante que o reposicionamento ocorre DEPOIS
        # que o gerenciador de janelas do Windows terminar qualquer ajuste próprio.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._pin_to_primary_screen)


class _CanvasReadOnlyView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, scale: float, parent=None):
        super().__init__(scene, parent)
        self._zoom_level = 0
        self._scale_factor = scale
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:8px; background:#fff;"
        )
        self.setMinimumHeight(max(300, int(420 * scale)))

    def zoom_in(self):
        self._apply_zoom(1.2, 1)

    def zoom_out(self):
        self._apply_zoom(1 / 1.2, -1)

    def fit_scene(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(0, 0, 100, 80)
        self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = 0

    def _apply_zoom(self, factor: float, step: int):
        next_level = self._zoom_level + step
        if next_level < -12 or next_level > 20:
            return
        self._zoom_level = next_level
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_level == 0:
            self.fit_scene()


class CanvasViewerDialog(QDialog):
    """Janela modal para visualizar o desenho sem permitir edição."""

    def __init__(self, json_data: str, scale: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visualizar Desenho")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QDialog {{ background-color:{theme.CONTENT_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background-color:{theme.CONTENT_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background-color:transparent; }}"
        )

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.90), int(screen.height() * 0.88))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        helper = QLabel("Visualização somente leitura. Use Ctrl + rolagem para zoom.")
        helper.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * scale))}pt;"
        )
        toolbar.addWidget(helper)
        toolbar.addStretch()

        btn_zoom_out = QPushButton("Zoom -")
        btn_zoom_out.setFixedHeight(max(30, int(34 * scale)))
        btn_zoom_out.setStyleSheet(theme.secondary_btn_style(scale))
        toolbar.addWidget(btn_zoom_out)

        btn_zoom_in = QPushButton("Zoom +")
        btn_zoom_in.setFixedHeight(max(30, int(34 * scale)))
        btn_zoom_in.setStyleSheet(theme.secondary_btn_style(scale))
        toolbar.addWidget(btn_zoom_in)

        btn_fit = QPushButton("Ajustar")
        btn_fit.setFixedHeight(max(30, int(34 * scale)))
        btn_fit.setStyleSheet(theme.secondary_btn_style(scale))
        toolbar.addWidget(btn_fit)
        layout.addLayout(toolbar)

        scene = QGraphicsScene(self)
        self.canvas_view = _CanvasReadOnlyView(scene, scale, self)
        layout.addWidget(self.canvas_view, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(max(34, int(38 * scale)))
        btn_close.setStyleSheet(theme.primary_btn_style(scale))
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

        result = load_canvas_scene(scene, json_data, selectable=False)
        if result.get("items", 0) == 0:
            placeholder = scene.addText("Nenhum desenho salvo para visualizar.")
            placeholder.setDefaultTextColor(QColor(theme.TEXT_LIGHT))
            placeholder.setFont(QFont(theme.FONT_PRIMARY, max(9, int(10 * scale))))
            placeholder.setPos(20, 20)
        self.canvas_view.fit_scene()

        btn_zoom_in.clicked.connect(self.canvas_view.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas_view.zoom_out)
        btn_fit.clicked.connect(self.canvas_view.fit_scene)


# ── View principal ────────────────────────────────────────────────────────────
class RequisitionForm(QWidget):
    saved           = Signal(dict)
    save_requested  = Signal()          # emitido pelo botão Salvar do formulário
    guide_requested = Signal()          # emitido pelo botão ? de ajuda
    req_id: int | None = None

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._clients: list[dict] = []
        self._threads: list = []
        self._canvas_json: str = "{}"   # armazena o JSON do desenho
        self._setup_ui()
        self._setup_hidden_shortcuts()
        self._load_clients()
        self._update_canvas_preview()

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ScrollArea
        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}"
        )
        root.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setStyleSheet(f"background:{theme.CONTENT_BG};")
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        s = self.scale
        margin = max(12, int(16 * s))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(10, int(12 * s)))

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_info_bar())
        layout.addWidget(self._build_client_section())
        layout.addWidget(self._build_items_section())
        layout.addWidget(self._build_bottom_section())

        # ── Botões Salvar + WhatsApp ──────────────────────────────────────────
        s = self.scale
        save_row = QHBoxLayout()
        save_row.addStretch()

        btn_calc = QPushButton("🧮 CALCULADORA DE PESO")
        btn_calc.setFixedHeight(max(42, int(48 * s)))
        btn_calc.setMinimumWidth(max(200, int(230 * s)))
        btn_calc.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        btn_calc.clicked.connect(self._open_weight_calculator)
        save_row.addWidget(btn_calc)
        self.btn_calc = btn_calc

        save_row.addSpacing(max(8, int(10 * s)))

        btn_production = QPushButton("ENVIAR PARA PRODUÇÃO")
        btn_production.setFixedHeight(max(42, int(48 * s)))
        btn_production.setMinimumWidth(max(220, int(250 * s)))
        btn_production.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        btn_production.clicked.connect(self._send_to_production)
        save_row.addWidget(btn_production)
        self.btn_production = btn_production
        self.btn_production.setText("🏭 ENVIAR PARA PRODUÇÃO")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_whatsapp = QPushButton("ENVIAR WHATSAPP")
        btn_whatsapp.setFixedHeight(max(42, int(48 * s)))
        btn_whatsapp.setMinimumWidth(max(180, int(210 * s)))
        btn_whatsapp.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        btn_whatsapp.clicked.connect(self._send_whatsapp_client)
        save_row.addWidget(btn_whatsapp)
        self.btn_whatsapp = btn_whatsapp
        self.btn_whatsapp.setText("📲 ENVIAR WHATSAPP")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_print = QPushButton("IMPRIMIR")
        btn_print.setFixedHeight(max(42, int(48 * s)))
        btn_print.setMinimumWidth(max(180, int(210 * s)))
        btn_print.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        self.btn_print = btn_print
        self._update_print_button_visual()
        btn_print.clicked.connect(self._print_requisition_pdf)
        save_row.addWidget(btn_print)

        save_row.addSpacing(max(8, int(10 * s)))

        btn_save = QPushButton("SALVAR REQUISIÇÃO")
        btn_save.setFixedHeight(max(42, int(48 * s)))
        btn_save.setMinimumWidth(max(220, int(260 * s)))
        btn_save.setStyleSheet(_emphasized_btn_style(theme.primary_btn_style(s)))
        btn_save.clicked.connect(self.save_requested.emit)
        save_row.addWidget(btn_save)
        self.btn_save = btn_save
        self.btn_save.setText("💾 SALVAR REQUISIÇÃO")
        layout.addLayout(save_row)

        self.lock_label = QLabel("")
        self.lock_label.setVisible(False)
        self.lock_label.setWordWrap(True)
        self.lock_label.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9*s))}pt; font-style:italic; border:none;"
        )
        layout.addWidget(self.lock_label)

        self._editable_widgets = [
            self.client_search,
            self.input_ped,
            self.input_prazo,
            self.chk_retirada,
            self.chk_entrega,
            self.input_obra,
            self.input_fone,
            self.input_address,
            self.item_table,
            self.input_obs,
            self.btn_canvas,
            self.btn_production,
            self.btn_save,
        ]
        self._set_form_locked(False)

        layout.addStretch()

    def _setup_hidden_shortcuts(self) -> None:
        """Atalhos escondidos da tela Nova Requisição (letras simples)."""
        shortcuts = {
            "C": self._shortcut_open_calculator,
            "P": self._shortcut_send_production,
            "S": self._shortcut_save,
            "W": self._shortcut_send_whatsapp,
            "D": self._shortcut_open_drawing_editor,
            "V": self._shortcut_open_drawing_viewer,
            "N": self._shortcut_prompt_ped_action,
            "E": self._shortcut_set_delivery,
            "R": self._shortcut_set_pickup,
        }

        self._hidden_shortcut_actions: list[QAction] = []
        for sequence, callback in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(
                lambda _checked=False, cb=callback: self._run_hidden_shortcut(cb)
            )
            self.addAction(action)
            self._hidden_shortcut_actions.append(action)

    def _run_hidden_shortcut(self, callback) -> None:
        if not self._can_process_hidden_shortcut():
            return
        callback()

    def _can_process_hidden_shortcut(self) -> bool:
        if not self.isVisible():
            return False

        if QApplication.activeModalWidget() is not None:
            return False

        focus = QApplication.focusWidget()
        if focus is None:
            return True

        editable_types = (
            QLineEdit,
            QTextEdit,
            QPlainTextEdit,
            QComboBox,
            QDateEdit,
            QAbstractItemView,
        )
        widget = focus
        while widget is not None:
            if isinstance(widget, editable_types):
                return False
            widget = widget.parentWidget()
        return True

    def _shortcut_open_calculator(self) -> None:
        if hasattr(self, "btn_calc") and self.btn_calc.isEnabled():
            self.btn_calc.click()

    def _shortcut_send_production(self) -> None:
        if hasattr(self, "btn_production") and self.btn_production.isEnabled():
            self.btn_production.click()

    def _shortcut_save(self) -> None:
        if hasattr(self, "btn_save") and self.btn_save.isEnabled():
            self.btn_save.click()

    def _shortcut_send_whatsapp(self) -> None:
        if hasattr(self, "btn_whatsapp") and self.btn_whatsapp.isEnabled():
            self.btn_whatsapp.click()

    def _shortcut_open_drawing_editor(self) -> None:
        if hasattr(self, "btn_canvas") and self.btn_canvas.isEnabled():
            self.btn_canvas.click()

    def _shortcut_open_drawing_viewer(self) -> None:
        if hasattr(self, "btn_canvas_view") and self.btn_canvas_view.isEnabled():
            self.btn_canvas_view.click()

    def _shortcut_prompt_ped_action(self) -> None:
        action = self._ask_ped_shortcut_action()
        if not action:
            return

        ped_number = self._ask_ped_number()
        if not ped_number:
            return

        if action == "fill":
            self.input_ped.setText(ped_number)
            self.input_ped.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.input_ped.selectAll()
            return

        self._open_requisition_by_ped(ped_number)

    def _ask_ped_shortcut_action(self) -> str | None:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Pedido")
        msg.setText("O que deseja fazer com o número do PED?")
        btn_fill = msg.addButton("Preencher PED", QMessageBox.ButtonRole.AcceptRole)
        btn_open = msg.addButton("Abrir por pedido", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

        # Atalhos locais do diálogo: P=Preencher, A=Abrir, C=Cancelar
        for key, button in (("P", btn_fill), ("A", btn_open), ("C", btn_cancel)):
            action = QAction(msg)
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(button.click)
            msg.addAction(action)

        apply_message_box_theme(msg)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_fill:
            return "fill"
        if clicked == btn_open:
            return "open"
        return None

    @staticmethod
    def _normalize_ped_number(value: str | None) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if not digits:
            return ""
        normalized = digits.lstrip("0")
        return normalized or "0"

    def _ask_ped_number(self) -> str | None:
        default_value = (self.input_ped.text() or "").strip()
        dialog = QDialog(self)
        dialog.setWindowTitle("Pedido")
        dialog.setModal(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setStyleSheet(
            f"QDialog {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
            f"}}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        lbl = QLabel("Digite o número do PED:")
        lbl.setStyleSheet(f"font-size:{max(8, int(10 * self.scale))}pt;")
        layout.addWidget(lbl)

        input_ped = QLineEdit(default_value)
        input_ped.setPlaceholderText("Ex.: 123456")
        input_ped.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*")))
        input_ped.setStyleSheet(theme.input_style(self.scale))
        input_ped.setMinimumWidth(max(240, int(280 * self.scale)))
        layout.addWidget(input_ped)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dialog.reject)
        buttons.addWidget(btn_ok)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)
        input_ped.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        input_ped.selectAll()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        ped_number = (input_ped.text() or "").strip()
        if not ped_number:
            return None
        if not ped_number.isdigit():
            QMessageBox.warning(self, "PED", "Digite apenas números no campo PED.")
            return None
        if self._normalize_ped_number(ped_number) == "0":
            QMessageBox.warning(self, "PED", "Informe um número de PED válido.")
            return None
        return ped_number

    def _open_requisition_by_ped(self, ped_number: str) -> None:
        if self.has_unsaved_data():
            if not ask_confirmation(
                self,
                "Abrir requisição por PED",
                "Existem dados no formulário atual que serão substituídos.\n\nDeseja continuar?",
                yes_text="Sim",
                no_text="Não",
            ):
                return

        normalized_target = self._normalize_ped_number(ped_number)
        thread, worker = _run_in_thread(
            api.list_requisitions,
            search=ped_number,
            limit=200,
            on_result=lambda data, target=normalized_target: self._on_requisition_search_by_ped(data, target),
            on_error=lambda msg: QMessageBox.critical(self, "PED", msg),
        )
        self._threads.append((thread, worker))

    def _on_requisition_search_by_ped(self, results: list, normalized_target: str) -> None:
        matches = []
        for req in (results or []):
            req_norm = self._normalize_ped_number(str(req.get("ped_number") or ""))
            if req_norm == normalized_target:
                matches.append(req)

        if not matches:
            QMessageBox.warning(self, "PED", "PED não encontrado.")
            return

        matches.sort(key=lambda req: int(req.get("id") or 0), reverse=True)
        selected = matches[0]
        self.load_requisition(
            selected,
            read_only=session.should_open_requisition_read_only("history"),
        )

    def _shortcut_set_delivery(self) -> None:
        if hasattr(self, "chk_entrega") and self.chk_entrega.isEnabled():
            self.chk_entrega.setChecked(True)

    def _shortcut_set_pickup(self) -> None:
        if hasattr(self, "chk_retirada") and self.chk_retirada.isEnabled():
            self.chk_retirada.setChecked(True)

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    def _build_header(self) -> QFrame:
        card = _make_card()
        layout = QHBoxLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12, int(16*s)), max(8, int(12*s)),
                                   max(12, int(16*s)), max(8, int(12*s)))
        layout.setSpacing(max(12, int(16*s)))

        # Título Requisição + número
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        lbl_req = QLabel("REQUISIÇÃO")
        lbl_req.setProperty("accent", "1")
        lbl_req.setStyleSheet(
            f"font-size:{max(10,int(12*s))}pt; font-weight:700; border:none;"
        )
        self.lbl_ped_num = QLabel("#000000")
        self.lbl_ped_num.setProperty("accent", "1")
        self.lbl_ped_num.setStyleSheet(
            f"font-size:{max(16,int(20*s))}pt; font-weight:bold; border:none;"
        )
        title_col.addWidget(lbl_req)
        title_col.addWidget(self.lbl_ped_num)
        layout.addLayout(title_col)

        layout.addStretch()

        # Data
        date_col = QVBoxLayout()
        date_col.setSpacing(2)
        date_col.addWidget(_field_label("📅 DATA", s))
        self.lbl_date = _value_label(date.today().strftime("%d/%m/%Y"), s)
        date_col.addWidget(self.lbl_date)
        layout.addLayout(date_col)

        # Vendedor
        vend_col = QVBoxLayout()
        vend_col.setSpacing(2)
        vend_col.addWidget(_field_label("👤 VENDEDOR", s))
        self.lbl_vendor = _value_label(session.user_name.upper(), s)
        vend_col.addWidget(self.lbl_vendor)
        layout.addLayout(vend_col)

        # Status
        status_col = QVBoxLayout()
        status_col.setSpacing(2)
        status_col.addWidget(_field_label("STATUS", s))
        self.status_badge = StatusBadge("em_andamento", s)
        status_col.addWidget(self.status_badge)
        layout.addLayout(status_col)

        # PED
        ped_col = QVBoxLayout()
        ped_col.setSpacing(2)
        ped_col.addWidget(_field_label("PED:", s))
        self.input_ped = QLineEdit()
        self.input_ped.setPlaceholderText("Nº pedido")
        self._ped_min_width = max(80, int(100*s))
        self._ped_max_width = max(180, int(240*s))
        self.input_ped.setFixedWidth(self._ped_min_width)
        self.input_ped.setFixedHeight(max(30, int(36*s)))
        self.input_ped.setStyleSheet(
            f"font-size:{max(14,int(18*s))}pt; font-weight:bold; color:{theme.PRIMARY};"
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:5px; padding:2px 6px;"
            f"background:{theme.INPUT_BG};"
        )
        # Apenas dígitos permitidos
        self.input_ped.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d*"))
        )
        def _resize_ped_field_width():
            text = self.input_ped.text().strip()
            sample = text if text else self.input_ped.placeholderText()
            target = self.input_ped.fontMetrics().horizontalAdvance(sample) + max(18, int(24 * s))
            target = max(self._ped_min_width, min(self._ped_max_width, target))
            self.input_ped.setFixedWidth(target)

        def _on_ped_changed(t: str):
            self.lbl_ped_num.setText(f"#{t.zfill(6)}" if t else "#000000")
            _resize_ped_field_width()

        self.input_ped.textChanged.connect(_on_ped_changed)
        _resize_ped_field_width()
        ped_col.addWidget(self.input_ped)
        layout.addLayout(ped_col)

        # Botão ? — abre o guia rápido desta tela
        sz_g = max(24, int(28 * s))
        self.btn_guide = QPushButton("?")
        self.btn_guide.setToolTip("Abrir guia rápido")
        self.btn_guide.setFixedSize(sz_g, sz_g)
        self.btn_guide.setStyleSheet(
            f"font-size:{max(10, int(11 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
            f"border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:{sz_g // 2}px; padding:0;"
            f"QPushButton:hover {{ color:{theme.PRIMARY}; border-color:{theme.PRIMARY}; }}"
        )
        self.btn_guide.clicked.connect(self.guide_requested)
        layout.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        return card

    # ── Barra de informações ───────────────────────────────────────────────────
    def _build_info_bar(self) -> QFrame:
        card = _make_card()
        layout = QHBoxLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12,int(16*s)), max(8,int(10*s)),
                                   max(12,int(16*s)), max(8,int(10*s)))
        layout.setSpacing(max(16,int(20*s)))

        def add_field(icon, label, widget):
            col = QVBoxLayout()
            col.setSpacing(2)
            title = f"{icon}  {label}".strip() if icon else label
            col.addWidget(_field_label(title, s))
            col.addWidget(widget)
            layout.addLayout(col)

        # Prazo de entrega
        self.input_prazo = QDateEdit(QDate.currentDate())
        self.input_prazo.setDisplayFormat("dd/MM/yyyy")
        self.input_prazo.setCalendarPopup(True)
        self.input_prazo.setFixedHeight(max(28,int(32*s)))
        self.input_prazo.setStyleSheet(theme.input_style(s))
        add_field("📦", "PRAZO DE ENTREGA", self.input_prazo)
        self._apply_min_delivery_constraint()

        # Retirada — mutuamente exclusivo com Entrega
        chk_style = f"color:{theme.TEXT_DARK}; font-size:{max(9,int(11*s))}pt; border:none;"

        self.chk_retirada = QCheckBox("NÃO")
        self.chk_retirada.setStyleSheet(chk_style)
        add_field("🏪", "RETIRADA", self.chk_retirada)

        self.chk_entrega = QCheckBox("NÃO")
        self.chk_entrega.setStyleSheet(chk_style)
        add_field("🚚", "ENTREGA", self.chk_entrega)

        # Mutuamente exclusivos + texto dinâmico SIM / NÃO
        def _on_retirada(checked: bool):
            self.chk_retirada.setText("SIM" if checked else "NÃO")
            if checked:
                self.chk_entrega.setChecked(False)

        def _on_entrega(checked: bool):
            self.chk_entrega.setText("SIM" if checked else "NÃO")
            if checked:
                self.chk_retirada.setChecked(False)

        self.chk_retirada.toggled.connect(_on_retirada)
        self.chk_entrega.toggled.connect(_on_entrega)

        layout.addStretch()

        return card

    # ── Prazo mínimo de entrega (dias úteis) ──────────────────────────────────
    @staticmethod
    def _earliest_delivery_qdate(min_days: int) -> QDate:
        """Retorna a data mais cedo permitida, somando `min_days` dias úteis
        (segunda a sexta) a partir de hoje. Sábado e domingo não contam."""
        current = QDate.currentDate()
        if min_days <= 0:
            return current
        added = 0
        while added < min_days:
            current = current.addDays(1)
            if current.dayOfWeek() <= 5:  # 1=seg ... 5=sex
                added += 1
        return current

    def _apply_min_delivery_constraint(self) -> None:
        """Aplica a data mínima de entrega ao seletor de prazo.
        Admin/gerente podem gravar abaixo do mínimo, então não recebem trava."""
        if getattr(session, "is_manager_or_admin", False):
            return
        try:
            min_days = int(res._read_file().get("min_delivery_business_days", 0) or 0)
        except Exception:
            min_days = 0
        if min_days <= 0:
            return
        earliest = self._earliest_delivery_qdate(min_days)
        self.input_prazo.setMinimumDate(earliest)
        if self.input_prazo.date() < earliest:
            self.input_prazo.setDate(earliest)
        self.input_prazo.setToolTip(
            f"Prazo mínimo de entrega: {min_days} dia(s) útil(eis) "
            f"(a partir de {earliest.toString('dd/MM/yyyy')})"
        )

    # ── Seção Cliente ─────────────────────────────────────────────────────────
    def _build_client_section(self) -> QFrame:
        card = _make_card()
        layout = QGridLayout(card)
        s = self.scale
        layout.setContentsMargins(max(12,int(16*s)), max(10,int(12*s)),
                                   max(12,int(16*s)), max(10,int(12*s)))
        layout.setHorizontalSpacing(max(16,int(20*s)))
        layout.setVerticalSpacing(max(6,int(8*s)))

        # Cliente (busca em tempo real por nome, código ou CPF/CNPJ)
        layout.addWidget(_field_label("👤 CLIENTE", s), 0, 0)
        self.client_search = ClientSearchBox(s, self)
        self.client_search.client_selected.connect(self._on_client_selected)
        layout.addWidget(self.client_search, 1, 0)

        # Obra
        layout.addWidget(_field_label("🏗️ OBRA", s), 0, 1)
        self.input_obra = QLineEdit()
        self.input_obra.setPlaceholderText("Nome da obra")
        self.input_obra.setFixedHeight(max(30,int(36*s)))
        self.input_obra.setStyleSheet(theme.input_style(s))
        bind_uppercase_line_edit(self.input_obra)
        layout.addWidget(self.input_obra, 1, 1)

        # Fone
        layout.addWidget(_field_label("📞 FONE", s), 2, 0)
        self.input_fone = QLineEdit()
        self.input_fone.setPlaceholderText("(61) 9 9999-9999")
        self.input_fone.setFixedHeight(max(30,int(36*s)))
        self.input_fone.setStyleSheet(theme.input_style(s))
        self.input_fone.setMaxLength(16)
        self.input_fone.textEdited.connect(self._on_phone_edited)
        layout.addWidget(self.input_fone, 3, 0)

        # Endereço
        layout.addWidget(_field_label("📍 ENDEREÇO A ENTREGAR", s), 2, 1)
        self.input_address = QLineEdit()
        self.input_address.setPlaceholderText("Endereço completo de entrega")
        self.input_address.setFixedHeight(max(30,int(36*s)))
        self.input_address.setStyleSheet(theme.input_style(s))
        bind_uppercase_line_edit(self.input_address)
        layout.addWidget(self.input_address, 3, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return card

    # ── Itens (largura total) ─────────────────────────────────────────────────
    def _build_items_section(self) -> QFrame:
        s = self.scale
        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent; border:none;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(max(10, int(12 * s)))

        items_card = _make_card()
        items_layout = QVBoxLayout(items_card)
        items_layout.setContentsMargins(max(10, int(12*s)), max(10, int(12*s)),
                                         max(10, int(12*s)), max(10, int(12*s)))
        items_layout.setSpacing(max(8, int(10*s)))

        self.item_table = ItemTable(s)
        self.item_table.product_lookup_requested.connect(self._lookup_product_by_code)
        items_layout.addWidget(self.item_table)
        row.addWidget(items_card, 2)

        preview_card = _make_card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(max(10, int(12*s)), max(10, int(12*s)),
                                          max(10, int(12*s)), max(10, int(12*s)))
        preview_layout.setSpacing(max(8, int(10*s)))

        lbl_preview = QLabel("EDITOR DE DESENHO")
        lbl_preview.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(9, int(11*s))}pt; font-weight:bold; border:none;"
        )
        preview_layout.addWidget(lbl_preview)
        lbl_preview.setText("🎨 EDITOR DE DESENHO")

        lbl_preview_hint = QLabel("Prévia do desenho salvo na requisição.")
        lbl_preview_hint.setWordWrap(True)
        lbl_preview_hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9*s))}pt; border:none;"
        )
        preview_layout.addWidget(lbl_preview_hint)

        self.canvas_preview = CanvasPreview(s)
        preview_layout.addWidget(self.canvas_preview, 1)

        self.lbl_canvas_info = QLabel("Nenhum desenho salvo ainda.")
        self.lbl_canvas_info.setWordWrap(True)
        self.lbl_canvas_info.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9*s))}pt; border:none;"
        )
        preview_layout.addWidget(self.lbl_canvas_info)
        self.lbl_canvas_info.setText("🖼️ Nenhum desenho salvo ainda.")

        btn_canvas = QPushButton("✏️ Abrir Editor de Desenho")
        btn_canvas.setFixedHeight(max(28, int(32*s)))
        btn_canvas.setStyleSheet(theme.secondary_btn_style(s))
        btn_canvas.clicked.connect(self._open_canvas_dialog)
        self.btn_canvas = btn_canvas

        btn_canvas_view = QPushButton("🖼️ Visualizar Desenho")
        btn_canvas_view.setFixedHeight(max(28, int(32*s)))
        btn_canvas_view.setStyleSheet(theme.secondary_btn_style(s))
        btn_canvas_view.clicked.connect(self._open_canvas_viewer)
        self.btn_canvas_view = btn_canvas_view

        btn_canvas_row = QHBoxLayout()
        btn_canvas_row.setContentsMargins(0, 0, 0, 0)
        btn_canvas_row.setSpacing(max(8, int(10 * s)))
        btn_canvas_row.addWidget(btn_canvas, 1)
        btn_canvas_row.addWidget(btn_canvas_view, 1)
        preview_layout.addLayout(btn_canvas_row)

        row.addWidget(preview_card, 1)
        return wrapper

    # ── Rodapé: Observação + Assinatura + QR ─────────────────────────────────
    def _build_bottom_section(self) -> QFrame:
        s = self.scale
        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent; border:none;")
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(10,int(12*s)))

        # Observação
        obs_card = _make_card()
        obs_layout = QVBoxLayout(obs_card)
        obs_layout.setContentsMargins(max(10,int(12*s)), max(10,int(12*s)),
                                       max(10,int(12*s)), max(10,int(12*s)))
        obs_layout.addWidget(_field_label("📝 OBSERVAÇÃO", s))
        self.input_obs = QTextEdit()
        self.input_obs.setPlaceholderText("Observações adicionais...")
        self.input_obs.setMaximumHeight(max(100,int(120*s)))
        self.input_obs.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:6px;"
            f"font-size:{max(9,int(11*s))}pt; padding:6px; background:{theme.INPUT_BG};"
        )
        bind_uppercase_text_edit(self.input_obs)
        obs_layout.addWidget(self.input_obs)
        layout.addWidget(obs_card, 2)

        # Assinatura + QR
        sig_card = _make_card()
        sig_layout = QHBoxLayout(sig_card)
        sig_layout.setContentsMargins(max(10,int(12*s)), max(10,int(12*s)),
                                       max(10,int(12*s)), max(10,int(12*s)))

        sig_col = QVBoxLayout()
        sig_col.addWidget(_field_label("✍️ ASSINATURA DO CLIENTE", s))
        sig_col.addStretch()
        sig_line = QFrame()
        sig_line.setFrameShape(QFrame.Shape.HLine)
        sig_line.setStyleSheet(f"color:{theme.BORDER_COLOR};")
        sig_col.addWidget(sig_line)
        lbl_click = QLabel("Imprimir e assinar")
        lbl_click.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_click.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8,int(9*s))}pt; font-style:italic; border:none;"
        )
        sig_col.addWidget(lbl_click)
        sig_layout.addLayout(sig_col, 2)

        # QR Code
        qr_col = QVBoxLayout()
        qr_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(max(80,int(90*s)), max(80,int(90*s)))
        self.qr_label.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:4px; background:#fff;"
        )
        lbl_qr_txt = QLabel("QR CODE\nVendedor")
        lbl_qr_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_qr_txt.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7,int(8*s))}pt; border:none;"
        )
        lbl_qr_txt.setText("🔳 QR CODE\nVendedor")
        self.lbl_qr_contact = QLabel("")
        self.lbl_qr_contact.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_contact.setWordWrap(True)
        self.lbl_qr_contact.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7,int(8*s))}pt; border:none;"
        )
        qr_col.addWidget(self.qr_label)
        qr_col.addWidget(lbl_qr_txt)
        qr_col.addWidget(self.lbl_qr_contact)
        sig_layout.addLayout(qr_col, 1)

        layout.addWidget(sig_card, 1)
        self._generate_qr()
        return wrapper

    # ── QR Code ───────────────────────────────────────────────────────────────
    def _generate_qr(self):
        if hasattr(self, "lbl_qr_contact"):
            self.lbl_qr_contact.setText(_format_phone_text(session.whatsapp) or "Sem contato cadastrado")
        if not hasattr(self, "qr_label"):
            return
        self.qr_label.clear()
        if not HAS_QR or not session.whatsapp:
            return
        try:
            phone = self._normalize_whatsapp_number(session.whatsapp)
            if not phone:
                return
            url = f"https://wa.me/{phone}"
            qr = qrcode.make(url)
            buf = io.BytesIO()
            qr.save(buf, format="PNG")
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.read())
            size = max(80, int(90 * self.scale))
            pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            self.qr_label.setPixmap(pix)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._generate_qr()

    def refresh_logged_user(self):
        if hasattr(self, "lbl_vendor"):
            self.lbl_vendor.setText((session.user_name or "--").upper())
        self._generate_qr()

    # ── WhatsApp do cliente ───────────────────────────────────────────────────
    def _send_whatsapp_client(self):
        if not self.req_id:
            QMessageBox.warning(
                self,
                "WhatsApp",
                "Salve a requisição antes de enviar o PDF pelo WhatsApp.",
            )
            return

        self._set_whatsapp_busy(True)
        thread, worker = _run_in_thread(
            api.get_requisition,
            self.req_id,
            on_result=self._open_saved_pdf_for_whatsapp,
            on_error=self._on_whatsapp_error,
        )
        self._threads.append((thread, worker))

    def _set_whatsapp_busy(self, busy: bool):
        if not hasattr(self, "btn_whatsapp"):
            return

        self.btn_whatsapp.setEnabled(not busy)
        self.btn_whatsapp.setText("⏳ PREPARANDO PDF..." if busy else "📲 ENVIAR WHATSAPP")

    def _set_print_busy(self, busy: bool):
        if not hasattr(self, "btn_print"):
            return

        self.btn_print.setEnabled(not busy)
        self.btn_print.setText("PREPARANDO IMPRESSÃO..." if busy else "IMPRIMIR")

    def _update_print_button_visual(self) -> None:
        if not hasattr(self, "btn_print"):
            return

        icon = None
        for icon_name in ("SP_DialogPrintButton", "SP_PrinterIcon"):
            std_icon = getattr(QStyle.StandardPixmap, icon_name, None)
            if std_icon is None:
                continue
            candidate = self.style().standardIcon(std_icon)
            if not candidate.isNull():
                icon = candidate
                break

        if icon and not icon.isNull():
            side = max(16, int(18 * self.scale))
            self.btn_print.setIcon(icon)
            self.btn_print.setIconSize(QSize(side, side))

    def _print_requisition_pdf(self):
        self._set_print_busy(True)
        try:
            pdf_path = self._find_saved_pdf_for_print()
            self._print_pdf_file(pdf_path)
        except Exception as exc:
            QMessageBox.critical(self, "Impressão", str(exc))
        finally:
            self._set_print_busy(False)

    def _on_whatsapp_error(self, msg: str):
        self._set_whatsapp_busy(False)
        QMessageBox.critical(self, "WhatsApp", msg)

    def _open_saved_pdf_for_whatsapp(self, req: dict):
        try:
            digits = self._normalize_whatsapp_number(req.get("phone") or self.input_fone.text())
            if not digits:
                QMessageBox.warning(
                    self,
                    "WhatsApp",
                    "A requisição salva não possui um telefone válido para envio.",
                )
                return

            pdf_path = self._generate_saved_pdf(req)

            import os
            import webbrowser

            try:
                os.startfile(os.path.dirname(pdf_path))
            except Exception:
                pass

            webbrowser.open(f"https://wa.me/{digits}")
            QMessageBox.information(
                self,
                "WhatsApp",
                "O PDF salvo foi gerado e a conversa do cliente foi aberta.\n\n"
                f"Arquivo pronto:\n{pdf_path}\n\n"
                "O anexo ainda precisa ser enviado manualmente porque o projeto "
                "não tem uma integração configurada de envio de documentos pelo WhatsApp.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "WhatsApp", str(exc))
        finally:
            self._set_whatsapp_busy(False)

    def _normalize_whatsapp_number(self, raw: str | None) -> str:
        import re

        digits = re.sub(r"\D", "", (raw or "").strip())
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = "55" + digits
        return digits

    def _build_current_pdf_payload(self) -> tuple[dict, dict, str, str]:
        data = self.get_form_data()
        ped_number = (data.get("ped_number") or "").strip()
        client = self.client_search.get_selected()

        if not ped_number or not ped_number.isdigit() or int(ped_number) == 0:
            raise RuntimeError("Informe um número de PED válido antes de imprimir.")

        if not data.get("client_id") or not client:
            raise RuntimeError("Selecione um cliente antes de imprimir.")

        req = dict(data)
        if self.req_id:
            req["id"] = self.req_id
        req["client_name"] = client.get("name") or ""
        req["client_code"] = client.get("code") or ""
        req["vendor_name"] = session.user_name or ""
        req["vendor_whatsapp"] = session.whatsapp or ""
        req["emission_date"] = local_now().isoformat()

        client_payload = {
            "id": client.get("id"),
            "code": client.get("code") or "",
            "name": client.get("name") or "",
            "phone": self.input_fone.text().strip() or client.get("phone") or "",
            "cnpj": client.get("cnpj") or "",
        }
        obs = self.input_obs.toPlainText().strip()
        return req, client_payload, obs, self._canvas_json

    def _find_saved_pdf_for_print(self) -> str:
        ped_number = self.input_ped.text().strip()
        if not ped_number or not ped_number.isdigit() or int(ped_number) == 0:
            raise RuntimeError("Informe um número de requisição válido antes de imprimir.")

        req_hint = {
            "vendor_code": getattr(self, "_req_vendor_code", ""),
            "vendor_name": getattr(self, "_req_vendor_name", ""),
        }
        folder = self._resolve_pdf_output_folder(require_configured_folder=True, req=req_hint)
        if not os.path.isdir(folder):
            raise RuntimeError("A pasta de PDFs configurada não foi encontrada.")

        ped_file = ped_number.zfill(6)
        prefix = f"REQ-{ped_file}-"

        try:
            pdf_candidates = [
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if name.lower().endswith(".pdf") and name.upper().startswith(prefix.upper())
            ]
        except OSError as exc:
            raise RuntimeError(f"Não foi possível acessar a pasta de PDFs.\n\n{exc}") from exc

        if not pdf_candidates:
            raise RuntimeError(
                "Não foi encontrado um PDF salvo para essa requisição na pasta configurada.\n\n"
                f"Requisição: {ped_file}"
            )

        pdf_candidates.sort(
            key=lambda path: (os.path.getmtime(path), os.path.basename(path).lower()),
            reverse=True,
        )
        return pdf_candidates[0]

    def _resolve_pdf_output_folder(
        self,
        require_configured_folder: bool = True,
        req: dict | None = None,
    ) -> str:
        from ..core.pdf_folders import vendor_subfolder as _vendor_subfolder
        base = res.pdf_folder.strip()
        if base:
            subfolder = _vendor_subfolder(
                session.user_code,
                session.user_name,
                session.role,
                str((req or {}).get("vendor_code") or ""),
                str((req or {}).get("vendor_name") or ""),
            )
            return os.path.join(base, subfolder)

        if require_configured_folder:
            raise RuntimeError(
                "Defina a pasta de PDFs nas Configurações antes de localizar ou gerar o PDF da requisição."
            )

        folder = os.path.join(tempfile.gettempdir(), "requisicoes-pdf")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _generate_pdf_file(
        self,
        req: dict,
        client: dict | None,
        obs: str,
        canvas_json: str,
        *,
        require_configured_folder: bool,
    ) -> str:
        try:
            from ..services.pdf_generator import generate_pdf, HAS_REPORTLAB
        except ImportError as exc:
            raise RuntimeError("A geração de PDF não está disponível neste ambiente.") from exc

        if not HAS_REPORTLAB:
            raise RuntimeError("A geração de PDF está indisponível porque o ReportLab não está instalado.")

        folder = self._resolve_pdf_output_folder(require_configured_folder=require_configured_folder, req=req)
        return generate_pdf(req, client, obs or req.get("obs") or "", folder, canvas_json)

    def _generate_saved_pdf(self, req: dict) -> str:
        client = {
            "code": req.get("client_code") or "",
            "name": req.get("client_name") or "",
            "phone": req.get("phone") or "",
        }
        canvas_json = (req.get("canvas") or {}).get("json_data") or "{}"
        return self._generate_pdf_file(
            req,
            client,
            req.get("obs") or "",
            canvas_json,
            require_configured_folder=True,
        )

    def _generate_current_pdf(self) -> str:
        req, client, obs, canvas_json = self._build_current_pdf_payload()
        return self._generate_pdf_file(
            req,
            client,
            obs,
            canvas_json,
            require_configured_folder=False,
        )

    def _prepare_local_pdf_for_print(self, pdf_path: str) -> str:
        if not os.path.isfile(pdf_path):
            raise RuntimeError("O PDF da requisição não foi encontrado para impressão.")

        temp_dir = os.path.join(tempfile.gettempdir(), "requisicoes-print")
        os.makedirs(temp_dir, exist_ok=True)

        ped_number = self.input_ped.text().strip() or "000000"
        fd, local_pdf_path = tempfile.mkstemp(
            prefix=f"req-{ped_number.zfill(6)}-",
            suffix=".pdf",
            dir=temp_dir,
        )
        os.close(fd)

        try:
            shutil.copyfile(pdf_path, local_pdf_path)
        except OSError as exc:
            try:
                os.remove(local_pdf_path)
            except OSError:
                pass
            raise RuntimeError(
                "Não foi possível preparar uma cópia local do PDF para impressão.\n\n"
                f"{exc}"
            ) from exc

        return local_pdf_path

    def _print_pdf_file(self, pdf_path: str) -> bool:
        try:
            from PySide6.QtCore import QRect, QSize
            from PySide6.QtGui import QPageLayout, QPainter
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError as exc:
            raise RuntimeError("A seleção de impressora não está disponível neste ambiente.") from exc

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(f"Requisicao {self.input_ped.text().strip() or '000000'}")
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
        printer.setFullPage(True)

        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Imprimir requisição")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        if printer.outputFormat() == QPrinter.OutputFormat.NativeFormat:
            printer.setOutputFileName("")

        local_pdf_path = self._prepare_local_pdf_for_print(pdf_path)
        document = QPdfDocument(self)
        painter = QPainter()
        try:
            load_result = document.load(local_pdf_path)
            if load_result != QPdfDocument.Error.None_:
                raise RuntimeError(
                    f"Não foi possível abrir o PDF da requisição para impressão ({load_result.name})."
                )
            if document.pageCount() <= 0:
                raise RuntimeError("O PDF da requisição não possui páginas para imprimir.")

            if not painter.begin(printer):
                raise RuntimeError("Não foi possível iniciar a impressão na impressora selecionada.")

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            for page_index in range(document.pageCount()):
                if page_index:
                    printer.newPage()

                page_size = document.pagePointSize(page_index)
                target_rect = printer.paperRect(QPrinter.Unit.DevicePixel)
                if target_rect.width() <= 0 or target_rect.height() <= 0:
                    target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                target_x = int(round(target_rect.x()))
                target_y = int(round(target_rect.y()))
                target_width = max(1, int(round(target_rect.width())))
                target_height = max(1, int(round(target_rect.height())))
                painter.fillRect(QRect(target_x, target_y, target_width, target_height), Qt.GlobalColor.white)

                width = max(1, int((page_size.width() / 72.0) * 300))
                height = max(1, int((page_size.height() / 72.0) * 300))
                image = document.render(page_index, QSize(width, height))
                if image.isNull():
                    raise RuntimeError(f"Não foi possível renderizar a página {page_index + 1} para impressão.")

                scaled_size = image.size()
                scaled_size.scale(target_width, target_height, Qt.AspectRatioMode.KeepAspectRatio)
                x = target_x + max(0, (target_width - scaled_size.width()) // 2)
                y = target_y + max(0, (target_height - scaled_size.height()) // 2)
                painter.drawImage(QRect(x, y, scaled_size.width(), scaled_size.height()), image)
        finally:
            if painter.isActive():
                painter.end()
            if hasattr(document, "close"):
                document.close()
            try:
                os.remove(local_pdf_path)
            except OSError:
                pass

        return True

    # ── Calculadora de Peso ───────────────────────────────────────────────────
    def _open_weight_calculator(self):
        s = self.scale
        dlg = QDialog(self)
        dlg.setWindowTitle("Calculadora de Peso")
        dlg.setModal(True)
        dlg.setMinimumWidth(max(340, int(380 * s)))
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        dlg.setStyleSheet(
            f"QDialog {{"
            f"  background-color:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"  border-radius:8px;"
            f"}}"
            f"QDialog QWidget {{ background-color:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ color:{theme.TEXT_DARK}; background-color:transparent; border:none; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(max(20, int(24 * s)), max(20, int(24 * s)),
                                   max(20, int(24 * s)), max(20, int(24 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        # Título
        lbl_title = QLabel("⚖️  Calculadora de Peso")
        lbl_title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(11, int(13 * s))}pt; font-weight:bold;"
        )
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{theme.BORDER_COLOR};")
        layout.addWidget(sep)

        # Campos de entrada
        grid = QGridLayout()
        grid.setSpacing(max(8, int(10 * s)))
        grid.setColumnStretch(1, 1)

        fs = max(9, int(10 * s))
        lbl_style = f"font-size:{fs}pt; font-weight:bold; color:{theme.TEXT_MEDIUM};"

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(lbl_style)
            return l

        def _input(placeholder="", default=""):
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setText(default)
            inp.setFixedHeight(max(30, int(36 * s)))
            inp.setStyleSheet(theme.input_style(s))
            validator = QRegularExpressionValidator(
                QRegularExpression(r"[0-9]*\.?[0-9]*")
            )
            inp.setValidator(validator)
            return inp

        inp_qnt   = _input("ex: 10", "")
        inp_comp  = _input("mm", "")
        inp_larg  = _input("mm", "")
        inp_chapa = _input("mm", "")
        inp_var   = _input("constante", "7.865")
        inp_var.setReadOnly(True)
        inp_var.setStyleSheet(
            inp_var.styleSheet() +
            f"background-color:{theme.SURFACE_SOFT}; color:{theme.TEXT_MEDIUM};"
        )

        grid.addWidget(_lbl("QNT:"),          0, 0)
        grid.addWidget(inp_qnt,               0, 1)
        grid.addWidget(_lbl("COMP (mm):"),    1, 0)
        grid.addWidget(inp_comp,              1, 1)
        grid.addWidget(_lbl("LARG. TOTAL (mm):"), 2, 0)
        grid.addWidget(inp_larg,              2, 1)
        grid.addWidget(_lbl("CHAPA (mm):"),   3, 0)
        grid.addWidget(inp_chapa,             3, 1)
        grid.addWidget(_lbl("VARIÁVEL:"),     4, 0)
        grid.addWidget(inp_var,               4, 1)
        layout.addLayout(grid)

        # Separador resultado
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{theme.BORDER_COLOR};")
        layout.addWidget(sep2)

        # Label de resultado
        lbl_result = QLabel("PESO = —")
        lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_result.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(14, int(16 * s))}pt;"
            f"font-weight:bold; padding:{max(8, int(10 * s))}px;"
            f"background-color:{theme.INPUT_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:8px;"
        )
        layout.addWidget(lbl_result)

        lbl_hint = QLabel("Resultado apenas para consulta — não salvo na requisição.")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8 * s))}pt; font-style:italic;"
        )
        layout.addWidget(lbl_hint)

        # Botão fechar
        btn_fechar = QPushButton("Fechar")
        btn_fechar.setFixedHeight(max(34, int(40 * s)))
        btn_fechar.setStyleSheet(theme.secondary_btn_style(s))
        btn_fechar.clicked.connect(dlg.accept)
        layout.addWidget(btn_fechar, alignment=Qt.AlignmentFlag.AlignRight)

        # Lógica de cálculo — recalcula a cada digitação
        def _recalculate():
            try:
                qnt   = float(inp_qnt.text().replace(",", ".") or "0")
                comp  = float(inp_comp.text().replace(",", ".") or "0")
                larg  = float(inp_larg.text().replace(",", ".") or "0")
                chapa = float(inp_chapa.text().replace(",", ".") or "0")
                var   = float(inp_var.text().replace(",", ".") or "7.865")
                peso  = (qnt * comp * larg * chapa * var) / 1_000_000
                txt   = f"{peso:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
                lbl_result.setText(f"PESO = {txt} kg")
            except (ValueError, ZeroDivisionError):
                lbl_result.setText("PESO = —")

        inp_qnt.textChanged.connect(_recalculate)
        inp_comp.textChanged.connect(_recalculate)
        inp_larg.textChanged.connect(_recalculate)
        inp_chapa.textChanged.connect(_recalculate)
        # inp_var é fixo — sem listener necessário

        dlg.exec()

    def _send_to_production(self):
        if not self.req_id:
            QMessageBox.warning(
                self,
                "Produção",
                "Salve a requisição antes de enviar para produção.",
            )
            return

        if not (self.chk_retirada.isChecked() or self.chk_entrega.isChecked()):
            QMessageBox.warning(
                self,
                "Produção",
                "Marque Retirada ou Entrega para enviar para produção.",
            )
            return

        invoice_action = self._confirm_invoice_before_send()
        if invoice_action == "cancel":
            return
        if invoice_action == "save":
            self.save_requested.emit()
            return

        destination = self._pick_production_destination()
        if not destination:
            return

        previous_status = getattr(self.status_badge, "_status", "em_andamento")
        self.status_badge.set_status("aguardando_recebimento")

        thread, worker = _run_in_thread(
            api.update_status,
            self.req_id,
            "aguardando_recebimento",
            _build_production_note(PROD_SEND, destination),
            on_result=lambda req, dest=destination: self._on_sent_to_production(req, dest),
            on_error=lambda msg, prev=previous_status: self._on_send_to_production_error(msg, prev),
        )
        self._threads.append((thread, worker))

    def _confirm_invoice_before_send(self) -> str:
        ped_number = (self.input_ped.text() or "").strip() or "sem PED"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Este pedido foi faturado")
        box.setText(f"Este pedido foi faturado ({ped_number})?")
        box.setTextFormat(Qt.TextFormat.PlainText)

        btn_yes = box.addButton("Sim", QMessageBox.ButtonRole.YesRole)
        btn_save = box.addButton("Apenas salvar", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

        box.setDefaultButton(btn_yes)
        box.setEscapeButton(btn_cancel)
        apply_message_box_theme(box)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_yes:
            return "yes"
        if clicked == btn_save:
            return "save"
        return "cancel"

    def _pick_production_destination(self) -> str | None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Enviar para produção")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText("Para qual produção deseja enviar a requisição?")

        btn_ar = msg.addButton("A&&R", QMessageBox.ButtonRole.AcceptRole)
        btn_pinheiro = msg.addButton("Pinheiro Indústria", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(msg)

        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_ar:
            return "A&R"
        if clicked == btn_pinheiro:
            return "Pinheiro Indústria"
        return None

    def _on_sent_to_production(self, req: dict, destination: str):
        self.status_badge.set_status(req.get("status", "aguardando_recebimento"))
        QMessageBox.information(
            self,
            "Produção",
            f"Requisição enviada para {destination}.",
        )

    def _on_send_to_production_error(self, msg: str, previous_status: str = "em_andamento"):
        self.status_badge.set_status(previous_status)
        friendly = msg
        if "aguardando_recebimento" in msg and "Input should be" in msg:
            friendly = (
                "O servidor ainda não reconhece o novo status de produção.\n\n"
                "Reinicie o servidor da API e tente novamente."
            )
        QMessageBox.critical(self, "Produção", friendly)

    # ── Editor de desenho (modal) ─────────────────────────────────────────────
    def _open_canvas_dialog(self):
        dlg = CanvasDialog(self._canvas_json, self.scale, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._canvas_json = dlg.get_json()
            self._update_canvas_preview()

    def _open_canvas_viewer(self):
        dlg = CanvasViewerDialog(self._canvas_json, self.scale, self)
        dlg.exec()

    # ── Clientes ──────────────────────────────────────────────────────────────
    def _load_clients(self):
        t, w = _run_in_thread(api.list_clients,
                               on_result=self._on_clients_loaded,
                               on_error=lambda e: None)
        self._threads.append((t, w))

    def _on_clients_loaded(self, clients: list):
        self._clients = clients
        self.client_search.set_clients(clients)

    def _on_client_selected(self, client: dict):
        """Preenche Fone e Endereço automaticamente ao selecionar um cliente."""
        if not client:
            return
        self._set_phone_text(client.get("phone") or "")
        addr_parts = [
            client.get("address") or "",
            client.get("city") or "",
            client.get("state") or "",
        ]
        self.input_address.setText(", ".join(p for p in addr_parts if p))

    def _on_phone_edited(self, text: str):
        self._set_phone_text(text)

    def _set_phone_text(self, raw: str):
        formatted = _format_phone_text(raw)
        if self.input_fone.text() == formatted:
            return
        self.input_fone.blockSignals(True)
        self.input_fone.setText(formatted)
        self.input_fone.setCursorPosition(len(formatted))
        self.input_fone.blockSignals(False)

    # ── Eventos ───────────────────────────────────────────────────────────────
    def _lookup_product_by_code(self, row: int, code: str):
        lookup_code = code.strip()
        if not lookup_code:
            return

        t, w = _run_in_thread(
            api.list_products, "", lookup_code, 1,
            on_result=lambda products, r=row, c=lookup_code: self._apply_product_lookup(r, c, products),
            on_error=lambda _: None,
        )
        self._threads.append((t, w))

    def _apply_product_lookup(self, row: int, requested_code: str, products: list):
        if self.item_table.get_product_code(row).strip() != requested_code:
            return
        if products:
            self.item_table.apply_product_lookup(row, products[0])

    def _update_canvas_preview(self):
        if not hasattr(self, "canvas_preview"):
            return

        self.canvas_preview.set_json(self._canvas_json)
        result = self.canvas_preview.last_result
        pdf_path = result.get("pdf") or ""

        if result.get("items"):
            self.lbl_canvas_info.setText("Prévia atual do desenho técnico.")
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        else:
            self.lbl_canvas_info.setText("Nenhum desenho salvo ainda.")
        if result.get("items"):
            self.lbl_canvas_info.setText("◉ Prévia atual do desenho técnico.")
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"▤ Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        else:
            self.lbl_canvas_info.setText("◌ Nenhum desenho salvo ainda.")

        if result.get("items"):
            self.lbl_canvas_info.setText("🎨 Prévia atual do desenho técnico.")
        elif pdf_path:
            self.lbl_canvas_info.setText(
                f"📎 Referência em PDF anexada: {os.path.basename(pdf_path)}"
            )
        else:
            self.lbl_canvas_info.setText("🖼️ Nenhum desenho salvo ainda.")

    def _set_form_locked(self, locked: bool, message: str = ""):
        for widget in getattr(self, "_editable_widgets", []):
            widget.setEnabled(not locked)

        if hasattr(self, "btn_whatsapp"):
            self.btn_whatsapp.setEnabled(True)
        if hasattr(self, "btn_canvas_view"):
            self.btn_canvas_view.setEnabled(True)

        if hasattr(self, "lock_label"):
            self.lock_label.setVisible(locked)
            self.lock_label.setText(message if locked else "")

    def has_unsaved_data(self) -> bool:
        if self.req_id is not None:
            return True
        if self.input_ped.text().strip():
            return True
        if self.input_obra.text().strip():
            return True
        if self.input_fone.text().strip():
            return True
        if self.input_address.text().strip():
            return True
        if self.input_obs.toPlainText().strip():
            return True
        if self.client_search.get_client_id() is not None:
            return True
        if self.input_prazo.date() != QDate.currentDate():
            return True
        if self.chk_retirada.isChecked() or self.chk_entrega.isChecked():
            return True
        if self.item_table.get_items():
            return True
        return self._canvas_json not in ("", "{}")

    # ── API pública ──────────────────────────────────────────────────────────
    def get_form_data(self) -> dict:
        client_id = self.client_search.get_client_id()
        prazo = self.input_prazo.date().toString("yyyy-MM-dd")
        total_weight = self.item_table.get_total_weight()
        return {
            "ped_number":       self.input_ped.text().strip(),
            "client_id":        client_id,
            "obra":             self.input_obra.text().strip() or None,
            "delivery_date":    prazo,
            "retirada":         self.chk_retirada.isChecked(),
            "entrega":          self.chk_entrega.isChecked(),
            "phone":            self.input_fone.text().strip() or None,
            "delivery_address": self.input_address.text().strip() or None,
            "weight":           total_weight,
            "items":            self.item_table.get_items(),
            "obs":              self.input_obs.toPlainText().strip() or None,
        }

    def load_requisition(self, data: dict, read_only: bool = False):
        """Popula o formulário com dados de uma requisição existente."""
        self._set_form_locked(False)
        self.req_id = data.get("id")
        # Guarda info do vendedor para uso em _find_saved_pdf_for_print
        self._req_vendor_code = str(data.get("vendor_code") or "")
        self._req_vendor_name = str(data.get("vendor_name") or "")
        self.input_ped.setText(str(data.get("ped_number") or ""))
        self.input_obra.setText(data.get("obra") or "")
        self._set_phone_text(data.get("phone") or "")
        self.input_address.setText(data.get("delivery_address") or "")

        # Requisição existente: libera a data mínima para exibir o prazo salvo,
        # mesmo que seja anterior ao mínimo vigente.
        self.input_prazo.setMinimumDate(QDate(2000, 1, 1))
        self.input_prazo.setToolTip("")
        delivery = data.get("delivery_date")
        if delivery:
            qd = QDate.fromString(str(delivery)[:10], "yyyy-MM-dd")
            self.input_prazo.setDate(qd)

        self.chk_retirada.setChecked(data.get("retirada", False))
        self.chk_entrega.setChecked(data.get("entrega", False))
        self.status_badge.set_status(data.get("status", "em_andamento"))
        self.lbl_ped_num.setText(f"#{str(data.get('ped_number','0')).zfill(6)}")

        # Cliente
        client_id = data.get("client_id")
        if client_id:
            self.client_search.set_client_by_id(client_id)

        # Itens
        self.item_table.set_items(data.get("items", []))
        self.input_obs.setPlainText(data.get("obs") or "")

        # Canvas — armazena JSON; será carregado no dialog ao abrir
        canvas_data = data.get("canvas")
        self._canvas_json = (canvas_data or {}).get("json_data") or "{}"
        self._update_canvas_preview()

        if read_only:
            self._set_form_locked(
                True,
                "Requisicao aberta em modo somente leitura para este perfil.",
            )
        elif data.get("finalized_at"):
            self._set_form_locked(
                True,
                "🏭 Produção recebida ou finalizada. Esta requisição não pode mais ser editada.",
            )

    def reset(self):
        """Limpa o formulário para nova requisição."""
        self._set_form_locked(False)
        self.req_id = None
        self.input_ped.clear()
        self.input_obra.clear()
        self.input_fone.clear()
        self.input_address.clear()
        self.input_obs.clear()
        self.input_prazo.setDate(QDate.currentDate())
        self._apply_min_delivery_constraint()
        self.chk_retirada.setChecked(False)
        self.chk_entrega.setChecked(False)
        self.client_search.clear()
        self.status_badge.set_status("em_andamento")
        self.lbl_ped_num.setText("#000000")
        self.item_table.set_items([])
        self._canvas_json = "{}"
        self._update_canvas_preview()

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self._page_scroll.setStyleSheet(f"QScrollArea {{ background:{bg}; border:none; }}")
        self._page_content.setStyleSheet(f"background:{bg};")
        self.input_ped.setStyleSheet(
            f"font-size:{max(14,int(18*s))}pt; font-weight:bold; color:{theme.PRIMARY};"
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:5px; padding:2px 6px;"
            f"background:{theme.INPUT_BG};"
        )
        self.input_obs.setStyleSheet(
            f"border:1px solid {theme.BORDER_COLOR}; border-radius:6px;"
            f"font-size:{max(9,int(11*s))}pt; padding:6px; background:{theme.INPUT_BG};"
        )
        self.input_obra.setStyleSheet(theme.input_style(s))
        self.input_prazo.setStyleSheet(theme.input_style(s))
        self.input_fone.setStyleSheet(theme.input_style(s))
        self.input_address.setStyleSheet(theme.input_style(s))
        chk_style = f"color:{theme.TEXT_DARK}; font-size:{max(9,int(11*s))}pt; border:none;"
        self.chk_retirada.setStyleSheet(chk_style)
        self.chk_entrega.setStyleSheet(chk_style)
        self.client_search.apply_theme(s)
        self.item_table.apply_theme()
        self.btn_calc.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        self.btn_production.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        self.btn_whatsapp.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        self.btn_print.setStyleSheet(_emphasized_btn_style(theme.secondary_btn_style(s)))
        self._update_print_button_visual()
        self.btn_save.setStyleSheet(_emphasized_btn_style(theme.primary_btn_style(s)))
        self.btn_canvas.setStyleSheet(theme.secondary_btn_style(s))
        self.btn_canvas_view.setStyleSheet(theme.secondary_btn_style(s))
