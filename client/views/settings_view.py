import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QSlider, QFrame, QGraphicsDropShadowEffect,
    QMessageBox, QProgressBar, QTextEdit,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor

from ..core import theme
from ..core.resolution import res
from ..api import client as api


DASH_BG = "#F4F7FB"
DASH_SURFACE = "#FFFFFF"
DASH_PRIMARY = "#1E3A5F"
DASH_SECONDARY = "#27496D"
DASH_SUCCESS = "#16A34A"
DASH_DANGER = "#DC2626"
DASH_TEXT = "#0F172A"
DASH_MUTED = "#64748B"
DASH_BORDER = "#E2E8F0"
DASH_ROW_ALT = "#F8FBFF"


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


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
    card.setObjectName("settingsCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    bg = background or DASH_SURFACE
    border = f"1px solid {border_color}" if border_color else "none"
    hover = hover_background or bg
    card.setStyleSheet(
        f"QFrame#settingsCard {{"
        f"  background:{bg}; border:{border}; border-radius:{radius}px;"
        f"}}"
        f"QFrame#settingsCard:hover {{"
        f"  background:{hover}; border:{border};"
        f"}}"
    )
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _section(title: str, scale: float) -> QLabel:
    cleaned = title.lstrip("ðŸâš™ï¸🌐🎨📥📦 ").strip()
    lbl = QLabel(cleaned)
    lbl.setStyleSheet(
        f"color:{DASH_TEXT}; font-size:{max(10,int(12*scale))}pt;"
        f"font-weight:800; padding-top:4px;"
    )
    return lbl


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedHeight(4)
    sep.setStyleSheet(f"background:{DASH_BORDER}; border:none; border-radius:2px;")
    return sep


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


def _field_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QLineEdit, QTextEdit {{"
        f"  background:{DASH_SURFACE}; border:1px solid {DASH_BORDER}; border-radius:14px;"
        f"  padding:9px 12px; font-size:{fs}pt; color:{DASH_TEXT};"
        f"  selection-background-color:{_rgba(DASH_PRIMARY, 24)}; selection-color:{DASH_TEXT};"
        f"}}"
        f"QLineEdit {{ placeholder-text-color:{DASH_MUTED}; }}"
    )


def _format_header_date(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y")


def _format_datetime(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%d/%m/%Y %H:%M")


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


class SettingsView(QWidget):
    scale_changed = Signal(float)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._import_threads: dict[str, tuple[QThread, ImportWorker]] = {}
        self._import_ui: dict[str, dict] = {}
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = DASH_BG
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
            f"color:{DASH_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Preferencias locais, conexao com o servidor e rotinas de importacao do sistema."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

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
        self.updated_label = QLabel("Preferencias do sistema")
        self.updated_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)
        header.addWidget(info_card, 0, Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root_layout.addWidget(scroll)

        container = QWidget()
        container.setObjectName("settingsContainer")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(
            f"QWidget#settingsContainer {{ background:{page_bg}; }}"
        )
        scroll.setWidget(container)

        outer = QVBoxLayout(container)
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
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
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
        grid.addWidget(self.input_url, 0, 1)

        self.btn_test = QPushButton("Testar conexão")
        self.btn_test.setFixedHeight(max(38,int(44*s)))
        self.btn_test.setStyleSheet(_flat_secondary_btn_style(s))
        self.btn_test.clicked.connect(self._test_connection)
        grid.addWidget(self.btn_test, 0, 2)

        self.lbl_conn_status = QLabel("")
        self.lbl_conn_status.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        grid.addWidget(self.lbl_conn_status, 1, 1, 1, 2)
        layout.addLayout(grid)

        layout.addWidget(_section("🎨 Aparência", s))
        layout.addWidget(_separator())

        scale_row = QHBoxLayout()
        scale_row.addWidget(self._lbl("Escala da interface:", s))

        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(70, 150)
        self.slider_scale.setValue(int(res.scale * 100))
        self.slider_scale.setTickInterval(10)
        self.slider_scale.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_scale.setFixedWidth(max(180,int(220*s)))
        self.slider_scale.valueChanged.connect(self._on_scale_change)

        self.lbl_scale_val = QLabel(f"{int(res.scale * 100)}%")
        self.lbl_scale_val.setFixedWidth(40)
        self.lbl_scale_val.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-weight:800; font-size:{max(10,int(12*s))}pt;"
        )
        scale_row.addWidget(self.slider_scale)
        scale_row.addWidget(self.lbl_scale_val)
        scale_row.addStretch()
        layout.addLayout(scale_row)

        screen_info = QLabel(
            f"Resolução detectada: {res.screen_width}×{res.screen_height}  |  "
            f"DPI: {res.dpi:.0f}  |  Escala automática: {res.auto_scale:.2f}×"
        )
        screen_info.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8,int(9*s))}pt; font-weight:600;"
        )
        layout.addWidget(screen_info)

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

        layout.addSpacing(4)
        btn_save = QPushButton("💾 Salvar configurações")
        btn_save.setText("SALVAR CONFIGURACOES")
        btn_save.setFixedHeight(max(38,int(44*s)))
        btn_save.setStyleSheet(_primary_action_btn_style(s))
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(card)
        outer.addStretch()

    def _create_import_section(self, layout: QVBoxLayout, kind: str, title: str,
                               description: str, default_path: str, button_text: str):
        s = self.scale
        layout.addWidget(_section(title, s))
        layout.addWidget(_separator())
        layout.addWidget(self._lbl(description, s, color=DASH_MUTED, italic=False))

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
            f"background:{DASH_ROW_ALT}; text-align:center; font-size:{max(8,int(9*s))}pt; }}"
            f"QProgressBar::chunk {{ background:{DASH_PRIMARY}; border-radius:3px; }}"
        )
        import_row.addWidget(progress_bar, 1)
        layout.addLayout(import_row)

        txt_log = QTextEdit()
        txt_log.setReadOnly(True)
        txt_log.setMaximumHeight(max(100,int(120*s)))
        txt_log.setVisible(False)
        txt_log.setStyleSheet(
            f"background:{DASH_ROW_ALT}; border:none; border-radius:12px;"
            f"font-size:{max(9,int(10*s))}pt; color:{DASH_TEXT}; padding:6px;"
        )
        layout.addWidget(txt_log)

        self._import_ui[kind] = {
            "input": input_path,
            "button": btn_import,
            "button_text": button_text,
            "progress": progress_bar,
            "log": txt_log,
        }

        if kind == "clients":
            self.input_ods_path = input_path
        elif kind == "products":
            self.input_products_path = input_path

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
        c = color or DASH_MUTED
        fs = max(8, int(9 * scale))
        style = f"color:{c}; font-size:{fs}pt;"
        if italic:
            style += " font-style:italic;"
        lbl.setStyleSheet(style)
        return lbl

    def _on_scale_change(self, value: int):
        self.lbl_scale_val.setText(f"{value}%")

    def _test_connection(self):
        url = self.input_url.text().strip()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        ok = api.health_check(url)
        s = self.scale
        if ok:
            self.lbl_conn_status.setText("Servidor online e respondendo")
            self.lbl_conn_status.setStyleSheet(f"color:{DASH_SUCCESS}; font-size:{max(8,int(9*s))}pt; font-weight:600;")
        else:
            self.lbl_conn_status.setText("Não foi possível conectar ao servidor")
            self.lbl_conn_status.setStyleSheet(f"color:{DASH_DANGER}; font-size:{max(8,int(9*s))}pt; font-weight:600;")
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar conexão")

    def _save(self):
        url = self.input_url.text().strip()
        scale = self.slider_scale.value() / 100.0
        clients_path = self.input_ods_path.text().strip()
        products_path = self.input_products_path.text().strip()
        res.save(
            server_url=url,
            font_scale=scale,
            ods_path=clients_path,
            products_path=products_path,
        )
        QMessageBox.information(
            self,
            "Salvo",
            "Configurações salvas.\nReinicie o aplicativo para aplicar a nova escala."
        )
        current = datetime.now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        self.scale_changed.emit(scale)

    def _browse_import_path(self, kind: str):
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
        path = self._import_ui[kind]["input"].text().strip()
        if not path:
            QMessageBox.warning(self, "Atenção", "Informe o caminho do arquivo.")
            return

        current = self._import_threads.get(kind)
        if current and current[0].isRunning():
            QMessageBox.information(
                self,
                "Importacao em andamento",
                "Essa importacao ainda esta em execucao. Aguarde a conclusao.",
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

    def _cleanup_import_thread(self, kind: str, thread: QThread, worker: ImportWorker):
        current = self._import_threads.get(kind)
        if current == (thread, worker):
            self._import_threads.pop(kind, None)
