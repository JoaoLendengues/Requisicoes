"""
Formulário principal de requisição — fiel ao mockup fornecido.
"""
import os
import io
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QCheckBox,
    QFrame, QSplitter, QTextEdit, QFileDialog, QMessageBox, QDialog,
    QGraphicsDropShadowEffect, QSizePolicy,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QDate, Signal, QThread, QObject, QEvent, QTimer, QRegularExpression
from PySide6.QtGui import QPixmap, QColor, QFont, QRegularExpressionValidator

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

from ..core import theme
from ..core.resolution import res
from ..core.session import session
from ..api import client as api
from ..widgets.status_badge import StatusBadge
from ..widgets.item_table import ItemTable
from ..widgets.canvas_widget import DrawingCanvas, CanvasPreview

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


# ── Card helper ───────────────────────────────────────────────────────────────
def _make_card(parent=None) -> QFrame:
    card = QFrame(parent)
    card.setStyleSheet(
        f"QFrame {{ background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
        f"border-radius:8px; }}"
    )
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(10)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    card.setGraphicsEffect(shadow)
    return card


def _field_label(text: str, scale: float) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8*scale))}pt; "
        f"font-weight:bold; text-transform:uppercase; border:none;"
    )
    return lbl


def _value_label(text: str = "—", scale: float = 1.0) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.TEXT_DARK}; font-size:{max(9, int(11*scale))}pt; "
        f"font-weight:bold; border:none;"
    )
    return lbl


# ── Campo de busca de cliente ─────────────────────────────────────────────────
class ClientSearchBox(QWidget):
    """
    Caixa de busca com dropdown em tempo real — filtragem no SERVIDOR.
    Suporta 100k+ clientes. Debounce de 300 ms para não sobrecarregar a API.
    Pesquisa por nome, código ou CPF/CNPJ (ignora pontuação).
    """
    client_selected = Signal(object)   # dict do cliente ou None

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._selected: dict | None = None
        self._threads: list = []

        # Timer de debounce — dispara busca 300 ms após parar de digitar
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._do_search)

        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Buscar por nome, código ou CPF/CNPJ...")
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

    # ── Digitação → debounce → busca no servidor ──────────────────────────────
    def _on_text(self, text: str):
        if self._selected:
            expected = f"{self._selected['code']} — {self._selected['name']}"
            if text == expected:
                return
            self._selected = None

        if len(text.strip()) < 2:
            self._debounce.stop()
            self._drop.hide()
            return

        self._debounce.start()

    def _do_search(self):
        term = self.input.text().strip()
        if len(term) < 2:
            return

        # Feedback visual imediato
        self._drop.clear()
        loading = QListWidgetItem("  ⌕ Buscando...")
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        self._drop.addItem(loading)
        self._reposition()
        self._drop.show()

        t, w = _run_in_thread(
            api.list_clients, term,
            on_result=self._on_results,
            on_error=lambda _: self._drop.hide(),
        )
        self._threads.append((t, w))

    def _on_results(self, clients: list):
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
        rows = min(max(self._drop.count(), 1), 8)
        row_h = max(30, int(34 * s))
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

    # ── Navegação por teclado ─────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if obj is self.input:
                if key == Qt.Key.Key_Escape:
                    self._drop.hide()
                    return True
                if key == Qt.Key.Key_Down and self._drop.isVisible():
                    if self._drop.count():
                        self._drop.setFocus()
                        self._drop.setCurrentRow(0)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self._drop.isVisible() and self._drop.count():
                        self._pick(self._drop.item(0))
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
        self._threads.append((t, w))

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


# ── Dialog do editor de desenho ───────────────────────────────────────────────
class CanvasDialog(QDialog):
    """Janela modal com o editor de desenho técnico."""

    def __init__(self, json_data: str, scale: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editor de Desenho")
        self.setModal(True)
        self.setStyleSheet(f"background:{theme.CONTENT_BG};")

        # Tamanho: 90% da tela disponível
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.90), int(screen.height() * 0.88))

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


