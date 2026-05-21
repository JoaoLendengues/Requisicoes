"""Central de usuarios com importacao, cadastro individual e manutencao de acessos."""

import os
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.session import session


ROLE_OPTIONS = [
    ("ADMINISTRADOR", "admin"),
    ("GERENTE", "gerente"),
    ("PRODUCAO", "producao"),
    ("INDUSTRIA", "industria"),
    ("VENDEDOR", "vendedor"),
]
ROLE_LABELS = {value: label for label, value in ROLE_OPTIONS}
ROLE_LABELS["entrega"] = "INDUSTRIA"

DASH_BG = "#F4F7FB"
DASH_SURFACE = "#FFFFFF"
DASH_PRIMARY = "#1E3A5F"
DASH_SECONDARY = "#27496D"
DASH_DANGER = "#DC2626"
DASH_SUCCESS = "#16A34A"
DASH_WARNING = "#F59E0B"
DASH_TEXT = "#0F172A"
DASH_MUTED = "#64748B"
DASH_BORDER = "#E2E8F0"
DASH_ROW_ALT = "#F8FBFF"


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
    color = QColor(DASH_TEXT)
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
    bg = background or DASH_SURFACE
    border = f"1px solid {border_color}" if border_color else "none"
    hover = hover_background or bg
    card.setStyleSheet(
        f"QFrame#userCenterCard {{"
        f"  background:{bg}; border:{border}; border-radius:{radius}px;"
        f"}}"
        f"QFrame#userCenterCard:hover {{"
        f"  background:{hover}; border:{border};"
        f"}}"
    )
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


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


def _primary_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DASH_PRIMARY}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{DASH_SECONDARY}; }}"
        f"QPushButton:pressed {{ background:#152D49; }}"
        f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
    )


def _danger_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DASH_DANGER}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:#B91C1C; }}"
        f"QPushButton:pressed {{ background:#991B1B; }}"
        f"QPushButton:disabled {{ background:#F0B4B4; color:#FFF7F7; }}"
    )


