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
from ..core.formatters import format_weight_kg
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
_FULL_WIDTH_SECTION_KEYS = {
    "aguardando_recebimento",
    "em_producao",
    "faturados",
    "cancelados",
}
_TABLE_STRETCH_COLUMNS = {
    "aguardando_recebimento": {1, 2},
    "em_producao": {1, 2, 5, 6, 7, 8},
    "faturados": {1, 2, 6, 7, 8, 9},
    "cancelados": {1, 2, 5},
    "atrasados": {1, 2, 6, 7, 8, 9},
}
_TABLE_LEFT_ALIGN_COLUMNS = {
    "aguardando_recebimento": {1, 2},
    "em_producao": {1, 2, 5, 6, 7, 8},
    "faturados": {1, 2, 6, 7, 8, 9},
    "cancelados": {1, 2, 5},
    "atrasados": {1, 2, 6, 7, 8, 9},
}
_TABLE_MIN_COLUMN_WIDTHS = {
    "aguardando_recebimento": {
        0: 92, 3: 96, 4: 190, 5: 126, 6: 162,
    },
    "em_producao": {
        0: 92, 3: 96, 4: 158, 9: 126,
    },
    "faturados": {
        0: 92, 3: 96, 4: 158, 5: 158, 10: 156,
    },
    "cancelados": {
        0: 92, 3: 96, 4: 158, 5: 280,
    },
    "atrasados": {
        0: 92, 3: 96, 4: 132, 5: 112, 10: 188,
    },
}


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


def _make_card(
    scale: float,
    background: str | None = None,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    """Card com o mesmo design "neon" do Painel Gerencial e Nova Requisição:
    gradient escuro suave + borda neon + sombra com cor de painel.
    """
    card = QFrame()
    card.setObjectName("orderCenterCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    accent = border_color or theme.PANEL_BORDER_SOFT
    card.setStyleSheet(_order_card_qss(radius, accent))
    _apply_shadow(card, blur=max(28, int(34 * scale)), y_offset=max(4, int(5 * scale)), alpha=56)
    return card


def _order_card_qss(radius: int, accent_color: str | None = None) -> str:
    """QSS do card neon — separado para que apply_theme possa reaplicar
    com a paleta corrente ao trocar claro/escuro."""
    accent = accent_color or theme.PANEL_BORDER_SOFT
    return (
        f"QFrame#orderCenterCard {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {theme.PANEL_CARD_BG_START},"
        f"    stop:0.55 {theme.PANEL_CARD_BG_MID},"
        f"    stop:1 {theme.PANEL_CARD_BG_END});"
        f"  border:1px solid {_rgba(accent, 126)};"
        f"  border-radius:{radius}px;"
        f"}}"
        f"QFrame#orderCenterCard:hover {{ border-color:{_rgba(accent, 210)}; }}"
    )


def _order_table_qss(scale: float) -> str:
    """QSS das tabelas das seções — mesma identidade neon do Painel Gerencial."""
    header_fg = theme.TEXT_WHITE if not theme.is_dark else theme.PANEL_TEXT_PRIMARY
    return (
        f"QTableWidget {{"
        f"  border:none; outline:none; background:{theme.PANEL_SURFACE_BG};"
        f"  alternate-background-color:{theme.PANEL_SURFACE_ALT};"
        f"  color:{theme.PANEL_TEXT_PRIMARY}; border-radius:14px;"
        f"  gridline-color:transparent; font-size:{max(8, int(9 * scale))}pt;"
        f"}}"
        f"QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {theme.PANEL_TABLE_HEADER_START},"
        f"    stop:1 {theme.PANEL_TABLE_HEADER_END});"
        f"  color:{header_fg}; padding:9px 10px;"
        f"  font-weight:800; font-size:{max(7, int(8 * scale))}pt; border:none;"
        f"}}"
        f"QHeaderView::section:hover {{ background:{theme.PANEL_NEON_SECONDARY}; }}"
        f"QTableWidget::item {{"
        f"  background:{theme.PANEL_SURFACE_BG}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"  padding:7px 6px; border-bottom:1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 26)};"
        f"}}"
        f"QTableWidget::item:alternate {{"
        f"  background:{theme.PANEL_SURFACE_ALT}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
        f"QTableWidget::item:selected {{"
        f"  background:{_rgba(theme.PANEL_NEON_PRIMARY, 56)};"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
    )


