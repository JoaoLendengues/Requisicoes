from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QThread,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.formatters import format_weight_kg
from ..widgets.smooth_scroll import SmoothScrollArea, apply_smooth_scroll
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)
from ..core.dialogs import apply_message_box_theme, ask_confirmation, fit_dialog_button_widths
from ..core.session import session


WAITING_RECEIPT_STAGE = "waiting_receipt"
WAITING_QUEUE_STAGE = "waiting_queue"

PROD_NOTE_PREFIX = "PRODUCAO"
PROD_SEND = "ENVIADA"
PROD_QUEUED = "FILA"
PROD_STARTED = "INICIADA"
PROD_RETURNED_QUEUE = "DEVOLVIDA_FILA"
PROD_FINISHED = "FINALIZADA"
PROD_CANCELED = "CANCELADA"
AR_DOBRA_SOURCE_MACHINE_NUMBERS = {1, 2, 3, 16}
PINHEIRO_MACHINE_FORWARD_RULES = {
    4: {
        "button_label": "Enviar para prensa de cumeeira",
        "target_number": 3,
    },
    5: {
        "button_label": "Enviar para dobradeira mecânica",
        "target_number": 6,
    },
}
WORKER_ROLE_OPERADOR = "operador"
WORKER_ROLE_AJUDANTE = "ajudante"
WORKER_ROLE_LABELS = {
    WORKER_ROLE_OPERADOR: "OPERADOR",
    WORKER_ROLE_AJUDANTE: "AJUDANTE",
}

MACHINE_STATUS_OPTIONS = (
    ("funcionando", "Funcionando"),
    ("manutencao", "Manutenção"),
)

# Motivos padrão para cancelamento. O cadastro do sistema pode sobrescrever
# esta lista, mas mantemos um fallback local para o caso de a API não responder.
CANCEL_REASON_OTHER = "OUTRO"
CANCEL_REASON_OPTIONS = (
    ("C01 - Cliente desistiu do pedido", "C01 - Cliente desistiu do pedido"),
    ("C02 - Cliente alterou o projeto", "C02 - Cliente alterou o projeto"),
    ("C03 - Pedido duplicado", "C03 - Pedido duplicado"),
    ("C04 - Medidas incorretas", "C04 - Medidas incorretas"),
    ("C05 - Quantidade incorreta", "C05 - Quantidade incorreta"),
    ("C06 - Desenho técnico incorreto", "C06 - Desenho técnico incorreto"),
    ("C07 - Falta de informações técnicas", "C07 - Falta de informações técnicas"),
    ("C08 - Material indisponível", "C08 - Material indisponível"),
    ("C09 - Equipamento indisponível", "C09 - Equipamento indisponível"),
    ("C10 - Obra cancelada", "C10 - Obra cancelada"),
    ("C11 - Requisição enviada incorretamente", "C11 - Requisição enviada incorretamente"),
    ("C12 - Falta de aprovação interna", "C12 - Falta de aprovação interna"),
    ("C13 - Problema logístico", "C13 - Problema logístico"),
    ("C14 - Produção inviável", "C14 - Produção inviável"),
    ("OUTRO", "Outro"),
)

_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "dashboard_icons"


def _destination_card_meta_dict() -> dict:
    return {
        "A&R": {
            "title": "A&R",
            "helper": "Fluxo operacional da produção da A&R.",
            "accent": theme.PRIMARY_HOVER,
            "icon": "producao_ar.png",
        },
        "Pinheiro Indústria": {
            "title": "Pinheiro Indústria",
            "helper": "Fluxo operacional da Pinheiro Indústria.",
            "accent": theme.PRIMARY,
            "icon": "producao_pinheiro_industria.png",
        },
    }


def _normalize_destination(destination: str) -> str:
    text = (destination or "").strip()
    folded = text.casefold()
    if folded == "a&r":
        return "A&R"
    if "pinheiro" in folded and "ind" in folded:
        return "Pinheiro Indústria"
    return text


def _destination_card_meta(destination: str) -> dict | None:
    return _destination_card_meta_dict().get(_normalize_destination(destination))


def _configured_cancel_reason_options() -> list[tuple[str, str]]:
    try:
        settings = api.get_operational_settings()
    except Exception:
        return list(CANCEL_REASON_OPTIONS)

    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in (settings.get("cancel_reasons") or []) if isinstance(settings, dict) else []:
        if not isinstance(item, dict):
            continue
        code = " ".join(str(item.get("code") or "").upper().split())
        reason = " ".join(str(item.get("reason") or "").split())
        if not code or not reason:
            continue
        value = f"{code} - {reason}"
        if value in seen:
            continue
        seen.add(value)
        options.append((value, value))

    if (CANCEL_REASON_OTHER, "Outro") not in options:
        options.append((CANCEL_REASON_OTHER, "Outro"))
    return options or list(CANCEL_REASON_OPTIONS)



def _is_dobra_source_machine_name(machine_name: str) -> bool:
    normalized_name = str(machine_name or "").strip()
    if not normalized_name:
        return False
    digits = re.findall(r"\d+", normalized_name)
    return any(int(token) in AR_DOBRA_SOURCE_MACHINE_NUMBERS for token in digits)


def _is_ar_dobra_source_machine(destination: str, machine_name: str) -> bool:
    return _normalize_destination(destination) == "A&R" and _is_dobra_source_machine_name(machine_name)


