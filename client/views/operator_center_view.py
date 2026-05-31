"""Cadastro de operadores — aba independente em Configurações."""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
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
from ..core.dialogs import ask_confirmation
from ..core.datetime_utils import format_datetime as _format_datetime, local_now
from ..core.text_case import bind_uppercase_line_edit
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from .user_center_view import (
    ActionWorker,
    UiCallback,
    _danger_action_btn_style,
    _field_style,
    _flat_secondary_btn_style,
    _make_card,
    _primary_action_btn_style,
    _rgba,
)


ROLE_OPTIONS = (
    ("OPERADOR", "operador"),
    ("AJUDANTE", "ajudante"),
)


def _role_label(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "ajudante":
        return "AJUDANTE"
    return "OPERADOR"


class OperatorCenterView(QWidget):
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None, embedded: bool = True):
        super().__init__(parent)
        self.scale = scale
        self.embedded = embedded
        self._threads: list[tuple[QThread, QObject]] = []
        self._operators: list[dict] = []
        self._selected_id: int | None = None
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("operatorCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#operatorCenterView {{ background:{page_bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(max(14, int(18 * s)))

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

        content = QWidget()
        content.setObjectName("operatorCenterContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(f"QWidget#operatorCenterContent {{ background:{page_bg}; }}")
        self._page_scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        body = QHBoxLayout()
        body.setSpacing(max(12, int(14 * s)))
        body.addWidget(self._build_table_card(), 3)
        body.addWidget(self._build_form_card(), 2)
        layout.addLayout(body)
        layout.addStretch()

        self._prepare_new()

    def _build_table_card(self) -> QFrame:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, radius=max(18, int(20 * s)))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                               max(16, int(20 * s)), max(14, int(18 * s)))
        lay.setSpacing(max(10, int(12 * s)))

        hdr = QHBoxLayout()
        hdr.setSpacing(max(8, int(10 * s)))
        title = QLabel("OPERADORES CADASTRADOS")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self.result_hint = QLabel("")
        self.result_hint.setProperty("muted", "1")
        self.result_hint.setStyleSheet(f"font-size:{max(8, int(9 * s))}pt;")
        hdr.addWidget(self.result_hint)

        new_btn = QPushButton("NOVO")
        new_btn.setFixedHeight(max(38, int(44 * s)))
        new_btn.setStyleSheet(_flat_secondary_btn_style(s))
        new_btn.clicked.connect(self._prepare_new)
        hdr.addWidget(new_btn)
        lay.addLayout(hdr)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["NOME", "FUNÇÃO"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_smooth_scroll(self.table)
        self.table.doubleClicked.connect(self._load_selected)
        self.table.itemSelectionChanged.connect(self._load_current_selection)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        head.setMinimumHeight(max(34, int(40 * s)))
        self.table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        self._apply_table_style()
        lay.addWidget(self.table, 1)
        return card

    def _build_form_card(self) -> QFrame:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, radius=max(18, int(20 * s)))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                               max(16, int(20 * s)), max(14, int(18 * s)))
        lay.setSpacing(max(10, int(12 * s)))

        title = QLabel("CADASTRO DE OPERADOR / AJUDANTE")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        helper = QLabel(
            "Cadastre o nome e defina a função da pessoa na produção."
        )
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt;")
        lay.addWidget(title)
        lay.addWidget(helper)

        self.form_status = QLabel("Novo operador")
        self.form_status.setProperty("accent", "1")
        self.form_status.setStyleSheet(f"font-size:{max(8, int(9 * s))}pt; font-weight:700;")
        lay.addWidget(self.form_status)

        name_lbl = QLabel("NOME")
        name_lbl.setProperty("muted", "1")
        name_lbl.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        self.input_name = QLineEdit()
        self.input_name.setFixedHeight(max(38, int(44 * s)))
        self.input_name.setStyleSheet(_field_style(s))
        self.input_name.setPlaceholderText("Nome do operador...")
        self.input_name.returnPressed.connect(self._save)
        bind_uppercase_line_edit(self.input_name)
        lay.addWidget(name_lbl)
        lay.addWidget(self.input_name)

        role_lbl = QLabel("FUNÇÃO")
        role_lbl.setProperty("muted", "1")
        role_lbl.setStyleSheet(f"font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        self.combo_role = QComboBox()
        self.combo_role.setFixedHeight(max(38, int(44 * s)))
        self.combo_role.setStyleSheet(_field_style(s))
        for label, value in ROLE_OPTIONS:
            self.combo_role.addItem(label, value)
        lay.addWidget(role_lbl)
        lay.addWidget(self.combo_role)

        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))

        self.btn_save = QPushButton("SALVAR")
        self.btn_save.setFixedHeight(max(38, int(44 * s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save)
        actions.addWidget(self.btn_save)

        self.btn_delete = QPushButton("EXCLUIR")
        self.btn_delete.setFixedHeight(max(38, int(44 * s)))
        self.btn_delete.setStyleSheet(_danger_action_btn_style(s))
        self.btn_delete.clicked.connect(self._delete)
        self.btn_delete.setEnabled(False)
        actions.addWidget(self.btn_delete)

        clear_btn = QPushButton("LIMPAR")
        clear_btn.setFixedHeight(max(38, int(44 * s)))
        clear_btn.setStyleSheet(_flat_secondary_btn_style(s))
        clear_btn.clicked.connect(self._prepare_new)
        actions.addWidget(clear_btn)
        lay.addLayout(actions)
        lay.addStretch()
        return card

    # ── Lógica ────────────────────────────────────────────────────────────────
    def refresh(self):
        self.error_label.hide()
        self._run_action(api.list_operators, on_result=self._populate)

    def _populate(self, payload: object):
        self._operators = [op for op in (payload or []) if isinstance(op, dict)]
        self.table.setRowCount(0)
        for op in self._operators:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(str(op.get("name") or "-"))
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 0, name_item)
            role_item = QTableWidgetItem(_role_label(op.get("role")))
            role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, role_item)
        n = len(self._operators)
        self.result_hint.setText(f"{n} cadastro(s).")

    def _prepare_new(self):
        self._selected_id = None
        self.form_status.setText("Novo operador")
        self.input_name.clear()
        self.combo_role.setCurrentIndex(0)
        self.btn_delete.setEnabled(False)
        self.table.clearSelection()

    def _load_selected(self, index):
        row = index.row()
        if 0 <= row < len(self._operators):
            self._load_into_form(self._operators[row])

    def _load_current_selection(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._operators):
            self._load_into_form(self._operators[row])

    def _load_into_form(self, op: dict):
        self._selected_id = int(op["id"])
        self.form_status.setText("Cadastro carregado")
        self.input_name.setText(str(op.get("name") or ""))
        role_value = str(op.get("role") or "operador")
        role_index = max(0, self.combo_role.findData(role_value))
        self.combo_role.setCurrentIndex(role_index)
        self.btn_delete.setEnabled(True)

    def _save(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Operadores", "Informe o nome do operador.")
            return
        role = str(self.combo_role.currentData() or "operador")
        if self._selected_id is None:
            self._run_action(
                api.create_operator, {"name": name, "role": role},
                on_result=lambda _: (self.refresh(), self._prepare_new()),
                success_message="Operador cadastrado com sucesso.",
            )
        else:
            self._run_action(
                api.update_operator, self._selected_id, {"name": name, "role": role},
                on_result=lambda _: (self.refresh(), self._prepare_new()),
                success_message="Operador atualizado com sucesso.",
            )

    def _delete(self):
        if self._selected_id is None:
            return
        if not ask_confirmation(
            self, "Operadores", "Deseja excluir este operador?",
            yes_text="Excluir", no_text="Cancelar"
        ):
            return
        self._run_action(
            api.delete_operator, self._selected_id,
            on_result=lambda _: (self.refresh(), self._prepare_new()),
            success_message="Operador excluído com sucesso.",
        )

    # ── Infra de threads ──────────────────────────────────────────────────────
    def _run_action(self, fn, *args, on_result=None, success_message: str = ""):
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
            cb.result.connect(lambda _: QMessageBox.information(self, "Operadores", success_message))
        cb.error.connect(lambda msg: (
            self.error_label.setText(f"Erro: {msg}"),
            self.error_label.show(),
        ))
        cb.error.connect(lambda msg: QMessageBox.critical(self, "Operadores", msg))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread, worker):
        self._threads = [p for p in self._threads if p != (thread, worker)]

    # ── Tema ──────────────────────────────────────────────────────────────────
    def _apply_table_style(self):
        s = self.scale
        self.table.setStyleSheet(
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
            f"  padding:7px 10px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
        )
        pal = self.table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        self.table.setPalette(pal)
        self.table.viewport().setAutoFillBackground(True)

    def apply_theme(self):
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#operatorCenterView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        self.input_name.setStyleSheet(_field_style(s))
        self.combo_role.setStyleSheet(_field_style(s))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_delete.setStyleSheet(_danger_action_btn_style(s))
        self._apply_table_style()
