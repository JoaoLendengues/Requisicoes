"""Central de pedidos com listas operacionais e acesso ao PDF do pedido finalizado."""

import os
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
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
from ..core.resolution import res
from ..services.pdf_generator import HAS_REPORTLAB, generate_pdf
from .requisition_form import _run_in_thread


_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_METRIC_ICON_FILES = {
    "pedidos_aguardando_recebimento": "aguardando_recebimento.png",
    "pedidos_em_producao": "pedidos_em_producao.png",
    "pedidos_finalizados": "pedidos_concluidos.png",
    "pedidos_cancelados": "pedidos_cancelados.png",
    "pedidos_atrasados": "pedidos_atrasados.png",
    "tempo_medio_producao_segundos": "tempo_medio_producao.png",
}


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
    card.setObjectName("orderCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    bg = background or theme.CARD_BG
    border = f"1px solid {border_color}" if border_color else "none"
    hover = hover_background or bg
    card.setStyleSheet(
        f"QFrame#orderCenterCard {{"
        f"  background:{bg}; border:{border}; border-radius:{radius}px;"
        f"}}"
        f"QFrame#orderCenterCard:hover {{"
        f"  background:{hover}; border:{border};"
        f"}}"
    )
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _metric_icon_path(key: str) -> Path | None:
    filename = _METRIC_ICON_FILES.get(key)
    if not filename:
        return None
    path = _ICON_DIR / filename
    return path if path.exists() else None


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


def _format_duration(seconds: object) -> str:
    if seconds in (None, "", "-"):
        return "-"
    try:
        total_seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return "-"

    if total_seconds < 60:
        return f"{total_seconds}s"

    minutes, _ = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts[:2]) or "0m"


def _format_waiting_minutes(minutes: object) -> str:
    try:
        total_minutes = max(0, int(minutes))
    except (TypeError, ValueError):
        return "-"

    if total_minutes < 60:
        return f"{total_minutes} min"

    hours, remaining = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining:02d}m"

    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}h"


class OrderCenterWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.get_order_center())
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class OrderCenterView(QWidget):
    open_requisition = Signal(int)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._rows: dict[str, list[dict]] = {
            "aguardando_recebimento": [],
            "em_producao": [],
            "finalizados": [],
            "cancelados": [],
            "atrasados": [],
        }
        self._metric_labels: dict[str, QLabel] = {}
        self._tables: dict[str, QTableWidget] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("orderCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#orderCenterView {{ background:{page_bg}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Central de Pedidos")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Acompanhamento operacional dos pedidos por etapa, ritmo e pendências da produção."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(16, int(18 * s)),
            hover_background=theme.CARD_BG,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        right_col.addWidget(info_card)
        right_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(right_col)
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("orderCenterContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(
            f"QWidget#orderCenterContent {{ background:{page_bg}; }}"
        )
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(3):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_aguardando_recebimento", theme.WARNING, "Aguardando Recebimento", "Pedidos pendentes de confirmação da produção."),
            ("pedidos_em_producao", theme.PRIMARY, "Pedidos em Produção", "Ordens que já entraram na esteira produtiva."),
            ("pedidos_finalizados", theme.SUCCESS, "Pedidos Finalizados", "Pedidos concluídos e prontos para consulta."),
            ("pedidos_cancelados", theme.DANGER, "Pedidos Cancelados", "Cancelamentos registrados na operação."),
            ("pedidos_atrasados", theme.DANGER, "Pedidos Atrasados", "Pedidos com prazo vencido e ainda abertos."),
            ("tempo_medio_producao_segundos", theme.BORDER_COLOR, "Tempo Médio de Produção", "Indicador médio de conclusão da produção."),
        ]
        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                index // 3,
                index % 3,
            )

        grid_top = QGridLayout()
        grid_top.setHorizontalSpacing(max(12, int(16 * s)))
        grid_top.setVerticalSpacing(max(12, int(16 * s)))
        grid_top.setColumnStretch(0, 1)
        grid_top.setColumnStretch(1, 1)
        layout.addLayout(grid_top)
        grid_top.addWidget(self._build_section("Pedidos aguardando recebimento", "aguardando_recebimento"), 0, 0)
        grid_top.addWidget(self._build_section("Pedidos em produção", "em_producao"), 0, 1)
        grid_top.addWidget(self._build_section("Pedidos finalizados", "finalizados", pdf_action=True), 1, 0)
        grid_top.addWidget(self._build_section("Pedidos cancelados", "cancelados"), 1, 1)
        layout.addWidget(self._build_section("Pedidos atrasados", "atrasados"))
        layout.addStretch()

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
            f"color:{theme.TEXT_DARK}; font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value.setWordWrap(True)

        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper = QLabel(helper_text)
        helper.setWordWrap(True)
        helper.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:{color}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(max(10, int(12 * s)))
        header_row.addWidget(value, 1, Qt.AlignmentFlag.AlignTop)

        icon_label = self._build_metric_icon_label(key)
        if icon_label is not None:
            header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addStretch()
        layout.addWidget(accent_line)
        self._metric_labels[key] = value
        return card

    def _build_metric_icon_label(self, key: str) -> QLabel | None:
        icon_path = _metric_icon_path(key)
        if icon_path is None:
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

    def _build_section(self, title_text: str, key: str, pdf_action: bool = False) -> QFrame:
        s = self.scale
        section_meta = {
            "aguardando_recebimento": (
                "Pedidos aguardando retorno e confirmação da produção.",
                theme.WARNING,
            ),
            "em_producao": (
                "Ordens em andamento com registro de recebimento na fabrica.",
                theme.PRIMARY,
            ),
            "finalizados": (
                "Pedidos concluídos com PDF individual e tempo médio de produção.",
                theme.SUCCESS,
            ),
            "cancelados": (
                "Histórico de cancelamentos para consulta rápida da operação.",
                theme.DANGER,
            ),
            "atrasados": (
                "Pedidos fora do prazo para acompanhamento imediato.",
                theme.BORDER_COLOR,
            ),
        }
        subtitle_text, accent_color = section_meta[key]

        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:{accent_color}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        layout.addWidget(accent)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(max(2, int(3 * s)))
        title = QLabel(title_text)
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{theme.TEXT_DARK}; background:transparent;"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)

        btn_open = QPushButton("ABRIR PEDIDO")
        btn_open.setFixedHeight(max(34, int(38 * s)))
        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_open.clicked.connect(lambda: self._open_selected(key))
        title_row.addWidget(btn_open)

        if pdf_action:
            btn_pdf = QPushButton("VER PDF")
            btn_pdf.setFixedHeight(max(34, int(38 * s)))
            btn_pdf.setStyleSheet(_primary_action_btn_style(s))
            btn_pdf.clicked.connect(self._open_selected_pdf)
            title_row.addWidget(btn_pdf)

        layout.addLayout(title_row)

        if pdf_action:
            self.avg_finished_label = QLabel("Tempo médio: -")
            self.avg_finished_label.setStyleSheet(
                f"color:{theme.TEXT_MEDIUM}; font-size:{max(7, int(8 * s))}pt; font-weight:600;"
            )
            layout.addWidget(self.avg_finished_label)

        table = self._create_table_for_section(key)
        self._tables[key] = table
        layout.addWidget(table, 1)
        return card

    def _create_table_for_section(self, key: str) -> QTableWidget:
        headers_by_section = {
            "aguardando_recebimento": ["PED", "CLIENTE", "VENDEDOR", "ENTREGA", "AGUARDANDO"],
            "em_producao": ["PED", "CLIENTE", "VENDEDOR", "RECEBIDO EM", "DESTINO"],
            "finalizados": ["PED", "CLIENTE", "FINALIZADO EM", "TEMPO", "DESTINO"],
            "cancelados": ["PED", "CLIENTE", "VENDEDOR", "CANCELADO EM"],
            "atrasados": ["PED", "CLIENTE", "ENTREGA", "ATRASO", "STATUS"],
        }

        stretch_columns = {
            "aguardando_recebimento": {1, 2},
            "em_producao": {1, 2},
            "finalizados": {1},
            "cancelados": {1, 2},
            "atrasados": {1},
        }

        headers = headers_by_section[key]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.doubleClicked.connect(lambda index, section=key: self._open_row(section, index.row()))

        s = self.scale
        header = table.horizontalHeader()
        for col in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col in stretch_columns[key]
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(col, mode)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * s)))
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
        # Sobrescreve a paleta do sistema (Windows ignora QSS em QTableView items).
        # QPalette.Base = fundo das células normais.
        # QPalette.AlternateBase = fundo das linhas alternadas.
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
        table.setMinimumHeight(max(220, int(240 * s)))
        return table

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()
        worker = OrderCenterWorker()
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
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.error_label.setText(f"Não foi possível carregar a central de pedidos.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta inválida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        for key, label in self._metric_labels.items():
            value = stats.get(key)
            if key == "tempo_medio_producao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        current = _parse_datetime(payload.get("generated_at")) or local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        if hasattr(self, "avg_finished_label"):
            self.avg_finished_label.setText(
                f"Tempo médio: {_format_duration(stats.get('tempo_medio_producao_segundos'))}"
            )

        for key in self._rows:
            rows = payload.get(key) or []
            self._rows[key] = rows if isinstance(rows, list) else []
            self._fill_section_table(key)

    def _fill_section_table(self, key: str):
        table = self._tables[key]
        table.clearSpans()
        table.setRowCount(0)
        rows = self._rows.get(key, [])

        if not rows:
            self._set_empty_message(table, "Nenhum pedido encontrado nesta etapa.")
            return

        for row_data in rows:
            if not isinstance(row_data, dict):
                continue

            row = table.rowCount()
            table.insertRow(row)

            if key == "aguardando_recebimento":
                values = [
                    str(row_data.get("ped_number") or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_date(row_data.get("delivery_date")),
                    _format_waiting_minutes(row_data.get("waiting_minutes")),
                ]
            elif key == "em_producao":
                values = [
                    str(row_data.get("ped_number") or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_datetime(row_data.get("received_at")),
                    str(row_data.get("destination") or "-"),
                ]
            elif key == "finalizados":
                values = [
                    str(row_data.get("ped_number") or "-"),
                    str(row_data.get("client_name") or "-"),
                    _format_datetime(row_data.get("finished_at")),
                    _format_duration(row_data.get("production_time_seconds")),
                    str(row_data.get("destination") or "-"),
                ]
            elif key == "cancelados":
                values = [
                    str(row_data.get("ped_number") or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_datetime(row_data.get("canceled_at")),
                ]
            else:
                values = [
                    str(row_data.get("ped_number") or "-"),
                    str(row_data.get("client_name") or "-"),
                    _format_date(row_data.get("delivery_date")),
                    f"{row_data.get('delay_days') or 0} dia(s)",
                    str(row_data.get("status") or "-"),
                ]

            for col, value in enumerate(values):
                if key == "atrasados" and col == 4:
                    status = str(row_data.get("status") or "")
                    badge = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    color_map = {
                        "em_andamento": theme.PRIMARY_HOVER,
                        "aguardando_recebimento": theme.WARNING,
                        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
                        "em_producao": theme.PRIMARY,
                        "cancelada": theme.DANGER,
                    }
                    color = color_map.get(status, theme.BORDER_COLOR)
                    badge.setStyleSheet(
                        f"background:{_rgba(color, 30)}; color:{color}; border-radius:999px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(row, col, badge)
                else:
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, col, item)

    def _set_empty_message(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(theme.TEXT_MEDIUM))
        table.setItem(0, 0, item)

    def _selected_row(self, key: str) -> dict | None:
        table = self._tables[key]
        row = table.currentRow()
        rows = self._rows.get(key, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _open_row(self, key: str, row_index: int):
        rows = self._rows.get(key, [])
        if 0 <= row_index < len(rows):
            self.open_requisition.emit(int(rows[row_index]["id"]))

    def _open_selected(self, key: str):
        row = self._selected_row(key)
        if not row:
            QMessageBox.information(self, "Central de pedidos", "Selecione um pedido primeiro.")
            return
        self.open_requisition.emit(int(row["id"]))

    def _open_selected_pdf(self):
        row = self._selected_row("finalizados")
        if not row:
            QMessageBox.information(
                self,
                "Central de pedidos",
                "Selecione um pedido finalizado para visualizar o PDF.",
            )
            return

        req_id = int(row["id"])
        thread, worker = _run_in_thread(
            api.get_requisition,
            req_id,
            on_result=self._open_pdf_for_requisition,
            on_error=lambda msg: QMessageBox.critical(self, "Central de pedidos", msg),
        )
        self._threads.append((thread, worker))

    def _open_pdf_for_requisition(self, req: dict):
        folder = res.pdf_folder.strip()
        if not folder:
            QMessageBox.warning(
                self,
                "Central de pedidos",
                "Defina a pasta de PDFs nas configurações antes de abrir o arquivo.",
            )
            return

        if not HAS_REPORTLAB:
            QMessageBox.warning(
                self,
                "Central de pedidos",
                "A geração de PDF não está disponível neste ambiente.",
            )
            return

        client = {
            "name": req.get("client_name"),
            "phone": req.get("phone"),
        }
        canvas = (req.get("canvas") or {}).get("json_data") or "{}"

        try:
            pdf_path = generate_pdf(req, client, req.get("obs") or "", folder, canvas)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Central de pedidos",
                f"Não foi possível gerar o PDF deste pedido.\n\n{exc}",
            )
            return

        try:
            if os.name == "nt":
                os.startfile(pdf_path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{pdf_path}")
        except Exception as exc:
            QMessageBox.information(
                self,
                "Central de pedidos",
                f"PDF gerado em:\n{pdf_path}\n\nNão foi possível abrir automaticamente: {exc}",
            )
