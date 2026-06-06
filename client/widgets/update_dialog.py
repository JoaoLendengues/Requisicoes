"""
Diálogo de atualização — Requisições Pinheiro.

UpdateAvailableDialog:
  - Popup que aparece automaticamente no startup quando há nova versão.
  - Header com gradient neon + transição de versão visual.
  - Painel de release notes renderizado em Markdown (mesmo body do GitHub).
  - Metadados: data da release, nome, tamanho do download.
  - Botões "Atualizar agora" / "Mais tarde" com estilo neon.
  - Após confirmar, baixa o pacote embutido com barra de progresso.
  - Durante o download a janela não pode ser fechada.
  - Ao concluir o download, lança o update_helper.exe e fecha o app.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QUrl, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap, QImage, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextBrowser,
    QFrame,
    QApplication,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QWidget,
    QSizePolicy,
)

from ..core import theme
from ..core.datetime_utils import format_date as _format_date
from ..updater import UpdateDownloader, UpdateInstaller, get_update_log_path
from .. import version as _version_mod


# Regex para extrair imagens do Markdown: ![alt](url) ou ![alt](url "title")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


class _ImageFetcher(QThread):
    """Baixa uma imagem em background sem bloquear a UI.

    Signal `loaded(url, QImage)` ao concluir com sucesso, `failed(url)` em erro.
    Tem timeout de 5s — release com imagem inacessivel nao trava o dialog.
    """
    loaded = Signal(str, QImage)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            import requests
            resp = requests.get(self._url, timeout=5, stream=True)
            resp.raise_for_status()
            data = resp.content
            img = QImage()
            if img.loadFromData(data):
                self.loaded.emit(self._url, img)
            else:
                self.failed.emit(self._url)
        except Exception:
            self.failed.emit(self._url)


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _format_release_date(iso: str) -> str:
    """Converte data ISO do GitHub em formato brasileiro: 'Lançado em 02/06/2026'."""
    if not iso:
        return ""
    try:
        # Aceita formato '2026-06-02T15:30:00Z' do GitHub
        formatted = _format_date(iso)
        return f"Lançado em {formatted}" if formatted != "-" else ""
    except Exception:
        return ""


def _format_size(size_bytes: int) -> str:
    """Tamanho human-readable: 12.4 MB."""
    if not size_bytes or size_bytes <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024 or unit == "GB":
            return f"{size_bytes:.1f} {unit}".replace(".0 ", " ")
        size_bytes /= 1024
    return ""


class UpdateAvailableDialog(QDialog):
    """Popup moderno de notificação de nova versão disponível."""

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self._downloader: UpdateDownloader | None = None
        self._downloading = False
        # Hero image: primeira imagem do Markdown vira banner no header (se houver).
        # Demais imagens permanecem inline no changelog (baixadas em background).
        self._hero_image_url: str | None = None
        self._inline_image_urls: list[str] = []
        self._image_fetchers: list[_ImageFetcher] = []
        self._loaded_images: dict[str, QImage] = {}
        self._extract_images()
        self._setup_ui()
        self._animate_in()
        # Inicia downloads das imagens APOS UI montada para nao bloquear setup
        QTimer.singleShot(0, self._start_image_downloads)

    def _extract_images(self) -> None:
        """Detecta imagens no Markdown e separa: hero (primeira) vs inline (resto).

        A hero so vira banner se for a primeira coisa significativa do Markdown
        (linhas iniciais antes de qualquer texto/header). Caso contrario, todas
        ficam inline no changelog.
        """
        md = (self.update_info.get("changelog") or "").lstrip()
        if not md:
            return
        # A primeira imagem nas primeiras linhas vira hero
        first_lines = md.split("\n\n", 1)[0]  # primeiro paragrafo
        first_match = _MD_IMAGE_RE.search(first_lines)
        all_matches = list(_MD_IMAGE_RE.finditer(md))

        if first_match and all_matches and all_matches[0].start() == first_match.start():
            # Primeira imagem aparece logo no inicio → vira hero
            self._hero_image_url = first_match.group(2)
            # Remove a hero do markdown body
            self.update_info = dict(self.update_info)
            self.update_info["changelog"] = md.replace(first_match.group(0), "", 1).lstrip()
            self._inline_image_urls = [m.group(2) for m in all_matches[1:]]
        else:
            self._inline_image_urls = [m.group(2) for m in all_matches]

    def _start_image_downloads(self) -> None:
        """Dispara downloads em background para hero + inline."""
        urls = []
        if self._hero_image_url:
            urls.append(self._hero_image_url)
        urls.extend(self._inline_image_urls)
        for url in urls:
            fetcher = _ImageFetcher(url, parent=self)
            fetcher.loaded.connect(self._on_image_loaded)
            fetcher.failed.connect(self._on_image_failed)
            fetcher.start()
            self._image_fetchers.append(fetcher)

    def _on_image_loaded(self, url: str, image: QImage) -> None:
        self._loaded_images[url] = image
        if url == self._hero_image_url:
            self._apply_hero_image(image)
        else:
            self._apply_inline_image(url, image)

    def _on_image_failed(self, url: str) -> None:
        # Em falha silenciosa, deixa o alt-text do Markdown aparecer no lugar
        pass

    def _apply_hero_image(self, image: QImage) -> None:
        """Substitui o placeholder do hero pela imagem carregada."""
        if not hasattr(self, "_hero_label") or self._hero_label is None:
            return
        # Redimensiona mantendo aspect ratio, largura máxima do dialog
        target_width = self.width() - 0  # full width
        pix = QPixmap.fromImage(image)
        # Crop/scale para banner 640x180 (proporcao 3.55:1)
        scaled = pix.scaled(
            target_width, 180,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center-crop horizontal se ficou mais largo que target
        if scaled.width() > target_width:
            x = (scaled.width() - target_width) // 2
            scaled = scaled.copy(x, 0, target_width, scaled.height())
        self._hero_label.setPixmap(scaled)
        self._hero_label.setVisible(True)

    def _apply_inline_image(self, url: str, image: QImage) -> None:
        """Registra a imagem como resource do QTextDocument E re-renderiza
        o Markdown garantindo que a referencia seja resolvida."""
        if not hasattr(self, "_notes") or self._notes is None:
            return
        # Limita largura para nao quebrar layout
        max_w = 540
        if image.width() > max_w:
            image = image.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)

        doc = self._notes.document()
        # Adiciona a resource antes de re-renderizar o Markdown.
        # setMarkdown() preserva resources adicionadas antes via addResource.
        doc.addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(url),
            image,
        )
        # IMPORTANTE: re-injetar o CSS porque setMarkdown recria documento.
        doc.setDefaultStyleSheet(self._markdown_css())
        # Re-renderiza Markdown — agora a resource ja esta registrada.
        current_md = self.update_info.get("changelog") or ""
        self._notes.setMarkdown(current_md)
        # Re-adiciona todas as outras imagens ja carregadas (setMarkdown perde resources antigos)
        for prev_url, prev_img in self._loaded_images.items():
            if prev_url == url or prev_url == self._hero_image_url:
                continue
            doc.addResource(
                QTextDocument.ResourceType.ImageResource,
                QUrl(prev_url),
                prev_img,
            )

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Atualização disponível")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        # Janela mais alta se houver hero image (banner 180px)
        height = 760 if self._hero_image_url else 580
        self.setFixedSize(640, height)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("updateDialog")

        # Background da janela usa paleta neon do app
        self.setStyleSheet(
            f"QDialog#updateDialog {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f"    stop:0 {theme.PANEL_CARD_BG_START},"
            f"    stop:0.55 {theme.PANEL_CARD_BG_MID},"
            f"    stop:1 {theme.PANEL_CARD_BG_END});"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero banner (so se hover hero_image_url; comeca oculto, aparece ao carregar)
        if self._hero_image_url:
            self._hero_label = QLabel()
            self._hero_label.setFixedHeight(180)
            self._hero_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._hero_label.setScaledContents(False)
            self._hero_label.setStyleSheet(
                f"background: {_rgba(theme.PANEL_SURFACE_BG, 200)};"
                f"border-bottom: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            )
            # Placeholder enquanto carrega
            placeholder = QLabel("🖼  Carregando imagem da release...")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(
                f"background: transparent; color: {theme.PANEL_TEXT_MUTED};"
                f"font-size: 10pt; font-style: italic;"
            )
            self._hero_label.setText("🖼  Carregando imagem...")
            root.addWidget(self._hero_label)
        else:
            self._hero_label = None

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        """Header gradient com badge de versão + transição visual."""
        header = QFrame()
        header.setObjectName("updateHeader")
        header.setFixedHeight(110)
        header.setStyleSheet(
            f"QFrame#updateHeader {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {_rgba(theme.PANEL_NEON_PRIMARY, 38)},"
            f"    stop:0.5 {_rgba(theme.PANEL_NEON_SECONDARY, 28)},"
            f"    stop:1 {_rgba(theme.PANEL_NEON_PRIMARY, 38)});"
            f"  border-bottom: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            f"}}"
        )

        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(28, 18, 28, 18)
        h_layout.setSpacing(16)

        # Ícone grande à esquerda
        icon = QLabel("🚀")
        icon.setStyleSheet(
            f"background: transparent; font-size: 38pt;"
        )
        icon.setFixedWidth(64)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(icon)

        # Coluna de textos
        col = QVBoxLayout()
        col.setSpacing(4)
        col.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Nova versão disponível")
        title.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_PRIMARY};"
            f"font-size: 16pt; font-weight: 800;"
        )
        col.addWidget(title)

        # Versão atual → nova versão (chip estilo "v1.2.3 → v1.3.0")
        version_row = QHBoxLayout()
        version_row.setSpacing(8)
        version_row.setContentsMargins(0, 0, 0, 0)

        current_version = getattr(_version_mod, "CURRENT_VERSION", "?")
        new_version = self.update_info.get("version", "?")

        from_chip = QLabel(f"v{current_version}")
        from_chip.setStyleSheet(self._chip_style(muted=True))
        version_row.addWidget(from_chip)

        arrow = QLabel("→")
        arrow.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_MUTED};"
            f"font-size: 14pt; font-weight: 700;"
        )
        version_row.addWidget(arrow)

        to_chip = QLabel(f"v{new_version}")
        to_chip.setStyleSheet(self._chip_style(muted=False))
        version_row.addWidget(to_chip)

        version_row.addStretch()
        col.addLayout(version_row)

        h_layout.addLayout(col, 1)
        return header

    def _build_body(self) -> QWidget:
        """Painel principal com release notes em Markdown."""
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 20, 28, 16)
        body_layout.setSpacing(12)

        # Linha de metadados (data + nome + tamanho)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(14)

        release_date = _format_release_date(self.update_info.get("release_date", ""))
        release_name = self.update_info.get("release_name", "").strip()
        size_bytes = self.update_info.get("asset_size") or 0
        size_str = _format_size(int(size_bytes)) if isinstance(size_bytes, (int, float)) else ""

        meta_parts = []
        if release_date:
            meta_parts.append(("📅", release_date))
        if release_name and release_name != f"v{self.update_info.get('version', '')}":
            meta_parts.append(("🏷️", release_name))
        if size_str:
            meta_parts.append(("📦", f"Pacote: {size_str}"))

        if meta_parts:
            for icon_text, text in meta_parts:
                chip = QLabel(f"{icon_text}  {text}")
                chip.setStyleSheet(
                    f"background: {_rgba(theme.PANEL_NEON_PRIMARY, 18)};"
                    f"color: {theme.PANEL_TEXT_PRIMARY};"
                    f"border: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 64)};"
                    f"border-radius: 12px; padding: 6px 12px;"
                    f"font-size: 9pt; font-weight: 600;"
                )
                meta_row.addWidget(chip)
            meta_row.addStretch()
            body_layout.addLayout(meta_row)

        # Cabeçalho "Notas da versão"
        notes_header = QLabel("📝  Notas da versão")
        notes_header.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_NEON_PRIMARY};"
            f"font-size: 10pt; font-weight: 800; padding-top: 4px;"
        )
        body_layout.addWidget(notes_header)

        # Render Markdown em QTextBrowser (suporta links)
        self._notes = QTextBrowser()
        self._notes.setOpenExternalLinks(True)
        self._notes.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._notes.setStyleSheet(
            f"QTextBrowser {{"
            f"  background: {_rgba(theme.PANEL_SURFACE_BG, 220)};"
            f"  color: {theme.PANEL_TEXT_PRIMARY};"
            f"  border: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 64)};"
            f"  border-radius: 12px;"
            f"  padding: 14px 16px;"
            f"  font-size: 10pt;"
            f"  selection-background-color: {_rgba(theme.PANEL_NEON_PRIMARY, 80)};"
            f"  selection-color: {theme.PANEL_TEXT_PRIMARY};"
            f"}}"
            f"QScrollBar:vertical {{"
            f"  background: transparent; width: 8px; margin: 4px 2px;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            f"  border-radius: 4px; min-height: 32px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{"
            f"  background: {_rgba(theme.PANEL_NEON_PRIMARY, 180)};"
            f"}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        # CSS embutido no documento — controla aparência do Markdown renderizado
        self._notes.document().setDefaultStyleSheet(self._markdown_css())

        changelog_md = self.update_info.get("changelog") or "_Sem notas de versão._"
        self._notes.setMarkdown(changelog_md)

        # Aplica paleta cuidadosamente para garantir cor de texto correta
        pal = self._notes.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.PANEL_TEXT_PRIMARY))
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.PANEL_SURFACE_BG))
        self._notes.setPalette(pal)

        body_layout.addWidget(self._notes, 1)

        # Aviso discreto
        aviso = QLabel(
            "ℹ️  O aplicativo será fechado para aplicar a atualização e reabrirá automaticamente."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_MUTED};"
            f"font-size: 9pt; padding: 2px 4px;"
        )
        body_layout.addWidget(aviso)

        return body

    def _build_footer(self) -> QWidget:
        """Rodapé com botões + barra de progresso."""
        footer = QFrame()
        footer.setObjectName("updateFooter")
        footer.setStyleSheet(
            f"QFrame#updateFooter {{"
            f"  background: {_rgba(theme.PANEL_SURFACE_BG, 60)};"
            f"  border-top: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 64)};"
            f"}}"
        )

        f_layout = QVBoxLayout(footer)
        f_layout.setContentsMargins(28, 16, 28, 20)
        f_layout.setSpacing(10)

        # Linha de progresso (oculta até o download começar)
        self._progress_label = QLabel("Baixando atualização...")
        self._progress_label.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_PRIMARY};"
            f"font-size: 9pt; font-weight: 600;"
        )
        self._progress_label.setVisible(False)
        f_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{"
            f"  border: none; border-radius: 4px;"
            f"  background: {_rgba(theme.PANEL_SURFACE_ALT, 200)};"
            f"}}"
            f"QProgressBar::chunk {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {theme.PANEL_NEON_PRIMARY},"
            f"    stop:1 {theme.PANEL_NEON_SECONDARY});"
            f"  border-radius: 4px;"
            f"}}"
        )
        self._progress_bar.setVisible(False)
        f_layout.addWidget(self._progress_bar)

        # Botões
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._btn_later = QPushButton("Mais tarde")
        self._btn_later.setFixedHeight(42)
        self._btn_later.setMinimumWidth(140)
        self._btn_later.setStyleSheet(self._secondary_style())
        self._btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_later.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_later)

        self._btn_update = QPushButton("🚀  Atualizar agora")
        self._btn_update.setFixedHeight(42)
        self._btn_update.setMinimumWidth(180)
        self._btn_update.setStyleSheet(self._primary_style())
        self._btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_update.clicked.connect(self._start_download)

        # Sombra sutil no botão primário
        shadow = QGraphicsDropShadowEffect(self._btn_update)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow_color = QColor(theme.PANEL_NEON_PRIMARY)
        shadow_color.setAlpha(120)
        shadow.setColor(shadow_color)
        self._btn_update.setGraphicsEffect(shadow)

        btn_row.addWidget(self._btn_update)
        f_layout.addLayout(btn_row)

        return footer

    # ── Animação de entrada ───────────────────────────────────────────────────

    def _animate_in(self) -> None:
        """Fade-in suave da janela ao abrir."""
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in = anim  # mantém ref
        QTimer.singleShot(0, anim.start)

    # ── Download (fluxo original preservado) ──────────────────────────────────

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
        self._progress_label.setText(f"Baixando atualização...  {value}%")

    def _on_download_finished(self, file_path: str) -> None:
        self._downloading = False
        self._progress_label.setText("✓ Download concluído. Preparando instalação...")
        self._progress_bar.setValue(100)

        success, message = UpdateInstaller.install_update(file_path)

        if success:
            self.accept()
            QTimer.singleShot(800, QApplication.instance().quit)
            return

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
    def _chip_style(muted: bool) -> str:
        if muted:
            return (
                f"background: {_rgba(theme.PANEL_SURFACE_ALT, 180)};"
                f"color: {theme.PANEL_TEXT_MUTED};"
                f"border: 1px solid {_rgba(theme.PANEL_TEXT_MUTED, 60)};"
                f"border-radius: 14px; padding: 4px 12px;"
                f"font-size: 10pt; font-weight: 700;"
            )
        return (
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"  stop:0 {_rgba(theme.PANEL_NEON_PRIMARY, 80)},"
            f"  stop:1 {_rgba(theme.PANEL_NEON_SECONDARY, 80)});"
            f"color: {theme.PANEL_TEXT_PRIMARY};"
            f"border: 1px solid {theme.PANEL_NEON_PRIMARY};"
            f"border-radius: 14px; padding: 4px 14px;"
            f"font-size: 10pt; font-weight: 800;"
        )

    @staticmethod
    def _primary_style() -> str:
        return (
            f"QPushButton {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {theme.PANEL_NEON_PRIMARY},"
            f"    stop:1 {theme.PANEL_NEON_SECONDARY});"
            f"  color: {theme.PANEL_TEXT_PRIMARY};"
            f"  border: none; border-radius: 14px;"
            f"  padding: 0 22px; font-size: 11pt; font-weight: 800;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {theme.PANEL_NEON_SECONDARY},"
            f"    stop:1 {theme.PANEL_NEON_PRIMARY});"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background: {theme.PANEL_NEON_PRIMARY};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background: {_rgba(theme.PANEL_TEXT_MUTED, 100)};"
            f"  color: {_rgba(theme.PANEL_TEXT_PRIMARY, 160)};"
            f"}}"
        )

    @staticmethod
    def _secondary_style() -> str:
        return (
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {theme.PANEL_TEXT_PRIMARY};"
            f"  border: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            f"  border-radius: 14px;"
            f"  padding: 0 22px; font-size: 10pt; font-weight: 700;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {_rgba(theme.PANEL_NEON_PRIMARY, 28)};"
            f"  border: 1px solid {theme.PANEL_NEON_PRIMARY};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  color: {theme.PANEL_TEXT_MUTED};"
            f"  border: 1px solid {_rgba(theme.PANEL_TEXT_MUTED, 60)};"
            f"}}"
        )

    @staticmethod
    def _markdown_css() -> str:
        """Stylesheet CSS aplicado ao documento Markdown renderizado.

        Controla aparência de headings, listas, código, links — emula visual
        moderno (GitHub-like) mas usando paleta neon do app.
        """
        text = theme.PANEL_TEXT_PRIMARY
        muted = theme.PANEL_TEXT_MUTED
        neon = theme.PANEL_NEON_PRIMARY
        neon2 = theme.PANEL_NEON_SECONDARY
        surface_alt = theme.PANEL_SURFACE_ALT
        return f"""
            body {{
                font-family: 'Inter', 'Segoe UI', sans-serif;
                color: {text};
                line-height: 1.6;
            }}
            h1, h2, h3, h4 {{
                color: {neon};
                font-weight: 800;
                margin-top: 14px;
                margin-bottom: 6px;
            }}
            h1 {{ font-size: 14pt; }}
            h2 {{ font-size: 13pt; }}
            h3 {{ font-size: 12pt; }}
            h4 {{ font-size: 11pt; }}
            p {{
                margin-top: 4px;
                margin-bottom: 8px;
                color: {text};
            }}
            ul, ol {{
                margin-left: 18px;
                margin-top: 4px;
                margin-bottom: 8px;
            }}
            li {{
                margin-bottom: 4px;
                color: {text};
            }}
            strong, b {{ color: {neon2}; font-weight: 800; }}
            em, i {{ color: {muted}; }}
            code {{
                background: {_rgba(surface_alt, 200)};
                color: {neon2};
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
            }}
            pre {{
                background: {_rgba(surface_alt, 200)};
                color: {text};
                padding: 10px 12px;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
                margin-top: 6px;
                margin-bottom: 8px;
            }}
            blockquote {{
                border-left: 3px solid {neon};
                padding-left: 12px;
                color: {muted};
                margin: 8px 0;
            }}
            a {{
                color: {neon};
                text-decoration: none;
                font-weight: 700;
            }}
            a:hover {{ text-decoration: underline; }}
            hr {{
                border: none;
                border-top: 1px solid {_rgba(neon, 60)};
                margin: 12px 0;
            }}
        """