def _field_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QLineEdit, QComboBox {{"
        f"  background:{DASH_SURFACE}; border:1px solid {DASH_BORDER}; border-radius:14px;"
        f"  padding:9px 12px; font-size:{fs}pt; color:{DASH_TEXT};"
        f"  selection-background-color:{_rgba(DASH_PRIMARY, 24)}; selection-color:{DASH_TEXT};"
        f"}}"
        f"QLineEdit {{ placeholder-text-color:{DASH_MUTED}; }}"
        f"QLineEdit:focus, QComboBox:focus {{ border:1px solid {_rgba(DASH_PRIMARY, 88)}; }}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{DASH_SURFACE}; color:{DASH_TEXT}; border:1px solid {DASH_BORDER};"
        f"  selection-background-color:{_rgba(DASH_PRIMARY, 18)}; selection-color:{DASH_TEXT};"
        f"}}"
    )


def _format_header_date(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y")


def _format_datetime(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y %H:%M")


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


class ImportWorker(QObject):
    progress = Signal(int, int, str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            from ..services.user_importer import import_users

            result = import_users(
                self.path,
                on_progress=lambda current, total, msg: self.progress.emit(current, total, msg),
            )
            self.result.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class UiCallback(QObject):
    result = Signal(object)
    error = Signal(str)


class UserCenterView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._users_all: list[dict] = []
        self._users_visible: list[dict] = []
        self._selected_user_id: int | None = None
        self._pending_code: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = DASH_BG
        self.setObjectName("userCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#userCenterView {{ background:{page_bg}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Central de Usuários")
        title.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Importe usuarios, ajuste niveis de acesso e mantenha senhas e cadastros em dia."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = _make_card(
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
            f"background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.updated_label = QLabel("Pronto para atualizar")
        self.updated_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
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
        content.setObjectName("userCenterContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(
            f"QWidget#userCenterContent {{ background:{page_bg}; }}"
        )
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        layout.addWidget(self._build_import_card())

        body = QHBoxLayout()
        body.setSpacing(max(12, int(14 * s)))
        body.addWidget(self._build_table_card(), 3)
        body.addWidget(self._build_form_card(), 2)
        layout.addLayout(body)
        layout.addStretch()

    def _build_import_card(self) -> QFrame:
        s = self.scale
        card = _make_card(
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
            f"background:{DASH_SECONDARY}; border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        title = QLabel("IMPORTACAO DE USUARIOS")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{DASH_TEXT}; background:transparent;"
        )
        helper = QLabel(
            "Arquivo esperado: usuarios.ods na pasta base, com colunas Codigo, Nome, Contato e Setor."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt;"
        )
        layout.addWidget(accent)
        layout.addWidget(title)
        layout.addWidget(helper)

        row = QHBoxLayout()
        self.input_import_path = QLineEdit(os.path.join(os.getcwd(), "usuarios.ods"))
        self.input_import_path.setFixedHeight(max(38, int(44 * s)))
        self.input_import_path.setStyleSheet(_field_style(s))
        row.addWidget(self.input_import_path, 1)

        browse = QPushButton("...")
        browse.setFixedSize(max(38, int(44 * s)), max(38, int(44 * s)))
        browse.setStyleSheet(_flat_secondary_btn_style(s))
        browse.clicked.connect(self._browse_import_file)
        row.addWidget(browse)

        self.import_btn = QPushButton("IMPORTAR USUARIOS")
        self.import_btn.setFixedHeight(max(38, int(44 * s)))
        self.import_btn.setStyleSheet(_primary_action_btn_style(s))
        self.import_btn.clicked.connect(self._start_import)
        row.addWidget(self.import_btn)
        layout.addLayout(row)

        self.import_progress = QProgressBar()
        self.import_progress.setVisible(False)
        self.import_progress.setStyleSheet(
            f"QProgressBar {{ border:none; border-radius:4px;"
            f"background:{DASH_ROW_ALT}; text-align:center; font-size:{max(8, int(9 * s))}pt; }}"
            f"QProgressBar::chunk {{ background:{DASH_PRIMARY}; border-radius:3px; }}"
        )
        layout.addWidget(self.import_progress)

        self.import_log = QTextEdit()
        self.import_log.setReadOnly(True)
        self.import_log.setMaximumHeight(max(100, int(120 * s)))
        self.import_log.hide()
        self.import_log.setStyleSheet(
            f"background:{DASH_ROW_ALT}; border:none; border-radius:12px;"
            f"font-size:{max(8, int(9 * s))}pt; color:{DASH_TEXT}; padding:6px;"
        )
        layout.addWidget(self.import_log)
        return card

    def _build_table_card(self) -> QFrame:
        s = self.scale
        card = _make_card(
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

        header = QHBoxLayout()
        header.setSpacing(max(10, int(12 * s)))
        title = QLabel("LISTA DE USUARIOS")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{DASH_TEXT}; background:transparent;"
        )
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por codigo, nome, contato ou setor...")
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
        self.table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{DASH_SURFACE};"
            f"  alternate-background-color:{DASH_ROW_ALT}; color:{DASH_TEXT};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{DASH_PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{DASH_SURFACE}; color:{DASH_TEXT};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(DASH_PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{_rgba(DASH_PRIMARY, 18)}; color:{DASH_TEXT}; }}"
            f"QTableWidget::item:alternate {{ background:{DASH_ROW_ALT}; color:{DASH_TEXT}; }}"
        )
        pal = self.table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(DASH_SURFACE))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(DASH_ROW_ALT))
        pal.setColor(QPalette.ColorRole.Text, QColor(DASH_TEXT))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(DASH_TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(DASH_PRIMARY, 40)))
        self.table.setPalette(pal)
        self.table.viewport().setAutoFillBackground(True)
        layout.addWidget(self.table, 1)
        return card

    def _build_form_card(self) -> QFrame:
        s = self.scale
        card = _make_card(
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

        title = QLabel("CADASTRO INDIVIDUAL")
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800;"
            f"color:{DASH_TEXT}; background:transparent;"
        )
        helper = QLabel(
            "Deixe a senha em branco para criar o usuario em primeiro acesso. No cadastro existente, so preencha a senha se quiser altera-la."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt;"
        )
        layout.addWidget(title)
        layout.addWidget(helper)

        grid = QGridLayout()
        grid.setHorizontalSpacing(max(8, int(10 * s)))
        grid.setVerticalSpacing(max(8, int(10 * s)))

        self.form_status = QLabel("Novo usuario")
        self.form_status.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(8, int(9 * s))}pt; font-weight:700;"
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
        self.check_active = QCheckBox("Usuario ativo")
        self.check_active.setChecked(True)
        self.check_active.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(8, int(9 * s))}pt;"
        )

        self.combo_role = QComboBox()
        self.combo_role.setFixedHeight(max(38, int(44 * s)))
        self.combo_role.setStyleSheet(_field_style(s))
        for label, value in ROLE_OPTIONS:
            self.combo_role.addItem(label, value)

        grid.addWidget(self._field_label("Codigo"), 0, 0)
        grid.addWidget(self.input_code, 0, 1)
        grid.addWidget(self._field_label("Nome"), 1, 0)
        grid.addWidget(self.input_name, 1, 1)
        grid.addWidget(self._field_label("Contato"), 2, 0)
        grid.addWidget(self.input_contact, 2, 1)
        grid.addWidget(self._field_label("Setor"), 3, 0)
        grid.addWidget(self.input_sector, 3, 1)
        grid.addWidget(self._field_label("Nivel de acesso"), 4, 0)
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
        label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * self.scale))}pt; font-weight:700;"
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
                lambda _: QMessageBox.information(self, "Central de usuarios", success_message)
            )
        cb.error.connect(self._show_error)
        cb.error.connect(lambda msg: QMessageBox.critical(self, "Central de usuarios", msg))
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
        self.error_label.setText(f"Nao foi possivel carregar a central de usuarios.\n\n{message}")
        self.error_label.show()

    def _populate_users(self, payload: object):
        self._users_all = payload if isinstance(payload, list) else []
        self._apply_filter()
        current = datetime.now()
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
                "Pendente" if user.get("must_change_password") else "Concluido",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

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

    def _browse_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar planilha de usuarios",
            "",
            "Planilhas (*.ods *.xlsx *.xlsm *.xls)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self.input_import_path.setText(path)

    def _start_import(self):
        path = self.input_import_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Central de usuarios", "Informe o caminho da planilha.")
            return

        current = next((pair for pair in self._threads if isinstance(pair[1], ImportWorker)), None)
        if current and current[0].isRunning():
            QMessageBox.information(self, "Central de usuarios", "A importacao atual ainda esta em andamento.")
            return

        self.import_btn.setEnabled(False)
        self.import_btn.setText("IMPORTANDO...")
        self.import_progress.show()
        self.import_progress.setMaximum(3)
        self.import_progress.setValue(0)
        self.import_log.hide()

        worker = ImportWorker(path)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_import_progress)
        worker.result.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(self._reset_import_button)
        thread.start()
        self._threads.append((thread, worker))

    def _on_import_progress(self, current: int, total: int, message: str):
        self.import_progress.setVisible(True)
        self.import_progress.setMaximum(total if total > 0 else 3)
        self.import_progress.setValue(current)
        self.import_progress.setFormat(message)

    def _on_import_done(self, result):
        self.import_progress.setVisible(True)
        self.import_progress.setValue(self.import_progress.maximum())
        self.import_log.show()
        try:
            self.import_log.setPlainText(result.summary())
        except Exception:
            self.import_log.setPlainText("Importacao concluida.")
        self.refresh()

    def _on_import_error(self, message: str):
        self.import_progress.hide()
        self.import_log.show()
        self.import_log.setPlainText(f"Erro:\n{message}")

    def _reset_import_button(self):
        self.import_btn.setEnabled(True)
        self.import_btn.setText("IMPORTAR USUARIOS")

    def _prepare_new_user(self):
        self._selected_user_id = None
        self.form_status.setText("Novo usuario")
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
            role = "industria"
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
            QMessageBox.warning(self, "Central de usuarios", "Informe ao menos codigo e nome.")
            return
        if contact and len(contact_digits) != 11:
            QMessageBox.warning(
                self,
                "Central de usuarios",
                "Informe o contato no formato (61) 9 9999-9999.",
            )
            return
        if password != password_confirm:
            QMessageBox.warning(self, "Central de usuarios", "A confirmacao da senha nao confere.")
            return
        if password and len(password.strip()) < 6:
            QMessageBox.warning(self, "Central de usuarios", "A senha precisa ter pelo menos 6 caracteres.")
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
                success_message="Usuario salvo com sucesso.",
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
            QMessageBox.information(self, "Central de usuarios", "Selecione um usuario primeiro.")
            return
        if self._selected_user_id == session.user_id:
            QMessageBox.warning(self, "Central de usuarios", "Nao e permitido desativar o proprio usuario.")
            return

        reply = QMessageBox.question(
            self,
            "Central de usuarios",
            "Deseja desativar este usuario?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._run_action(
            api.deactivate_user,
            self._selected_user_id,
            on_result=lambda _: (self.refresh(), self._prepare_new_user()),
            success_message="Usuario desativado com sucesso.",
        )
