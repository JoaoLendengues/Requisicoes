"""Painel gerencial com indicadores operacionais e alertas."""

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


_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_METRIC_ICON_FILES = {
    "pedidos_em_producao": "pedidos_em_producao.png",
    "pedidos_em_atraso": "pedidos_atrasados.png",
    "pedidos_finalizados_hoje": "pedidos_concluidos.png",
    "producao_pinheiro_industria": "producao_pinheiro_industria.png",
    "producao_ar": "producao_ar.png",
    "requisicoes_feitas_no_dia": "requisicoes_do_dia.png",
    "pedidos_sem_confirmacao_1h": "aguardando_recebimento.png",
    "tempo_medio_finalizacao_segundos": "tempo_medio_producao.png",
}


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _tint(color: str, alpha: int = 40) -> str:
    """Cor sólida equivalente a rgba(color, alpha) sobre fundo branco."""
    c = QColor(color)
    a = alpha / 255.0
    r = round(c.red() * a + 255 * (1 - a))
    g = round(c.green() * a + 255 * (1 - a))
    b = round(c.blue() * a + 255 * (1 - a))
    return f"#{r:02x}{g:02x}{b:02x}"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.TEXT_DARK)
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
        f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
        f"  border:1px solid {theme.BORDER_COLOR}; outline:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{_rgba(theme.PRIMARY, 70)}; }}"
        f"QPushButton:pressed {{ background:#E7EEF7; }}"
        f"QPushButton:disabled {{ background:#E5EAF2; color:#97A3B6; border-color:#E5EAF2; }}"
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

    hours, remaining_minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining_minutes:02d}m"

    days, remaining_hours = divmod(hours, 24)
    return f"{days}d {remaining_hours:02d}h"


def _machine_status_label(value: object) -> str:
    status = str(value or "").strip().casefold()
    if status == "funcionando":
        return "Funcionando"
    if status == "manutencao":
        return "Manutencao"
    return str(value or "-") or "-"


