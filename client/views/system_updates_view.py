"""
Diálogo de verificação de atualizações — Requisições Pinheiro.

Acessado pelo botão "Atualizações" na sidebar. Janela independente com
verificação de nova versão, status e acesso ao UpdateAvailableDialog.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
    QGraphicsDropShadowEffect,
)

from ..core import theme
from .. import version as _version_mod


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


class SystemUpdatesDialog(QDialog):
    """Janela de verificação e gerenciamento de atualizações do sistema."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_checker = None
        self._setup_ui()
        self._animate_in()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Atualizações")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(500, 360)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("systemUpdatesDialog")
        self.setStyleSheet(
            f"QDialog#systemUpdatesDialog {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f"    stop:0 {theme.PANEL_CARD_BG_START},"
            f"    stop:0.55 {theme.PANEL_CARD_BG_MID},"
            f"    stop:1 {theme.PANEL_CARD_BG_END});"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("updatesHeader")
        header.setFixedHeight(108)
        header.setStyleSheet(
            f"QFrame#updatesHeader {{"
            f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {_rgba(theme.PANEL_NEON_PRIMARY, 38)},"
            f"    stop:0.5 {_rgba(theme.PANEL_NEON_SECONDARY, 28)},"
            f"    stop:1 {_rgba(theme.PANEL_NEON_PRIMARY, 38)});"
            f"  border-bottom: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            f"}}"
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.setSpacing(16)

        icon_label = QLabel("🔄")
        icon_label.setStyleSheet("background: transparent; font-size: 34pt;")
        icon_label.setFixedWidth(60)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        col = QVBoxLayout()
        col.setSpacing(6)
        col.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Atualizações do Sistema")
        title.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_PRIMARY};"
            f"font-size: 15pt; font-weight: 800;"
        )
        col.addWidget(title)

        current_version = getattr(_version_mod, "CURRENT_VERSION", "?")
        version_chip = QLabel(f"Versão instalada: v{current_version}")
        version_chip.setStyleSheet(
            f"background: {_rgba(theme.PANEL_NEON_PRIMARY, 22)};"
            f"color: {theme.PANEL_TEXT_PRIMARY};"
            f"border: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 90)};"
            f"border-radius: 12px; padding: 4px 14px;"
            f"font-size: 10pt; font-weight: 700;"
        )
        col.addWidget(version_chip)
        layout.addLayout(col, 1)
        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 28, 32, 16)
        layout.setSpacing(14)

        helper = QLabel(
            "Clique em <b>Verificar agora</b> para checar se há uma nova versão disponível no GitHub. "
            "Quando houver uma atualização, o sistema exibirá os detalhes e permitirá "
            "iniciar a instalação com um clique — sem precisar de intervenção manual."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet(
            f"background: transparent; color: {theme.PANEL_TEXT_MUTED};"
            f"font-size: 10pt; line-height: 1.6;"
        )
        layout.addWidget(helper)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"background: transparent; font-size: 10pt; font-weight: 700;"
            f"color: {theme.PANEL_TEXT_MUTED};"
        )
        layout.addWidget(self._status_label)
        layout.addStretch()
        return body

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("updatesFooter")
        footer.setStyleSheet(
            f"QFrame#updatesFooter {{"
            f"  background: {_rgba(theme.PANEL_SURFACE_BG, 60)};"
            f"  border-top: 1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 64)};"
            f"}}"
        )

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(28, 16, 28, 20)
        layout.setSpacing(10)
        layout.addStretch()

        self._btn_close = QPushButton("Fechar")
        self._btn_close.setFixedHeight(42)
        self._btn_close.setMinimumWidth(120)
        self._btn_close.setStyleSheet(self._secondary_style())
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.reject)
        layout.addWidget(self._btn_close)

        self._btn_check = QPushButton("🔍  Verificar agora")
        self._btn_check.setFixedHeight(42)
        self._btn_check.setMinimumWidth(190)
        self._btn_check.setStyleSheet(self._primary_style())
        self._btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_check.clicked.connect(self._check_updates)

        shadow = QGraphicsDropShadowEffect(self._btn_check)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        color = QColor(theme.PANEL_NEON_PRIMARY)
        color.setAlpha(120)
        shadow.setColor(color)
        self._btn_check.setGraphicsEffect(shadow)

        layout.addWidget(self._btn_check)
        return footer

    def _animate_in(self) -> None:
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in = anim
        QTimer.singleShot(0, anim.start)

    def _check_updates(self) -> None:
        from ..updater import UpdateChecker

        self._btn_check.setEnabled(False)
        self._btn_check.setText("Verificando...")
        self._set_status("", color=None)

        self._update_checker = UpdateChecker(parent=self)
        self._update_checker.update_available.connect(self._on_update_found)
        self._update_checker.no_update.connect(self._on_no_update)
        self._update_checker.error.connect(self._on_check_error)
        self._update_checker.start()

    def _on_update_found(self, update_info: dict) -> None:
        from ..widgets.update_dialog import UpdateAvailableDialog

        self._btn_check.setEnabled(True)
        self._btn_check.setText("🔍  Verificar agora")
        version = update_info.get("version", "?")
        self._set_status(f"✓  Nova versão encontrada: v{version}", color=theme.SUCCESS)
        UpdateAvailableDialog(update_info, parent=self).exec()

    def _on_no_update(self) -> None:
        self._btn_check.setEnabled(True)
        self._btn_check.setText("🔍  Verificar agora")
        self._set_status("✓  Você já tem a versão mais recente.", color=theme.SUCCESS)

    def _on_check_error(self, error_msg: str) -> None:
        self._btn_check.setEnabled(True)
        self._btn_check.setText("🔍  Tentar novamente")
        self._set_status(f"⚠  Erro ao verificar: {error_msg}", color=theme.DANGER)

    def _set_status(self, text: str, color: str | None) -> None:
        self._status_label.setText(text)
        fg = color if color else theme.PANEL_TEXT_MUTED
        self._status_label.setStyleSheet(
            f"background: transparent; font-size: 10pt; font-weight: 700; color: {fg};"
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
            f"QPushButton:pressed {{ background: {theme.PANEL_NEON_PRIMARY}; }}"
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
        )
