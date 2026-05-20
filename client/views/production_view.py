from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QPalette, QColor, QPixmap

from ..api import client as api
from ..core.session import session
from ..core import theme


COLS = ["PED", "CLIENTE", "OBRA", "DATA"]
ALL_DESTINATIONS = ("A&R", "Pinheiro Indústria")
WAITING_STAGE = "waiting"
PRODUCTION_STAGE = "production"

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_RECEIVED = "RECEBIDA"
PROD_FINISHED = "FINALIZADA"
PROD_CANCELED = "CANCELADA"

PROD_CARD_SURFACE = "#FFFFFF"
PROD_CARD_PRIMARY = "#1E3A5F"
PROD_CARD_SECONDARY = "#27496D"
PROD_CARD_TEXT = "#0F172A"
PROD_CARD_MUTED = "#64748B"

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_DESTINATION_CARD_META = {
    "A&R": {
        "title": "Producao da A&R",
        "helper": "Fila ativa enviada para esse destino.",
        "accent": PROD_CARD_SECONDARY,
        "icon": "producao_ar.png",
    },
    "Pinheiro Indústria": {
        "title": "Producao Pinheiro Industria",
        "helper": "Fila ativa enviada para esse destino.",
        "accent": PROD_CARD_PRIMARY,
        "icon": "producao_pinheiro_industria.png",
    },
}


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
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


def _format_header_date(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y")


class ProductionWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.list_requisitions(limit=200))
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


def _make_card(scale: float) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"background:{theme.CARD_BG}; border:none; border-radius:8px;"
    )
    return card


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(PROD_CARD_TEXT)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


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


def _build_production_note(action: str, destination: str, reason: str = "") -> str:
    if reason:
        return f"{PROD_NOTE_PREFIX}|{action}|{destination}|{reason.strip()}"
    return f"{PROD_NOTE_PREFIX}|{action}|{destination}"


def _normalize_destination(destination: str) -> str:
    text = (destination or "").strip()
    folded = text.casefold()
    if folded == "a&r":
        return "A&R"
    if folded in ("pinheiro indústria".casefold(), "pinheiro industria".casefold()):
        return "Pinheiro Indústria"
    return text


def _destination_card_meta(destination: str) -> dict | None:
    return _DESTINATION_CARD_META.get(_normalize_destination(destination))


def _parse_production_note(note: str) -> dict | None:
    parts = (note or "").split("|", 3)
    if len(parts) < 3 or parts[0] != PROD_NOTE_PREFIX:
        return None
    return {
        "action": parts[1].strip(),
        "destination": _normalize_destination(parts[2]),
        "reason": parts[3].strip() if len(parts) > 3 else "",
    }


