"""
Diálogo de atualização — Requisições Pinheiro.

UpdateAvailableDialog:
  - Popup que aparece automaticamente no startup quando há nova versão.
  - Mostra versão disponível, changelog e botões "Atualizar agora" / "Mais tarde".
  - Após confirmar, baixa o pacote embutido no próprio dialog (com barra de progresso).
  - Durante o download a janela não pode ser fechada.
  - Ao concluir o download, lança o update_helper.exe e fecha o app.
"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QFrame,
    QApplication,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from ..core import theme
from ..updater import UpdateDownloader, UpdateInstaller, get_update_log_path


class UpdateAvailableDialog(QDialog):
    """
    Popup de notificação de nova versão disponível.
    Exibido automaticamente no startup — o usuário escolhe atualizar ou adiar.
    """

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self._downloader: UpdateDownloader | None = None
        self._downloading = False
        self._setup_ui()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Atualização disponível")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Título
        title = QLabel(f"Nova versão disponível: v{self.update_info['version']}")
        title.setFont(QFont(theme.FONT_PRIMARY, 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {theme.TEXT_DARK};")
        layout.addWidget(title)

        # Changelog
        changelog_header = QLabel("O que há de novo:")
        changelog_header.setStyleSheet(
            f"background:transparent; font-size: 9pt; font-weight: 700; color: {theme.TEXT_MEDIUM};"
        )
        layout.addWidget(changelog_header)

        changelog = QTextEdit()
        changelog.setReadOnly(True)
        changelog.setPlainText(self.update_info.get("changelog") or "Sem notas de versão.")
        changelog.setFixedHeight(110)
        changelog.setStyleSheet(
            f"background: {theme.TABLE_ALT_ROW}; border: none; border-radius: 10px;"
            f"font-size: 9pt; padding: 8px; color: {theme.TEXT_DARK};"
        )
        layout.addWidget(changelog)

        # Aviso
        aviso = QLabel(
            "O aplicativo será fechado para aplicar a atualização e reabrirá automaticamente."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"background:transparent; font-size: 9pt; color: {theme.TEXT_MEDIUM};")
        layout.addWidget(aviso)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_COLOR};")
        layout.addWidget(sep)

        # Botões
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_later = QPushButton("Mais tarde")
        self._btn_later.setFixedHeight(38)
        self._btn_later.setStyleSheet(self._secondary_style())
        self._btn_later.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_later)

        self._btn_update = QPushButton("Atualizar agora")
        self._btn_update.setFixedHeight(38)
        self._btn_update.setStyleSheet(self._primary_style())
        self._btn_update.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_update)

        layout.addLayout(btn_row)

        # Progresso (oculto até o download começar)
        self._progress_label = QLabel("Baixando atualização...")
        self._progress_label.setStyleSheet(
            f"background:transparent; font-size: 9pt; color: {theme.TEXT_MEDIUM};"
        )
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{"
            f"  border: none; border-radius: 4px;"
            f"  background: {theme.TABLE_ALT_ROW};"
            f"}}"
            f"QProgressBar::chunk {{"
            f"  background: {theme.PRIMARY}; border-radius: 4px;"
            f"}}"
        )
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        self._downloading = True
        self._btn_update.setEnabled(False)
        self._btn_update.setText("Baixando...")
        self._btn_later.setEnabled(False)
        self._progress_label.setVisible(True)
        self._progress_bar.setVisible(True)

        self._downloader = UpdateDownloader(
            self.update_info["download_url"],
            self.update_info.get("asset_name", ""),
            parent=self,
        )
        self._downloader.progress.connect(self._on_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_progress(self, value: int) -> None:
        self._progress_bar.setValue(value)
        self._progress_label.setText(f"Baixando atualização... {value}%")

    def _on_download_finished(self, file_path: str) -> None:
        self._downloading = False
        self._progress_label.setText("Preparando instalação...")
        self._progress_bar.setValue(100)

        success, message = UpdateInstaller.install_update(file_path)

        if success:
            self.accept()
            # Pequeno delay para o helper ter tempo de iniciar antes do app fechar
            QTimer.singleShot(800, QApplication.instance().quit)
            return

        # Falha na instalação
        log_path = get_update_log_path()
        detail = message
        if log_path.exists():
            detail += f"\n\nLog: {log_path}"
        QMessageBox.critical(self, "Erro na atualização", detail)
        self._reset_buttons()

    def _on_download_error(self, error_msg: str) -> None:
        self._downloading = False
        QMessageBox.critical(
            self, "Erro no download",
            f"Não foi possível baixar a atualização:\n\n{error_msg}",
        )
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        self._btn_update.setEnabled(True)
        self._btn_update.setText("Tentar novamente")
        self._btn_later.setEnabled(True)
        self._progress_label.setVisible(False)
        self._progress_bar.setVisible(False)

    # ── Impede fechar durante download ────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._downloading:
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self) -> None:
        if self._downloading:
            return
        super().reject()

    # ── Estilos ───────────────────────────────────────────────────────────────

    @staticmethod
    def _primary_style() -> str:
        return (
            f"QPushButton {{"
            f"  background: {theme.PRIMARY}; color: #fff;"
            f"  border: none; border-radius: 12px;"
            f"  padding: 0 22px; font-size: 10pt; font-weight: 700;"
            f"}}"
            f"QPushButton:hover {{ background: {theme.PRIMARY_HOVER}; }}"
            f"QPushButton:pressed {{ background: {theme.SIDEBAR_BG}; }}"
            f"QPushButton:disabled {{ background: #A7B3C6; color: #F8FAFC; }}"
        )

    @staticmethod
    def _secondary_style() -> str:
        return (
            f"QPushButton {{"
            f"  background: {theme.CARD_BG}; color: {theme.TEXT_DARK};"
            f"  border: 1px solid {theme.BORDER_COLOR}; border-radius: 12px;"
            f"  padding: 0 22px; font-size: 10pt; font-weight: 700;"
            f"}}"
            f"QPushButton:hover {{ background: {theme.TABLE_ALT_ROW}; }}"
            f"QPushButton:disabled {{ color: {theme.TEXT_MEDIUM}; }}"
        )
