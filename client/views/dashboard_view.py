"""Painel gerencial com indicadores operacionais e alertas."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QObject, QPoint, QRectF, QSize, QThread, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from ..core.datetime_utils import (
    format_date as _format_date,
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)


_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"
_METRIC_ICON_FILES = {
    "pedidos_em_producao": "pedidos_em_producao.png",
    "pedidos_em_atraso": "pedidos_atrasados.png",
    "pedidos_finalizados_hoje": "pedidos_concluidos.png",
    "producao_pinheiro_industria": "producao_pinheiro_industria.png",
    "producao_ar": "producao_ar.png",
    "requisicoes_feitas_no_dia": "requisicoes_do_dia.png",
    "pedidos_sem_confirmacao_1h": "aguardando_recebimento.png",
    "tempo_medio_finalizacao_segundos": "tempo_medio_producao.png",
}
_NEON_PERIOD_COLORS = {
    "monthly": "#22D3EE",
    "weekly": "#FB7185",
    "daily": "#A3E635",
}
_RADAR_PERIOD_COLORS = {
    "monthly": "#0891B2",
    "weekly": "#E11D48",
    "daily": "#65A30D",
}
_NEON_PERIOD_LABELS = {
    "monthly": "MENSAL",
    "weekly": "SEMANAL",
    "daily": "DIÁRIO",
}
_IAR_TOOLTIP_TEXTS = {
    "iar_geral": (
        "Resume a saúde da operação no período selecionado. Quanto mais perto de 100%, "
        "melhor o equilíbrio entre prazo, produtividade e baixo cancelamento."
    ),
    "prazo_percent": (
        "Percentual de pedidos finalizados dentro do prazo de entrega no período. "
        "Quanto maior, melhor o cumprimento dos compromissos."
    ),
    "produtividade_percent": (
        "Percentual de pedidos recebidos no período que já foram finalizados. "
        "Indica o ritmo de escoamento da produção."
    ),
    "cancelamentos_percent": (
        "Percentual de pedidos que seguiram ativos no período, sem cancelamento. "
        "Quanto maior, menor a perda operacional e comercial."
    ),
}
_IAR_TOOLTIP_TEXTS.update(
    {
        "iar_geral": (
            "Resume a saude da operacao no periodo selecionado.\n"
            "Quanto mais perto de 100%, melhor o equilibrio entre prazo,\n"
            "produtividade e baixo cancelamento."
        ),
        "prazo_percent": (
            "Percentual de pedidos finalizados dentro do prazo de entrega no periodo.\n"
            "Quanto maior, melhor o cumprimento dos compromissos."
        ),
        "produtividade_percent": (
            "Percentual de pedidos recebidos no periodo que ja foram finalizados.\n"
            "Indica o ritmo de escoamento da producao."
        ),
        "cancelamentos_percent": (
            "Percentual de pedidos que seguiram ativos no periodo, sem cancelamento.\n"
            "Quanto maior, menor a perda operacional e comercial."
        ),
    }
)

def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _tint(color: str, alpha: int = 40) -> str:
    """Cor sólida equivalente a rgba(color, alpha) sobre fundo branco."""
    c = QColor(color)
    a = alpha / 255.0
    r = round(c.red() * a + 255 * (1 - a))
    g = round(c.green() * a + 255 * (1 - a))
    b = round(c.blue() * a + 255 * (1 - a))
    return f"#{r:02x}{g:02x}{b:02x}"


def _apply_shadow(widget: QWidget, blur: int = 28, y_offset: int = 6, alpha: int = 24) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.PANEL_SHADOW)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


class _DashboardHoverTooltip(QFrame):
    def __init__(self, scale: float, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self._scale = scale
        self._text = ""
        self.setObjectName("dashboardHoverTooltip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._label)
        self.apply_theme(scale)

    def apply_theme(self, scale: float | None = None) -> None:
        if scale is not None:
            self._scale = scale

        s = self._scale
        max_width = max(250, int(340 * s))
        radius = max(10, int(12 * s))
        padding_v = max(8, int(10 * s))
        padding_h = max(12, int(14 * s))
        font_size = max(8, int(9 * s))

        self._label.setMaximumWidth(max_width)
        self._label.setStyleSheet(
            f"background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
            f"font-size:{font_size}pt; font-weight:600; line-height:1.2;"
        )
        self.setStyleSheet(
            f"QFrame#dashboardHoverTooltip {{"
            f"  background:{theme.PANEL_SURFACE_BG};"
            f"  border:1px solid {_rgba(theme.PANEL_NEON_PRIMARY, 110)};"
            f"  border-radius:{radius}px;"
            f"  padding:{padding_v}px {padding_h}px;"
            f"}}"
        )
        self._refresh_size()

    def _refresh_size(self) -> None:
        self._label.adjustSize()
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self.adjustSize()

    def show_for(self, widget: QWidget, text: str) -> None:
        if not text:
            self.hide()
            return

        self._text = text
        self._label.setText(text)
        self._refresh_size()

        offset = max(10, int(12 * self._scale))
        screen = widget.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.show()
            return

        screen_rect = screen.availableGeometry()
        anchor_bottom = widget.mapToGlobal(QPoint(widget.width() // 2, widget.height()))
        anchor_top = widget.mapToGlobal(QPoint(widget.width() // 2, 0))
        x = anchor_bottom.x() - (self.width() // 2)
        y = anchor_bottom.y() + offset

        min_x = screen_rect.left() + 8
        max_x = screen_rect.right() - self.width() - 8
        if max_x < min_x:
            max_x = min_x
        x = max(min_x, min(x, max_x))

        if y + self.height() > screen_rect.bottom() - 8:
            y = anchor_top.y() - self.height() - offset
        if y < screen_rect.top() + 8:
            y = screen_rect.top() + 8

        self.move(x, y)
        self.show()
        self.raise_()


def _restore_table_sorting(table: QTableWidget) -> None:
    table.setSortingEnabled(False)
    allow_sorting = bool(table.property("allowSorting"))
    header = table.horizontalHeader()
    header.setSectionsClickable(allow_sorting)
    sort_column_prop = table.property("sortColumn")
    sort_column = -1 if sort_column_prop is None else int(sort_column_prop)
    if allow_sorting and sort_column >= 0:
        sort_order = (
            Qt.SortOrder.DescendingOrder
            if str(table.property("sortOrder") or "asc") == "desc"
            else Qt.SortOrder.AscendingOrder
        )
        table.sortItems(sort_column, sort_order)
        _refresh_rank_column(table)
        header.setSortIndicator(sort_column, sort_order)
        header.setSortIndicatorShown(True)
        return
    header.setSortIndicatorShown(False)


def _refresh_rank_column(table: QTableWidget) -> None:
    if bool(table.property("showingEmptyMessage")):
        return

    rank_column_prop = table.property("rankColumn")
    rank_column = -1 if rank_column_prop is None else int(rank_column_prop)
    if rank_column < 0:
        return

    for row_index in range(table.rowCount()):
        rank_text = str(row_index + 1)
        item = table.item(row_index, rank_column)
        if item is None:
            item = _SortableTableWidgetItem(rank_text, row_index + 1)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_index, rank_column, item)
            continue
        item.setText(rank_text)
        if isinstance(item, _SortableTableWidgetItem):
            item._sort_value = row_index + 1


def _shadow_card_qss(accent: str, radius: int) -> str:
    """QSS dos shadow cards do Dashboard. Extraído para que apply_theme()
    consiga reaplicar lendo os parâmetros guardados como property em cada
    card (theme_card_accent / theme_card_radius)."""
    return (
        f"QFrame#dashboardCard {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {theme.PANEL_CARD_BG_START}, stop:0.55 {theme.PANEL_CARD_BG_MID}, stop:1 {theme.PANEL_CARD_BG_END});"
        f"  border:1px solid {_rgba(accent, 126)};"
        f"  border-radius:{radius}px;"
        f"}}"
        f"QFrame#dashboardCard:hover {{ border-color:{_rgba(accent, 210)}; }}"
    )


def _make_shadow_card(
    scale: float,
    background: str,
    border_color: str | None = None,
    radius: int = 18,
    hover_background: str | None = None,
) -> QFrame:
    card = QFrame()
    card.setObjectName("dashboardCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    accent = border_color or theme.PANEL_BORDER_SOFT
    card.setProperty("theme_bg", "card")
    radius_int = int(radius)
    # theme.themed: aplica agora E reaplica em toda troca de tema. As cores
    # PANEL_CARD_BG_* viviam burnadas do __init__ — agora a closure lê o
    # valor atual de theme.* na hora da reaplicação.
    theme.themed(card, lambda a=accent, r=radius_int: _shadow_card_qss(a, r))
    _apply_shadow(card, blur=max(28, int(34 * scale)), y_offset=max(4, int(5 * scale)), alpha=56)
    return card


def _metric_icon_path(key: str) -> Path | None:
    filename = _METRIC_ICON_FILES.get(key)
    if not filename:
        return None
    path = _ICON_DIR / filename
    return path if path.exists() else None


def _flat_secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


def _scoped_field_qss_dash(s: float) -> str:
    """Escopa _field_style por property dashField='1'. Permite que apply_theme
    cubra todos os combos/dates do dashboard em uma única chamada de
    setStyleSheet no root da view."""
    raw = _field_style(s)
    return (raw
        .replace("QComboBox, QDateEdit ",
                 "QComboBox[dashField='1'], QDateEdit[dashField='1'] ")
        .replace("QComboBox:hover, QDateEdit:hover",
                 "QComboBox[dashField='1']:hover, QDateEdit[dashField='1']:hover")
        .replace("QComboBox:focus, QDateEdit:focus",
                 "QComboBox[dashField='1']:focus, QDateEdit[dashField='1']:focus")
        .replace("QComboBox::", "QComboBox[dashField='1']::")
        .replace("QDateEdit ", "QDateEdit[dashField='1'] ")
        .replace("QComboBox QAbstractItemView",
                 "QComboBox[dashField='1'] QAbstractItemView")
    )


def _scoped_chip_qss_dash(s: float) -> str:
    """Escopa _neon_period_chip_style por property dashPeriodChip='1'."""
    raw = _neon_period_chip_style(s)
    selector = "QPushButton[dashPeriodChip='1']"
    return (raw
        .replace("QPushButton ", f"{selector} ")
        .replace("QPushButton:", f"{selector}:")
    )


def _field_style(scale: float) -> str:
    fs = max(8, int(9 * scale))
    radius = max(12, int(14 * scale))
    return (
        f"QComboBox, QDateEdit {{"
        f"  background:{theme.PANEL_SURFACE_BG}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {_rgba(_NEON_PERIOD_COLORS['monthly'], 92)}; border-radius:{radius}px;"
        f"  padding:8px 28px 8px 12px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QComboBox:hover, QDateEdit:hover {{ border-color:{_NEON_PERIOD_COLORS['weekly']}; }}"
        f"QComboBox:focus, QDateEdit:focus {{ border-color:{_NEON_PERIOD_COLORS['daily']}; }}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QDateEdit {{ padding-right:12px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{theme.PANEL_SURFACE_BG}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {_rgba(_NEON_PERIOD_COLORS['monthly'], 92)};"
        f"  selection-background-color:{_rgba(_NEON_PERIOD_COLORS['monthly'], 56)};"
        f"  selection-color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
    )


def _neon_period_chip_style(scale: float) -> str:
    fs = max(8, int(9 * scale))
    radius = max(12, int(14 * scale))
    chip_text = "#000000" if not theme.is_dark else theme.PANEL_TEXT_PRIMARY
    return (
        f"QPushButton {{"
        f"  background:{theme.PANEL_SURFACE_BG}; color:{chip_text};"
        f"  border:1px solid rgba(148, 163, 184, 0.32); border-radius:{radius}px;"
        f"  padding:7px 14px; font-size:{fs}pt; font-weight:800;"
        f"}}"
        f"QPushButton:hover {{ border-color:{_RADAR_PERIOD_COLORS['monthly']}; color:{chip_text}; }}"
        f"QPushButton:checked {{"
        f"  background:{theme.PANEL_SURFACE_ALT}; color:{chip_text}; border:1px solid {_RADAR_PERIOD_COLORS['monthly']};"
        f"}}"
        f"QPushButton:checked:hover {{ border-color:{_RADAR_PERIOD_COLORS['weekly']}; }}"
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

    hours, remaining_minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {remaining_minutes:02d}m"

    days, remaining_hours = divmod(hours, 24)
    return f"{days}d {remaining_hours:02d}h"


def _format_percentage(value: object) -> str:
    try:
        percentage = max(0.0, float(value))
    except (TypeError, ValueError):
        return "-"
    return f"{percentage:.1f}%".replace(".", ",")


def _format_percentage_precise(value: object, decimals: int = 2) -> str:
    try:
        percentage = max(0.0, float(value))
    except (TypeError, ValueError):
        return "-"
    return f"{percentage:.{max(0, decimals)}f}%".replace(".", ",")


def _iar_color(value: object) -> str:
    try:
        percentage = float(value)
    except (TypeError, ValueError):
        return theme.PANEL_TEXT_MUTED
    if percentage >= 90.0:
        return theme.SUCCESS
    if percentage >= 75.0:
        return theme.WARNING
    return theme.DANGER


def _format_weight_kg(value: object) -> str:
    return format_weight_kg(value)


def _machine_status_label(value: object) -> str:
    status = str(value or "").strip().casefold()
    if status == "funcionando":
        return "Funcionando"
    if status == "manutencao":
        return "Manutenção"
    return str(value or "-") or "-"


def _machine_status_color(value: object) -> str:
    status = str(value or "").strip().casefold()
    if status == "funcionando":
        return theme.SUCCESS
    if status == "manutencao":
        return theme.WARNING
    return theme.BORDER_COLOR


class _SortableTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str, sort_value: object | None = None):
        super().__init__(text)
        self._sort_value = text.casefold() if sort_value is None else sort_value

    def __lt__(self, other):
        if isinstance(other, _SortableTableWidgetItem):
            return self._sort_key(self._sort_value) < self._sort_key(other._sort_value)
        return super().__lt__(other)

    @staticmethod
    def _sort_key(value: object) -> tuple[int, object]:
        if value is None:
            return (2, "")
        if isinstance(value, datetime):
            return (
                0,
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
            )
        if isinstance(value, (int, float)):
            return (0, float(value))
        return (1, str(value).casefold())


class NeonComparisonWidget(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        scale: float,
        mode: str = "kg",
        max_rows: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._scale = scale
        self._mode = mode
        self._max_rows = max_rows
        self._selected_period = "monthly"
        self._rows: list[dict] = []
        self._empty_message = "Nenhum dado disponivel para exibir."
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumHeight(self._content_height())

    def set_rows(self, rows: object, empty_message: str) -> None:
        self._rows = [row for row in (rows or []) if isinstance(row, dict)]
        self._empty_message = empty_message
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(max(320, int(360 * self._scale)), self._content_height())

    def set_selected_period(self, period_key: str) -> None:
        if period_key not in _RADAR_PERIOD_COLORS:
            period_key = "monthly"
        if self._selected_period == period_key:
            return
        self._selected_period = period_key
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    def _content_height(self) -> int:
        top_block = max(92, int(108 * self._scale))
        row_height = max(92, int(102 * self._scale)) if self._mode == "count_kg" else max(82, int(90 * self._scale))
        visible_rows = max(1, len(self._visible_rows()))
        bottom_padding = max(16, int(20 * self._scale))
        return top_block + (visible_rows * row_height) + bottom_padding

    def _value_for_period(self, row: dict, period_key: str) -> float:
        return max(0.0, float(row.get(f"{period_key}_kg") or 0.0))

    def _bar_label(self, row: dict, period_key: str) -> str:
        kg_text = f"{_format_weight_kg(row.get(f'{period_key}_kg'))} KG"
        if self._mode == "count_kg":
            count = int(row.get(f"{period_key}_count") or 0)
            return f"{kg_text} | {count} REQ"
        return kg_text

    def _visible_rows(self) -> list[dict]:
        period_key = self._selected_period

        def _sort_key(row: dict) -> tuple[float, float, float, str]:
            count_value = float(row.get(f"{period_key}_count") or 0)
            kg_value = self._value_for_period(row, period_key)
            weekly_value = self._value_for_period(row, "weekly")
            weekly_count = float(row.get("weekly_count") or 0)
            if self._mode == "count_kg":
                return (
                    -kg_value,
                    -count_value,
                    -weekly_value,
                    -weekly_count,
                    str(row.get("label") or "").casefold(),
                )
            return (
                -kg_value,
                -weekly_value,
                str(row.get("label") or "").casefold(),
            )

        rows = sorted(self._rows, key=_sort_key)
        if self._max_rows is not None:
            return rows[: self._max_rows]
        return rows

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        radius = max(18, int(22 * self._scale))
        path.addRoundedRect(QRectF(rect), radius, radius)

        background = QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0.0, QColor(theme.PANEL_CARD_BG_START))
        background.setColorAt(0.55, QColor(theme.PANEL_CARD_BG_MID))
        background.setColorAt(1.0, QColor(theme.PANEL_CARD_BG_END))
        painter.fillPath(path, background)

        border = QLinearGradient(rect.topLeft(), rect.bottomRight())
        active_color = _RADAR_PERIOD_COLORS.get(self._selected_period, _RADAR_PERIOD_COLORS["monthly"])
        border.setColorAt(0.0, QColor(active_color).lighter(150))
        border.setColorAt(0.5, QColor(active_color))
        border.setColorAt(1.0, QColor(active_color).darker(170))
        pen = QPen()
        pen.setBrush(border)
        pen.setWidth(max(1, int(1.4 * self._scale)))
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(QColor(theme.PANEL_TEXT_PRIMARY))
        title_font = painter.font()
        title_font.setPointSize(max(10, int(12 * self._scale)))
        title_font.setBold(True)
        painter.setFont(title_font)
        left_pad = max(18, int(22 * self._scale))
        top_pad = max(16, int(20 * self._scale))
        painter.drawText(
            QRectF(left_pad, top_pad, rect.width() - (left_pad * 2), max(24, int(30 * self._scale))),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._title,
        )

        badge_width = max(90, int(106 * self._scale))
        badge_height = max(20, int(24 * self._scale))
        badge_rect = QRectF(
            rect.right() - left_pad - badge_width,
            top_pad,
            badge_width,
            badge_height,
        )
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        badge_color = QColor(active_color)
        badge_color.setAlpha(46)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge_rect, badge_height / 2, badge_height / 2)
        painter.setPen(QColor(active_color).lighter(150))
        if not theme.is_dark:
            painter.setPen(QColor("#000000"))
        badge_font = painter.font()
        badge_font.setPointSize(max(7, int(8 * self._scale)))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            _NEON_PERIOD_LABELS.get(self._selected_period, "MENSAL"),
        )

        painter.setPen(QColor(theme.PANEL_TEXT_MUTED))
        subtitle_font = painter.font()
        subtitle_font.setPointSize(max(7, int(8 * self._scale)))
        subtitle_font.setBold(False)
        painter.setFont(subtitle_font)
        subtitle_rect = QRectF(
            left_pad,
            top_pad + max(24, int(30 * self._scale)),
            rect.width() - (left_pad * 2),
            max(30, int(36 * self._scale)),
        )
        subtitle_flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap)
        painter.drawText(
            subtitle_rect,
            subtitle_flags,
            self._subtitle,
        )

        body_top = subtitle_rect.bottom() + max(14, int(18 * self._scale))
        visible_rows = self._visible_rows()
        if not visible_rows:
            painter.setPen(QColor(theme.PANEL_TEXT_MUTED))
            empty_font = painter.font()
            empty_font.setPointSize(max(8, int(9 * self._scale)))
            painter.setFont(empty_font)
            empty_flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)
            painter.drawText(
                QRectF(
                    left_pad,
                    body_top,
                    rect.width() - (left_pad * 2),
                    rect.height() - body_top - max(16, int(20 * self._scale)),
                ),
                empty_flags,
                self._empty_message,
            )
            return

        max_value = max(
            self._value_for_period(row, self._selected_period)
            for row in visible_rows
        )
        if max_value <= 0:
            max_value = 1.0

        row_height = max(92, int(102 * self._scale)) if self._mode == "count_kg" else max(82, int(90 * self._scale))
        label_height = max(32, int(36 * self._scale)) if self._mode == "count_kg" else max(28, int(32 * self._scale))
        bar_height = max(14, int(16 * self._scale))
        value_height = max(18, int(20 * self._scale))
        bar_width = max(120, rect.width() - (left_pad * 2))

        for row_index, row in enumerate(visible_rows):
            row_top = body_top + (row_index * row_height)

            painter.setPen(QColor(theme.PANEL_TEXT_PRIMARY))
            row_label_font = painter.font()
            row_label_font.setPointSize(max(8, int(9 * self._scale)))
            row_label_font.setBold(True)
            painter.setFont(row_label_font)
            label_rect = QRectF(
                left_pad,
                row_top,
                bar_width,
                label_height,
            )
            label_flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap)
            painter.drawText(
                label_rect,
                label_flags,
                str(row.get("label") or "-"),
            )

            period_key = self._selected_period
            value = self._value_for_period(row, period_key)
            ratio = min(1.0, value / max_value) if max_value else 0.0
            current_y = row_top + label_height + max(8, int(10 * self._scale))
            track_rect = QRectF(left_pad, current_y, bar_width, bar_height)

            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRoundedRect(track_rect, bar_height / 2, bar_height / 2)

            fill_width = max(0.0, bar_width * ratio)
            if fill_width > 0:
                glow_color = QColor(_RADAR_PERIOD_COLORS[period_key])
                glow_color.setAlpha(58)
                painter.setBrush(glow_color)
                painter.drawRoundedRect(
                    QRectF(track_rect.x(), track_rect.y() - 1, fill_width, bar_height + 2),
                    (bar_height + 2) / 2,
                    (bar_height + 2) / 2,
                )

                fill_gradient = QLinearGradient(track_rect.left(), track_rect.top(), track_rect.left() + fill_width, track_rect.top())
                fill_gradient.setColorAt(0.0, QColor(_RADAR_PERIOD_COLORS[period_key]).lighter(140))
                fill_gradient.setColorAt(1.0, QColor(_RADAR_PERIOD_COLORS[period_key]))
                painter.setBrush(fill_gradient)
                painter.drawRoundedRect(
                    QRectF(track_rect.x(), track_rect.y(), fill_width, bar_height),
                    bar_height / 2,
                    bar_height / 2,
                )

            painter.setPen(QColor(theme.PANEL_TEXT_PRIMARY))
            value_font = painter.font()
            value_font.setPointSize(max(8, int(10 * self._scale)))
            value_font.setBold(True)
            painter.setFont(value_font)
            painter.drawText(
                QRectF(
                    left_pad,
                    current_y + bar_height + max(6, int(8 * self._scale)),
                    bar_width,
                    value_height,
                ),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._bar_label(row, period_key),
            )

class DashWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        ar_period: str,
        industria_period: str,
        performance_period: str,
        performance_date_start: str | None,
        performance_date_end: str | None,
        performance_destination: str,
        comparison_destination: str,
        people_period: str,
        people_destination: str,
    ):
        super().__init__()
        self.ar_period = ar_period
        self.industria_period = industria_period
        self.performance_period = performance_period
        self.performance_date_start = performance_date_start
        self.performance_date_end = performance_date_end
        self.performance_destination = performance_destination
        self.comparison_destination = comparison_destination
        self.people_period = people_period
        self.people_destination = people_destination

    def run(self):
        try:
            self.result.emit(
                api.get_management_dashboard(
                    ar_period=self.ar_period,
                    industria_period=self.industria_period,
                    performance_period=self.performance_period,
                    performance_date_start=self.performance_date_start,
                    performance_date_end=self.performance_date_end,
                    performance_destination=self.performance_destination,
                    comparison_destination=self.comparison_destination,
                    people_period=self.people_period,
                    people_destination=self.people_destination,
                )
            )
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class DashboardView(QWidget):
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._metric_labels: dict[str, QLabel] = {}
        # Títulos e helpers dos metric cards — registrados para reaplicar cor
        # em apply_theme (antes ficavam burnados com PANEL_TEXT_PRIMARY/MUTED
        # do tema do init).
        self._metric_title_labels: dict[str, QLabel] = {}
        self._metric_helper_labels: dict[str, QLabel] = {}
        self._comparison_period = "monthly"
        self._comparison_period_buttons: dict[str, QPushButton] = {}
        self._machine_period_options = [
            ("Últimos 30 dias", "30d"),
            ("Últimos 7 dias", "7d"),
            ("Hoje", "today"),
            ("Mês passado", "last_month"),
        ]
        self._performance_period_options = [
            ("Hoje", "today"),
            ("Semana", "week"),
            ("Mês", "month"),
            ("Ano", "year"),
            ("Periodo personalizado", "custom"),
        ]
        self._production_filter_options = [
            ("Todas as produções", ""),
            ("A&R", "A&R"),
            ("Pinheiro Indústria", "Pinheiro Indústria"),
        ]
        self.ar_period_combo: QComboBox | None = None
        self.industria_period_combo: QComboBox | None = None
        self.performance_period_combo: QComboBox | None = None
        self.performance_destination_combo: QComboBox | None = None
        self.comparison_destination_combo: QComboBox | None = None
        self.performance_date_from: QDateEdit | None = None
        self.performance_date_to: QDateEdit | None = None
        self.performance_date_wrap: QWidget | None = None
        self.iar_card: QFrame | None = None
        self.iar_value_label: QLabel | None = None
        self.iar_status_chip: QLabel | None = None
        self.iar_counts_label: QLabel | None = None
        self.iar_detail_blocks: dict[str, QFrame] = {}
        self.iar_detail_title_labels: dict[str, QLabel] = {}
        self.iar_detail_value_labels: dict[str, QLabel] = {}
        self._hover_tooltip_targets: dict[QWidget, str] = {}
        self._hover_tooltip = _DashboardHoverTooltip(scale, self)
        self.people_period_combo: QComboBox | None = None
        self.people_destination_combo: QComboBox | None = None
        self._setup_ui()
        self.refresh()

    def eventFilter(self, obj, event):
        if isinstance(obj, QWidget) and obj in self._hover_tooltip_targets:
            event_type = event.type()
            if event_type in (QEvent.Type.Enter, QEvent.Type.ToolTip):
                self._hover_tooltip.show_for(obj, self._hover_tooltip_targets[obj])
                return event_type == QEvent.Type.ToolTip
            if event_type in (
                QEvent.Type.Leave,
                QEvent.Type.Hide,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.FocusOut,
            ):
                self._hover_tooltip.hide()
        return super().eventFilter(obj, event)

    def _register_hover_tooltip(self, widget: QWidget | None, text: str) -> None:
        if widget is None or not text:
            return
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget.setMouseTracking(True)
        self._hover_tooltip_targets[widget] = text
        widget.installEventFilter(self)

    def _setup_ui(self):
        s = self.scale
        self.setObjectName("dashboardView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Background da view raiz. theme.themed() ao inves de capturar
        # theme.CONTENT_BG no init: o registry reaplica em toda troca de tema.
        theme.themed(self, lambda: f"QWidget#dashboardView {{ background:{theme.CONTENT_BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))

        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Painel de Produção")
        # Cor explicita: palette nao propaga consistentemente para widgets
        # com setStyleSheet inline (mesmo que o stylesheet nao mexa em color).
        theme.themed(title, lambda: (
            f"background:transparent; font-size:{max(18, int(24 * s))}pt;"
            f"font-weight:800; color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        subtitle = QLabel(
            "Visão executiva da operação industrial com indicadores, alertas e ritmo de produção."
        )
        subtitle.setProperty("muted", "1")
        theme.themed(subtitle, lambda: (
            f"background:transparent; font-size:{max(8, int(10 * s))}pt;"
            f"color:{theme.PANEL_TEXT_MUTED};"
        ))
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(max(10, int(12 * s)))

        info_card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=_NEON_PERIOD_COLORS["monthly"],
            radius=max(16, int(18 * s)),
            hover_background=theme.CARD_BG,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setProperty("muted", "1")
        theme.themed(date_hint, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        self.date_label = QLabel(_format_header_date())
        theme.themed(self.date_label, lambda: (
            f"font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setProperty("muted", "1")
        theme.themed(self.updated_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        theme.themed(self.refresh_btn, lambda: _flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        header_right.addWidget(info_card)
        header_right.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)

        # Botão ? — abre o guia rápido desta tela
        sz_g = max(24, int(28 * s))
        self.btn_guide = QPushButton("?")
        self.btn_guide.setToolTip("Abrir guia rápido")
        self.btn_guide.setFixedSize(sz_g, sz_g)
        theme.themed(self.btn_guide, lambda: (
            f"font-size:{max(10, int(11 * s))}pt; font-weight:700;"
            f"color:{theme.PANEL_TEXT_MUTED}; background:transparent;"
            f"border:1px solid {_rgba(_NEON_PERIOD_COLORS['monthly'], 102)};"
            f"border-radius:{sz_g // 2}px; padding:0;"
        ))
        self.btn_guide.clicked.connect(self.guide_requested)
        header_right.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)

        header.addLayout(header_right)

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
        # Backgrounds tematicos via theme.themed(): o registry reaplica
        # automaticamente. Sem isso, ficavam burnados com a cor capturada
        # no init e nao atualizavam ao trocar de tema.
        theme.themed(self._page_scroll, lambda: f"QScrollArea {{ border:none; background:{theme.CONTENT_BG}; }}")
        theme.themed(self._page_scroll.viewport(), lambda: f"background:{theme.CONTENT_BG}; border:none;")
        root.addWidget(self._page_scroll, 1)

        self._page_content = QWidget()
        self._page_content.setObjectName("dashboardContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        theme.themed(self._page_content, lambda: f"QWidget#dashboardContent {{ background:{theme.CONTENT_BG}; }}")
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        self.iar_card = self._build_iar_card()
        layout.addWidget(self.iar_card)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        card_defs = [
            ("pedidos_em_producao", theme.PRIMARY, "Pedidos em Produção", "Requisições recebidas pela produção."),
            ("pedidos_em_atraso", theme.DANGER, "Pedidos em Atraso", "Pedidos abertos com prazo vencido."),
            ("pedidos_finalizados_hoje", theme.SUCCESS, "Finalizados Hoje", "Finalizações registradas no dia."),
            ("requisicoes_feitas_no_dia", theme.PRIMARY_HOVER, "Requisições do Dia", "Novas requisições criadas hoje."),
            ("producao_pinheiro_industria", theme.PRIMARY, "Produção Pinheiro Indústria", "Fila ativa enviada para esse destino."),
            ("producao_ar", theme.PRIMARY_HOVER, "Produção da A&R", "Fila ativa enviada para esse destino."),
            ("pedidos_sem_confirmacao_1h", theme.WARNING, "Sem Confirmação", "Aguardando retorno há mais de 1 hora."),
            ("tempo_medio_finalizacao_segundos", theme.BORDER_COLOR, "Tempo Médio de Finalização", "Média entre recebimento e finalização."),
        ]

        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            row = index // 4
            col = index % 4
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                row,
                col,
            )

        self.radar_multi_panel_card = self._build_radar_multi_panel_card()
        layout.addWidget(self.radar_multi_panel_card)
        layout.addStretch()

    def _build_iar_card(self) -> QFrame:
        s = self.scale
        today = local_now().date()
        month_start = QDate(today.year, today.month, 1)
        today_qdate = QDate(today.year, today.month, today.day)

        card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=theme.SUCCESS,
            radius=max(20, int(22 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            max(18, int(24 * s)),
            max(16, int(20 * s)),
            max(18, int(24 * s)),
            max(16, int(20 * s)),
        )
        layout.setSpacing(max(12, int(14 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(5, int(6 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(theme.SUCCESS, 240)}, stop:0.5 {_rgba(theme.WARNING, 180)}, stop:1 {_rgba(theme.DANGER, 220)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        title_row = QHBoxLayout()
        title_row.setSpacing(max(10, int(12 * s)))

        title_col = QVBoxLayout()
        title_col.setSpacing(max(3, int(4 * s)))
        title_label = QLabel("IAR GERAL")
        theme.themed(title_label, lambda: (
            f"font-size:{max(14, int(18 * s))}pt; font-weight:900;"
            f"background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        self._register_hover_tooltip(title_label, _IAR_TOOLTIP_TEXTS["iar_geral"])
        subtitle_label = QLabel(
            "KPI principal da operação, calculado por prazo, produtividade e eficiência de cancelamentos."
        )
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("muted", "1")
        theme.themed(subtitle_label, lambda: (
            f"font-size:{max(8, int(9 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        subtitle_label.setText(
            "KPI principal da operacao, calculado por prazo, produtividade e eficiencia de cancelamentos."
        )
        title_col.addWidget(title_label)
        title_col.addWidget(subtitle_label)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(max(8, int(10 * s)))

        self.performance_date_wrap = QWidget()
        self.performance_date_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        period_dates_layout = QHBoxLayout(self.performance_date_wrap)
        period_dates_layout.setContentsMargins(0, 0, 0, 0)
        period_dates_layout.setSpacing(max(6, int(8 * s)))

        from_label = QLabel("De")
        theme.themed(from_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        self.performance_date_from = QDateEdit()
        self.performance_date_from.setCalendarPopup(True)
        self.performance_date_from.setDisplayFormat("dd/MM/yyyy")
        self.performance_date_from.setDate(month_start)
        self.performance_date_from.setFixedHeight(max(34, int(38 * s)))
        self.performance_date_from.setMinimumWidth(max(120, int(134 * s)))
        theme.themed(self.performance_date_from, lambda: _field_style(s))
        self.performance_date_from.dateChanged.connect(self._on_performance_date_changed)

        to_label = QLabel("Até")
        theme.themed(to_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        to_label.setText("Ate")
        self.performance_date_to = QDateEdit()
        self.performance_date_to.setCalendarPopup(True)
        self.performance_date_to.setDisplayFormat("dd/MM/yyyy")
        self.performance_date_to.setDate(today_qdate)
        self.performance_date_to.setFixedHeight(max(34, int(38 * s)))
        self.performance_date_to.setMinimumWidth(max(120, int(134 * s)))
        theme.themed(self.performance_date_to, lambda: _field_style(s))
        self.performance_date_to.dateChanged.connect(self._on_performance_date_changed)

        period_dates_layout.addWidget(from_label)
        period_dates_layout.addWidget(self.performance_date_from)
        period_dates_layout.addWidget(to_label)
        period_dates_layout.addWidget(self.performance_date_to)

        self.performance_period_combo = QComboBox()
        self.performance_period_combo.setFixedHeight(max(34, int(38 * s)))
        self.performance_period_combo.setMinimumWidth(max(170, int(220 * s)))
        theme.themed(self.performance_period_combo, lambda: _field_style(s))
        for label, value in self._performance_period_options:
            self.performance_period_combo.addItem(label, value)
        selected_index = self.performance_period_combo.findData("month")
        if selected_index >= 0:
            self.performance_period_combo.setCurrentIndex(selected_index)
        self.performance_period_combo.currentIndexChanged.connect(self._on_performance_filter_changed)

        production_filter_label = QLabel("PRODUÇÃO")
        theme.themed(production_filter_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))
        self.performance_destination_combo = QComboBox()
        self.performance_destination_combo.setFixedHeight(max(34, int(38 * s)))
        self.performance_destination_combo.setMinimumWidth(max(170, int(200 * s)))
        theme.themed(self.performance_destination_combo, lambda: _field_style(s))
        for label, value in self._production_filter_options:
            self.performance_destination_combo.addItem(label, value)
        self.performance_destination_combo.currentIndexChanged.connect(self._on_performance_filter_changed)

        filters_row.addWidget(self.performance_date_wrap, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        filters_row.addWidget(self.performance_period_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        filters_row.addWidget(production_filter_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        filters_row.addWidget(self.performance_destination_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        title_row.addLayout(title_col, 1)
        title_row.addLayout(filters_row)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(max(16, int(20 * s)))

        hero_col = QVBoxLayout()
        hero_col.setSpacing(max(6, int(8 * s)))
        self.iar_value_label = QLabel("0,00%")
        self.iar_value_label.setStyleSheet(
            f"font-size:{max(26, int(34 * s))}pt; font-weight:900; background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
        )
        self.iar_status_chip = QLabel("PREOCUPANTE")
        self.iar_status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.iar_status_chip.setMinimumWidth(max(118, int(136 * s)))
        hero_col.addWidget(self.iar_value_label)
        hero_col.addWidget(self.iar_status_chip, 0, Qt.AlignmentFlag.AlignLeft)

        self.iar_counts_label = QLabel("Recebidas: 0 | Finalizadas: 0 | Canceladas: 0")
        self.iar_counts_label.setProperty("muted", "1")
        self.iar_counts_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        )
        self.iar_counts_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        hero_row.addLayout(hero_col, 1)
        hero_row.addWidget(self.iar_counts_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        details_row = QHBoxLayout()
        details_row.setSpacing(max(12, int(14 * s)))
        details_row.addWidget(self._build_iar_detail_block("Prazo", "prazo_percent"), 1)
        details_row.addWidget(self._build_iar_detail_block("Produtividade", "produtividade_percent"), 1)
        details_row.addWidget(self._build_iar_detail_block("Cancelamentos", "cancelamentos_percent"), 1)

        layout.addWidget(accent)
        layout.addLayout(title_row)
        layout.addLayout(hero_row)
        layout.addLayout(details_row)

        self._update_performance_filter_visibility()
        self._apply_iar_visuals(0.0)
        return card

    def _build_iar_detail_block(self, title: str, key: str) -> QWidget:
        s = self.scale
        wrapper = QFrame()
        wrapper.setObjectName("iarDetailBlock")
        wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(max(12, int(14 * s)), max(10, int(12 * s)), max(12, int(14 * s)), max(10, int(12 * s)))
        layout.setSpacing(max(4, int(5 * s)))

        title_label = QLabel(title)
        tooltip_text = _IAR_TOOLTIP_TEXTS.get(key, "")
        value_label = QLabel("0,00%")
        self._register_hover_tooltip(value_label, tooltip_text)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        self._apply_iar_detail_block_style(wrapper, title_label, value_label, theme.PANEL_NEON_PRIMARY)
        self.iar_detail_blocks[key] = wrapper
        self.iar_detail_title_labels[key] = title_label
        self.iar_detail_value_labels[key] = value_label
        return wrapper

    def _apply_iar_detail_block_style(
        self,
        block: QFrame,
        title_label: QLabel,
        value_label: QLabel,
        color: str,
    ) -> None:
        s = self.scale
        border_alpha = 186 if theme.is_dark else 142
        surface_alpha = 24 if theme.is_dark else 14
        block.setStyleSheet(
            f"QFrame#iarDetailBlock {{"
            f"  background:{_rgba(color, surface_alpha)};"
            f"  border:1px solid {_rgba(color, border_alpha)};"
            f"  border-radius:{max(14, int(16 * s))}px;"
            f"}}"
        )
        title_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s))}pt; font-weight:800; background:transparent; border:none; color:{color};"
        )
        value_label.setStyleSheet(
            f"font-size:{max(13, int(16 * s))}pt; font-weight:900; background:transparent; border:none; color:{theme.PANEL_TEXT_PRIMARY};"
        )

    def _build_metric_card(
        self,
        color: str,
        title: str,
        helper_text: str,
        key: str,
    ) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=color,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)),
                                  max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("-")
        theme.themed(value_label, lambda: (
            f"font-size:{max(20, int(26 * s))}pt; font-weight:800; background:transparent; border:none;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        value_label.setWordWrap(True)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        theme.themed(title_label, lambda: (
            f"font-size:{max(9, int(11 * s))}pt; font-weight:700; background:transparent; border:none;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "1")
        theme.themed(helper_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; background:transparent; border:none;"
            f"color:{theme.PANEL_TEXT_MUTED};"
        ))

        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(color, 235)}, stop:0.5 {_rgba(color, 155)}, stop:1 {_rgba(color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(max(10, int(12 * s)))
        header_row.addWidget(value_label, 1, Qt.AlignmentFlag.AlignTop)

        icon_label = self._build_metric_icon_label(key)
        if icon_label is not None:
            header_row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addStretch()
        layout.addWidget(accent_line)

        self._metric_labels[key] = value_label
        self._metric_title_labels[key] = title_label
        self._metric_helper_labels[key] = helper_label
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

    # ── Radar multi-panel ─────────────────────────────────────────────────────

    _RADAR_PANEL_DEFS: list[tuple[str, str, str | None]] = [
        ("destinos",        "Destinos de produção",                         None),
        ("maq_prod",        "Produção por máquina",                         None),
        ("vendedores_comp", "Vendedores",                                    None),
        ("operadores",      "Operadores",                                    None),
        ("ajudantes",       "Ajudantes",                                     None),
        ("top_vendors",     "Vendedores com mais requisições",               None),
        ("sem_conf",        "Pedidos sem confirmação",                       None),
        ("top_pessoas",     "Operadores e ajudantes com mais produções",     "people"),
        ("maq_ar",          "Máquinas que mais operam — A&R",               "ar"),
        ("maq_ind",         "Máquinas que mais operam — Indústria",         "industria"),
        ("recentes",        "Últimas requisições",                           None),
    ]
    _RADAR_DEFAULT_OPEN: frozenset[str] = frozenset({"destinos", "top_vendors", "recentes"})

    def _build_radar_multi_panel_card(self) -> QFrame:
        s = self.scale

        card = _make_shadow_card(
            s, theme.CARD_BG,
            border_color=theme.PRIMARY_HOVER,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        root = QVBoxLayout(card)
        root.setContentsMargins(
            max(16, int(20 * s)), max(14, int(18 * s)),
            max(16, int(20 * s)), max(14, int(18 * s)),
        )
        root.setSpacing(max(10, int(12 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {_rgba(theme.PRIMARY_HOVER,235)},stop:0.5 {_rgba(theme.PRIMARY_HOVER,155)},stop:1 {_rgba(theme.PRIMARY_HOVER,235)});"
            f"border:none;border-radius:{max(2,int(3*s))}px;"
        )

        title_label = QLabel("RADAR COMPARATIVO DE PRODUÇÃO")
        theme.themed(title_label, lambda: (
            f"font-size:{max(10,int(12*s))}pt;font-weight:800;background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))

        subtitle_label = QLabel(
            "Adicione as visões que desejar e analise múltiplas métricas ao mesmo tempo."
        )
        subtitle_label.setWordWrap(True)
        theme.themed(subtitle_label, lambda: (
            f"font-size:{max(7,int(8*s))}pt;background:transparent;color:{theme.PANEL_TEXT_MUTED};"
        ))

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(max(8, int(10 * s)))
        toolbar.setContentsMargins(0, 0, 0, 0)

        self._radar_add_combo = QComboBox()
        self._radar_add_combo.setFixedHeight(max(34, int(38 * s)))
        self._radar_add_combo.setMinimumWidth(max(280, int(340 * s)))
        theme.themed(self._radar_add_combo, lambda: _field_style(s))

        btn_add = QPushButton("+ Adicionar")
        btn_add.setFixedHeight(max(34, int(38 * s)))
        theme.themed(btn_add, lambda: _flat_secondary_btn_style(s))
        btn_add.clicked.connect(self._on_radar_add_panel)

        toolbar.addWidget(self._radar_add_combo)
        toolbar.addWidget(btn_add)
        toolbar.addStretch()

        period_label = QLabel("PERÍODO:")
        theme.themed(period_label, lambda: (
            f"font-size:{max(8,int(9*s))}pt;font-weight:800;background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        toolbar.addWidget(period_label)

        for period_key in ("monthly", "weekly", "daily"):
            btn = QPushButton(_NEON_PERIOD_LABELS[period_key])
            btn.setCheckable(True)
            btn.setChecked(period_key == self._comparison_period)
            btn.setFixedHeight(max(32, int(36 * s)))
            theme.themed(btn, lambda: _neon_period_chip_style(s))
            btn.clicked.connect(
                lambda checked=False, key=period_key: self._set_comparison_period(key)
            )
            self._comparison_period_buttons[period_key] = btn
            toolbar.addWidget(btn)

        dest_label = QLabel("PRODUÇÃO:")
        theme.themed(dest_label, lambda: (
            f"font-size:{max(8,int(9*s))}pt;font-weight:800;background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        self.comparison_destination_combo = QComboBox()
        self.comparison_destination_combo.setFixedHeight(max(34, int(38 * s)))
        self.comparison_destination_combo.setMinimumWidth(max(160, int(200 * s)))
        theme.themed(self.comparison_destination_combo, lambda: _field_style(s))
        for lbl, val in self._production_filter_options:
            self.comparison_destination_combo.addItem(lbl, val)
        self.comparison_destination_combo.currentIndexChanged.connect(
            self._on_comparison_filter_changed
        )
        toolbar.addWidget(dest_label)
        toolbar.addWidget(self.comparison_destination_combo)

        # ── Panel list (scrollable) ───────────────────────────────────────────
        panel_scroll = SmoothScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        apply_smooth_scroll(panel_scroll)
        theme.themed(panel_scroll, lambda: f"QScrollArea{{border:none;background:{theme.CARD_BG};}}")
        theme.themed(panel_scroll.viewport(), lambda: f"background:{theme.CARD_BG};border:none;")

        panel_container = QWidget()
        panel_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._radar_panel_layout = QVBoxLayout(panel_container)
        self._radar_panel_layout.setContentsMargins(0, max(4, int(6 * s)), 0, 0)
        self._radar_panel_layout.setSpacing(max(12, int(16 * s)))

        self._radar_panel_widgets: dict[str, QFrame] = {}
        self._build_all_radar_panels()
        self._radar_panel_layout.addStretch()

        panel_scroll.setWidget(panel_container)

        root.addWidget(accent)
        root.addWidget(title_label)
        root.addWidget(subtitle_label)
        root.addLayout(toolbar)
        root.addWidget(panel_scroll, 1)

        self._refresh_radar_add_combo()
        self._apply_comparison_period()
        return card

    def _build_all_radar_panels(self) -> None:
        s = self.scale

        # Criar NeonComparisonWidgets (preservados exatamente como antes)
        self.production_destination_chart = NeonComparisonWidget(
            "DESTINOS DE PRODUÇÃO",
            "Peso finalizado por producao em cada recorte de tempo.",
            s, mode="kg", max_rows=None,
        )
        self.production_machine_chart = NeonComparisonWidget(
            "PRODUÇÃO POR MÁQUINA",
            "Maquinas com maior numero de requisicoes e peso processado no periodo.",
            s, mode="count_kg", max_rows=8,
        )
        self.vendor_comparison_chart = NeonComparisonWidget(
            "VENDEDORES",
            "Requisicoes emitidas e peso correspondente no periodo.",
            s, mode="count_kg", max_rows=8,
        )
        self.operator_comparison_chart = NeonComparisonWidget(
            "OPERADORES",
            "Producoes finalizadas e peso processado por operador.",
            s, mode="count_kg", max_rows=8,
        )
        self.helper_comparison_chart = NeonComparisonWidget(
            "AJUDANTES",
            "Producoes finalizadas e peso processado por ajudante.",
            s, mode="count_kg", max_rows=8,
        )
        self._apply_comparison_period()

        # Mapeia key → body widget
        bodies: dict[str, QWidget] = {
            "destinos":        self.production_destination_chart,
            "maq_prod":        self.production_machine_chart,
            "vendedores_comp": self.vendor_comparison_chart,
            "operadores":      self.operator_comparison_chart,
            "ajudantes":       self.helper_comparison_chart,
            "top_vendors":     self._build_top_vendors_table(),
            "sem_conf":        self._build_alerts_table(),
            "top_pessoas":     self._build_top_people_body(),
            "maq_ar":          self._build_top_machines_ar_table(),
            "maq_ind":         self._build_top_machines_industria_table(),
            "recentes":        self._build_recent_table(),
        }

        for key, label, combo_type in self._RADAR_PANEL_DEFS:
            panel = self._make_radar_panel_frame(key, label, bodies[key], combo_type)
            panel.setVisible(key in self._RADAR_DEFAULT_OPEN)
            self._radar_panel_layout.addWidget(panel)
            self._radar_panel_widgets[key] = panel

    def _make_radar_panel_frame(
        self,
        key: str,
        title: str,
        body: QWidget,
        combo_type: str | None,
    ) -> QFrame:
        s = self.scale

        panel = QFrame()
        panel.setObjectName("radarPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        theme.themed(panel, lambda: (
            f"QFrame#radarPanel{{background:{theme.PANEL_SURFACE_BG};"
            f"border:1px solid {_rgba(theme.PRIMARY_HOVER,60)};"
            f"border-radius:{max(12,int(14*s))}px;}}"
        ))
        root = QVBoxLayout(panel)
        root.setContentsMargins(
            max(12, int(14 * s)), max(10, int(12 * s)),
            max(12, int(14 * s)), max(10, int(12 * s)),
        )
        root.setSpacing(max(8, int(10 * s)))

        # ── Cabeçalho do painel ──────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(max(8, int(10 * s)))
        header.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title.upper())
        theme.themed(title_lbl, lambda: (
            f"font-size:{max(8,int(9*s))}pt;font-weight:800;background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        header.addWidget(title_lbl, 1)

        # Combos de período por painel (apenas para "top_pessoas", "maq_ar", "maq_ind")
        if combo_type == "ar":
            self.ar_period_combo = QComboBox()
            self.ar_period_combo.setFixedHeight(max(28, int(32 * s)))
            self.ar_period_combo.setMinimumWidth(max(130, int(160 * s)))
            theme.themed(self.ar_period_combo, lambda: _field_style(s))
            for lbl, val in self._machine_period_options:
                self.ar_period_combo.addItem(lbl, val)
            idx = self.ar_period_combo.findData("30d")
            if idx >= 0:
                self.ar_period_combo.setCurrentIndex(idx)
            self.ar_period_combo.currentIndexChanged.connect(
                lambda _=None: self._on_machine_period_changed()
            )
            header.addWidget(self.ar_period_combo)

        elif combo_type == "industria":
            self.industria_period_combo = QComboBox()
            self.industria_period_combo.setFixedHeight(max(28, int(32 * s)))
            self.industria_period_combo.setMinimumWidth(max(130, int(160 * s)))
            theme.themed(self.industria_period_combo, lambda: _field_style(s))
            for lbl, val in self._machine_period_options:
                self.industria_period_combo.addItem(lbl, val)
            idx = self.industria_period_combo.findData("30d")
            if idx >= 0:
                self.industria_period_combo.setCurrentIndex(idx)
            self.industria_period_combo.currentIndexChanged.connect(
                lambda _=None: self._on_machine_period_changed()
            )
            header.addWidget(self.industria_period_combo)

        elif combo_type == "people":
            self.people_period_combo = QComboBox()
            self.people_period_combo.setFixedHeight(max(28, int(32 * s)))
            self.people_period_combo.setMinimumWidth(max(130, int(160 * s)))
            theme.themed(self.people_period_combo, lambda: _field_style(s))
            for lbl, val in self._machine_period_options:
                self.people_period_combo.addItem(lbl, val)
            idx = self.people_period_combo.findData("30d")
            if idx >= 0:
                self.people_period_combo.setCurrentIndex(idx)
            self.people_period_combo.currentIndexChanged.connect(
                lambda _=None: self._on_machine_period_changed()
            )
            header.addWidget(self.people_period_combo)

            self.people_destination_combo = QComboBox()
            self.people_destination_combo.setFixedHeight(max(28, int(32 * s)))
            self.people_destination_combo.setMinimumWidth(max(130, int(160 * s)))
            theme.themed(self.people_destination_combo, lambda: _field_style(s))
            for lbl, val in self._production_filter_options:
                self.people_destination_combo.addItem(lbl, val)
            self.people_destination_combo.currentIndexChanged.connect(
                lambda _=None: self._on_machine_period_changed()
            )
            header.addWidget(self.people_destination_combo)

        # Botão fechar
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(max(24, int(28 * s)), max(24, int(28 * s)))
        theme.themed(btn_close, lambda: (
            f"QPushButton{{background:transparent;color:{theme.PANEL_TEXT_MUTED};"
            f"border:1px solid {_rgba(theme.PANEL_TEXT_MUTED,60)};"
            f"border-radius:{max(12,int(14*s))}px;font-size:{max(9,int(10*s))}pt;padding:0;}}"
            f"QPushButton:hover{{background:{_rgba(theme.DANGER,30)};color:{theme.DANGER};"
            f"border-color:{_rgba(theme.DANGER,100)};}}"
        ))
        btn_close.clicked.connect(lambda: self._close_radar_panel(key))
        header.addWidget(btn_close)

        root.addLayout(header)

        # Linha separadora fina
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        theme.themed(sep, lambda: (
            f"QFrame{{background:{_rgba(theme.PRIMARY_HOVER,50)};border:none;max-height:1px;}}"
        ))
        root.addWidget(sep)

        root.addWidget(body, 1)
        return panel

    def _refresh_radar_add_combo(self) -> None:
        combo = getattr(self, "_radar_add_combo", None)
        if combo is None:
            return
        combo.clear()
        combo.addItem("Escolher visão para adicionar...", "")
        for key, label, _ in self._RADAR_PANEL_DEFS:
            panel = self._radar_panel_widgets.get(key)
            if panel is not None and not panel.isVisible():
                combo.addItem(label, key)

    def _on_radar_add_panel(self) -> None:
        combo = getattr(self, "_radar_add_combo", None)
        if combo is None:
            return
        key = str(combo.currentData() or "")
        if not key:
            return
        panel = self._radar_panel_widgets.get(key)
        if panel is not None:
            panel.setVisible(True)
        self._refresh_radar_add_combo()

    def _close_radar_panel(self, key: str) -> None:
        panel = self._radar_panel_widgets.get(key)
        if panel is not None:
            panel.setVisible(False)
        self._refresh_radar_add_combo()

    # ── /Radar multi-panel ────────────────────────────────────────────────────

    def _build_section_card(self, title: str, subtitle: str, body: QWidget, accent_color: str) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=accent_color,
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

        title_label = QLabel(title)
        theme.themed(title_label, lambda: (
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("muted", "1")
        theme.themed(subtitle_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))

        layout.addWidget(accent)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(body, 1)
        return card

    def _build_machine_section_card(
        self,
        title: str,
        subtitle: str,
        body: QWidget,
        accent_color: str,
        combo_attr: str | None,
        default_period: str,
        extra_combo_attr: str | None = None,
        extra_combo_options: list[tuple[str, str]] | None = None,
        extra_combo_default: str = "",
    ) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=accent_color,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            max(16, int(20 * s)),
            max(14, int(18 * s)),
            max(16, int(20 * s)),
            max(14, int(18 * s)),
        )
        layout.setSpacing(max(10, int(12 * s)))

        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        title_row = QHBoxLayout()
        title_row.setSpacing(max(10, int(12 * s)))

        title_label = QLabel(title)
        theme.themed(title_label, lambda: (
            f"font-size:{max(10, int(12 * s))}pt; font-weight:800; background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))

        period_combo: QComboBox | None = None
        if combo_attr:
            period_combo = QComboBox()
            period_combo.setFixedHeight(max(34, int(38 * s)))
            period_combo.setMinimumWidth(max(170, int(210 * s)))
            theme.themed(period_combo, lambda: _field_style(s))
            for label, value in self._machine_period_options:
                period_combo.addItem(label, value)
            selected_index = period_combo.findData(default_period)
            if selected_index >= 0:
                period_combo.setCurrentIndex(selected_index)
            period_combo.currentIndexChanged.connect(lambda _=None: self._on_machine_period_changed())
            setattr(self, combo_attr, period_combo)

        extra_combo: QComboBox | None = None
        if extra_combo_attr:
            extra_combo = QComboBox()
            extra_combo.setFixedHeight(max(34, int(38 * s)))
            extra_combo.setMinimumWidth(max(150, int(180 * s)))
            theme.themed(extra_combo, lambda: _field_style(s))
            for label, value in (extra_combo_options or []):
                extra_combo.addItem(label, value)
            selected_extra_index = extra_combo.findData(extra_combo_default)
            if selected_extra_index >= 0:
                extra_combo.setCurrentIndex(selected_extra_index)
            extra_combo.currentIndexChanged.connect(lambda _=None: self._on_machine_period_changed())
            setattr(self, extra_combo_attr, extra_combo)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setProperty("muted", "1")
        theme.themed(subtitle_label, lambda: (
            f"font-size:{max(7, int(8 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
        ))

        title_row.addWidget(title_label, 1)
        if extra_combo is not None:
            title_row.addWidget(extra_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if period_combo is not None:
            title_row.addWidget(period_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(accent)
        layout.addLayout(title_row)
        layout.addWidget(subtitle_label)
        layout.addWidget(body, 1)
        return card

    def _update_performance_filter_visibility(self) -> None:
        is_custom = (
            str(self.performance_period_combo.currentData() or "month") == "custom"
            if self.performance_period_combo
            else False
        )
        if self.performance_date_wrap is not None:
            self.performance_date_wrap.setVisible(is_custom)

    def _on_performance_filter_changed(self) -> None:
        self._update_performance_filter_visibility()
        self.refresh()

    def _on_comparison_filter_changed(self) -> None:
        self.refresh()

    def _on_performance_date_changed(self) -> None:
        if (
            self.performance_date_from
            and self.performance_date_to
            and self.performance_date_from.date() > self.performance_date_to.date()
        ):
            changed = self.sender()
            if changed is self.performance_date_from:
                self.performance_date_to.setDate(self.performance_date_from.date())
            else:
                self.performance_date_from.setDate(self.performance_date_to.date())
        if self.performance_period_combo and str(self.performance_period_combo.currentData() or "") == "custom":
            self.refresh()

    def _selected_performance_params(self) -> tuple[str, str | None, str | None]:
        period_key = (
            str(self.performance_period_combo.currentData() or "month")
            if self.performance_period_combo
            else "month"
        )
        if period_key != "custom" or not self.performance_date_from or not self.performance_date_to:
            return period_key, None, None

        start_date = self.performance_date_from.date().toPython()
        end_date = self.performance_date_to.date().toPython()
        return period_key, start_date.isoformat(), end_date.isoformat()

    def _selected_performance_destination(self) -> str:
        return (
            str(self.performance_destination_combo.currentData() or "")
            if self.performance_destination_combo
            else ""
        )

    def _selected_comparison_destination(self) -> str:
        return (
            str(self.comparison_destination_combo.currentData() or "")
            if self.comparison_destination_combo
            else ""
        )

    def _apply_iar_visuals(self, iar_percent: object) -> None:
        color = _iar_color(iar_percent)
        try:
            percentage = float(iar_percent)
        except (TypeError, ValueError):
            percentage = 0.0
        status_text = "BOM"
        if percentage < 75.0:
            status_text = "PREOCUPANTE"
        elif percentage < 90.0:
            status_text = "ATENÇÃO"

        if self.iar_value_label is not None:
            self.iar_value_label.setStyleSheet(
                f"font-size:{max(26, int(34 * self.scale))}pt; font-weight:900; background:transparent; color:{color};"
            )
        if self.iar_status_chip is not None:
            self.iar_status_chip.setText(status_text)
            self.iar_status_chip.setStyleSheet(
                f"background:{_rgba(color, 44)}; color:{color};"
                f"border:1px solid {_rgba(color, 132)}; border-radius:{max(11, int(13 * self.scale))}px;"
                f"padding:6px 12px; font-size:{max(8, int(9 * self.scale))}pt; font-weight:900;"
            )

    def _fill_iar_card(self, iar_general: object) -> None:
        data = iar_general if isinstance(iar_general, dict) else {}
        iar_percent = data.get("iar_percent")
        if self.iar_value_label is not None:
            self.iar_value_label.setText(_format_percentage_precise(iar_percent))
        if self.iar_counts_label is not None:
            self.iar_counts_label.setText(
                "Recebidas: "
                f"{int(data.get('received_count') or 0)} | "
                "Finalizadas: "
                f"{int(data.get('finalized_count') or 0)} | "
                "Canceladas: "
                f"{int(data.get('canceled_count') or 0)}"
            )
        for key, label in self.iar_detail_value_labels.items():
            label.setText(_format_percentage_precise(data.get(key)))
            block = self.iar_detail_blocks.get(key)
            title_label = self.iar_detail_title_labels.get(key)
            if block is not None and title_label is not None:
                self._apply_iar_detail_block_style(
                    block,
                    title_label,
                    label,
                    _iar_color(data.get(key)),
                )
        self._apply_iar_visuals(iar_percent)

    def _set_comparison_period(self, period_key: str) -> None:
        if period_key not in _NEON_PERIOD_LABELS:
            period_key = "monthly"
        self._comparison_period = period_key
        self._apply_comparison_period()

    def _apply_comparison_period(self) -> None:
        for key, btn in self._comparison_period_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(key == self._comparison_period)
            btn.blockSignals(False)

        for chart in [
            getattr(self, "production_destination_chart", None),
            getattr(self, "production_machine_chart", None),
            getattr(self, "vendor_comparison_chart", None),
            getattr(self, "operator_comparison_chart", None),
            getattr(self, "helper_comparison_chart", None),
        ]:
            if chart is not None:
                chart.set_selected_period(self._comparison_period)

    def _on_table_header_clicked(self, table: QTableWidget, section: int) -> None:
        if not bool(table.property("allowSorting")):
            return

        blocked_columns = {
            int(value)
            for value in (table.property("blockedSortColumns") or [])
        }
        if section in blocked_columns:
            return

        current_column_prop = table.property("sortColumn")
        current_column = -1 if current_column_prop is None else int(current_column_prop)
        current_order = (
            Qt.SortOrder.DescendingOrder
            if str(table.property("sortOrder") or "asc") == "desc"
            else Qt.SortOrder.AscendingOrder
        )
        next_order = Qt.SortOrder.AscendingOrder
        if current_column == section:
            next_order = (
                Qt.SortOrder.DescendingOrder
                if current_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )

        table.setProperty("sortColumn", section)
        table.setProperty(
            "sortOrder",
            "desc" if next_order == Qt.SortOrder.DescendingOrder else "asc",
        )
        table.sortItems(section, next_order)
        _refresh_rank_column(table)
        header = table.horizontalHeader()
        header.setSortIndicator(section, next_order)
        header.setSortIndicatorShown(True)

    def _create_table(
        self,
        headers: list[str],
        stretch_columns: set[int],
        *,
        sortable: bool = True,
        blocked_sort_columns: set[int] | None = None,
        rank_column: int | None = None,
    ) -> QTableWidget:
        s = self.scale
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)

        header = table.horizontalHeader()
        for index in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if index in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(index, mode)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumHeight(max(34, int(40 * s)))
        header.setSortIndicatorShown(False)
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        table.setProperty("blockedSortColumns", sorted(blocked_sort_columns or set()))
        table.setProperty("allowSorting", sortable)
        table.setProperty("rankColumn", -1 if rank_column is None else rank_column)
        table.setProperty("sortColumn", -1)
        table.setProperty("sortOrder", "asc")
        table.setProperty("showingEmptyMessage", False)
        table.setSortingEnabled(False)
        header.setSectionsClickable(sortable)
        if sortable:
            header.sectionClicked.connect(lambda section, tbl=table: self._on_table_header_clicked(tbl, section))

        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.PANEL_SURFACE_BG};"
            f"  alternate-background-color:{theme.PANEL_SURFACE_ALT};"
            f"  color:{theme.PANEL_TEXT_PRIMARY}; border-radius:14px;"
            f"  gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {theme.PANEL_TABLE_HEADER_START}, stop:1 {theme.PANEL_TABLE_HEADER_END});"
            f"  color:{theme.TEXT_WHITE if not theme.is_dark else theme.PANEL_TEXT_PRIMARY}; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QHeaderView::section:hover {{ background:{theme.PANEL_TABLE_HEADER_END}; }}"
            f"QTableWidget::item {{"
            f"  background:{theme.PANEL_SURFACE_BG}; color:{theme.PANEL_TEXT_PRIMARY};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(_NEON_PERIOD_COLORS['monthly'], 26)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.PANEL_SURFACE_ALT}; color:{theme.PANEL_TEXT_PRIMARY}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(_NEON_PERIOD_COLORS['monthly'], 56)}; color:{theme.PANEL_TEXT_PRIMARY}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.PANEL_SURFACE_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.PANEL_SURFACE_ALT))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.PANEL_TEXT_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)
        apply_smooth_scroll(table)
        return table

    def _build_top_vendors_table(self) -> QTableWidget:
        self.top_vendors_table = self._create_table(
            [
                "#",
                "VENDEDOR",
                "REQUISIÇÕES",
                "PESO(KG)",
                "PRAZO (%)",
                "PRODUTIVIDADE (%)",
                "CANCELAMENTOS (%)",
                "IAR (%)",
            ],
            {1},
            blocked_sort_columns={0},
            rank_column=0,
        )
        self.top_vendors_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.top_vendors_table

    def _build_top_people_body(self) -> QWidget:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(12, int(16 * self.scale)))
        layout.addWidget(self._build_people_column("OPERADORES COM MAIS PRODUÇÕES", self._build_top_operators_table()), 1)
        layout.addWidget(self._build_people_column("AJUDANTES COM MAIS PRODUÇÕES", self._build_top_helpers_table()), 1)
        return container

    def _build_people_column(self, title: str, table: QTableWidget) -> QWidget:
        wrapper = QWidget()
        wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(6, int(8 * self.scale)))
        label = QLabel(title)
        theme.themed(label, lambda: (
            f"font-size:{max(8, int(9 * self.scale))}pt; font-weight:800; background:transparent;"
            f"color:{theme.PANEL_TEXT_PRIMARY};"
        ))
        layout.addWidget(label)
        layout.addWidget(table, 1)
        return wrapper

    def _build_top_operators_table(self) -> QTableWidget:
        self.top_operators_table = self._create_table(
            ["#", "OPERADOR", "PRODUÇÕES", "PESO(KG)"],
            {1},
            blocked_sort_columns={0},
            rank_column=0,
        )
        self.top_operators_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.top_operators_table

    def _build_top_helpers_table(self) -> QTableWidget:
        self.top_helpers_table = self._create_table(
            ["#", "AJUDANTE", "PRODUÇÕES", "PESO(KG)"],
            {1},
            blocked_sort_columns={0},
            rank_column=0,
        )
        self.top_helpers_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.top_helpers_table

    def _build_alerts_table(self) -> QTableWidget:
        self.alerts_table = self._create_table(
            ["PED", "CLIENTE", "DESTINO", "AGUARDANDO"],
            {1},
        )
        self.alerts_table.setMinimumHeight(max(220, int(250 * self.scale)))
        return self.alerts_table

    def _build_recent_table(self) -> QTableWidget:
        self.recent_table = self._create_table(
            ["PED", "CLIENTE", "VENDEDOR", "EMISSÃO", "STATUS", "DESTINO"],
            {2, 4},
        )
        self.recent_table.setMinimumHeight(max(260, int(300 * self.scale)))
        return self.recent_table

    def _build_top_machines_ar_table(self) -> QTableWidget:
        self.top_machines_ar_table = self._create_table(
            [
                "POSIÇÃO",
                "MÁQUINA",
                "PRODUÇÕES",
                "TEMPO MÉDIO",
                "TEMPO DE TRABALHO",
                "TEMPO PARADO",
                "EFICIÊNCIA",
                "PESO(KG)",
                "STATUS",
            ],
            {1},
            blocked_sort_columns={0},
            rank_column=0,
        )
        header = self.top_machines_ar_table.horizontalHeader()
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        self.top_machines_ar_table.setColumnWidth(8, max(140, int(170 * self.scale)))
        self.top_machines_ar_table.verticalHeader().setDefaultSectionSize(max(36, int(42 * self.scale)))
        self.top_machines_ar_table.setMinimumHeight(max(300, int(340 * self.scale)))
        return self.top_machines_ar_table

    def _build_top_machines_industria_table(self) -> QTableWidget:
        self.top_machines_industria_table = self._create_table(
            [
                "POSIÇÃO",
                "MÁQUINA",
                "PRODUÇÕES",
                "TEMPO MÉDIO",
                "TEMPO DE TRABALHO",
                "TEMPO PARADO",
                "EFICIÊNCIA",
                "PESO(KG)",
                "STATUS",
            ],
            {1},
            blocked_sort_columns={0},
            rank_column=0,
        )
        header = self.top_machines_industria_table.horizontalHeader()
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        self.top_machines_industria_table.setColumnWidth(8, max(140, int(170 * self.scale)))
        self.top_machines_industria_table.verticalHeader().setDefaultSectionSize(max(36, int(42 * self.scale)))
        self.top_machines_industria_table.setMinimumHeight(max(300, int(340 * self.scale)))
        return self.top_machines_industria_table

    def _on_machine_period_changed(self):
        self.refresh()

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()

        ar_period = str(self.ar_period_combo.currentData() or "30d") if self.ar_period_combo else "30d"
        industria_period = (
            str(self.industria_period_combo.currentData() or "30d")
            if self.industria_period_combo
            else "30d"
        )
        performance_period, performance_date_start, performance_date_end = self._selected_performance_params()
        performance_destination = self._selected_performance_destination()
        comparison_destination = self._selected_comparison_destination()
        people_period = (
            str(self.people_period_combo.currentData() or "30d")
            if self.people_period_combo
            else "30d"
        )
        people_destination = (
            str(self.people_destination_combo.currentData() or "")
            if self.people_destination_combo
            else ""
        )

        worker = DashWorker(
            ar_period,
            industria_period,
            performance_period,
            performance_date_start,
            performance_date_end,
            performance_destination,
            comparison_destination,
            people_period,
            people_destination,
        )
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
        if self.ar_period_combo:
            self.ar_period_combo.setEnabled(not loading)
        if self.industria_period_combo:
            self.industria_period_combo.setEnabled(not loading)
        if self.performance_period_combo:
            self.performance_period_combo.setEnabled(not loading)
        if self.performance_destination_combo:
            self.performance_destination_combo.setEnabled(not loading)
        if self.comparison_destination_combo:
            self.comparison_destination_combo.setEnabled(not loading)
        if self.performance_date_from:
            self.performance_date_from.setEnabled(not loading)
        if self.performance_date_to:
            self.performance_date_to.setEnabled(not loading)
        if self.people_period_combo:
            self.people_period_combo.setEnabled(not loading)
        if self.people_destination_combo:
            self.people_destination_combo.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.error_label.setText(f"Não foi possível carregar o painel.\n\n{message}")
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
            if key == "tempo_medio_finalizacao_segundos":
                label.setText(_format_duration(value))
            else:
                label.setText(str(value if value is not None else 0))

        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

        self._fill_iar_card(payload.get("iar_general") or {})
        self._fill_comparison_charts(payload.get("insights") or {})
        self._fill_top_vendors_table(payload.get("top_vendors") or [])
        self._fill_top_people_table(
            self.top_operators_table,
            payload.get("top_operators") or [],
            "Nenhum operador encontrado no período.",
        )
        self._fill_top_people_table(
            self.top_helpers_table,
            payload.get("top_helpers") or [],
            "Nenhum ajudante encontrado no período.",
        )
        self._fill_alerts_table(payload.get("receipt_alerts") or [])
        self._fill_top_machines_table(
            self.top_machines_ar_table,
            payload.get("top_machines_ar") or [],
            "Nenhuma máquina da A&R encontrada.",
        )
        self._fill_top_machines_table(
            self.top_machines_industria_table,
            payload.get("top_machines_industria") or [],
            "Nenhuma máquina da Indústria encontrada.",
        )
        self._fill_recent_table(payload.get("recent_requisitions") or [])

    def _fill_comparison_charts(self, insights: object) -> None:
        data = insights if isinstance(insights, dict) else {}
        self.production_destination_chart.set_rows(
            data.get("production_kg_by_destination") or [],
            "Nenhuma producao finalizada encontrada para o comparativo em KG.",
        )
        self.production_machine_chart.set_rows(
            data.get("production_kg_by_machine") or [],
            "Nenhuma maquina com producao finalizada encontrada no comparativo.",
        )
        self.vendor_comparison_chart.set_rows(
            data.get("requisitions_kg_by_vendor") or [],
            "Nenhum vendedor com requisicoes suficientes para o comparativo.",
        )
        self.operator_comparison_chart.set_rows(
            data.get("requisitions_kg_by_operator") or [],
            "Nenhum operador com producoes finalizadas no comparativo.",
        )
        self.helper_comparison_chart.set_rows(
            data.get("requisitions_kg_by_helper") or [],
            "Nenhum ajudante com producoes finalizadas no comparativo.",
        )

    def _fill_top_vendors_table(self, rows: object):
        table = self.top_vendors_table
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(0)
        table.setProperty("showingEmptyMessage", False)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhum vendedor encontrado.")
            _restore_table_sorting(table)
            return

        for index, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue
            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(index),
                str(row.get("vendor_name") or "-"),
                str(row.get("requisition_count") or 0),
                _format_weight_kg(row.get("total_weight_kg")),
                _format_percentage_precise(row.get("prazo_percent")),
                _format_percentage_precise(row.get("produtividade_percent")),
                _format_percentage_precise(row.get("cancelamentos_percent")),
                _format_percentage_precise(row.get("iar_percent")),
            ]
            sort_values = [
                index,
                str(row.get("vendor_name") or "-"),
                int(row.get("requisition_count") or 0),
                float(row.get("total_weight_kg") or 0.0),
                float(row.get("prazo_percent") or 0.0),
                float(row.get("produtividade_percent") or 0.0),
                float(row.get("cancelamentos_percent") or 0.0),
                float(row.get("iar_percent") or 0.0),
            ]
            for col, value in enumerate(values):
                item = _SortableTableWidgetItem(value, sort_values[col])
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(line, col, item)
        _restore_table_sorting(table)

    def _fill_top_people_table(self, table: QTableWidget, rows: object, empty_message: str):
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(0)
        table.setProperty("showingEmptyMessage", False)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, empty_message)
            _restore_table_sorting(table)
            return

        for index, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue
            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(index),
                str(row.get("person_name") or "-"),
                str(row.get("production_count") or 0),
                _format_weight_kg(row.get("total_weight_kg")),
            ]
            sort_values = [
                index,
                str(row.get("person_name") or "-"),
                int(row.get("production_count") or 0),
                float(row.get("total_weight_kg") or 0.0),
            ]
            for col, value in enumerate(values):
                item = _SortableTableWidgetItem(value, sort_values[col])
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(line, col, item)
        _restore_table_sorting(table)

    def _fill_alerts_table(self, rows: object):
        table = self.alerts_table
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(0)
        table.setProperty("showingEmptyMessage", False)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhum pedido aguardando confirmação há mais de 1 hora.")
            _restore_table_sorting(table)
            return

        for row in items:
            if not isinstance(row, dict):
                continue
            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("destination") or "-"),
                _format_waiting_minutes(row.get("waiting_minutes")),
            ]
            sort_values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("destination") or "-"),
                int(row.get("waiting_minutes") or 0),
            ]
            for col, value in enumerate(values):
                item = _SortableTableWidgetItem(value, sort_values[col])
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(line, col, item)
        _restore_table_sorting(table)

    def _fill_top_machines_table(
        self,
        table: QTableWidget,
        rows: object,
        empty_message: str,
    ):
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(0)
        table.setProperty("showingEmptyMessage", False)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, empty_message)
            _restore_table_sorting(table)
            return

        for index, row in enumerate(items, start=1):
            if not isinstance(row, dict):
                continue

            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(index),
                str(row.get("machine_name") or "-"),
                str(row.get("total_operations") or 0),
                _format_duration(row.get("average_seconds")),
                _format_duration(row.get("work_time_seconds")),
                _format_duration(row.get("stopped_time_seconds")),
                _format_percentage(row.get("efficiency_percent")),
                _format_weight_kg(row.get("total_weight_kg")),
                str(row.get("machine_status") or "-"),
            ]
            sort_values = [
                index,
                str(row.get("machine_name") or "-"),
                int(row.get("total_operations") or 0),
                int(row.get("average_seconds") or 0),
                int(row.get("work_time_seconds") or 0),
                int(row.get("stopped_time_seconds") or 0),
                float(row.get("efficiency_percent") or 0.0),
                float(row.get("total_weight_kg") or 0.0),
                str(row.get("machine_status") or "-"),
            ]

            for col, value in enumerate(values):
                if col == 8:
                    machine_status = str(row.get("machine_status") or "")
                    item = _SortableTableWidgetItem("", sort_values[col])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)
                    color = _machine_status_color(machine_status)
                    label = QLabel(_machine_status_label(machine_status))
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{_rgba(color, 48)}; color:{color}; border-radius:6px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(line, col, label)
                else:
                    item = _SortableTableWidgetItem(value, sort_values[col])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)
        _restore_table_sorting(table)

    def _fill_recent_table(self, rows: object):
        table = self.recent_table
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(0)
        table.setProperty("showingEmptyMessage", False)
        items = rows if isinstance(rows, list) else []

        if not items:
            self._set_empty_message(table, "Nenhuma requisição recente encontrada.")
            _restore_table_sorting(table)
            return

        for row in items:
            if not isinstance(row, dict):
                continue

            line = table.rowCount()
            table.insertRow(line)
            values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("vendor_name") or "-"),
                _format_date(row.get("emission_date")),
                str(row.get("status") or "-"),
                str(row.get("destination") or "-"),
            ]
            emission_dt = _parse_datetime(row.get("emission_date"))
            sort_values = [
                str(row.get("ped_number") or "-"),
                str(row.get("client_name") or "-"),
                str(row.get("vendor_name") or "-"),
                emission_dt or datetime.min,
                str(row.get("status") or "-"),
                str(row.get("destination") or "-"),
            ]

            for col, value in enumerate(values):
                if col == 4:
                    status = str(row.get("status") or "")
                    item = _SortableTableWidgetItem("", sort_values[col])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)
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
                    label = QLabel(theme.STATUS_LABELS.get(status, status or "-"))
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        f"background:{_rgba(color, 48)}; color:{color}; border-radius:6px;"
                        f"font-weight:700; padding:4px 10px; font-size:{max(7, int(8 * self.scale))}pt;"
                    )
                    table.setCellWidget(line, col, label)
                else:
                    item = _SortableTableWidgetItem(value, sort_values[col])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(line, col, item)
        _restore_table_sorting(table)

    def _set_empty_message(self, table: QTableWidget, message: str):
        table.setProperty("showingEmptyMessage", True)
        table.setRowCount(1)
        table.setSpan(0, 0, 1, table.columnCount())
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(theme.PANEL_TEXT_MUTED))
        table.setItem(0, 0, item)

    def _apply_table_style(self, table: QTableWidget) -> None:
        s = self.scale
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  border:none; outline:none; background:{theme.PANEL_SURFACE_BG};"
            f"  alternate-background-color:{theme.PANEL_SURFACE_ALT};"
            f"  color:{theme.PANEL_TEXT_PRIMARY}; border-radius:14px;"
            f"  gridline-color:transparent; font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"    stop:0 {theme.PANEL_TABLE_HEADER_START}, stop:1 {theme.PANEL_TABLE_HEADER_END});"
            f"  color:{theme.TEXT_WHITE if not theme.is_dark else theme.PANEL_TEXT_PRIMARY}; padding:9px 10px;"
            f"  font-weight:800; font-size:{max(7, int(8 * s))}pt; border:none;"
            f"}}"
            f"QTableWidget::item {{"
            f"  background:{theme.PANEL_SURFACE_BG}; color:{theme.PANEL_TEXT_PRIMARY};"
            f"  padding:7px 6px; border-bottom:1px solid {_rgba(_NEON_PERIOD_COLORS['monthly'], 26)};"
            f"}}"
            f"QTableWidget::item:alternate {{ background:{theme.PANEL_SURFACE_ALT}; color:{theme.PANEL_TEXT_PRIMARY}; }}"
            f"QTableWidget::item:selected {{ background:{_rgba(_NEON_PERIOD_COLORS['monthly'], 56)}; color:{theme.PANEL_TEXT_PRIMARY}; }}"
        )
        pal = table.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(theme.PANEL_SURFACE_BG))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.PANEL_SURFACE_ALT))
        pal.setColor(QPalette.ColorRole.Text, QColor(theme.PANEL_TEXT_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
        table.setPalette(pal)
        table.viewport().setAutoFillBackground(True)

    def _refresh_machine_status_labels(self, table: QTableWidget) -> None:
        """Re-estiliza os QLabel de STATUS embutidos nas células da tabela de máquinas."""
        status_col = 8
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, status_col)
            if isinstance(widget, QLabel):
                raw = widget.text()
                if raw == "Funcionando":
                    machine_status = "funcionando"
                elif raw == "Manutenção":
                    machine_status = "manutencao"
                else:
                    machine_status = ""
                color = _machine_status_color(machine_status)
                widget.setStyleSheet(
                    f"background:{_rgba(color, 48)}; color:{color}; border-radius:6px;"
                    f"font-weight:700; padding:4px 10px;"
                    f"font-size:{max(7, int(8 * self.scale))}pt;"
                )

    def apply_theme(self) -> None:
        """Reaplica tema no Painel Gerencial — versao otimizada.

        Otimizacoes:
        1) QPalette no root cascateia cores fundamentais.
        2) UMA chamada setStyleSheet no root cobre:
           - bg da view + content + scroll area
           - 12-15 cards (QFrame#dashboardCard) via objectName selector
           - 5 combos + 2 dates (via property dashField)
           - N period chips (via property dashPeriodChip)
           Antes era 1 + 12-15 cards (loop findChildren) + 5 + 2 + N chamadas.
        3) Properties setadas em runtime (custo desprezivel vs setStyleSheet).
        """
        s = self.scale
        bg = theme.CONTENT_BG

        # QPalette no root — cores cascateiam para os ~313 filhos automaticamente
        self._hover_tooltip.hide()
        self._hover_tooltip.apply_theme(s)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window,          QColor(bg))
        pal.setColor(QPalette.ColorRole.WindowText,      QColor(theme.PANEL_TEXT_PRIMARY))
        pal.setColor(QPalette.ColorRole.Text,            QColor(theme.PANEL_TEXT_PRIMARY))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.PANEL_TEXT_MUTED))
        pal.setColor(QPalette.ColorRole.Base,            QColor(theme.PANEL_SURFACE_BG))
        pal.setColor(QPalette.ColorRole.Highlight,       QColor(theme.PANEL_NEON_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
        self.setPalette(pal)

        # Marca properties (microssegundos cada). Em runtime para nao alterar
        # _setup_ui — Qt resolve o property selector automaticamente.
        for combo in (
            getattr(self, "performance_period_combo", None),
            getattr(self, "performance_destination_combo", None),
            getattr(self, "comparison_destination_combo", None),
            getattr(self, "people_period_combo", None),
            getattr(self, "people_destination_combo", None),
            getattr(self, "ar_period_combo", None),
            getattr(self, "industria_period_combo", None),
        ):
            if combo is not None:
                combo.setProperty("dashField", "1")
        for date_edit in (
            getattr(self, "performance_date_from", None),
            getattr(self, "performance_date_to", None),
        ):
            if date_edit is not None:
                date_edit.setProperty("dashField", "1")
        for btn in self._comparison_period_buttons.values():
            btn.setProperty("dashPeriodChip", "1")

        # QSS view-level: 1 chamada cobre bg + cards + fields + chips
        card_qss = (
            f"QFrame#dashboardCard {{"
            f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            f"    stop:0 {theme.PANEL_CARD_BG_START},"
            f"    stop:0.55 {theme.PANEL_CARD_BG_MID},"
            f"    stop:1 {theme.PANEL_CARD_BG_END});"
            f"  border:1px solid {_rgba(theme.PANEL_BORDER_SOFT, 126)};"
            f"  border-radius:{max(18, int(20 * s))}px;"
            f"}}"
            f"QFrame#dashboardCard:hover {{ border-color:{_rgba(theme.PANEL_BORDER_SOFT, 210)}; }}"
        )
        self.setStyleSheet(
            f"QWidget#dashboardView, QWidget#dashboardContent {{ background:{bg}; }}"
            f"QScrollArea {{ border:none; background:{bg}; }}"
            + card_qss
            + _scoped_field_qss_dash(s)
            + _scoped_chip_qss_dash(s)
        )
        self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")

        # error_label tem cores DANGER (alpha) que precisam regenerar.
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )

        # Tabelas (helper centralizado)
        for tbl in [
            getattr(self, "top_vendors_table", None),
            getattr(self, "top_operators_table", None),
            getattr(self, "top_helpers_table", None),
            getattr(self, "alerts_table", None),
            getattr(self, "top_machines_ar_table", None),
            getattr(self, "top_machines_industria_table", None),
            getattr(self, "recent_table", None),
        ]:
            if tbl is not None:
                self._apply_table_style(tbl)
        for tbl in [
            getattr(self, "top_machines_ar_table", None),
            getattr(self, "top_machines_industria_table", None),
        ]:
            if tbl is not None:
                self._refresh_machine_status_labels(tbl)

        # NeonComparisonWidget pinta via QPainter lendo theme.PANEL_CARD_BG_*.
        # Sem forçar update(), mantém o pixmap cacheado do tema antigo.
        for widget in self.findChildren(NeonComparisonWidget):
            widget.update()

        # NOTE: os loops para combos, date pickers, chips, cards
        # (dashboardCard), refresh_btn, btn_guide, date_label, updated_label,
        # _metric_labels, _metric_title_labels, _metric_helper_labels foram
        # removidos porque agora todos esses widgets usam theme.themed() no
        # __init__ — o registry os reaplica automaticamente em set_dark().

        # iar_detail_value_labels e iar_counts_label ainda usam setStyleSheet
        # direto porque os iar_detail_blocks têm cores dinâmicas (baseadas no
        # valor IAR) que mudam em runtime via _apply_iar_visuals — migrá-los
        # para themed exigiria também migrar o flow de cor dinâmica.
        for lbl in self.iar_detail_value_labels.values():
            lbl.setStyleSheet(
                f"font-size:{max(13, int(16 * s))}pt; font-weight:900; background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
            )
        if self.iar_counts_label is not None:
            self.iar_counts_label.setStyleSheet(
                f"font-size:{max(8, int(9 * s))}pt; background:transparent; color:{theme.PANEL_TEXT_MUTED};"
            )
        self._apply_iar_visuals(
            self.iar_value_label.text().replace("%", "").replace(".", "").replace(",", ".")
            if self.iar_value_label is not None
            else 0.0
        )
        for chart in [
            getattr(self, "production_destination_chart", None),
            getattr(self, "production_machine_chart", None),
            getattr(self, "vendor_comparison_chart", None),
            getattr(self, "operator_comparison_chart", None),
            getattr(self, "helper_comparison_chart", None),
        ]:
            if chart is not None:
                chart.update()

        # NOTE: removido o for card in findChildren(QFrame, "dashboardCard"):
        # o card_qss agora está no QSS view-level (1 chamada cobre todos).
        self.update()