def _apply_order_table_palette(table) -> None:
    """Atualiza a QPalette da tabela — necessário no Windows pois o Qt
    ignora QSS em algumas regiões do QTableView (linhas alternadas)."""
    pal = table.palette()
    pal.setColor(QPalette.ColorRole.Base, QColor(theme.PANEL_SURFACE_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.PANEL_SURFACE_ALT))
    pal.setColor(QPalette.ColorRole.Text, QColor(theme.PANEL_TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_rgba(theme.PANEL_NEON_PRIMARY, 60)))
    table.setPalette(pal)
    table.viewport().setAutoFillBackground(True)


def _metric_icon_path(key: str) -> Path | None:
    filename = _METRIC_ICON_FILES.get(key)
    if not filename:
        return None
    path = _ICON_DIR / filename
    return path if path.exists() else None


def _flat_secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


def _primary_action_btn_style(scale: float) -> str:
    return theme.primary_btn_style(scale)


def _danger_action_btn_style(scale: float) -> str:
    return theme.danger_btn_style(scale)


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


def _format_waiting_label(minutes: object) -> str:
    waiting = _format_waiting_minutes(minutes)
    if waiting == "-":
        return "-"
    return f"Há {waiting}"


def _format_weight(value: object) -> str:
    return format_weight_kg(value)


