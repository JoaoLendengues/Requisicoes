"""Tela de entregas com indicadores, agenda e aÃ§Ãµes operacionais."""

from __future__ import annotations

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
    card.setObjectName("deliveryCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#deliveryCenterCard {{ border-radius:{radius}px; }}")
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
        f"QPushButton:pressed {{ background:#E7EEF7; }}"
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
        f"QPushButton:pressed {{ background:#152D49; }}"
        f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
    )


def _format_weight(value: object) -> str:
    try:
        weight_value = float(value or 0.0)
    except (TypeError, ValueError):
        return "-"
    return f"{weight_value:.2f}".replace(".", ",")


def _status_badge_color(status: str) -> str:
    color_map = {
        "em_andamento": theme.PRIMARY_HOVER,
        "prazo_alterado": theme.STATUS_COLORS.get("prazo_alterado", theme.WARNING),
        "entregue": theme.STATUS_COLORS.get("entregue", theme.SUCCESS),
        "aguardando_recebimento": theme.WARNING,
        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
        "aguardando_faturamento": theme.STATUS_COLORS.get("aguardando_faturamento", theme.WARNING),
        "em_producao": theme.PRIMARY,
        "faturado": theme.STATUS_COLORS.get("faturado", theme.SUCCESS),
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
        self._row_by_id: dict[int, dict] = {}
        self._completed_row_by_id: dict[int, dict] = {}
        self._metric_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("deliveryCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#deliveryCenterView {{ background:{page_bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Entregas")
        title.setStyleSheet(f"font-size:{max(18, int(24 * s))}pt; font-weight:800;")
        subtitle = QLabel(
            "Agenda operacional de entregas com acompanhamento de prazos, status e conclusao."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        status_col = QVBoxLayout()
        status_col.setSpacing(max(6, int(8 * s)))
        self.date_label = QLabel(_format_header_date())
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.date_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:700; color:{theme.TEXT_MEDIUM};"
        )
        self.updated_label = QLabel("Atualizado em -")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; color:{theme.TEXT_MEDIUM};"
        )
        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(34, int(38 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
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
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{page_bg}; }}")
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("deliveryCenterContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#deliveryCenterContent {{ background:{page_bg}; }}"
        )
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
        section_title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        section_subtitle = QLabel(
            "Selecione uma entrega para alterar o prazo ou registrar a conclusao."
        )
        section_subtitle.setWordWrap(True)
        section_subtitle.setProperty("muted", "1")
        section_subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        title_col.addWidget(section_title)
        title_col.addWidget(section_subtitle)
        title_row.addLayout(title_col, 1)

        self.btn_change_deadline = QPushButton("ALTERAR PRAZO")
        self.btn_change_deadline.setFixedHeight(max(34, int(38 * s)))
        self.btn_change_deadline.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_change_deadline.clicked.connect(self._change_selected_deadline)
        title_row.addWidget(self.btn_change_deadline)

        self.btn_mark_delivered = QPushButton("ENTREGUE")
        self.btn_mark_delivered.setFixedHeight(max(34, int(38 * s)))
        self.btn_mark_delivered.setStyleSheet(_primary_action_btn_style(s))
        self.btn_mark_delivered.clicked.connect(self._mark_selected_delivered)
        title_row.addWidget(self.btn_mark_delivered)

        card_layout.addLayout(title_row)

        self.table = self._create_table(self._open_row)
        card_layout.addWidget(self.table, 1)
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
        completed_title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        completed_subtitle = QLabel("Pedidos com entrega concluida.")
        completed_subtitle.setWordWrap(True)
        completed_subtitle.setProperty("muted", "1")
        completed_subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        completed_layout.addWidget(completed_title)
        completed_layout.addWidget(completed_subtitle)

        completed_actions_row = QHBoxLayout()
        completed_actions_row.setContentsMargins(0, 0, 0, 0)
        completed_actions_row.setSpacing(max(8, int(10 * s)))
        completed_actions_row.addStretch()
        self.btn_cancel_delivered = QPushButton("CANCELAR ENTREGA")
        self.btn_cancel_delivered.setFixedHeight(max(34, int(38 * s)))
        self.btn_cancel_delivered.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_cancel_delivered.clicked.connect(self._cancel_selected_delivered)
        completed_actions_row.addWidget(self.btn_cancel_delivered)
        completed_layout.addLayout(completed_actions_row)

        self.completed_table = self._create_table(self._open_completed_row)
        completed_layout.addWidget(self.completed_table, 1)
        content_layout.addWidget(completed_card, 1)
        content_layout.addStretch()

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
        value.setStyleSheet(
            f"font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value.setWordWrap(True)

        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper = QLabel(helper_text)
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

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
            f"QHeaderView::section:hover {{ background:{theme.PRIMARY_HOVER}; }}"
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
        self.btn_change_deadline.setEnabled(not loading)
        self.btn_mark_delivered.setEnabled(not loading)
        if hasattr(self, "btn_cancel_delivered"):
            self.btn_cancel_delivered.setEnabled(not loading)
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

        current = _parse_datetime(payload.get("generated_at")) or local_now()
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

    def _fill_table(
        self,
        table: QTableWidget,
        rows: list[dict],
        row_map: dict[int, dict],
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

            req_id = int(row_data.get("id") or 0)
            if req_id:
                row_map[req_id] = row_data

            ped_raw = row_data.get("ped_number")
            try:
                ped_sort = int(ped_raw)
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
                    hidden_item = SortableItem(value, sort_key=status)
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
                if col == 0 and req_id:
                    item.setData(Qt.ItemDataRole.UserRole, req_id)
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

    def _selected_row(self) -> dict | None:
        row_index = self.table.currentRow()
        if row_index < 0:
            return None
        item = self.table.item(row_index, 0)
        if item is None:
            return None
        req_id = item.data(Qt.ItemDataRole.UserRole)
        if not req_id:
            return None
        return self._row_by_id.get(int(req_id))

    def _selected_completed_row(self) -> dict | None:
        row_index = self.completed_table.currentRow()
        if row_index < 0:
            return None
        item = self.completed_table.item(row_index, 0)
        if item is None:
            return None
        req_id = item.data(Qt.ItemDataRole.UserRole)
        if not req_id:
            return None
        return self._completed_row_by_id.get(int(req_id))

    def _open_row(self, row_index: int):
        item = self.table.item(row_index, 0)
        if item is None:
            return
        req_id = item.data(Qt.ItemDataRole.UserRole)
        if req_id:
            self.open_requisition.emit(int(req_id))

    def _open_completed_row(self, row_index: int):
        item = self.completed_table.item(row_index, 0)
        if item is None:
            return
        req_id = item.data(Qt.ItemDataRole.UserRole)
        if req_id:
            self.open_requisition.emit(int(req_id))

    def _change_selected_deadline(self):
        row = self._selected_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione um pedido primeiro.")
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
            int(row["id"]),
            new_date,
            reason,
            success_message="Prazo de entrega alterado com sucesso.",
        )

    def _mark_selected_delivered(self):
        row = self._selected_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione um pedido primeiro.")
            return
        if row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ja foi concluida.")
            return
        if not QMessageBox.question(
            self,
            "Entregue",
            f"Confirmar a entrega do pedido {row.get('ped_number') or '-'}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            return

        self._run_action(
            api.mark_delivery_delivered,
            int(row["id"]),
            success_message="Entrega registrada com sucesso.",
        )

    def _cancel_selected_delivered(self):
        row = self._selected_completed_row()
        if not row:
            QMessageBox.information(self, "Entregas", "Selecione uma entrega realizada primeiro.")
            return

        if not row.get("delivered_at"):
            QMessageBox.information(self, "Entregas", "Esta entrega ainda nao foi concluida.")
            return

        reason = self._ask_delivery_cancel_reason(row)
        if not reason:
            return

        self._run_action(
            api.cancel_delivery_delivered,
            int(row["id"]),
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
        header.setStyleSheet(f"font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
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
        header.setStyleSheet(f"font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        info = QLabel("Selecione o motivo para cancelar a entrega e retornar para a agenda.")
        info.setWordWrap(True)
        info.setProperty("muted", "1")
        info.setStyleSheet(f"font-size:{max(8, int(9 * self.scale))}pt;")
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
        error_lbl.setStyleSheet(f"color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
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

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#deliveryCenterView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(
            f"QWidget#deliveryCenterContent {{ background:{bg}; }}"
        )
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_change_deadline.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_mark_delivered.setStyleSheet(_primary_action_btn_style(s))
        if hasattr(self, "btn_cancel_delivered"):
            self.btn_cancel_delivered.setStyleSheet(_flat_secondary_btn_style(s))
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        self._apply_table_style(self.table)
        self._apply_table_style(self.completed_table)

