"""Tela de entregas com indicadores, agenda e ações operacionais."""

from __future__ import annotations

from datetime import timedelta as _timedelta

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
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
    QVBoxLayout,
    QWidget,
    QDialog,
)

from ..api import client as api
from ..core import theme
from ..core.dialogs import ask_confirmation
from ..core.formatters import format_weight_kg
from ..core.datetime_utils import (
    format_date as _format_date,
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..widgets.sortable_item import SortableItem
from .requisition_form import _run_in_thread


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.PANEL_SHADOW)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


def _delivery_card_qss(border_color: str | None, radius: int) -> str:
    """QSS dos cards do delivery center. Cobre background gradient +
    border (que muda com tema) num único stylesheet do widget.
    Chamado via theme.themed() para reaplicar a cada troca de tema."""
    accent = border_color or theme.PANEL_BORDER_SOFT
    return (
        f"QFrame#deliveryCenterCard {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {theme.PANEL_CARD_BG_START},"
        f"    stop:0.55 {theme.PANEL_CARD_BG_MID},"
        f"    stop:1 {theme.PANEL_CARD_BG_END});"
        f"  border:1px solid {_rgba(accent, 126)};"
        f"  border-radius:{radius}px;"
        f"}}"
    )


def _make_card(
    scale: float,
    background: str | None = None,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    card = QFrame()
    card.setObjectName("deliveryCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    radius_int = int(radius)
    theme.themed(card, lambda: _delivery_card_qss(border_color, radius_int))
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


def _primary_action_btn_style(scale: float) -> str:
    return theme.primary_btn_style(scale)


def _format_weight(value: object) -> str:
    return format_weight_kg(value)


def _status_badge_color(status: str) -> str:
    color_map = {
        "em_andamento": theme.PRIMARY_HOVER,
        "prazo_alterado": theme.STATUS_COLORS.get("prazo_alterado", theme.WARNING),
        "entregue": theme.STATUS_COLORS.get("entregue", theme.SUCCESS),
        "aguardando_recebimento": theme.WARNING,
        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
        "em_producao": theme.PRIMARY,
        "faturado": theme.STATUS_COLORS.get("faturado", theme.SUCCESS),
        "finalizado": theme.STATUS_COLORS.get("finalizado", theme.SUCCESS),
        "cancelada": theme.DANGER,
    }
    return color_map.get(status, theme.BORDER_COLOR)


class DeliveryCenterWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            payload = api.get_delivery_center()
            settings = api.get_operational_settings()
            if isinstance(payload, dict):
                payload["delivery_cancel_reasons"] = (
                    settings.get("delivery_cancel_reasons")
                    if isinstance(settings, dict)
                    else []
                )
                payload["delivery_deadline_change_reasons"] = (
                    settings.get("delivery_deadline_change_reasons")
                    if isinstance(settings, dict)
                    else []
                )
            self.result.emit(payload)
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class DeliveryCenterView(QWidget):
    open_requisition = Signal(int)
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._pending_rows: list[dict] = []
        self._completed_rows: list[dict] = []
        self._delivery_cancel_reason_rows: list[dict[str, str]] = []
        self._delivery_deadline_reason_rows: list[dict[str, str]] = []
        self._row_by_id: dict[str, dict] = {}
        self._completed_row_by_id: dict[str, dict] = {}
        self._metric_labels: dict[str, QLabel] = {}
        self._view_mode: str = "list"
        self._schedule_week_offset: int = 0
        self._schedule_selected_row: dict | None = None
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        self.setObjectName("deliveryCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Background da view via theme.themed() — sem isso, o page_bg capturado
        # no init do tema escuro permanecia ao trocar pra claro (a area entre
        # cards continuava escura mesmo apos a troca).
        theme.themed(self, lambda: f"QWidget#deliveryCenterView {{ background:{theme.CONTENT_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Entregas")
        # Cor explicita ao inves de depender de palette herdada — palette
        # nao propaga consistentemente quando ha setStyleSheet inline no
        # widget, mesmo que o stylesheet nao mexa em color.
        theme.themed(title, lambda: (
            f"background:transparent; font-size:{max(18, int(24 * s))}pt;"
            f"font-weight:800; color:{theme.TEXT_DARK};"
        ))
        subtitle = QLabel(
            "Agenda operacional de entregas com acompanhamento de prazos, status e conclusao."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        theme.themed(subtitle, lambda: (
            f"background:transparent; font-size:{max(8, int(10 * s))}pt;"
            f"color:{theme.TEXT_MEDIUM};"
        ))
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        status_col = QVBoxLayout()
        status_col.setSpacing(max(6, int(8 * s)))
        self.date_label = QLabel(_format_header_date())
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        theme.themed(self.date_label, lambda: (
            f"background:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"font-weight:700; color:{theme.TEXT_MEDIUM};"
        ))
        self.updated_label = QLabel("Atualizado em -")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        theme.themed(self.updated_label, lambda: (
            f"background:transparent; font-size:{max(7, int(8 * s))}pt; color:{theme.TEXT_MEDIUM};"
        ))
        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(34, int(38 * s)))
        theme.themed(self.refresh_btn, lambda: _flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        status_col.addWidget(self.date_label)
        status_col.addWidget(self.updated_label)
        status_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        header.addLayout(status_col)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        root.addWidget(self.error_label)

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        theme.themed(self._page_scroll, lambda: f"QScrollArea {{ border:none; background:{theme.CONTENT_BG}; }}")
        theme.themed(self._page_scroll.viewport(), lambda: f"background:{theme.CONTENT_BG}; border:none;")
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("deliveryCenterContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        theme.themed(self._page_content, lambda: f"QWidget#deliveryCenterContent {{ background:{theme.CONTENT_BG}; }}")
        self._page_scroll.setWidget(self._page_content)

        content_layout = QVBoxLayout(self._page_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(max(16, int(18 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        content_layout.addLayout(metrics)

        card_defs = [
            ("deliveries_today", theme.PRIMARY, "ENTREGAS PARA HOJE", "Pedidos com entrega prevista para o dia atual."),
            ("delayed_deliveries", theme.DANGER, "ENTREGAS ATRASADAS", "Pedidos de entrega pendente com prazo vencido."),
            ("changed_delivery_deadlines", theme.STATUS_COLORS.get("prazo_alterado", theme.WARNING), "PRAZO DE ENTREGA ALTERADO", "Entregas pendentes com prazo ajustado."),
            ("completed_deliveries", theme.SUCCESS, "ENTREGAS REALIZADAS", "Pedidos de entrega concluidos."),
        ]
        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                0,
                index,
            )

        table_card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        card_layout = QVBoxLayout(table_card)
        card_layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                       max(16, int(20 * s)), max(14, int(18 * s)))
        card_layout.setSpacing(max(10, int(12 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(theme.PRIMARY, 235)}, stop:0.5 {_rgba(theme.PRIMARY, 155)}, stop:1 {_rgba(theme.PRIMARY, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        card_layout.addWidget(accent)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(max(2, int(3 * s)))
        section_title = QLabel("Agenda de Entregas")
        theme.themed(section_title, lambda: (
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"background:transparent; color:{theme.TEXT_DARK};"
        ))
        section_subtitle = QLabel(
            "Selecione uma entrega ou parcela para alterar o prazo ou registrar a conclusao."
        )
        section_subtitle.setWordWrap(True)
        section_subtitle.setProperty("muted", "1")
        theme.themed(section_subtitle, lambda: (
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; color:{theme.TEXT_MEDIUM};"
        ))
        title_col.addWidget(section_title)
        title_col.addWidget(section_subtitle)
        title_row.addLayout(title_col, 1)

        self._btn_view_list = QPushButton("Lista")
        self._btn_view_list.setFixedHeight(max(32, int(36 * s)))
        self._btn_view_sched = QPushButton("Cronograma")
        self._btn_view_sched.setFixedHeight(max(32, int(36 * s)))
        theme.themed(self._btn_view_list, lambda: self._toggle_btn_style("list"))
        theme.themed(self._btn_view_sched, lambda: self._toggle_btn_style("schedule"))
        self._btn_view_list.clicked.connect(lambda: self._set_delivery_view("list"))
        self._btn_view_sched.clicked.connect(lambda: self._set_delivery_view("schedule"))
        title_row.addWidget(self._btn_view_list)
        title_row.addWidget(self._btn_view_sched)
        title_row.addSpacing(max(8, int(10 * s)))

        btn_create = QPushButton("CRIAR")
        btn_create.setFixedHeight(max(32, int(36 * s)))
        theme.themed(btn_create, lambda: (
            f"QPushButton {{ background:{_rgba(theme.SUCCESS, 35)}; color:{theme.SUCCESS};"
            f"border:1px solid {_rgba(theme.SUCCESS, 80)}; border-radius:{max(5, int(6 * s))}px;"
            f"padding:0 {max(10, int(12 * s))}px; font-size:{max(8, int(9 * s))}pt; font-weight:600; }}"
            f"QPushButton:hover {{ background:{_rgba(theme.SUCCESS, 55)}; }}"
        ))
        btn_create.clicked.connect(self._open_create_delivery_dialog)
        title_row.addWidget(btn_create)
        title_row.addSpacing(max(8, int(10 * s)))

        self.btn_change_deadline = QPushButton("ALTERAR PRAZO")
        self.btn_change_deadline.setFixedHeight(max(34, int(38 * s)))
        theme.themed(self.btn_change_deadline, lambda: _flat_secondary_btn_style(s))
        self.btn_change_deadline.clicked.connect(self._change_selected_deadline)
        title_row.addWidget(self.btn_change_deadline)

        self.btn_mark_delivered = QPushButton("ENTREGUE")
        self.btn_mark_delivered.setFixedHeight(max(34, int(38 * s)))
        theme.themed(self.btn_mark_delivered, lambda: _primary_action_btn_style(s))
        self.btn_mark_delivered.clicked.connect(self._mark_selected_delivered)
        title_row.addWidget(self.btn_mark_delivered)

        card_layout.addLayout(title_row)

        self.table = self._create_table(self._open_row)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_pending_selection_changed)
        card_layout.addWidget(self.table, 1)

        self._schedule_widget = self._build_schedule_widget()
        self._schedule_widget.setVisible(False)
        card_layout.addWidget(self._schedule_widget, 1)

        content_layout.addWidget(table_card, 1)

        completed_card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        completed_layout = QVBoxLayout(completed_card)
        completed_layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                            max(16, int(20 * s)), max(14, int(18 * s)))
        completed_layout.setSpacing(max(10, int(12 * s)))

        completed_accent = QFrame()
        completed_accent.setFixedHeight(max(4, int(5 * s)))
        completed_accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(theme.SUCCESS, 235)}, stop:0.5 {_rgba(theme.SUCCESS, 155)}, stop:1 {_rgba(theme.SUCCESS, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        completed_layout.addWidget(completed_accent)

        completed_title = QLabel("Entregas Realizadas")
        theme.themed(completed_title, lambda: (
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"background:transparent; color:{theme.TEXT_DARK};"
        ))
        completed_subtitle = QLabel("Entregas e parcelas concluidas.")
        completed_subtitle.setWordWrap(True)
        completed_subtitle.setProperty("muted", "1")
        theme.themed(completed_subtitle, lambda: (
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; color:{theme.TEXT_MEDIUM};"
        ))
        completed_layout.addWidget(completed_title)
        completed_layout.addWidget(completed_subtitle)

        completed_actions_row = QHBoxLayout()
        completed_actions_row.setContentsMargins(0, 0, 0, 0)
        completed_actions_row.setSpacing(max(8, int(10 * s)))
        completed_actions_row.addStretch()
        self.btn_cancel_delivered = QPushButton("CANCELAR ENTREGA")
        self.btn_cancel_delivered.setFixedHeight(max(34, int(38 * s)))
        theme.themed(self.btn_cancel_delivered, lambda: _flat_secondary_btn_style(s))
        self.btn_cancel_delivered.clicked.connect(self._cancel_selected_delivered)
        completed_actions_row.addWidget(self.btn_cancel_delivered)
        completed_layout.addLayout(completed_actions_row)

        self.completed_table = self._create_table(self._open_completed_row)
        self.completed_table.itemSelectionChanged.connect(self._on_completed_selection_changed)
        completed_layout.addWidget(self.completed_table, 1)
        content_layout.addWidget(completed_card, 1)
        content_layout.addStretch()
        self._update_action_buttons()

    def _build_metric_card(
        self,
        color: str,
        title_text: str,
        helper_text: str,
        key: str,
    ) -> QFrame:
        s = self.scale
        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value = QLabel("-")
        theme.themed(value, lambda: (
            f"font-size:{max(20, int(26 * s))}pt; font-weight:800;"
            f"background:transparent; border:none; color:{theme.TEXT_DARK};"
        ))
        value.setWordWrap(True)

        title = QLabel(title_text)
        title.setWordWrap(True)
        theme.themed(title, lambda: (
            f"font-size:{max(9, int(11 * s))}pt; font-weight:700;"
            f"background:transparent; border:none; color:{theme.TEXT_DARK};"
        ))

        helper = QLabel(helper_text)
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        theme.themed(helper, lambda: (
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none; color:{theme.TEXT_MEDIUM};"
        ))

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(color, 235)}, stop:0.5 {_rgba(color, 155)}, stop:1 {_rgba(color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        layout.addWidget(value)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addStretch()
        layout.addWidget(accent_line)
        self._metric_labels[key] = value
        return card

    def _create_table(self, open_handler=None) -> QTableWidget:
        headers = [
            "PEDIDO",
            "CLIENTE",
            "VENDEDOR",
            "PESO",
            "PRODUCAO",
            "DATA PREVISTA",
            "MOTIVO ALTERACAO PRAZO",
            "STATUS DO PEDIDO",
            "DATA DA ENTREGA",
        ]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if open_handler is not None:
            table.doubleClicked.connect(lambda index, handler=open_handler: handler(index.row()))

        header = table.horizontalHeader()
        stretch_columns = {1, 2, 6}
        for col in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(col, mode)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * self.scale)))
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(7, max(190, int(210 * self.scale)))
        table.verticalHeader().setDefaultSectionSize(max(36, int(42 * self.scale)))
        table.setSortingEnabled(True)
        self._apply_table_style(table)
        table.setMinimumHeight(max(360, int(420 * self.scale)))
        apply_smooth_scroll(table)
        return table

    def _apply_table_style(self, table: QTableWidget) -> None:
        s = self.scale
        table.setStyleSheet(theme.neon_table_qss(self.scale))
        theme.apply_neon_table_palette(table)

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()
        worker = DeliveryCenterWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.btn_change_deadline.setEnabled(False)
            self.btn_mark_delivered.setEnabled(False)
            if hasattr(self, "btn_cancel_delivered"):
                self.btn_cancel_delivered.setEnabled(False)
        else:
            self._update_action_buttons()
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.error_label.setText(f"Nao foi possivel carregar a tela de entregas.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta invalida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        for key, label in self._metric_labels.items():
            label.setText(str(stats.get(key) if stats.get(key) is not None else 0))

        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

        raw_reasons = payload.get("delivery_cancel_reasons") or []
        self._delivery_cancel_reason_rows = [
            {
                "code": " ".join(str(item.get("code") or "").upper().split()),
                "reason": " ".join(str(item.get("reason") or "").split()),
            }
            for item in raw_reasons
            if isinstance(item, dict)
            and str(item.get("code") or "").strip()
            and str(item.get("reason") or "").strip()
        ]
        raw_deadline_reasons = payload.get("delivery_deadline_change_reasons") or []
        self._delivery_deadline_reason_rows = [
            {
                "code": " ".join(str(item.get("code") or "").upper().split()),
                "reason": " ".join(str(item.get("reason") or "").split()),
            }
            for item in raw_deadline_reasons
            if isinstance(item, dict)
            and str(item.get("code") or "").strip()
            and str(item.get("reason") or "").strip()
        ]

        raw_rows = payload.get("rows") or []
        rows = raw_rows if isinstance(raw_rows, list) else []
        self._pending_rows = [row for row in rows if isinstance(row, dict) and not row.get("delivered_at")]
        self._completed_rows = [row for row in rows if isinstance(row, dict) and row.get("delivered_at")]
        self._row_by_id = {}
        self._completed_row_by_id = {}
        self._fill_table(
            self.table,
            self._pending_rows,
            self._row_by_id,
            "Nenhuma entrega pendente na agenda.",
            sort_column=5,
            sort_order=Qt.SortOrder.AscendingOrder,
        )
        self._fill_table(
            self.completed_table,
            self._completed_rows,
            self._completed_row_by_id,
            "Nenhuma entrega realizada ainda.",
            sort_column=8,
            sort_order=Qt.SortOrder.DescendingOrder,
        )
        self._update_action_buttons()
        self._render_schedule()

    def _fill_table(
        self,
        table: QTableWidget,
        rows: list[dict],
        row_map: dict[str, dict],
        empty_message: str,
        sort_column: int,
        sort_order: Qt.SortOrder,
    ):
        table.clearSpans()
        table.setRowCount(0)

        if not rows:
            self._set_empty_message(table, empty_message)
            return

        table.setSortingEnabled(False)
        for row_data in rows:
            if not isinstance(row_data, dict):
                continue

            row = table.rowCount()
            table.insertRow(row)

            row_key = self._row_key(row_data)
            if row_key:
                row_map[row_key] = row_data

            ped_raw = row_data.get("ped_number")
            ped_sort_source = str(ped_raw or "").split("/", 1)[0]
            try:
                ped_sort = int(ped_sort_source)
            except (TypeError, ValueError):
                ped_sort = 0
            try:
                weight_sort = float(row_data.get("weight") or 0.0)
            except (TypeError, ValueError):
                weight_sort = 0.0

            status = str(row_data.get("status") or "")
            values = [
                str(ped_raw or "-"),
                str(row_data.get("client_name") or "-"),
                str(row_data.get("vendor_name") or "-"),
                _format_weight(row_data.get("weight")),
                str(row_data.get("destination") or "-"),
                _format_date(row_data.get("delivery_date")),
                str(row_data.get("deadline_change_reason") or "-"),
                theme.STATUS_LABELS.get(status, status or "-"),
                _format_datetime(row_data.get("delivered_at")),
            ]
            sort_keys = [
                ped_sort,
                None,
                None,
                weight_sort,
                None,
                str(row_data.get("delivery_date") or ""),
                str(row_data.get("deadline_change_reason") or ""),
                None,
                str(row_data.get("delivered_at") or ""),
            ]

            for col, value in enumerate(values):
                if col == 7:
                    hidden_item = SortableItem("", sort_key=status)
                    hidden_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, col, hidden_item)

                    badge = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    color = _status_badge_color(status)
                    badge.setStyleSheet(
                        f"background:{_rgba(color, 30)}; color:{color}; border-radius:999px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(row, col, badge)
                    continue

                sk = sort_keys[col] if col < len(sort_keys) else None
                item = SortableItem(value, sort_key=sk) if sk is not None else QTableWidgetItem(value)
                if col == 0 and row_key:
                    item.setData(Qt.ItemDataRole.UserRole, row_key)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

        table.setSortingEnabled(True)
        table.sortByColumn(sort_column, sort_order)

    def _set_empty_message(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(theme.TEXT_MEDIUM))
        table.setItem(0, 0, item)

    def _row_key(self, row: dict | None) -> str:
        if not isinstance(row, dict):
            return ""
        split_id = int(row.get("production_split_id") or 0)
        if split_id:
            return f"split:{split_id}"
        req_id = int(row.get("source_requisition_id") or row.get("id") or 0)
        if req_id:
            return f"req:{req_id}"
        return ""

    def _source_requisition_id(self, row: dict | None) -> int:
        if not isinstance(row, dict):
            return 0
        return int(row.get("source_requisition_id") or row.get("id") or 0)

    def _production_split_id(self, row: dict | None) -> int:
        if not isinstance(row, dict):
            return 0
        return int(row.get("production_split_id") or 0)

    def _row_subject_label(self, row: dict | None) -> str:
        ped = str((row or {}).get("ped_number") or "-")
        if self._production_split_id(row):
            return f"a parcela {ped}"
        return f"o pedido {ped}"

    def _selected_rows(self) -> list[dict]:
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return []
        rows: list[dict] = []
        for index in selection_model.selectedRows(0):
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            row_key = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if not row_key:
                continue
            row = self._row_by_id.get(row_key)
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _selected_row(self) -> dict | None:
        rows = self._selected_rows()
        if len(rows) != 1:
            return None
        return rows[0]

    def _selected_completed_rows(self) -> list[dict]:
        selection_model = self.completed_table.selectionModel()
        if selection_model is None:
            return []
        rows: list[dict] = []
        for index in selection_model.selectedRows(0):
            item = self.completed_table.item(index.row(), 0)
            if item is None:
                continue
            row_key = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if not row_key:
                continue
            row = self._completed_row_by_id.get(row_key)
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _selected_completed_row(self) -> dict | None:
        rows = self._selected_completed_rows()
        if len(rows) != 1:
            return None
        return rows[0]

    def _row_key(self, row: dict) -> str:
        if not isinstance(row, dict):
            return ""
        split_id = int(row.get("production_split_id") or 0)
        if split_id:
            return f"split:{split_id}"
        req_id = int(row.get("id") or row.get("source_requisition_id") or 0)
        return f"req:{req_id}" if req_id else ""

    def _row_requisition_id(self, row: dict | None) -> int:
        if not isinstance(row, dict):
            return 0
        return int(row.get("source_requisition_id") or row.get("id") or 0)

    def _can_mark_row_delivered(self, row: dict | None) -> bool:
        if not isinstance(row, dict):
            return False
        if row.get("delivered_at"):
            return False
        return str(row.get("status") or "").strip().lower() in {"finalizado", "prazo_alterado"}

    def _can_mark_rows_delivered(self, rows: list[dict]) -> bool:
        return bool(rows) and all(self._can_mark_row_delivered(row) for row in rows)

    def _mark_delivery_target(self, row: dict) -> tuple[callable, int]:
        split_id = self._production_split_id(row)
        if split_id:
            return api.mark_split_delivery_delivered, split_id
        return api.mark_delivery_delivered, self._row_requisition_id(row)

    def _mark_rows_delivered(self, rows: list[dict]) -> int:
        delivered_count = 0
        for row in rows:
            fn, target_id = self._mark_delivery_target(row)
            fn(int(target_id))
            delivered_count += 1
        return delivered_count

    def _delivery_confirmation_message(self, rows: list[dict]) -> str:
        if len(rows) == 1:
            return f"Confirmar a entrega de {self._row_subject_label(rows[0])}?"
        return f"Confirmar a entrega de {len(rows)} itens selecionados?"

    def _delivery_success_message(self, count: int) -> str:
        if count == 1:
            return "Entrega registrada com sucesso."
        return f"{count} entregas registradas com sucesso."

    def _update_action_buttons(self) -> None:
        pending_rows = self._selected_rows()
        completed_rows = self._selected_completed_rows()
        self.btn_change_deadline.setEnabled(len(pending_rows) == 1)
        self.btn_mark_delivered.setEnabled(self._can_mark_rows_delivered(pending_rows))
        if hasattr(self, "btn_cancel_delivered"):
            self.btn_cancel_delivered.setEnabled(len(completed_rows) == 1)

    def _on_pending_selection_changed(self) -> None:
        if self.table.selectionModel() is not None and self.table.selectionModel().hasSelection():
            self.completed_table.blockSignals(True)
            self.completed_table.clearSelection()
            self.completed_table.blockSignals(False)
        self._update_action_buttons()

    def _on_completed_selection_changed(self) -> None:
        if (
            self.completed_table.selectionModel() is not None
            and self.completed_table.selectionModel().hasSelection()
        ):
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.blockSignals(False)
        self._update_action_buttons()

    def _open_row(self, row_index: int):
        item = self.table.item(row_index, 0)
        if item is None:
            return
        row = self._row_by_id.get(str(item.data(Qt.ItemDataRole.UserRole) or "").strip())
        req_id = self._row_requisition_id(row)
        if req_id:
            self.open_requisition.emit(req_id)

    def _open_completed_row(self, row_index: int):
        item = self.completed_table.item(row_index, 0)
        if item is None:
            return
        row = self._completed_row_by_id.get(str(item.data(Qt.ItemDataRole.UserRole) or "").strip())
        req_id = self._row_requisition_id(row)
        if req_id:
            self.open_requisition.emit(req_id)

    def _change_selected_deadline(self):
        row = self._selected_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione um pedido ou parcela primeiro.")
            return
        if not self._can_mark_rows_delivered(rows):
            return
        result = self._ask_delivery_date(row)
        if result is None:
            return

        new_date, reason = result
        self._run_action(
            api.update_delivery_schedule,
            self._row_requisition_id(row),
            new_date,
            reason,
            success_message="Prazo de entrega alterado com sucesso.",
        )

    def _mark_selected_delivered(self):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Entregas", "Selecione ao menos um pedido ou parcela primeiro.")
            return
        if row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ja foi concluida.")
            return
        if str(row.get("status") or "").strip().lower() != "finalizado":
            QMessageBox.information(
                self,
                "Entregas",
                "Somente pedidos já finalizados podem ser marcados como entregues.",
            )
            return
        if not QMessageBox.question(
            self,
            "Entregue",
            f"Confirmar a entrega de {self._row_subject_label(row)}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            return

        split_id = self._production_split_id(row)
        self._run_action(
            api.mark_split_delivery_delivered if row.get("production_split_id") else api.mark_delivery_delivered,
            int(row.get("production_split_id") or row["id"]),
            success_message="Entrega registrada com sucesso.",
        )

    def _cancel_selected_delivered(self):
        row = self._selected_completed_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione um pedido ou parcela entregue primeiro.")
            return

        if not row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ainda nao foi concluida.")
            return

        reason = self._ask_delivery_cancel_reason(row)
        if not reason:
            return

        split_id = self._production_split_id(row)
        self._run_action(
            api.cancel_split_delivery_delivered if row.get("production_split_id") else api.cancel_delivery_delivered,
            int(row.get("production_split_id") or row["id"]),
            reason,
            success_message="Entrega cancelada e retornada para a agenda.",
        )

    def _run_action(self, fn, *args, success_message: str):
        self._set_loading(True)
        thread, worker = _run_in_thread(
            fn,
            *args,
            on_result=lambda _result, message=success_message: self._after_action_success(message),
            on_error=lambda msg: self._after_action_error(msg),
        )
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        self._threads.append((thread, worker))

    def _after_action_success(self, message: str):
        self._set_loading(False)
        QMessageBox.information(self, "Entregas", message)
        self.refresh()

    def _after_action_error(self, message: str):
        self._set_loading(False)
        QMessageBox.critical(self, "Entregas", message)

    def _ask_delivery_date(self, req: dict) -> tuple[str, str] | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Alterar Prazo de Entrega")
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

        ped = str(req.get("ped_number") or "")
        header = QLabel(f"Pedido PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        lbl_date = QLabel("Novo prazo de entrega:")
        layout.addWidget(lbl_date)

        date_edit = QDateEdit()
        date_edit.setDisplayFormat("dd/MM/yyyy")
        date_edit.setCalendarPopup(True)
        date_edit.setFixedHeight(max(34, int(38 * self.scale)))
        date_edit.setStyleSheet(theme.input_style(self.scale))
        current = _parse_datetime(req.get("delivery_date"))
        if current is None:
            from PySide6.QtCore import QDate
            current_date = QDate.fromString(str(req.get("delivery_date") or "")[:10], "yyyy-MM-dd")
            date_edit.setDate(current_date if current_date.isValid() else QDate.currentDate())
        else:
            from PySide6.QtCore import QDate
            date_edit.setDate(QDate(current.year, current.month, current.day))
        layout.addWidget(date_edit)

        reasons = self._delivery_deadline_reason_rows
        if not reasons:
            QMessageBox.warning(
                self,
                "Entregas",
                "Nao ha motivos de alteracao de prazo configurados.\n"
                "Cadastre em Configuracoes > Sistema.",
            )
            return None

        lbl_reason = QLabel("Motivo da alteracao:")
        layout.addWidget(lbl_reason)

        reason_combo = QComboBox()
        reason_combo.setFixedHeight(max(34, int(38 * self.scale)))
        reason_combo.setStyleSheet(theme.input_style(self.scale))
        for row in reasons:
            code = str(row.get("code") or "").strip()
            reason = str(row.get("reason") or "").strip()
            reason_combo.addItem(f"{code} - {reason}", reason)
        layout.addWidget(reason_combo)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
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

        def _confirm():
            normalized = " ".join(str(reason_combo.currentData() or "").split())
            if len(normalized) < 3:
                error_lbl.setText("Selecione um motivo valido.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_new_date", date_edit.date().toString("yyyy-MM-dd"))
            dlg.setProperty("_reason", normalized)
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        new_date = str(dlg.property("_new_date") or "")
        reason = str(dlg.property("_reason") or "")
        if not new_date:
            return None
        return new_date, reason

    def _ask_delivery_cancel_reason(self, req: dict) -> str | None:
        reasons = self._delivery_cancel_reason_rows
        if not reasons:
            QMessageBox.warning(
                self,
                "Entregas",
                "Nao ha motivos de cancelamento de entrega configurados.\n"
                "Cadastre em Configuracoes > Sistema.",
            )
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Cancelar Entrega")
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

        ped = str(req.get("ped_number") or "")
        header = QLabel(f"Pedido PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        info = QLabel("Selecione o motivo para cancelar a entrega e retornar para a agenda.")
        info.setWordWrap(True)
        info.setProperty("muted", "1")
        info.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(info)

        combo = QComboBox()
        combo.setFixedHeight(max(34, int(38 * self.scale)))
        combo.setStyleSheet(theme.input_style(self.scale))
        for row in reasons:
            code = str(row.get("code") or "").strip()
            reason = str(row.get("reason") or "").strip()
            combo.addItem(f"{code} - {reason}", reason)
        layout.addWidget(combo)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Fechar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        def _confirm():
            reason = str(combo.currentData() or "").strip()
            if not reason:
                error_lbl.setText("Selecione um motivo valido.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_reason", reason)
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        reason = str(dlg.property("_reason") or "").strip()
        return reason or None

    def _change_selected_deadline(self):
        row = self._selected_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione um pedido ou parcela primeiro.")
            return
        if row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ja foi concluida.")
            return

        result = self._ask_delivery_date(row)
        if result is None:
            return

        new_date, reason = result
        self._run_action(
            api.update_delivery_schedule,
            self._row_requisition_id(row),
            new_date,
            reason,
            success_message="Prazo de entrega alterado com sucesso.",
        )

    def _mark_selected_delivered(self):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Entregas", "Selecione ao menos um pedido ou parcela primeiro.")
            return
        if not self._can_mark_rows_delivered(rows):
            QMessageBox.information(
                self,
                "Entregas",
                "Somente pedidos finalizados ou com prazo alterado podem ser marcados como entregues.",
            )
            return
        if not ask_confirmation(
            self,
            "Entregue",
            self._delivery_confirmation_message(rows),
            yes_text="Sim",
            no_text="Não",
            default_to_yes=False,
        ):
            return

        self._run_action(
            self._mark_rows_delivered,
            rows,
            success_message=self._delivery_success_message(len(rows)),
        )

    def _build_schedule_widget(self) -> QWidget:
        s = self.scale
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        theme.themed(container, lambda: f"background:{theme.CONTENT_BG}; border:none;")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(max(8, int(10 * s)))

        # Navigation row
        nav_row = QHBoxLayout()
        nav_row.setSpacing(max(6, int(8 * s)))
        btn_prev = QPushButton("◀")
        btn_prev.setFixedSize(max(28, int(32 * s)), max(28, int(32 * s)))
        theme.themed(btn_prev, lambda: theme.secondary_btn_style(s))
        btn_prev.clicked.connect(lambda: self._sched_navigate(-1))
        self._sched_week_label = QLabel()
        self._sched_week_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sched_week_label.setMinimumWidth(max(180, int(200 * s)))
        theme.themed(self._sched_week_label, lambda: (
            f"background:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"font-weight:600; color:{theme.TEXT_DARK};"
        ))
        btn_next = QPushButton("▶")
        btn_next.setFixedSize(max(28, int(32 * s)), max(28, int(32 * s)))
        theme.themed(btn_next, lambda: theme.secondary_btn_style(s))
        btn_next.clicked.connect(lambda: self._sched_navigate(1))
        nav_row.addStretch()
        nav_row.addWidget(btn_prev)
        nav_row.addWidget(self._sched_week_label)
        nav_row.addWidget(btn_next)
        nav_row.addStretch()
        outer.addLayout(nav_row)

        # 7-column calendar (Mon–Sun)
        DAY_NAMES = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
        cal_row = QHBoxLayout()
        cal_row.setSpacing(max(5, int(6 * s)))
        self._sched_day_heads: list[QLabel] = []
        self._sched_day_bodies: list[QVBoxLayout] = []

        for day_name in DAY_NAMES:
            col = QWidget()
            col.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(max(3, int(4 * s)))

            lbl_name = QLabel(day_name)
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            theme.themed(lbl_name, lambda: (
                f"background:transparent; font-size:{max(7, int(8 * s))}pt;"
                f"color:{theme.TEXT_MEDIUM}; font-weight:600;"
            ))
            lbl_num = QLabel("-")
            lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            theme.themed(lbl_num, lambda: (
                f"background:transparent; font-size:{max(9, int(11 * s))}pt;"
                f"font-weight:700; color:{theme.TEXT_DARK};"
            ))
            self._sched_day_heads.append(lbl_num)
            col_layout.addWidget(lbl_name)
            col_layout.addWidget(lbl_num)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            theme.themed(scroll, lambda: (
                f"QScrollArea {{ border:none; background:{theme.PANEL_SURFACE_BG};"
                f"border-radius:{max(6, int(8 * s))}px; }}"
            ))
            body_widget = QWidget()
            body_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            theme.themed(body_widget, lambda: f"background:{theme.PANEL_SURFACE_BG};")
            body_layout = QVBoxLayout(body_widget)
            body_layout.setContentsMargins(
                max(4, int(5 * s)), max(4, int(5 * s)),
                max(4, int(5 * s)), max(4, int(5 * s)),
            )
            body_layout.setSpacing(max(3, int(4 * s)))
            body_layout.addStretch()
            self._sched_day_bodies.append(body_layout)
            scroll.setWidget(body_widget)
            scroll.setMinimumHeight(max(110, int(130 * s)))
            col_layout.addWidget(scroll, 1)
            cal_row.addWidget(col, 1)

        outer.addLayout(cal_row)

        # Legend
        legend_row = QHBoxLayout()
        legend_row.setSpacing(max(16, int(22 * s)))
        legend_row.addStretch()
        for leg_label, leg_color in [
            ("No prazo", theme.PRIMARY),
            ("Atrasada", theme.DANGER),
            ("Prazo alterado", theme.WARNING),
            ("Entregue", theme.SUCCESS),
        ]:
            leg = QHBoxLayout()
            leg.setSpacing(max(6, int(7 * s)))
            dot = QFrame()
            dot.setFixedSize(max(11, int(13 * s)), max(11, int(13 * s)))
            dot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            c = leg_color
            theme.themed(dot, lambda col=c: (
                f"QFrame {{ background:{_rgba(col, 160)}; border-radius:{max(3, int(4 * s))}px; border:none; }}"
            ))
            lbl_leg = QLabel(leg_label)
            cl = leg_color
            theme.themed(lbl_leg, lambda col=cl: (
                f"background:transparent; font-size:{max(9, int(10 * s))}pt;"
                f"font-weight:600; color:{col};"
            ))
            leg.addWidget(dot)
            leg.addWidget(lbl_leg)
            legend_row.addLayout(leg)
        legend_row.addStretch()
        outer.addLayout(legend_row)

        # Detail panel (hidden until chip clicked)
        self._sched_detail_frame = QFrame()
        self._sched_detail_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        theme.themed(self._sched_detail_frame, lambda: (
            f"QFrame {{ background:{theme.PANEL_SURFACE_BG};"
            f"border:1px solid {theme.PANEL_BORDER_SOFT};"
            f"border-radius:{max(8, int(10 * s))}px; }}"
        ))
        self._sched_detail_frame.setVisible(False)
        detail_layout = QVBoxLayout(self._sched_detail_frame)
        detail_layout.setContentsMargins(
            max(12, int(14 * s)), max(10, int(12 * s)),
            max(12, int(14 * s)), max(10, int(12 * s)),
        )
        detail_layout.setSpacing(max(6, int(8 * s)))

        self._sched_detail_title = QLabel()
        theme.themed(self._sched_detail_title, lambda: (
            f"background:transparent; font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; color:{theme.TEXT_DARK};"
        ))
        detail_layout.addWidget(self._sched_detail_title)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(max(16, int(20 * s)))
        self._sched_detail_fields: dict[str, QLabel] = {}
        for field_key in ["Cliente", "Vendedor", "Peso", "Data prevista", "Status"]:
            fld_col = QVBoxLayout()
            fld_col.setSpacing(max(2, int(3 * s)))
            lbl_key = QLabel(field_key)
            theme.themed(lbl_key, lambda: (
                f"background:transparent; font-size:{max(7, int(8 * s))}pt; color:{theme.TEXT_MEDIUM};"
            ))
            val = QLabel("-")
            theme.themed(val, lambda: (
                f"background:transparent; font-size:{max(8, int(9 * s))}pt;"
                f"font-weight:600; color:{theme.TEXT_DARK};"
            ))
            fld_col.addWidget(lbl_key)
            fld_col.addWidget(val)
            fields_row.addLayout(fld_col)
            self._sched_detail_fields[field_key] = val
        fields_row.addStretch()
        detail_layout.addLayout(fields_row)

        detail_btn_row = QHBoxLayout()
        detail_btn_row.setSpacing(max(8, int(10 * s)))
        detail_btn_row.addStretch()
        self._sched_btn_deadline = QPushButton("ALTERAR PRAZO")
        self._sched_btn_deadline.setFixedHeight(max(30, int(34 * s)))
        theme.themed(self._sched_btn_deadline, lambda: _flat_secondary_btn_style(s))
        self._sched_btn_deadline.clicked.connect(self._sched_change_deadline)
        self._sched_btn_delivered = QPushButton("ENTREGUE")
        self._sched_btn_delivered.setFixedHeight(max(30, int(34 * s)))
        theme.themed(self._sched_btn_delivered, lambda: _primary_action_btn_style(s))
        self._sched_btn_delivered.clicked.connect(self._sched_mark_delivered)
        detail_btn_row.addWidget(self._sched_btn_deadline)
        detail_btn_row.addWidget(self._sched_btn_delivered)
        detail_layout.addLayout(detail_btn_row)

        outer.addWidget(self._sched_detail_frame)
        return container

    def _sched_chip_qss(self, row: dict) -> str:
        s = self.scale
        if row.get("delivered_at"):
            bg = _rgba(theme.TEXT_MEDIUM, 22)
            fg = theme.TEXT_MEDIUM
        else:
            delivery_dt = _parse_datetime(row.get("delivery_date"))
            today = local_now().date()
            status = str(row.get("status") or "")
            if delivery_dt and delivery_dt.date() < today:
                bg, fg = _rgba(theme.DANGER, 35), theme.DANGER
            elif status == "prazo_alterado":
                bg, fg = _rgba(theme.WARNING, 35), theme.WARNING
            else:
                bg, fg = _rgba(theme.PRIMARY, 35), theme.PRIMARY
        r = max(5, int(6 * s))
        pv, ph = max(3, int(4 * s)), max(5, int(6 * s))
        fs = max(7, int(9 * s))
        return (
            f"QPushButton {{ background:{bg}; color:{fg}; border-radius:{r}px;"
            f"padding:{pv}px {ph}px; text-align:left; border:none; font-size:{fs}pt; }}"
            f"QPushButton:hover {{ background:{bg}; }}"
        )

    def _render_schedule(self) -> None:
        if not hasattr(self, "_sched_day_heads"):
            return
        today = local_now().date()
        monday = today - _timedelta(days=today.weekday())
        week_start = monday + _timedelta(weeks=self._schedule_week_offset)
        week_dates = [week_start + _timedelta(days=i) for i in range(7)]

        MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        s_d, e_d = week_dates[0], week_dates[6]
        if s_d.month == e_d.month:
            nav_lbl = f"{s_d.day}–{e_d.day} {MONTHS[s_d.month - 1]} {s_d.year}"
        else:
            nav_lbl = f"{s_d.day} {MONTHS[s_d.month - 1]} – {e_d.day} {MONTHS[e_d.month - 1]} {e_d.year}"
        self._sched_week_label.setText(nav_lbl)

        for i, d in enumerate(week_dates):
            head = self._sched_day_heads[i]
            head.setText(str(d.day))
            if d == today:
                theme.themed(head, lambda: (
                    f"background:{_rgba(theme.PRIMARY, 45)};"
                    f"border-radius:{max(12, int(14 * self.scale))}px;"
                    f"font-size:{max(9, int(11 * self.scale))}pt; font-weight:800; color:{theme.PRIMARY};"
                    f"min-width:{max(24, int(28 * self.scale))}px; padding:2px;"
                ))
            else:
                theme.themed(head, lambda: (
                    f"background:transparent; font-size:{max(9, int(11 * self.scale))}pt;"
                    f"font-weight:700; color:{theme.TEXT_DARK};"
                ))
            body = self._sched_day_bodies[i]
            while body.count() > 1:
                item = body.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        date_to_col = {d: i for i, d in enumerate(week_dates)}
        for row in list(self._pending_rows) + list(self._completed_rows):
            delivery_dt = _parse_datetime(row.get("delivery_date"))
            if delivery_dt is None:
                continue
            col_idx = date_to_col.get(delivery_dt.date())
            if col_idx is None:
                continue
            ped = str(row.get("ped_number") or "-")
            client = str(row.get("client_name") or "-")
            chip = QPushButton(f"{ped}\n{client}")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            r = row
            theme.themed(chip, lambda row_ref=r: self._sched_chip_qss(row_ref))
            chip.clicked.connect(lambda checked=False, row_ref=r: self._on_schedule_chip_clicked(row_ref))
            self._sched_day_bodies[col_idx].insertWidget(
                self._sched_day_bodies[col_idx].count() - 1, chip
            )

    def _on_schedule_chip_clicked(self, row: dict) -> None:
        self._schedule_selected_row = row
        ped = str(row.get("ped_number") or "-")
        client = str(row.get("client_name") or "-")
        self._sched_detail_title.setText(f"{ped}  —  {client}")
        self._sched_detail_fields["Cliente"].setText(client)
        self._sched_detail_fields["Vendedor"].setText(str(row.get("vendor_name") or "-"))
        self._sched_detail_fields["Peso"].setText(_format_weight(row.get("weight")))
        self._sched_detail_fields["Data prevista"].setText(_format_date(row.get("delivery_date")))
        status = str(row.get("status") or "")
        self._sched_detail_fields["Status"].setText(
            theme.STATUS_LABELS.get(status, status or "-")
        )
        self._sched_btn_delivered.setEnabled(self._can_mark_row_delivered(row))
        self._sched_btn_deadline.setEnabled(not bool(row.get("delivered_at")))
        self._sched_detail_frame.setVisible(True)

    def _sched_navigate(self, direction: int) -> None:
        self._schedule_week_offset += direction
        self._schedule_selected_row = None
        if hasattr(self, "_sched_detail_frame"):
            self._sched_detail_frame.setVisible(False)
        self._render_schedule()

    def _toggle_active_style(self) -> str:
        s = self.scale
        return (
            f"QPushButton {{ background:{_rgba(theme.PRIMARY, 40)}; color:{theme.PRIMARY};"
            f"border:1px solid {_rgba(theme.PRIMARY, 90)}; border-radius:{max(5, int(6 * s))}px;"
            f"padding:0 {max(10, int(12 * s))}px; font-size:{max(8, int(9 * s))}pt; font-weight:600; }}"
        )

    def _toggle_btn_style(self, mode: str) -> str:
        if getattr(self, "_view_mode", "list") == mode:
            return self._toggle_active_style()
        return theme.secondary_btn_style(self.scale)

    def _set_delivery_view(self, mode: str) -> None:
        self._view_mode = mode
        is_list = mode == "list"
        self.table.setVisible(is_list)
        self._schedule_widget.setVisible(not is_list)
        self._btn_view_list.setStyleSheet(self._toggle_btn_style("list"))
        self._btn_view_sched.setStyleSheet(self._toggle_btn_style("schedule"))
        if not is_list:
            self._render_schedule()

    def _open_create_delivery_dialog(self) -> None:
        s = self.scale
        dlg = QDialog(self)
        dlg.setWindowTitle("Agendar Nova Entrega")
        dlg.setModal(True)
        dlg.setMinimumWidth(max(400, int(440 * s)))
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(max(16, int(20 * s)), max(16, int(20 * s)),
                                  max(16, int(20 * s)), max(16, int(20 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        hdr = QLabel("Agendar Nova Entrega")
        hdr.setStyleSheet(
            f"background:transparent; font-weight:800; font-size:{max(10, int(12 * s))}pt;"
        )
        layout.addWidget(hdr)

        sub = QLabel("Digite o numero do pedido para buscar os dados da requisicao.")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; color:{theme.TEXT_MEDIUM};"
        )
        layout.addWidget(sub)

        # PED input row
        ped_row = QHBoxLayout()
        ped_row.setSpacing(max(6, int(8 * s)))
        ped_input = QComboBox()
        ped_input.setEditable(True)
        ped_input.setFixedHeight(max(34, int(38 * s)))
        ped_input.setStyleSheet(theme.input_style(s))
        ped_input.setPlaceholderText("Ex: 1234")
        btn_search = QPushButton("BUSCAR")
        btn_search.setFixedHeight(max(34, int(38 * s)))
        btn_search.setStyleSheet(theme.secondary_btn_style(s))
        ped_row.addWidget(ped_input, 1)
        ped_row.addWidget(btn_search)
        layout.addLayout(ped_row)

        status_lbl = QLabel("")
        status_lbl.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; color:{theme.TEXT_MEDIUM};"
        )
        status_lbl.setVisible(False)
        layout.addWidget(status_lbl)

        # Result panel (hidden until search)
        result_frame = QFrame()
        result_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        result_frame.setStyleSheet(
            f"QFrame {{ background:{_rgba(theme.PRIMARY, 12)};"
            f"border:1px solid {_rgba(theme.PRIMARY, 50)}; border-radius:{max(8, int(10 * s))}px; }}"
        )
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(max(10, int(12 * s)), max(8, int(10 * s)),
                                         max(10, int(12 * s)), max(8, int(10 * s)))
        result_layout.setSpacing(max(4, int(6 * s)))
        result_frame.setVisible(False)

        result_ped_lbl = QLabel()
        result_ped_lbl.setStyleSheet(
            f"background:transparent; font-weight:700; font-size:{max(9, int(11 * s))}pt;"
        )
        result_layout.addWidget(result_ped_lbl)

        result_fields_row = QHBoxLayout()
        result_fields_row.setSpacing(max(16, int(20 * s)))
        result_field_labels: dict[str, QLabel] = {}
        for fkey in ["Cliente", "Vendedor", "Status"]:
            fc = QVBoxLayout()
            fc.setSpacing(1)
            fl = QLabel(fkey)
            fl.setStyleSheet(
                f"background:transparent; font-size:{max(7, int(8 * s))}pt; color:{theme.TEXT_MEDIUM};"
            )
            fv = QLabel("-")
            fv.setStyleSheet(
                f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
            )
            fc.addWidget(fl)
            fc.addWidget(fv)
            result_fields_row.addLayout(fc)
            result_field_labels[fkey] = fv
        result_fields_row.addStretch()
        result_layout.addLayout(result_fields_row)
        layout.addWidget(result_frame)

        # Date picker (hidden until result shown)
        date_section = QFrame()
        date_section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        date_section.setStyleSheet("QFrame { background:transparent; border:none; }")
        date_sec_layout = QVBoxLayout(date_section)
        date_sec_layout.setContentsMargins(0, 0, 0, 0)
        date_sec_layout.setSpacing(max(4, int(5 * s)))
        date_lbl = QLabel("Data de entrega:")
        date_lbl.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt;"
        )
        from PySide6.QtCore import QDate
        date_edit = QDateEdit()
        date_edit.setDisplayFormat("dd/MM/yyyy")
        date_edit.setCalendarPopup(True)
        date_edit.setFixedHeight(max(34, int(38 * s)))
        date_edit.setStyleSheet(theme.input_style(s))
        date_edit.setDate(QDate.currentDate())
        date_edit.setMinimumDate(QDate.currentDate())
        date_sec_layout.addWidget(date_lbl)
        date_sec_layout.addWidget(date_edit)
        layout.addWidget(date_section)
        date_section.setVisible(False)

        error_lbl = QLabel("")
        error_lbl.setWordWrap(True)
        error_lbl.setStyleSheet(
            f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * s))}pt;"
        )
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(s))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("AGENDAR")
        btn_ok.setStyleSheet(theme.primary_btn_style(s))
        btn_ok.setEnabled(False)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        # State
        _found_row: list[dict] = [{}]

        def _do_search():
            ped_text = str(ped_input.currentText() or "").strip()
            if not ped_text:
                return
            btn_search.setEnabled(False)
            status_lbl.setText("Buscando...")
            status_lbl.setVisible(True)
            result_frame.setVisible(False)
            date_section.setVisible(False)
            btn_ok.setEnabled(False)
            error_lbl.setVisible(False)

            def _on_result(rows):
                btn_search.setEnabled(True)
                if not isinstance(rows, list) or not rows:
                    status_lbl.setText("Nenhum pedido encontrado com esse numero.")
                    return
                # Prefer exact match on ped_number prefix
                matched = next(
                    (r for r in rows if str(r.get("ped_number") or "").split("/")[0] == ped_text),
                    rows[0],
                )
                _found_row[0] = matched
                ped_num = str(matched.get("ped_number") or "-")
                result_ped_lbl.setText(f"Pedido #{ped_num}")
                result_field_labels["Cliente"].setText(str(matched.get("client_name") or "-"))
                result_field_labels["Vendedor"].setText(str(matched.get("vendor_name") or "-"))
                status_val = str(matched.get("status") or "")
                result_field_labels["Status"].setText(
                    theme.STATUS_LABELS.get(status_val, status_val or "-")
                )
                existing_date = matched.get("delivery_date")
                if existing_date:
                    from PySide6.QtCore import QDate as _QD
                    qd = _QD.fromString(str(existing_date)[:10], "yyyy-MM-dd")
                    if qd.isValid():
                        date_edit.setDate(qd)
                status_lbl.setVisible(False)
                result_frame.setVisible(True)
                date_section.setVisible(True)
                btn_ok.setEnabled(True)

            def _on_error(msg):
                btn_search.setEnabled(True)
                status_lbl.setText(f"Erro ao buscar: {msg}")

            thread, worker = _run_in_thread(
                api.lookup_requisitions_by_ped,
                ped_text,
                on_result=_on_result,
                on_error=_on_error,
            )
            thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
            self._threads.append((thread, worker))

        def _do_schedule():
            row = _found_row[0]
            if not row:
                return
            req_id = int(row.get("id") or row.get("source_requisition_id") or 0)
            if not req_id:
                error_lbl.setText("Nao foi possivel identificar o ID da requisicao.")
                error_lbl.setVisible(True)
                return
            new_date = date_edit.date().toString("yyyy-MM-dd")
            btn_ok.setEnabled(False)
            btn_cancel.setEnabled(False)
            error_lbl.setVisible(False)

            def _on_ok(_result):
                QMessageBox.information(
                    self, "Entregas",
                    "Entrega agendada com sucesso. Vendedor notificado.",
                )
                dlg.accept()
                self.refresh()

            def _on_err(msg):
                btn_ok.setEnabled(True)
                btn_cancel.setEnabled(True)
                error_lbl.setText(msg)
                error_lbl.setVisible(True)

            thread, worker = _run_in_thread(
                api.schedule_delivery,
                req_id,
                new_date,
                on_result=_on_ok,
                on_error=_on_err,
            )
            self._track_thread(thread, worker)

        btn_search.clicked.connect(_do_search)
        ped_input.lineEdit().returnPressed.connect(_do_search)
        btn_ok.clicked.connect(_do_schedule)

        dlg.exec()

    def _sched_change_deadline(self) -> None:
        row = self._schedule_selected_row
        if not row:
            return
        if row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ja foi concluida.")
            return
        result = self._ask_delivery_date(row)
        if result is None:
            return
        new_date, reason = result
        self._run_action(
            api.update_delivery_schedule,
            self._row_requisition_id(row),
            new_date,
            reason,
            success_message="Prazo de entrega alterado com sucesso.",
        )

    def _sched_mark_delivered(self) -> None:
        row = self._schedule_selected_row
        if not row:
            return
        if not self._can_mark_row_delivered(row):
            QMessageBox.information(
                self,
                "Entregas",
                "Somente pedidos finalizados ou com prazo alterado podem ser marcados como entregues.",
            )
            return
        if not ask_confirmation(
            self,
            "Entregue",
            self._delivery_confirmation_message([row]),
            yes_text="Sim",
            no_text="Nao",
            default_to_yes=False,
        ):
            return
        self._run_action(
            self._mark_rows_delivered,
            [row],
            success_message=self._delivery_success_message(1),
        )

    def apply_theme(self) -> None:
        """Reaplica o tema na view.

        Otimizado: em vez de findChildren(QWidget) + unpolish/polish em todos
        os widgets (~30-40 ms para ~80 widgets), confiamos no QApplication
        que ja reinvalida o stylesheet global ao trocar tema, e propagamos
        as cores via QPalette no root (filhos herdam automaticamente).

        Mantemos setStyleSheet apenas onde o conteudo realmente depende do
        tema E nao cabe na palette: gradients (botoes), borders com alpha,
        background do error_label com cores DANGER.
        """
        s = self.scale
        bg = theme.CONTENT_BG

        # QPalette no root — cascateia automaticamente para todos os filhos
        # que nao tem palette propria. Cobre cor de texto base, fundos,
        # placeholder e seleção. Custa ~10us, vs ~30ms do polish loop.
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window,          QColor(bg))
        pal.setColor(QPalette.ColorRole.WindowText,      QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Text,            QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.TEXT_MEDIUM))
        pal.setColor(QPalette.ColorRole.Base,            QColor(theme.PANEL_SURFACE_BG))
        pal.setColor(QPalette.ColorRole.Highlight,       QColor(theme.PANEL_NEON_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
        self.setPalette(pal)

        # Backgrounds combinados em uma unica chamada (era 4 antes)
        self.setStyleSheet(
            f"QWidget#deliveryCenterView, QWidget#deliveryCenterContent {{ background:{bg}; }}"
            f"QScrollArea {{ border:none; background:{bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")

        # NOTE: refresh_btn, btn_change_deadline, btn_mark_delivered,
        # btn_cancel_delivered, date_label, updated_label e os cards do
        # _make_card foram migrados para theme.themed() no __init__.
        # O registry global os reaplica em set_dark() automaticamente.

        # Error label — cores DANGER (alpha) precisam ser regeneradas
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )

        # Tabelas — helper centralizado (theme.neon_table_qss + apply_neon_table_palette)
        self._apply_table_style(self.table)
        self._apply_table_style(self.completed_table)

        # Toggle buttons — re-aplica estilos ativos/inativos apos troca de tema
        if hasattr(self, "_btn_view_list"):
            self._btn_view_list.setStyleSheet(self._toggle_btn_style("list"))
            self._btn_view_sched.setStyleSheet(self._toggle_btn_style("schedule"))

        # Repaint pontual — substitui o loop polish que custava 30-40ms.
        # O QApplication.setStyleSheet(global) ja foi atualizado no
        # _on_theme_toggle do main_window, entao os property selectors do QSS
        # global (QLabel[muted='1'], QFrame[theme_bg='card']) ja sao re-resolvidos.
        self.update()