def _format_deadline_met(value: object) -> str:
    if value is True:
        return "SIM"
    if value is False:
        return "NÃO"
    return "-"


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
        self._metric_title_labels: dict[str, QLabel] = {}
        self._metric_helper_labels: dict[str, QLabel] = {}
        self._section_title_labels: list[QLabel] = []
        self._section_subtitle_labels: list[QLabel] = []
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
            f"background:transparent; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Acompanhamento operacional dos pedidos por etapa, ritmo e pendências da produção."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"background:transparent; font-size:{max(8, int(10 * s))}pt;"
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
            ("pedidos_faturados", theme.STATUS_COLORS.get("faturado", theme.SUCCESS), "Pedidos Finalizados", "Pedidos concluídos na produção e disponíveis para consulta."),
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
            ("faturados",              "Finalizados"),
            ("cancelados",             "Cancelados"),
            ("atrasados",              "Atrasados"),
        ]
        for key, label in chip_defs:
            chip = QPushButton(label)
            chip.setCheckable(True)
            chip.setChecked(key in self._active_sections)
            chip.setFixedHeight(max(32, int(36 * s)))
            chip.setStyleSheet(self._chip_style(s))
            chip.toggled.connect(lambda _checked, k=key: self._on_chip_toggled(k, _checked))
            filter_bar.addWidget(chip)
            self._filter_chips[key] = chip

        filter_bar.addStretch()

        self._btn_apply_filter = QPushButton("APLICAR")
        self._btn_apply_filter.setFixedHeight(max(34, int(38 * s)))
        self._btn_apply_filter.setStyleSheet(_primary_action_btn_style(s))
        self._btn_apply_filter.clicked.connect(self._apply_section_filter)
        filter_bar.addWidget(self._btn_apply_filter)

        self._btn_reset_filter = QPushButton("TODOS")
        self._btn_reset_filter.setFixedHeight(max(34, int(38 * s)))
        self._btn_reset_filter.setStyleSheet(_flat_secondary_btn_style(s))
        self._btn_reset_filter.clicked.connect(self._reset_filter)
        filter_bar.addWidget(self._btn_reset_filter)

        self._btn_clear_filter = QPushButton("DESMARCAR TODOS")
        self._btn_clear_filter.setFixedHeight(max(34, int(38 * s)))
        self._btn_clear_filter.setStyleSheet(_danger_action_btn_style(s))
        self._btn_clear_filter.setToolTip("Limpar a seleção atual dos filtros")
        self._btn_clear_filter.clicked.connect(self._clear_filter_selection)
        filter_bar.addWidget(self._btn_clear_filter)

        layout.addLayout(filter_bar)

        # ── Pré-constrói as seções (ficam no cache; visibilidade gerida) ──
        self._build_section("Pedidos aguardando recebimento", "aguardando_recebimento")
        self._build_section("Pedidos em produção",             "em_producao")
        self._build_section("Pedidos finalizados",             "faturados", pdf_action=True)
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
        # Pill total: usa metade da altura fixa do chip.
        # Garante cantos totalmente arredondados em qualquer escala.
        chip_h = max(32, int(36 * scale))
        radius = chip_h // 2
        return (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_MEDIUM};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:{radius}px;"
            f"  padding:6px 16px; font-size:{fs}pt; font-weight:700; outline:none;"
            f"}}"
            f"QPushButton:hover {{ border-color:{_rgba(theme.PRIMARY, 80)}; color:{theme.TEXT_DARK}; border-radius:{radius}px; }}"
            f"QPushButton:checked {{"
            f"  background:{theme.PRIMARY}; color:#FFFFFF; border-color:{theme.PRIMARY}; border-radius:{radius}px;"
            f"}}"
            f"QPushButton:checked:hover {{ background:{theme.PRIMARY_HOVER}; border-color:{theme.PRIMARY_HOVER}; border-radius:{radius}px; }}"
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

    def _clear_filter_selection(self):
        """Desmarca todos os chips para facilitar uma nova seleção manual."""
        for chip in self._filter_chips.values():
            chip.setChecked(False)

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

        row_idx = 0
        col_idx = 0

        for i, key in enumerate(visible):
            card = self._section_cards[key]
            should_span = key in _FULL_WIDTH_SECTION_KEYS or (
                col_idx == 0 and i == len(visible) - 1
            )
            if should_span:
            # Última item ímpar → span 2 colunas
                if col_idx != 0:
                    row_idx += 1
                    col_idx = 0
                grid.addWidget(card, row_idx, 0, 1, 2)
                row_idx += 1
            else:
                grid.addWidget(card, row_idx, col_idx)
                if col_idx == 0:
                    col_idx = 1
                else:
                    col_idx = 0
                    row_idx += 1
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
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        )
        value.setWordWrap(True)

        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"font-size:{max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        )

        helper = QLabel(helper_text)
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
            f"color:{theme.PANEL_TEXT_MUTED};"
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
        self._metric_title_labels[key] = title
        self._metric_helper_labels[key] = helper
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
                "Pedidos finalizados com consulta rápida do PDF e histórico da operação.",
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
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
            f"color:{theme.PANEL_TEXT_MUTED};"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)
        self._section_title_labels.append(title)
        self._section_subtitle_labels.append(subtitle)

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
                f"background:transparent; font-size:{max(7, int(8 * s))}pt; font-weight:600;"
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
            "aguardando_recebimento": ["PEDIDO", "CLIENTE", "VENDEDOR", "PESO", "DATA ENVIO PARA PRODUÇÃO", "PRAZO", "AGUARDANDO RECEBIMENTO"],
            "em_producao": ["PEDIDO", "CLIENTE", "VENDEDOR", "PESO", "RECEBIDO EM", "PRODUÇÃO", "MÁQUINA", "OPERADOR", "AJUDANTE", "PRAZO"],
            "faturados": ["PEDIDO", "CLIENTE", "VENDEDOR", "PESO", "FATURADO EM", "FINALIZADO EM", "PRODUÇÃO", "MÁQUINA", "OPERADOR", "AJUDANTE", "ATENDEU AO PRAZO"],
            "cancelados": ["PEDIDO", "CLIENTE", "VENDEDOR", "PESO", "CANCELADO EM", "MOTIVO DE CANCELAMENTO"],
            "atrasados": ["PEDIDO", "CLIENTE", "VENDEDOR", "PESO", "PRAZO ENTREGA", "ATRASO", "PRODUÇÃO", "MÁQUINA", "OPERADOR", "AJUDANTE", "STATUS"],
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
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * s)))
        header.setMinimumSectionSize(max(86, int(96 * s)))
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        if key == "atrasados":
            table.verticalHeader().setDefaultSectionSize(max(36, int(42 * s)))

        table.setSortingEnabled(True)
        table.setStyleSheet(_order_table_qss(s))
        _apply_order_table_palette(table)
        table.setMinimumHeight(max(320, int(360 * s)))
        apply_smooth_scroll(table)
        self._configure_table_columns(table, key)
        return table

    def _configure_table_columns(self, table: QTableWidget, key: str):
        header = table.horizontalHeader()
        stretch_columns = _TABLE_STRETCH_COLUMNS[key]
        min_widths = _TABLE_MIN_COLUMN_WIDTHS.get(key, {})
        header_metrics = QFontMetrics(header.font())
        header_padding = max(26, int(34 * self.scale))

        for col in range(table.columnCount()):
            if col in stretch_columns:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
                continue

            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            table.resizeColumnToContents(col)
            header_text = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
            header_width = header_metrics.horizontalAdvance(header_text) + header_padding
            minimum_width = int(min_widths.get(col, 0) * self.scale)
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(col, max(table.columnWidth(col), header_width, minimum_width))

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
            self._configure_table_columns(table, key)
            return

        table.setSortingEnabled(False)
        left_align_columns = _TABLE_LEFT_ALIGN_COLUMNS.get(key, set())
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
            try:
                weight_sort = float(row_data.get("weight") or 0.0)
            except (TypeError, ValueError):
                weight_sort = 0.0

            operator_display = ", ".join(
                str(name).strip()
                for name in (row_data.get("operator_names") or [])
                if str(name).strip()
            ) or "-"
            helper_display = ", ".join(
                str(name).strip()
                for name in (row_data.get("helper_names") or [])
                if str(name).strip()
            ) or "-"

            if key == "aguardando_recebimento":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_weight(row_data.get("weight")),
                    _format_datetime(row_data.get("sent_to_production_at")),
                    _format_date(row_data.get("delivery_date")),
                    _format_waiting_label(row_data.get("waiting_minutes")),
                ]
                sort_keys = [
                    ped_sort,
                    None,
                    None,
                    weight_sort,
                    str(row_data.get("sent_to_production_at") or ""),
                    str(row_data.get("delivery_date") or ""),
                    row_data.get("waiting_minutes") or 0,
                ]
            elif key == "em_producao":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_weight(row_data.get("weight")),
                    _format_datetime(row_data.get("received_at")),
                    str(row_data.get("destination") or "-"),
                    str(row_data.get("machine_name") or "-"),
                    operator_display,
                    helper_display,
                    _format_date(row_data.get("delivery_date")),
                ]
                sort_keys = [
                    ped_sort,
                    None,
                    None,
                    weight_sort,
                    str(row_data.get("received_at") or ""),
                    None,
                    None,
                    None,
                    None,
                    str(row_data.get("delivery_date") or ""),
                ]
            elif key == "faturados":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_weight(row_data.get("weight")),
                    _format_datetime(row_data.get("invoiced_at")),
                    _format_datetime(row_data.get("finished_at")),
                    str(row_data.get("destination") or "-"),
                    str(row_data.get("machine_name") or "-"),
                    operator_display,
                    helper_display,
                    _format_deadline_met(row_data.get("deadline_met")),
                ]
                sort_keys = [
                    ped_sort,
                    None,
                    None,
                    weight_sort,
                    str(row_data.get("invoiced_at") or ""),
                    str(row_data.get("finished_at") or ""),
                    None,
                    None,
                    None,
                    None,
                    -1 if row_data.get("deadline_met") is None else int(bool(row_data.get("deadline_met"))),
                ]
            elif key == "cancelados":
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_weight(row_data.get("weight")),
                    _format_datetime(row_data.get("canceled_at")),
                    str(row_data.get("cancel_reason") or "-"),
                ]
                sort_keys = [
                    ped_sort,
                    None,
                    None,
                    weight_sort,
                    str(row_data.get("canceled_at") or ""),
                    None,
                ]
            else:  # atrasados
                values = [
                    str(ped_raw or "-"),
                    str(row_data.get("client_name") or "-"),
                    str(row_data.get("vendor_name") or "-"),
                    _format_weight(row_data.get("weight")),
                    _format_date(row_data.get("delivery_date")),
                    f"{row_data.get('delay_days') or 0} dia(s)",
                    str(row_data.get("destination") or "-"),
                    str(row_data.get("machine_name") or "-"),
                    operator_display,
                    helper_display,
                    str(row_data.get("status") or "-"),
                ]
                sort_keys = [
                    ped_sort,
                    None,
                    None,
                    weight_sort,
                    str(row_data.get("delivery_date") or ""),
                    row_data.get("delay_days") or 0,
                    None,
                    None,
                    None,
                    None,
                    None,
                ]

            for col, value in enumerate(values):
                if key == "atrasados" and col == 10:
                    status = str(row_data.get("status") or "")
                    badge = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    color_map = {
                        "em_andamento": theme.PRIMARY_HOVER,
                        "rascunho": theme.STATUS_COLORS.get("rascunho", theme.PRIMARY_HOVER),
                        "aguardando_recebimento": theme.WARNING,
                        "aguardando_na_fila": theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
                        "em_producao": theme.PRIMARY,
                        "faturado": theme.STATUS_COLORS.get("faturado", theme.SUCCESS),
                        "finalizado": theme.STATUS_COLORS.get("finalizado", theme.SUCCESS),
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
                    alignment = (
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                        if col in left_align_columns
                        else Qt.AlignmentFlag.AlignCenter
                    )
                    item.setTextAlignment(alignment)
                    item.setToolTip(value)
                    table.setItem(row, col, item)
        table.setSortingEnabled(True)
        self._configure_table_columns(table, key)

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
            req_id = rows[row_index].get("source_requisition_id") or rows[row_index].get("id")
            self.open_requisition.emit(int(req_id))

    def _open_selected(self, key: str):
        row = self._selected_row(key)
        if not row:
            QMessageBox.information(self, "Central de pedidos", "Selecione um pedido primeiro.")
            return
        req_id = row.get("source_requisition_id") or row.get("id")
        self.open_requisition.emit(int(req_id))

    def _open_selected_pdf(self, key: str):
        row = self._selected_row(key)
        if not row:
            QMessageBox.information(
                self,
                "Central de pedidos",
                "Selecione um pedido para visualizar o PDF.",
            )
            return

        req_id = int(row.get("source_requisition_id") or row["id"])
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

        btn_edit = box.addButton("Nova Requisição", QMessageBox.ButtonRole.AcceptRole)
        btn_receipt = box.addButton("Aguardando Recebimento", QMessageBox.ButtonRole.ActionRole)
        btn_close = box.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(box)
        # Ajusta as larguras pelo texto real para evitar truncamento em qualquer escala.
        metrics = QFontMetrics(btn_edit.font())
        horizontal_padding = max(44, int(52 * self.scale))
        btn_edit_w = max(180, metrics.horizontalAdvance(btn_edit.text()) + horizontal_padding)
        btn_receipt_w = max(220, metrics.horizontalAdvance(btn_receipt.text()) + horizontal_padding)
        btn_close_w = max(120, metrics.horizontalAdvance(btn_close.text()) + horizontal_padding)
        btn_edit.setMinimumWidth(btn_edit_w)
        btn_receipt.setMinimumWidth(btn_receipt_w)
        btn_close.setMinimumWidth(btn_close_w)
        row_padding = max(88, int(96 * self.scale))
        box.setMinimumWidth(max(760, btn_edit_w + btn_receipt_w + btn_close_w + row_padding))
        btn_receipt.setEnabled(bool(destination))
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_edit:
            self._apply_reopen_canceled_status(
                row,
                new_status="rascunho",
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
        req_id = int(row.get("source_requisition_id") or row["id"])
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
        table.setStyleSheet(_order_table_qss(self.scale))
        _apply_order_table_palette(table)

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

        # Reaplica o gradient dos cards (mesmo padrão do Painel Gerencial e
        # Nova Requisição): o QSS é gravado uma única vez na criação e fica
        # com a paleta antiga ao trocar tema sem essa reaplicação.
        card_qss = _order_card_qss(radius=max(18, int(20 * s)))
        for card in self.findChildren(QFrame, "orderCenterCard"):
            card.setStyleSheet(card_qss)

        # Labels dos metric cards (topo) — re-estiliza para refletir a paleta
        # corrente. Sem isso, a cor congelada na criação fica igual ao fundo
        # quando o tema troca (escuro<->claro).
        for lbl in self._metric_labels.values():
            lbl.setStyleSheet(
                f"font-size:{max(20, int(26 * s))}pt;"
                f"font-weight:800; background:transparent; border:none;"
                f"color:{theme.PANEL_TEXT_PRIMARY};"
            )
        for lbl in self._metric_title_labels.values():
            lbl.setStyleSheet(
                f"font-size:{max(9, int(11 * s))}pt;"
                f"font-weight:700; background:transparent; border:none;"
                f"color:{theme.PANEL_TEXT_PRIMARY};"
            )
        for lbl in self._metric_helper_labels.values():
            lbl.setStyleSheet(
                f"font-size:{max(7, int(8 * s))}pt;"
                f"background:transparent; border:none;"
                f"color:{theme.PANEL_TEXT_MUTED};"
            )
        # Títulos / subtítulos dos cards de seção (Aguardando, Em Produção...).
        for lbl in self._section_title_labels:
            lbl.setStyleSheet(
                f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
                f"color:{theme.PANEL_TEXT_PRIMARY};"
            )
        for lbl in self._section_subtitle_labels:
            lbl.setStyleSheet(
                f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
                f"color:{theme.PANEL_TEXT_MUTED};"
            )

        # Re-polish dos filhos garante que labels e botões internos (que têm
        # setStyleSheet inline sem cor explícita) peguem o global_style novo.
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)

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
