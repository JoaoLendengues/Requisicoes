"""Central de pedidos com listas operacionais e acesso ao PDF do pedido finalizado."""

import os
import webbrowser
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor
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
from ..core.resolution import res
from ..services.pdf_generator import HAS_REPORTLAB, generate_pdf
from .requisition_form import _run_in_thread


def _make_card(scale: float, background: str = None) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"background:{background or theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
    )
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(14)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 12))
    card.setGraphicsEffect(shadow)
    return card


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
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
        return datetime.fromisoformat(text).strftime("%d/%m/%Y")
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
        root = QVBoxLayout(self)
        root.setContentsMargins(max(12, int(16 * s)), max(12, int(16 * s)),
                                max(12, int(16 * s)), max(12, int(16 * s)))
        root.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        title_col = QVBoxLayout()

        title = QLabel("CENTRAL DE PEDIDOS")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(15, int(18 * s))}pt; font-weight:bold;"
        )
        subtitle = QLabel(
            "Acompanhe pedidos por etapa, atrasos e finalizacoes em uma tela unica."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QVBoxLayout()
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.updated_label.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(32, int(36 * s)))
        self.refresh_btn.setStyleSheet(theme.secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        right_col.addWidget(self.updated_label)
        right_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        header.addLayout(right_col)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:rgba(239, 68, 68, 0.12); color:{theme.DANGER};"
            f"border:1px solid rgba(239, 68, 68, 0.4); border-radius:8px;"
            f"padding:10px 12px; font-size:{max(8, int(9 * s))}pt;"
        )
        root.addWidget(self.error_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(12, int(14 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(10, int(12 * s)))
        metrics.setVerticalSpacing(max(10, int(12 * s)))
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_aguardando_recebimento", theme.WARNING, "PEDIDOS AGUARDANDO RECEBIMENTO"),
            ("pedidos_em_producao", theme.PRIMARY_HOVER, "PEDIDOS EM PRODUCAO"),
            ("pedidos_finalizados", theme.SUCCESS, "PEDIDOS FINALIZADOS"),
            ("pedidos_cancelados", theme.DANGER, "PEDIDOS CANCELADOS"),
            ("pedidos_atrasados", theme.DANGER, "PEDIDOS ATRASADOS"),
            ("tempo_medio_producao_segundos", theme.SIDEBAR_BG, "TEMPO MEDIO DE PRODUCAO"),
        ]
        for index, (key, color, title_text) in enumerate(card_defs):
            metrics.addWidget(self._build_metric_card(color, title_text, key), index // 3, index % 3)

        grid_top = QGridLayout()
        grid_top.setHorizontalSpacing(max(10, int(12 * s)))
        grid_top.setVerticalSpacing(max(10, int(12 * s)))
        layout.addLayout(grid_top)
        grid_top.addWidget(self._build_section("Pedidos aguardando recebimento", "aguardando_recebimento"), 0, 0)
        grid_top.addWidget(self._build_section("Pedidos em producao", "em_producao"), 0, 1)
        grid_top.addWidget(self._build_section("Pedidos finalizados", "finalizados", pdf_action=True), 1, 0)
        grid_top.addWidget(self._build_section("Pedidos cancelados", "cancelados"), 1, 1)
        layout.addWidget(self._build_section("Pedidos atrasados", "atrasados"))
        layout.addStretch()

    def _build_metric_card(self, color: str, title_text: str, key: str) -> QFrame:
        s = self.scale
        card = _make_card(s, color)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(14, int(18 * s)), max(12, int(16 * s)),
                                  max(14, int(18 * s)), max(12, int(16 * s)))

        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color:rgba(255,255,255,0.88); font-size:{max(8, int(9 * s))}pt; font-weight:bold;"
        )

        value = QLabel("-")
        value.setStyleSheet(
            f"color:#fff; font-size:{max(20, int(24 * s))}pt; font-weight:bold;"
        )

        layout.addWidget(title)
        layout.addWidget(value)
        layout.addStretch()
        self._metric_labels[key] = value
        return card

    def _build_section(self, title_text: str, key: str, pdf_action: bool = False) -> QFrame:
        s = self.scale
        card = _make_card(s)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(14, int(16 * s)), max(12, int(14 * s)),
                                  max(14, int(16 * s)), max(12, int(14 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        title_row = QHBoxLayout()
        title = QLabel(title_text.upper())
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(10, int(12 * s))}pt; font-weight:bold;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        btn_open = QPushButton("ABRIR PEDIDO")
        btn_open.setFixedHeight(max(28, int(32 * s)))
        btn_open.setStyleSheet(theme.secondary_btn_style(s))
        btn_open.clicked.connect(lambda: self._open_selected(key))
        title_row.addWidget(btn_open)

        if pdf_action:
            btn_pdf = QPushButton("VER PDF")
            btn_pdf.setFixedHeight(max(28, int(32 * s)))
            btn_pdf.setStyleSheet(theme.primary_btn_style(s))
            btn_pdf.clicked.connect(self._open_selected_pdf)
            title_row.addWidget(btn_pdf)

        layout.addLayout(title_row)

        if pdf_action:
            self.avg_finished_label = QLabel("Tempo medio: -")
            self.avg_finished_label.setStyleSheet(
                f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8 * s))}pt;"
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
        table.doubleClicked.connect(lambda index, section=key: self._open_row(section, index.row()))

        header = table.horizontalHeader()
        for col in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col in stretch_columns[key]
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(col, mode)

        s = self.scale
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:7px;"
            f"  font-weight:bold; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item:selected {{ background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )
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

    def _show_error(self, message: str):
        self.error_label.setText(f"Nao foi possivel carregar a central de pedidos.\n\n{message}")
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
            if key == "tempo_medio_producao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        self.updated_label.setText(f"Atualizado em {_format_datetime(payload.get('generated_at'))}")
        if hasattr(self, "avg_finished_label"):
            self.avg_finished_label.setText(
                f"Tempo medio: {_format_duration(stats.get('tempo_medio_producao_segundos'))}"
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
                    color = theme.STATUS_COLORS.get(status, theme.TEXT_MEDIUM)
                    badge.setStyleSheet(
                        f"background:{color}; color:{theme.TEXT_WHITE}; border-radius:8px;"
                        f"font-weight:600; padding:3px 8px; font-size:{max(7, int(8 * self.scale))}pt;"
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
                "Defina a pasta de PDFs nas configuracoes antes de abrir o arquivo.",
            )
            return

        if not HAS_REPORTLAB:
            QMessageBox.warning(
                self,
                "Central de pedidos",
                "A geracao de PDF nao esta disponivel neste ambiente.",
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
                f"Nao foi possivel gerar o PDF deste pedido.\n\n{exc}",
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
                f"PDF gerado em:\n{pdf_path}\n\nNao foi possivel abrir automaticamente: {exc}",
            )
