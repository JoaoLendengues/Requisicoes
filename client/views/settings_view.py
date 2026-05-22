import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QMessageBox, QProgressBar, QTextEdit,
    QFileDialog, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor

from ..core import theme
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)
from ..core.resolution import res, SCALE_STEPS
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


class ImportWorker(QObject):
    progress = Signal(str, int, int, str)
    finished = Signal(str, object)
    error = Signal(str, str)

    def __init__(self, kind: str, path: str):
        super().__init__()
        self.kind = kind
        self.path = path

    def run(self):
        try:
            if self.kind == "clients":
                from ..services.client_importer import import_clients as import_fn
            elif self.kind == "products":
                from ..services.product_importer import import_products as import_fn
            else:
                raise ValueError(f"Tipo de importação inválido: {self.kind}")

            result = import_fn(
                self.path,
                on_progress=lambda current, total, msg: self.progress.emit(
                    self.kind, current, total, msg
                ),
            )
            self.finished.emit(self.kind, result)
        except Exception as exc:
            self.error.emit(self.kind, str(exc))


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
                raise ValueError(f"Ação inválida: {self.action}")
            self.result.emit(self.action, result)
        except api.APIError as exc:
            self.error.emit(self.action, exc.detail)
        except Exception as exc:
            self.error.emit(self.action, str(exc))
        finally:
            self.finished.emit()