def _machine_status_color(value: object) -> str:
    status = str(value or "").strip().casefold()
    if status == "funcionando":
        return theme.SUCCESS
    if status == "manutencao":
        return theme.WARNING
    return theme.BORDER_COLOR


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
        page_bg = theme.CONTENT_BG
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
        title = QLabel("Painel de Produção")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Visão executiva da operação industrial com indicadores, alertas e ritmo de produção."
        )
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * s))}pt;"
        )
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(max(10, int(12 * s)))

        info_card = _make_shadow_card(
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
        header_right.addWidget(info_card)
        header_right.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(header_right)

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
            ("pedidos_em_producao", theme.PRIMARY, "Pedidos em Produção", "Requisições recebidas pela produção."),
            ("pedidos_em_atraso", theme.DANGER, "Pedidos em Atraso", "Pedidos abertos com prazo vencido."),
            ("pedidos_finalizados_hoje", theme.SUCCESS, "Finalizados Hoje", "Finalizações registradas no dia."),
            ("requisicoes_feitas_no_dia", theme.PRIMARY_HOVER, "Requisições do Dia", "Novas requisições criadas hoje."),
            ("producao_pinheiro_industria", theme.PRIMARY, "Produção Pinheiro Indústria", "Fila ativa enviada para esse destino."),
            ("producao_ar", theme.PRIMARY_HOVER, "Produção da A&R", "Fila ativa enviada para esse destino."),
            ("pedidos_sem_confirmacao_1h", theme.WARNING, "Sem Confirmação", "Aguardando retorno há mais de 1 hora."),
            ("tempo_medio_finalizacao_segundos", theme.BORDER_COLOR, "Tempo Médio de Finalização", "Média entre recebimento e finalização."),
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
                "Vendedores com Mais Requisições",
                "Ranking geral por volume de requisições emitidas.",
                self._build_top_vendors_table(),
                theme.PRIMARY,
            ),
            1,
        )
        secondary_row.addWidget(
            self._build_section_card(
                "Pedidos sem Confirmação",
                "Pedidos aguardando retorno da produção por mais de 1 hora.",
                self._build_alerts_table(),
                theme.WARNING,
            ),
            1,
        )
        layout.addLayout(secondary_row)

        machine_row = QHBoxLayout()
        machine_row.setSpacing(max(12, int(16 * s)))
        machine_row.addWidget(
            self._build_section_card(
                "MAQUINAS QUE MAIS OPERAM - A&R",
                "Ranking das maquinas da A&R por volume de operacoes finalizadas.",
                self._build_top_machines_ar_table(),
                theme.PRIMARY_HOVER,
            ),
            1,
        )
        machine_row.addWidget(
            self._build_section_card(
                "MAQUINAS QUE MAIS OPERAM - INDUSTRIA",
                "Ranking das maquinas da Industria por volume de operacoes finalizadas.",
                self._build_top_machines_industria_table(),
                theme.PRIMARY,
            ),
            1,
        )
        layout.addLayout(machine_row)

        layout.addWidget(
            self._build_section_card(
                "Últimas Requisições",
                "Visão rápida das requisições mais recentes do sistema.",
                self._build_recent_table(),
                theme.BORDER_COLOR,
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
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("-")
        value_label.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value_label.setWordWrap(True)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setStyleSheet(
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

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{theme.TEXT_DARK}; background:transparent;"
        )

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
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
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  alternate-background-color:{theme.TABLE_ALT_ROW};"
            f"  color:{theme.BORDER_COLOR}; border-radius:14px;"
            f"  gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
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
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 40)}; color:{theme.TEXT_DARK}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
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
            {2, 4},
        )
        self.recent_table.setMinimumHeight(max(260, int(300 * self.scale)))
        return self.recent_table

    def _build_top_machines_ar_table(self) -> QTableWidget:
        self.top_machines_ar_table = self._create_table(
            ["#", "MAQUINA", "OPERACOES", "EM PRODUCAO", "TEMPO MEDIO", "STATUS"],
            {1},
        )
        self.top_machines_ar_table.setMinimumHeight(max(260, int(300 * self.scale)))
        return self.top_machines_ar_table

    def _build_top_machines_industria_table(self) -> QTableWidget:
        self.top_machines_industria_table = self._create_table(
            ["#", "MAQUINA", "OPERACOES", "EM PRODUCAO", "TEMPO MEDIO", "STATUS"],
            {1},
        )
        self.top_machines_industria_table.setMinimumHeight(max(260, int(300 * self.scale)))
        return self.top_machines_industria_table

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
        self.error_label.setText(f"Não foi possível carregar o painel.\n\n{message}")
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
            if key == "tempo_medio_finalizacao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        current = _parse_datetime(payload.get("generated_at")) or local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

        self._fill_top_vendors_table(payload.get("top_vendors") or [])
        self._fill_alerts_table(payload.get("receipt_alerts") or [])
        self._fill_top_machines_table(
            self.top_machines_ar_table,
            payload.get("top_machines_ar") or [],
            "Nenhuma maquina da A&R encontrada.",
        )
        self._fill_top_machines_table(
            self.top_machines_industria_table,
            payload.get("top_machines_industria") or [],
            "Nenhuma maquina da Industria encontrada.",
        )
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
            self._set_empty_message(table, "Nenhum pedido aguardando confirmação há mais de 1 hora.")
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

    def _fill_top_machines_table(
        self,
        table: QTableWidget,
        rows: object,
        empty_message: str,
    ):
        table.clearSpans()
        table.setRowCount(0)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, empty_message)
            return

        for index, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue

            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(index),
                str(row.get("machine_name") or "-"),
                str(row.get("total_operations") or 0),
                str(row.get("in_production_count") or 0),
                _format_duration(row.get("average_seconds")),
                str(row.get("machine_status") or "-"),
            ]

            for col, value in enumerate(values):
                if col == 5:
                    machine_status = str(row.get("machine_status") or "")
                    color = _machine_status_color(machine_status)
                    label = QLabel(_machine_status_label(machine_status))
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{_tint(color, 50)}; color:{color}; border-radius:6px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(line, col, label)
                else:
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)

    def _fill_recent_table(self, rows: object):
        table = self.recent_table
        table.clearSpans()
        table.setRowCount(0)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhuma requisição recente encontrada.")
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
                    color_map = {
                        "em_andamento": theme.PRIMARY_HOVER,
                        "aguardando_recebimento": theme.WARNING,
                        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
                        "em_producao": theme.PRIMARY,
                        "cancelada": theme.DANGER,
                    }
                    color = color_map.get(status, theme.BORDER_COLOR)
                    label = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{_tint(color, 50)}; color:{color}; border-radius:6px;"
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
        item.setForeground(QColor(theme.TEXT_MEDIUM))
        table.setItem(0, 0, item)
