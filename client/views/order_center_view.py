"""Central de pedidos com listas operacionais, faturamento e acesso ao PDF."""

import os
import webbrowser
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QObject, QParallelAnimationGroup,
    QPropertyAnimation, QThread, Qt, Signal,
)
from PySide6.QtGui import QColor, QFontMetrics, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..widgets.sortable_item import SortableItem
from ..core.dialogs import apply_message_box_theme
from ..core.datetime_utils import (
    format_date as _format_date,
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)
from ..core.resolution import res
from ..services.pdf_generator import HAS_REPORTLAB, generate_pdf
from .requisition_form import _run_in_thread


_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_METRIC_ICON_FILES = {
    "pedidos_aguardando_recebimento": "aguardando_recebimento.png",
    "pedidos_em_producao": "pedidos_em_producao.png",
    "pedidos_faturados": "pedidos_concluidos.png",
    "pedidos_cancelados": "pedidos_cancelados.png",
    "pedidos_atrasados": "pedidos_atrasados.png",
    "tempo_medio_producao_segundos": "tempo_medio_producao.png",
}

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_SEND = "ENVIADA"


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
    card.setObjectName("orderCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#orderCenterCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _metric_icon_path(key: str) -> Path | None:
    filename = _METRIC_ICON_FILES.get(key)
    if not filename:
        return None
    path = _ICON_DIR / filename
    return path if path.exists() else None


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


def _format_duration(seconds: object) -> str:
    if seconds in (None, "", "-"):
        return "-"
    try:
        total_seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return "-"

    if total_seconds < 60:
        return f"{total_seconds}s"

    minutes, _ = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts[:2]) or "0m"


def _format_waiting_minutes(minutes: object) -> str:
    try:
        total_minutes = max(0, int(minutes))
    except (TypeError, ValueError):
        return "-"

    if total_minutes < 60:
        return f"{total_minutes} min"

    hours, remaining = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining:02d}m"

    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}h"


def _build_production_note(action: str, destination: str) -> str:
    destination_text = str(destination or "").strip()
    return "|".join([PROD_NOTE_PREFIX, action, destination_text])


class OrderCenterWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.get_order_center())
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class OrderCenterView(QWidget):
    open_requisition = Signal(int)
    guide_requested  = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._rows: dict[str, list[dict]] = {
            "aguardando_recebimento": [],
            "em_producao": [],
            "faturados": [],
            "cancelados": [],
            "atrasados": [],
        }
        self._metric_labels: dict[str, QLabel] = {}
        self._tables: dict[str, QTableWidget] = {}
        self._section_cards: dict = {}
        # Filtros: chaves ativas = tabelas visíveis. Persiste entre refreshes.
        self._active_sections: set[str] = {
            "aguardando_recebimento", "em_producao",
            "faturados", "cancelados", "atrasados",
        }
        self._filter_chips: dict[str, QPushButton] = {}
        self._sections_container: QWidget | None = None
        self._anim_group: QParallelAnimationGroup | None = None
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale
        page_bg = theme.CONTENT_BG
        self.setObjectName("orderCenterView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#orderCenterView {{ background:{page_bg}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel("Central de Pedidos")
        title.setStyleSheet(
            f"font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Acompanhamento operacional dos pedidos por etapa, ritmo e pendências da produção."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

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
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        right_col.addWidget(info_card)
        right_col.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)

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
        self.btn_guide.clicked.connect(self.guide_requested)
        right_col.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        header.addLayout(right_col)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        root.addWidget(self.error_label)

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{page_bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(
            f"background:{page_bg}; border:none;"
        )
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("orderCenterContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_content.setStyleSheet(
            f"QWidget#orderCenterContent {{ background:{page_bg}; }}"
        )
        self._page_scroll.setWidget(self._page_content)
        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_aguardando_recebimento", theme.WARNING, "Aguardando Recebimento", "Pedidos pendentes de confirmação da produção."),
            ("pedidos_em_producao", theme.PRIMARY, "Pedidos em Produção", "Ordens que já entraram na esteira produtiva."),
            ("pedidos_faturados", theme.STATUS_COLORS.get("faturado", theme.SUCCESS), "Pedidos Faturados", "Pedidos faturados e disponíveis para consulta."),
            ("pedidos_cancelados", theme.DANGER, "Pedidos Cancelados", "Cancelamentos registrados na operação."),
            ("pedidos_atrasados", theme.DANGER, "Pedidos Atrasados", "Pedidos com prazo vencido e ainda abertos."),
            ("tempo_medio_producao_segundos", theme.BORDER_COLOR, "Tempo Médio de Produção", "Indicador médio de conclusão da produção."),
        ]
        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                index // 4,
                index % 4,
            )

        # ── Barra de filtros ──────────────────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(max(6, int(8 * s)))
        filter_bar.setContentsMargins(0, 0, 0, 0)

        filter_lbl = QLabel("MOSTRAR:")
        filter_lbl.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
        )
        filter_bar.addWidget(filter_lbl)

        chip_defs = [
            ("aguardando_recebimento", "Aguardando"),
            ("em_producao",            "Em Produção"),
            ("faturados",              "Faturados"),
            ("cancelados",             "Cancelados"),
            ("atrasados",              "Atrasados"),
        ]
        for key, label in chip_defs:
            chip = QPushButton(label)
            chip.setCheckable(True)
            chip.setChecked(key in self._active_sections)
            chip.setFixedHeight(max(28, int(32 * s)))
            chip.setStyleSheet(self._chip_style(s))
            chip.toggled.connect(lambda _checked, k=key: self._on_chip_toggled(k, _checked))
            filter_bar.addWidget(chip)
            self._filter_chips[key] = chip

        filter_bar.addStretch()

        self._btn_apply_filter = QPushButton("APLICAR")
        self._btn_apply_filter.setFixedHeight(max(28, int(32 * s)))
        self._btn_apply_filter.setStyleSheet(_primary_action_btn_style(s))
        self._btn_apply_filter.clicked.connect(self._apply_section_filter)
        filter_bar.addWidget(self._btn_apply_filter)

        self._btn_reset_filter = QPushButton("TODOS")
        self._btn_reset_filter.setFixedHeight(max(28, int(32 * s)))
        self._btn_reset_filter.setStyleSheet(_flat_secondary_btn_style(s))
        self._btn_reset_filter.clicked.connect(self._reset_filter)
        filter_bar.addWidget(self._btn_reset_filter)

        layout.addLayout(filter_bar)

        # ── Pré-constrói as seções (ficam no cache; visibilidade gerida) ──
        self._build_section("Pedidos aguardando recebimento", "aguardando_recebimento")
        self._build_section("Pedidos em produção",             "em_producao")
        self._build_section("Pedidos faturados",               "faturados", pdf_action=True)
        self._build_section("Pedidos cancelados",              "cancelados")
        self._build_section("Pedidos atrasados",               "atrasados")

        # ── Container dinâmico das seções ────────────────────────────────
        self._sections_container = QWidget()
        self._sections_container.setObjectName("sectionsContainer")
        self._sections_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sections_container.setStyleSheet(
            f"QWidget#sectionsContainer {{ background:{page_bg}; }}"
        )
        layout.addWidget(self._sections_container)
        layout.addStretch()

        self._rebuild_sections_layout(animate=False)

    # ── Chip style ───────────────────────────────────────────────────────────
    def _chip_style(self, scale: float) -> str:
        fs = max(8, int(9 * scale))
        return (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_MEDIUM};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:999px;"
            f"  padding:4px 14px; font-size:{fs}pt; font-weight:700; outline:none;"
            f"}}"
            f"QPushButton:hover {{ border-color:{_rgba(theme.PRIMARY, 80)}; color:{theme.TEXT_DARK}; }}"
            f"QPushButton:checked {{"
            f"  background:{theme.PRIMARY}; color:#FFFFFF; border-color:{theme.PRIMARY};"
            f"}}"
            f"QPushButton:checked:hover {{ background:{theme.PRIMARY_HOVER}; border-color:{theme.PRIMARY_HOVER}; }}"
        )

    # ── Lógica de filtros ─────────────────────────────────────────────────────
    def _on_chip_toggled(self, key: str, checked: bool):
        """Registra intenção do usuário mas NÃO aplica ainda (só ao clicar Aplicar)."""
        # Não impede que todos sejam desmarcados — o Aplicar exige ao menos 1
        pass

    def _apply_section_filter(self):
        """Lê os chips marcados e reconstrói o layout com animação."""
        selected = {k for k, chip in self._filter_chips.items() if chip.isChecked()}
        if not selected:
            # Garante ao menos 1 seção visível
            for chip in self._filter_chips.values():
                chip.setChecked(True)
            selected = set(self._active_sections)
        if selected == self._active_sections:
            # Sem mudança real — apenas garante layout correto
            self._rebuild_sections_layout(animate=False)
            return
        self._active_sections = selected
        self._rebuild_sections_layout(animate=True)

    def _reset_filter(self):
        """Marca todos os chips e aplica."""
        for chip in self._filter_chips.values():
            chip.setChecked(True)
        self._active_sections = set(self._filter_chips.keys())
        self._rebuild_sections_layout(animate=True)

    # ── Reconstrução do layout ────────────────────────────────────────────────
    def _rebuild_sections_layout(self, animate: bool = True):
        """
        Reconstrói o QGridLayout do container com as seções ativas.
        Distribui em 2 colunas; última seção ímpar ocupa largura total.
        """
        if self._sections_container is None:
            return

        s = self.scale
        gap = max(12, int(16 * s))

        # Remove layout antigo sem destruir os widgets (reparent pra None)
        old_layout = self._sections_container.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)  # type: ignore[arg-type]
                sub = item.layout()
                if sub is not None:
                    while sub.count():
                        si = sub.takeAt(0)
                        sw = si.widget()
                        if sw is not None:
                            sw.setParent(None)  # type: ignore[arg-type]
            QWidget().setLayout(old_layout)  # descarta layout

        section_order = [
            "aguardando_recebimento", "em_producao",
            "faturados", "cancelados", "atrasados",
        ]
        visible = [k for k in section_order if k in self._active_sections]

        grid = QGridLayout(self._sections_container)
        grid.setHorizontalSpacing(gap)
        grid.setVerticalSpacing(gap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for i, key in enumerate(visible):
            card = self._section_cards[key]
            row_idx = i // 2
            col_idx = i % 2
            # Última item ímpar → span 2 colunas
            if i == len(visible) - 1 and len(visible) % 2 == 1:
                grid.addWidget(card, row_idx, 0, 1, 2)
            else:
                grid.addWidget(card, row_idx, col_idx)
            card.show()

        # Esconde cards que não estão na seleção
        for key, card in self._section_cards.items():
            if key not in self._active_sections:
                card.hide()

        if animate:
            self._animate_sections_in(visible)

    def _animate_sections_in(self, keys: list[str]):
        """Anima a entrada de cada seção visível com slide-down (height)."""
        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        group = QParallelAnimationGroup(self)
        for key in keys:
            card = self._section_cards[key]
            natural_h = card.sizeHint().height() or max(280, int(320 * self.scale))
            anim = QPropertyAnimation(card, b"maximumHeight", self)
            anim.setDuration(220)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0)
            anim.setEndValue(natural_h)
            group.addAnimation(anim)
            card.setMaximumHeight(0)
        group.finished.connect(lambda: self._remove_height_constraint(keys))
        self._anim_group = group
        group.start()

    def _remove_height_constraint(self, keys: list[str]):
        """Remove o limite de altura após animação para não travar redimensionamento."""
        for key in keys:
            card = self._section_cards.get(key)
            if card is not None:
                card.setMaximumHeight(16_777_215)  # QWIDGETSIZE_MAX

    def _build_metric_card(
        self,
        color: str,
        title_text: str,
        helper_text: str,
        key: str,
    ) -> QFrame:
        s = self.scale
        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value = QLabel("-")
        value.setStyleSheet(
            f"font-size:{max(20, int(26 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )
        value.setWordWrap(True)

        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper = QLabel(helper_text)
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(color, 235)}, stop:0.5 {_rgba(color, 155)}, stop:1 {_rgba(color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(max(10, int(12 * s)))
        header_row.addWidget(value, 1, Qt.AlignmentFlag.AlignTop)

        icon_label = self._build_metric_icon_label(key)
        if icon_label is not None:
            header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addStretch()
        layout.addWidget(accent_line)
        self._metric_labels[key] = value
        return card

    def _build_metric_icon_label(self, key: str) -> QLabel | None:
        icon_path = _metric_icon_path(key)
        if icon_path is None:
            return None

        pixmap = QPixmap(str(icon_path))
        if pixmap.isNull():
            return None

        size = max(52, int(62 * self.scale))
        label = QLabel()
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background:transparent; border:none;")
        label.setPixmap(
            pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return label

    def _build_section(
        self,
        title_text: str,
        key: str,
        pdf_action: bool = False,
    ) -> QFrame:
        s = self.scale
        section_meta = {
            "aguardando_recebimento": (
                "Pedidos aguardando retorno e confirmação da produção.",
                theme.WARNING,
            ),
            "em_producao": (
                "Ordens em andamento com registro de recebimento na fábrica.",
                theme.PRIMARY,
            ),
            "faturados": (
                "Pedidos faturados com consulta rápida do PDF e histórico da operação.",
                theme.STATUS_COLORS.get("faturado", theme.SUCCESS),
            ),
            "cancelados": (
                "Histórico de cancelamentos para consulta rápida da operação.",
                theme.DANGER,
            ),
            "atrasados": (
                "Pedidos fora do prazo para acompanhamento imediato.",
                theme.BORDER_COLOR,
            ),
        }
        subtitle_text, accent_color = section_meta[key]

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
        layout.setSpacing(max(10, int(12 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        layout.addWidget(accent)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(max(2, int(3 * s)))
        title = QLabel(title_text)
        title.setStyleSheet(
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)

        btn_open = QPushButton("ABRIR PEDIDO")
        btn_open.setFixedHeight(max(34, int(38 * s)))
        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_open.clicked.connect(lambda: self._open_selected(key))
        title_row.addWidget(btn_open)

        if pdf_action:
            btn_pdf = QPushButton("VER PDF")
            btn_pdf.setFixedHeight(max(34, int(38 * s)))
            btn_pdf.setStyleSheet(_primary_action_btn_style(s))
            btn_pdf.clicked.connect(lambda _checked=False, section=key: self._open_selected_pdf(section))
            title_row.addWidget(btn_pdf)
        if key == "cancelados":
            btn_restore = QPushButton("RETORNAR STATUS")
            btn_restore.setFixedHeight(max(34, int(38 * s)))
            btn_restore.setStyleSheet(_flat_secondary_btn_style(s))
            btn_restore.clicked.connect(self._reopen_canceled_selected)
            title_row.addWidget(btn_restore)

        layout.addLayout(title_row)

        previous_avg_label = getattr(self, "avg_finished_label", None)
        if pdf_action:
            self.avg_finished_label = QLabel("Tempo médio: -")
            self.avg_finished_label.setProperty("muted", "1")
            self.avg_finished_label.setStyleSheet(
                f"font-size:{max(7, int(8 * s))}pt; font-weight:600;"
            )
            layout.addWidget(self.avg_finished_label)
            if key != "faturados":
                self.avg_finished_label.hide()
                if previous_avg_label is not None:
                    self.avg_finished_label = previous_avg_label

        table = self._create_table_for_section(key)
        self._tables[key] = table
        layout.addWidget(table, 1)
        self._section_cards[key] = card
        # Não adiciona ao layout aqui — o container dinâmico gerencia a posição
        return card

    def _create_table_for_section(self, key: str) -> QTableWidget:
        headers_by_section = {
            "aguardando_recebimento": ["PED", "CLIENTE", "VENDEDOR", "ENTREGA", "AGUARDANDO"],
            "em_producao": ["PED", "CLIENTE", "VENDEDOR", "RECEBIDO EM", "DESTINO"],
            "faturados": ["PED", "CLIENTE", "FATURADO EM", "FINALIZADO EM", "DESTINO"],
            "cancelados": ["PED", "CLIENTE", "VENDEDOR", "CANCELADO EM", "MOTIVO"],
            "atrasados": ["PED", "CLIENTE", "ENTREGA", "ATRASO", "STATUS"],
        }

        stretch_columns = {
            "aguardando_recebimento": {1, 2},
            "em_producao": {1, 2},
            "faturados": {1},
            "cancelados": {1, 4},
            "atrasados": {1},
        }

        headers = headers_by_section[key]
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.doubleClicked.connect(lambda index, section=key: self._open_row(section, index.row()))

        s = self.scale
        header = table.horizontalHeader()
        for col in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if col in stretch_columns[key]
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(col, mode)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * s)))
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        if key == "atrasados":
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(4, max(210, int(240 * s)))
            table.verticalHeader().setDefaultSectionSize(max(36, int(42 * s)))

        table.setSortingEnabled(True)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  alternate-background-color:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QHeaderView::section:hover {{ background:{theme.PRIMARY_HOVER}; }}"
            f"QTableWidget::item {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
        )
        # Sobrescreve a paleta do sistema (Windows ignora QSS em QTableView items).
        # QPalette.Base = fundo das células normais.
        # QPalette.AlternateBase = fundo das linhas alternadas.
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
        table.setMinimumHeight(max(220, int(240 * s)))
        apply_smooth_scroll(table)
        return table

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()
        worker = OrderCenterWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.error_label.setText(f"Não foi possível carregar a central de pedidos.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta inválida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        for key, label in self._metric_labels.items():
            value = stats.get(key)
            if key == "tempo_medio_producao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        current = _parse_datetime(payload.get("generated_at")) or local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")
        if hasattr(self, "avg_finished_label"):
            self.avg_finished_label.setText(
                f"Tempo médio: {_format_duration(stats.get('tempo_medio_producao_segundos'))}"
            )

        for key in self._rows:
            rows = payload.get(key) or []
            self._rows[key] = rows if isinstance(rows, list) else []
            self._fill_section_table(key)

    def _fill_section_table(self, key: str):
        table = self._tables[key]
        table.clearSpans()
        table.setRowCount(0)
        rows = self._rows.get(key, [])

        if not rows:
            self._set_empty_message(table, "Nenhum pedido encontrado nesta etapa.")
            return

        table.setSortingEnabled(False)
        for row_data in rows:
            if not isinstance(row_data, dict):
                continue

            row = table.rowCount()
            table.insertRow(row)

            ped_raw = row_data.get("ped_number")
            try:
                ped_sort = int(ped_raw)
            except (TypeError, ValueError):
                ped_sort = 0

            if key == "aguardando_recebimento":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_date(row_data.get("delivery_date")),
                    _format_waiting_minutes(row_data.get("waiting_minutes")),
                ]
                sort_keys = [ped_sort, None, None,
                             str(row_data.get("delivery_date") or ""),
                             row_data.get("waiting_minutes") or 0]
            elif key == "em_producao":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_datetime(row_data.get("received_at")),
                    str(row_data.get("destination") or "-"),
                ]
                sort_keys = [ped_sort, None, None,
                             str(row_data.get("received_at") or ""), None]
            elif key == "faturados":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    _format_datetime(row_data.get("invoiced_at")),
                    _format_datetime(row_data.get("finished_at")),
                    str(row_data.get("destination") or "-"),
                ]
                sort_keys = [ped_sort, None,
                             str(row_data.get("invoiced_at") or ""),
                             str(row_data.get("finished_at") or ""),
                             None]
            elif key == "cancelados":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_datetime(row_data.get("canceled_at")),
                    str(row_data.get("cancel_reason") or "-"),
                ]
                sort_keys = [ped_sort, None, None,
                             str(row_data.get("canceled_at") or ""), None]
            else:  # atrasados
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    _format_date(row_data.get("delivery_date")),
                    f"{row_data.get('delay_days') or 0} dia(s)",
                    str(row_data.get("status") or "-"),
                ]
                sort_keys = [ped_sort, None,
                             str(row_data.get("delivery_date") or ""),
                             row_data.get("delay_days") or 0,
                             None]

            for col, value in enumerate(values):
                if key == "atrasados" and col == 4:
                    status = str(row_data.get("status") or "")
                    badge = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    color_map = {
                        "em_andamento": theme.PRIMARY_HOVER,
                        "aguardando_recebimento": theme.WARNING,
                        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
                        "aguardando_faturamento": theme.STATUS_COLORS.get("aguardando_faturamento", theme.WARNING),
                        "em_producao": theme.PRIMARY,
                        "faturado": theme.STATUS_COLORS.get("faturado", theme.SUCCESS),
                        "cancelada": theme.DANGER,
                    }
                    color = color_map.get(status, theme.BORDER_COLOR)
                    badge.setStyleSheet(
                        f"background:{_rgba(color, 30)}; color:{color}; border-radius:999px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(row, col, badge)
                else:
                    sk = sort_keys[col] if col < len(sort_keys) else None
                    item = SortableItem(value, sort_key=sk) if sk is not None else QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, col, item)
        table.setSortingEnabled(True)

    def _set_empty_message(self, table: QTableWidget, message: str):
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(theme.TEXT_MEDIUM))
        table.setItem(0, 0, item)

    def _selected_row(self, key: str) -> dict | None:
        table = self._tables[key]
        row = table.currentRow()
        rows = self._rows.get(key, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _open_row(self, key: str, row_index: int):
        rows = self._rows.get(key, [])
        if 0 <= row_index < len(rows):
            self.open_requisition.emit(int(rows[row_index]["id"]))

    def _open_selected(self, key: str):
        row = self._selected_row(key)
        if not row:
            QMessageBox.information(self, "Central de pedidos", "Selecione um pedido primeiro.")
            return
        self.open_requisition.emit(int(row["id"]))

    def _open_selected_pdf(self, key: str):
        row = self._selected_row(key)
        if not row:
            QMessageBox.information(
                self,
                "Central de pedidos",
                "Selecione um pedido para visualizar o PDF.",
            )
            return

        req_id = int(row["id"])
        thread, worker = _run_in_thread(
            api.get_requisition,
            req_id,
            on_result=self._open_pdf_for_requisition,
            on_error=lambda msg: QMessageBox.critical(self, "Central de pedidos", msg),
        )
        self._threads.append((thread, worker))

    def _reopen_canceled_selected(self):
        row = self._selected_row("cancelados")
        if not row:
            QMessageBox.information(
                self,
                "Central de pedidos",
                "Selecione um pedido cancelado primeiro.",
            )
            return

        ped_number = str(row.get("ped_number") or "").strip() or "sem PED"
        destination = str(row.get("destination") or "").strip()

        box = QMessageBox(self)
        box.setWindowTitle("Retornar Status")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Como deseja retornar o pedido {ped_number}?")
        if destination:
            box.setInformativeText(f"Destino de produção registrado: {destination}.")
        else:
            box.setInformativeText(
                "Este pedido não possui destino de produção registrado para voltar em aguardando recebimento."
            )

        btn_edit = box.addButton("Nova requisição (editar)", QMessageBox.ButtonRole.AcceptRole)
        btn_receipt = box.addButton("Aguardando recebimento", QMessageBox.ButtonRole.ActionRole)
        btn_close = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(box)
        # Ajusta as larguras pelo texto real para evitar truncamento em qualquer escala.
        metrics = QFontMetrics(btn_edit.font())
        horizontal_padding = max(44, int(52 * self.scale))
        btn_edit_w = max(170, metrics.horizontalAdvance(btn_edit.text()) + horizontal_padding)
        btn_receipt_w = max(170, metrics.horizontalAdvance(btn_receipt.text()) + horizontal_padding)
        btn_close_w = max(120, metrics.horizontalAdvance(btn_close.text()) + horizontal_padding)
        btn_edit.setMinimumWidth(btn_edit_w)
        btn_receipt.setMinimumWidth(btn_receipt_w)
        btn_close.setMinimumWidth(btn_close_w)
        row_padding = max(88, int(96 * self.scale))
        box.setMinimumWidth(max(620, btn_edit_w + btn_receipt_w + btn_close_w + row_padding))
        btn_receipt.setEnabled(bool(destination))
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_edit:
            self._apply_reopen_canceled_status(
                row,
                new_status="em_andamento",
                note="",
                success_message=f"Pedido {ped_number} voltou para nova requisição.",
            )
        elif clicked == btn_receipt:
            if not destination:
                QMessageBox.warning(
                    self,
                    "Central de pedidos",
                    "Não foi possível retornar para aguardando recebimento sem destino de produção.",
                )
                return
            self._apply_reopen_canceled_status(
                row,
                new_status="aguardando_recebimento",
                note=_build_production_note(PROD_SEND, destination),
                success_message=f"Pedido {ped_number} voltou para aguardando recebimento em {destination}.",
            )
        elif clicked == btn_close:
            return

    def _apply_reopen_canceled_status(
        self,
        row: dict,
        *,
        new_status: str,
        note: str,
        success_message: str,
    ):
        req_id = int(row["id"])
        thread, worker = _run_in_thread(
            api.update_status,
            req_id,
            new_status,
            note,
            on_result=lambda _req: self._after_reopen_canceled(success_message),
            on_error=lambda msg: QMessageBox.critical(self, "Central de pedidos", msg),
        )
        self._threads.append((thread, worker))

    def _after_reopen_canceled(self, success_message: str):
        QMessageBox.information(self, "Central de pedidos", success_message)
        self.refresh()

    def _apply_table_style(self, table: QTableWidget) -> None:
        s = self.scale
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.CARD_BG};"
            f"  alternate-background-color:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK};"
            f"  border-radius:14px; gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:{theme.PRIMARY}; color:#fff; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(theme.PRIMARY, 18)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.TABLE_ALT_ROW}; color:{theme.TEXT_DARK}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(theme.PRIMARY, 18)}; color:{theme.TEXT_DARK}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.CARD_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.TABLE_ALT_ROW))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PRIMARY, 40)))
        table.setPalette(pal)

    def apply_theme(self) -> None:
        s = self.scale
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#orderCenterView {{ background:{bg}; }}")
        self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#orderCenterContent {{ background:{bg}; }}")
        if self._sections_container is not None:
            self._sections_container.setStyleSheet(
                f"QWidget#sectionsContainer {{ background:{bg}; }}"
            )
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self._btn_apply_filter.setStyleSheet(_primary_action_btn_style(s))
        self._btn_reset_filter.setStyleSheet(_flat_secondary_btn_style(s))
        chip_style = self._chip_style(s)
        for chip in self._filter_chips.values():
            chip.setStyleSheet(chip_style)
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        for table in self._tables.values():
            self._apply_table_style(table)

    def _open_pdf_for_requisition(self, req: dict):
        folder = res.pdf_folder.strip()
        if not folder:
            QMessageBox.warning(
                self,
                "Central de pedidos",
                "Defina a pasta de PDFs nas configurações antes de abrir o arquivo.",
            )
            return

        if not HAS_REPORTLAB:
            QMessageBox.warning(
                self,
                "Central de pedidos",
                "A geração de PDF não está disponível neste ambiente.",
            )
            return

        client = {
            "name": req.get("client_name"),
            "phone": req.get("phone"),
        }
        canvas = (req.get("canvas") or {}).get("json_data") or "{}"

        try:
            pdf_path = generate_pdf(req, client, req.get("obs") or "", folder, canvas)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Central de pedidos",
                f"Não foi possível gerar o PDF deste pedido.\n\n{exc}",
            )
            return

        try:
            if os.name == "nt":
                os.startfile(pdf_path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{pdf_path}")
        except Exception as exc:
            QMessageBox.information(
                self,
                "Central de pedidos",
                f"PDF gerado em:\n{pdf_path}\n\nNão foi possível abrir automaticamente: {exc}",
            )
