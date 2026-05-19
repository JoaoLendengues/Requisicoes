"""Painel gerencial com indicadores operacionais e alertas."""

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
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


def _make_shadow_card(scale: float, background: str, border_color: str | None = None) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"background:{background}; border:none; border-radius:8px;"
    )
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.SURFACE_SOFT}; color:{theme.PRIMARY};"
        f"  border:none; outline:none; border-radius:8px;"
        f"  padding:7px 16px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.SELECTION_BG}; }}"
        f"QPushButton:pressed {{ background:#CFE0FF; }}"
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
        self.setObjectName("dashboardView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#dashboardView {{ background:{theme.PRIMARY_LIGHT}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(max(12, int(16 * s)), max(12, int(16 * s)),
                                max(12, int(16 * s)), max(12, int(16 * s)))
        root.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(8, int(10 * s)))

        title_col = QVBoxLayout()
        title = QLabel("PAINEL GERENCIAL")
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(15, int(18 * s))}pt; font-weight:bold;"
        )
        subtitle = QLabel(
            "Acompanhe producao, prazos e alertas em uma unica tela."
        )
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QVBoxLayout()
        header_right.setSpacing(max(4, int(6 * s)))
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.updated_label.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(32, int(36 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        header_right.addWidget(self.updated_label)
        header_right.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        header.addLayout(header_right)

        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:rgba(239, 68, 68, 0.12); color:{theme.DANGER};"
            f"border:none; border-radius:8px;"
            f"padding:10px 12px; font-size:{max(8, int(9 * s))}pt;"
        )
        root.addWidget(self.error_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{theme.PRIMARY_LIGHT}; }}"
        )
        scroll.viewport().setStyleSheet(
            f"background:{theme.PRIMARY_LIGHT}; border:none;"
        )
        root.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("dashboardContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(
            f"QWidget#dashboardContent {{ background:{theme.PRIMARY_LIGHT}; }}"
        )
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(12, int(14 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(10, int(12 * s)))
        metrics.setVerticalSpacing(max(10, int(12 * s)))
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_em_producao", theme.PRIMARY_HOVER, "PEDIDOS EM PRODUCAO", "Requisicoes recebidas pela producao."),
            ("pedidos_em_atraso", theme.DANGER, "PEDIDOS EM ATRASO", "Pedidos abertos com prazo vencido."),
            ("pedidos_finalizados_hoje", theme.SUCCESS, "PEDIDOS FINALIZADOS HOJE", "Finalizacoes registradas no dia."),
            ("requisicoes_feitas_no_dia", theme.PRIMARY, "REQUISICOES FEITAS NO DIA", "Novas requisicoes criadas hoje."),
            ("producao_pinheiro_industria", theme.PRIMARY_LIGHT, "PRODUCAO DA PINHEIRO INDUSTRIA", "Fila ativa enviada para esse destino."),
            ("producao_ar", theme.PRIMARY_HOVER, "PRODUCAO DA A&R", "Fila ativa enviada para esse destino."),
            ("pedidos_sem_confirmacao_1h", theme.WARNING, "SEM CONFIRMACAO DE RECEBIMENTO", "Aguardando retorno ha mais de 1 hora."),
            ("tempo_medio_finalizacao_segundos", theme.SIDEBAR_BG, "TEMPO MEDIO DE FINALIZACAO", "Media entre recebimento e finalizacao."),
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
        secondary_row.setSpacing(max(10, int(12 * s)))
        secondary_row.addWidget(
            self._build_section_card(
                "VENDEDORES QUE MAIS FAZEM REQUISICAO",
                "Ranking geral por volume de requisicoes.",
                self._build_top_vendors_table(),
            ),
            1,
        )
        secondary_row.addWidget(
            self._build_section_card(
                "PEDIDOS SEM CONFIRMACAO DE RECEBIMENTO",
                "Pedidos aguardando retorno da producao por mais de 1 hora.",
                self._build_alerts_table(),
            ),
            1,
        )
        layout.addLayout(secondary_row)

        layout.addWidget(
            self._build_section_card(
                "ULTIMAS REQUISICOES",
                "Visao rapida das requisicoes mais recentes do sistema.",
                self._build_recent_table(),
            )
        )
        layout.addStretch()

    def _build_metric_card(self, color: str, title: str, helper_text: str, key: str) -> QFrame:
        s = self.scale
        card = _make_shadow_card(s, color)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(14, int(18 * s)), max(12, int(16 * s)),
                                  max(14, int(18 * s)), max(12, int(16 * s)))
        layout.setSpacing(max(4, int(6 * s)))

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color:rgba(255,255,255,0.88); font-size:{max(7, int(9 * s))}pt;"
            f"font-weight:bold; background:transparent; border:none;"
        )

        value_label = QLabel("-")
        value_label.setStyleSheet(
            f"color:#fff; font-size:{max(18, int(23 * s))}pt;"
            f"font-weight:bold; background:transparent; border:none;"
        )
        value_label.setWordWrap(True)

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setStyleSheet(
            f"color:rgba(255,255,255,0.78); font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(helper_label)
        layout.addStretch()

        self._metric_labels[key] = value_label
        return card

    def _build_section_card(self, title: str, subtitle: str, body: QWidget) -> QFrame:
        s = self.scale
        card = _make_shadow_card(s, theme.CARD_BG, theme.BORDER_COLOR)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(14, int(16 * s)), max(12, int(14 * s)),
                                  max(14, int(16 * s)), max(12, int(14 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(10, int(12 * s))}pt; font-weight:bold;"
        )

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8 * s))}pt;"
        )

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

        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:7px;"
            f"  font-weight:bold; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{ padding:4px; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
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
                    color = theme.STATUS_COLORS.get(status, theme.TEXT_MEDIUM)
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{color}; color:{theme.TEXT_WHITE}; border-radius:8px;"
                        f"font-weight:600; padding:3px 8px; font-size:{max(7, int(8 * self.scale))}pt;"
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
        table.setItem(0, 0, item)