class SettingsView(QWidget):
    scale_changed = Signal(float)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._import_threads: dict[str, tuple[QThread, ImportWorker]] = {}
        self._threads: list[tuple[QThread, QObject]] = []
        self._import_ui: dict[str, dict] = {}
        self._pending_save_context: dict | None = None
        self._setup_ui()
        self._apply_permissions()
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
        subtitle = QLabel(
            "Preferências locais, conexão com o servidor e rotinas de importação do sistema."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"font-size:{max(8, int(10 * s))}pt;"
        )
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

        self._page_scroll = QScrollArea(self)
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
        outer.setSpacing(max(16,int(18*s)))

        title = QLabel("⚙️ CONFIGURAÇÕES")
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(14,int(17*s))}pt; font-weight:bold;"
        )
        outer.addWidget(title)

        title.hide()

        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16,int(20*s)), max(14,int(18*s)),
                                   max(16,int(20*s)), max(14,int(18*s)))
        layout.setSpacing(max(12,int(16*s)))

        layout.addWidget(_section("🌐 Conexão com o Servidor", s))
        layout.addWidget(_separator())

        grid = QGridLayout()
        grid.setSpacing(max(8,int(10*s)))

        grid.addWidget(self._lbl("URL do servidor:", s), 0, 0)
        self.input_url = QLineEdit(res.server_url)
        self.input_url.setFixedHeight(max(38,int(44*s)))
        self.input_url.setStyleSheet(_field_style(s))
        self.input_url.setPlaceholderText("http://192.168.1.100:5000")
        self.input_url.setReadOnly(True)
        self.input_url.setToolTip("A URL do servidor é fixa e não pode ser alterada nesta tela.")
        grid.addWidget(self.input_url, 0, 1)

        self.btn_test = QPushButton("Testar conexão")
        self.btn_test.setFixedHeight(max(38,int(44*s)))
        self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_test.clicked.connect(self._test_connection)
        grid.addWidget(self.btn_test, 0, 2)

        self.lbl_conn_status = QLabel("")
        self.lbl_conn_status.setProperty("muted", "1")
        self.lbl_conn_status.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        grid.addWidget(self.lbl_conn_status, 1, 1, 1, 2)
        layout.addLayout(grid)

        layout.addWidget(_section("🎨 Aparência", s))
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
            btn.setStyleSheet(
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
            btn.clicked.connect(lambda checked=False, lbl=label: self._on_scale_btn(lbl))
            scale_row.addWidget(btn)
            self._scale_btns[label] = btn

        scale_row.addStretch()
        layout.addLayout(scale_row)

        self.screen_info = QLabel(
            f"Resolução detectada: {res.screen_width}×{res.screen_height}  |  "
            f"DPI: {res.dpi:.0f}  |  Recomendado: {res.recommended_label}"
        )
        self.screen_info.setProperty("muted", "1")
        self.screen_info.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        layout.addWidget(self.screen_info)

        layout.addWidget(_section("Alertas de Faturamento", s))
        layout.addWidget(_separator())

        billing_grid = QGridLayout()
        billing_grid.setSpacing(max(8, int(10 * s)))

        billing_grid.addWidget(self._lbl("Dias para notificar gerente:", s), 0, 0)
        self.input_pending_invoice_days = QSpinBox()
        self.input_pending_invoice_days.setRange(1, 3650)
        self.input_pending_invoice_days.setValue(
            int(res._read_file().get("pending_invoice_alert_days", 1) or 1)
        )
        self.input_pending_invoice_days.setFixedHeight(max(38, int(44 * s)))
        self.input_pending_invoice_days.setStyleSheet(_field_style(s))
        billing_grid.addWidget(self.input_pending_invoice_days, 0, 1)

        self.operational_status = QLabel("Sincronizando prazo de alerta com o servidor...")
        self.operational_status.setProperty("muted", "1")
        self.operational_status.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        billing_grid.addWidget(self.operational_status, 1, 1, 1, 2)
        layout.addLayout(billing_grid)

        self._create_import_section(
            layout=layout,
            kind="clients",
            title="📥 Importação de Clientes (ODS/Excel)",
            description=(
                "Planilha com colunas: Código, Nome, CPF/CNPJ "
                "(novos clientes são criados; existentes são atualizados)."
            ),
            default_path=res._read_file().get(
                "ods_path", r"Z:\REQUISIÇÕES (VENDAS)\relacao_cadastros.ods"
            ),
            button_text="Importar Clientes",
        )

        self._create_import_section(
            layout=layout,
            kind="products",
            title="📦 Importação de Produtos (ODS/Excel)",
            description=(
                "Planilha com colunas como Código e Nome/Descrição. "
                "Os produtos são importados em lote e ficam disponíveis para lookup na requisição."
            ),
            default_path=self._default_products_path(),
            button_text="Importar Produtos",
        )

        layout.addWidget(_section("Atualizacoes do Sistema", s))
        layout.addWidget(_separator())

        update_row = QHBoxLayout()
        update_row.setSpacing(max(8, int(10 * s)))

        from ..version import CURRENT_VERSION as _CURRENT_VERSION
        self._version_label = QLabel(f"Versao atual: v{_CURRENT_VERSION}")
        self._version_label.setProperty("muted", "1")
        self._version_label.setStyleSheet(
            f"font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        update_row.addWidget(self._version_label)
        update_row.addStretch()

        self.btn_check_update = QPushButton("Verificar atualizacoes")
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

        layout.addSpacing(4)
        self.btn_save = QPushButton("SALVAR CONFIGURACOES")
        self.btn_save.setFixedHeight(max(38,int(44*s)))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        self.btn_save.clicked.connect(self._save)
        layout.addWidget(self.btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(card)
        outer.addStretch()

    def _create_import_section(self, layout: QVBoxLayout, kind: str, title: str,
                               description: str, default_path: str, button_text: str):
        s = self.scale
        layout.addWidget(_section(title, s))
        layout.addWidget(_separator())
        layout.addWidget(self._lbl(description, s, color=theme.TEXT_MEDIUM, italic=False))

        path_row = QHBoxLayout()
        path_row.addWidget(self._lbl("Arquivo:", s))

        input_path = QLineEdit(default_path)
        input_path.setFixedHeight(max(38,int(44*s)))
        input_path.setStyleSheet(_field_style(s))
        path_row.addWidget(input_path, 1)

        btn_browse = QPushButton("...")
        btn_browse.setFixedSize(max(38,int(44*s)), max(38,int(44*s)))
        btn_browse.setStyleSheet(_flat_secondary_btn_style(s))
        btn_browse.setToolTip("Navegar...")
        btn_browse.clicked.connect(lambda: self._browse_import_path(kind))
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        import_row = QHBoxLayout()
        btn_import = QPushButton(button_text)
        btn_import.setFixedHeight(max(38,int(44*s)))
        btn_import.setStyleSheet(_primary_action_btn_style(s))
        btn_import.clicked.connect(lambda: self._start_import(kind))
        import_row.addWidget(btn_import)

        progress_bar = QProgressBar()
        progress_bar.setFixedHeight(max(18,int(22*s)))
        progress_bar.setVisible(False)
        progress_bar.setStyleSheet(
            f"QProgressBar {{ border:none; border-radius:4px;"
            f"background:{theme.TABLE_ALT_ROW}; text-align:center; font-size:{max(8,int(9*s))}pt; }}"
            f"QProgressBar::chunk {{ background:{theme.PRIMARY}; border-radius:3px; }}"
        )
        import_row.addWidget(progress_bar, 1)
        layout.addLayout(import_row)

        txt_log = QTextEdit()
        txt_log.setReadOnly(True)
        txt_log.setMaximumHeight(max(100,int(120*s)))
        txt_log.setVisible(False)
        txt_log.setStyleSheet(
            f"background:{theme.TABLE_ALT_ROW}; border:none; border-radius:12px;"
            f"font-size:{max(9,int(10*s))}pt; color:{theme.TEXT_DARK}; padding:6px;"
        )
        layout.addWidget(txt_log)

        self._import_ui[kind] = {
            "input": input_path,
            "button": btn_import,
            "browse": btn_browse,
            "button_text": button_text,
            "progress": progress_bar,
            "log": txt_log,
        }

        if kind == "clients":
            self.input_ods_path = input_path
        elif kind == "products":
            self.input_products_path = input_path

    def _apply_permissions(self):
        self.input_url.setReadOnly(True)
        self.input_url.setToolTip("A URL do servidor é fixa e não pode ser alterada nesta tela.")

        if session.is_admin:
            return

        admin_only_message = "Somente administradores podem alterar esta configuração."
        self.input_pending_invoice_days.setEnabled(False)
        self.input_pending_invoice_days.setToolTip(admin_only_message)

        for kind in ("clients", "products"):
            ui = self._import_ui.get(kind)
            if not ui:
                continue
            ui["input"].setReadOnly(True)
            ui["input"].setToolTip(admin_only_message)
            ui["button"].setEnabled(False)
            ui["button"].setToolTip(admin_only_message)
            ui["browse"].setEnabled(False)
            ui["browse"].setToolTip(admin_only_message)

    def _default_products_path(self) -> str:
        settings_data = res._read_file()
        saved_products_path = settings_data.get("products_path")
        if saved_products_path:
            return saved_products_path

        clients_path = settings_data.get("ods_path", "")
        if clients_path:
            return os.path.join(os.path.dirname(clients_path), "produtos.ods")

        return r"Z:\REQUISIÇÕES (VENDAS)\produtos.ods"

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
                "Nao foi possivel sincronizar com o servidor. Usando valor local."
            )
            return

        if action == "save_operational":
            self._finish_save(False, message)

    def _set_save_busy(self, busy: bool):
        self.btn_save.setEnabled(not busy)
        self.btn_save.setText("SALVANDO..." if busy else "SALVAR CONFIGURACOES")

    def _finish_save(self, remote_ok: bool, error_message: str = ""):
        context = self._pending_save_context or {}
        scale_changed = bool(context.get("scale_changed"))
        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        self._set_save_busy(False)

        if remote_ok:
            self.operational_status.setText(
                f"Prazo sincronizado com o servidor: {self.input_pending_invoice_days.value()} dia(s)."
            )
            if scale_changed:
                QMessageBox.information(
                    self,
                    "Salvo",
                    "Configuracoes salvas.\nA interface sera recarregada com a nova escala.",
                )
                self.scale_changed.emit(res.scale)
            else:
                QMessageBox.information(self, "Salvo", "Configuracoes salvas.")
        else:
            self.operational_status.setText(
                "Nao foi possivel salvar o prazo no servidor. O valor local foi mantido."
            )
            message = (
                "As configuracoes locais foram salvas, mas o prazo de alerta "
                "de faturamento nao foi salvo no servidor.\n\n"
                f"{error_message}"
            )
            QMessageBox.warning(self, "Atencao", message)
            if scale_changed:
                self.scale_changed.emit(res.scale)

        self._pending_save_context = None

    def _on_scale_btn(self, label: str):
        for lbl, btn in self._scale_btns.items():
            btn.setChecked(lbl == label)

    def _test_connection(self):
        url = self.input_url.text().strip()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        ok = api.health_check(url)
        s = self.scale
        if ok:
            self.lbl_conn_status.setText("Servidor online e respondendo")
            self.lbl_conn_status.setStyleSheet(f"color:{theme.SUCCESS}; font-size:{max(8,int(9*s))}pt; font-weight:600;")
        else:
            self.lbl_conn_status.setText("Não foi possível conectar ao servidor")
            self.lbl_conn_status.setStyleSheet(f"color:{theme.DANGER}; font-size:{max(8,int(9*s))}pt; font-weight:600;")
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar conexão")

    def _save(self):
        url = self.input_url.text().strip()
        clients_path = self.input_ods_path.text().strip()
        products_path = self.input_products_path.text().strip()
        pending_invoice_alert_days = int(self.input_pending_invoice_days.value())

        selected_label = next(
            (lbl for lbl, btn in self._scale_btns.items() if btn.isChecked()),
            "100%",
        )
        font_scale_value = selected_label

        scale_changed = (font_scale_value != res._user_scale)

        res.save(
            server_url=url,
            font_scale=font_scale_value,
            ods_path=clients_path,
            products_path=products_path,
            pending_invoice_alert_days=pending_invoice_alert_days,
        )
        self._pending_save_context = {"scale_changed": scale_changed}
        self._set_save_busy(True)
        self.operational_status.setText("Salvando prazo de alerta no servidor...")
        self._start_api_worker(
            "save_operational",
            {"pending_invoice_alert_days": pending_invoice_alert_days},
        )
        return

        if scale_changed:
            QMessageBox.information(
                self,
                "Salvo",
                "Configurações salvas.\nA interface será recarregada com a nova escala.",
            )
            self.scale_changed.emit(res.scale)
        else:
            current = local_now()
            self.date_label.setText(_format_header_date(current))
            self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
            QMessageBox.information(self, "Salvo", "Configurações salvas.")

    def _browse_import_path(self, kind: str):
        if not session.is_admin:
            QMessageBox.warning(self, "Acesso negado", "Somente administradores podem alterar este caminho.")
            return
        title = (
            "Selecionar planilha de clientes"
            if kind == "clients"
            else "Selecionar planilha de produtos"
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            "Planilhas (*.ods *.xlsx *.xlsm *.xls)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            self._import_ui[kind]["input"].setText(path)

    def _start_import(self, kind: str):
        if not session.is_admin:
            QMessageBox.warning(self, "Acesso negado", "Somente administradores podem executar esta importação.")
            return
        path = self._import_ui[kind]["input"].text().strip()
        if not path:
            QMessageBox.warning(self, "Atenção", "Informe o caminho do arquivo.")
            return

        current = self._import_threads.get(kind)
        if current and current[0].isRunning():
            QMessageBox.information(
                self,
                "Importação em andamento",
                "Essa importação ainda está em execução. Aguarde a conclusão.",
            )
            return

        self._set_import_busy(kind, True)

        worker = ImportWorker(kind, path)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        worker.finished.connect(lambda *_: thread.quit())
        worker.error.connect(lambda *_: thread.quit())
        self._import_threads[kind] = (thread, worker)
        worker.finished.connect(lambda *_: worker.deleteLater())
        worker.error.connect(lambda *_: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda k=kind, t=thread, w=worker: self._cleanup_import_thread(k, t, w)
        )
        thread.start()

    def _set_import_busy(self, kind: str, busy: bool):
        ui = self._import_ui[kind]
        ui["button"].setEnabled(not busy)
        ui["button"].setText("Importando..." if busy else ui["button_text"])
        ui["progress"].setVisible(True if busy else ui["progress"].isVisible())
        if busy:
            ui["progress"].setMaximum(3)
            ui["progress"].setValue(0)
            ui["progress"].setFormat("")
            ui["log"].setVisible(False)

    def _on_progress(self, kind: str, current: int, total: int, msg: str):
        ui = self._import_ui[kind]
        ui["progress"].setVisible(True)
        ui["progress"].setMaximum(total if total > 0 else 3)
        ui["progress"].setValue(current)
        ui["progress"].setFormat(msg)

    def _on_import_done(self, kind: str, result):
        ui = self._import_ui[kind]
        ui["button"].setEnabled(True)
        ui["button"].setText(ui["button_text"])
        ui["progress"].setVisible(True)
        ui["progress"].setValue(ui["progress"].maximum())
        ui["log"].setVisible(True)
        ui["log"].setPlainText(result.summary())

    def _on_import_error(self, kind: str, msg: str):
        ui = self._import_ui[kind]
        ui["button"].setEnabled(True)
        ui["button"].setText(ui["button_text"])
        ui["progress"].setVisible(False)
        ui["log"].setVisible(True)
        ui["log"].setPlainText(f"Erro:\n{msg}")

    def _check_updates(self) -> None:
        from ..updater import UpdateChecker
        from ..widgets.update_dialog import UpdateAvailableDialog

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
        self.btn_check_update.setText("Verificar atualizacoes")
        self._update_status_label.setText(
            f"Nova versao disponivel: v{update_info['version']}"
        )
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.SUCCESS};"
        )
        UpdateAvailableDialog(update_info, parent=self).exec()

    def _on_no_update(self) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizacoes")
        self._update_status_label.setText("Voce ja tem a versao mais recente.")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.SUCCESS};"
        )

    def _on_update_check_error(self, error_msg: str) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizacoes")
        self._update_status_label.setText(f"Erro ao verificar: {error_msg}")
        self._update_status_label.setStyleSheet(
            f"font-size:{max(8,int(9*self.scale))}pt; font-weight:600;"
            f"color:{theme.DANGER};"
        )

    def _cleanup_import_thread(self, kind: str, thread: QThread, worker: ImportWorker):
        current = self._import_threads.get(kind)
        if current == (thread, worker):
            self._import_threads.pop(kind, None)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#settingsView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#settingsContainer {{ background:{bg}; }}")
        self.input_url.setStyleSheet(_field_style(s))
        self.input_pending_invoice_days.setStyleSheet(_field_style(s))
        self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_save.setStyleSheet(_primary_action_btn_style(s))
        for btn in self._scale_btns.values():
            checked = btn.isChecked()
            btn.setStyleSheet(
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
        for ui in self._import_ui.values():
            ui["input"].setStyleSheet(_field_style(s))
            ui["button"].setStyleSheet(_primary_action_btn_style(s))
            ui["browse"].setStyleSheet(_flat_secondary_btn_style(s))
            ui["progress"].setStyleSheet(
                f"QProgressBar {{ border:none; border-radius:4px;"
                f"background:{theme.TABLE_ALT_ROW}; text-align:center; font-size:{max(8,int(9*s))}pt; }}"
                f"QProgressBar::chunk {{ background:{theme.PRIMARY}; border-radius:3px; }}"
            )
            ui["log"].setStyleSheet(
                f"background:{theme.TABLE_ALT_ROW}; border:none; border-radius:12px;"
                f"font-size:{max(9,int(10*s))}pt; color:{theme.TEXT_DARK}; padding:6px;"
            )