class ProductionView(QWidget):
    open_requisition = Signal(int)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.destinations = session.visible_production_destinations
        self._threads: list[tuple[QThread, QObject]] = []
        self._rows_by_destination: dict[str, dict[str, list[dict]]] = {
            destination: {WAITING_STAGE: [], PRODUCTION_STAGE: []}
            for destination in self.destinations
        }
        self._cards: dict[str, dict[str, dict]] = {}
        self._count_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = "#F4F7FB"
        self.setObjectName("productionView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#productionView {{ background:{page_bg}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12, int(16 * s)), max(12, int(16 * s)),
                                  max(12, int(16 * s)), max(12, int(16 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Produção")
        title.setStyleSheet(
            f"color:{PROD_CARD_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Acompanhamento operacional por destino, etapa e pendencias da producao."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{PROD_CARD_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = QFrame()
        info_card.setObjectName("productionInfoCard")
        info_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        info_card.setStyleSheet(
            f"QFrame#productionInfoCard {{"
            f"  background:{PROD_CARD_SURFACE}; border:none;"
            f"  border-radius:{max(16, int(18 * s))}px;"
            f"}}"
        )
        _apply_shadow(info_card, blur=max(26, int(30 * s)), y_offset=max(4, int(5 * s)))

        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setStyleSheet(
            f"color:{PROD_CARD_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{PROD_CARD_TEXT}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setStyleSheet(
            f"color:{PROD_CARD_MUTED}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
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
        layout.addLayout(header)

        counts = QGridLayout()
        counts.setSpacing(max(8, int(10 * s)))
        for index, destination in enumerate(self.destinations):
            counts.setColumnStretch(index, 1)
            counts.addWidget(self._build_destination_summary_card(destination), 0, index)

        layout.addLayout(counts)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(max(10, int(12 * s)))
        for destination in self.destinations:
            columns_row.addWidget(self._build_destination_column(destination), 1)
        layout.addLayout(columns_row, 1)

        hint = QLabel(
            "Use os painéis de cada destino para abrir, confirmar recebimento, finalizar ou cancelar requisições."
        )
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

    def _build_destination_column(self, destination: str) -> QFrame:
        s = self.scale
        card = _make_card(s)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(12, int(14 * s)), max(12, int(14 * s)),
                                  max(12, int(14 * s)), max(12, int(14 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        title = QLabel(_normalize_destination(destination))
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(11, int(13 * s))}pt; font-weight:bold;"
        )
        layout.addWidget(title)

        self._cards[destination] = {}

        waiting_panel = self._build_stage_panel(destination, WAITING_STAGE)
        production_panel = self._build_stage_panel(destination, PRODUCTION_STAGE)

        self._cards[destination][WAITING_STAGE] = waiting_panel
        self._cards[destination][PRODUCTION_STAGE] = production_panel

        layout.addWidget(waiting_panel["card"])
        layout.addWidget(production_panel["card"])
        return card

    def _build_destination_summary_card(self, destination: str) -> QFrame:
        s = self.scale
        meta = _destination_card_meta(destination) or {}
        title_text = meta.get("title") or _normalize_destination(destination)
        helper_text = meta.get("helper") or "Requisicoes ativas neste destino."
        accent_color = meta.get("accent") or PROD_CARD_PRIMARY

        card = QFrame()
        card.setObjectName("productionSummaryCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            f"QFrame#productionSummaryCard {{"
            f"  background:{PROD_CARD_SURFACE}; border:none;"
            f"  border-radius:{max(18, int(20 * s))}px;"
            f"}}"
        )
        _apply_shadow(card, blur=max(26, int(30 * s)), y_offset=max(4, int(5 * s)))

        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("0")
        value_label.setStyleSheet(
            f"color:{PROD_CARD_TEXT}; font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value_label.setWordWrap(True)

        title_label = QLabel(title_text)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color:{PROD_CARD_PRIMARY}; font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setStyleSheet(
            f"color:{PROD_CARD_MUTED}; font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:{accent_color}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(max(10, int(12 * s)))
        header_row.addWidget(value_label, 1, Qt.AlignmentFlag.AlignTop)

        icon_label = self._build_destination_icon_label(destination)
        if icon_label is not None:
            header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addStretch()
        layout.addWidget(accent_line)

        self._count_labels[destination] = value_label
        return card

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

    def _build_stage_panel(self, destination: str, stage: str) -> dict:
        s = self.scale
        card = QFrame()
        card.setStyleSheet(
            f"background:{theme.INPUT_BG}; border:none; border-radius:8px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(10, int(12 * s)), max(10, int(12 * s)),
                                  max(10, int(12 * s)), max(10, int(12 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        if stage == WAITING_STAGE:
            title_text = "Aguardando Recebimento"
            subtitle_text = "Requisições enviadas para produção e ainda não recebidas."
            primary_text = "Confirmar Recebimento"
        else:
            title_text = "Em Produção"
            subtitle_text = "Requisições já recebidas pela produção."
            primary_text = "Finalizar"

        title_row = QHBoxLayout()
        title = QLabel(title_text)
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(9, int(11 * s))}pt; font-weight:bold;"
        )
        count = QLabel("0")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setMinimumWidth(max(28, int(34 * s)))
        count.setStyleSheet(
            f"background:{theme.TABLE_HEADER_BG}; color:#fff; border-radius:999px;"
            f"font-size:{max(8, int(9 * s))}pt; font-weight:bold; padding:2px 8px;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(count)

        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(7, int(8 * s))}pt;"
        )
        layout.addLayout(title_row)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        btn_open = QPushButton("Abrir")
        btn_primary = QPushButton(primary_text)
        btn_cancel = QPushButton("Cancelar")

        for btn in (btn_open, btn_primary, btn_cancel):
            btn.setFixedHeight(max(28, int(32 * s)))

        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_primary.setStyleSheet(theme.primary_btn_style(s))
        btn_cancel.setStyleSheet(theme.danger_btn_style(s))

        btn_open.clicked.connect(lambda: self._open_selected(destination, stage))
        if stage == WAITING_STAGE:
            btn_primary.clicked.connect(lambda: self._confirm_receipt(destination))
        else:
            btn_primary.clicked.connect(lambda: self._finish_production(destination))
        btn_cancel.clicked.connect(lambda: self._cancel_requisition(destination, stage))

        actions.addWidget(btn_open)
        actions.addWidget(btn_primary)
        actions.addWidget(btn_cancel)
        layout.addLayout(actions)

        table = QTableWidget(0, len(COLS))
        table.setHorizontalHeaderLabels(COLS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  gridline-color:transparent; font-size:{max(9, int(10 * s))}pt; color:{theme.TEXT_DARK};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:8px;"
            f"  font-weight:bold; font-size:{max(8, int(9 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
        table.doubleClicked.connect(
            lambda index, dest=destination, current_stage=stage: self._open_row(dest, current_stage, index.row())
        )
        layout.addWidget(table, 1)

        return {
            "card": card,
            "table": table,
            "count": count,
            "open": btn_open,
            "primary": btn_primary,
            "cancel": btn_cancel,
        }

    def refresh(self):
        self._set_loading(True)
        worker = ProductionWorker()
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
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _on_refresh_result(self, payload: object):
        try:
            self._populate(payload)
        except Exception as exc:
            self._show_error(f"Não foi possível carregar a aba de produção.\n\n{exc}")

    def _show_error(self, msg: str):
        if hasattr(self, "updated_label"):
            self.updated_label.setText("Falha ao atualizar")
        QMessageBox.critical(self, "Produção", msg)

    def _populate(self, payload: object):
        grouped = {
            destination: {WAITING_STAGE: [], PRODUCTION_STAGE: []}
            for destination in self.destinations
        }

        if isinstance(payload, list):
            for req in payload:
                if not isinstance(req, dict):
                    continue

                destination = self._production_destination(req)
                if destination not in grouped:
                    continue

                status = str(req.get("status") or "").strip()
                if status == "aguardando_recebimento":
                    grouped[destination][WAITING_STAGE].append(dict(req))
                elif status == "em_producao":
                    grouped[destination][PRODUCTION_STAGE].append(dict(req))
        elif isinstance(payload, dict):
            for req in payload.get("waiting", []) or []:
                if not isinstance(req, dict):
                    continue
                destination = self._production_destination(req)
                if destination in grouped:
                    grouped[destination][WAITING_STAGE].append(dict(req))

            for req in payload.get("production", []) or []:
                if not isinstance(req, dict):
                    continue
                destination = self._production_destination(req)
                if destination in grouped:
                    grouped[destination][PRODUCTION_STAGE].append(dict(req))
        else:
            raise ValueError("Resposta inválida ao carregar a produção.")

        self._rows_by_destination = grouped

        for destination in self.destinations:
            waiting_rows = grouped[destination][WAITING_STAGE]
            production_rows = grouped[destination][PRODUCTION_STAGE]
            self._count_labels[destination].setText(str(len(waiting_rows) + len(production_rows)))
            self._fill_stage_table(destination, WAITING_STAGE, waiting_rows)
            self._fill_stage_table(destination, PRODUCTION_STAGE, production_rows)

        generated_at = _parse_datetime(payload.get("generated_at")) if isinstance(payload, dict) else None
        current = generated_at or datetime.now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

    def _fill_stage_table(self, destination: str, stage: str, rows: list[dict]):
        panel = self._cards[destination][stage]
        table = panel["table"]
        panel["count"].setText(str(len(rows)))
        table.setRowCount(0)

        for req in rows:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                str(req.get("ped_number", "")),
                req.get("client_name") or str(req.get("client_id", "")),
                req.get("obra") or "—",
                str(req.get("emission_date", ""))[:10],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _production_destination(self, req: dict) -> str:
        history = req.get("status_history") or []
        if not isinstance(history, list):
            return ""

        for entry in reversed(history):
            if not isinstance(entry, dict):
                continue

            note = (entry.get("note") or "").strip()
            parsed = _parse_production_note(note)
            if parsed and parsed["destination"] in ALL_DESTINATIONS:
                return parsed["destination"]
            normalized_note = _normalize_destination(note)
            if normalized_note in ALL_DESTINATIONS:
                return normalized_note

        return ""

    def _selected_req(self, destination: str, stage: str) -> dict | None:
        table = self._cards[destination][stage]["table"]
        row = table.currentRow()
        rows = self._rows_by_destination.get(destination, {}).get(stage, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _open_row(self, destination: str, stage: str, row: int):
        rows = self._rows_by_destination.get(destination, {}).get(stage, [])
        if 0 <= row < len(rows):
            self.open_requisition.emit(rows[row]["id"])

    def _open_selected(self, destination: str, stage: str):
        req = self._selected_req(destination, stage)
        if not req:
            QMessageBox.information(self, "Produção", "Selecione uma requisição primeiro.")
            return
        self.open_requisition.emit(req["id"])

    def _confirm_receipt(self, destination: str):
        req = self._selected_req(destination, WAITING_STAGE)
        if not req:
            QMessageBox.information(
                self,
                "Produção",
                "Selecione uma requisição no painel de aguardando recebimento.",
            )
            return

        thread, worker = self._run_action(
            api.update_status,
            req["id"],
            "em_producao",
            _build_production_note(PROD_RECEIVED, destination),
            success_message=f"Recebimento confirmado em {destination}.",
        )
        self._threads.append((thread, worker))

    def _finish_production(self, destination: str):
        req = self._selected_req(destination, PRODUCTION_STAGE)
        if not req:
            QMessageBox.information(
                self,
                "Produção",
                "Selecione uma requisição no painel de em produção.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Finalizar produção",
            "Deseja finalizar a produção desta requisição?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        thread, worker = self._run_action(
            api.update_status,
            req["id"],
            "em_producao",
            _build_production_note(PROD_FINISHED, destination),
            success_message=f"Produção finalizada em {destination}.",
        )
        self._threads.append((thread, worker))

    def _cancel_requisition(self, destination: str, stage: str):
        req = self._selected_req(destination, stage)
        if not req:
            panel_name = "aguardando recebimento" if stage == WAITING_STAGE else "em produção"
            QMessageBox.information(
                self,
                "Produção",
                f"Selecione uma requisição no painel de {panel_name}.",
            )
            return

        reason = self._ask_cancel_reason()
        if reason is None:
            return

        thread, worker = self._run_action(
            api.update_status,
            req["id"],
            "em_andamento",
            _build_production_note(PROD_CANCELED, destination, reason),
            success_message="Requisição devolvida para em andamento.",
        )
        self._threads.append((thread, worker))

    def _ask_cancel_reason(self) -> str | None:
        while True:
            reason, ok = QInputDialog.getMultiLineText(
                self,
                "Cancelar requisição",
                "Informe o motivo do cancelamento:",
            )
            if not ok:
                return None

            normalized = " ".join(reason.split())
            if len(normalized) < 10:
                QMessageBox.warning(
                    self,
                    "Motivo inválido",
                    "O motivo do cancelamento precisa ter pelo menos 10 letras.",
                )
                continue
            return normalized

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
        return thread, worker

    def _after_action(self, success_message: str):
        self.refresh()
        QMessageBox.information(self, "Produção", success_message)
