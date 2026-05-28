from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)
from ..core.dialogs import apply_message_box_theme, ask_confirmation
from ..core.session import session


WAITING_RECEIPT_STAGE = "waiting_receipt"
WAITING_QUEUE_STAGE = "waiting_queue"

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_QUEUED = "FILA"
PROD_STARTED = "INICIADA"
PROD_RETURNED_QUEUE = "DEVOLVIDA_FILA"
PROD_FINISHED = "FINALIZADA"
PROD_CANCELED = "CANCELADA"

MACHINE_STATUS_OPTIONS = (
    ("funcionando", "Funcionando"),
    ("manutencao", "Manutenção"),
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"


def _destination_card_meta_dict() -> dict:
    return {
        "A&R": {
            "title": "A&R",
            "helper": "Fluxo operacional da produção da A&R.",
            "accent": theme.PRIMARY_HOVER,
            "icon": "producao_ar.png",
        },
        "Pinheiro Indústria": {
            "title": "Pinheiro Indústria",
            "helper": "Fluxo operacional da Pinheiro Indústria.",
            "accent": theme.PRIMARY,
            "icon": "producao_pinheiro_industria.png",
        },
    }


def _normalize_destination(destination: str) -> str:
    text = (destination or "").strip()
    folded = text.casefold()
    if folded == "a&r":
        return "A&R"
    if "pinheiro" in folded and "ind" in folded:
        return "Pinheiro Indústria"
    return text


def _destination_card_meta(destination: str) -> dict | None:
    return _destination_card_meta_dict().get(_normalize_destination(destination))


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.TEXT_DARK)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


def _make_card(
    scale: float,
    background: str | None = None,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    card = QFrame()
    card.setObjectName("productionCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#productionCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
        f"  border:1px solid {theme.BORDER_COLOR}; outline:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{_rgba(theme.PRIMARY, 70)}; }}"
        f"QPushButton:pressed {{ background:{theme.SELECTION_BG}; }}"
        f"QPushButton:disabled {{ background:#E5EAF2; color:#97A3B6; border-color:#E5EAF2; }}"
    )


def _primary_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.PRIMARY}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background:{theme.SIDEBAR_BG}; }}"
        f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
    )


def _danger_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.DANGER}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:#B91C1C; }}"
        f"QPushButton:pressed {{ background:#991B1B; }}"
        f"QPushButton:disabled {{ background:#F0B4B4; color:#FFF7F7; }}"
    )


def _machine_combo_style(scale: float) -> str:
    fs = max(8, int(9 * scale))
    return (
        f"QComboBox {{"
        f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
        f"  border:1px solid {theme.BORDER_COLOR}; border-radius:12px;"
        f"  padding:7px 12px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
        f"  border:1px solid {theme.BORDER_COLOR};"
        f"  selection-background-color:{theme.SELECTION_BG}; selection-color:{theme.TEXT_DARK};"
        f"}}"
    )


def _build_production_note(action: str, destination: str, *, machine: str = "", reason: str = "") -> str:
    parts = [PROD_NOTE_PREFIX, action, destination]
    if machine:
        parts.append(f"machine={machine}")
    if reason:
        parts.append(f"reason={reason.strip()}")
    return "|".join(parts)


def _format_elapsed(value: str | None) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return "-"
    return _format_datetime(dt)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "-"
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min"


class ProductionWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, destination: str):
        super().__init__()
        self.destination = destination

    def run(self):
        try:
            self.result.emit(api.get_production_summary(self.destination))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class ActionWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args

    def run(self):
        try:
            self.result.emit(self.fn(*self.args))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class UiCallback(QObject):
    result = Signal(object)
    error = Signal(str)