def _machine_number_prefix(machine_name: str) -> int | None:
    match = re.match(r"\s*(\d+)\b", str(machine_name or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _machine_forward_action(destination: str, machine_name: str) -> dict | None:
    normalized_destination = _normalize_destination(destination)
    if normalized_destination == "A&R" and _is_dobra_source_machine_name(machine_name):
        return {
            "button_label": "Enviar para dobra",
            "target_mode": "picker",
            "window_title": "Enviar para dobra",
            "prompt_text": (
                f"Escolha a máquina de dobra de destino "
                f"(origem: {str(machine_name or '').strip()}):"
            ),
        }

    if normalized_destination == "Pinheiro Indústria":
        machine_number = _machine_number_prefix(machine_name)
        if machine_number is None:
            return None
        rule = PINHEIRO_MACHINE_FORWARD_RULES.get(machine_number)
        if rule:
            return dict(rule, target_mode="fixed")
    return None


def _rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def _blend(base_color: str, overlay_color: str, overlay_alpha: int) -> str:
    base = QColor(base_color)
    overlay = QColor(overlay_color)
    alpha = max(0, min(255, int(overlay_alpha))) / 255.0
    red = round(overlay.red() * alpha + base.red() * (1 - alpha))
    green = round(overlay.green() * alpha + base.green() * (1 - alpha))
    blue = round(overlay.blue() * alpha + base.blue() * (1 - alpha))
    return f"#{red:02X}{green:02X}{blue:02X}"


# ── Helpers de estilo para machine cards (centralizados para permitir
# re-aplicação rápida em apply_theme sem recriar o widget). ───────────────────
def _scoped_btn_qss(role: str, fn, s: float) -> str:
    """Reescreve um QSS de botão pra usar selector property-based.

    Permite que apply_theme defina o estilo de TODOS os botões com
    productionBtn='<role>' em uma única chamada de setStyleSheet no nível da
    view, em vez de setStyleSheet individual em cada botão.
    """
    raw = fn(s)
    selector = f"QPushButton[productionBtn='{role}']"
    return raw.replace("QPushButton ", f"{selector} ").replace("QPushButton:", f"{selector}:")


def _machine_accent_style(accent_color: str, s: float) -> str:
    return (
        f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
        f"border:none; border-radius:{max(2, int(3 * s))}px;"
    )

def _machine_title_style(s: float) -> str:
    return f"background:transparent; font-size:{max(9, int(11 * s))}pt; font-weight:800;"

def _machine_subtitle_style(s: float) -> str:
    return f"background:transparent; font-size:{max(7, int(8 * s))}pt;"

def _machine_status_label_style(s: float, status_value: object = "") -> str:
    color = theme.WARNING if _is_machine_in_maintenance(status_value) else theme.TEXT_MEDIUM
    return f"background:transparent; color:{color}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"

def _machine_stat_title_style(s: float, status_value: object = "") -> str:
    color = theme.WARNING if _is_machine_in_maintenance(status_value) else theme.PANEL_TEXT_MUTED
    return f"background:transparent; color:{color}; font-size:{max(6, int(7 * s))}pt; font-weight:700;"

def _machine_stat_value_style(s: float, status_value: object = "") -> str:
    color = (
        _blend(theme.PANEL_TEXT_PRIMARY, theme.WARNING, 18)
        if _is_machine_in_maintenance(status_value)
        else theme.PANEL_TEXT_PRIMARY
    )
    return f"background:transparent; color:{color}; font-size:{max(9, int(11 * s))}pt; font-weight:800;"


def _machine_stat_box_style(s: float, status_value: object = "") -> str:
    radius = max(10, int(12 * s))
    if _is_machine_in_maintenance(status_value):
        background = _blend(theme.PANEL_SURFACE_BG, theme.WARNING, 18)
    else:
        background = theme.PANEL_SURFACE_BG
    return (
        f"background:{background};"
        f"border:none;"
        f"border-radius:{radius}px;"
    )


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
    card = QFrame()
    card.setObjectName("productionCard")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    card.setProperty("theme_bg", "card_bordered" if border_color else "card")
    card.setStyleSheet(f"QFrame#productionCard {{ border-radius:{radius}px; }}")
    _apply_shadow(card, blur=max(26, int(30 * scale)), y_offset=max(4, int(5 * scale)))
    return card


def _flat_secondary_btn_style(scale: float) -> str:
    return theme.secondary_btn_style(scale)


def _primary_action_btn_style(scale: float) -> str:
    return theme.primary_btn_style(scale)


def _danger_action_btn_style(scale: float) -> str:
    return theme.danger_btn_style(scale)


def _warning_secondary_btn_style(scale: float) -> str:
    fs = max(9, int(10 * scale))
    background = _blend(theme.PANEL_SURFACE_BG, theme.WARNING, 18)
    hover_background = _blend(theme.PANEL_SURFACE_ALT, theme.WARNING, 24)
    pressed_background = _blend(theme.PANEL_SURFACE_BG, theme.WARNING, 34)
    border = _rgba(theme.WARNING, 150)
    border_hover = _rgba(theme.WARNING, 220)
    return (
        f"QPushButton {{"
        f"  background:{background}; color:{theme.WARNING}; border:1px solid {border};"
        f"  border-radius:14px; padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{hover_background}; border-color:{border_hover}; }}"
        f"QPushButton:pressed {{ background:{pressed_background}; }}"
        f"QPushButton:disabled {{ background:{_rgba(theme.PANEL_BORDER_SOFT, 36)}; color:{theme.PANEL_TEXT_MUTED}; border-color:{theme.PANEL_BORDER_SOFT}; }}"
    )


def _apply_machine_card_button_styles(theme_widgets: dict, scale: float, status_value: object = "") -> None:
    """Garante o estilo visual dos botões dos cards de máquina."""
    secondary_style = (
        _warning_secondary_btn_style(scale)
        if _is_machine_in_maintenance(status_value)
        else _flat_secondary_btn_style(scale)
    )
    button_styles = {
        "status_button": secondary_style,
        "btn_open": secondary_style,
        "btn_finish": _primary_action_btn_style(scale),
        "btn_forward_machine": _primary_action_btn_style(scale),
        "btn_prazo": secondary_style,
        "btn_cancel": _danger_action_btn_style(scale),
    }
    for key, style in button_styles.items():
        button = theme_widgets.get(key)
        if button is not None:
            button.setStyleSheet(style)


def _machine_combo_style(scale: float, status_value: object = "") -> str:
    fs = max(8, int(9 * scale))
    accent = _machine_status_accent(status_value)
    popup_bg = (
        _blend(theme.CARD_BG, theme.WARNING, 16)
        if _is_machine_in_maintenance(status_value)
        else theme.CARD_BG
    )
    popup_border = (
        _rgba(theme.WARNING, 112)
        if _is_machine_in_maintenance(status_value)
        else theme.BORDER_COLOR
    )
    return (
        f"QComboBox {{"
        f"  background:{_rgba(accent, 18)}; color:{accent};"
        f"  border:1px solid {_rgba(accent, 156)}; border-radius:12px;"
        f"  padding:7px 12px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QComboBox::drop-down {{ border:none; width:24px; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{popup_bg}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {popup_border}; border-radius:10px;"
        f"  padding:4px; outline:none;"
        f"  selection-background-color:{_rgba(accent, 44)}; selection-color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
        f"QComboBox QAbstractItemView::item {{"
        f"  padding:7px 12px; border:none; border-radius:6px;"
        f"}}"
    )


def _sanitize_note_value(value: object) -> str:
    return " ".join(str(value or "").replace("|", " ").replace(";", " ").split()).strip()


def _normalize_worker_role(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == WORKER_ROLE_AJUDANTE:
        return WORKER_ROLE_AJUDANTE
    return WORKER_ROLE_OPERADOR


def _machine_team_members(machine: dict) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    seen: set[str] = set()
    raw_members = machine.get("team_members") or []
    if isinstance(raw_members, list):
        for raw_member in raw_members:
            if not isinstance(raw_member, dict):
                continue
            name = _sanitize_note_value(raw_member.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            members.append(
                {
                    "name": name,
                    "role": _normalize_worker_role(raw_member.get("role")),
                }
            )
    if members:
        return members

    for raw_name in machine.get("operators") or []:
        name = _sanitize_note_value(raw_name)
        if not name or name in seen:
            continue
        seen.add(name)
        members.append({"name": name, "role": WORKER_ROLE_OPERADOR})
    return members


def _split_team_members(machine: dict) -> tuple[list[str], list[str]]:
    operators: list[str] = []
    helpers: list[str] = []
    for member in _machine_team_members(machine):
        if member["role"] == WORKER_ROLE_AJUDANTE:
            helpers.append(member["name"])
        else:
            operators.append(member["name"])
    return operators, helpers


def _format_weight_kg(value: object) -> str:
    return format_weight_kg(value)


def _machine_status_accent(status_value: object) -> str:
    normalized = str(status_value or "").strip().casefold()
    if normalized == "funcionando":
        return theme.SUCCESS
    if normalized == "manutencao":
        return theme.WARNING
    return theme.BORDER_COLOR


def _is_machine_in_maintenance(machine_or_status: object) -> bool:
    if isinstance(machine_or_status, dict):
        value = machine_or_status.get("status")
    else:
        value = machine_or_status
    return str(value or "").strip().casefold() == "manutencao"


def _machine_card_style(scale: float, status_value: object) -> str:
    radius = max(18, int(20 * scale))
    if not _is_machine_in_maintenance(status_value):
        return f"QFrame#productionCard {{ border-radius:{radius}px; }}"

    start = _blend(theme.PANEL_CARD_BG_START, theme.WARNING, 36)
    mid = _blend(theme.PANEL_CARD_BG_MID, theme.WARNING, 28)
    end = _blend(theme.PANEL_CARD_BG_END, theme.WARNING, 18)
    border = _rgba(theme.WARNING, 178)
    border_hover = _rgba(theme.WARNING, 232)
    return (
        f"QFrame#productionCard {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {start}, stop:0.55 {mid}, stop:1 {end});"
        f"  border:1px solid {border};"
        f"  border-radius:{radius}px;"
        f"}}"
        f"QFrame#productionCard:hover {{ border-color:{border_hover}; }}"
    )


def _machine_table_qss(scale: float, status_value: object = "") -> str:
    if not _is_machine_in_maintenance(status_value):
        return theme.neon_table_qss(scale)

    header_fg = theme.TEXT_WHITE if not theme.is_dark else theme.PANEL_TEXT_PRIMARY
    fs_item = max(8, int(9 * scale))
    fs_head = max(7, int(8 * scale))
    base = _blend(theme.PANEL_SURFACE_BG, theme.WARNING, 18)
    alt = _blend(theme.PANEL_SURFACE_ALT, theme.WARNING, 24)
    header_start = _blend(theme.PANEL_TABLE_HEADER_START, theme.WARNING, 52)
    header_end = _blend(theme.PANEL_TABLE_HEADER_END, theme.WARNING, 42)
    header_hover = _blend(theme.PANEL_TABLE_HEADER_END, theme.WARNING, 62)
    border = _rgba(theme.WARNING, 34)
    selected = _blend(base, theme.WARNING, 36)
    return (
        f"QTableWidget {{"
        f"  border:none; outline:none; background:{base};"
        f"  alternate-background-color:{alt};"
        f"  color:{theme.PANEL_TEXT_PRIMARY}; border-radius:14px;"
        f"  gridline-color:transparent; font-size:{fs_item}pt;"
        f"}}"
        f"QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {header_start},"
        f"    stop:1 {header_end});"
        f"  color:{header_fg}; padding:9px 10px;"
        f"  font-weight:800; font-size:{fs_head}pt; border:none;"
        f"}}"
        f"QHeaderView::section:hover {{ background:{header_hover}; }}"
        f"QTableWidget::item {{"
        f"  background:{base}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"  padding:7px 6px; border-bottom:1px solid {border};"
        f"}}"
        f"QTableWidget::item:alternate {{"
        f"  background:{alt}; color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
        f"QTableWidget::item:selected {{"
        f"  background:{selected};"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
    )


def _apply_machine_table_palette(table: QTableWidget, status_value: object = "") -> None:
    if not _is_machine_in_maintenance(status_value):
        theme.apply_neon_table_palette(table)
        return

    base = _blend(theme.PANEL_SURFACE_BG, theme.WARNING, 18)
    alt = _blend(theme.PANEL_SURFACE_ALT, theme.WARNING, 24)
    highlight = _blend(base, theme.WARNING, 36)
    pal = table.palette()
    pal.setColor(QPalette.ColorRole.Base, QColor(base))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(alt))
    pal.setColor(QPalette.ColorRole.Text, QColor(theme.PANEL_TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(highlight))
    table.setPalette(pal)


def _build_production_note(
    action: str,
    destination: str,
    *,
    machine: str = "",
    reason: str = "",
    operators: list[str] | None = None,
    helpers: list[str] | None = None,
    transfer: bool = False,
) -> str:
    parts = [PROD_NOTE_PREFIX, action, destination]
    if machine:
        parts.append(f"machine={_sanitize_note_value(machine)}")
    if reason:
        parts.append(f"reason={_sanitize_note_value(reason)}")
    operator_names = []
    seen: set[str] = set()
    for raw_name in operators or []:
        normalized = _sanitize_note_value(raw_name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        operator_names.append(normalized)
    if operator_names:
        parts.append(f"operators={';'.join(operator_names)}")
    helper_names = []
    seen_helpers: set[str] = set()
    for raw_name in helpers or []:
        normalized = _sanitize_note_value(raw_name)
        if not normalized or normalized in seen_helpers:
            continue
        seen_helpers.add(normalized)
        helper_names.append(normalized)
    if helper_names:
        parts.append(f"helpers={';'.join(helper_names)}")
    if transfer:
        parts.append("transfer=1")
    return "|".join(parts)


def _format_elapsed(value: str | None) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return "-"
    return _format_datetime(dt)


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "-"
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min"


class ProductionWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, destination: str):
        super().__init__()
        self.destination = destination

    def run(self):
        try:
            self.result.emit(api.get_production_summary(self.destination))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class ActionWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args

    def run(self):
        try:
            self.result.emit(self.fn(*self.args))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class UiCallback(QObject):
    result = Signal(object)
    error = Signal(str)


class _ClickableFrame(QFrame):
    """QFrame que emite `clicked` ao receber mousePressEvent com botão esquerdo.

    Usado como header clicável dos cards-acordeão de máquinas — alternativa
    leve a QPushButton flat quando o header precisa de layout rico (chevron +
    título + stats inline + status text).
    """

    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ProductionView(QWidget):
    open_requisition = Signal(int)
    guide_requested  = Signal()          # emitido pelo botão ? de ajuda

    def __init__(
        self,
        scale: float = 1.0,
        destinations: tuple[str, ...] | None = None,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.scale = scale
        configured_destinations = destinations or session.visible_production_destinations
        self.destinations = tuple(_normalize_destination(dest) for dest in configured_destinations)
        self.destination = self.destinations[0] if self.destinations else "A&R"
        self.page_title = title or self.destination
        self.page_subtitle = subtitle or "Acompanhamento operacional da produção."
        self.dialog_title = self.page_title
        self._threads: list[tuple[QThread, QObject]] = []
        self._stage_rows: dict[str, list[dict]] = {
            WAITING_RECEIPT_STAGE: [],
            WAITING_QUEUE_STAGE: [],
        }
        self._machine_cards: dict[int, dict] = {}
        self._machines_data: list[dict] = []
        self._setup_ui()
        if self.destination in session.visible_production_destinations:
            self.refresh()

    def _build_view_stylesheet(self, s: float, bg: str) -> str:
        """QSS view-level: backgrounds + regras property-based dos botões
        dos cards. Aplicar essa string UMA vez via self.setStyleSheet() faz
        com que TODOS os botões com property productionBtn=... peguem o
        estilo via cascata, sem precisar setStyleSheet individual em cada um.

        Usado em _setup_ui (construção inicial) e em apply_theme (troca de tema).
        """
        return (
            f"QWidget#productionView {{ background:{bg}; }}"
            f"QScrollArea {{ background:{bg}; border:none; }}"
            + _scoped_btn_qss("secondary", _flat_secondary_btn_style, s)
            + _scoped_btn_qss("primary",   _primary_action_btn_style, s)
            + _scoped_btn_qss("danger",    _danger_action_btn_style,  s)
        )

    def _setup_ui(self):
        s = self.scale
        self.setObjectName("productionView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # QSS completo já na construção: inclui regras dos botões dos cards
        # (productionBtn property). Cards futuros herdam automaticamente.
        self.setStyleSheet(self._build_view_stylesheet(s, theme.CONTENT_BG))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._page_scroll.setStyleSheet(f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}")
        root.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setStyleSheet(f"background:{theme.CONTENT_BG};")
        self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)), max(18, int(24 * s)), max(18, int(24 * s)))
        layout.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))
        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))

        title = QLabel(self.page_title)
        title.setStyleSheet(f"background:transparent; font-size:{max(18, int(24 * s))}pt; font-weight:800;")
        subtitle = QLabel(self.page_subtitle)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"background:transparent; font-size:{max(8, int(10 * s))}pt;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(max(10, int(12 * s)))

        info_card = _make_card(s, theme.CARD_BG, hover_background=theme.CARD_BG, radius=max(16, int(18 * s)))
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)), max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setProperty("muted", "1")
        date_hint.setStyleSheet(f"background:transparent; font-size:{max(7, int(8 * s))}pt; font-weight:700;")
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(f"background:transparent; font-size:{max(13, int(16 * s))}pt; font-weight:800;")
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(f"background:transparent; font-size:{max(7, int(8 * s))}pt;")
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
        layout.addLayout(header)

        counts = QGridLayout()
        counts.setHorizontalSpacing(max(12, int(16 * s)))
        counts.setVerticalSpacing(max(12, int(16 * s)))
        self.summary_waiting_receipt = self._build_summary_card("Aguardando Recebimento", theme.WARNING, "Pedidos enviados e ainda não recebidos.")
        self.summary_waiting_queue = self._build_summary_card(
            "Aguardando na Fila",
            theme.STATUS_COLORS.get("aguardando_na_fila", theme.WARNING),
            "Pedidos recebidos e aguardando máquina.",
        )
        self.summary_in_production = self._build_summary_card("Em Produção", theme.PRIMARY, "Pedidos atualmente rodando em alguma máquina.")
        counts.addWidget(self.summary_waiting_receipt["card"], 0, 0)
        counts.addWidget(self.summary_waiting_queue["card"], 0, 1)
        counts.addWidget(self.summary_in_production["card"], 0, 2)
        layout.addLayout(counts)

        stages_row = QHBoxLayout()
        stages_row.setSpacing(max(14, int(18 * s)))
        self.waiting_receipt_panel = self._build_stage_panel(
            WAITING_RECEIPT_STAGE,
            "Aguardando Recebimento",
            "Confirmar recebimento e decidir o próximo passo.",
            ["PED", "CLIENTE", "VENDEDOR", "OBRA", "PESO(kg)", "ENVIADA EM"],
            "Receber",
        )
        self.waiting_queue_panel = self._build_stage_panel(
            WAITING_QUEUE_STAGE,
            "Aguardando na Fila",
            "Pedidos aguardando liberação de máquina.",
            ["PED", "CLIENTE", "VENDEDOR", "OBRA", "PESO(kg)", "FILA DESDE"],
            "Enviar para Máquina",
        )
        stages_row.addWidget(self.waiting_receipt_panel["card"], 1)
        stages_row.addWidget(self.waiting_queue_panel["card"], 1)
        layout.addLayout(stages_row)

        machines_header = QHBoxLayout()
        machines_header.setSpacing(max(10, int(12 * s)))
        machine_title_col = QVBoxLayout()
        machine_title_col.setSpacing(max(3, int(4 * s)))

        machine_title = QLabel("Máquinas")
        machine_title.setStyleSheet(f"background:transparent; color:{theme.TEXT_DARK}; font-size:{max(12, int(14 * s))}pt; font-weight:800;")
        machine_subtitle = QLabel("Selecione a requisição de cada card para finalizar ou devolver para a fila.")
        machine_subtitle.setWordWrap(True)
        machine_subtitle.setProperty("muted", "1")
        machine_subtitle.setStyleSheet(f"background:transparent; font-size:{max(7, int(8 * s))}pt;")
        machine_title_col.addWidget(machine_title)
        machine_title_col.addWidget(machine_subtitle)
        machine_subtitle.setText(
            "Acompanhe as maquinas desta producao e use os cards para abrir, finalizar "
            "ou devolver requisicoes que ja estao em producao."
        )
        machines_header.addLayout(machine_title_col, 1)

        icon_label = self._build_destination_icon_label(self.destination)
        if icon_label is not None:
            machines_header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(machines_header)

        self.machines_widget = QWidget()
        self.machines_grid = QGridLayout(self.machines_widget)
        self.machines_grid.setContentsMargins(0, 0, 0, 0)
        self.machines_grid.setHorizontalSpacing(max(12, int(16 * s)))
        self.machines_grid.setVerticalSpacing(max(12, int(16 * s)))
        layout.addWidget(self.machines_widget)

    def _build_destination_icon_label(self, destination: str) -> QLabel | None:
        meta = _destination_card_meta(destination) or {}
        filename = meta.get("icon")
        if not filename:
            return None

        icon_path = _ICON_DIR / filename
        if not icon_path.exists():
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

    def _build_summary_card(self, title_text: str, accent_color: str, helper_text: str) -> dict:
        s = self.scale
        card = _make_card(s, theme.CARD_BG, hover_background=theme.CARD_BG, radius=max(18, int(20 * s)))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(15, int(18 * s)), max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("0")
        value_label.setStyleSheet(
            f"background:transparent; font-size:{max(20, int(26 * s))}pt; font-weight:800;"
        )
        title_label = QLabel(title_text)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"background:transparent; font-size:{max(9, int(11 * s))}pt; font-weight:700;"
        )
        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "1")
        helper_label.setStyleSheet(
            f"background:transparent; font-size:{max(7, int(8 * s))}pt;"
        )
        accent_line = QFrame()
        accent_line.setFixedHeight(max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(accent_color, 235)}, stop:0.5 {_rgba(accent_color, 155)}, stop:1 {_rgba(accent_color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addStretch()
        layout.addWidget(accent_line)
        return {"card": card, "value": value_label}

    def _build_stage_panel(
        self,
        stage: str,
        title_text: str,
        subtitle_text: str,
        headers: list[str],
        primary_text: str,
    ) -> dict:
        s = self.scale
        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)), max(16, int(20 * s)), max(14, int(18 * s)))
        layout.setSpacing(max(10, int(12 * s)))

        title_row = QHBoxLayout()
        title = QLabel(title_text)
        title.setStyleSheet(f"background:transparent; font-size:{max(12, int(14 * s))}pt; font-weight:800;")
        count = QLabel("0")
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setMinimumWidth(max(28, int(34 * s)))
        count.setStyleSheet(
            f"background:transparent; color:{theme.PRIMARY}; border:none;"
            f"font-size:{max(9, int(11 * s))}pt; font-weight:800; padding:0px;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(count)

        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(f"background:transparent; font-size:{max(9, int(10 * s))}pt;")
        layout.addLayout(title_row)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))
        btn_open = QPushButton("Abrir")
        btn_primary = QPushButton(primary_text)
        btn_prazo = QPushButton("Alterar Prazo")
        btn_cancel = QPushButton("Cancelar")
        for btn in (btn_open, btn_primary, btn_prazo, btn_cancel):
            btn.setFixedHeight(max(34, int(38 * s)))

        btn_open.setStyleSheet(_flat_secondary_btn_style(s))
        btn_primary.setStyleSheet(_primary_action_btn_style(s))
        btn_prazo.setStyleSheet(_flat_secondary_btn_style(s))
        btn_cancel.setStyleSheet(_danger_action_btn_style(s))

        btn_open.clicked.connect(lambda: self._open_selected_stage(stage))
        if stage == WAITING_RECEIPT_STAGE:
            btn_primary.clicked.connect(self._receive_selected)
        else:
            btn_primary.clicked.connect(self._send_queue_selected_to_machine)
        btn_prazo.clicked.connect(lambda: self._change_delivery_selected_stage(stage))
        btn_cancel.clicked.connect(lambda: self._cancel_selected_stage(stage))

        actions.addWidget(btn_open)
        actions.addWidget(btn_primary)
        actions.addWidget(btn_prazo)
        actions.addWidget(btn_cancel)
        layout.addLayout(actions)

        table = self._build_table(headers, stretch_columns={1, 2, 3})
        table.doubleClicked.connect(lambda index, current_stage=stage: self._open_stage_row(current_stage, index.row()))
        table.setMinimumHeight(max(240, int(270 * s)))
        layout.addWidget(table, 1)

        return {
            "card": card,
            "table": table,
            "count": count,
        }

    def _build_table(self, headers: list[str], *, stretch_columns: set[int]) -> QTableWidget:
        s = self.scale
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header_widget = table.horizontalHeader()
        for col in range(len(headers)):
            mode = QHeaderView.ResizeMode.Stretch if col in stretch_columns else QHeaderView.ResizeMode.ResizeToContents
            header_widget.setSectionResizeMode(col, mode)
        header_widget.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header_widget.setMinimumHeight(max(34, int(40 * s)))
        table.verticalHeader().setDefaultSectionSize(max(32, int(38 * s)))
        table.setStyleSheet(theme.neon_table_qss(self.scale))
        theme.apply_neon_table_palette(table)
        apply_smooth_scroll(table)
        return table

    def refresh(self):
        self._set_loading(True)
        worker = ProductionWorker(self.destination)
        thread = QThread()
        cb = UiCallback()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(cb.result)
        worker.error.connect(cb.error)
        cb.result.connect(self._on_refresh_result)
        cb.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())
        self.refresh_btn.setEnabled(not loading)

    def _on_refresh_result(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta inválida ao carregar a produção.")
            return

        stats = payload.get("stats") or {}
        self.summary_waiting_receipt["value"].setText(str(stats.get("aguardando_recebimento") or 0))
        self.summary_waiting_queue["value"].setText(str(stats.get("aguardando_na_fila") or 0))
        self.summary_in_production["value"].setText(str(stats.get("em_producao") or 0))

        self._stage_rows[WAITING_RECEIPT_STAGE] = [
            row for row in (payload.get("waiting_receipt") or []) if isinstance(row, dict)
        ]
        self._stage_rows[WAITING_QUEUE_STAGE] = [
            row for row in (payload.get("waiting_queue") or []) if isinstance(row, dict)
        ]

        self._fill_stage_table(self.waiting_receipt_panel, self._stage_rows[WAITING_RECEIPT_STAGE], WAITING_RECEIPT_STAGE)
        self._fill_stage_table(self.waiting_queue_panel, self._stage_rows[WAITING_QUEUE_STAGE], WAITING_QUEUE_STAGE)

        self._machines_data = [
            machine for machine in (payload.get("machines") or []) if isinstance(machine, dict)
        ]
        self._populate_machine_cards()

        current = local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

    def _fill_stage_table(self, panel: dict, rows: list[dict], stage: str):
        table = panel["table"]
        panel["count"].setText(str(len(rows)))
        table.setRowCount(0)

        for req in rows:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                str(req.get("ped_number") or ""),
                str(req.get("client_name") or "-"),
                str(req.get("vendor_name") or "-"),
                str(req.get("obra") or "-"),
                _format_weight_kg(req.get("weight")),
                _format_elapsed(req.get("waiting_since")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _clear_layout(self, layout: QGridLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)  # type: ignore[arg-type]

    def _populate_machine_cards(self):
        self._clear_layout(self.machines_grid)
        self._machine_cards = {}
        s = self.scale

        if not self._machines_data:
            empty = QLabel("Nenhuma máquina cadastrada para este destino.")
            empty.setStyleSheet(f"background:transparent; color:{theme.TEXT_MEDIUM}; font-size:{max(8, int(10 * s))}pt; font-weight:600;")
            empty.setProperty("muted", "1")
            self.machines_grid.addWidget(empty, 0, 0)
            return

        # Layout vertical: cada máquina ocupa uma linha inteira (col=0).
        # Cards são acordeões — fechados ficam compactos (~60-80px de altura),
        # liberando muito espaço vertical mesmo com 15+ máquinas.
        for index, machine in enumerate(self._machines_data):
            machine_card = self._build_machine_card(machine)
            self.machines_grid.addWidget(machine_card["card"], index, 0)
            self._machine_cards[int(machine["id"])] = machine_card

    def _build_machine_card(self, machine: dict) -> dict:
        """Constrói um card-acordeão de máquina (header sempre visível +
        content expansível com lazy table)."""
        s = self.scale
        meta = _destination_card_meta(self.destination) or {}
        current_status = str(machine.get("status") or "funcionando")
        accent_color = (
            theme.WARNING
            if _is_machine_in_maintenance(current_status)
            else (meta.get("accent") or theme.PRIMARY)
        )
        machine_id = int(machine["id"])
        machine_name = str(machine.get("name") or "").strip()
        rows = [row for row in (machine.get("rows") or []) if isinstance(row, dict)]

        # ====== CARD CONTAINER ======
        card = _make_card(
            s,
            theme.CARD_BG,
            border_color=theme.BORDER_COLOR,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Faixa de accent (compacta, sempre visível)
        accent = QFrame()
        accent.setFixedHeight(max(4, int(5 * s)))
        accent.setStyleSheet(_machine_accent_style(accent_color, s))
        card_layout.addWidget(accent)

        # ====== HEADER (sempre visível, clicável) ======
        header = _ClickableFrame()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_margin = max(14, int(18 * s))
        v_margin = max(10, int(12 * s))
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(h_margin, v_margin, h_margin, v_margin)
        header_layout.setSpacing(max(10, int(12 * s)))

        # Chevron (▸ recolhido / ▾ expandido). Animação de rotação não é
        # trivial em QLabel sem QGraphicsView; alternamos o texto, que é
        # suficiente visualmente e zero-custo.
        chevron = QLabel("▸")
        chevron_font_size = max(11, int(14 * s))
        chevron.setStyleSheet(
            f"background:transparent; color:{theme.PANEL_TEXT_PRIMARY};"
            f"font-size:{chevron_font_size}pt; font-weight:700;"
        )
        chevron.setFixedWidth(max(18, int(22 * s)))
        chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(chevron)

        # Nome da máquina
        title = QLabel(machine_name or "Máquina")
        title.setStyleSheet(_machine_title_style(s))
        header_layout.addWidget(title)

        header_layout.addStretch(1)

        # Summary inline: status atual + qtd em produção + finalizadas
        status_text = next(
            (text for value, text in MACHINE_STATUS_OPTIONS if value == current_status),
            current_status.title(),
        )
        qty_in_prod = int(machine.get("quantity_in_production") or 0)
        finalized = int(machine.get("finalized_count") or 0)
        summary_label = QLabel(
            f"{status_text}  ·  {qty_in_prod} em produção  ·  {finalized} finalizadas"
        )
        summary_fs = max(8, int(10 * s))
        # Cor do status_text segue o accent (vermelho/amarelo se manutenção)
        summary_label.setStyleSheet(
            f"background:transparent; color:{accent_color};"
            f"font-size:{summary_fs}pt; font-weight:600;"
        )
        summary_label.setProperty("muted", "1")
        header_layout.addWidget(summary_label)

        card_layout.addWidget(header)

        # ====== CONTENT (expansível, fechado por padrão) ======
        content = QFrame()
        content.setMaximumHeight(0)  # FECHADO inicialmente
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(h_margin, 0, h_margin, max(14, int(18 * s)))
        content_layout.setSpacing(max(8, int(10 * s)))

        # Operadores / ajudantes
        operator_names, helper_names = _split_team_members(machine)
        operator_summary = QLabel(
            "Operadores cadastrados: "
            + (", ".join(operator_names) if operator_names else "nenhum")
            + "\nAjudantes cadastrados: "
            + (", ".join(helper_names) if helper_names else "nenhum")
        )
        operator_summary.setWordWrap(True)
        operator_summary.setProperty("muted", "1")
        operator_summary.setStyleSheet(_machine_subtitle_style(s))
        if operator_names or helper_names:
            operator_summary.setToolTip(
                "Operadores: "
                + (", ".join(operator_names) if operator_names else "nenhum")
                + "\nAjudantes: "
                + (", ".join(helper_names) if helper_names else "nenhum")
            )
        content_layout.addWidget(operator_summary)

        # Stats grid completo
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(max(10, int(12 * s)))
        stats_grid.setVerticalSpacing(max(8, int(10 * s)))
        stat_blocks = [
            self._machine_stat_block("Quantidade em Produção", str(qty_in_prod), current_status),
            self._machine_stat_block("Finalizadas", str(finalized), current_status),
            self._machine_stat_block("Tempo Médio", _format_duration(machine.get("average_seconds")), current_status),
        ]
        stats_grid.addWidget(stat_blocks[0], 0, 0)
        stats_grid.addWidget(stat_blocks[1], 0, 1)
        stats_grid.addWidget(stat_blocks[2], 1, 0, 1, 2)
        content_layout.addLayout(stats_grid)
        _stat_titles = [getattr(b, "_stat_title_lbl", None) for b in stat_blocks if getattr(b, "_stat_title_lbl", None)]
        _stat_values = [getattr(b, "_stat_value_lbl", None) for b in stat_blocks if getattr(b, "_stat_value_lbl", None)]

        # Linha de status (label + combo + botão Atualizar Status)
        status_row = QHBoxLayout()
        status_row.setSpacing(max(8, int(10 * s)))
        status_label = QLabel("Status da Máquina")
        status_label.setStyleSheet(_machine_status_label_style(s, current_status))
        status_label.setProperty("muted", "1")
        status_combo = QComboBox()
        for value, text in MACHINE_STATUS_OPTIONS:
            status_combo.addItem(text, value)
        combo_index = max(0, status_combo.findData(current_status))
        status_combo.setCurrentIndex(combo_index)
        status_combo.setStyleSheet(_machine_combo_style(s, current_status))
        status_combo.currentIndexChanged.connect(
            lambda _index, combo=status_combo: combo.setStyleSheet(
                _machine_combo_style(self.scale, combo.currentData())
            )
        )
        status_button = QPushButton("Atualizar Status")
        status_button.setFixedHeight(max(34, int(38 * s)))
        status_button.setProperty("productionBtn", "secondary")
        status_button.clicked.connect(
            lambda checked=False, mid=machine_id, combo=status_combo: self._update_machine_status(mid, combo)
        )
        status_row.addWidget(status_label)
        status_row.addStretch()
        status_row.addWidget(status_combo)
        status_row.addWidget(status_button)
        content_layout.addLayout(status_row)

        # Linha de ações (Abrir, Finalizar, [Enviar pra dobra], Alterar Prazo, Cancelar)
        actions = QHBoxLayout()
        actions.setSpacing(max(8, int(10 * s)))
        btn_open = QPushButton("Abrir")
        machine_forward_action = _machine_forward_action(self.destination, machine_name)
        btn_finish = QPushButton("Finalizar")
        btn_forward_machine = (
            QPushButton(str(machine_forward_action.get("button_label") or "Encaminhar"))
            if machine_forward_action is not None
            else None
        )
        btn_prazo = QPushButton("Alterar Prazo")
        btn_cancel = QPushButton("Cancelar")
        action_buttons = [btn_open, btn_finish, btn_prazo, btn_cancel]
        if btn_forward_machine is not None:
            action_buttons.insert(2, btn_forward_machine)
        for btn in action_buttons:
            btn.setFixedHeight(max(34, int(38 * s)))
        btn_open.setProperty("productionBtn", "secondary")
        btn_finish.setProperty("productionBtn", "primary")
        if btn_forward_machine is not None:
            btn_forward_machine.setProperty("productionBtn", "primary")
        btn_prazo.setProperty("productionBtn", "secondary")
        btn_cancel.setProperty("productionBtn", "danger")
        _apply_machine_card_button_styles(
            {
                "status_button": status_button,
                "btn_open": btn_open,
                "btn_finish": btn_finish,
                "btn_forward_machine": btn_forward_machine,
                "btn_prazo": btn_prazo,
                "btn_cancel": btn_cancel,
            },
            s,
            current_status,
        )
        btn_open.clicked.connect(lambda: self._open_selected_machine(machine_id))
        btn_finish.clicked.connect(lambda: self._finish_selected_machine(machine_id))
        if btn_forward_machine is not None:
            btn_forward_machine.clicked.connect(
                lambda checked=False, mid=machine_id, action=dict(machine_forward_action or {}): (
                    self._forward_selected_machine(mid, action)
                )
            )
        btn_prazo.clicked.connect(lambda: self._change_delivery_selected_machine(machine_id))
        btn_cancel.clicked.connect(lambda: self._return_selected_machine_to_queue(machine_id))
        actions.addWidget(btn_open)
        if btn_forward_machine is not None:
            forward_actions = QVBoxLayout()
            forward_actions.setSpacing(max(6, int(8 * s)))
            forward_actions.addWidget(btn_finish)
            forward_actions.addWidget(btn_forward_machine)
            actions.addLayout(forward_actions)
        else:
            actions.addWidget(btn_finish)
        actions.addWidget(btn_prazo)
        actions.addWidget(btn_cancel)
        content_layout.addLayout(actions)

        # Placeholder onde a TABELA será inserida LAZY na 1ª expansão.
        # Mantemos um container vazio aqui pra que o layout não pule quando
        # a tabela aparecer pela primeira vez.
        table_container = QFrame()
        table_container.setStyleSheet("background:transparent; border:none;")
        table_container_layout = QVBoxLayout(table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(table_container, 1)

        card_layout.addWidget(content)

        card.setStyleSheet(_machine_card_style(s, current_status))

        # Click no header alterna expandido/recolhido
        header.clicked.connect(lambda mid=machine_id: self._toggle_machine_card(mid))

        return {
            "card": card,
            "header": header,
            "content": content,
            "chevron": chevron,
            "table_container": table_container,
            "table_container_layout": table_container_layout,
            "table": None,          # LAZY: criada na 1ª expansão
            "table_built": False,
            "expanded": False,
            "expand_anim": None,    # ref pra QPropertyAnimation viva
            "combo": status_combo,
            "rows": rows,
            "machine": dict(machine),
            "_theme_widgets": {
                "accent": accent,
                "accent_color": accent_color,
                "title": title,
                "operator_summary": operator_summary,
                "status_label": status_label,
                "status_combo": status_combo,
                "status_button": status_button,
                "btn_open": btn_open,
                "btn_finish": btn_finish,
                "btn_forward_machine": btn_forward_machine,
                "btn_prazo": btn_prazo,
                "btn_cancel": btn_cancel,
                "stat_blocks": stat_blocks,
                "stat_titles": _stat_titles,
                "stat_values": _stat_values,
                "summary_label": summary_label,
            },
        }

    def _ensure_machine_table_built(self, card_data: dict) -> None:
        """Cria e popula a tabela do card na primeira expansão (lazy load).

        Idempotente: chamadas posteriores são no-op (flag `table_built`).
        Sem isso, abrir A&R com 18 máquinas custaria 18 × build_table +
        18 × fill + 18 × apply_table_style mesmo se nenhum card tivesse
        sido expandido.
        """
        if card_data.get("table_built"):
            return
        machine = card_data.get("machine") or {}
        machine_id = int(machine.get("id") or 0)
        current_status = str(machine.get("status") or "funcionando")
        s = self.scale

        table = self._build_table(
            ["PED", "CLIENTE", "VENDEDOR", "OPERADOR", "AJUDANTE", "INICIADO EM", "PESO(kg)"],
            stretch_columns={1, 2, 3, 4},
        )
        table.setMinimumHeight(max(180, int(210 * s)))
        self._apply_table_style(table, current_status)
        self._fill_machine_table(table, card_data.get("rows") or [])
        table.doubleClicked.connect(
            lambda index, mid=machine_id: self._open_machine_row(mid, index.row())
        )
        card_data["table_container_layout"].addWidget(table)
        card_data["table"] = table
        card_data["table_built"] = True

    def _toggle_machine_card(self, machine_id: int) -> None:
        """Alterna expandido/recolhido de um card-acordeão com animação.

        Na primeira expansão de cada card, a tabela é construída lazily
        (`_ensure_machine_table_built`) — daí a tela inicial só renderiza
        os headers, sem custo de QTableWidget × N máquinas.
        """
        card_data = self._machine_cards.get(machine_id)
        if not card_data:
            return

        content: QFrame = card_data["content"]
        chevron: QLabel = card_data["chevron"]
        is_expanded = bool(card_data.get("expanded"))

        if not is_expanded:
            # EXPANDIR — garante tabela criada e anima maximumHeight.
            self._ensure_machine_table_built(card_data)
            # Força o layout a recalcular sizeHint depois de inserir a tabela.
            content.adjustSize()
            target_height = max(
                content.sizeHint().height(),
                content.layout().sizeHint().height() if content.layout() else 0,
            )
            if target_height <= 0:
                # Fallback: abre sem animar se o sizeHint ainda não estabilizou.
                content.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
                card_data["expanded"] = True
                chevron.setText("▾")
                return

            anim = QPropertyAnimation(content, b"maximumHeight", content)
            anim.setDuration(220)
            anim.setStartValue(content.maximumHeight())
            anim.setEndValue(target_height)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            # Após terminar, liberar maximumHeight pra não limitar o conteúdo
            # se a tabela crescer (ex: usuário recebe nova requisição).
            anim.finished.connect(lambda c=content: c.setMaximumHeight(16777215))
            card_data["expand_anim"] = anim  # mantém ref viva
            anim.start()

            card_data["expanded"] = True
            chevron.setText("▾")
        else:
            # RECOLHER — anima maximumHeight de current → 0.
            current_height = content.height()
            anim = QPropertyAnimation(content, b"maximumHeight", content)
            anim.setDuration(200)
            anim.setStartValue(current_height)
            anim.setEndValue(0)
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            card_data["expand_anim"] = anim
            anim.start()

            card_data["expanded"] = False
            chevron.setText("▸")

    def _apply_theme_to_machine_card(self, card_data: dict) -> None:
        """Re-aplica APENAS o QSS dependente do tema em um card de máquina existente.

        Substitui o caminho antigo (destruir e recriar TODOS os 12-18 cards),
        que custava ~500ms+ em A&R / Pinheiro Indústria.

        Otimização extra (Jun/2026): widgets cujo QSS é puramente geométrico
        (font-size, weight — sem cor) NAO precisam ser reaplicados aqui:
          - title, operator_summary: sem cor (herda do palette via property)
          - stat_titles, stat_values: sem cor

        So reaplicamos o que de fato depende de cores do tema:
          - accent (gradient com accent_color)
          - status_label (color: TEXT_MEDIUM)
          - status_combo, botoes (hover/background dependem do tema)
          - table (helper centralizado)
        """
        s = self.scale
        tw = card_data.get("_theme_widgets") or {}
        if not tw:
            # Card construído antes da refatoração — fallback seguro.
            return
        machine_status = str((card_data.get("machine") or {}).get("status") or "funcionando")
        accent_color = (
            theme.WARNING
            if _is_machine_in_maintenance(machine_status)
            else (tw.get("accent_color") or theme.PRIMARY)
        )
        if card_data.get("card") is not None:
            card_data["card"].setStyleSheet(_machine_card_style(s, machine_status))
        if tw.get("accent") is not None:
            tw["accent"].setStyleSheet(_machine_accent_style(accent_color, s))
        if tw.get("status_label") is not None:
            tw["status_label"].setStyleSheet(_machine_status_label_style(s, machine_status))
        if tw.get("status_combo") is not None:
            tw["status_combo"].setStyleSheet(_machine_combo_style(s, tw["status_combo"].currentData()))
        _apply_machine_card_button_styles(tw, s, machine_status)
        for stat_box in tw.get("stat_blocks") or []:
            if stat_box is not None:
                stat_box.setStyleSheet(_machine_stat_box_style(s, machine_status))
        for title_label in tw.get("stat_titles") or []:
            if title_label is not None:
                title_label.setStyleSheet(_machine_stat_title_style(s, machine_status))
        for value_label in tw.get("stat_values") or []:
            if value_label is not None:
                value_label.setStyleSheet(_machine_stat_value_style(s, machine_status))
        if card_data.get("table") is not None:
            self._apply_table_style(card_data["table"], machine_status)
        # summary_label do header (acordeão) — cor segue o accent
        summary_lbl = tw.get("summary_label")
        if summary_lbl is not None:
            summary_fs = max(8, int(10 * s))
            summary_lbl.setStyleSheet(
                f"background:transparent; color:{accent_color};"
                f"font-size:{summary_fs}pt; font-weight:600;"
            )

    def _machine_stat_block(self, title_text: str, value_text: str, status_value: object = "") -> QWidget:
        s = self.scale
        box = QWidget()
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box.setStyleSheet(_machine_stat_box_style(s, status_value))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(max(8, int(10 * s)), max(6, int(8 * s)), max(8, int(10 * s)), max(6, int(8 * s)))
        layout.setSpacing(max(2, int(3 * s)))

        title = QLabel(title_text.upper())
        title.setProperty("muted", "1")
        title.setStyleSheet(_machine_stat_title_style(s, status_value))
        value = QLabel(value_text)
        value.setWordWrap(True)
        value.setStyleSheet(_machine_stat_value_style(s, status_value))
        layout.addWidget(title)
        layout.addWidget(value)
        # Anexa refs no próprio QWidget pra _build_machine_card coletar logo após.
        box._stat_title_lbl = title  # type: ignore[attr-defined]
        box._stat_value_lbl = value  # type: ignore[attr-defined]
        return box

    def _fill_machine_table(self, table: QTableWidget, rows: list[dict]):
        table.setRowCount(0)
        for req in rows:
            row = table.rowCount()
            table.insertRow(row)
            operator_names = [
                str(name or "").strip()
                for name in (req.get("operator_names") or [])
                if str(name or "").strip()
            ]
            helper_names = [
                str(name or "").strip()
                for name in (req.get("helper_names") or [])
                if str(name or "").strip()
            ]
            tooltip_lines: list[str] = []
            if operator_names:
                tooltip_lines.append("Operadores: " + ", ".join(operator_names))
            if helper_names:
                tooltip_lines.append("Ajudantes: " + ", ".join(helper_names))
            tooltip = "\n".join(tooltip_lines)
            values = [
                str(req.get("ped_number") or ""),
                str(req.get("client_name") or "-"),
                str(req.get("vendor_name") or "-"),
                ", ".join(operator_names) if operator_names else "-",
                ", ".join(helper_names) if helper_names else "-",
                _format_elapsed(req.get("production_started_at")),
                _format_weight_kg(req.get("weight")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if tooltip:
                    item.setToolTip(tooltip)
                table.setItem(row, col, item)

    def _selected_stage_row(self, stage: str) -> dict | None:
        panel = self.waiting_receipt_panel if stage == WAITING_RECEIPT_STAGE else self.waiting_queue_panel
        row = panel["table"].currentRow()
        rows = self._stage_rows.get(stage, [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _selected_machine_row(self, machine_id: int) -> tuple[dict | None, dict | None]:
        card = self._machine_cards.get(machine_id)
        if not card:
            return None, None
        # Tabela é criada lazy na 1ª expansão. Se o usuário invocar uma ação
        # antes (cenário defensivo — botões só ficam visíveis no expandido),
        # retornamos sem currentRow.
        table = card.get("table")
        if table is None:
            return None, card["machine"]
        row = table.currentRow()
        rows = card["rows"]
        if 0 <= row < len(rows):
            return rows[row], card["machine"]
        return None, card["machine"]

    def _row_requisition_id(self, req: dict) -> int:
        return int(req.get("source_requisition_id") or req["id"])

    def _row_split_id(self, req: dict) -> int | None:
        split_id = req.get("production_split_id")
        if split_id in (None, ""):
            return None
        return int(split_id)

    def _is_split_row(self, req: dict) -> bool:
        return self._row_split_id(req) is not None

    def _stage_for_row(self, req: dict) -> str | None:
        req_id = self._row_requisition_id(req)
        split_id = self._row_split_id(req)
        for stage in (WAITING_RECEIPT_STAGE, WAITING_QUEUE_STAGE):
            for row in self._stage_rows.get(stage, []):
                if self._row_requisition_id(row) != req_id:
                    continue
                if self._row_split_id(row) != split_id:
                    continue
                return stage
        return None

    def _fifo_stage_message(self, stage: str, first_row: dict) -> str:
        ped = str(first_row.get("ped_number") or "-")
        anchor = (
            _parse_datetime(first_row.get("waiting_since"))
            or _parse_datetime(first_row.get("created_at"))
            or _parse_datetime(first_row.get("emission_date"))
        )
        when_text = f" enviada em {_format_datetime(anchor)}" if anchor else ""
        if stage == WAITING_RECEIPT_STAGE:
            return (
                f"Atenda primeiro a requisicao PED {ped}{when_text} "
                "antes de responder outra em aguardando recebimento."
            )
        return (
            f"Atenda primeiro a requisicao PED {ped}{when_text} "
            "antes de iniciar outra requisicao na fila."
        )

    def _ensure_fifo_stage_row(self, req: dict, stage: str) -> bool:
        rows = self._stage_rows.get(stage, [])
        if not rows:
            return True

        first_row = rows[0]
        if (
            self._row_requisition_id(first_row) == self._row_requisition_id(req)
            and self._row_split_id(first_row) == self._row_split_id(req)
        ):
            return True

        self._show_info(self._fifo_stage_message(stage, first_row))
        return False

    def _ask_partial_weight(self, req: dict) -> float | None:
        remaining_weight = float(req.get("weight") or 0.0)
        total_weight = float(req.get("total_weight") or remaining_weight)
        if remaining_weight <= 0:
            self._show_info("Nao ha saldo pendente para encaminhar.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Quantidade para Producao")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        ped = str(req.get("ped_number") or "-")
        header = QLabel(f"Requisicao PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        question = QLabel("QUANTOS KG VOCE DESEJA PRODUZIR?")
        question.setWordWrap(True)
        question.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(10 * self.scale))}pt;")
        layout.addWidget(question)

        total_label = QLabel(f"KG total da requisicao: {_format_weight_kg(total_weight)}")
        pending_label = QLabel(f"KG pendente para encaminhar: {_format_weight_kg(remaining_weight)}")
        total_label.setProperty("muted", "1")
        pending_label.setProperty("muted", "1")
        total_label.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        pending_label.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(total_label)
        layout.addWidget(pending_label)

        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setMinimum(0.001)
        spin.setMaximum(remaining_weight)
        spin.setValue(remaining_weight)
        spin.setSingleStep(0.100)
        spin.setFixedHeight(max(38, int(44 * self.scale)))
        spin.setStyleSheet(_machine_combo_style(self.scale))
        layout.addWidget(spin)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        def _confirm():
            selected_weight = round(float(spin.value() or 0.0), 3)
            if selected_weight <= 0 or selected_weight > remaining_weight:
                error_lbl.setText("Informe um peso valido dentro do saldo pendente.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_selected_weight", selected_weight)
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return float(dlg.property("_selected_weight") or 0.0)

    def _show_error(self, msg: str):
        self.updated_label.setText("Falha ao atualizar")
        friendly = str(msg or "").strip()
        normalized = friendly.casefold()
        if normalized in {"not found", "404: not found"} or "not found" in normalized:
            friendly = (
                "O servidor da API ainda não carregou o novo fluxo de produção.\n\n"
                "Reinicie o servidor e abra novamente a tela de produção."
            )
        QMessageBox.critical(self, self.dialog_title, friendly)

    def _show_info(self, msg: str):
        QMessageBox.information(self, self.dialog_title, msg)

    def _open_stage_row(self, stage: str, row: int):
        rows = self._stage_rows.get(stage, [])
        if 0 <= row < len(rows):
            self.open_requisition.emit(self._row_requisition_id(rows[row]))

    def _open_machine_row(self, machine_id: int, row: int):
        card = self._machine_cards.get(machine_id)
        if not card:
            return
        rows = card["rows"]
        if 0 <= row < len(rows):
            self.open_requisition.emit(self._row_requisition_id(rows[row]))

    def _open_selected_stage(self, stage: str):
        req = self._selected_stage_row(stage)
        if not req:
            self._show_info("Selecione uma requisição primeiro.")
            return
        self.open_requisition.emit(self._row_requisition_id(req))

    def _open_selected_machine(self, machine_id: int):
        req, _machine = self._selected_machine_row(machine_id)
        if not req:
            self._show_info("Selecione uma requisição no card da máquina.")
            return
        self.open_requisition.emit(self._row_requisition_id(req))

    def _start_production_selection(self, req: dict):
        stage = self._stage_for_row(req)
        if stage and not self._ensure_fifo_stage_row(req, stage):
            return
        machine = self._pick_machine_for_production(req)
        if not machine:
            return
        self._start_production(req, machine=machine)

    def _pick_machine_for_production(self, req: dict) -> dict | None:
        machines = [
            dict(machine)
            for machine in self._machines_data
            if str(machine.get("name") or "").strip()
        ]
        if not machines:
            self._show_error("Nao ha maquinas cadastradas para este destino.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar Maquina")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        ped = str(req.get("ped_number") or "-")
        header = QLabel(f"Requisicao PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        helper = QLabel("Clique na maquina que sera usada nesta producao.")
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(helper)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:12px; }}"
        )
        scroll.setMinimumHeight(max(220, int(250 * self.scale)))
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(max(8, int(10 * self.scale)))

        def _select_machine(selected_machine: dict):
            dlg.setProperty("_machine_id", int(selected_machine["id"]))
            dlg.accept()

        btn_style = (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; text-align:left;"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:12px;"
            f"  padding:0px;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{_rgba(theme.PRIMARY, 80)}; }}"
            f"QPushButton:pressed {{ background:{theme.SELECTION_BG}; }}"
            f"QPushButton:disabled {{ background:{_rgba(theme.BORDER_COLOR, 54)}; color:{theme.TEXT_LIGHT}; border-color:{theme.BORDER_COLOR}; }}"
        )
        for machine in machines:
            machine_name = str(machine.get("name") or "").strip()
            operator_names = [
                str(name or "").strip()
                for name in (machine.get("operators") or [])
                if str(name or "").strip()
            ]
            status_label = "Funcionando" if str(machine.get("status") or "funcionando") == "funcionando" else "Manutencao"
            operator_summary = ", ".join(operator_names) if operator_names else "Sem operadores cadastrados"
            btn = QPushButton()
            btn.setMinimumHeight(max(104, int(126 * self.scale)))
            btn.setStyleSheet(btn_style)
            btn.setEnabled(bool(operator_names))
            btn_layout = QVBoxLayout(btn)
            btn_layout.setContentsMargins(14, 12, 14, 12)
            btn_layout.setSpacing(max(3, int(4 * self.scale)))

            title_lbl = QLabel(machine_name)
            title_lbl.setStyleSheet(
                f"background:transparent; color:{theme.TEXT_DARK};"
                f"font-size:{max(8, int(9 * self.scale))}pt; font-weight:700;"
            )
            title_lbl.setWordWrap(True)
            title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

            status_lbl = QLabel(f"Status: {status_label}")
            status_lbl.setStyleSheet(
                f"background:transparent; color:{theme.TEXT_DARK};"
                f"font-size:{max(8, int(9 * self.scale))}pt; font-weight:700;"
            )
            status_lbl.setWordWrap(True)
            status_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

            operators_lbl = QLabel(f"Operadores: {operator_summary}")
            operators_lbl.setStyleSheet(
                f"background:transparent; color:{theme.TEXT_DARK};"
                f"font-size:{max(8, int(9 * self.scale))}pt; font-weight:700;"
            )
            operators_lbl.setWordWrap(True)
            operators_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

            btn_layout.addWidget(title_lbl)
            btn_layout.addWidget(status_lbl)
            btn_layout.addWidget(operators_lbl)
            btn.clicked.connect(
                lambda checked=False, current_machine=dict(machine): _select_machine(current_machine)
            )
            if operator_names:
                btn.setToolTip(f"Selecionar {machine_name}")
            else:
                btn.setToolTip("Cadastre operadores para liberar esta maquina.")
            content_layout.addWidget(btn)
        content_layout.addStretch()
        layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        machine_id = dlg.property("_machine_id")
        for machine in machines:
            if int(machine["id"]) == int(machine_id):
                return machine
        self._show_error("Nao foi possivel localizar a maquina selecionada.")
        return None

    def _pick_machine_operators(self, machine: dict) -> list[str] | None:
        operator_names = [
            str(name or "").strip()
            for name in (machine.get("operators") or [])
            if str(name or "").strip()
        ]
        if not operator_names:
            self._show_error(
                "Esta maquina nao possui operadores cadastrados.\n\n"
                "Cadastre os operadores em Configuracoes > Cadastro de Maquinas."
            )
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar operadores")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        header = QLabel(f"Máquina: {str(machine.get('name') or '').strip() or '-'}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)
        header.setText(f"Maquina: {str(machine.get('name') or '').strip() or '-'}")

        helper = QLabel("Marque quais operadores cadastrados nesta maquina irao trabalhar nesta requisicao.")
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(helper)

        selection_row = QHBoxLayout()
        selection_row.addStretch()
        btn_all = QPushButton("Todos")
        btn_none = QPushButton("Limpar")
        btn_all.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_none.setStyleSheet(theme.secondary_btn_style(self.scale))
        selection_row.addWidget(btn_all)
        selection_row.addWidget(btn_none)
        layout.addLayout(selection_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:12px; }}"
        )
        scroll.setMinimumHeight(max(160, int(190 * self.scale)))
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(max(6, int(8 * self.scale)))

        checkboxes: list[QCheckBox] = []
        for name in operator_names:
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
            content_layout.addWidget(checkbox)
            checkboxes.append(checkbox)
        content_layout.addStretch()
        layout.addWidget(scroll)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        btn_all.clicked.connect(lambda: [checkbox.setChecked(True) for checkbox in checkboxes])
        btn_none.clicked.connect(lambda: [checkbox.setChecked(False) for checkbox in checkboxes])

        def _confirm():
            selected = [checkbox.text().strip() for checkbox in checkboxes if checkbox.isChecked()]
            if not selected:
                error_lbl.setText("Selecione pelo menos um operador.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_operators", selected)
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return [str(name).strip() for name in (dlg.property("_operators") or []) if str(name).strip()]

    def _assign_selected_to_machine(self, machine_id: int):
        req = (
            self._selected_stage_row(WAITING_RECEIPT_STAGE)
            or self._selected_stage_row(WAITING_QUEUE_STAGE)
        )
        if not req:
            self._show_info(
                "Selecione uma requisicao em 'Aguardando Recebimento' ou 'Aguardando na Fila' "
                "e depois use esta maquina."
            )
            return

        stage = self._stage_for_row(req)
        if stage and not self._ensure_fifo_stage_row(req, stage):
            return

        card = self._machine_cards.get(machine_id)
        if not card:
            self._show_error("Não foi possível localizar o card da máquina selecionada.")
            return

        self._start_production(req, machine=dict(card.get("machine") or {}))

    def _receive_selected(self):
        req = self._selected_stage_row(WAITING_RECEIPT_STAGE)
        if not req:
            self._show_info("Selecione uma requisição em aguardando recebimento.")
            return

        if not self._ensure_fifo_stage_row(req, WAITING_RECEIPT_STAGE):
            return

        box = QMessageBox(self)
        box.setWindowTitle("Confirmar Recebimento")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Como deseja encaminhar esta requisição após o recebimento?")
        btn_queue = box.addButton("Aguardando na fila", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton("Cancelar requisição", QMessageBox.ButtonRole.DestructiveRole)
        btn_close = box.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
        apply_message_box_theme(box)
        # Evita corte de texto dos botões longos nessa confirmação.
        button_widths = fit_dialog_button_widths(
            [btn_queue, btn_cancel, btn_close],
            scale=self.scale,
        )
        button_gap = max(10, int(12 * self.scale))
        horizontal_padding = max(72, int(92 * self.scale))
        box.setMinimumWidth(
            max(
                580,
                int(640 * self.scale),
                sum(button_widths) + button_gap * 2 + horizontal_padding,
            )
        )
        box.exec()
        clicked = box.clickedButton()

        if clicked == btn_queue:
            self._move_to_queue(req)
        elif clicked == btn_cancel:
            self._cancel_to_progress(req)

    def _move_to_queue(self, req: dict):
        if not self._ensure_fifo_stage_row(req, WAITING_RECEIPT_STAGE):
            return
        self._run_action(
            api.update_status,
            self._row_requisition_id(req),
            "aguardando_na_fila",
            _build_production_note(PROD_QUEUED, self.destination),
            success_message="Requisição movida para aguardando na fila.",
        )

    def _pick_machine(
        self,
        *,
        exclude_machine: str | None = None,
        window_title: str = "Selecionar Máquina",
        prompt_text: str = "Escolha a máquina de destino:",
    ) -> str | None:
        excluded = str(exclude_machine or "").strip()
        machine_names = [
            str(machine.get("name") or "").strip()
            for machine in self._machines_data
            if (
                machine.get("name")
                and str(machine.get("name") or "").strip() != excluded
                and not _is_machine_in_maintenance(machine)
            )
        ]
        if not machine_names:
            if excluded:
                self._show_error("Nao ha outra maquina funcionando disponivel para este envio.")
            else:
                self._show_error("Nao ha maquinas funcionando cadastradas para este destino.")
            return None
        if not machine_names:
            if excluded:
                self._show_error("Não há outra máquina disponível para este envio.")
            else:
                self._show_error("Não há máquinas cadastradas para este destino.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle(window_title)
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        lbl = QLabel(prompt_text)
        layout.addWidget(lbl)

        combo = QComboBox()
        combo.addItems(machine_names)
        combo.setStyleSheet(_machine_combo_style(self.scale))
        layout.addWidget(combo)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        btn_ok.clicked.connect(dlg.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(combo.currentText() or "").strip() or None

    def _start_production(self, req: dict, *, machine: dict | None = None):
        if machine is None:
            self._start_production_selection(req)
            return

        machine_name = str(machine.get("name") or "").strip()
        if not machine_name:
            self._show_error("A máquina selecionada não possui um nome válido.")
            return

        if _is_machine_in_maintenance(machine):
            self._show_info(
                f"A maquina {machine_name} esta em manutencao e nao pode receber requisicoes."
            )
            return

        selected_team = self._pick_machine_operators(machine)
        if not selected_team:
            return

        split_id = self._row_split_id(req)
        note = _build_production_note(
            PROD_STARTED,
            self.destination,
            machine=machine_name,
            operators=selected_team["operators"],
            helpers=selected_team["helpers"],
        )
        if split_id is not None:
            self._run_action(
                api.update_production_split_status,
                split_id,
                "em_producao",
                note,
                success_message=f"Parcela enviada para {machine_name}.",
            )
            return

        selected_weight = self._ask_partial_weight(req)
        if selected_weight is None:
            return

        self._run_action(
            api.create_production_split,
            self._row_requisition_id(req),
            {
                "weight": selected_weight,
                "destination": self.destination,
                "machine_name": machine_name,
                "operators": selected_team["operators"],
                "helpers": selected_team["helpers"],
            },
            success_message=f"Parcela de {_format_weight_kg(selected_weight)} enviada para {machine_name}.",
        )

    def _pick_machine_for_production(self, req: dict) -> dict | None:
        machines = [
            dict(machine)
            for machine in self._machines_data
            if str(machine.get("name") or "").strip()
        ]
        if not machines:
            self._show_error("Nao ha maquinas cadastradas para este destino.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar Maquina")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        ped = str(req.get("ped_number") or "-")
        header = QLabel(f"Requisicao PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        helper = QLabel("Clique na maquina que sera usada nesta producao.")
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(helper)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:12px; }}"
        )
        scroll.setMinimumHeight(max(220, int(250 * self.scale)))
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(max(8, int(10 * self.scale)))

        def _select_machine(selected_machine: dict):
            dlg.setProperty("_machine_id", int(selected_machine["id"]))
            dlg.accept()

        btn_style = (
            f"QPushButton {{"
            f"  background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; text-align:left;"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:12px;"
            f"  padding:3px 4px; font-size:{max(8, int(9 * self.scale))}pt; font-weight:700;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.TABLE_ALT_ROW}; border-color:{_rgba(theme.PRIMARY, 80)}; }}"
            f"QPushButton:pressed {{ background:{theme.SELECTION_BG}; }}"
            f"QPushButton:disabled {{ background:{_rgba(theme.BORDER_COLOR, 54)}; color:{theme.TEXT_LIGHT}; border-color:{theme.BORDER_COLOR}; }}"
        )
        maintenance_btn_style = (
            f"QPushButton {{"
            f"  background:{_blend(theme.CARD_BG, theme.WARNING, 18)}; color:{theme.TEXT_DARK}; text-align:left;"
            f"  border:1px solid {_rgba(theme.WARNING, 150)}; border-radius:12px;"
            f"  padding:3px 4px; font-size:{max(8, int(9 * self.scale))}pt; font-weight:700;"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background:{_blend(theme.CARD_BG, theme.WARNING, 26)}; color:{theme.WARNING};"
            f"  border-color:{_rgba(theme.WARNING, 176)};"
            f"}}"
        )
        for machine in machines:
            machine_name = str(machine.get("name") or "").strip()
            operator_names, helper_names = _split_team_members(machine)
            is_maintenance = _is_machine_in_maintenance(machine)
            status_label = "Funcionando" if str(machine.get("status") or "funcionando") == "funcionando" else "Manutencao"
            operator_summary = ", ".join(operator_names) if operator_names else "Nenhum operador cadastrado"
            helper_summary = ", ".join(helper_names) if helper_names else "Nenhum ajudante cadastrado"
            btn = QPushButton(
                f"{machine_name}\n"
                f"Status: {status_label}\n"
                f"Operadores: {operator_summary}\n"
                f"Ajudantes: {helper_summary}"
            )
            btn.setMinimumHeight(max(78, int(92 * self.scale)))
            btn.setStyleSheet(maintenance_btn_style if is_maintenance else btn_style)
            btn.setEnabled(bool(operator_names) and not is_maintenance)
            btn.clicked.connect(
                lambda checked=False, current_machine=dict(machine): _select_machine(current_machine)
            )
            if is_maintenance:
                btn.setToolTip("Esta maquina esta em manutencao e nao pode receber requisicoes.")
            elif operator_names:
                btn.setToolTip(f"Selecionar {machine_name}")
            else:
                btn.setToolTip("Cadastre pelo menos um operador para liberar esta maquina.")
            content_layout.addWidget(btn)
        content_layout.addStretch()
        layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        machine_id = dlg.property("_machine_id")
        for machine in machines:
            if int(machine["id"]) == int(machine_id):
                return machine
        self._show_error("Nao foi possivel localizar a maquina selecionada.")
        return None

    def _pick_machine_operators(self, machine: dict) -> dict[str, list[str]] | None:
        team_members = _machine_team_members(machine)
        operator_names = [member["name"] for member in team_members if member["role"] == WORKER_ROLE_OPERADOR]
        if not operator_names:
            self._show_error(
                "Esta maquina nao possui operadores cadastrados.\n\n"
                "Cadastre a equipe em Configuracoes > Cadastro de Maquinas."
            )
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar equipe")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        machine_name = str(machine.get("name") or "").strip() or "-"
        header = QLabel(f"Maquina: {machine_name}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        helper = QLabel(
            "Marque quem vai trabalhar nesta requisicao. E obrigatorio selecionar pelo menos um operador."
        )
        helper.setWordWrap(True)
        helper.setProperty("muted", "1")
        helper.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
        layout.addWidget(helper)

        selection_row = QHBoxLayout()
        selection_row.addStretch()
        btn_all = QPushButton("Todos")
        btn_none = QPushButton("Limpar")
        btn_all.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_none.setStyleSheet(theme.secondary_btn_style(self.scale))
        selection_row.addWidget(btn_all)
        selection_row.addWidget(btn_none)
        layout.addLayout(selection_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.BORDER_COLOR}; background:{theme.CARD_BG}; border-radius:12px; }}"
        )
        scroll.setMinimumHeight(max(160, int(190 * self.scale)))
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(max(6, int(8 * self.scale)))

        checkboxes: list[tuple[QCheckBox, str, str]] = []
        for member in team_members:
            role_label = WORKER_ROLE_LABELS.get(member["role"], "OPERADOR")
            checkbox = QCheckBox(f"{member['name']} ({role_label})")
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"background:transparent; font-size:{max(8, int(9 * self.scale))}pt;")
            content_layout.addWidget(checkbox)
            checkboxes.append((checkbox, member["name"], member["role"]))
        content_layout.addStretch()
        layout.addWidget(scroll)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        btn_all.clicked.connect(lambda: [checkbox.setChecked(True) for checkbox, _name, _role in checkboxes])
        btn_none.clicked.connect(lambda: [checkbox.setChecked(False) for checkbox, _name, _role in checkboxes])

        def _confirm():
            selected_operators = [
                name
                for checkbox, name, role in checkboxes
                if checkbox.isChecked() and role == WORKER_ROLE_OPERADOR
            ]
            selected_helpers = [
                name
                for checkbox, name, role in checkboxes
                if checkbox.isChecked() and role == WORKER_ROLE_AJUDANTE
            ]
            if not selected_operators:
                error_lbl.setText("Selecione pelo menos um operador.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty(
                "_team_selection",
                {
                    "operators": selected_operators,
                    "helpers": selected_helpers,
                },
            )
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        selected_team = dlg.property("_team_selection") or {}
        return {
            "operators": [
                str(name).strip()
                for name in (selected_team.get("operators") or [])
                if str(name).strip()
            ],
            "helpers": [
                str(name).strip()
                for name in (selected_team.get("helpers") or [])
                if str(name).strip()
            ],
        }

    def _send_queue_selected_to_machine(self):
        req = self._selected_stage_row(WAITING_QUEUE_STAGE)
        if not req:
            self._show_info("Selecione uma requisição na grade aguardando na fila.")
            return
        self._start_production_selection(req)

    def _cancel_selected_stage(self, stage: str):
        req = self._selected_stage_row(stage)
        if not req:
            self._show_info("Selecione uma requisição primeiro.")
            return
        self._cancel_to_progress(req)

    def _cancel_to_progress(self, req: dict):
        if self._is_split_row(req):
            regroup_all = self._ask_split_cancel_mode()
            if regroup_all is None:
                return
            if regroup_all:
                self._run_action(
                    api.regroup_production_splits,
                    self._row_requisition_id(req),
                    success_message="Requisição reagrupada com sucesso.",
                )
                return
            self._cancel_split_only(req)
            return
        reason = self._ask_cancel_reason()
        if reason is None:
            return

        self._run_action(
            api.update_status,
            self._row_requisition_id(req),
            "cancelada",
            _build_production_note(PROD_CANCELED, self.destination, reason=reason),
            success_message="Requisição retornada para rascunho.",
        )

    def _finish_selected_machine(self, machine_id: int):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return
        if not ask_confirmation(
            self,
            "Finalizar Produção",
            "Deseja finalizar a produção desta requisição?",
            yes_text="Sim",
            no_text="Não",
        ):
            return

        machine_name = str(machine.get("name") or "")
        split_id = self._row_split_id(req)
        self._run_action(
            self._finalize_and_invoice_requisition,
            split_id if split_id is not None else self._row_requisition_id(req),
            machine_name,
            split_id is not None,
            success_message="Parcela finalizada." if split_id is not None else "Requisição finalizada e faturada.",
        )

    def _find_machine_by_number(self, target_number: int) -> dict | None:
        for machine in self._machines_data:
            if _machine_number_prefix(str(machine.get("name") or "").strip()) == int(target_number):
                return dict(machine)
        return None

    def _forward_selected_machine(self, machine_id: int, action: dict | None = None):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return

        action = dict(action or {})
        source_machine = str(machine.get("name") or "").strip()
        target_mode = str(action.get("target_mode") or "picker").strip().lower()
        target_machine_data: dict | None = None

        if target_mode == "fixed":
            target_number = int(action.get("target_number") or 0)
            if target_number <= 0:
                self._show_error("A configuração da máquina de destino está inválida.")
                return
            target_machine_data = self._find_machine_by_number(target_number)
        else:
            target_machine = self._pick_machine(
                exclude_machine=source_machine,
                window_title=str(action.get("window_title") or "Selecionar Máquina"),
                prompt_text=str(
                    action.get("prompt_text")
                    or f"Escolha a máquina de destino (origem: {source_machine}):"
                ),
            )
            if not target_machine:
                return
            target_machine_data = next(
                (
                    dict(machine_item)
                    for machine_item in self._machines_data
                    if str(machine_item.get("name") or "").strip() == target_machine
                ),
                None,
            )

        if not target_machine_data:
            self._show_error("Nao foi possivel localizar a maquina de destino selecionada.")
            return

        target_machine = str(target_machine_data.get("name") or "").strip()
        if _is_machine_in_maintenance(target_machine_data):
            self._show_info(
                f"A maquina {target_machine} esta em manutencao e nao pode receber requisicoes."
            )
            return

        selected_team = self._pick_machine_operators(target_machine_data)
        if not selected_team:
            return

        split_id = self._row_split_id(req)
        self._run_action(
            self._transfer_machine_requisition,
            split_id if split_id is not None else self._row_requisition_id(req),
            source_machine,
            target_machine,
            selected_team,
            split_id is not None,
            success_message=(
                f"Parcela enviada para {target_machine}."
                if split_id is not None
                else f"Requisição enviada para {target_machine}."
            ),
        )

    def _send_selected_machine_to_dobra(self, machine_id: int):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return

        source_machine = str(machine.get("name") or "").strip()
        target_machine = self._pick_machine(
            exclude_machine=source_machine,
            window_title="Enviar para dobra",
            prompt_text=f"Escolha a máquina de dobra de destino (origem: {source_machine}):",
        )
        if not target_machine:
            return

        target_machine_data = next(
            (
                dict(machine_item)
                for machine_item in self._machines_data
                if str(machine_item.get("name") or "").strip() == target_machine
            ),
            None,
        )
        if not target_machine_data:
            self._show_error("Nao foi possivel localizar a maquina de dobra selecionada.")
            return
        if _is_machine_in_maintenance(target_machine_data):
            self._show_info(
                f"A maquina {target_machine} esta em manutencao e nao pode receber requisicoes."
            )
            return

        selected_team = self._pick_machine_operators(target_machine_data)
        if not selected_team:
            return

        split_id = self._row_split_id(req)
        self._run_action(
            self._transfer_machine_requisition,
            split_id if split_id is not None else self._row_requisition_id(req),
            source_machine,
            target_machine,
            selected_team,
            split_id is not None,
            success_message=f"Parcela enviada para dobra na máquina {target_machine}." if split_id is not None else f"Requisição enviada para dobra na máquina {target_machine}.",
        )

    def _transfer_machine_requisition(
        self,
        req_id: int,
        source_machine: str,
        target_machine: str,
        selected_team: dict[str, list[str]],
        is_split: bool = False,
    ):
        queue_note = _build_production_note(PROD_RETURNED_QUEUE, self.destination, machine=source_machine)
        start_note = _build_production_note(
            PROD_STARTED,
            self.destination,
            machine=target_machine,
            operators=selected_team.get("operators") or [],
            helpers=selected_team.get("helpers") or [],
            transfer=True,
        )
        if is_split:
            api.update_production_split_status(req_id, "aguardando_na_fila", queue_note)
            api.update_production_split_status(req_id, "em_producao", start_note)
            return
        api.update_status(req_id, "aguardando_na_fila", queue_note)
        api.update_status(req_id, "em_producao", start_note)

    def _finalize_and_invoice_requisition(self, req_id: int, machine_name: str, is_split: bool = False):
        # Por regra de negocio (Jun/2026): ao finalizar producao, status vai
        # direto para FINALIZADO. O servidor processa a transicao a partir do
        # _PROD_FINISHED na note. FATURADO foi reaproveitado para registrar o
        # envio do vendedor para producao (timeline historica, nao status atual).
        note = _build_production_note(PROD_FINISHED, self.destination, machine=machine_name)
        if is_split:
            api.update_production_split_status(req_id, "finalizado", note)
            return
        api.update_status(req_id, "em_andamento", note)

    def _return_selected_machine_to_queue(self, machine_id: int):
        req, machine = self._selected_machine_row(machine_id)
        if not req or not machine:
            self._show_info("Selecione uma requisição em produção dentro do card da máquina.")
            return
        if self._is_split_row(req):
            regroup_all = self._ask_split_cancel_mode()
            if regroup_all is None:
                return
            if regroup_all:
                self._run_action(
                    api.regroup_production_splits,
                    self._row_requisition_id(req),
                    success_message="Requisição reagrupada com sucesso.",
                )
                return
            self._cancel_split_only(req, source_machine=str(machine.get("name") or ""))
            return
        if not ask_confirmation(
            self,
            "Devolver para Fila",
            "Deseja devolver esta requisição para aguardando na fila?",
            yes_text="Sim",
            no_text="Não",
        ):
            return

        self._run_action(
            api.update_status,
            self._row_requisition_id(req),
            "aguardando_na_fila",
            _build_production_note(PROD_RETURNED_QUEUE, self.destination, machine=str(machine.get("name") or "")),
            success_message="Requisição devolvida para aguardando na fila.",
        )

    def _update_machine_status(self, machine_id: int, combo: QComboBox):
        status_value = str(combo.currentData() or "funcionando")
        status_label = combo.currentText()
        card = self._machine_cards.get(machine_id) or {}
        current_status = str((card.get("machine") or {}).get("status") or "")
        if current_status == status_value:
            self._show_info("O status da máquina já está definido dessa forma.")
            return
        self._run_action(
            api.update_production_machine_status,
            machine_id,
            status_value,
            success_message=f"Status da máquina atualizado para {status_label}.",
        )

    def _change_delivery_selected_stage(self, stage: str):
        req = self._selected_stage_row(stage)
        if not req:
            self._show_info("Selecione uma requisição primeiro.")
            return
        self._change_delivery_date(req)

    def _change_delivery_selected_machine(self, machine_id: int):
        req, _machine = self._selected_machine_row(machine_id)
        if not req:
            self._show_info("Selecione uma requisição no card da máquina.")
            return
        self._change_delivery_date(req)

    def _change_delivery_date(self, req: dict):
        result = self._ask_delivery_date(req)
        if result is None:
            return
        new_date, reason = result
        self._run_action(
            self._update_delivery_date_and_waiting_receipt,
            self._row_requisition_id(req),
            new_date,
            reason,
            success_message=(
                "Prazo de entrega alterado. "
                "Status atualizado para aguardando recebimento e vendedor notificado."
            ),
        )

    def _update_delivery_date_and_waiting_receipt(self, req_id: int, new_date: str, reason: str) -> dict:
        # Usa endpoint transacional novo (commit 884d995++) — antes eram 2
        # chamadas HTTP sequenciais; se a segunda falhasse a req ficava em
        # prazo_alterado quando deveria voltar a aguardando_recebimento.
        return api.update_delivery_date_and_resend(req_id, new_date, reason)

    def _ask_delivery_date(self, req: dict) -> tuple[str, str] | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Alterar Prazo de Entrega")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        ped = str(req.get("ped_number") or "")
        header = QLabel(f"Requisição PED #{ped}")
        header.setStyleSheet(f"background:transparent; font-weight:800; font-size:{max(9, int(11 * self.scale))}pt;")
        layout.addWidget(header)

        lbl_date = QLabel("Novo prazo de entrega:")
        layout.addWidget(lbl_date)

        date_edit = QDateEdit()
        date_edit.setDisplayFormat("dd/MM/yyyy")
        date_edit.setCalendarPopup(True)
        date_edit.setFixedHeight(max(34, int(38 * self.scale)))
        date_edit.setStyleSheet(theme.input_style(self.scale))
        current = QDate.fromString(str(req.get("delivery_date") or "")[:10], "yyyy-MM-dd")
        date_edit.setDate(current if current.isValid() else QDate.currentDate())
        layout.addWidget(date_edit)

        lbl_reason = QLabel("Motivo da alteração:")
        layout.addWidget(lbl_reason)

        input_reason = QTextEdit()
        input_reason.setPlaceholderText("Descreva o motivo da alteração do prazo...")
        input_reason.setMinimumHeight(max(96, int(120 * self.scale)))
        input_reason.setStyleSheet(theme.input_style(self.scale))
        layout.addWidget(input_reason)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        def _confirm():
            normalized = " ".join(input_reason.toPlainText().split())
            if len(normalized) < 5:
                error_lbl.setText("Informe um motivo com pelo menos 5 caracteres.")
                error_lbl.setVisible(True)
                return
            dlg.setProperty("_new_date", date_edit.date().toString("yyyy-MM-dd"))
            dlg.setProperty("_reason", normalized)
            dlg.accept()

        btn_ok.clicked.connect(_confirm)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        new_date = str(dlg.property("_new_date") or "")
        reason = str(dlg.property("_reason") or "")
        if not new_date:
            return None
        return new_date, reason

    def _ask_cancel_reason(self) -> str | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Cancelar Requisição")
        dlg.setModal(True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QDialog QWidget {{ background:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
            f"QLabel {{ background:transparent; color:{theme.TEXT_DARK}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(max(8, int(10 * self.scale)))

        lbl = QLabel("Selecione o motivo do cancelamento:")
        layout.addWidget(lbl)

        combo_reason = QComboBox()
        for value, text in _configured_cancel_reason_options():
            combo_reason.addItem(text, value)
        combo_reason.setStyleSheet(_machine_combo_style(self.scale))
        layout.addWidget(combo_reason)

        lbl_other = QLabel("Descreva o motivo:")
        layout.addWidget(lbl_other)

        input_reason = QTextEdit()
        input_reason.setPlaceholderText("Descreva o motivo...")
        input_reason.setMinimumHeight(max(96, int(120 * self.scale)))
        input_reason.setStyleSheet(theme.input_style(self.scale))
        layout.addWidget(input_reason)

        error_lbl = QLabel("")
        error_lbl.setStyleSheet(f"background:transparent; color:{theme.DANGER}; font-size:{max(8, int(9 * self.scale))}pt;")
        error_lbl.setVisible(False)
        layout.addWidget(error_lbl)

        def _on_reason_changed():
            is_other = str(combo_reason.currentData() or "") == CANCEL_REASON_OTHER
            lbl_other.setVisible(is_other)
            input_reason.setVisible(is_other)

        combo_reason.currentIndexChanged.connect(lambda _=None: _on_reason_changed())
        _on_reason_changed()

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(theme.secondary_btn_style(self.scale))
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton("Confirmar")
        btn_ok.setStyleSheet(theme.primary_btn_style(self.scale))
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        def _confirm_reason():
            selected = str(combo_reason.currentData() or "")
            if selected == CANCEL_REASON_OTHER:
                normalized = " ".join(input_reason.toPlainText().split())
                if len(normalized) < 5:
                    error_lbl.setText("Descreva o motivo com pelo menos 5 caracteres.")
                    error_lbl.setVisible(True)
                    return
                final_reason = normalized.upper()
            else:
                final_reason = selected
            dlg.setProperty("_cancel_reason", final_reason)
            dlg.accept()

        btn_ok.clicked.connect(_confirm_reason)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return str(dlg.property("_cancel_reason") or "")

    def _ask_split_cancel_mode(self) -> bool | None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Cancelar Parcela")
        box.setText("VOCÊ DESEJA REAGRUPAR TODA A REQUISIÇÃO")
        box.setTextFormat(Qt.TextFormat.PlainText)

        yes_button = box.addButton("SIM", QMessageBox.ButtonRole.YesRole)
        no_button = box.addButton("NÃO", QMessageBox.ButtonRole.NoRole)

        box.setDefaultButton(no_button)
        apply_message_box_theme(box)
        box.exec()

        clicked = box.clickedButton()
        if clicked == yes_button:
            return True
        if clicked == no_button:
            return False
        return None

    def _cancel_split_only(self, req: dict, *, source_machine: str = ""):
        split_id = self._row_split_id(req)
        if split_id is None:
            return
        reason = self._ask_cancel_reason()
        if reason is None:
            return
        self._run_action(
            api.update_production_split_status,
            split_id,
            "aguardando_na_fila",
            _build_production_note(
                PROD_CANCELED,
                self.destination,
                machine=source_machine,
                reason=reason,
            ),
            success_message="Parcela cancelada e liberada para novo envio à máquina.",
        )

    def _run_action(self, fn, *args, success_message: str):
        worker = ActionWorker(fn, *args)
        thread = QThread()
        cb = UiCallback()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(cb.result)
        worker.error.connect(cb.error)
        cb.result.connect(lambda _: self._after_action(success_message))
        cb.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        worker._cb = cb
        thread.start()
        self._threads.append((thread, worker))

    def _after_action(self, success_message: str):
        self.refresh()
        self._show_info(success_message)

    def _apply_table_style(self, table: QTableWidget, status_value: object = "") -> None:
        s = self.scale
        table.setStyleSheet(_machine_table_qss(self.scale, status_value))
        _apply_machine_table_palette(table, status_value)

    def apply_theme(self) -> None:
        """Reaplica tema na ProductionView (A&R / Pinheiro Indústria).

        Otimizado em duas frentes:
        1) QPalette no root cascateia cores fundamentais (Window, Text,
           Highlight, etc.) para os ~200-360 widgets filhos em microssegundos,
           sem regerar setStyleSheet em cada um.
        2) _apply_theme_to_machine_card pula widgets cujo QSS nao depende do
           tema (title/subtitle/stat_titles/stat_values — sao font-size only).

        Backgrounds combinados em uma unica chamada de setStyleSheet.
        """
        s = self.scale
        bg = theme.CONTENT_BG

        # QPalette no root — cores base cascateiam para filhos sem palette propria
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window,          QColor(bg))
        pal.setColor(QPalette.ColorRole.WindowText,      QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.Text,            QColor(theme.TEXT_DARK))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.TEXT_MEDIUM))
        pal.setColor(QPalette.ColorRole.Base,            QColor(theme.PANEL_SURFACE_BG))
        pal.setColor(QPalette.ColorRole.Highlight,       QColor(theme.PANEL_NEON_PRIMARY))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.PANEL_TEXT_PRIMARY))
        self.setPalette(pal)

        # QSS view-level: cobre TODOS os ~90 botões dos cards em uma única
        # chamada (em vez de 4-5 setStyleSheet × N cards = 70-90 chamadas).
        self.setStyleSheet(self._build_view_stylesheet(s, bg))
        self._page_content.setStyleSheet(f"background:{bg};")

        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        for panel in (self.waiting_receipt_panel, self.waiting_queue_panel):
            self._apply_table_style(panel["table"])

        # Re-estiliza os machine_cards EXISTENTES (sem destruir + recriar).
        # A versão antiga chamava _populate_machine_cards() — recriava 12-18
        # cards, ~200-360 widgets + QGraphicsDropShadow novos (~500ms+).
        # Agora usamos refs em "_theme_widgets" para reaplicar QSS in-place.
        for card_data in self._machine_cards.values():
            self._apply_theme_to_machine_card(card_data)

        self.update()