# ── View principal ────────────────────────────────────────────────────────────
class RequisitionForm(QWidget):
    saved           = Signal(dict)
    save_requested  = Signal()          # emitido pelo botão Salvar do formulário
    req_id: int | None = None

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._clients: list[dict] = []
        self._threads: list = []
        self._canvas_json: str = "{}"   # armazena o JSON do desenho
        self._setup_ui()
        self._load_clients()
        self._update_canvas_preview()

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}"
        )
        root.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet(f"background:{theme.CONTENT_BG};")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
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
        btn_calc.setStyleSheet(theme.secondary_btn_style(s))
        btn_calc.clicked.connect(self._open_weight_calculator)
        save_row.addWidget(btn_calc)
        self.btn_calc = btn_calc

        save_row.addSpacing(max(8, int(10 * s)))

        btn_production = QPushButton("ENVIAR PARA PRODUÇÃO")
        btn_production.setFixedHeight(max(42, int(48 * s)))
        btn_production.setMinimumWidth(max(220, int(250 * s)))
        btn_production.setStyleSheet(theme.secondary_btn_style(s))
        btn_production.clicked.connect(self._send_to_production)
        save_row.addWidget(btn_production)
        self.btn_production = btn_production
        self.btn_production.setText("🏭 ENVIAR PARA PRODUÇÃO")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_whatsapp = QPushButton("ENVIAR WHATSAPP")
        btn_whatsapp.setFixedHeight(max(42, int(48 * s)))
        btn_whatsapp.setMinimumWidth(max(180, int(210 * s)))
        btn_whatsapp.setStyleSheet(theme.secondary_btn_style(s))
        btn_whatsapp.clicked.connect(self._send_whatsapp_client)
        save_row.addWidget(btn_whatsapp)
        self.btn_whatsapp = btn_whatsapp
        self.btn_whatsapp.setText("📲 ENVIAR WHATSAPP")

        save_row.addSpacing(max(8, int(10 * s)))

        btn_save = QPushButton("SALVAR REQUISIÇÃO")
        btn_save.setFixedHeight(max(42, int(48 * s)))
        btn_save.setMinimumWidth(max(220, int(260 * s)))
        btn_save.setStyleSheet(theme.primary_btn_style(s))
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
        lbl_req.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8,int(9*s))}pt; font-weight:bold; border:none;"
        )
        self.lbl_ped_num = QLabel("#000000")
        self.lbl_ped_num.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(16,int(20*s))}pt; font-weight:bold; border:none;"
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
        self.input_ped.setFixedWidth(max(80, int(100*s)))
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
        self.input_ped.textChanged.connect(
            lambda t: self.lbl_ped_num.setText(f"#{t.zfill(6)}" if t else "#000000")
        )
        ped_col.addWidget(self.input_ped)
        layout.addLayout(ped_col)

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
        layout.addWidget(self.input_obra, 1, 1)

        # Fone
        layout.addWidget(_field_label("📞 FONE", s), 2, 0)
        self.input_fone = QLineEdit()
        self.input_fone.setPlaceholderText("(61) 9 9999-9999")
        self.input_fone.setFixedHeight(max(30,int(36*s)))
        self.input_fone.setStyleSheet(theme.input_style(s))
        layout.addWidget(self.input_fone, 3, 0)

        # Endereço
        layout.addWidget(_field_label("📍 ENDEREÇO A ENTREGAR", s), 2, 1)
        self.input_address = QLineEdit()
        self.input_address.setPlaceholderText("Endereço completo de entrega")
        self.input_address.setFixedHeight(max(30,int(36*s)))
        self.input_address.setStyleSheet(theme.input_style(s))
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
            f"color:{theme.TEXT_DARK}; font-size:{max(9, int(11*s))}pt; font-weight:bold; border:none;"
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
        btn_canvas.setFixedHeight(max(30, int(34*s)))
        btn_canvas.setStyleSheet(theme.secondary_btn_style(s))
        btn_canvas.clicked.connect(self._open_canvas_dialog)
        preview_layout.addWidget(btn_canvas)
        self.btn_canvas = btn_canvas

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
        qr_col.addWidget(self.qr_label)
        qr_col.addWidget(lbl_qr_txt)
        sig_layout.addLayout(qr_col, 1)

        layout.addWidget(sig_card, 1)
        self._generate_qr()
        return wrapper

    # ── QR Code ───────────────────────────────────────────────────────────────
    def _generate_qr(self):
        if not HAS_QR or not session.whatsapp:
            return
        try:
            phone = "".join(filter(str.isdigit, session.whatsapp))
            url = f"https://wa.me/55{phone}"
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

    def _generate_saved_pdf(self, req: dict) -> str:
        folder = res.pdf_folder.strip()
        if not folder:
            raise RuntimeError(
                "Defina a pasta de PDFs nas Configurações antes de enviar a requisição pelo WhatsApp."
            )

        try:
            from ..services.pdf_generator import generate_pdf, HAS_REPORTLAB
        except ImportError as exc:
            raise RuntimeError("A geração de PDF não está disponível neste ambiente.") from exc

        if not HAS_REPORTLAB:
            raise RuntimeError("A geração de PDF está indisponível porque o ReportLab não está instalado.")

        client = {
            "code": req.get("client_code") or "",
            "name": req.get("client_name") or "",
            "phone": req.get("phone") or "",
        }
        canvas_json = (req.get("canvas") or {}).get("json_data") or "{}"
        return generate_pdf(req, client, req.get("obs") or "", folder, canvas_json)

    # ── Calculadora de Peso ───────────────────────────────────────────────────
    def _open_weight_calculator(self):
        s = self.scale
        dlg = QDialog(self)
        dlg.setWindowTitle("Calculadora de Peso")
        dlg.setModal(True)
        dlg.setMinimumWidth(max(340, int(380 * s)))

        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; }}"
            f"QLabel {{ color:{theme.TEXT_DARK}; border:none; }}"
            f"QLineEdit {{ {theme.input_style(s)} }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(max(20, int(24 * s)), max(20, int(24 * s)),
                                   max(20, int(24 * s)), max(20, int(24 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        # Título
        lbl_title = QLabel("⚖️  Calculadora de Peso")
        lbl_title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(11, int(13 * s))}pt; font-weight:bold;"
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
            f"background:{theme.TABLE_HEADER_BG}; color:#94A3B8;"
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
            f"background:{theme.INPUT_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:6px;"
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
                txt   = f"{peso:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
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

    def _pick_production_destination(self) -> str | None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Enviar para produção")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText("Selecione para qual produção a requisição deve ser enviada.")

        btn_ar = msg.addButton("A&&R", QMessageBox.ButtonRole.AcceptRole)
        btn_pinheiro = msg.addButton("Pinheiro Indústria", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)

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
        self.input_fone.setText(client.get("phone") or "")
        addr_parts = [
            client.get("address") or "",
            client.get("city") or "",
            client.get("state") or "",
        ]
        self.input_address.setText(", ".join(p for p in addr_parts if p))

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

    def load_requisition(self, data: dict):
        """Popula o formulário com dados de uma requisição existente."""
        self._set_form_locked(False)
        self.req_id = data.get("id")
        self.input_ped.setText(str(data.get("ped_number") or ""))
        self.input_obra.setText(data.get("obra") or "")
        self.input_fone.setText(data.get("phone") or "")
        self.input_address.setText(data.get("delivery_address") or "")

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

        if data.get("finalized_at"):
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
        self.chk_retirada.setChecked(False)
        self.chk_entrega.setChecked(False)
        self.client_search.clear()
        self.status_badge.set_status("em_andamento")
        self.lbl_ped_num.setText("#000000")
        self.item_table.set_items([])
        self._canvas_json = "{}"
        self._update_canvas_preview()
