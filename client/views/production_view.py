from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsDropShadowEffect, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QColor

from ..api import client as api
from ..core import theme


COLS = ["PED", "CLIENTE", "OBRA", "FASE", "DATA"]
DESTINATIONS = ("A&R", "Pinheiro Indústria")

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_SEND = "ENVIADA"
PROD_RECEIVED = "RECEBIDA"
PROD_FINISHED = "FINALIZADA"
PROD_CANCELED = "CANCELADA"


class ProductionWorker(QObject):
    result = Signal(list)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.list_requisitions("em_producao", limit=200))
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


def _make_card(scale: float) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
    )
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(12)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 20))
    card.setGraphicsEffect(shadow)
    return card


def _build_production_note(action: str, destination: str, reason: str = "") -> str:
    if reason:
        return f"{PROD_NOTE_PREFIX}|{action}|{destination}|{reason.strip()}"
    return f"{PROD_NOTE_PREFIX}|{action}|{destination}"


def _parse_production_note(note: str) -> dict | None:
    parts = (note or "").split("|", 3)
    if len(parts) < 3 or parts[0] != PROD_NOTE_PREFIX:
        return None
    return {
        "action": parts[1].strip(),
        "destination": parts[2].strip(),
        "reason": parts[3].strip() if len(parts) > 3 else "",
    }


