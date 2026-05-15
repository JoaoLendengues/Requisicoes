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
        f"color:{theme.TEXT_DARK}; font-size:{max(11,int(13*scale))}pt;"
        f"font-weight:bold; padding-top:8px;"
    )
    return lbl


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color:{theme.BORDER_COLOR};")
    return sep


# ── Worker de importação (não bloqueia UI) ────────────────────────────────────
class ImportWorker(QObject):
    progress = Signal(int, int, str)   # atual, total, mensagem
    finished = Signal(object)          # ImportResult
    error    = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            from ..services.client_importer import import_clients
            result = import_clients(self.path, on_progress=self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── View de Configurações ─────────────────────────────────────────────────────
class SettingsView(QWidget):
    scale_changed = Signal(float)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._import_thread = None
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale

        # ScrollArea para suportar telas pequenas
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

        title = QLabel("CONFIGURAÇÕES")
        title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(14,int(17*s))}pt; font-weight:bold;"
        )
        outer.addWidget(title)

        # ── Card principal ────────────────────────────────────────────────────
        card = QFrame()
        card.setStyleSheet(
            f"background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR}; border-radius:10px;"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 20))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16,int(24*s)), max(16,int(20*s)),
                                   max(16,int(24*s)), max(16,int(20*s)))
        layout.setSpacing(max(10,int(14*s)))

        # ── Servidor ─────────────────────────────────────────────────────────
        layout.addWidget(_section("🌐  Conexão com o Servidor", s))
        layout.addWidget(_separator())

        grid = QGridLayout()
        grid.setSpacing(max(8,int(10*s)))

        grid.addWidget(self._lbl("URL do servidor:", s), 0, 0)
        self.input_url = QLineEdit(res.server_url)
        self.input_url.setFixedHeight(max(30,int(36*s)))
        self.input_url.setStyleSheet(theme.input_style(s))
        self.input_url.setPlaceholderText("http://192.168.1.100:8000")
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

        # ── Aparência ─────────────────────────────────────────────────────────
        layout.addWidget(_section("🎨  Aparência", s))
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

        # ── Importação de Clientes ────────────────────────────────────────────
        layout.addWidget(_section("📥  Importação de Clientes (ODS/Excel)", s))
        layout.addWidget(_separator())

        layout.addWidget(self._lbl(
            "Planilha com colunas: Código, Nome, CPF/CNPJ  "
            "(novos clientes são criados; existentes são atualizados)", s,
            color=theme.TEXT_LIGHT, italic=True
        ))

        path_row = QHBoxLayout()
        path_row.addWidget(self._lbl("Arquivo:", s))

        self.input_ods_path = QLineEdit(
            res._read_file().get("ods_path",
                                  r"Z:\REQUISIÇÕES (VENDAS)\relacao_cadastros.ods")
        )
        self.input_ods_path.setFixedHeight(max(30,int(36*s)))
        self.input_ods_path.setStyleSheet(theme.input_style(s))
        path_row.addWidget(self.input_ods_path, 1)

        btn_browse = QPushButton("📂")
        btn_browse.setFixedSize(max(30,int(36*s)), max(30,int(36*s)))
        btn_browse.setStyleSheet(theme.secondary_btn_style(s))
        btn_browse.setToolTip("Navegar...")
        btn_browse.clicked.connect(self._browse_ods)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        # Barra de progresso + botão importar
        import_row = QHBoxLayout()
        self.btn_import = QPushButton("⬆  Importar Clientes")
        self.btn_import.setFixedHeight(max(34,int(40*s)))
        self.btn_import.setStyleSheet(theme.primary_btn_style(s))
        self.btn_import.clicked.connect(self._start_import)
        import_row.addWidget(self.btn_import)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(max(18,int(22*s)))
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ border:1px solid {theme.BORDER_COLOR}; border-radius:4px;"
            f"background:{theme.INPUT_BG}; text-align:center; font-size:{max(8,int(9*s))}pt; }}"
            f"QProgressBar::chunk {{ background:{theme.PRIMARY}; border-radius:3px; }}"
        )
        import_row.addWidget(self.progress_bar, 1)
        layout.addLayout(import_row)

        # Log do resultado
        self.txt_import_log = QTextEdit()
        self.txt_import_log.setReadOnly(True)
        self.txt_import_log.setMaximumHeight(max(100,int(120*s)))
        self.txt_import_log.setVisible(False)
        self.txt_import_log.setStyleSheet(
            f"background:#F8FAFC; border:1px solid {theme.BORDER_COLOR}; border-radius:6px;"
            f"font-size:{max(9,int(10*s))}pt; color:{theme.TEXT_DARK}; padding:4px;"
        )
        layout.addWidget(self.txt_import_log)

        # ── Botão Salvar ──────────────────────────────────────────────────────
        layout.addSpacing(4)
        btn_save = QPushButton("💾  Salvar configurações")
        btn_save.setFixedHeight(max(36,int(42*s)))
        btn_save.setStyleSheet(theme.primary_btn_style(s))
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(card)
        outer.addStretch()

    # ── Helpers ───────────────────────────────────────────────────────────────
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

    # ── Servidor ──────────────────────────────────────────────────────────────
    def _on_scale_change(self, value: int):
        self.lbl_scale_val.setText(f"{value}%")

    def _test_connection(self):
        url = self.input_url.text().strip()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testando...")
        ok = api.health_check(url)
        s = self.scale
        if ok:
            self.lbl_conn_status.setText("✅  Servidor online e respondendo")
            self.lbl_conn_status.setStyleSheet(f"color:{theme.SUCCESS}; font-size:{max(9,int(10*s))}pt;")
        else:
            self.lbl_conn_status.setText("❌  Não foi possível conectar ao servidor")
            self.lbl_conn_status.setStyleSheet(f"color:{theme.DANGER}; font-size:{max(9,int(10*s))}pt;")
        self.btn_test.setEnabled(True)
        self.btn_test.setText("Testar conexão")

    def _save(self):
        url   = self.input_url.text().strip()
        scale = self.slider_scale.value() / 100.0
        path  = self.input_ods_path.text().strip()
        res.save(server_url=url, font_scale=scale, ods_path=path)
        QMessageBox.information(self, "Salvo",
                                "Configurações salvas.\n"
                                "Reinicie o aplicativo para aplicar a nova escala.")
        self.scale_changed.emit(scale)

    # ── Importação ────────────────────────────────────────────────────────────
    def _browse_ods(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar planilha de clientes", "",
            "Planilhas (*.ods *.xlsx *.xlsm *.xls)"
        )
        if path:
            self.input_ods_path.setText(path)

    def _start_import(self):
        path = self.input_ods_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Atenção", "Informe o caminho do arquivo.")
            return

        self.btn_import.setEnabled(False)
        self.btn_import.setText("Importando...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.txt_import_log.setVisible(False)

        self._worker = ImportWorker(path)
        self._import_thread = QThread()
        self._worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_import_done)
        self._worker.error.connect(self._on_import_error)
        self._worker.finished.connect(self._import_thread.quit)
        self._import_thread.start()

    def _on_progress(self, current: int, total: int, msg: str):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{msg} ({current}/{total})")

    def _on_import_done(self, result):
        self.btn_import.setEnabled(True)
        self.btn_import.setText("⬆  Importar Clientes")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.txt_import_log.setVisible(True)
        self.txt_import_log.setPlainText(result.summary())

    def _on_import_error(self, msg: str):
        self.btn_import.setEnabled(True)
        self.btn_import.setText("⬆  Importar Clientes")
        self.progress_bar.setVisible(False)
        self.txt_import_log.setVisible(True)
        self.txt_import_log.setPlainText(f"❌  Erro:\n{msg}")
