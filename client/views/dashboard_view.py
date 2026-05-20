"""Painel gerencial com indicadores operacionais e alertas."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme


DASH_BG = "#F4F7FB"
DASH_SURFACE = "#FFFFFF"
DASH_PRIMARY = "#1E3A5F"
DASH_SECONDARY = "#27496D"
DASH_SUCCESS = "#16A34A"
DASH_DANGER = "#DC2626"
DASH_WARNING = "#F59E0B"
DASH_SLATE = "#334155"
DASH_TEXT = "#0F172A"
DASH_MUTED = "#64748B"
DASH_BORDER = "#E2E8F0"
DASH_ROW_ALT = "#F8FBFF"

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_METRIC_ICON_FILES = {
    "pedidos_em_producao": "pedidos_em_producao.png",
    "pedidos_em_atraso": "pedidos_atrasados.png",
    "pedidos_finalizados_hoje": "pedidos_concluidos.png",
    "pedidos_sem_confirmacao_1h": "aguardando_recebimento.png",
    "tempo_medio_finalizacao_segundos": "tempo_medio_producao.png",
}


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(DASH_TEXT)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


def _make_shadow_card(
    scale: float,
    background: str,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    card = QFrame()
    card.setObjectName("dashboardCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    border = f"1px solid {border_color}" if border_color else "none"
    hover = hover_background or background
    card.setStyleSheet(
        f"QFrame#dashboardCard {{"
        f"  background:{background}; border:{border}; border-radius:{radius}px;"
        f"}}"
        f"QFrame#dashboardCard:hover {{"
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
        f"  background:{DASH_SURFACE}; color:{DASH_PRIMARY};"
        f"  border:1px solid {DASH_BORDER}; outline:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{DASH_ROW_ALT}; border-color:{_rgba(DASH_PRIMARY, 70)}; }}"
        f"QPushButton:pressed {{ background:#E7EEF7; }}"
        f"QPushButton:disabled {{ background:#E5EAF2; color:#97A3B6; border-color:#E5EAF2; }}"
    )


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _format_datetime(value: object) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "-"
    return parsed.strftime("%d/%m/%Y %H:%M")


def _format_date(value: object) -> str:
    if not value:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    if "T" in text:
        return _format_datetime(text)[:10]
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return text[:10]


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

    hours, remaining_minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining_minutes:02d}m"

    days, remaining_hours = divmod(hours, 24)
    return f"{days}d {remaining_hours:02d}h"


def _format_header_date(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y")


class DashWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.get_management_dashboard())
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class DashboardView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._metric_labels: dict[str, QLabel] = {}
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        s = self.scale
        page_bg = DASH_BG
        self.setObjectName("dashboardView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#dashboardView {{ background:{page_bg}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))

        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Painel de Producao")
        title.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Visao executiva da operacao industrial com indicadores, alertas e ritmo de producao."
        )
        subtitle.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(max(10, int(12 * s)))

        info_card = _make_shadow_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(16, int(18 * s)),
            hover_background=DASH_SURFACE,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
        )
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt;"
        )
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        header_right.addWidget(info_card)
        header_right.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(header_right)

        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(DASH_DANGER, 18)}; color:{DASH_DANGER};"
            f"border:1px solid {_rgba(DASH_DANGER, 48)}; border-radius:16px;"
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
        content.setObjectName("dashboardContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(
            f"QWidget#dashboardContent {{ background:{page_bg}; }}"
        )
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_em_producao", DASH_PRIMARY, "Pedidos em Producao", "Requisicoes recebidas pela producao."),
            ("pedidos_em_atraso", DASH_DANGER, "Pedidos em Atraso", "Pedidos abertos com prazo vencido."),
            ("pedidos_finalizados_hoje", DASH_SUCCESS, "Finalizados Hoje", "Finalizacoes registradas no dia."),
            ("requisicoes_feitas_no_dia", DASH_SECONDARY, "Requisicoes do Dia", "Novas requisicoes criadas hoje."),
            ("producao_pinheiro_industria", DASH_PRIMARY, "Producao Pinheiro Industria", "Fila ativa enviada para esse destino."),
            ("producao_ar", DASH_SECONDARY, "Producao da A&R", "Fila ativa enviada para esse destino."),
            ("pedidos_sem_confirmacao_1h", DASH_WARNING, "Sem Confirmacao", "Aguardando retorno ha mais de 1 hora."),
            ("tempo_medio_finalizacao_segundos", DASH_SLATE, "Tempo Medio de Finalizacao", "Media entre recebimento e finalizacao."),
        ]

        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            row = index // 4
            col = index % 4
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                row,
                col,
            )

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(max(12, int(16 * s)))
        secondary_row.addWidget(
            self._build_section_card(
                "Vendedores com Mais Requisicoes",
                "Ranking geral por volume de requisicoes emitidas.",
                self._build_top_vendors_table(),
                DASH_PRIMARY,
            ),
            1,
        )
        secondary_row.addWidget(
            self._build_section_card(
                "Pedidos sem Confirmacao",
                "Pedidos aguardando retorno da producao por mais de 1 hora.",
                self._build_alerts_table(),
                DASH_WARNING,
            ),
            1,
        )
        layout.addLayout(secondary_row)

        layout.addWidget(
            self._build_section_card(
                "Ultimas Requisicoes",
                "Visao rapida das requisicoes mais recentes do sistema.",
                self._build_recent_table(),
                DASH_SLATE,
            )
        )
        layout.addStretch()

    def _build_metric_card(
        self,
        color: str,
        title: str,
        helper_text: str,
        key: str,
    ) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("-")
        value_label.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value_label.setWordWrap(True)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:{color}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(max(10, int(12 * s)))
        header_row.addWidget(value_label, 1, Qt.AlignmentFlag.AlignTop)

        icon_label = self._build_metric_icon_label(key)
        if icon_label is not None:
            header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addStretch()
        layout.addWidget(accent_line)

        self._metric_labels[key] = value_label
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

    def _build_section_card(self, title: str, subtitle: str, body: QWidget, accent_color: str) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
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

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(10, int(12 * s))}pt; font-weight:800;"
        )

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt;"
        )

        layout.addWidget(accent)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(body, 1)
        return card

    def _create_table(self, headers: list[str], stretch_columns: set[int]) -> QTableWidget:
        s = self.scale
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)

        header = table.horizontalHeader()
        for index in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if index in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(index, mode)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * s)))
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))

        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{DASH_SURFACE};"
            f"  alternate-background-color:{DASH_ROW_ALT};"
            f"  color:{DASH_SLATE}; border-radius:14px;"
            f"  gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{DASH_PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(DASH_PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{DASH_ROW_ALT}; }}"
        )
        return table

    def _build_top_vendors_table(self) -> QTableWidget:
        self.top_vendors_table = self._create_table(
            ["#", "VENDEDOR", "REQUISICOES"],
            {1},
        )
        self.top_vendors_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.top_vendors_table

    def _build_alerts_table(self) -> QTableWidget:
        self.alerts_table = self._create_table(
            ["PED", "CLIENTE", "DESTINO", "AGUARDANDO"],
            {1},
        )
        self.alerts_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.alerts_table

    def _build_recent_table(self) -> QTableWidget:
        self.recent_table = self._create_table(
            ["PED", "CLIENTE", "VENDEDOR", "EMISSAO", "STATUS", "DESTINO"],
            {1, 2},
        )
        self.recent_table.setMinimumHeight(max(260, int(300 * self.scale)))
        return self.recent_table

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()

        worker = DashWorker()
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
        self.error_label.setText(f"Nao foi possivel carregar o painel.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta invalida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        for key, label in self._metric_labels.items():
            value = stats.get(key)
            if key == "tempo_medio_finalizacao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        generated_at = _parse_datetime(payload.get("generated_at"))
        self.date_label.setText(_format_header_date(generated_at or datetime.now()))
        self.updated_label.setText(
            f"Atualizado em {_format_datetime(payload.get('generated_at'))}"
        )

        self._fill_top_vendors_table(payload.get("top_vendors") or [])
        self._fill_alerts_table(payload.get("receipt_alerts") or [])
        self._fill_recent_table(payload.get("recent_requisitions") or [])

    def _fill_top_vendors_table(self, rows: object):
        table = self.top_vendors_table
        table.clearSpans()
        table.setRowCount(0)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhum vendedor encontrado.")
            return

        for index, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue
            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(index),
                str(row.get("vendor_name") or "-"),
                str(row.get("requisition_count") or 0),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(line, col, item)

    def _fill_alerts_table(self, rows: object):
        table = self.alerts_table
        table.clearSpans()
        table.setRowCount(0)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhum pedido aguardando confirmacao ha mais de 1 hora.")
            return

        for row in items:
            if not isinstance(row, dict):
                continue
            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("destination") or "-"),
                _format_waiting_minutes(row.get("waiting_minutes")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(line, col, item)

    def _fill_recent_table(self, rows: object):
        table = self.recent_table
        table.clearSpans()
        table.setRowCount(0)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhuma requisicao recente encontrada.")
            return

        for row in items:
            if not isinstance(row, dict):
                continue

            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("vendor_name") or "-"),
                _format_date(row.get("emission_date")),
                str(row.get("status") or "-"),
                str(row.get("destination") or "-"),
            ]

            for col, value in enumerate(values):
                if col == 4:
                    status = str(row.get("status") or "")
                    label = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    color_map = {
                        "em_andamento": DASH_SECONDARY,
                        "aguardando_recebimento": DASH_WARNING,
                        "em_producao": DASH_PRIMARY,
                        "cancelada": DASH_DANGER,
                    }
                    color = color_map.get(status, DASH_SLATE)
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{_rgba(color, 30)}; color:{color}; border-radius:999px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(line, col, label)
                else:
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)

    def _set_empty_message(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(DASH_MUTED))
        table.setItem(0, 0, item)