class ProductionView(QWidget):
    open_requisition = Signal(int)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list = []
        self._rows_by_destination: dict[str, list[dict]] = {dest: [] for dest in DESTINATIONS}
        self._cards: dict[str, dict] = {}
        self._count_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(max(12, int(16 * s)), max(12, int(16 * s)),
                                  max(12, int(16 * s)), max(12, int(16 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("⚒ PRODUÇÃO")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(14, int(17 * s))}pt; font-weight:bold;"
        )
        subtitle = QLabel("Acompanhe o recebimento, cancelamento e finalização das requisições enviadas para produção.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        btn_refresh = QPushButton("↻ ATUALIZAR")
        btn_refresh.setFixedHeight(max(32, int(36 * s)))
        btn_refresh.setStyleSheet(theme.secondary_btn_style(s))
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        counts = QGridLayout()
        counts.setSpacing(max(8, int(10 * s)))
        for index, destination in enumerate(DESTINATIONS):
            card = _make_card(s)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(max(12, int(14 * s)), max(10, int(12 * s)),
                                           max(12, int(14 * s)), max(10, int(12 * s)))
            lbl_title = QLabel(f"▣ {destination.upper()}")
            lbl_title.setStyleSheet(
                f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-weight:bold;"
            )
            lbl_value = QLabel("0")
            lbl_value.setStyleSheet(
                f"color:{theme.TEXT_DARK}; font-size:{max(18, int(24 * s))}pt; font-weight:bold;"
            )
            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_value)
            self._count_labels[destination] = lbl_value
            counts.addWidget(card, 0, index)
        layout.addLayout(counts)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(max(10, int(12 * s)))
        for destination in DESTINATIONS:
            tables_row.addWidget(self._build_destination_card(destination), 1)
        layout.addLayout(tables_row, 1)

        hint = QLabel("Selecione uma requisição para liberar as ações do card.")
        hint.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-style:italic;"
        )
        layout.addWidget(hint)

    def _build_destination_card(self, destination: str) -> QFrame:
        s = self.scale
        card = _make_card(s)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(12, int(14 * s)), max(12, int(14 * s)),
                                  max(12, int(14 * s)), max(12, int(14 * s)))
        layout.setSpacing(max(8, int(10 * s)))

        lbl_title = QLabel(f"◈ {destination}")
        lbl_title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(10, int(12 * s))}pt; font-weight:bold;"
        )
        layout.addWidget(lbl_title)

        actions = QHBoxLayout()
        btn_open = QPushButton("◎ Abrir")
        btn_receive = QPushButton("✓ Confirmar Recebimento")
        btn_cancel = QPushButton("✕ Cancelar")
        btn_finish = QPushButton("✔ Finalizar")
        for btn in (btn_open, btn_receive, btn_cancel, btn_finish):
            btn.setFixedHeight(max(28, int(32 * s)))
        btn_open.setStyleSheet(theme.secondary_btn_style(s))
        btn_receive.setStyleSheet(theme.secondary_btn_style(s))
        btn_cancel.setStyleSheet(theme.danger_btn_style(s))
        btn_finish.setStyleSheet(theme.primary_btn_style(s))

        btn_open.clicked.connect(lambda: self._open_selected(destination))
        btn_receive.clicked.connect(lambda: self._confirm_receipt(destination))
        btn_cancel.clicked.connect(lambda: self._cancel_requisition(destination))
        btn_finish.clicked.connect(lambda: self._finish_production(destination))

        for btn in (btn_open, btn_receive, btn_cancel, btn_finish):
            actions.addWidget(btn)
        layout.addLayout(actions)

        table = QTableWidget(0, len(COLS))
        table.setHorizontalHeaderLabels(COLS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
            f"  gridline-color:{theme.BORDER_COLOR}; font-size:{max(9, int(10 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.TABLE_HEADER_BG}; color:#fff; padding:8px;"
            f"  font-weight:bold; font-size:{max(8, int(9 * s))}pt; border:none;"
            f"  border-right:1px solid {theme.TABLE_BORDER};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; }}"
        )
        table.doubleClicked.connect(lambda index, dest=destination: self._open_row(dest, index.row()))
        table.itemSelectionChanged.connect(lambda dest=destination: self._update_action_state(dest))
        layout.addWidget(table, 1)

        self._cards[destination] = {
            "table": table,
            "open": btn_open,
            "receive": btn_receive,
            "cancel": btn_cancel,
            "finish": btn_finish,
        }
        self._update_action_state(destination)
        return card

    def refresh(self):
        worker = ProductionWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.error.connect(lambda msg: QMessageBox.critical(self, "Produção", msg))
        worker.finished.connect(thread.quit)
        thread.start()
        self._threads.append((thread, worker))

    def _populate(self, requisitions: list):
        grouped = {dest: [] for dest in DESTINATIONS}
        for req in requisitions:
            state = self._production_state_for(req)
            destination = state.get("destination")
            if destination not in grouped:
                continue
            if state["action"] == PROD_FINISHED:
                continue
            req_copy = dict(req)
            req_copy["_production_action"] = state["action"]
            req_copy["_production_phase"] = state["phase"]
            req_copy["_production_destination"] = destination
            grouped[destination].append(req_copy)

        self._rows_by_destination = grouped

        for destination in DESTINATIONS:
            rows = grouped[destination]
            self._count_labels[destination].setText(str(len(rows)))
            table = self._cards[destination]["table"]
            table.setRowCount(0)
            for req in rows:
                row = table.rowCount()
                table.insertRow(row)
                values = [
                    str(req.get("ped_number", "")),
                    req.get("client_name") or str(req.get("client_id", "")),
                    req.get("obra") or "—",
                    req.get("_production_phase", ""),
                    str(req.get("emission_date", ""))[:10],
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, col, item)
            self._update_action_state(destination)

    def _production_state_for(self, req: dict) -> dict:
        history = req.get("status_history") or []
        for entry in reversed(history):
            note = (entry.get("note") or "").strip()
            parsed = _parse_production_note(note)
            if parsed:
                action = parsed["action"]
                destination = parsed["destination"]
                if action == PROD_RECEIVED:
                    phase = "Recebimento confirmado"
                elif action == PROD_FINISHED:
                    phase = "Produção finalizada"
                else:
                    phase = "Aguardando recebimento"
                return {
                    "action": action,
                    "destination": destination,
                    "phase": phase,
                }
            if note in DESTINATIONS:
                return {
                    "action": PROD_SEND,
                    "destination": note,
                    "phase": "Aguardando recebimento",
                }
        return {
            "action": PROD_SEND,
            "destination": "",
            "phase": "Aguardando recebimento",
        }

    def _selected_req(self, destination: str) -> dict | None:
        table = self._cards[destination]["table"]
        row = table.currentRow()
        rows = self._rows_by_destination.get(destination, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _update_action_state(self, destination: str):
        req = self._selected_req(destination)
        card = self._cards[destination]
        has_selection = req is not None
        action = req.get("_production_action") if req else ""
        card["open"].setEnabled(has_selection)
        card["cancel"].setEnabled(has_selection)
        card["receive"].setEnabled(has_selection and action == PROD_SEND)
        card["finish"].setEnabled(has_selection and action == PROD_RECEIVED)

    def _open_row(self, destination: str, row: int):
        rows = self._rows_by_destination.get(destination, [])
        if 0 <= row < len(rows):
            self.open_requisition.emit(rows[row]["id"])

    def _open_selected(self, destination: str):
        req = self._selected_req(destination)
        if not req:
            QMessageBox.information(self, "Produção", "Selecione uma requisição primeiro.")
            return
        self.open_requisition.emit(req["id"])

    def _confirm_receipt(self, destination: str):
        req = self._selected_req(destination)
        if not req:
            QMessageBox.information(self, "Produção", "Selecione uma requisição primeiro.")
            return
        if req.get("_production_action") != PROD_SEND:
            QMessageBox.information(
                self,
                "Produção",
                "O recebimento só pode ser confirmado para requisições ainda não recebidas.",
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
        req = self._selected_req(destination)
        if not req:
            QMessageBox.information(self, "Produção", "Selecione uma requisição primeiro.")
            return
        if req.get("_production_action") != PROD_RECEIVED:
            QMessageBox.information(
                self,
                "Produção",
                "Finalize apenas requisições que já tiveram o recebimento confirmado.",
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
            "em_andamento",
            _build_production_note(PROD_FINISHED, destination),
            success_message=f"Produção finalizada em {destination}.",
        )
        self._threads.append((thread, worker))

    def _cancel_requisition(self, destination: str):
        req = self._selected_req(destination)
        if not req:
            QMessageBox.information(self, "Produção", "Selecione uma requisição primeiro.")
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
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(lambda _: self._after_action(success_message))
        worker.error.connect(lambda msg: QMessageBox.critical(self, "Produção", msg))
        worker.finished.connect(thread.quit)
        thread.start()
        return thread, worker

    def _after_action(self, success_message: str):
        self.refresh()
        QMessageBox.information(self, "Produção", success_message)
