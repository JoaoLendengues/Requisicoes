import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QMessageBox, QSpinBox, QFileDialog, QCheckBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor

from ..core import theme
from ..core import login_backgrounds
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)
from ..core.resolution import res, SCALE_STEPS, FONT_SIZE_STEPS
from ..core.session import session
from ..api import client as api


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.TEXT_DARK)
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
    card.setObjectName("settingsCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#settingsCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _section(title: str, scale: float) -> QLabel:
    cleaned = title.lstrip("⚙️🌐🎨📥📦 ").strip()
    lbl = QLabel(cleaned)
    lbl.setStyleSheet(
        f"font-size:{max(10,int(12*scale))}pt; font-weight:800; padding-top:4px;"
    )
    return lbl


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedHeight(4)
    sep.setProperty("theme_bg", "separator")
    sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    sep.setStyleSheet("border:none; border-radius:2px;")
    return sep


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


def _primary_action_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{theme.PRIMARY}; color:#FFFFFF; border:none; border-radius:14px;"
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{theme.PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background:#152D49; }}"
        f"QPushButton:disabled {{ background:#A7B3C6; color:#F8FAFC; }}"
    )


def _field_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QLineEdit, QTextEdit, QSpinBox {{"
        f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:14px;"
        f"  padding:9px 12px; font-size:{fs}pt; color:{theme.TEXT_DARK};"
        f"  selection-background-color:{_rgba(theme.PRIMARY, 24)}; selection-color:{theme.TEXT_DARK};"
        f"}}"
        f"QLineEdit {{ placeholder-text-color:{theme.TEXT_MEDIUM}; }}"
    )


def _spinbox_style(scale: float) -> str:
    """Estilo completo para QSpinBox: campo + botões arredondados + setas finas."""
    fs   = max(9, int(10 * scale))
    bw   = max(20, int(24 * scale))   # largura dos botões up/down
    aw   = max(7,  int(9  * scale))   # tamanho das setas
    return (
        f"QSpinBox {{"
        f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:14px;"
        f"  padding:9px {bw + 4}px 9px 12px; font-size:{fs}pt; color:{theme.TEXT_DARK};"
        f"  selection-background-color:{_rgba(theme.PRIMARY, 24)}; selection-color:{theme.TEXT_DARK};"
        f"}}"
        f"QSpinBox::up-button {{"
        f"  subcontrol-origin:border; subcontrol-position:top right;"
        f"  width:{bw}px; border:none; background:transparent;"
        f"  border-top-right-radius:13px;"
        f"}}"
        f"QSpinBox::down-button {{"
        f"  subcontrol-origin:border; subcontrol-position:bottom right;"
        f"  width:{bw}px; border:none; background:transparent;"
        f"  border-bottom-right-radius:13px;"
        f"}}"
        f"QSpinBox::up-button:hover, QSpinBox::down-button:hover {{"
        f"  background:{_rgba(theme.PRIMARY, 18)};"
        f"}}"
        f"QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{"
        f"  background:{_rgba(theme.PRIMARY, 36)};"
        f"}}"
        f"QSpinBox::up-arrow   {{ width:{aw}px; height:{aw}px; }}"
        f"QSpinBox::down-arrow {{ width:{aw}px; height:{aw}px; }}"
    )



def _checkbox_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    sz = max(14, int(16 * scale))
    return (
        f"QCheckBox {{ font-size:{fs}pt; color:{theme.TEXT_DARK}; spacing:8px; }}"
        f"QCheckBox::indicator {{"
        f"  width:{sz}px; height:{sz}px;"
        f"  border:1.5px solid {theme.BORDER_COLOR}; border-radius:4px;"
        f"  background:{theme.CARD_BG};"
        f"}}"
        f"QCheckBox::indicator:checked {{"
        f"  background:{theme.PRIMARY}; border-color:{theme.PRIMARY};"
        f"}}"
        f"QCheckBox::indicator:hover {{ border-color:{theme.PRIMARY}; }}"
    )


def _table_style() -> str:
    return (
        f"QTableWidget {{"
        f"  background:{theme.CARD_BG}; gridline-color:{theme.BORDER_COLOR};"
        f"  border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
        f"  font-size:9pt;"
        f"}}"
        f"QTableWidget::item {{ padding:6px 10px; color:{theme.TEXT_DARK}; }}"
        f"QTableWidget::item:selected {{"
        f"  background:{theme.SELECTION_BG}; color:{theme.TEXT_DARK};"
        f"}}"
        f"QHeaderView::section {{"
        f"  background:{theme.TABLE_HEADER_BG}; color:#fff;"
        f"  padding:6px 10px; border:none; font-weight:700; font-size:9pt;"
        f"}}"
        f"QHeaderView::section:first {{ border-top-left-radius:10px; }}"
        f"QHeaderView::section:last  {{ border-top-right-radius:10px; }}"
    )



class SettingsApiWorker(QObject):
    result = Signal(str, object)
    error = Signal(str, str)
    finished = Signal()

    def __init__(self, action: str, payload: dict | None = None):
        super().__init__()
        self.action = action
        self.payload = payload or {}

    def run(self):
        try:
            if self.action == "load_operational":
                result = api.get_operational_settings()
            elif self.action == "save_operational":
                result = api.update_operational_settings(self.payload)
            elif self.action == "trigger_backup":
                result = api.trigger_backup()
            elif self.action == "list_backups":
                result = api.list_backups()
            elif self.action == "change_password":
                result = api.change_password(
                    self.payload["current_password"],
                    self.payload["new_password"],
                )
            elif self.action == "get_backup_settings":
                result = api.get_backup_settings()
            elif self.action == "save_backup_settings":
                result = api.update_backup_settings(self.payload)
            else:
                raise ValueError(f"Acao invalida: {self.action}")
            self.result.emit(self.action, result)
        except api.APIError as exc:
            self.error.emit(self.action, exc.detail)
        except Exception as exc:
            self.error.emit(self.action, str(exc))
        finally:
            self.finished.emit()


class SettingsView(QWidget):
    scale_changed = Signal(float)
    font_size_changed = Signal()
    show_guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._pending_save_context: dict | None = None
        self._setup_ui()
        if session.settings_show_billing:
            self.refresh_operational_settings(silent=True)

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("settingsView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#settingsView {{ background:{page_bg}; }}")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                       max(18, int(24 * s)), 0)
        root_layout.setSpacing(0)

        # ── Cabeçalho ─────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Configurações")
        title.setStyleSheet(f"font-size:{max(18, int(24 * s))}pt; font-weight:800;")
        subtitle = QLabel("Preferências e configurações do sistema.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        info_card = _make_card(s, theme.CARD_BG, border_color=None,
                               radius=max(16, int(18 * s)))
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
        self.updated_label = QLabel("Preferências do sistema")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)
        header.addWidget(info_card, 0, Qt.AlignmentFlag.AlignTop)

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
        self.btn_guide.clicked.connect(self.show_guide_requested)
        header.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        root_layout.addLayout(header)
        root_layout.addSpacing(max(12, int(16 * s)))

        # ── Barra de abas ──────────────────────────────────────────────────
        self._tab_btns: list[QPushButton] = []
        self._system_tab_index = -1
        tab_bar = QWidget()
        tab_bar.setObjectName("settingsTabBar")
        tab_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tab_bar.setStyleSheet("QWidget#settingsTabBar { background:transparent; }")
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(0)
        root_layout.addWidget(tab_bar)

        # linha separadora sob as abas
        self._tab_sep = QFrame()
        self._tab_sep.setFrameShape(QFrame.Shape.NoFrame)
        self._tab_sep.setFixedHeight(1)
        self._tab_sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tab_sep.setStyleSheet(
            f"QFrame {{ background:{theme.BORDER_COLOR}; border:none; }}"
        )
        root_layout.addWidget(self._tab_sep)
        root_layout.addSpacing(max(10, int(12 * s)))

        # ── Área de scroll (conteúdo das abas) ────────────────────────────
        self._page_scroll = SmoothScrollArea(self)
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root_layout.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("settingsContainer")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#settingsContainer {{ background:{page_bg}; }}"
        )
        self._page_scroll.setWidget(self._page_content)

        outer = QVBoxLayout(self._page_content)
        outer.setContentsMargins(0, 0, 0, max(16, int(20 * s)))
        outer.setSpacing(0)

        self._tab_stack = QStackedWidget()
        outer.addWidget(self._tab_stack)

        # ── Botão global de salvar (fora do scroll, fixo no rodapé) ──────
        root_layout.addSpacing(max(8, int(10 * s)))
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, max(16, int(20 * s)))
        self.btn_save = QPushButton("SALVAR CONFIGURAÇÕES")
        self.btn_save.setFixedHeight(max(38, int(44 * s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save)
        save_row.addWidget(self.btn_save)
        save_row.addStretch()
        root_layout.addLayout(save_row)

        # ════ Helpers para construção das abas ═══════════════════════════

        _cm = (max(16, int(20 * s)), max(14, int(18 * s)),
               max(16, int(20 * s)), max(14, int(18 * s)))
        _cs = max(12, int(16 * s))

        def _new_card() -> QFrame:
            return _make_card(s, theme.CARD_BG, border_color=None,
                              radius=max(18, int(20 * s)))

        def _wrap(card: QFrame) -> QWidget:
            """Envolve um card numa página com padding superior e stretch."""
            pg = QWidget()
            pg.setObjectName("settingsTabPage")
            pg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            pg.setStyleSheet(f"QWidget#settingsTabPage {{ background:{page_bg}; }}")
            lt = QVBoxLayout(pg)
            lt.setContentsMargins(0, max(12, int(14 * s)), 0, 0)
            lt.setSpacing(0)
            lt.addWidget(card)
            lt.addStretch()
            return pg

        def _add_tab(label: str, page: QWidget) -> None:
            idx = len(self._tab_btns)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setStyleSheet(self._tab_btn_style(s))
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
            tab_bar_layout.addWidget(btn)
            self._tab_btns.append(btn)
            self._tab_stack.addWidget(page)

        # ════════════════════════════════════════════════════════════════
        # ABA: Aparência
        # ════════════════════════════════════════════════════════════════
        card_ap = _new_card()
        lay_ap = QVBoxLayout(card_ap)
        lay_ap.setContentsMargins(*_cm)
        lay_ap.setSpacing(_cs)

        lay_ap.addWidget(_section("Aparência", s))
        lay_ap.addWidget(_separator())

        scale_row = QHBoxLayout()
        scale_row.setSpacing(max(6, int(8 * s)))
        scale_row.addWidget(self._lbl("Escala da interface:", s))

        self._scale_btns: dict[str, QPushButton] = {}
        active_label = res.scale_label
        for label, _factor in SCALE_STEPS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(label == active_label)
            btn.setFixedHeight(max(32, int(36 * s)))
            btn.setStyleSheet(self._scale_btn_style(s))
            btn.clicked.connect(lambda checked=False, lbl=label: self._on_scale_btn(lbl))
            scale_row.addWidget(btn)
            self._scale_btns[label] = btn
        scale_row.addStretch()
        lay_ap.addLayout(scale_row)

        self.screen_info = QLabel(
            f"Resolução detectada: {res.screen_width}x{res.screen_height}  |  "
            f"DPI: {res.dpi:.0f}  |  Recomendado: {res.recommended_label}"
        )
        self.screen_info.setProperty("muted", "1")
        self.screen_info.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        lay_ap.addWidget(self.screen_info)

        lay_ap.addWidget(_section("Tamanho de Fonte", s))
        lay_ap.addWidget(_separator())

        font_size_row = QHBoxLayout()
        font_size_row.setSpacing(max(6, int(8 * s)))
        font_size_row.addWidget(self._lbl("Tamanho do texto:", s))

        self._font_size_btns: dict[str, QPushButton] = {}
        active_font_label = res.font_size_label
        for label, _factor in FONT_SIZE_STEPS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(label == active_font_label)
            btn.setFixedHeight(max(32, int(36 * s)))
            btn.setStyleSheet(self._scale_btn_style(s))
            btn.clicked.connect(lambda checked=False, lbl=label: self._on_font_size_btn(lbl))
            font_size_row.addWidget(btn)
            self._font_size_btns[label] = btn
        font_size_row.addStretch()
        lay_ap.addLayout(font_size_row)

        font_size_hint = QLabel(
            "Aumenta ou reduz apenas os textos, mantendo o layout da interface."
        )
        font_size_hint.setProperty("muted", "1")
        font_size_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        lay_ap.addWidget(font_size_hint)

        _add_tab("Aparência", _wrap(card_ap))

        # ════════════════════════════════════════════════════════════════
        # ABA: Conta
        # ════════════════════════════════════════════════════════════════
        card_ct = _new_card()
        lay_ct = QVBoxLayout(card_ct)
        lay_ct.setContentsMargins(*_cm)
        lay_ct.setSpacing(_cs)

        lay_ct.addWidget(_section("Alterar Senha", s))
        lay_ct.addWidget(_separator())

        pwd_grid = QGridLayout()
        pwd_grid.setSpacing(max(8, int(10 * s)))

        pwd_grid.addWidget(self._lbl("Senha atual:", s), 0, 0)
        self._input_pwd_current = QLineEdit()
        self._input_pwd_current.setEchoMode(QLineEdit.EchoMode.Password)
        self._input_pwd_current.setPlaceholderText("Digite sua senha atual")
        self._input_pwd_current.setFixedHeight(max(38, int(44 * s)))
        self._input_pwd_current.setStyleSheet(_field_style(s))
        pwd_grid.addWidget(self._input_pwd_current, 0, 1)

        pwd_grid.addWidget(self._lbl("Nova senha:", s), 1, 0)
        self._input_pwd_new = QLineEdit()
        self._input_pwd_new.setEchoMode(QLineEdit.EchoMode.Password)
        self._input_pwd_new.setPlaceholderText("Mínimo 6 caracteres")
        self._input_pwd_new.setFixedHeight(max(38, int(44 * s)))
        self._input_pwd_new.setStyleSheet(_field_style(s))
        pwd_grid.addWidget(self._input_pwd_new, 1, 1)

        pwd_grid.addWidget(self._lbl("Confirmar nova senha:", s), 2, 0)
        self._input_pwd_confirm = QLineEdit()
        self._input_pwd_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._input_pwd_confirm.setPlaceholderText("Repita a nova senha")
        self._input_pwd_confirm.setFixedHeight(max(38, int(44 * s)))
        self._input_pwd_confirm.setStyleSheet(_field_style(s))
        pwd_grid.addWidget(self._input_pwd_confirm, 2, 1)

        lay_ct.addLayout(pwd_grid)

        pwd_action_row = QHBoxLayout()
        pwd_action_row.setSpacing(max(8, int(10 * s)))
        self._btn_change_pwd = QPushButton("Alterar Senha")
        self._btn_change_pwd.setFixedHeight(max(38, int(44 * s)))
        self._btn_change_pwd.setStyleSheet(_flat_secondary_btn_style(s))
        self._btn_change_pwd.clicked.connect(self._on_change_password)
        pwd_action_row.addWidget(self._btn_change_pwd)
        self._lbl_pwd_status = QLabel("")
        self._lbl_pwd_status.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        pwd_action_row.addWidget(self._lbl_pwd_status)
        pwd_action_row.addStretch()
        lay_ct.addLayout(pwd_action_row)

        _add_tab("Conta", _wrap(card_ct))

        # ════════════════════════════════════════════════════════════════
        # ABA: Sistema (admin + gerente)
        # ════════════════════════════════════════════════════════════════
        if session.settings_show_billing or session.settings_show_connection:
            card_sis = _new_card()
            lay_sis = QVBoxLayout(card_sis)
            lay_sis.setContentsMargins(*_cm)
            lay_sis.setSpacing(_cs)

            # Conexão com o Servidor (admin only)
            self._conn_section = QWidget()
            conn_vl = QVBoxLayout(self._conn_section)
            conn_vl.setContentsMargins(0, 0, 0, 0)
            conn_vl.setSpacing(max(8, int(10 * s)))
            conn_vl.addWidget(_section("Conexão com o Servidor", s))
            conn_vl.addWidget(_separator())
            conn_grid = QGridLayout()
            conn_grid.setSpacing(max(8, int(10 * s)))
            conn_grid.addWidget(self._lbl("URL do servidor:", s), 0, 0)
            self.input_url = QLineEdit(res.server_url)
            self.input_url.setFixedHeight(max(38, int(44 * s)))
            self.input_url.setStyleSheet(_field_style(s))
            self.input_url.setPlaceholderText("http://192.168.1.100:5000")
            self.input_url.setReadOnly(True)
            self.input_url.setToolTip(
                "A URL do servidor é fixa e não pode ser alterada nesta tela."
            )
            conn_grid.addWidget(self.input_url, 0, 1)
            self.btn_test = QPushButton("Testar conexão")
            self.btn_test.setFixedHeight(max(38, int(44 * s)))
            self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
            self.btn_test.clicked.connect(self._test_connection)
            conn_grid.addWidget(self.btn_test, 0, 2)
            self.lbl_conn_status = QLabel("")
            self.lbl_conn_status.setProperty("muted", "1")
            self.lbl_conn_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
            conn_grid.addWidget(self.lbl_conn_status, 1, 1, 1, 2)
            conn_vl.addLayout(conn_grid)
            lay_sis.addWidget(self._conn_section)
            self._conn_section.setVisible(session.settings_show_connection)

            # Alertas de Faturamento (admin + gerente)
            self._billing_section = QWidget()
            billing_vl = QVBoxLayout(self._billing_section)
            billing_vl.setContentsMargins(0, 0, 0, 0)
            billing_vl.setSpacing(max(8, int(10 * s)))
            billing_vl.addWidget(_section("Alertas de Faturamento", s))
            billing_vl.addWidget(_separator())
            billing_row = QHBoxLayout()
            billing_row.setSpacing(max(8, int(10 * s)))
            billing_row.addWidget(self._lbl("Dias para notificar gerente:", s))
            self.input_pending_invoice_days = QSpinBox()
            self.input_pending_invoice_days.setRange(1, 3650)
            self.input_pending_invoice_days.setValue(
                int(res._read_file().get("pending_invoice_alert_days", 1) or 1)
            )
            self.input_pending_invoice_days.setFixedHeight(max(38, int(44 * s)))
            self.input_pending_invoice_days.setFixedWidth(max(110, int(130 * s)))
            self.input_pending_invoice_days.setStyleSheet(_spinbox_style(s))
            billing_row.addWidget(self.input_pending_invoice_days)
            billing_row.addStretch()
            billing_vl.addLayout(billing_row)
            self.operational_status = QLabel(
                "Sincronizando prazo de alerta com o servidor..."
            )
            self.operational_status.setProperty("muted", "1")
            self.operational_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
            billing_vl.addWidget(self.operational_status)

            # Prazo mínimo de entrega (dias úteis)
            billing_vl.addSpacing(max(6, int(8 * s)))
            billing_vl.addWidget(_section("Prazo Mínimo de Entrega", s))
            billing_vl.addWidget(_separator())
            min_deliv_row = QHBoxLayout()
            min_deliv_row.setSpacing(max(8, int(10 * s)))
            min_deliv_row.addWidget(self._lbl("Mínimo de dias úteis:", s))
            self.input_min_delivery_days = QSpinBox()
            self.input_min_delivery_days.setRange(0, 365)
            self.input_min_delivery_days.setValue(
                int(res._read_file().get("min_delivery_business_days", 0) or 0)
            )
            self.input_min_delivery_days.setFixedHeight(max(38, int(44 * s)))
            self.input_min_delivery_days.setFixedWidth(max(110, int(130 * s)))
            self.input_min_delivery_days.setStyleSheet(_spinbox_style(s))
            min_deliv_row.addWidget(self.input_min_delivery_days)
            min_deliv_row.addStretch()
            billing_vl.addLayout(min_deliv_row)
            min_deliv_hint = QLabel(
                "0 = sem restrição. Define quantos dias úteis (seg-sex) à frente o "
                "vendedor deve agendar a entrega. Admin e gerente podem salvar abaixo do mínimo."
            )
            min_deliv_hint.setWordWrap(True)
            min_deliv_hint.setProperty("muted", "1")
            min_deliv_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
            billing_vl.addWidget(min_deliv_hint)

            lay_sis.addWidget(self._billing_section)
            self._billing_section.setVisible(session.settings_show_billing)

            # ── Painel Técnico embarcado (admin) ─────────────────────────────
            # Migrado da antiga tela "Painel Técnico" da sidebar para cá.
            self._technical_panel = None
            if session.can_access_technical_panel:
                from .technical_panel_view import TechnicalPanelView
                self._technical_panel = TechnicalPanelView(s, embedded=True)
                self._technical_panel.guide_requested.connect(self.show_guide_requested)

            if self._technical_panel is not None:
                # O card de configurações de sistema + o painel técnico convivem
                # na mesma aba. O painel fica fora do card (sobre o page_bg) para
                # preservar o contraste original entre seus cards e o fundo.
                sis_page = QWidget()
                sis_page.setObjectName("settingsTabPage")
                sis_page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                sis_page.setStyleSheet(
                    f"QWidget#settingsTabPage {{ background:{page_bg}; }}"
                )
                sis_lt = QVBoxLayout(sis_page)
                sis_lt.setContentsMargins(0, max(12, int(14 * s)), 0, 0)
                sis_lt.setSpacing(max(14, int(18 * s)))
                sis_lt.addWidget(card_sis)
                sis_lt.addWidget(self._technical_panel)
                sis_lt.addStretch()
                self._system_tab_index = len(self._tab_btns)
                _add_tab("Sistema", sis_page)
            else:
                _add_tab("Sistema", _wrap(card_sis))
        else:
            self._technical_panel = None
            # Placeholders para roles sem acesso ao painel de sistema
            self._conn_section        = QWidget()
            self._billing_section     = QWidget()
            self.input_url            = QLineEdit()
            self.btn_test             = QPushButton()
            self.lbl_conn_status      = QLabel()
            self.input_pending_invoice_days = QSpinBox()
            self.input_min_delivery_days = QSpinBox()
            self.operational_status   = QLabel()

        # ════════════════════════════════════════════════════════════════
        # ABA: Login (admin only)
        # ════════════════════════════════════════════════════════════════
        if session.settings_show_login_backgrounds:
            card_bg = _new_card()
            lay_bg = QVBoxLayout(card_bg)
            lay_bg.setContentsMargins(*_cm)
            lay_bg.setSpacing(max(8, int(10 * s)))

            lay_bg.addWidget(_section("Fundo da Tela de Login", s))
            lay_bg.addWidget(_separator())

            bg_folder_row = QHBoxLayout()
            bg_folder_row.setSpacing(max(8, int(10 * s)))
            bg_folder_row.addWidget(self._lbl("Pasta de imagens:", s))
            self.input_bg_folder = QLineEdit(res.bg_folder)
            self.input_bg_folder.setFixedHeight(max(38, int(44 * s)))
            self.input_bg_folder.setStyleSheet(_field_style(s))
            self.input_bg_folder.setPlaceholderText(
                r"Z:\REQUISIÇÕES (VENDAS)\login_backgrounds"
            )
            bg_folder_row.addWidget(self.input_bg_folder, 1)
            self._btn_browse_bg_folder = QPushButton("Procurar")
            self._btn_browse_bg_folder.setFixedHeight(max(38, int(44 * s)))
            self._btn_browse_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_browse_bg_folder.clicked.connect(self._browse_bg_folder)
            bg_folder_row.addWidget(self._btn_browse_bg_folder)
            self._btn_verify_bg_folder = QPushButton("Verificar")
            self._btn_verify_bg_folder.setFixedHeight(max(38, int(44 * s)))
            self._btn_verify_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_verify_bg_folder.clicked.connect(self._verify_bg_folder)
            bg_folder_row.addWidget(self._btn_verify_bg_folder)
            lay_bg.addLayout(bg_folder_row)

            self._lbl_bg_folder_status = QLabel("")
            self._lbl_bg_folder_status.setWordWrap(True)
            self._lbl_bg_folder_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
            lay_bg.addWidget(self._lbl_bg_folder_status)

            bg_folder_hint = QLabel(
                "Pasta compartilhada (ex.: rede Z:\\) onde ficam as imagens de fundo. "
                "Todos que apontarem para o mesmo caminho verão as mesmas imagens."
            )
            bg_folder_hint.setWordWrap(True)
            bg_folder_hint.setProperty("muted", "1")
            bg_folder_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
            lay_bg.addWidget(bg_folder_hint)

            self._bg_table = QTableWidget(0, 1)
            apply_smooth_scroll(self._bg_table)
            self._bg_table.setHorizontalHeaderLabels(["Arquivo"])
            self._bg_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            self._bg_table.verticalHeader().setVisible(False)
            self._bg_table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows
            )
            self._bg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self._bg_table.setAlternatingRowColors(True)
            self._bg_table.setMinimumHeight(max(120, int(140 * s)))
            self._bg_table.setMaximumHeight(max(200, int(220 * s)))
            self._bg_table.setStyleSheet(_table_style())
            lay_bg.addWidget(self._bg_table)

            bg_btn_row = QHBoxLayout()
            bg_btn_row.setSpacing(max(8, int(10 * s)))
            self._btn_open_bg_folder = QPushButton("Abrir Pasta")
            self._btn_open_bg_folder.setFixedHeight(max(36, int(42 * s)))
            self._btn_open_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_open_bg_folder.clicked.connect(self._open_bg_folder)
            bg_btn_row.addWidget(self._btn_open_bg_folder)
            self._btn_refresh_bg_table = QPushButton("Atualizar")
            self._btn_refresh_bg_table.setFixedHeight(max(36, int(42 * s)))
            self._btn_refresh_bg_table.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_refresh_bg_table.clicked.connect(self._on_refresh_bg_table)
            bg_btn_row.addWidget(self._btn_refresh_bg_table)
            bg_btn_row.addStretch()
            lay_bg.addLayout(bg_btn_row)

            bg_hint = QLabel(
                "Coloque as imagens diretamente na pasta acima (PNG, JPG, BMP, WEBP). "
                "Clique em 'Abrir Pasta' para acessá-la pelo Explorador de Arquivos "
                "e 'Atualizar' para recarregar a lista."
            )
            bg_hint.setWordWrap(True)
            bg_hint.setProperty("muted", "1")
            bg_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
            lay_bg.addWidget(bg_hint)

            self._refresh_bg_table()
            _add_tab("Login", _wrap(card_bg))
        else:
            self.input_bg_folder        = QLineEdit()
            self._btn_browse_bg_folder  = QPushButton()
            self._btn_verify_bg_folder  = QPushButton()
            self._lbl_bg_folder_status  = QLabel()
            self._bg_table              = QTableWidget(0, 1)
            self._btn_open_bg_folder    = QPushButton()
            self._btn_refresh_bg_table  = QPushButton()

        # ════════════════════════════════════════════════════════════════
        # ABA: Backup (admin only)
        # ════════════════════════════════════════════════════════════════
        if session.settings_show_backup:
            card_bk = _new_card()
            lay_bk = QVBoxLayout(card_bk)
            lay_bk.setContentsMargins(*_cm)
            lay_bk.setSpacing(max(8, int(10 * s)))

            lay_bk.addWidget(_section("Backup do Banco de Dados", s))
            lay_bk.addWidget(_separator())

            backup_folder_row = QHBoxLayout()
            backup_folder_row.setSpacing(max(8, int(10 * s)))
            backup_folder_row.addWidget(self._lbl("Pasta de destino:", s))
            _bfd = QLineEdit()
            _bfd.setReadOnly(True)
            _bfd.setFixedHeight(max(38, int(44 * s)))
            _bfd.setStyleSheet(_field_style(s))
            _bfd.setToolTip("O destino do backup é configurado no servidor (.env / config.py).")
            _bfd.setText(r"\\10.1.1.140\ti\REQUISIÇÕES (VENDAS)\backup_bd")
            backup_folder_row.addWidget(_bfd, 1)
            lay_bk.addLayout(backup_folder_row)

            sched_title = QLabel("Agendamento:")
            sched_title.setStyleSheet(
                f"font-size:{max(9,int(10*s))}pt; font-weight:700; padding-top:6px;"
            )
            lay_bk.addWidget(sched_title)

            sched_grid = QGridLayout()
            sched_grid.setSpacing(max(6, int(8 * s)))
            sched_grid.setColumnMinimumWidth(0, max(90, int(110 * s)))

            chk_style = _checkbox_style(s)
            spn_style = _spinbox_style(s)

            self._chk_daily = QCheckBox("Diário")
            self._chk_daily.setChecked(True)
            self._chk_daily.setStyleSheet(chk_style)
            sched_grid.addWidget(self._chk_daily, 0, 0)

            hour_row = QHBoxLayout()
            hour_row.setSpacing(max(4, int(6 * s)))
            hour_row.addWidget(self._lbl("Horário:", s))
            self._spin_daily_hour = QSpinBox()
            self._spin_daily_hour.setRange(0, 23)
            self._spin_daily_hour.setValue(2)
            self._spin_daily_hour.setSuffix("h")
            self._spin_daily_hour.setFixedHeight(max(32, int(36 * s)))
            self._spin_daily_hour.setFixedWidth(max(72, int(84 * s)))
            self._spin_daily_hour.setStyleSheet(spn_style)
            hour_row.addWidget(self._spin_daily_hour)
            hour_row.addStretch()
            sched_grid.addLayout(hour_row, 0, 1)

            ret_d_row = QHBoxLayout()
            ret_d_row.setSpacing(max(4, int(6 * s)))
            ret_d_row.addWidget(self._lbl("Retenção:", s))
            self._spin_ret_daily = QSpinBox()
            self._spin_ret_daily.setRange(1, 365)
            self._spin_ret_daily.setValue(15)
            self._spin_ret_daily.setSuffix(" arqs.")
            self._spin_ret_daily.setFixedHeight(max(32, int(36 * s)))
            self._spin_ret_daily.setFixedWidth(max(90, int(104 * s)))
            self._spin_ret_daily.setStyleSheet(spn_style)
            ret_d_row.addWidget(self._spin_ret_daily)
            ret_d_row.addStretch()
            sched_grid.addLayout(ret_d_row, 0, 2)

            self._chk_weekly = QCheckBox("Semanal")
            self._chk_weekly.setChecked(True)
            self._chk_weekly.setStyleSheet(chk_style)
            sched_grid.addWidget(self._chk_weekly, 1, 0)
            sched_grid.addWidget(self._lbl("toda segunda-feira", s, italic=True), 1, 1)

            ret_w_row = QHBoxLayout()
            ret_w_row.setSpacing(max(4, int(6 * s)))
            ret_w_row.addWidget(self._lbl("Retenção:", s))
            self._spin_ret_weekly = QSpinBox()
            self._spin_ret_weekly.setRange(1, 52)
            self._spin_ret_weekly.setValue(8)
            self._spin_ret_weekly.setSuffix(" arqs.")
            self._spin_ret_weekly.setFixedHeight(max(32, int(36 * s)))
            self._spin_ret_weekly.setFixedWidth(max(90, int(104 * s)))
            self._spin_ret_weekly.setStyleSheet(spn_style)
            ret_w_row.addWidget(self._spin_ret_weekly)
            ret_w_row.addStretch()
            sched_grid.addLayout(ret_w_row, 1, 2)

            self._chk_monthly = QCheckBox("Mensal")
            self._chk_monthly.setChecked(False)
            self._chk_monthly.setStyleSheet(chk_style)
            sched_grid.addWidget(self._chk_monthly, 2, 0)
            sched_grid.addWidget(self._lbl("dia 1 de cada mês", s, italic=True), 2, 1)

            ret_m_row = QHBoxLayout()
            ret_m_row.setSpacing(max(4, int(6 * s)))
            ret_m_row.addWidget(self._lbl("Retenção:", s))
            self._spin_ret_monthly = QSpinBox()
            self._spin_ret_monthly.setRange(1, 24)
            self._spin_ret_monthly.setValue(6)
            self._spin_ret_monthly.setSuffix(" arqs.")
            self._spin_ret_monthly.setFixedHeight(max(32, int(36 * s)))
            self._spin_ret_monthly.setFixedWidth(max(90, int(104 * s)))
            self._spin_ret_monthly.setStyleSheet(spn_style)
            ret_m_row.addWidget(self._spin_ret_monthly)
            ret_m_row.addStretch()
            sched_grid.addLayout(ret_m_row, 2, 2)

            lay_bk.addLayout(sched_grid)

            save_sched_row = QHBoxLayout()
            save_sched_row.setSpacing(max(8, int(10 * s)))
            self._btn_save_backup_settings = QPushButton("Salvar Agendamento")
            self._btn_save_backup_settings.setFixedHeight(max(36, int(42 * s)))
            self._btn_save_backup_settings.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_save_backup_settings.clicked.connect(self._on_save_backup_settings)
            save_sched_row.addWidget(self._btn_save_backup_settings)
            self._lbl_sched_status = QLabel("")
            self._lbl_sched_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
            save_sched_row.addWidget(self._lbl_sched_status)
            save_sched_row.addStretch()
            lay_bk.addLayout(save_sched_row)

            lay_bk.addWidget(_separator())

            backup_action_row = QHBoxLayout()
            backup_action_row.setSpacing(max(8, int(10 * s)))
            self._btn_run_backup = QPushButton("Fazer Backup Agora")
            self._btn_run_backup.setFixedHeight(max(38, int(44 * s)))
            self._btn_run_backup.setStyleSheet(_primary_action_btn_style(s))
            self._btn_run_backup.clicked.connect(self._on_backup_run)
            backup_action_row.addWidget(self._btn_run_backup)
            self._btn_refresh_backup_table = QPushButton("Atualizar Lista")
            self._btn_refresh_backup_table.setFixedHeight(max(38, int(44 * s)))
            self._btn_refresh_backup_table.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_refresh_backup_table.clicked.connect(self._on_refresh_backup_table)
            backup_action_row.addWidget(self._btn_refresh_backup_table)
            backup_action_row.addStretch()
            lay_bk.addLayout(backup_action_row)

            self._lbl_backup_status = QLabel("")
            self._lbl_backup_status.setWordWrap(True)
            self._lbl_backup_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
            lay_bk.addWidget(self._lbl_backup_status)

            self._backup_table = QTableWidget(0, 3)
            apply_smooth_scroll(self._backup_table)
            self._backup_table.setHorizontalHeaderLabels(
                ["Arquivo", "Tamanho", "Criado em"]
            )
            self._backup_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            self._backup_table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            self._backup_table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.ResizeToContents
            )
            self._backup_table.verticalHeader().setVisible(False)
            self._backup_table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows
            )
            self._backup_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers
            )
            self._backup_table.setAlternatingRowColors(True)
            self._backup_table.setMinimumHeight(max(120, int(140 * s)))
            self._backup_table.setMaximumHeight(max(200, int(220 * s)))
            self._backup_table.setStyleSheet(_table_style())
            lay_bk.addWidget(self._backup_table)

            backup_hint = QLabel(
                "Os backups automáticos são executados no horário configurado acima. "
                "Retenção: número máximo de arquivos mantidos por tipo — os mais antigos "
                "são excluídos automaticamente."
            )
            backup_hint.setWordWrap(True)
            backup_hint.setProperty("muted", "1")
            backup_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
            lay_bk.addWidget(backup_hint)

            self._start_api_worker("get_backup_settings")
            self._on_refresh_backup_table()
            _add_tab("Backup", _wrap(card_bk))
        else:
            self._chk_daily               = QCheckBox()
            self._chk_weekly              = QCheckBox()
            self._chk_monthly             = QCheckBox()
            self._spin_daily_hour         = QSpinBox()
            self._spin_ret_daily          = QSpinBox()
            self._spin_ret_weekly         = QSpinBox()
            self._spin_ret_monthly        = QSpinBox()
            self._btn_save_backup_settings = QPushButton()
            self._lbl_sched_status        = QLabel()
            self._btn_run_backup          = QPushButton()
            self._btn_refresh_backup_table = QPushButton()
            self._lbl_backup_status       = QLabel()
            self._backup_table            = QTableWidget(0, 3)

        # ════════════════════════════════════════════════════════════════
        # ABA: Usuários (admin only) — Central de Usuários embarcada
        # ════════════════════════════════════════════════════════════════
        self._user_center_tab_index = -1
        if session.is_admin:
            from .user_center_view import UserCenterView
            self._user_center = UserCenterView(s, embedded=True)
            self._user_center_tab_index = len(self._tab_btns)
            _add_tab("Usuários", self._user_center)
        else:
            self._user_center = None

        # ════════════════════════════════════════════════════════════════
        # ABA: Clientes (admin only) — Cadastro de clientes embarcado
        # ════════════════════════════════════════════════════════════════
        self._client_center_tab_index = -1
        if session.is_admin:
            from .client_center_view import ClientCenterView
            self._client_center = ClientCenterView(s, embedded=True)
            self._client_center.guide_requested.connect(self.show_guide_requested)
            self._client_center_tab_index = len(self._tab_btns)
            _add_tab("Clientes", self._client_center)
        else:
            self._client_center = None
        self._machine_center_tab_index = -1
        if session.is_admin:
            from .machine_center_view import MachineCenterView
            self._machine_center = MachineCenterView(s, embedded=True)
            self._machine_center_tab_index = len(self._tab_btns)
            _add_tab("Cadastro de Máquinas", self._machine_center)
        else:
            self._machine_center = None

        # ════════════════════════════════════════════════════════════════
        # ABA: Operadores (admin only)
        # ════════════════════════════════════════════════════════════════
        self._operator_center_tab_index = -1
        if session.is_admin:
            from .operator_center_view import OperatorCenterView
            self._operator_center = OperatorCenterView(s, embedded=True)
            self._operator_center.guide_requested.connect(self.show_guide_requested)
            self._operator_center_tab_index = len(self._tab_btns)
            _add_tab("Operadores", self._operator_center)
        else:
            self._operator_center = None

        # ════════════════════════════════════════════════════════════════
        # ABA: Ajuda
        # ════════════════════════════════════════════════════════════════
        card_help = _new_card()
        lay_help = QVBoxLayout(card_help)
        lay_help.setContentsMargins(*_cm)
        lay_help.setSpacing(_cs)

        lay_help.addWidget(_section("Atualizações do Sistema", s))
        lay_help.addWidget(_separator())

        update_row = QHBoxLayout()
        update_row.setSpacing(max(8, int(10 * s)))
        from ..version import CURRENT_VERSION as _CURRENT_VERSION
        self._version_label = QLabel(f"Versão atual: v{_CURRENT_VERSION}")
        self._version_label.setProperty("muted", "1")
        self._version_label.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        update_row.addWidget(self._version_label)
        update_row.addStretch()
        self.btn_check_update = QPushButton("Verificar atualizações")
        self.btn_check_update.setFixedHeight(max(38, int(44 * s)))
        self.btn_check_update.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_check_update.clicked.connect(self._check_updates)
        update_row.addWidget(self.btn_check_update)
        lay_help.addLayout(update_row)

        self._update_status_label = QLabel("")
        self._update_status_label.setProperty("muted", "1")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        lay_help.addWidget(self._update_status_label)

        lay_help.addWidget(_section("Guia Rápido", s))
        lay_help.addWidget(_separator())

        guide_row = QHBoxLayout()
        guide_row.setSpacing(max(8, int(10 * s)))
        guide_hint = QLabel("Precisa relembrar alguma funcionalidade?")
        guide_hint.setProperty("muted", "1")
        guide_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        guide_row.addWidget(guide_hint)
        guide_row.addStretch()
        self.btn_show_guide = QPushButton("📖  Ver Guia Rápido")
        self.btn_show_guide.setFixedHeight(max(38, int(44 * s)))
        self.btn_show_guide.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_show_guide.clicked.connect(self.show_guide_requested)
        guide_row.addWidget(self.btn_show_guide)
        lay_help.addLayout(guide_row)

        _add_tab("Ajuda", _wrap(card_help))

        # Fecha a barra de abas com um stretch à direita
        tab_bar_layout.addStretch()

    def _lbl(self, text: str, scale: float, color: str = None,
             italic: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("muted", "1")
        fs = max(8, int(9 * scale))
        style = f"font-size:{fs}pt;"
        if italic:
            style += " font-style:italic;"
        lbl.setStyleSheet(style)
        return lbl

    def refresh_operational_settings(self, silent: bool = False):
        if not session.settings_show_billing:
            return
        if not silent:
            self.operational_status.setText("Sincronizando prazo de alerta com o servidor...")
        self._start_api_worker("load_operational")

    def _start_api_worker(self, action: str, payload: dict | None = None):
        worker = SettingsApiWorker(action, payload)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._on_api_result)
        worker.error.connect(self._on_api_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _on_api_result(self, action: str, payload: object):
        if action == "load_operational":
            data = payload if isinstance(payload, dict) else {}
            days = int(data.get("pending_invoice_alert_days") or 1)
            self.input_pending_invoice_days.setValue(days)
            min_deliv = int(data.get("min_delivery_business_days") or 0)
            self.input_min_delivery_days.setValue(min_deliv)
            self.operational_status.setText(
                f"Prazo sincronizado com o servidor: {days} dia(s)."
            )
            res.save(pending_invoice_alert_days=days,
                     min_delivery_business_days=min_deliv)
            return

        if action == "save_operational":
            self._finish_save(True)

        if action == "trigger_backup":
            self._btn_run_backup.setEnabled(True)
            self._btn_run_backup.setText("Fazer Backup Agora")
            s = self.scale
            data = payload if isinstance(payload, dict) else {}
            if data.get("success"):
                filename = data.get("filename", "")
                size_kb  = int(data.get("size_bytes", 0)) // 1024
                self._lbl_backup_status.setText(
                    f"Backup concluído: {filename}  ({size_kb} KB)"
                )
                self._lbl_backup_status.setStyleSheet(
                    f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.SUCCESS};"
                )
                # Refresca a tabela automaticamente após backup bem-sucedido
                self._on_refresh_backup_table()
            else:
                error = data.get("error", "Erro desconhecido")
                self._lbl_backup_status.setText(f"Falha no backup: {error}")
                self._lbl_backup_status.setStyleSheet(
                    f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.DANGER};"
                )

        if action == "list_backups":
            self._btn_refresh_backup_table.setEnabled(True)
            self._btn_refresh_backup_table.setText("Atualizar Lista")
            entries = payload if isinstance(payload, list) else []
            self._populate_backup_table(entries)

        if action == "change_password":
            self._btn_change_pwd.setEnabled(True)
            self._btn_change_pwd.setText("Alterar Senha")
            self._input_pwd_current.clear()
            self._input_pwd_new.clear()
            self._input_pwd_confirm.clear()
            s = self.scale
            self._lbl_pwd_status.setText("Senha alterada com sucesso!")
            self._lbl_pwd_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.SUCCESS};"
            )

        if action == "get_backup_settings":
            data = payload if isinstance(payload, dict) else {}
            self._chk_daily.setChecked(bool(data.get("daily_enabled", True)))
            self._chk_weekly.setChecked(bool(data.get("weekly_enabled", True)))
            self._chk_monthly.setChecked(bool(data.get("monthly_enabled", False)))
            self._spin_daily_hour.setValue(int(data.get("daily_hour", 2)))
            self._spin_ret_daily.setValue(int(data.get("retention_daily", 15)))
            self._spin_ret_weekly.setValue(int(data.get("retention_weekly", 8)))
            self._spin_ret_monthly.setValue(int(data.get("retention_monthly", 6)))

        if action == "save_backup_settings":
            self._btn_save_backup_settings.setEnabled(True)
            self._btn_save_backup_settings.setText("Salvar Agendamento")
            s = self.scale
            self._lbl_sched_status.setText("Agendamento salvo!")
            self._lbl_sched_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.SUCCESS};"
            )

    def _on_api_error(self, action: str, message: str):
        if action == "load_operational":
            self.operational_status.setText(
                "Não foi possível sincronizar com o servidor. Usando valor local."
            )
            return

        if action == "save_operational":
            self._finish_save(False, message)

        if action == "trigger_backup":
            self._btn_run_backup.setEnabled(True)
            self._btn_run_backup.setText("Fazer Backup Agora")
            s = self.scale
            self._lbl_backup_status.setText(f"Erro ao executar backup: {message}")
            self._lbl_backup_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.DANGER};"
            )

        if action == "list_backups":
            self._btn_refresh_backup_table.setEnabled(True)
            self._btn_refresh_backup_table.setText("Atualizar Lista")

        if action == "change_password":
            self._btn_change_pwd.setEnabled(True)
            self._btn_change_pwd.setText("Alterar Senha")
            s = self.scale
            self._lbl_pwd_status.setText(f"Erro: {message}")
            self._lbl_pwd_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.DANGER};"
            )

        if action == "get_backup_settings":
            pass  # mantém os valores padrão já exibidos nos controles

        if action == "save_backup_settings":
            self._btn_save_backup_settings.setEnabled(True)
            self._btn_save_backup_settings.setText("Salvar Agendamento")
            s = self.scale
            self._lbl_sched_status.setText(f"Erro: {message}")
            self._lbl_sched_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.DANGER};"
            )

    def _set_save_busy(self, busy: bool):
        self.btn_save.setEnabled(not busy)
        self.btn_save.setText("SALVANDO..." if busy else "SALVAR CONFIGURAÇÕES")

    def _finish_save(self, remote_ok: bool, error_message: str = ""):
        context = self._pending_save_context or {}
        scale_changed = bool(context.get("scale_changed"))
        font_size_changed = bool(context.get("font_size_changed"))
        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        self._set_save_busy(False)

        if remote_ok:
            self.operational_status.setText(
                f"Prazo sincronizado com o servidor: {self.input_pending_invoice_days.value()} dia(s)."
            )
            QMessageBox.information(self, "Configurações", "Configurações aplicadas com sucesso.")
            if scale_changed:
                self.scale_changed.emit(res.scale)
            elif font_size_changed:
                self.font_size_changed.emit()
        else:
            self.operational_status.setText(
                "Não foi possível salvar o prazo no servidor. O valor local foi mantido."
            )
            QMessageBox.warning(
                self,
                "Atenção",
                "As configurações locais foram salvas, mas o prazo de alerta "
                f"de faturamento não foi salvo no servidor.\n\n{error_message}",
            )
            if scale_changed:
                self.scale_changed.emit(res.scale)
            elif font_size_changed:
                self.font_size_changed.emit()

        self._pending_save_context = None

    def _scale_btn_style(self, s: float) -> str:
        return (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
            f"  padding:0 {max(10, int(14*s))}px;"
            f"  font-size:{max(8, int(9*s))}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{theme.PRIMARY}; }}"
            f"QPushButton:checked {{"
            f"  background:{theme.PRIMARY}; color:#fff; border-color:{theme.PRIMARY};"
            f"}}"
        )

    def _tab_btn_style(self, s: float) -> str:
        fs  = max(9, int(10 * s))
        pad = max(8, int(10 * s))
        px  = max(16, int(20 * s))
        return (
            f"QPushButton {{"
            f"  background:transparent; color:{theme.TEXT_MEDIUM};"
            f"  border:none; border-bottom:2px solid transparent;"
            f"  padding:{pad}px {px}px; font-size:{fs}pt; font-weight:600;"
            f"  border-radius:0px;"
            f"}}"
            f"QPushButton:hover {{ color:{theme.TEXT_DARK}; }}"
            f"QPushButton:checked {{"
            f"  color:{theme.PRIMARY}; border-bottom:2px solid {theme.PRIMARY};"
            f"  font-weight:700;"
            f"}}"
        )

    def _switch_tab(self, idx: int) -> None:
        """Ativa a aba de índice idx e reseta o scroll ao topo."""
        self._tab_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setChecked(i == idx)
        self._page_scroll.verticalScrollBar().setValue(0)

        # As abas de Usuários e Clientes têm seus próprios botões de salvar; o
        # botão global "SALVAR CONFIGURAÇÕES" não se aplica a elas.
        on_users_tab = (idx == self._user_center_tab_index)
        on_clients_tab = (idx == self._client_center_tab_index)
        on_machines_tab = (idx == self._machine_center_tab_index)
        on_operators_tab = (idx == getattr(self, "_operator_center_tab_index", -1))
        self.btn_save.setVisible(not (on_users_tab or on_clients_tab or on_machines_tab or on_operators_tab))
        if on_users_tab and self._user_center is not None:
            self._user_center.refresh()
        if on_clients_tab and self._client_center is not None:
            self._client_center.refresh()
        if on_machines_tab and self._machine_center is not None:
            self._machine_center.refresh()

        on_operators_tab = (idx == self._operator_center_tab_index)
        if on_operators_tab and self._operator_center is not None:
            self._operator_center.refresh()

        # Ao abrir a aba Sistema, atualiza as métricas do Painel Técnico.
        if idx == self._system_tab_index and self._technical_panel is not None:
            self._technical_panel.refresh()

    def _on_scale_btn(self, label: str):
        for lbl, btn in self._scale_btns.items():
            btn.setChecked(lbl == label)

    def _on_font_size_btn(self, label: str):
        for lbl, btn in self._font_size_btns.items():
            btn.setChecked(lbl == label)

    def _test_connection(self):
        url = self.input_url.text().strip()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        ok = api.health_check(url)
        s = self.scale
        if ok:
            self.lbl_conn_status.setText("Servidor online e respondendo")
            self.lbl_conn_status.setStyleSheet(
                f"color:{theme.SUCCESS}; font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
        else:
            self.lbl_conn_status.setText("Não foi possível conectar ao servidor")
            self.lbl_conn_status.setStyleSheet(
                f"color:{theme.DANGER}; font-size:{max(8,int(9*s))}pt; font-weight:600;"
            )
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar conexão")

    def _save(self):
        selected_scale = next(
            (lbl for lbl, btn in self._scale_btns.items() if btn.isChecked()),
            "100%",
        )
        selected_font_size = next(
            (lbl for lbl, btn in self._font_size_btns.items() if btn.isChecked()),
            "Normal",
        )
        scale_changed     = (selected_scale != res._user_scale)
        font_size_changed = (selected_font_size != res.font_size_label)

        # Coleta kwargs comuns (aparência + pasta de bg se visível)
        save_kwargs: dict = dict(font_scale=selected_scale, font_size=selected_font_size)
        if session.settings_show_login_backgrounds:
            bg_folder_val = self.input_bg_folder.text().strip()
            if bg_folder_val:
                save_kwargs["bg_folder"] = bg_folder_val

        if session.settings_show_billing:
            # Admin / Gerente: salva aparência + prazo de faturamento no servidor
            pending_invoice_alert_days = int(self.input_pending_invoice_days.value())
            min_delivery_business_days = int(self.input_min_delivery_days.value())
            res.save(**save_kwargs,
                     pending_invoice_alert_days=pending_invoice_alert_days,
                     min_delivery_business_days=min_delivery_business_days)
            if session.settings_show_login_backgrounds:
                self._refresh_bg_table()
            self._pending_save_context = {
                "scale_changed": scale_changed,
                "font_size_changed": font_size_changed,
            }
            self._set_save_busy(True)
            self.operational_status.setText("Salvando configurações no servidor...")
            self._start_api_worker(
                "save_operational",
                {
                    "pending_invoice_alert_days": pending_invoice_alert_days,
                    "min_delivery_business_days": min_delivery_business_days,
                },
            )
        else:
            # Demais roles: salva apenas aparência localmente
            res.save(**save_kwargs)
            if session.settings_show_login_backgrounds:
                self._refresh_bg_table()
            current = local_now()
            self.date_label.setText(_format_header_date(current))
            self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
            QMessageBox.information(self, "Configurações", "Configurações aplicadas com sucesso.")
            if scale_changed:
                self.scale_changed.emit(res.scale)
            elif font_size_changed:
                self.font_size_changed.emit()

    # ── Fundo da Tela de Login ────────────────────────────────────────────────

    def _open_bg_folder(self) -> None:
        """Abre a pasta de backgrounds no Explorador de Arquivos."""
        path = self.input_bg_folder.text().strip() or res.bg_folder
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                QMessageBox.warning(
                    self, "Pasta não encontrada",
                    f"Não foi possível acessar ou criar a pasta:\n{path}",
                )
                return
        os.startfile(path)

    def _on_refresh_bg_table(self) -> None:
        """Recarrega a tabela e notifica o LoginView."""
        self._refresh_bg_table()
        self._notify_login_view_bg_changed()

    def _browse_bg_folder(self) -> None:
        """Abre seletor de pasta para o caminho de imagens de fundo."""
        current = self.input_bg_folder.text().strip()
        path = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta de Backgrounds",
            current if os.path.isdir(current) else "",
        )
        if path:
            self.input_bg_folder.setText(os.path.normpath(path))

    def _verify_bg_folder(self) -> None:
        """Verifica se a pasta de backgrounds está acessível e conta as imagens."""
        path = self.input_bg_folder.text().strip()

        if not path:
            self._set_bg_folder_status("Informe um caminho de pasta.", theme.DANGER)
            return

        if not os.path.isdir(path):
            self._set_bg_folder_status(
                f"Pasta não encontrada ou inacessível: {path}", theme.DANGER
            )
            return

        exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        try:
            images = [
                f for f in os.listdir(path)
                if os.path.splitext(f.lower())[1] in exts
            ]
        except Exception as exc:
            self._set_bg_folder_status(f"Erro ao ler a pasta: {exc}", theme.DANGER)
            return

        total = len(images)
        if total == 0:
            self._set_bg_folder_status(
                "Pasta acessível, mas nenhuma imagem encontrada ainda.",
                theme.TEXT_MEDIUM,
            )
        else:
            self._set_bg_folder_status(
                f"Pasta OK — {total} imagem(ns) encontrada(s).",
                theme.SUCCESS,
            )

    def _set_bg_folder_status(self, message: str, color: str) -> None:
        self._lbl_bg_folder_status.setText(message)
        self._lbl_bg_folder_status.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600; color:{color};"
        )

    def _refresh_bg_table(self) -> None:
        """Recarrega a tabela com as imagens encontradas na pasta."""
        images = login_backgrounds.load_all()
        self._bg_table.setRowCount(0)
        for filename in images:
            row = self._bg_table.rowCount()
            self._bg_table.insertRow(row)
            self._bg_table.setItem(row, 0, QTableWidgetItem(filename))

    def _notify_login_view_bg_changed(self) -> None:
        """Avisa o LoginView para recarregar o fundo, se acessível."""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            for widget in app.allWidgets():
                if widget.__class__.__name__ == "LoginView":
                    if hasattr(widget, "reload_background"):
                        widget.reload_background()
                    break
        except Exception:
            pass

    # ── Backup do Banco de Dados ─────────────────────────────────────────────

    # ── Alterar Senha ────────────────────────────────────────────────────────

    def _on_change_password(self) -> None:
        current = self._input_pwd_current.text()
        new     = self._input_pwd_new.text()
        confirm = self._input_pwd_confirm.text()
        s = self.scale

        def _set_status(msg: str, color: str):
            self._lbl_pwd_status.setText(msg)
            self._lbl_pwd_status.setStyleSheet(
                f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{color};"
            )

        if not current:
            _set_status("Informe a senha atual.", theme.DANGER)
            return
        if len(new) < 6:
            _set_status("A nova senha precisa ter pelo menos 6 caracteres.", theme.DANGER)
            return
        if new != confirm:
            _set_status("As senhas não coincidem.", theme.DANGER)
            return

        self._btn_change_pwd.setEnabled(False)
        self._btn_change_pwd.setText("Alterando...")
        self._lbl_pwd_status.setText("")
        self._start_api_worker("change_password", {
            "current_password": current,
            "new_password":     new,
        })

    def _on_save_backup_settings(self) -> None:
        """Envia as configurações de agendamento ao servidor."""
        self._btn_save_backup_settings.setEnabled(False)
        self._btn_save_backup_settings.setText("Salvando...")
        self._lbl_sched_status.setText("")
        payload = {
            "daily_enabled":     self._chk_daily.isChecked(),
            "weekly_enabled":    self._chk_weekly.isChecked(),
            "monthly_enabled":   self._chk_monthly.isChecked(),
            "daily_hour":        self._spin_daily_hour.value(),
            "retention_daily":   self._spin_ret_daily.value(),
            "retention_weekly":  self._spin_ret_weekly.value(),
            "retention_monthly": self._spin_ret_monthly.value(),
        }
        self._start_api_worker("save_backup_settings", payload)

    def _on_backup_run(self) -> None:
        """Dispara backup manual via API."""
        s = self.scale
        self._btn_run_backup.setEnabled(False)
        self._btn_run_backup.setText("Executando...")
        self._lbl_backup_status.setText("Aguardando o servidor concluir o backup...")
        self._lbl_backup_status.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600; color:{theme.TEXT_MEDIUM};"
        )
        self._start_api_worker("trigger_backup")

    def _on_refresh_backup_table(self) -> None:
        """Solicita a lista de backups ao servidor."""
        self._btn_refresh_backup_table.setEnabled(False)
        self._btn_refresh_backup_table.setText("Carregando...")
        self._start_api_worker("list_backups")

    def _populate_backup_table(self, entries: list[dict]) -> None:
        """Preenche a tabela com os backups retornados pela API."""
        self._backup_table.setRowCount(0)
        for entry in entries:
            row = self._backup_table.rowCount()
            self._backup_table.insertRow(row)

            self._backup_table.setItem(row, 0, QTableWidgetItem(entry.get("filename", "")))

            size_bytes = int(entry.get("size_bytes") or 0)
            if size_bytes >= 1_048_576:
                size_str = f"{size_bytes / 1_048_576:.1f} MB"
            elif size_bytes >= 1024:
                size_str = f"{size_bytes // 1024} KB"
            else:
                size_str = f"{size_bytes} B"
            self._backup_table.setItem(row, 1, QTableWidgetItem(size_str))

            raw_dt = entry.get("created_at", "")
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(raw_dt)
                dt_str = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                dt_str = raw_dt
            self._backup_table.setItem(row, 2, QTableWidgetItem(dt_str))

    def _check_updates(self) -> None:
        from ..updater import UpdateChecker

        self.btn_check_update.setEnabled(False)
        self.btn_check_update.setText("Verificando...")
        self._update_status_label.setText("")

        self._update_checker = UpdateChecker(parent=self)
        self._update_checker.update_available.connect(self._on_update_found)
        self._update_checker.no_update.connect(self._on_no_update)
        self._update_checker.error.connect(self._on_update_check_error)
        self._update_checker.start()

    def _on_update_found(self, update_info: dict) -> None:
        from ..widgets.update_dialog import UpdateAvailableDialog
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizações")
        self._update_status_label.setText(
            f"Nova versão disponível: v{update_info['version']}"
        )
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.SUCCESS};"
        )
        UpdateAvailableDialog(update_info, parent=self).exec()

    def _on_no_update(self) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizações")
        self._update_status_label.setText("Você já tem a versão mais recente.")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.SUCCESS};"
        )

    def _on_update_check_error(self, error_msg: str) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizações")
        self._update_status_label.setText(f"Erro ao verificar: {error_msg}")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.DANGER};"
        )

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#settingsView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#settingsContainer {{ background:{bg}; }}")
        self._tab_sep.setStyleSheet(
            f"QFrame {{ background:{theme.BORDER_COLOR}; border:none; }}"
        )
        tab_btn_st = self._tab_btn_style(s)
        for btn in self._tab_btns:
            btn.setStyleSheet(tab_btn_st)
        self.input_url.setStyleSheet(_field_style(s))
        if session.settings_show_billing:
            self.input_pending_invoice_days.setStyleSheet(_spinbox_style(s))
        self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
        self._input_pwd_current.setStyleSheet(_field_style(s))
        self._input_pwd_new.setStyleSheet(_field_style(s))
        self._input_pwd_confirm.setStyleSheet(_field_style(s))
        self._btn_change_pwd.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_check_update.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_show_guide.setStyleSheet(_flat_secondary_btn_style(s))
        btn_style = self._scale_btn_style(s)
        for btn in self._scale_btns.values():
            btn.setStyleSheet(btn_style)
        for btn in self._font_size_btns.values():
            btn.setStyleSheet(btn_style)
        if session.settings_show_login_backgrounds:
            self.input_bg_folder.setStyleSheet(_field_style(s))
            self._btn_browse_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_verify_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_open_bg_folder.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_refresh_bg_table.setStyleSheet(_flat_secondary_btn_style(s))
            self._bg_table.setStyleSheet(_table_style())
            self._refresh_bg_table()
        if session.settings_show_backup:
            chk_style = _checkbox_style(s)
            spn_style = _spinbox_style(s)
            self._chk_daily.setStyleSheet(chk_style)
            self._chk_weekly.setStyleSheet(chk_style)
            self._chk_monthly.setStyleSheet(chk_style)
            self._spin_daily_hour.setStyleSheet(spn_style)
            self._spin_ret_daily.setStyleSheet(spn_style)
            self._spin_ret_weekly.setStyleSheet(spn_style)
            self._spin_ret_monthly.setStyleSheet(spn_style)
            self._btn_save_backup_settings.setStyleSheet(_flat_secondary_btn_style(s))
            self._btn_run_backup.setStyleSheet(_primary_action_btn_style(s))
            self._btn_refresh_backup_table.setStyleSheet(_flat_secondary_btn_style(s))
            self._backup_table.setStyleSheet(_table_style())
        if getattr(self, "_user_center", None) is not None:
            self._user_center.apply_theme()
        if getattr(self, "_client_center", None) is not None:
            self._client_center.apply_theme()
        if getattr(self, "_machine_center", None) is not None:
            self._machine_center.apply_theme()
        if getattr(self, "_operator_center", None) is not None:
            self._operator_center.apply_theme()
        if getattr(self, "_technical_panel", None) is not None:
            self._technical_panel.apply_theme()
