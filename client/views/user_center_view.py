"""Central de usuários: cadastro individual e manutenção de acessos."""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..core.dialogs import ask_confirmation
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)
from ..core.session import session
from ..core.text_case import bind_uppercase_line_edit


ROLE_OPTIONS = [
    ("ADMINISTRADOR", "admin"),
    ("GERENTE", "gerente"),
    ("A&R", "producao"),
    ("INDÚSTRIA", "industria"),
    ("ENTREGAS", "entregas"),
    ("VENDEDOR", "vendedor"),
]
ROLE_LABELS = {value: label for label, value in ROLE_OPTIONS}
ROLE_LABELS["entrega"] = "ENTREGAS"

def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _format_contact_text(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    digits = digits[-11:]
    if not digits:
        return ""
    if len(digits) <= 2:
        return f"({digits}"
    formatted = f"({digits[:2]})"
    if len(digits) >= 3:
        formatted += f" {digits[2]}"
    if len(digits) >= 4:
        formatted += f" {digits[3:7]}"
    if len(digits) >= 8:
        formatted += f"-{digits[7:11]}"
    return formatted


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.PANEL_SHADOW)
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
    card.setObjectName("userCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#userCenterCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


def _primary_action_btn_style(scale: float) -> str:
    return theme.primary_btn_style(scale)


def _danger_action_btn_style(scale: float) -> str:
    return theme.danger_btn_style(scale)


def _field_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QLineEdit, QComboBox {{"
        f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:14px;"
        f"  padding:9px 12px; font-size:{fs}pt; color:{theme.TEXT_DARK};"
        f"  selection-background-color:{_rgba(theme.PRIMARY, 24)}; selection-color:{theme.TEXT_DARK};"
        f"}}"
        f"QLineEdit {{ placeholder-text-color:{theme.TEXT_MEDIUM}; }}"
        f"QLineEdit:focus, QComboBox:focus {{ border:1px solid {_rgba(theme.PRIMARY, 88)}; }}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; border:1px solid {theme.BORDER_COLOR};"
        f"  selection-background-color:{_rgba(theme.PRIMARY, 18)}; selection-color:{theme.TEXT_DARK};"
        f"}}"
    )


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


class UserCenterView(QWidget):
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.scale = scale
        self.embedded = embedded
        self._threads: list[tuple[QThread, QObject]] = []
        self._users_all: list[dict] = []
        self._users_visible: list[dict] = []
        self._selected_user_id: int | None = None
        self._pending_code: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("userCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#userCenterView {{ background:{page_bg}; }}"
        )
        root = QVBoxLayout(self)
        if self.embedded:
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                    max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        if self.embedded:
            # No modo embarcado (aba de Configurações) o cabeçalho próprio é
            # suprimido — Configurações já fornece título e data. Mantemos os
            # widgets referenciados pela lógica como controles ocultos.
            self.date_label = QLabel(_format_header_date())
            self.updated_label = QLabel("")
            self.refresh_btn = QPushButton()
            self.refresh_btn.hide()
            self.btn_guide = QPushButton()
            self.btn_guide.hide()
            self._build_body(root, page_bg)
            return

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Central de Usuários")
        title.setStyleSheet(
            f"background:transparent; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Importe usuários, ajuste níveis de acesso e mantenha senhas e cadastros em dia."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(10 * s))}pt;"
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
        date_hint.setProperty("muted", "1")
        date_hint.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700; background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"font-size:{max(13, int(16 * s))}pt; font-weight:800; background:transparent;"
        )
        self.updated_label = QLabel("Pronto para atualizar")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
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

        # Botão ? — abre o guia rápido desta tela
        sz_g = max(24, int(28 * s))
        self.btn_guide = QPushButton("?")
        self.btn_guide.setToolTip("Abrir guia rápido")
        self.btn_guide.setFixedSize(sz_g, sz_g)
        self.btn_guide.setStyleSheet(
            f"font-size:{max(10, int(11 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
            f"border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:{sz_g // 2}px; padding:0;"
        )
        self.btn_guide.clicked.connect(self.guide_requested)
        right_col.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        header.addLayout(right_col)
        root.addLayout(header)

        self._build_body(root, page_bg)

    def _build_body(self, root: QVBoxLayout, page_bg: str) -> None:
        s = self.scale
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
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("userCenterContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#userCenterContent {{ background:{page_bg}; }}"
        )
        self._page_scroll.setWidget(self._page_content)
        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        body = QHBoxLayout()
        body.setSpacing(max(12, int(14 * s)))
        self.table_card = self._build_table_card()
        self.form_card = self._build_form_card()
        body.addWidget(self.table_card, 3)
        body.addWidget(self.form_card, 2)
        layout.addLayout(body)
        layout.addStretch()

    def _build_table_card(self) -> QFrame:
        s = self.scale
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

        header = QHBoxLayout()
        header.setSpacing(max(10, int(12 * s)))
        title = QLabel("LISTA DE USUÁRIOS")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por código, nome, contato ou setor...")
        self.search_input.setFixedHeight(max(38, int(44 * s)))
        self.search_input.setStyleSheet(_field_style(s))
        self.search_input.textChanged.connect(self._apply_filter)
        header.addWidget(self.search_input)

        new_btn = QPushButton("NOVO")
        new_btn.setFixedHeight(max(38, int(44 * s)))
        new_btn.setStyleSheet(_flat_secondary_btn_style(s))
        new_btn.clicked.connect(self._prepare_new_user)
        header.addWidget(new_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["CODIGO", "NOME", "CONTATO", "SETOR", "ACESSO", "STATUS", "PRIMEIRO ACESSO"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setShowGrid(False)
        apply_smooth_scroll(self.table)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.doubleClicked.connect(self._load_selected_user)
        self.table.itemSelectionChanged.connect(self._load_current_selection)
        header_widget = self.table.horizontalHeader()
        for col in (1, 2, 3):
            header_widget.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for col in (0, 4, 5, 6):
            header_widget.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header_widget.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header_widget.setMinimumHeight(max(34, int(40 * s)))
        self.table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        self.table.setSortingEnabled(True)
        self.table.setStyleSheet(theme.neon_table_qss(self.scale))
        theme.apply_neon_table_palette(self.table)
        layout.addWidget(self.table, 1)
        return card

    def _build_form_card(self) -> QFrame:
        s = self.scale
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

        title = QLabel("CADASTRO INDIVIDUAL")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        helper = QLabel(
            "Deixe a senha em branco para criar o usuário em primeiro acesso. No cadastro existente, só preencha a senha se quiser alterá-la."
        )
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(
            f"background:transparent; font-size:{max(7, int(8 * s))}pt;"
        )
        layout.addWidget(title)
        layout.addWidget(helper)

        grid = QGridLayout()
        grid.setHorizontalSpacing(max(8, int(10 * s)))
        grid.setVerticalSpacing(max(8, int(10 * s)))

        self.form_status = QLabel("Novo usuário")
        self.form_status.setProperty("accent", "1")
        self.form_status.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:700;"
        )
        layout.addWidget(self.form_status)

        self.input_code = self._input()
        self.input_name = self._input()
        self.input_contact = self._input()
        self.input_contact.setPlaceholderText("(61) 9 9999-9999")
        self.input_contact.setMaxLength(16)
        self.input_contact.textEdited.connect(self._on_contact_edited)
        self.input_sector = self._input()
        self.input_password = self._input(password=True)
        self.input_password_confirm = self._input(password=True)
        bind_uppercase_line_edit(self.input_code)
        bind_uppercase_line_edit(self.input_name)
        bind_uppercase_line_edit(self.input_sector)
        self.check_active = QCheckBox("Usuário ativo")
        self.check_active.setChecked(True)
        self.check_active.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt;"
        )

        self.combo_role = QComboBox()
        self.combo_role.setFixedHeight(max(38, int(44 * s)))
        self.combo_role.setStyleSheet(_field_style(s))
        for label, value in ROLE_OPTIONS:
            self.combo_role.addItem(label, value)

        grid.addWidget(self._field_label("Código"), 0, 0)
        grid.addWidget(self.input_code, 0, 1)
        grid.addWidget(self._field_label("Nome"), 1, 0)
        grid.addWidget(self.input_name, 1, 1)
        grid.addWidget(self._field_label("Contato"), 2, 0)
        grid.addWidget(self.input_contact, 2, 1)
        grid.addWidget(self._field_label("Setor"), 3, 0)
        grid.addWidget(self.input_sector, 3, 1)
        grid.addWidget(self._field_label("Nível de acesso"), 4, 0)
        grid.addWidget(self.combo_role, 4, 1)
        grid.addWidget(self._field_label("Nova senha"), 5, 0)
        grid.addWidget(self.input_password, 5, 1)
        grid.addWidget(self._field_label("Confirmar senha"), 6, 0)
        grid.addWidget(self.input_password_confirm, 6, 1)
        layout.addLayout(grid)
        layout.addWidget(self.check_active)

        actions = QHBoxLayout()
        self.btn_save = QPushButton("SALVAR")
        self.btn_save.setFixedHeight(max(38, int(44 * s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save_user)
        actions.addWidget(self.btn_save)

        self.btn_disable = QPushButton("DESATIVAR")
        self.btn_disable.setFixedHeight(max(38, int(44 * s)))
        self.btn_disable.setStyleSheet(_danger_action_btn_style(s))
        self.btn_disable.clicked.connect(self._deactivate_user)
        actions.addWidget(self.btn_disable)

        clear_btn = QPushButton("LIMPAR")
        clear_btn.setFixedHeight(max(38, int(44 * s)))
        clear_btn.setStyleSheet(_flat_secondary_btn_style(s))
        clear_btn.clicked.connect(self._prepare_new_user)
        actions.addWidget(clear_btn)
        layout.addLayout(actions)
        layout.addStretch()
        return card

    def _input(self, password: bool = False) -> QLineEdit:
        s = self.scale
        field = QLineEdit()
        field.setFixedHeight(max(38, int(44 * s)))
        field.setStyleSheet(_field_style(s))
        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setProperty("muted", "1")
        label.setStyleSheet(
            f"font-size:{max(7, int(8 * self.scale))}pt; font-weight:700;"
            f"background:transparent;"
        )
        return label

    def _on_contact_edited(self, text: str):
        self._set_contact_text(text)

    def _set_contact_text(self, raw: str):
        formatted = _format_contact_text(raw)
        if self.input_contact.text() == formatted:
            return
        self.input_contact.blockSignals(True)
        self.input_contact.setText(formatted)
        self.input_contact.setCursorPosition(len(formatted))
        self.input_contact.blockSignals(False)

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()
        self._run_action(api.list_users, on_result=self._populate_users)

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
            cb.result.connect(
                lambda _: QMessageBox.information(self, "Central de usuários", success_message)
            )
        cb.error.connect(self._show_error)
        cb.error.connect(lambda msg: QMessageBox.critical(self, "Central de usuários", msg))
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
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.updated_label.setText("Falha ao atualizar")
        self.error_label.setText(f"Não foi possível carregar a central de usuários.\n\n{message}")
        self.error_label.show()

    def _populate_users(self, payload: object):
        self._users_all = payload if isinstance(payload, list) else []
        self._apply_filter()
        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

    def _apply_filter(self):
        term = self.search_input.text().strip().lower()
        if not term:
            self._users_visible = list(self._users_all)
        else:
            self._users_visible = []
            for user in self._users_all:
                if not isinstance(user, dict):
                    continue
                haystack = " ".join(
                    [
                        str(user.get("code") or ""),
                        str(user.get("name") or ""),
                        str(user.get("whatsapp") or ""),
                        str(user.get("sector") or ""),
                        ROLE_LABELS.get(str(user.get("role") or ""), str(user.get("role") or "")),
                    ]
                ).lower()
                if term in haystack:
                    self._users_visible.append(user)
        self._fill_table()

    def _fill_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for user in self._users_visible:
            if not isinstance(user, dict):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                str(user.get("code") or "-"),
                str(user.get("name") or "-"),
                _format_contact_text(str(user.get("whatsapp") or "")) or "-",
                str(user.get("sector") or "-"),
                ROLE_LABELS.get(str(user.get("role") or ""), str(user.get("role") or "-")),
                "Ativo" if user.get("is_active") else "Inativo",
                "Pendente" if user.get("must_change_password") else "Concluído",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)

        if self._pending_code:
            matched = False
            for index, user in enumerate(self._users_visible):
                if str(user.get("code") or "") == self._pending_code:
                    self.table.selectRow(index)
                    self._load_user_into_form(user)
                    matched = True
                    break
            if matched or not self._users_visible:
                self._pending_code = None

    def _prepare_new_user(self):
        self._selected_user_id = None
        self.form_status.setText("Novo usuário")
        self.input_code.clear()
        self.input_name.clear()
        self.input_contact.clear()
        self.input_sector.clear()
        self.combo_role.setCurrentIndex(max(0, self.combo_role.findData("vendedor")))
        self.input_password.clear()
        self.input_password_confirm.clear()
        self.check_active.setChecked(True)
        self.btn_disable.setEnabled(False)

    def _load_selected_user(self, index):
        row = index.row()
        if 0 <= row < len(self._users_visible):
            self._load_user_into_form(self._users_visible[row])

    def _load_current_selection(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._users_visible):
            self._load_user_into_form(self._users_visible[row])

    def _load_user_into_form(self, user: dict):
        self._selected_user_id = int(user["id"])
        self.form_status.setText(
            "Primeiro acesso pendente" if user.get("must_change_password") else "Cadastro carregado"
        )
        self.input_code.setText(str(user.get("code") or ""))
        self.input_name.setText(str(user.get("name") or ""))
        self._set_contact_text(str(user.get("whatsapp") or ""))
        self.input_sector.setText(str(user.get("sector") or ""))
        role = str(user.get("role") or "vendedor")
        if role == "entrega":
            role = "entregas"
        idx = max(0, self.combo_role.findData(role))
        self.combo_role.setCurrentIndex(idx)
        self.input_password.clear()
        self.input_password_confirm.clear()
        self.check_active.setChecked(bool(user.get("is_active")))
        self.btn_disable.setEnabled(True)

    def _save_user(self):
        code = self.input_code.text().strip()
        name = self.input_name.text().strip()
        contact = _format_contact_text(self.input_contact.text().strip())
        sector = self.input_sector.text().strip()
        role = self.combo_role.currentData()
        password = self.input_password.text()
        password_confirm = self.input_password_confirm.text()
        contact_digits = "".join(ch for ch in contact if ch.isdigit())

        if not code or not name:
            QMessageBox.warning(self, "Central de usuários", "Informe ao menos código e nome.")
            return
        if contact and len(contact_digits) != 11:
            QMessageBox.warning(
                self,
                "Central de usuários",
                "Informe o contato no formato (61) 9 9999-9999.",
            )
            return
        if password != password_confirm:
            QMessageBox.warning(self, "Central de usuários", "A confirmação da senha não confere.")
            return
        if password and len(password.strip()) < 6:
            QMessageBox.warning(self, "Central de usuários", "A senha precisa ter pelo menos 6 caracteres.")
            return

        self._set_contact_text(contact)

        payload = {
            "code": code,
            "name": name,
            "whatsapp": contact or None,
            "sector": sector or None,
            "role": role,
            "is_active": self.check_active.isChecked(),
        }
        if password.strip():
            payload["password"] = password.strip()

        self._pending_code = code
        def _after_save(_):
            if self._selected_user_id == session.user_id:
                session.user_name = name
                session.user_code = code
                session.whatsapp = contact
            self.refresh()
        if self._selected_user_id is None:
            self._run_action(
                api.create_user,
                payload,
                on_result=_after_save,
                success_message="Usuário salvo com sucesso.",
            )
        else:
            self._run_action(
                api.update_user,
                self._selected_user_id,
                payload,
                on_result=_after_save,
                success_message="Cadastro atualizado com sucesso.",
            )

    def _deactivate_user(self):
        if self._selected_user_id is None:
            QMessageBox.information(self, "Central de usuários", "Selecione um usuário primeiro.")
            return
        if self._selected_user_id == session.user_id:
            QMessageBox.warning(self, "Central de usuários", "Não é permitido desativar o próprio usuário.")
            return

        reply = ask_confirmation(
            self,
            "Central de usuários",
            "Deseja desativar este usuário?",
            yes_text="Sim",
            no_text="Não",
        )
        if not reply:
            return

        self._run_action(
            api.deactivate_user,
            self._selected_user_id,
            on_result=lambda _: (self.refresh(), self._prepare_new_user()),
            success_message="Usuário desativado com sucesso.",
        )

    def _apply_table_style(self) -> None:
        s = self.scale
        self.table.setStyleSheet(theme.neon_table_qss(self.scale))
        theme.apply_neon_table_palette(self.table)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#userCenterView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#userCenterContent {{ background:{bg}; }}")
        if not self.embedded:
            self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        self.search_input.setStyleSheet(_field_style(s))
        self._apply_table_style()
        self.combo_role.setStyleSheet(_field_style(s))
        for inp in (
            self.input_code, self.input_name, self.input_contact,
            self.input_sector, self.input_password, self.input_password_confirm,
        ):
            inp.setStyleSheet(_field_style(s))
        self.check_active.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * s))}pt;")
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_disable.setStyleSheet(_danger_action_btn_style(s))
