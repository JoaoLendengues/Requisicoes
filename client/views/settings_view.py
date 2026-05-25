import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QMessageBox, QSpinBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QBrush, QColor

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
        self.setStyleSheet(
            f"QWidget#settingsView {{ background:{page_bg}; }}"
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                       max(18, int(24 * s)), max(18, int(24 * s)))
        root_layout.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Configurações")
        title.setStyleSheet(
            f"font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel("Preferências e configurações do sistema.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

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
        self.updated_label = QLabel("Preferências do sistema")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)
        header.addWidget(info_card, 0, Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(header)

        self._page_scroll = SmoothScrollArea(self)
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root_layout.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setObjectName("settingsContainer")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#settingsContainer {{ background:{page_bg}; }}"
        )
        self._page_scroll.setWidget(self._page_content)

        outer = QVBoxLayout(self._page_content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(max(16, int(18 * s)))

        page_title = QLabel("CONFIGURAÇÕES")
        page_title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(14,int(17*s))}pt; font-weight:bold;"
        )
        outer.addWidget(page_title)
        page_title.hide()

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
        layout.setSpacing(max(12, int(16 * s)))

        # ── Conexão com o Servidor (admin only) ──────────────────────────────
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
        self.input_url.setToolTip("A URL do servidor é fixa e não pode ser alterada nesta tela.")
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

        layout.addWidget(self._conn_section)
        self._conn_section.setVisible(session.settings_show_connection)

        # ── Aparência (todos) ─────────────────────────────────────────────────
        layout.addWidget(_section("Aparência", s))
        layout.addWidget(_separator())

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
        layout.addLayout(scale_row)

        self.screen_info = QLabel(
            f"Resolução detectada: {res.screen_width}x{res.screen_height}  |  "
            f"DPI: {res.dpi:.0f}  |  Recomendado: {res.recommended_label}"
        )
        self.screen_info.setProperty("muted", "1")
        self.screen_info.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        layout.addWidget(self.screen_info)

        # ── Tamanho de Fonte (todos) ──────────────────────────────────────────
        layout.addWidget(_section("Tamanho de Fonte", s))
        layout.addWidget(_separator())

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
        layout.addLayout(font_size_row)

        font_size_hint = QLabel(
            "Aumenta ou reduz apenas os textos, mantendo o layout da interface."
        )
        font_size_hint.setProperty("muted", "1")
        font_size_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        layout.addWidget(font_size_hint)

        # ── Alertas de Faturamento (admin + gerente) ──────────────────────────
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

        self.operational_status = QLabel("Sincronizando prazo de alerta com o servidor...")
        self.operational_status.setProperty("muted", "1")
        self.operational_status.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        billing_vl.addWidget(self.operational_status)

        layout.addWidget(self._billing_section)
        self._billing_section.setVisible(session.settings_show_billing)

        # ── Fundo da Tela de Login (admin only) ──────────────────────────────
        self._login_bg_section = QWidget()
        bg_vl = QVBoxLayout(self._login_bg_section)
        bg_vl.setContentsMargins(0, 0, 0, 0)
        bg_vl.setSpacing(max(8, int(10 * s)))

        bg_vl.addWidget(_section("Fundo da Tela de Login", s))
        bg_vl.addWidget(_separator())

        # ── Pasta de backgrounds ─────────────────────────────────────────────
        bg_folder_row = QHBoxLayout()
        bg_folder_row.setSpacing(max(8, int(10 * s)))
        bg_folder_row.addWidget(self._lbl("Pasta de imagens:", s))
        self.input_bg_folder = QLineEdit(res.bg_folder)
        self.input_bg_folder.setFixedHeight(max(38, int(44 * s)))
        self.input_bg_folder.setStyleSheet(_field_style(s))
        self.input_bg_folder.setPlaceholderText(r"Z:\REQUISIÇÕES (VENDAS)\login_backgrounds")
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
        bg_vl.addLayout(bg_folder_row)

        self._lbl_bg_folder_status = QLabel("")
        self._lbl_bg_folder_status.setWordWrap(True)
        self._lbl_bg_folder_status.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        bg_vl.addWidget(self._lbl_bg_folder_status)

        bg_folder_hint = QLabel(
            "Pasta compartilhada (ex.: rede Z:\\) onde ficam as imagens e o config.json. "
            "Todos que apontarem para o mesmo caminho verão as mesmas campanhas."
        )
        bg_folder_hint.setWordWrap(True)
        bg_folder_hint.setProperty("muted", "1")
        bg_folder_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        bg_vl.addWidget(bg_folder_hint)

        # Tabela de campanhas
        self._bg_table = QTableWidget(0, 3)
        apply_smooth_scroll(self._bg_table)
        self._bg_table.setHorizontalHeaderLabels(["Nome", "Período", "Status"])
        self._bg_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._bg_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bg_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._bg_table.verticalHeader().setVisible(False)
        self._bg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._bg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._bg_table.setAlternatingRowColors(True)
        self._bg_table.setMinimumHeight(max(120, int(140 * s)))
        self._bg_table.setMaximumHeight(max(200, int(220 * s)))
        self._bg_table.setStyleSheet(_table_style())
        bg_vl.addWidget(self._bg_table)

        # Linha de botões
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

        bg_vl.addLayout(bg_btn_row)

        bg_hint = QLabel(
            "Coloque as imagens e o config.json na pasta acima. "
            "Clique em 'Abrir Pasta' para gerenciá-la pelo Explorador de Arquivos, "
            "e 'Atualizar' para recarregar a lista."
        )
        bg_hint.setWordWrap(True)
        bg_hint.setProperty("muted", "1")
        bg_hint.setStyleSheet(f"font-size:{max(8,int(9*s))}pt; font-weight:600;")
        bg_vl.addWidget(bg_hint)

        layout.addWidget(self._login_bg_section)
        self._login_bg_section.setVisible(session.settings_show_login_backgrounds)
        if session.settings_show_login_backgrounds:
            self._refresh_bg_table()

        # ── Atualizações do Sistema (todos) ───────────────────────────────────
        layout.addWidget(_section("Atualizações do Sistema", s))
        layout.addWidget(_separator())

        update_row = QHBoxLayout()
        update_row.setSpacing(max(8, int(10 * s)))

        from ..version import CURRENT_VERSION as _CURRENT_VERSION
        self._version_label = QLabel(f"Versão atual: v{_CURRENT_VERSION}")
        self._version_label.setProperty("muted", "1")
        self._version_label.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        update_row.addWidget(self._version_label)
        update_row.addStretch()

        self.btn_check_update = QPushButton("Verificar atualizações")
        self.btn_check_update.setFixedHeight(max(38, int(44 * s)))
        self.btn_check_update.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_check_update.clicked.connect(self._check_updates)
        update_row.addWidget(self.btn_check_update)

        layout.addLayout(update_row)

        self._update_status_label = QLabel("")
        self._update_status_label.setProperty("muted", "1")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        layout.addWidget(self._update_status_label)

        # ── Botão Salvar ──────────────────────────────────────────────────────
        layout.addSpacing(4)
        self.btn_save = QPushButton("SALVAR CONFIGURAÇÕES")
        self.btn_save.setFixedHeight(max(38, int(44 * s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save)
        layout.addWidget(self.btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(card)
        outer.addStretch()

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
            self.operational_status.setText(
                f"Prazo sincronizado com o servidor: {days} dia(s)."
            )
            res.save(pending_invoice_alert_days=days)
            return

        if action == "save_operational":
            self._finish_save(True)

    def _on_api_error(self, action: str, message: str):
        if action == "load_operational":
            self.operational_status.setText(
                "Não foi possível sincronizar com o servidor. Usando valor local."
            )
            return

        if action == "save_operational":
            self._finish_save(False, message)

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
            res.save(**save_kwargs, pending_invoice_alert_days=pending_invoice_alert_days)
            if session.settings_show_login_backgrounds:
                self._refresh_bg_table()
            self._pending_save_context = {
                "scale_changed": scale_changed,
                "font_size_changed": font_size_changed,
            }
            self._set_save_busy(True)
            self.operational_status.setText("Salvando prazo de alerta no servidor...")
            self._start_api_worker(
                "save_operational",
                {"pending_invoice_alert_days": pending_invoice_alert_days},
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
        """Verifica se a pasta de backgrounds está acessível e mostra quantas campanhas há."""
        path = self.input_bg_folder.text().strip()
        s = self.scale

        if not path:
            self._set_bg_folder_status("Informe um caminho de pasta.", theme.DANGER)
            return

        if not os.path.isdir(path):
            self._set_bg_folder_status(
                f"Pasta não encontrada ou inacessível: {path}", theme.DANGER
            )
            return

        config_path = os.path.join(path, "config.json")
        if not os.path.isfile(config_path):
            self._set_bg_folder_status(
                f"Pasta acessível, mas ainda sem campanhas (config.json não encontrado em {path}).",
                theme.TEXT_MEDIUM,
            )
            return

        # Lê diretamente do path informado (sem depender do valor salvo em settings)
        import json as _json
        try:
            with open(config_path, encoding="utf-8") as f:
                data = _json.load(f)
            campaigns = data if isinstance(data, list) else []
        except Exception as exc:
            self._set_bg_folder_status(f"Erro ao ler config.json: {exc}", theme.DANGER)
            return

        total = len(campaigns)
        today = __import__("datetime").date.today().isoformat()
        active = sum(
            1 for c in campaigns
            if c.get("start", "") <= today <= c.get("end", "")
        )
        self._set_bg_folder_status(
            f"Pasta OK — {total} campanha(s) cadastrada(s), {active} ativa(s) hoje.",
            theme.SUCCESS,
        )

    def _set_bg_folder_status(self, message: str, color: str) -> None:
        self._lbl_bg_folder_status.setText(message)
        self._lbl_bg_folder_status.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600; color:{color};"
        )

    def _refresh_bg_table(self) -> None:
        """Recarrega a tabela de campanhas a partir do config.json."""
        campaigns = login_backgrounds.load_all()
        self._bg_table.setRowCount(0)
        _STATUS_COLORS = {
            "Ativa":       theme.SUCCESS,
            "Programada":  theme.PRIMARY_LIGHT,
            "Expirada":    theme.TEXT_LIGHT,
        }
        for camp in campaigns:
            row = self._bg_table.rowCount()
            self._bg_table.insertRow(row)

            name_item = QTableWidgetItem(camp.get("name", ""))
            name_item.setData(Qt.ItemDataRole.UserRole, camp.get("id", 0))
            self._bg_table.setItem(row, 0, name_item)

            start = camp.get("start", "")
            end   = camp.get("end",   "")
            period = f"{login_backgrounds.fmt_date(start)} – {login_backgrounds.fmt_date(end)}"
            self._bg_table.setItem(row, 1, QTableWidgetItem(period))

            status = login_backgrounds.campaign_status(start, end)
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QBrush(QColor(_STATUS_COLORS.get(status, theme.TEXT_DARK))))
            self._bg_table.setItem(row, 2, status_item)

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
        self.input_url.setStyleSheet(_field_style(s))
        if session.settings_show_billing:
            self.input_pending_invoice_days.setStyleSheet(_spinbox_style(s))
        self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_check_update.setStyleSheet(_flat_secondary_btn_style(s))
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
