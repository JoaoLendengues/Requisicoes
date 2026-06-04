from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import theme
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
)
from ..widgets.smooth_scroll import SmoothScrollArea


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.PANEL_SHADOW)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


def _make_card(scale: float, radius: int = 18) -> QFrame:
    card = QFrame()
    card.setObjectName("systemUpdatesCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card")
    card.setStyleSheet(f"QFrame#systemUpdatesCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _section(title: str, scale: float) -> QLabel:
    label = QLabel(title)
    label.setStyleSheet(
        f"background:transparent; font-size:{max(10, int(12 * scale))}pt; "
        f"font-weight:800; padding-top:4px;"
    )
    return label


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedHeight(4)
    sep.setProperty("theme_bg", "separator")
    sep.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    sep.setStyleSheet("border:none; border-radius:2px;")
    return sep


def _secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


class SystemUpdatesView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._update_checker = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("systemUpdatesView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#systemUpdatesView {{ background:{page_bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)), max(18, int(24 * s)), 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Atualizações do Sistema")
        title.setStyleSheet(
            f"background:transparent; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Verifique novas versões do aplicativo e acompanhe o status da atualização."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"background:transparent; font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        info_card = _make_card(s, radius=max(16, int(18 * s)))
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(
            max(14, int(16 * s)),
            max(10, int(12 * s)),
            max(14, int(16 * s)),
            max(10, int(12 * s)),
        )
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
        self.updated_label = QLabel("Central de atualização do aplicativo")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)
        header.addWidget(info_card)
        root.addLayout(header)

        root.addSpacing(max(14, int(18 * s)))

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{page_bg}; }}")

        self._page_content = QWidget()
        self._page_content.setObjectName("systemUpdatesContainer")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(f"QWidget#systemUpdatesContainer {{ background:{page_bg}; }}")
        self._page_scroll.setWidget(self._page_content)
        root.addWidget(self._page_scroll, 1)

        content = QVBoxLayout(self._page_content)
        content.setContentsMargins(0, 0, 0, max(18, int(22 * s)))
        content.setSpacing(max(14, int(18 * s)))

        card = _make_card(s)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            max(18, int(22 * s)),
            max(16, int(20 * s)),
            max(18, int(22 * s)),
            max(18, int(22 * s)),
        )
        card_layout.setSpacing(max(10, int(12 * s)))
        content.addWidget(card)
        content.addStretch()

        card_layout.addWidget(_section("Atualizações do Sistema", s))
        card_layout.addWidget(_separator())

        from ..version import CURRENT_VERSION as _CURRENT_VERSION

        version_row = QHBoxLayout()
        version_row.setSpacing(max(8, int(10 * s)))
        self._version_label = QLabel(f"Versão atual: v{_CURRENT_VERSION}")
        self._version_label.setProperty("muted", "1")
        self._version_label.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        version_row.addWidget(self._version_label)
        version_row.addStretch()
        self.btn_check_update = QPushButton("Verificar atualizações")
        self.btn_check_update.setFixedHeight(max(38, int(44 * s)))
        self.btn_check_update.setStyleSheet(_secondary_btn_style(s))
        self.btn_check_update.clicked.connect(self._check_updates)
        version_row.addWidget(self.btn_check_update)
        card_layout.addLayout(version_row)

        helper = QLabel(
            "Use esta tela para procurar novas versões. Quando houver uma atualização disponível, "
            "o aplicativo exibirá os detalhes e permitirá iniciar a instalação."
        )
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        card_layout.addWidget(helper)

        self._update_status_label = QLabel("")
        self._update_status_label.setWordWrap(True)
        self._update_status_label.setProperty("muted", "1")
        self._update_status_label.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        card_layout.addWidget(self._update_status_label)

    def refresh(self) -> None:
        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

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
        self._update_status_label.setText(f"Nova versão disponível: v{update_info['version']}")
        self._update_status_label.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt; "
            f"font-weight:600; color:{theme.SUCCESS};"
        )
        UpdateAvailableDialog(update_info, parent=self).exec()

    def _on_no_update(self) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizações")
        self._update_status_label.setText("Você já tem a versão mais recente.")
        self._update_status_label.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt; "
            f"font-weight:600; color:{theme.SUCCESS};"
        )

    def _on_update_check_error(self, error_msg: str) -> None:
        self.btn_check_update.setEnabled(True)
        self.btn_check_update.setText("Verificar atualizações")
        self._update_status_label.setText(f"Erro ao verificar: {error_msg}")
        self._update_status_label.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt; "
            f"font-weight:600; color:{theme.DANGER};"
        )

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#systemUpdatesView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#systemUpdatesContainer {{ background:{bg}; }}")
        self.btn_check_update.setStyleSheet(_secondary_btn_style(s))
