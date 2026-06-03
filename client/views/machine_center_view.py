"""Cadastro de máquinas de produção embarcado em Configurações."""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)
from ..core.text_case import bind_uppercase_line_edit
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from .user_center_view import (
    ActionWorker,
    UiCallback,
    _field_style,
    _flat_secondary_btn_style,
    _make_card,
    _primary_action_btn_style,
    _rgba,
)


DESTINATION_OPTIONS = (
    ("A&R", "A&R"),
    ("PINHEIRO INDÚSTRIA", "Pinheiro Indústria"),
)
ROLE_LABELS = {
    "producao": "A&R",
    "industria": "INDÚSTRIA",
    "entrega": "ENTREGAS",
    "entregas": "ENTREGAS",
}
STATUS_LABELS = {
    "funcionando": "FUNCIONANDO",
    "manutencao": "MANUTENÇÃO",
}
MACHINE_OPERATOR_ROLE_OPTIONS = (
    ("OPERADOR", "operador"),
    ("AJUDANTE", "ajudante"),
)


def _normalize_operator_role(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "ajudante":
        return "ajudante"
    return "operador"


def _role_label(value: object) -> str:
    if _normalize_operator_role(value) == "ajudante":
        return "AJUDANTE"
    return "OPERADOR"


class MachineCenterView(QWidget):
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None, embedded: bool = True):
        super().__init__(parent)
        self.scale = scale
        self.embedded = embedded
        self._threads: list[tuple[QThread, QObject]] = []
        self._machines_all: list[dict] = []
        self._operators_global: list[dict] = []         # cadastro global com nome + função
        self._machine_operator_rows: list[dict] = []    # vinculados à máquina em edição
        self._selected_machine_id: int | None = None
        self._pending_machine_id: int | None = None
        self._pending_refreshes = 0
        self._refresh_failed = False
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("machineCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#machineCenterView {{ background:{page_bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(max(14, int(18 * s)))

        self.date_label = QLabel(_format_header_date())
        self.updated_label = QLabel("")
        self.refresh_btn = QPushButton()
        self.refresh_btn.hide()

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
        self._page_scroll.viewport().setStyleSheet(f"background:{page_bg}; border:none;")
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("machineCenterContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#machineCenterContent {{ background:{page_bg}; }}"
        )
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        body = QHBoxLayout()
        body.setSpacing(max(12, int(14 * s)))
        body.addWidget(self._build_table_card(), 3)
        body.addWidget(self._build_form_card(), 2)
        layout.addLayout(body)
        layout.addStretch()

        self._prepare_new_machine()
        self.refresh()

    def _build_table_card(self) -> QFrame:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, radius=max(18, int(20 * s)))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            max(16, int(20 * s)),
            max(14, int(18 * s)),
            max(16, int(20 * s)),
            max(14, int(18 * s)),
        )
        layout.setSpacing(max(10, int(12 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(8, int(10 * s)))
        title = QLabel("MÁQUINAS CADASTRADAS")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        header.addWidget(title)
        header.addStretch()

        self.result_hint = QLabel("Carregando máquinas...")
        self.result_hint.setProperty("muted", "1")
        self.result_hint.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt;")
        header.addWidget(self.result_hint)

        self.btn_refresh_list = QPushButton("ATUALIZAR")
        self.btn_refresh_list.setFixedHeight(max(38, int(44 * s)))
        self.btn_refresh_list.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_refresh_list.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh_list)

        new_btn = QPushButton("NOVO")
        new_btn.setFixedHeight(max(38, int(44 * s)))
        new_btn.setStyleSheet(_flat_secondary_btn_style(s))
        new_btn.clicked.connect(self._prepare_new_machine)
        header.addWidget(new_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["NOME", "PRODUÇÃO", "OPERADOR", "AJUDANTE", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_smooth_scroll(self.table)
        self.table.doubleClicked.connect(self._load_selected_machine)
        self.table.itemSelectionChanged.connect(self._load_current_selection)

        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(max(360, int(420 * s)))
        self._apply_table_style()
        layout.addWidget(self.table, 1)
        return card

    def _build_form_card(self) -> QFrame:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, radius=max(18, int(20 * s)))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            max(16, int(20 * s)),
            max(14, int(18 * s)),
            max(16, int(20 * s)),
            max(14, int(18 * s)),
        )
        layout.setSpacing(max(10, int(12 * s)))

        title = QLabel("CADASTRO DE MÁQUINAS")
        title.setStyleSheet(f"background:transparent; font-size:{max(10, int(12 * s))}pt; font-weight:800;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Cadastre o nome da máquina, defina a produção e vincule os operadores responsáveis."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt;")
        layout.addWidget(subtitle)

        self.form_status = QLabel("Nova máquina")
        self.form_status.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:700; color:{theme.PRIMARY};"
        )
        layout.addWidget(self.form_status)

        form = QGridLayout()
        form.setHorizontalSpacing(max(10, int(12 * s)))
        form.setVerticalSpacing(max(8, int(10 * s)))

        form.addWidget(self._field_label("Nome da máquina"), 0, 0)
        self.input_name = self._input()
        bind_uppercase_line_edit(self.input_name)
        self.input_name.setPlaceholderText("Ex.: DOBRADEIRA 01")
        form.addWidget(self.input_name, 1, 0, 1, 2)

        form.addWidget(self._field_label("Produção"), 2, 0)
        self.combo_destination = QComboBox()
        self.combo_destination.setFixedHeight(max(38, int(44 * s)))
        self.combo_destination.setStyleSheet(_field_style(s))
        for label, value in DESTINATION_OPTIONS:
            self.combo_destination.addItem(label, value)
        self.combo_destination.currentIndexChanged.connect(self._on_destination_changed)
        form.addWidget(self.combo_destination, 3, 0, 1, 2)

        layout.addLayout(form)

        # ── Seção de equipe ───────────────────────────────────────────────
        ops_title = QLabel("EQUIPE DA MÁQUINA")
        ops_title.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:800;")
        layout.addWidget(ops_title)

        ops_hint = QLabel(
            "Digite o nome, defina se a pessoa é OPERADOR ou AJUDANTE e clique em Adicionar. "
            "Nomes novos são criados automaticamente."
        )
        ops_hint.setWordWrap(True)
        ops_hint.setProperty("muted", "1")
        ops_hint.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt;")
        layout.addWidget(ops_hint)

        ops_input_row = QHBoxLayout()
        ops_input_row.setSpacing(max(6, int(8 * s)))
        self.input_operator = QLineEdit()
        self.input_operator.setFixedHeight(max(38, int(44 * s)))
        self.input_operator.setStyleSheet(_field_style(s))
        self.input_operator.setPlaceholderText("Nome da pessoa...")
        self.input_operator.returnPressed.connect(self._add_operator_from_input)
        bind_uppercase_line_edit(self.input_operator)
        ops_input_row.addWidget(self.input_operator, 1)
        self.combo_operator_role = QComboBox()
        self.combo_operator_role.setFixedHeight(max(38, int(44 * s)))
        self.combo_operator_role.setStyleSheet(_field_style(s))
        for label, value in MACHINE_OPERATOR_ROLE_OPTIONS:
            self.combo_operator_role.addItem(label, value)
        ops_input_row.addWidget(self.combo_operator_role)
        self.btn_add_operator = QPushButton("ADICIONAR")
        self.btn_add_operator.setFixedHeight(max(38, int(44 * s)))
        self.btn_add_operator.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_add_operator.clicked.connect(self._add_operator_from_input)
        ops_input_row.addWidget(self.btn_add_operator)
        layout.addLayout(ops_input_row)

        self.operators_scroll = SmoothScrollArea()
        self.operators_scroll.setWidgetResizable(True)
        self.operators_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.operators_scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:14px; }}"
        )
        self.operators_scroll.setMinimumHeight(max(140, int(160 * s)))
        self.operators_scroll.setMaximumHeight(max(240, int(280 * s)))

        self.operators_content = QWidget()
        self.operators_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.operators_content.setStyleSheet(f"background:{theme.CARD_BG};")
        self.operators_scroll.setWidget(self.operators_content)

        self.operators_layout = QVBoxLayout(self.operators_content)
        self.operators_layout.setContentsMargins(
            max(10, int(12 * s)), max(8, int(10 * s)),
            max(10, int(12 * s)), max(8, int(10 * s)),
        )
        self.operators_layout.setSpacing(max(4, int(6 * s)))
        layout.addWidget(self.operators_scroll)

        self.save_status = QLabel("")
        self.save_status.setWordWrap(True)
        self.save_status.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        layout.addWidget(self.save_status)

        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))
        self.btn_save = QPushButton("SALVAR CADASTRO")
        self.btn_save.setFixedHeight(max(38, int(44 * s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save_machine)
        actions.addWidget(self.btn_save)

        clear_btn = QPushButton("LIMPAR")
        clear_btn.setFixedHeight(max(38, int(44 * s)))
        clear_btn.setStyleSheet(_flat_secondary_btn_style(s))
        clear_btn.clicked.connect(self._prepare_new_machine)
        actions.addWidget(clear_btn)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        return card

    def _input(self) -> QLineEdit:
        field = QLineEdit()
        field.setFixedHeight(max(38, int(44 * self.scale)))
        field.setStyleSheet(_field_style(self.scale))
        return field

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setProperty("muted", "1")
        label.setStyleSheet(
            f"font-size:{max(7, int(8 * self.scale))}pt; font-weight:700;"
            f"background:transparent;"
        )
        return label

    def _current_destination(self) -> str:
        return str(self.combo_destination.currentData() or "A&R")

    def refresh(self):
        self.error_label.hide()
        self.save_status.setText("Carregando máquinas e operadores...")
        self._pending_refreshes = 2
        self._refresh_failed = False
        self._set_loading(True)
        self._run_action(
            api.list_operators,
            on_result=self._populate_operators_global,
            on_error=self._on_refresh_error,
            show_dialog_errors=False,
            on_finished=self._finish_refresh_step,
        )
        self._run_action(
            api.list_production_machine_registry,
            on_result=self._populate_machines,
            on_error=self._on_refresh_error,
            show_dialog_errors=False,
            on_finished=self._finish_refresh_step,
        )

    def _run_action(
        self,
        fn,
        *args,
        on_result=None,
        on_error=None,
        success_message: str = "",
        show_dialog_errors: bool = True,
        on_finished=None,
    ):
        worker = ActionWorker(fn, *args)
        thread = QThread()
        cb = UiCallback()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(cb.result)
        worker.error.connect(cb.error)
        if on_result:
            cb.result.connect(on_result)
        if success_message:
            cb.result.connect(
                lambda _: QMessageBox.information(self, "Cadastro de máquinas", success_message)
            )

        error_handler = on_error or self._show_error
        cb.error.connect(error_handler)
        if show_dialog_errors:
            cb.error.connect(lambda msg: QMessageBox.critical(self, "Cadastro de máquinas", msg))

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        if on_finished:
            thread.finished.connect(on_finished)
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        self.btn_refresh_list.setEnabled(not loading)
        self.btn_save.setEnabled(not loading)
        self.btn_add_operator.setEnabled(not loading)
        self.combo_operator_role.setEnabled(not loading)
        if loading:
            self.result_hint.setText("Sincronizando...")

    def _finish_refresh_step(self):
        self._pending_refreshes = max(0, self._pending_refreshes - 1)
        if self._pending_refreshes:
            return
        self._set_loading(False)
        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        if self._refresh_failed:
            self.save_status.setText("Falha ao sincronizar os dados.")
        else:
            self.save_status.setText("Dados sincronizados com sucesso.")

    def _show_error(self, message: str):
        self.error_label.setText(f"Não foi possível carregar o cadastro de máquinas.\n\n{message}")
        self.error_label.show()
        self.save_status.setText("Falha ao sincronizar os dados.")

    def _on_refresh_error(self, message: str):
        self._refresh_failed = True
        self._show_error(message)

    def _operator_lookup(self) -> dict[str, dict]:
        return {
            str(operator.get("name") or "").strip(): operator
            for operator in self._operators_global
            if isinstance(operator, dict) and operator.get("name")
        }

    def _split_team_rows(self, operators: list[dict]) -> tuple[list[str], list[str]]:
        operator_names: list[str] = []
        helper_names: list[str] = []
        for operator in operators:
            if not isinstance(operator, dict):
                continue
            name = str(operator.get("name") or "").strip()
            if not name:
                continue
            if _normalize_operator_role(operator.get("role")) == "ajudante":
                helper_names.append(name)
            else:
                operator_names.append(name)
        return operator_names, helper_names

    def _team_payload(self) -> list[dict]:
        return [
            {
                "name": str(operator.get("name") or "").strip(),
                "role": _normalize_operator_role(operator.get("role")),
            }
            for operator in self._machine_operator_rows
            if str(operator.get("name") or "").strip()
        ]

    def _populate_operators_global(self, payload: object):
        self._operators_global = [
            {
                "name": str(op.get("name") or "").strip(),
                "role": _normalize_operator_role(op.get("role")),
            }
            for op in (payload if isinstance(payload, list) else [])
            if isinstance(op, dict) and op.get("name")
        ]
        completer = QCompleter(
            [str(op.get("name") or "").strip() for op in self._operators_global],
            self.input_operator,
        )
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.input_operator.setCompleter(completer)

    def _populate_machines(self, payload: object):
        self._machines_all = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        self._fill_table()

    def _fill_table(self):
        self.table.setRowCount(0)
        for machine in self._machines_all:
            row = self.table.rowCount()
            self.table.insertRow(row)

            team_rows = [
                {
                    "name": str(op.get("name") or "").strip(),
                    "role": _normalize_operator_role(op.get("role")),
                }
                for op in (machine.get("operators") or [])
                if isinstance(op, dict) and op.get("name")
            ]
            operator_names, helper_names = self._split_team_rows(team_rows)
            operator_text = self._format_operator_summary(operator_names)
            helper_text = self._format_operator_summary(helper_names)
            values = [
                str(machine.get("name") or "-"),
                str(machine.get("destination") or "-").upper(),
                operator_text,
                helper_text,
                STATUS_LABELS.get(str(machine.get("status") or ""), str(machine.get("status") or "-").upper()),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 2, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 2 and operator_names:
                    item.setToolTip(", ".join(operator_names))
                if col == 3 and helper_names:
                    item.setToolTip(", ".join(helper_names))
                self.table.setItem(row, col, item)

        total = len(self._machines_all)
        self.result_hint.setText(f"{total} máquina(s) importada(s) da produção.")

        target_id = self._pending_machine_id or self._selected_machine_id
        self._pending_machine_id = None
        if target_id is not None and self._select_machine_in_table(target_id):
            return
        if total and self._selected_machine_id is not None and self._select_machine_in_table(self._selected_machine_id):
            return
        if not total:
            self._prepare_new_machine()

    def _format_operator_summary(self, operators: list[str]) -> str:
        clean = [name for name in operators if name]
        if not clean:
            return "-"
        if len(clean) <= 2:
            return ", ".join(clean)
        return f"{clean[0]}, {clean[1]} +{len(clean) - 2}"

    def _select_machine_in_table(self, machine_id: int) -> bool:
        for index, machine in enumerate(self._machines_all):
            if int(machine.get("id") or 0) == int(machine_id):
                self.table.selectRow(index)
                self._load_machine_into_form(machine)
                return True
        return False

    def _prepare_new_machine(self):
        self._selected_machine_id = None
        self._machine_operator_rows = []
        self.form_status.setText("Nova máquina")
        self.save_status.setText("Preencha os dados para cadastrar uma nova máquina.")
        self.input_name.clear()
        self.input_operator.clear()
        self.combo_operator_role.setCurrentIndex(0)
        self.combo_destination.setCurrentIndex(0)
        self._rebuild_operator_list()
        self.table.clearSelection()

    def _load_selected_machine(self, index):
        row = index.row()
        if 0 <= row < len(self._machines_all):
            self._load_machine_into_form(self._machines_all[row])

    def _load_current_selection(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._machines_all):
            self._load_machine_into_form(self._machines_all[row])

    def _load_machine_into_form(self, machine: dict):
        self._selected_machine_id = int(machine.get("id") or 0)
        self.form_status.setText("Cadastro carregado")
        self.save_status.setText("Máquina carregada para edição.")
        self.input_name.setText(str(machine.get("name") or ""))
        self.input_operator.clear()
        self.combo_operator_role.setCurrentIndex(0)

        destination = str(machine.get("destination") or "A&R")
        idx = max(0, self.combo_destination.findData(destination))
        self.combo_destination.blockSignals(True)
        self.combo_destination.setCurrentIndex(idx)
        self.combo_destination.blockSignals(False)

        self._machine_operator_rows = [
            {
                "name": str(op.get("name") or "").strip(),
                "role": _normalize_operator_role(op.get("role")),
            }
            for op in (machine.get("operators") or [])
            if isinstance(op, dict) and op.get("name")
        ]
        self._rebuild_operator_list()

    def _on_destination_changed(self):
        pass  # destino não filtra mais operadores

    def _add_operator_from_input(self):
        name = self.input_operator.text().strip().upper()
        role = _normalize_operator_role(self.combo_operator_role.currentData())
        if not name:
            self.input_operator.clear()
            return

        for operator in self._machine_operator_rows:
            if str(operator.get("name") or "").strip() == name:
                operator["role"] = role
                self._rebuild_operator_list()
                self.input_operator.clear()
                self.combo_operator_role.setCurrentIndex(0)
                return

        self._machine_operator_rows.append({"name": name, "role": role})
        self._rebuild_operator_list()
        self.input_operator.clear()
        self.combo_operator_role.setCurrentIndex(0)

    def _remove_operator(self, name: str):
        self._machine_operator_rows = [
            operator
            for operator in self._machine_operator_rows
            if str(operator.get("name") or "").strip() != name
        ]
        self._rebuild_operator_list()

    def _clear_operator_widgets(self):
        while self.operators_layout.count():
            item = self.operators_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_operator_list(self):
        self._clear_operator_widgets()
        s = self.scale
        if not self._machine_operator_rows:
            empty = QLabel("Nenhuma pessoa vinculada.")
            empty.setProperty("muted", "1")
            empty.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt;")
            self.operators_layout.addWidget(empty)
            self.operators_layout.addStretch()
            return
        for operator in self._machine_operator_rows:
            name = str(operator.get("name") or "").strip()
            role_text = _role_label(operator.get("role"))
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(max(6, int(8 * s)))
            lbl = QLabel(f"{name}  •  {role_text}")
            lbl.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt; color:{theme.TEXT_DARK};")
            row_layout.addWidget(lbl, 1)
            btn_rm = QPushButton("×")
            btn_rm.setFixedSize(max(22, int(26 * s)), max(22, int(26 * s)))
            btn_rm.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{theme.DANGER};"
                f"border:none; font-size:{max(12, int(14 * s))}pt; font-weight:700; }}"
                f"QPushButton:hover {{ color:#B91C1C; }}"
            )
            btn_rm.clicked.connect(lambda _, n=name: self._remove_operator(n))
            row_layout.addWidget(btn_rm)
            self.operators_layout.addWidget(row_widget)
        self.operators_layout.addStretch()

    def _save_machine(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Cadastro de máquinas", "Informe o nome da máquina.")
            return

        payload = {
            "name": name,
            "destination": self._current_destination(),
            "operators": self._team_payload(),
        }
        self.save_status.setText("Salvando cadastro da máquina...")

        if self._selected_machine_id is None:
            self._run_action(
                api.create_production_machine,
                payload,
                on_result=self._after_save,
                success_message="Máquina cadastrada com sucesso.",
            )
            return

        self._run_action(
            api.update_production_machine,
            self._selected_machine_id,
            payload,
            on_result=self._after_save,
            success_message="Cadastro atualizado com sucesso.",
        )

    def _after_save(self, payload: object):
        machine = payload if isinstance(payload, dict) else {}
        self._pending_machine_id = int(machine.get("id") or 0) or None
        self.refresh()

    def _apply_table_style(self) -> None:
        s = self.scale
        self.table.setStyleSheet(theme.neon_table_qss(self.scale))
        theme.apply_neon_table_palette(self.table)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#machineCenterView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#machineCenterContent {{ background:{bg}; }}")
        self.operators_scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:14px; }}"
        )
        self.operators_content.setStyleSheet(f"background:{theme.CARD_BG};")
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        self.btn_refresh_list.setStyleSheet(_flat_secondary_btn_style(s))
        self._apply_table_style()
        self.input_name.setStyleSheet(_field_style(s))
        self.input_operator.setStyleSheet(_field_style(s))
        self.combo_operator_role.setStyleSheet(_field_style(s))
        self.combo_destination.setStyleSheet(_field_style(s))
        self.btn_add_operator.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self._rebuild_operator_list()
