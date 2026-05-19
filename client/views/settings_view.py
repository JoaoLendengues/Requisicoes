import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton, QSlider, QFrame,
    QGraphicsDropShadowEffect, QMessageBox, QProgressBar, QTextEdit,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QColor

from ..core import theme
from ..core.resolution import res
from ..api import client as api


def _section(title: str, scale: float) -> QLabel:
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color:{theme.PRIMARY}; font-size:{max(11,int(13*scale))}pt;"
        f"font-weight:bold; padding-top:8px;"
    )
    return lbl


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedHeight(4)
    sep.setStyleSheet("background:transparent; border:none;")
    return sep


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

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet(f"background:{theme.CONTENT_BG};")
        scroll.setWidget(container)

        outer = QVBoxLayout(container)
        outer.setContentsMargins(max(12,int(16*s)), max(12,int(16*s)),
                                  max(12,int(16*s)), max(12,int(16*s)))
        outer.setSpacing(max(10,int(14*s)))

        title = QLabel("⚙️ CONFIGURAÇÕES")
        title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(14,int(17*s))}pt; font-weight:bold;"
        )
        outer.addWidget(title)

        card = QFrame()
        card.setStyleSheet(
            f"background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:8px;"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 12))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16,int(24*s)), max(16,int(20*s)),
                                   max(16,int(24*s)), max(16,int(20*s)))
        layout.setSpacing(max(10,int(14*s)))

        layout.addWidget(_section("🌐 Conexão com o Servidor", s))
        layout.addWidget(_separator())

        grid = QGridLayout()
        grid.setSpacing(max(8,int(10*s)))

        grid.addWidget(self._lbl("URL do servidor:", s), 0, 0)
        self.input_url = QLineEdit(res.server_url)
        self.input_url.setFixedHeight(max(30,int(36*s)))
        self.input_url.setStyleSheet(theme.input_style(s))
        self.input_url.setPlaceholderText("http://192.168.1.100:5000")
        grid.addWidget(self.input_url, 0, 1)

        self.btn_test = QPushButton("Testar conexão")
        self.btn_test.setFixedHeight(max(30,int(36*s)))
        self.btn_test.setStyleSheet(theme.secondary_btn_style(s))
        self.btn_test.clicked.connect(self._test_connection)
        grid.addWidget(self.btn_test, 0, 2)

        self.lbl_conn_status = QLabel("")
        self.lbl_conn_status.setStyleSheet(f"font-size:{max(9,int(10*s))}pt;")
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
            f"color:{theme.PRIMARY}; font-weight:bold; font-size:{max(10,int(12*s))}pt;"
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
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8,int(9*s))}pt; font-style:italic;"
        )
        layout.addWidget(screen_info)

        layout.addWidget(_section("📄 PDF Automático", s))
        layout.addWidget(_separator())

        layout.addWidget(self._lbl(
            "Pasta onde os PDFs serão salvos automaticamente ao salvar uma requisição.",
            s, color=theme.TEXT_LIGHT, italic=True
        ))

        pdf_row = QHBoxLayout()
        pdf_row.addWidget(self._lbl("Pasta de PDFs:", s))

        self.input_pdf_folder = QLineEdit(res._read_file().get("pdf_folder", ""))
        self.input_pdf_folder.setPlaceholderText(r"Ex.: Z:\REQUISIÇÕES (VENDAS)\PDFs")
        self.input_pdf_folder.setFixedHeight(max(30, int(36 * s)))
        self.input_pdf_folder.setStyleSheet(theme.input_style(s))
        pdf_row.addWidget(self.input_pdf_folder, 1)

        btn_browse_pdf = QPushButton("...")
        btn_browse_pdf.setFixedSize(max(30, int(36 * s)), max(30, int(36 * s)))
        btn_browse_pdf.setStyleSheet(theme.secondary_btn_style(s))
        btn_browse_pdf.setToolTip("Selecionar pasta...")
        btn_browse_pdf.clicked.connect(self._browse_pdf_folder)
        pdf_row.addWidget(btn_browse_pdf)
        layout.addLayout(pdf_row)

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
        btn_save.setFixedHeight(max(36,int(42*s)))
        btn_save.setStyleSheet(theme.primary_btn_style(s))
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(card)
        outer.addStretch()

    def _create_import_section(self, layout: QVBoxLayout, kind: str, title: str,
                               description: str, default_path: str, button_text: str):
        s = self.scale
        layout.addWidget(_section(title, s))
        layout.addWidget(_separator())
        layout.addWidget(self._lbl(description, s, color=theme.TEXT_LIGHT, italic=True))

        path_row = QHBoxLayout()
        path_row.addWidget(self._lbl("Arquivo:", s))

        input_path = QLineEdit(default_path)
        input_path.setFixedHeight(max(30,int(36*s)))
        input_path.setStyleSheet(theme.input_style(s))
        path_row.addWidget(input_path, 1)

        btn_browse = QPushButton("...")
        btn_browse.setFixedSize(max(30,int(36*s)), max(30,int(36*s)))
        btn_browse.setStyleSheet(theme.secondary_btn_style(s))
        btn_browse.setToolTip("Navegar...")
        btn_browse.clicked.connect(lambda: self._browse_import_path(kind))
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        import_row = QHBoxLayout()
        btn_import = QPushButton(button_text)
        btn_import.setFixedHeight(max(34,int(40*s)))
        btn_import.setStyleSheet(theme.primary_btn_style(s))
        btn_import.clicked.connect(lambda: self._start_import(kind))
        import_row.addWidget(btn_import)

        progress_bar = QProgressBar()
        progress_bar.setFixedHeight(max(18,int(22*s)))
        progress_bar.setVisible(False)
        progress_bar.setStyleSheet(
            f"QProgressBar {{ border:1px solid {theme.BORDER_COLOR}; border-radius:4px;"
            f"background:{theme.INPUT_BG}; text-align:center; font-size:{max(8,int(9*s))}pt; }}"
            f"QProgressBar::chunk {{ background:{theme.PRIMARY}; border-radius:3px; }}"
        )
        import_row.addWidget(progress_bar, 1)
        layout.addLayout(import_row)

        txt_log = QTextEdit()
        txt_log.setReadOnly(True)
        txt_log.setMaximumHeight(max(100,int(120*s)))
        txt_log.setVisible(False)
        txt_log.setStyleSheet(
            f"background:{theme.INPUT_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:6px;"
            f"font-size:{max(9,int(10*s))}pt; color:{theme.TEXT_DARK}; padding:4px;"
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
        c = color or theme.TEXT_MEDIUM
        fs = max(9, int(11 * scale))
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
            self.lbl_conn_status.setStyleSheet(f"color:{theme.SUCCESS}; font-size:{max(9,int(10*s))}pt;")
        else:
            self.lbl_conn_status.setText("Não foi possível conectar ao servidor")
            self.lbl_conn_status.setStyleSheet(f"color:{theme.DANGER}; font-size:{max(9,int(10*s))}pt;")
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar conexão")

    def _save(self):
        url = self.input_url.text().strip()
        scale = self.slider_scale.value() / 100.0
        clients_path = self.input_ods_path.text().strip()
        products_path = self.input_products_path.text().strip()
        pdf_folder = self.input_pdf_folder.text().strip()
        res.save(
            server_url=url,
            font_scale=scale,
            ods_path=clients_path,
            products_path=products_path,
            pdf_folder=pdf_folder,
        )
        QMessageBox.information(
            self,
            "Salvo",
            "Configurações salvas.\nReinicie o aplicativo para aplicar a nova escala."
        )
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

    def _browse_pdf_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar pasta para PDFs",
            "",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if folder:
            self.input_pdf_folder.setText(folder)

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