class ProductionView(QWidget):
    open_requisition = Signal(int)
    guide_requested  = Signal()          # emitido pelo botão ? de ajuda

    def __init__(
        self,
        scale: float = 1.0,
        destinations: tuple[str, ...] | None = None,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.scale = scale
        configured_destinations = destinations or session.visible_production_destinations
        self.destinations = tuple(_normalize_destination(dest) for dest in configured_destinations)
        self.destination = self.destinations[0] if self.destinations else "A&R"
        self.page_title = title or self.destination
        self.page_subtitle = subtitle or "Acompanhamento operacional da produção."
        self.dialog_title = self.page_title
        self._threads: list[tuple[QThread, QObject]] = []
        self._stage_rows: dict[str, list[dict]] = {
            WAITING_RECEIPT_STAGE: [],
            WAITING_QUEUE_STAGE: [],
        }
        self._machine_cards: dict[int, dict] = {}
        self._machines_data: list[dict] = []
        self._setup_ui()
        if self.destination in session.visible_production_destinations:
            self.refresh()

    def _setup_ui(self):
        s = self.scale
        self.setObjectName("productionView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#productionView {{ background:{theme.CONTENT_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}")
        root.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setStyleSheet(f"background:{theme.CONTENT_BG};")
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)), max(18, int(24 * s)), max(18, int(24 * s)))
        layout.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel(self.page_title)
        title.setStyleSheet(f"font-size:{max(18, int(24 * s))}pt; font-weight:800;")
        subtitle = QLabel(self.page_subtitle)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = _make_card(s, theme.CARD_BG, hover_background=theme.CARD_BG, radius=max(16, int(18 * s)))
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)), max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setProperty("muted", "1")
        date_hint.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(f"font-size:{max(13, int(16 * s))}pt; font-weight:800;")
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt;")
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)

        right_col.addWidget(info_card)
        right_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)

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
        )
        self.btn_guide.clicked.connect(self.guide_requested)
        right_col.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        header.addLayout(right_col)
        layout.addLayout(header)

        counts = QGridLayout()
        counts.setHorizontalSpacing(max(12, int(16 * s)))
        counts.setVerticalSpacing(max(12, int(16 * s)))
        self.summary_waiting_receipt = self._build_summary_card("Aguardando Recebimento", theme.WARNING, "Pedidos enviados e ainda não recebidos.")
        self.summary_waiting_queue = self._build_summary_card(
            "Aguardando na Fila",
            theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
            "Pedidos recebidos e aguardando máquina.",
        )
        self.summary_in_production = self._build_summary_card("Em Produção", theme.PRIMARY, "Pedidos atualmente rodando em alguma máquina.")
        counts.addWidget(self.summary_waiting_receipt["card"], 0, 0)
        counts.addWidget(self.summary_waiting_queue["card"], 0, 1)
        counts.addWidget(self.summary_in_production["card"], 0, 2)
        layout.addLayout(counts)

        stages_row = QHBoxLayout()
        stages_row.setSpacing(max(14, int(18 * s)))
        self.waiting_receipt_panel = self._build_stage_panel(
            WAITING_RECEIPT_STAGE,
            "Aguardando Recebimento",
            "Confirmar recebimento e decidir o próximo passo.",
            ["PED", "CLIENTE", "OBRA", "ENVIADA EM"],
            "Receber",
        )
        self.waiting_queue_panel = self._build_stage_panel(
            WAITING_QUEUE_STAGE,
            "Aguardando na Fila",
            "Pedidos aguardando liberação de máquina.",
            ["PED", "CLIENTE", "OBRA", "FILA DESDE"],
            "Enviar para Máquina",
        )
        stages_row.addWidget(self.waiting_receipt_panel["card"], 1)
        stages_row.addWidget(self.waiting_queue_panel["card"], 1)
        layout.addLayout(stages_row)

        machines_header = QHBoxLayout()
        machines_header.setSpacing(max(10, int(12 * s)))
        machine_title_col = QVBoxLayout()
        machine_title_col.setSpacing(max(3, int(4 * s)))

        machine_title = QLabel("Máquinas")
        machine_title.setStyleSheet(f"color:{theme.TEXT_DARK}; font-size:{max(12, int(14 * s))}pt; font-weight:800;")
        machine_subtitle = QLabel("Selecione a requisição de cada card para finalizar ou devolver para a fila.")
        machine_subtitle.setWordWrap(True)
        machine_subtitle.setProperty("muted", "1")
        machine_subtitle.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt;")
        machine_title_col.addWidget(machine_title)
        machine_title_col.addWidget(machine_subtitle)
        machines_header.addLayout(machine_title_col, 1)

        icon_label = self._build_destination_icon_label(self.destination)
        if icon_label is not None:
            machines_header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(machines_header)

        self.machines_widget = QWidget()
        self.machines_grid = QGridLayout(self.machines_widget)
        self.machines_grid.setContentsMargins(0, 0, 0, 0)
        self.machines_grid.setHorizontalSpacing(max(12, int(16 * s)))
        self.machines_grid.setVerticalSpacing(max(12, int(16 * s)))
        layout.addWidget(self.machines_widget)

    def _build_destination_icon_label(self, destination: str) -> QLabel | None:
        meta = _destination_card_meta(destination) or {}
        filename = meta.get("icon")
        if not filename:
            return None

        icon_path = _ICON_DIR / filename
        if not icon_path.exists():
            return None

        pixmap = QPixmap(str(icon_path))
        if pixmap.isNull():
            return None

        size = max(52, int(62 * self.scale))
        label = QLabel()
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background:transparent; border:none;")
        label.setPixmap(
            pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return label

    def _build_summary_card(self, title_text: str, accent_color: str, helper_text: str) -> dict:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, hover_background=theme.CARD_BG, radius=max(18, int(20 * s)))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)), max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("0")
        value_label.setStyleSheet(
            f"font-size:{max(20, int(26 * s))}pt; font-weight:800;"
        )
        title_label = QLabel(title_text)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"font-size:{max(9, int(11 * s))}pt; font-weight:700;"
        )
        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "1")
        helper_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
        )
        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addStretch()
        layout.addWidget(accent_line)
        return {"card": card, "value": value_label}

    def _build_stage_panel(
        self,
        stage: str,
        title_text: str,
        subtitle_text: str,
        headers: list[str],
        primary_text: str,
    ) -> dict:
        s = self.scale
        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)), max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        title_row = QHBoxLayout()
        title = QLabel(title_text)
        title.setStyleSheet(f"font-size:{max(12, int(14 * s))}pt; font-weight:800;")
        count = QLabel("0")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setMinimumWidth(max(28, int(34 * s)))
        count.setStyleSheet(
            f"background:transparent; color:{theme.PRIMARY}; border:none;"
            f"font-size:{max(9, int(11 * s))}pt; font-weight:800; padding:0px;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(count)

        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"font-size:{max(9, int(10 * s))}pt;")
        layout.addLayout(title_row)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))
        btn_open = QPushButton("Abrir")
        btn_primary = QPushButton(primary_text)
        btn_cancel = QPushButton("Cancelar")
        for btn in (btn_open, btn_primary, btn_cancel):
            btn.setFixedHeight(max(34, int(38 * s)))

        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_primary.setStyleSheet(_primary_action_btn_style(s))
        btn_cancel.setStyleSheet(_danger_action_btn_style(s))

        btn_open.clicked.connect(lambda: self._open_selected_stage(stage))
        if stage == WAITING_RECEIPT_STAGE:
            btn_primary.clicked.connect(self._receive_selected)
        else:
            btn_primary.clicked.connect(self._send_queue_selected_to_machine)
        btn_cancel.clicked.connect(lambda: self._cancel_selected_stage(stage))

        actions.addWidget(btn_open)
        actions.addWidget(btn_primary)
        actions.addWidget(btn_cancel)
        layout.addLayout(actions)

        table = self._build_table(headers, stretch_columns={1, 2})
        table.doubleClicked.connect(lambda index, current_stage=stage: self._open_stage_row(current_stage, index.row()))
        table.setMinimumHeight(max(240, int(270 * s)))
        layout.addWidget(table, 1)

        return {
            "card": card,
            "table": table,
            "count": count,
        }

    def _build_table(self, headers: list[str], *, stretch_columns: set[int]) -> QTableWidget:
        s = self.scale
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header_widget = table.horizontalHeader()
        for col in range(len(headers)):
            mode = QHeaderView.ResizeMode.Stretch if col in stretch_columns else QHeaderView.ResizeMode.ResizeToContents
            header_widget.setSectionResizeMode(col, mode)
        header_widget.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header_widget.setMinimumHeight(max(34, int(40 * s)))
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  alternate-background-color:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
        apply_smooth_scroll(table)
        return table

    def refresh(self):
        self._set_loading(True)
        worker = ProductionWorker(self.destination)
        thread = QThread()
        cb = UiCallback()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(cb.result)
        worker.error.connect(cb.error)
        cb.result.connect(self._on_refresh_result)
        cb.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())
        self.refresh_btn.setEnabled(not loading)

    def _on_refresh_result(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta inválida ao carregar a produção.")
            return

        stats = payload.get("stats") or {}
        self.summary_waiting_receipt["value"].setText(str(stats.get("aguardando_recebimento") or 0))
        self.summary_waiting_queue["value"].setText(str(stats.get("aguardando_na_fila") or 0))
        self.summary_in_production["value"].setText(str(stats.get("em_producao") or 0))

        self._stage_rows[WAITING_RECEIPT_STAGE] = [
            row for row in (payload.get("waiting_receipt") or []) if isinstance(row, dict)
        ]
        self._stage_rows[WAITING_QUEUE_STAGE] = [
            row for row in (payload.get("waiting_queue") or []) if isinstance(row, dict)
        ]

        self._fill_stage_table(self.waiting_receipt_panel, self._stage_rows[WAITING_RECEIPT_STAGE], WAITING_RECEIPT_STAGE)
        self._fill_stage_table(self.waiting_queue_panel, self._stage_rows[WAITING_QUEUE_STAGE], WAITING_QUEUE_STAGE)

        self._machines_data = [
            machine for machine in (payload.get("machines") or []) if isinstance(machine, dict)
        ]
        self._populate_machine_cards()

        generated_at = _parse_datetime(payload.get("generated_at")) or local_now()
        self.date_label.setText(_format_header_date(generated_at))
        self.updated_label.setText(f"Atualizado em {_format_datetime(generated_at)}")

    def _fill_stage_table(self, panel: dict, rows: list[dict], stage: str):
        table = panel["table"]
        panel["count"].setText(str(len(rows)))
        table.setRowCount(0)

        for req in rows:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                str(req.get("ped_number") or ""),
                str(req.get("client_name") or "-"),
                str(req.get("obra") or "-"),
                _format_elapsed(req.get("waiting_since")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _clear_layout(self, layout: QGridLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)  # type: ignore[arg-type]

    def _populate_machine_cards(self):
        self._clear_layout(self.machines_grid)
        self._machine_cards = {}
        s = self.scale

        if not self._machines_data:
            empty = QLabel("Nenhuma máquina cadastrada para este destino.")
            empty.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * s))}pt; font-weight:600;")
            empty.setProperty("muted", "1")
            self.machines_grid.addWidget(empty, 0, 0)
            return

        for index, machine in enumerate(self._machines_data):
            machine_card = self._build_machine_card(machine)
            row = index // 2
            col = index % 2
            self.machines_grid.addWidget(machine_card["card"], row, col)
            self._machine_cards[int(machine["id"])] = machine_card

    def _build_machine_card(self, machine: dict) -> dict:
        s = self.scale
        meta = _destination_card_meta(self.destination) or {}
        accent_color = meta.get("accent") or theme.PRIMARY

        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=theme.BORDER_COLOR,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(14, int(18 * s)), max(14, int(18 * s)), max(14, int(18 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        layout.addWidget(accent)

        title = QLabel(str(machine.get("name") or "Máquina"))
        title.setWordWrap(True)
        title.setStyleSheet(f"font-size:{max(9, int(11 * s))}pt; font-weight:800;")
        layout.addWidget(title)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(max(10, int(12 * s)))
        stats_grid.setVerticalSpacing(max(8, int(10 * s)))
        stats_grid.addWidget(self._machine_stat_block("Quantidade em Produção", str(machine.get("quantity_in_production") or 0)), 0, 0)
        stats_grid.addWidget(self._machine_stat_block("Finalizadas", str(machine.get("finalized_count") or 0)), 0, 1)
        stats_grid.addWidget(self._machine_stat_block("Tempo Médio", _format_duration(machine.get("average_seconds"))), 1, 0, 1, 2)
        layout.addLayout(stats_grid)

        status_row = QHBoxLayout()
        status_row.setSpacing(max(8, int(10 * s)))
        status_label = QLabel("Status da Máquina")
        status_label.setStyleSheet(f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        status_label.setProperty("muted", "1")
        status_combo = QComboBox()
        for value, text in MACHINE_STATUS_OPTIONS:
            status_combo.addItem(text, value)
        status_combo.setStyleSheet(_machine_combo_style(s))
        current_status = str(machine.get("status") or "funcionando")
        combo_index = max(0, status_combo.findData(current_status))
        status_combo.setCurrentIndex(combo_index)
        status_button = QPushButton("Atualizar Status")
        status_button.setFixedHeight(max(34, int(38 * s)))
        status_button.setStyleSheet(_flat_secondary_btn_style(s))
        status_button.clicked.connect(
            lambda checked=False, mid=int(machine["id"]), combo=status_combo: self._update_machine_status(mid, combo)
        )
        status_row.addWidget(status_label)
        status_row.addStretch()
        status_row.addWidget(status_combo)
        status_row.addWidget(status_button)
        layout.addLayout(status_row)

        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))
        btn_open = QPushButton("Abrir")
        btn_finish = QPushButton("Finalizar")
        btn_cancel = QPushButton("Cancelar")
        for btn in (btn_open, btn_finish, btn_cancel):
            btn.setFixedHeight(max(34, int(38 * s)))
        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_finish.setStyleSheet(_primary_action_btn_style(s))
        btn_cancel.setStyleSheet(_danger_action_btn_style(s))
        btn_open.clicked.connect(lambda: self._open_selected_machine(int(machine["id"])))
        btn_finish.clicked.connect(lambda: self._finish_selected_machine(int(machine["id"])))
        btn_cancel.clicked.connect(lambda: self._return_selected_machine_to_queue(int(machine["id"])))
        actions.addWidget(btn_open)
        actions.addWidget(btn_finish)
        actions.addWidget(btn_cancel)
        layout.addLayout(actions)

        table = self._build_table(["PED", "CLIENTE", "INICIO"], stretch_columns={1})
        table.setMinimumHeight(max(180, int(210 * s)))
        rows = [row for row in (machine.get("rows") or []) if isinstance(row, dict)]
        self._fill_machine_table(table, rows)
        table.doubleClicked.connect(
            lambda index, machine_id=int(machine["id"]): self._open_machine_row(machine_id, index.row())
        )
        layout.addWidget(table, 1)

        return {
            "card": card,
            "table": table,
            "combo": status_combo,
            "rows": rows,
            "machine": dict(machine),
        }

    def _machine_stat_block(self, title_text: str, value_text: str) -> QWidget:
        s = self.scale
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(2, int(3 * s)))

        title = QLabel(title_text.upper())
        title.setProperty("muted", "1")
        title.setStyleSheet(f"font-size:{max(6, int(7 * s))}pt; font-weight:700;")
        value = QLabel(value_text)
        value.setWordWrap(True)
        value.setStyleSheet(f"font-size:{max(9, int(11 * s))}pt; font-weight:800;")
        layout.addWidget(title)
        layout.addWidget(value)
        return box

    def _fill_machine_table(self, table: QTableWidget, rows: list[dict]):
        table.setRowCount(0)
        for req in rows:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                str(req.get("ped_number") or ""),
                str(req.get("client_name") or "-"),
                _format_elapsed(req.get("production_started_at")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _selected_stage_row(self, stage: str) -> dict | None:
        panel = self.waiting_receipt_panel if stage == WAITING_RECEIPT_STAGE else self.waiting_queue_panel
        row = panel["table"].currentRow()
        rows = self._stage_rows.get(stage, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _selected_machine_row(self, machine_id: int) -> tuple[dict | None, dict | None]:
        card = self._machine_cards.get(machine_id)
        if not card:
            return None, None
        row = card["table"].currentRow()
        rows = card["rows"]
        if 0 <= row < len(rows):
            return rows[row], card["machine"]
        return None, card["machine"]

    def _show_error(self, msg: str):
        self.updated_label.setText("Falha ao atualizar")
        friendly = str(msg or "").strip()
        normalized = friendly.casefold()
        if normalized in {"not found", "404: not found"} or "not found" in normalized:
            friendly = (
                "O servidor da API ainda não carregou o novo fluxo de produção.\n\n"
                "Reinicie o servidor e abra novamente a tela de produção."
            )
        QMessageBox.critical(self, self.dialog_title, friendly)

    def _show_info(self, msg: str):
        QMessageBox.information(self, self.dialog_title, msg)

    def _open_stage_row(self, stage: str, row: int):
        rows = self._stage_rows.get(stage, [])
        if 0 <= row < len(rows):
            self.open_requisition.emit(int(rows[row]["id"]))

    def _open_machine_row(self, machine_id: int, row: int):
        card = self._machine_cards.get(machine_id)
        if not card:
            return
        rows = card["rows"]
        if 0 <= row < len(rows):
            self.open_requisition.emit(int(rows[row]["id"]))

    def _open_selected_stage(self, stage: str):
        req = self._selected_stage_row(stage)
        if not req:
            self._show_info("Selecione uma requisição primeiro.")
            return
        self.open_requisition.emit(int(req["id"]))

    def _open_selected_machine(self, machine_id: int):
        req, _machine = self._selected_machine_row(machine_id)
        if not req:
            self._show_info("Selecione uma requisição no card da máquina.")
            return
        self.open_requisition.emit(int(req["id"]))

    def _receive_selected(self):
        req = self._selected_stage_row(WAITING_RECEIPT_STAGE)
        if not req:
            self._show_info("Selecione uma requisição em aguardando recebimento.")
            return

        box = QMessageBox(self)
        box.setWindowTitle("Confirmar Recebimento")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Como deseja encaminhar esta requisição após o recebimento?")
        btn_queue = box.addButton("Aguardando na fila", QMessageBox.ButtonRole.AcceptRole)
        btn_machine = box.addButton("Em produção", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton("Cancelar requisição", QMessageBox.ButtonRole.DestructiveRole)
        btn_close = box.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(box)
        # Evita corte de texto dos botões longos nessa confirmação.
        btn_wide = max(150, int(170 * self.scale))
        btn_narrow = max(120, int(132 * self.scale))
        btn_queue.setMinimumWidth(btn_wide)
        btn_cancel.setMinimumWidth(btn_wide)
        btn_machine.setMinimumWidth(btn_narrow)
        btn_close.setMinimumWidth(btn_narrow)
        box.setMinimumWidth(max(580, int(640 * self.scale)))
        box.exec()
        clicked = box.clickedButton()

        if clicked == btn_queue:
            self._move_to_queue(req)
        elif clicked == btn_machine:
            self._start_production(req)
        elif clicked == btn_cancel:
            self._cancel_to_progress(req)

    def _move_to_queue(self, req: dict):
        self._run_action(
            api.update_status,
            int(req["id"]),
            "aguardando_na_fila",
            _build_production_note(PROD_QUEUED, self.destination),
            success_message="Requisição movida para aguardando na fila.",
        )

    def _pick_machine(self) -> str | None:
        machine_names = [str(machine.get("name") or "") for machine in self._machines_data if machine.get("name")]
        if not machine_names:
            self._show_error("Não há máquinas cadastradas para este destino.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar Máquina")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        lbl = QLabel("Escolha a máquina de destino:")
        layout.addWidget(lbl)

        combo = QComboBox()
        combo.addItems(machine_names)
        combo.setStyleSheet(_machine_combo_style(self.scale))
        layout.addWidget(combo)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        btn_ok.clicked.connect(dlg.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(combo.currentText() or "").strip() or None

    def _start_production(self, req: dict):
        machine_name = self._pick_machine()
        if not machine_name:
            return

        self._run_action(
            api.update_status,
            int(req["id"]),
            "em_producao",
            _build_production_note(PROD_STARTED, self.destination, machine=machine_name),
            success_message=f"Requisição enviada para {machine_name}.",
        )

    def _send_queue_selected_to_machine(self):
        req = self._selected_stage_row(WAITING_QUEUE_STAGE)
        if not req:
            self._show_info("Selecione uma requisição na grade aguardando na fila.")
            return
        self._start_production(req)

    def _cancel_selected_stage(self, stage: str):
        req = self._selected_stage_row(stage)
        if not req:
            self._show_info("Selecione uma requisição primeiro.")
            return
        self._cancel_to_progress(req)

    def _cancel_to_progress(self, req: dict):
        reason = self._ask_cancel_reason()
        if reason is None:
            return

        self._run_action(
            api.update_status,
            int(req["id"]),
            "cancelada",
            _build_production_note(PROD_CANCELED, self.destination, reason=reason),
            success_message="Requisição cancelada.",
        )

    def _finish_selected_machine(self, machine_id: int):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return
        if not ask_confirmation(
            self,
            "Finalizar Produção",
            "Deseja finalizar a produção desta requisição?",
            yes_text="Sim",
            no_text="Não",
        ):
            return

        machine_name = str(machine.get("name") or "")
        self._run_action(
            self._finalize_and_invoice_requisition,
            int(req["id"]),
            machine_name,
            success_message="Requisição finalizada e faturada.",
        )

    def _finalize_and_invoice_requisition(self, req_id: int, machine_name: str):
        note = _build_production_note(PROD_FINISHED, self.destination, machine=machine_name)
        api.update_status(req_id, "em_andamento", note)

        # Compatibilidade: servidores antigos ainda deixam em aguardando faturamento
        # após finalizar produção; neste caso, já faturamos na sequência.
        try:
            api.update_status(req_id, "faturado")
        except api.APIError as exc:
            detail = str(exc.detail or "")
            tolerated_errors = (
                "Somente pedidos aguardando faturamento podem ser marcados como faturados",
                "Pedidos faturados não podem retornar para outro status operacional",
            )
            if any(message in detail for message in tolerated_errors):
                return
            raise

    def _return_selected_machine_to_queue(self, machine_id: int):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return
        if not ask_confirmation(
            self,
            "Devolver para Fila",
            "Deseja devolver esta requisição para aguardando na fila?",
            yes_text="Sim",
            no_text="Não",
        ):
            return

        self._run_action(
            api.update_status,
            int(req["id"]),
            "aguardando_na_fila",
            _build_production_note(PROD_RETURNED_QUEUE, self.destination, machine=str(machine.get("name") or "")),
            success_message="Requisição devolvida para aguardando na fila.",
        )

    def _update_machine_status(self, machine_id: int, combo: QComboBox):
        status_value = str(combo.currentData() or "funcionando")
        status_label = combo.currentText()
        card = self._machine_cards.get(machine_id) or {}
        current_status = str((card.get("machine") or {}).get("status") or "")
        if current_status == status_value:
            self._show_info("O status da máquina já está definido dessa forma.")
            return
        self._run_action(
            api.update_production_machine_status,
            machine_id,
            status_value,
            success_message=f"Status da máquina atualizado para {status_label}.",
        )

    def _ask_cancel_reason(self) -> str | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Cancelar Requisição")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        lbl = QLabel("Informe o motivo do cancelamento:")
        layout.addWidget(lbl)

        input_reason = QTextEdit()
        input_reason.setPlaceholderText("Descreva o motivo...")
        input_reason.setMinimumHeight(max(96, int(120 * self.scale)))
        input_reason.setStyleSheet(theme.input_style(self.scale))
        layout.addWidget(input_reason)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        def _confirm_reason():
            normalized = " ".join(input_reason.toPlainText().split())
            if len(normalized) < 10:
                error_lbl.setText("O motivo do cancelamento precisa ter pelo menos 10 letras.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_cancel_reason", normalized)
            dlg.accept()

        btn_ok.clicked.connect(_confirm_reason)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(dlg.property("_cancel_reason") or "")

    def _run_action(self, fn, *args, success_message: str):
        worker = ActionWorker(fn, *args)
        thread = QThread()
        cb = UiCallback()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(cb.result)
        worker.error.connect(cb.error)
        cb.result.connect(lambda _: self._after_action(success_message))
        cb.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _after_action(self, success_message: str):
        self.refresh()
        self._show_info(success_message)

    def _apply_table_style(self, table: QTableWidget) -> None:
        s = self.scale
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  alternate-background-color:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        table.setPalette(pal)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#productionView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ background:{bg}; border:none; }}")
        self._page_content.setStyleSheet(f"background:{bg};")
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        for panel in (self.waiting_receipt_panel, self.waiting_queue_panel):
            self._apply_table_style(panel["table"])
        for card in self._machine_cards.values():
            self._apply_table_style(card["table"])
            card["combo"].setStyleSheet(_machine_combo_style(s))


