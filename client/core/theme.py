"""
Sistema de temas — Ferragens Pinheiro.

Uso:
    from ..core import theme
    color = theme.CARD_BG          # sempre retorna a paleta ativa
    theme.set_dark(True)           # troca para modo escuro
    theme.is_dark                  # bool

Troca de tema em tempo de execução:
    Após chamar set_dark(), faça um soft-restart da MainWindow para que
    todos os widgets sejam reconstruídos com as novas cores.
"""
import sys

from PySide6.QtGui import QColor

# ── Paleta clara (padrão) ─────────────────────────────────────────────────────

_LIGHT: dict = {
    # Sidebar / rodapé
    "SIDEBAR_BG":        "#0F3D6E",
    "SIDEBAR_HOVER":     "#16508F",
    "SIDEBAR_ACTIVE":    "#1E5FA8",
    "SIDEBAR_INDICATOR": "#22D3EE",
    "FOOTER_BG":         "#0F3D6E",

    # Área de conteúdo
    "CONTENT_BG":        "#EAF3FF",
    "CARD_BG":           "#FFFFFF",
    "INPUT_BG":          "#F9FCFF",
    "SURFACE_SOFT":      "#EFF6FF",

    # Primária
    "PRIMARY":           "#0F5BD7",
    "PRIMARY_HOVER":     "#0284C7",
    "PRIMARY_LIGHT":     "#38BDF8",

    # Bordas / tabelas
    "BORDER_COLOR":      "#C8D9EC",
    "TABLE_HEADER_BG":   "#154E86",
    "TABLE_ALT_ROW":     "#F3F8FF",
    "TABLE_BORDER":      "#C8D9EC",
    "SELECTION_BG":      "#DBEEFF",

    # Texto
    "TEXT_DARK":         "#102033",
    "TEXT_MEDIUM":       "#61758E",
    "TEXT_LIGHT":        "#7F91A8",
    "TEXT_LABEL":        "#97A9BD",
    "TEXT_WHITE":        "#FFFFFF",

    # Semânticas
    "DANGER":            "#E11D48",
    "SUCCESS":           "#16A34A",
    "WARNING":           "#D97706",

    # Status de requisição
    "STATUS_COLORS": {
        "em_andamento":           "#38BDF8",
        "prazo_alterado":         "#A855F7",
        "entregue":               "#22C55E",
        "aguardando_recebimento": "#F59E0B",
        "aguardando_na_fila":     "#D97706",
        "aguardando_faturamento": "#B45309",
        "em_producao":            "#0F5BD7",
        "faturado":               "#16A34A",
        "cancelada":              "#E11D48",
    },
    "PANEL_CARD_BG_START":   "#F8FCFF",
    "PANEL_CARD_BG_MID":     "#EEF6FF",
    "PANEL_CARD_BG_END":     "#F8FBFF",
    "PANEL_SURFACE_BG":      "#FFFFFF",
    "PANEL_SURFACE_ALT":     "#EDF5FF",
    "PANEL_BORDER_SOFT":     "#C5D7EB",
    "PANEL_TEXT_PRIMARY":    "#102033",
    "PANEL_TEXT_MUTED":      "#61758E",
    "PANEL_NEON_PRIMARY":    "#0EA5E9",
    "PANEL_NEON_SECONDARY":  "#F43F5E",
    "PANEL_NEON_TERTIARY":   "#84CC16",
    "PANEL_TABLE_HEADER_START": "#123E6F",
    "PANEL_TABLE_HEADER_END":   "#1B5C97",
    "PANEL_SHADOW":          "#0F172A",

    # ── Tokens: Toast de notificação ──────────────────────────────────────────
    "TOAST_BG":          "#E7ECF3",       # fundo do card (mais escuro para contraste)
    "TOAST_BORDER":      "#D9E1EC",       # borda externa
    "TOAST_TITLE":       "#1E2A3A",       # texto do título
    "TOAST_BODY":        "#475569",       # texto da mensagem (escurecido p/ contraste)
    "TOAST_MUTED":       "#64748B",       # timestamp / secundário
    "TOAST_CLOSE_FG":    "#94A0B2",       # ícone fechar
    "TOAST_CLOSE_HV":    "#F5F7FA",       # hover fundo fechar
    "TOAST_SHADOW":      "rgba(0,44,109,0.12)",  # sombra suave azul

    # ── Tokens: Drawer de notificações ───────────────────────────────────────
    "DRAWER_BG":         "#F5F7FA",       # fundo geral
    "DRAWER_HEADER":     "#FFFFFF",       # fundo do cabeçalho
    "DRAWER_CARD":       "#FFFFFF",       # fundo de cada card
    "DRAWER_BORDER":     "#D9E1EC",       # bordas dos cards
    "DRAWER_TITLE":      "#1E2A3A",       # título dos cards
    "DRAWER_BODY":       "#475569",       # mensagem dos cards (escurecido p/ contraste)
    "DRAWER_MUTED":      "#64748B",       # timestamp / secundário
    "DRAWER_SCROLL":     "#D9E1EC",       # handle da barra de rolagem
    "DRAWER_OVERLAY":    "rgba(0,44,109,0.30)",  # overlay semitransparente
    "DRAWER_SHADOW":     "rgba(0,44,109,0.14)",  # sombra lateral
}

# ── Paleta escura (modo dark) ─────────────────────────────────────────────────

_DARK: dict = {
    # Sidebar / rodapé
    "SIDEBAR_BG":        "#08111F",
    "SIDEBAR_HOVER":     "#0E1B2D",
    "SIDEBAR_ACTIVE":    "#13304A",
    "SIDEBAR_INDICATOR": "#22D3EE",
    "FOOTER_BG":         "#08111F",

    # Área de conteúdo
    "CONTENT_BG":        "#06101B",
    "CARD_BG":           "#0B1324",
    "INPUT_BG":          "#0B1324",
    "SURFACE_SOFT":      "#10203A",

    # Primária
    "PRIMARY":           "#22D3EE",
    "PRIMARY_HOVER":     "#67E8F9",
    "PRIMARY_LIGHT":     "#A5F3FC",

    # Bordas / tabelas
    "BORDER_COLOR":      "#24364F",
    "TABLE_HEADER_BG":   "#1C3B63",
    "TABLE_ALT_ROW":     "#10203A",
    "TABLE_BORDER":      "#24364F",
    "SELECTION_BG":      "#133452",

    # Texto
    "TEXT_DARK":         "#F8FAFC",
    "TEXT_MEDIUM":       "#93A4BD",
    "TEXT_LIGHT":        "#7187A3",
    "TEXT_LABEL":        "#5E728A",
    "TEXT_WHITE":        "#FFFFFF",

    # Semânticas
    "DANGER":            "#FB7185",
    "SUCCESS":           "#4ADE80",
    "WARNING":           "#FBBF24",

    # Status de requisição
    "STATUS_COLORS": {
        "em_andamento":           "#67E8F9",
        "prazo_alterado":         "#C084FC",
        "entregue":               "#4ADE80",
        "aguardando_recebimento": "#FBBF24",
        "aguardando_na_fila":     "#F59E0B",
        "aguardando_faturamento": "#D97706",
        "em_producao":            "#22D3EE",
        "faturado":               "#4ADE80",
        "cancelada":              "#FB7185",
    },
    "PANEL_CARD_BG_START":   "#07111E",
    "PANEL_CARD_BG_MID":     "#0A1628",
    "PANEL_CARD_BG_END":     "#111F36",
    "PANEL_SURFACE_BG":      "#0B1324",
    "PANEL_SURFACE_ALT":     "#10203A",
    "PANEL_BORDER_SOFT":     "#24364F",
    "PANEL_TEXT_PRIMARY":    "#F8FAFC",
    "PANEL_TEXT_MUTED":      "#93A4BD",
    "PANEL_NEON_PRIMARY":    "#22D3EE",
    "PANEL_NEON_SECONDARY":  "#FB7185",
    "PANEL_NEON_TERTIARY":   "#A3E635",
    "PANEL_TABLE_HEADER_START": "#12233E",
    "PANEL_TABLE_HEADER_END":   "#1C3B63",
    "PANEL_SHADOW":          "#020817",

    # ── Tokens: Toast de notificação ──────────────────────────────────────────
    "TOAST_BG":          "#1E293B",
    "TOAST_BORDER":      "#334155",
    "TOAST_TITLE":       "#F1F5F9",
    "TOAST_BODY":        "#CBD5E1",
    "TOAST_MUTED":       "#94A3B8",
    "TOAST_CLOSE_FG":    "#64748B",
    "TOAST_CLOSE_HV":    "#334155",
    "TOAST_SHADOW":      "rgba(0,0,0,0.40)",

    # ── Tokens: Drawer de notificações ───────────────────────────────────────
    "DRAWER_BG":         "#0F172A",
    "DRAWER_HEADER":     "#1E293B",
    "DRAWER_CARD":       "#1E293B",
    "DRAWER_BORDER":     "rgba(255,255,255,0.08)",
    "DRAWER_TITLE":      "#F1F5F9",
    "DRAWER_BODY":       "#CBD5E1",
    "DRAWER_MUTED":      "#94A3B8",
    "DRAWER_SCROLL":     "rgba(255,255,255,0.15)",
    "DRAWER_OVERLAY":    "rgba(0,0,0,0.50)",
    "DRAWER_SHADOW":     "rgba(0,0,0,0.50)",
}

# ── STATUS_LABELS (igual em ambos os modos) ───────────────────────────────────

STATUS_LABELS: dict = {
    "em_andamento":           "Rascunho",
    "prazo_alterado":         "Prazo Alterado",
    "entregue":               "Entregue",
    "aguardando_recebimento": "Aguardando Recebimento",
    "aguardando_na_fila":     "Aguardando na Fila",
    "aguardando_faturamento": "Aguardando Faturamento",
    "em_producao":            "Em Producao",
    "faturado":               "Faturado",
    "cancelada":              "Cancelada",
}

# ── Fontes (invariantes) ──────────────────────────────────────────────────────

FONT_PRIMARY  = "Inter"
FONT_FALLBACK = "Segoe UI"

# ── Estado de modo e inicialização ────────────────────────────────────────────

is_dark: bool = False


def _apply_palette(palette: dict) -> None:
    """Escreve todos os tokens da paleta no namespace deste módulo."""
    m = sys.modules[__name__]
    for key, value in palette.items():
        setattr(m, key, value)


def _sync_external_panel_tokens() -> None:
    token_map = {
        "client.views.dashboard_view": {
            "_DASH_CARD_BG_START": "PANEL_CARD_BG_START",
            "_DASH_CARD_BG_MID": "PANEL_CARD_BG_MID",
            "_DASH_CARD_BG_END": "PANEL_CARD_BG_END",
            "_DASH_SURFACE_BG": "PANEL_SURFACE_BG",
            "_DASH_SURFACE_ALT": "PANEL_SURFACE_ALT",
            "_DASH_BORDER_SOFT": "PANEL_BORDER_SOFT",
            "_DASH_TEXT_PRIMARY": "PANEL_TEXT_PRIMARY",
            "_DASH_TEXT_MUTED": "PANEL_TEXT_MUTED",
            "_DASH_TABLE_HEADER_START": "PANEL_TABLE_HEADER_START",
            "_DASH_TABLE_HEADER_END": "PANEL_TABLE_HEADER_END",
        },
        "client.views.requisition_form": {
            "_REQ_CARD_BG_START": "PANEL_CARD_BG_START",
            "_REQ_CARD_BG_MID": "PANEL_CARD_BG_MID",
            "_REQ_CARD_BG_END": "PANEL_CARD_BG_END",
            "_REQ_SURFACE_BG": "PANEL_SURFACE_BG",
            "_REQ_SURFACE_ALT": "PANEL_SURFACE_ALT",
            "_REQ_BORDER_SOFT": "PANEL_BORDER_SOFT",
            "_REQ_TEXT_PRIMARY": "PANEL_TEXT_PRIMARY",
            "_REQ_TEXT_MUTED": "PANEL_TEXT_MUTED",
            "_REQ_NEON_PRIMARY": "PANEL_NEON_PRIMARY",
            "_REQ_NEON_SECONDARY": "PANEL_NEON_SECONDARY",
            "_REQ_NEON_TERTIARY": "PANEL_NEON_TERTIARY",
            "_REQ_TABLE_HEADER_START": "PANEL_TABLE_HEADER_START",
            "_REQ_TABLE_HEADER_END": "PANEL_TABLE_HEADER_END",
        },
        "client.widgets.item_table": {
            "_REQ_SURFACE_BG": "PANEL_SURFACE_BG",
            "_REQ_SURFACE_ALT": "PANEL_SURFACE_ALT",
            "_REQ_BORDER_SOFT": "PANEL_BORDER_SOFT",
            "_REQ_TEXT_PRIMARY": "PANEL_TEXT_PRIMARY",
            "_REQ_TEXT_MUTED": "PANEL_TEXT_MUTED",
            "_REQ_NEON_PRIMARY": "PANEL_NEON_PRIMARY",
            "_REQ_NEON_SECONDARY": "PANEL_NEON_SECONDARY",
            "_REQ_TABLE_HEADER_START": "PANEL_TABLE_HEADER_START",
            "_REQ_TABLE_HEADER_END": "PANEL_TABLE_HEADER_END",
        },
    }
    theme_module = sys.modules[__name__]
    for module_name, mapping in token_map.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr_name, theme_attr in mapping.items():
            setattr(module, attr_name, getattr(theme_module, theme_attr))


def set_dark(dark: bool) -> None:
    """
    Alterna entre modo escuro e claro.
    Após chamar, faça um soft-restart da MainWindow para reconstruir os widgets.
    """
    global is_dark
    is_dark = dark
    _apply_palette(_DARK if dark else _LIGHT)
    _sync_external_panel_tokens()


# Aplica paleta clara como padrão ao importar o módulo
_apply_palette(_LIGHT)
_sync_external_panel_tokens()


# ── Helpers de estilo ─────────────────────────────────────────────────────────

def rgba(color: str, alpha: int) -> str:
    parsed = QColor(color)
    return f"rgba({parsed.red()}, {parsed.green()}, {parsed.blue()}, {alpha})"


def status_style(status: str) -> str:
    color = STATUS_COLORS.get(status, TEXT_MEDIUM)  # noqa: F821
    return (
        f"background:{rgba(color, 46)}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"border:1px solid {rgba(color, 155)}; border-radius:12px;"
        f"padding:4px 12px; font-weight:700;"
    )


def card_style() -> str:
    return (
        f"background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"stop:0 {PANEL_CARD_BG_START}, stop:0.55 {PANEL_CARD_BG_MID}, stop:1 {PANEL_CARD_BG_END});"
        f"border:1px solid {rgba(PANEL_NEON_PRIMARY, 72)}; border-radius:18px;"
    )


def input_style(scale: float = 1.0) -> str:
    fs = max(9, int(10 * scale))
    radius = max(12, int(14 * scale))
    return (
        f"QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{PANEL_SURFACE_BG}; border:1px solid {PANEL_BORDER_SOFT}; border-radius:{radius}px;"  # noqa: F821
        f"  padding:8px 12px; font-size:{fs}pt; color:{PANEL_TEXT_PRIMARY}; font-weight:600;"  # noqa: F821
        f"  selection-background-color:{rgba(PANEL_NEON_PRIMARY, 64)}; selection-color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QLineEdit, QTextEdit {{"
        f"  placeholder-text-color:{TEXT_LABEL};"  # noqa: F821
        f"}}"
        f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, "
        f"QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"  border:1px solid {PANEL_NEON_SECONDARY};"  # noqa: F821
        f"}}"
        f"QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover, "
        f"QSpinBox:hover, QDoubleSpinBox:hover {{"
        f"  border:1px solid {PANEL_NEON_PRIMARY};"  # noqa: F821
        f"}}"
        f"QComboBox::drop-down, QDateEdit::drop-down {{"
        f"  border:none; width:24px;"
        f"}}"
        f"QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  selection-background-color:{rgba(PANEL_NEON_PRIMARY, 56)}; selection-color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
    )


def primary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(10 * scale))
    fg = "#04111F" if is_dark else TEXT_WHITE
    return (
        f"QPushButton {{"
        f"  background:{PRIMARY}; color:{fg}; border:none; border-radius:14px;"  # noqa: F821
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:800;"
        f"}}"
        f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"  # noqa: F821
        f"QPushButton:pressed {{ background:{rgba(PRIMARY, 220)}; color:{fg}; }}"  # noqa: F821
        f"QPushButton:disabled {{ background:{rgba(PANEL_BORDER_SOFT, 90)}; color:{TEXT_LIGHT}; }}"
    )


def secondary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {rgba(PANEL_NEON_PRIMARY, 110)};"  # noqa: F821
        f"  border-radius:14px; padding:9px 18px; font-size:{fs}pt; font-weight:700;"
        f"}}"
        f"QPushButton:hover {{ background:{PANEL_SURFACE_ALT}; border-color:{PANEL_NEON_SECONDARY}; }}"  # noqa: F821
        f"QPushButton:pressed {{ background:{rgba(PANEL_NEON_PRIMARY, 26)}; }}"
        f"QPushButton:disabled {{ background:{rgba(PANEL_BORDER_SOFT, 36)}; color:{PANEL_TEXT_MUTED}; border-color:{PANEL_BORDER_SOFT}; }}"  # noqa: F821
    )


def danger_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(10 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DANGER}; color:{TEXT_WHITE}; border:none; border-radius:14px;"  # noqa: F821
        f"  padding:9px 18px; font-size:{fs}pt; font-weight:800;"
        f"}}"
        f"QPushButton:hover {{ background:{QColor(DANGER).lighter(112).name()}; }}"
        f"QPushButton:pressed {{ background:{QColor(DANGER).darker(118).name()}; }}"
        f"QPushButton:disabled {{ background:{rgba(DANGER, 90)}; color:{TEXT_WHITE}; }}"
    )


def neon_table_qss(scale: float = 1.0) -> str:
    """QSS unificado para tabelas com identidade neon (Painel Gerencial /
    Nova Requisição / Central de Pedidos). Lê PANEL_* em runtime para
    refletir tema claro/escuro corrente."""
    header_fg = TEXT_WHITE if not is_dark else PANEL_TEXT_PRIMARY  # noqa: F821
    fs_item = max(8, int(9 * scale))
    fs_head = max(7, int(8 * scale))
    return (
        f"QTableWidget {{"
        f"  border:none; outline:none; background:{PANEL_SURFACE_BG};"  # noqa: F821
        f"  alternate-background-color:{PANEL_SURFACE_ALT};"  # noqa: F821
        f"  color:{PANEL_TEXT_PRIMARY}; border-radius:14px;"  # noqa: F821
        f"  gridline-color:transparent; font-size:{fs_item}pt;"
        f"}}"
        f"QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {PANEL_TABLE_HEADER_START},"  # noqa: F821
        f"    stop:1 {PANEL_TABLE_HEADER_END});"  # noqa: F821
        f"  color:{header_fg}; padding:9px 10px;"
        f"  font-weight:800; font-size:{fs_head}pt; border:none;"
        f"}}"
        f"QHeaderView::section:hover {{ background:{PANEL_NEON_SECONDARY}; }}"  # noqa: F821
        f"QTableWidget::item {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"  padding:7px 6px; border-bottom:1px solid {rgba(PANEL_NEON_PRIMARY, 26)};"  # noqa: F821
        f"}}"
        f"QTableWidget::item:alternate {{"
        f"  background:{PANEL_SURFACE_ALT}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QTableWidget::item:selected {{"
        f"  background:{rgba(PANEL_NEON_PRIMARY, 56)};"  # noqa: F821
        f"  color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
    )


def apply_neon_table_palette(table) -> None:
    """Aplica QPalette neon — necessário no Windows pois o Qt ignora QSS
    em algumas regiões do QTableView (especialmente alternate-row)."""
    from PySide6.QtGui import QColor, QPalette
    pal = table.palette()
    pal.setColor(QPalette.ColorRole.Base, QColor(PANEL_SURFACE_BG))  # noqa: F821
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL_SURFACE_ALT))  # noqa: F821
    pal.setColor(QPalette.ColorRole.Text, QColor(PANEL_TEXT_PRIMARY))  # noqa: F821
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(PANEL_TEXT_PRIMARY))  # noqa: F821
    pal.setColor(QPalette.ColorRole.Highlight, QColor(rgba(PANEL_NEON_PRIMARY, 60)))  # noqa: F821
    table.setPalette(pal)
    table.viewport().setAutoFillBackground(True)


def global_style() -> str:
    table_header_fg = TEXT_WHITE if not is_dark else PANEL_TEXT_PRIMARY  # noqa: F821
    return (
        f"QMainWindow {{"
        f"  background:{CONTENT_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog {{"
        f"  background-color:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog QWidget {{"
        f"  background-color:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QWidget {{"
        f"  color:{TEXT_DARK};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QLabel {{ background:transparent; color:{TEXT_DARK}; }}"  # noqa: F821
        f"QFrame {{ color:{TEXT_DARK}; }}"  # noqa: F821
        f"QToolTip {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {rgba(PANEL_NEON_PRIMARY, 96)};"  # noqa: F821
        f"  padding:6px 10px; border-radius:10px;"
        f"}}"
        f"QAbstractItemView {{"
        f"  outline:none; alternate-background-color:{TABLE_ALT_ROW};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PANEL_TABLE_HEADER_START}, stop:1 {PANEL_TABLE_HEADER_END});"
        f"  color:{table_header_fg}; padding:8px 10px;"
        f"  border:none; font-weight:700;"
        f"}}"
        f"QTableCornerButton::section {{"
        f"  background:{PANEL_TABLE_HEADER_START}; border:none;"  # noqa: F821
        f"}}"
        f"QTabBar::tab {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_MUTED}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  padding:8px 14px; margin-right:4px; border-top-left-radius:10px; border-top-right-radius:10px;"
        f"}}"
        f"QTabBar::tab:selected {{ background:{PANEL_SURFACE_ALT}; color:{PANEL_TEXT_PRIMARY}; border-color:{PANEL_NEON_PRIMARY}; }}"  # noqa: F821
        f"QScrollBar:vertical {{ width:10px; background:transparent; margin:2px; }}"
        f"QScrollBar::handle:vertical {{"
        f"  background:{BORDER_COLOR}; border-radius:5px; min-height:36px;"  # noqa: F821
        f"}}"
        f"QScrollBar::handle:vertical:hover {{ background:{PRIMARY_LIGHT}; }}"  # noqa: F821
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        f"QScrollBar:horizontal {{ height:10px; background:transparent; margin:2px; }}"
        f"QScrollBar::handle:horizontal {{ background:{BORDER_COLOR}; border-radius:5px; }}"  # noqa: F821
        f"QScrollBar::handle:horizontal:hover {{ background:{PRIMARY_LIGHT}; }}"  # noqa: F821
        f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        f"QCalendarWidget QWidget {{ background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; }}"  # noqa: F821
        f"QCalendarWidget QAbstractItemView:enabled {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"  selection-background-color:{PRIMARY}; selection-color:{TEXT_WHITE};"  # noqa: F821
        f"}}"
        f"QCalendarWidget QToolButton {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:none; padding:6px; border-radius:10px;"  # noqa: F821
        f"}}"
        f"QCalendarWidget QToolButton:hover {{ background:{PANEL_SURFACE_ALT}; }}"  # noqa: F821
        f"QCalendarWidget #qt_calendar_navigationbar {{"
        f"  background:{PANEL_SURFACE_ALT}; border-bottom:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"}}"
        f"QMessageBox {{"
        f"  background-color:{CARD_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"  # noqa: F821
        f"}}"
        f"QMessageBox QWidget {{ background-color:{CARD_BG}; color:{TEXT_DARK}; }}"  # noqa: F821
        f"QMessageBox QLabel {{ background-color:transparent; color:{TEXT_DARK}; padding:2px 0; }}"  # noqa: F821
        f"QMessageBox QFrame {{ background-color:{CARD_BG}; border:none; }}"  # noqa: F821
        f"QMessageBox QDialogButtonBox {{ background-color:{CARD_BG}; border-top:1px solid {BORDER_COLOR}; padding-top:10px; }}"  # noqa: F821
        f"QMessageBox QPushButton, QMessageBox QDialogButtonBox QPushButton {{"
        f"  background:{SIDEBAR_BG}; background-color:{SIDEBAR_BG}; background-image:none;"  # noqa: F821
        f"  color:{TEXT_WHITE}; border:1px solid {SIDEBAR_BG};"  # noqa: F821
        f"  border-radius:8px; padding:7px 16px; min-width:84px; min-height:34px; font-weight:600;"
        f"}}"
        f"QMessageBox QPushButton:hover, QMessageBox QDialogButtonBox QPushButton:hover {{"
        f"  background:{SIDEBAR_HOVER}; background-color:{SIDEBAR_HOVER}; border-color:{SIDEBAR_HOVER};"  # noqa: F821
        f"}}"
        f"QMessageBox QPushButton:pressed, QMessageBox QDialogButtonBox QPushButton:pressed {{"
        f"  background:{SIDEBAR_ACTIVE}; background-color:{SIDEBAR_ACTIVE}; border-color:{SIDEBAR_ACTIVE};"  # noqa: F821
        f"}}"
        f"QMessageBox QPushButton:focus, QMessageBox QPushButton:default,"
        f"QMessageBox QDialogButtonBox QPushButton:focus, QMessageBox QDialogButtonBox QPushButton:default {{"
        f"  background:{SIDEBAR_BG}; background-color:{SIDEBAR_BG}; color:{TEXT_WHITE}; border:1px solid {SIDEBAR_ACTIVE};"  # noqa: F821
        f"}}"
        f"QMessageBox QPushButton:disabled, QMessageBox QDialogButtonBox QPushButton:disabled {{"
        f"  background-color:{BORDER_COLOR}; color:{TEXT_LIGHT}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"}}"
        f"QInputDialog, QFileDialog, QColorDialog {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QInputDialog QWidget, QFileDialog QWidget, QColorDialog QWidget {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QInputDialog QLabel, QFileDialog QLabel, QColorDialog QLabel {{"
        f"  background-color:transparent; color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QInputDialog QLineEdit, QInputDialog QTextEdit, QInputDialog QPlainTextEdit,"
        f"QFileDialog QLineEdit, QFileDialog QTextEdit, QFileDialog QPlainTextEdit,"
        f"QColorDialog QLineEdit, QColorDialog QTextEdit, QColorDialog QPlainTextEdit {{"
        f"  background-color:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"  # noqa: F821
        f"  padding:7px 10px; color:{TEXT_DARK};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QInputDialog QComboBox, QFileDialog QComboBox, QColorDialog QComboBox,"
        f"QColorDialog QSpinBox, QColorDialog QDoubleSpinBox {{"
        f"  background-color:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"  # noqa: F821
        f"  padding:7px 10px; color:{TEXT_DARK};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QFileDialog QListView, QFileDialog QTreeView, QFileDialog QTableView {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  alternate-background-color:{TABLE_ALT_ROW};"  # noqa: F821
        f"}}"
        f"QFileDialog QSplitter::handle {{ background:{BORDER_COLOR}; }}"  # noqa: F821
        f"QInputDialog QDialogButtonBox, QFileDialog QDialogButtonBox, QColorDialog QDialogButtonBox {{"
        f"  background-color:{CARD_BG}; border-top:1px solid {BORDER_COLOR}; padding-top:10px;"  # noqa: F821
        f"}}"
        f"QInputDialog QPushButton, QFileDialog QPushButton, QColorDialog QPushButton {{"
        f"  background:{SIDEBAR_BG}; background-color:{SIDEBAR_BG}; background-image:none;"  # noqa: F821
        f"  color:{TEXT_WHITE}; border:1px solid {SIDEBAR_BG};"  # noqa: F821
        f"  border-radius:8px; padding:7px 16px; min-width:84px; min-height:34px; font-weight:600;"
        f"}}"
        f"QInputDialog QPushButton:hover, QFileDialog QPushButton:hover, QColorDialog QPushButton:hover {{"
        f"  background:{SIDEBAR_HOVER}; background-color:{SIDEBAR_HOVER}; border-color:{SIDEBAR_HOVER};"  # noqa: F821
        f"}}"
        f"QInputDialog QPushButton:pressed, QFileDialog QPushButton:pressed, QColorDialog QPushButton:pressed {{"
        f"  background:{SIDEBAR_ACTIVE}; background-color:{SIDEBAR_ACTIVE}; border-color:{SIDEBAR_ACTIVE};"  # noqa: F821
        f"}}"
        f"QInputDialog QPushButton:focus, QInputDialog QPushButton:default,"
        f"QFileDialog QPushButton:focus, QFileDialog QPushButton:default,"
        f"QColorDialog QPushButton:focus, QColorDialog QPushButton:default {{"
        f"  background:{SIDEBAR_BG}; background-color:{SIDEBAR_BG}; color:{TEXT_WHITE}; border:1px solid {SIDEBAR_ACTIVE};"  # noqa: F821
        f"}}"
        f"QInputDialog QPushButton:disabled, QFileDialog QPushButton:disabled, QColorDialog QPushButton:disabled {{"
        f"  background-color:{BORDER_COLOR}; color:{TEXT_LIGHT}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"}}"
        f"QLineEdit, QTextEdit, QPlainTextEdit {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  border-radius:12px; padding:8px 12px;"
        f"  selection-background-color:{rgba(PANEL_NEON_PRIMARY, 64)}; selection-color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{"
        f"  border:1px solid {PANEL_NEON_SECONDARY};"  # noqa: F821
        f"}}"
        f"QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only {{"
        f"  background:{PANEL_SURFACE_ALT}; color:{PANEL_TEXT_MUTED};"  # noqa: F821
        f"}}"
        f"QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  border-radius:12px; padding:8px 12px;"
        f"  selection-background-color:{rgba(PANEL_NEON_PRIMARY, 64)}; selection-color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"  border:1px solid {PANEL_NEON_SECONDARY};"  # noqa: F821
        f"}}"
        f"QComboBox::drop-down, QDateEdit::drop-down {{"
        f"  border:none; width:24px;"
        f"}}"
        f"QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  selection-background-color:{rgba(PANEL_NEON_PRIMARY, 56)}; selection-color:{PANEL_TEXT_PRIMARY};"  # noqa: F821
        f"}}"
        f"QCheckBox {{ spacing:8px; }}"
        f"QCheckBox::indicator {{"
        f"  width:16px; height:16px; border-radius:4px; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  background:{PANEL_SURFACE_BG};"  # noqa: F821
        f"}}"
        f"QCheckBox::indicator:checked {{"
        f"  background:{PRIMARY}; border:1px solid {PRIMARY};"  # noqa: F821
        f"}}"
        f"QSlider::groove:horizontal {{"
        f"  height:6px; background:{BORDER_COLOR}; border-radius:3px;"  # noqa: F821
        f"}}"
        f"QSlider::handle:horizontal {{"
        f"  background:{PRIMARY}; width:16px; margin:-6px 0; border-radius:8px;"  # noqa: F821
        f"}}"
        f"QSlider::sub-page:horizontal {{ background:{PRIMARY_LIGHT}; border-radius:3px; }}"  # noqa: F821
        f"QMenu {{"
        f"  background:{PANEL_SURFACE_BG}; color:{PANEL_TEXT_PRIMARY}; border:1px solid {PANEL_BORDER_SOFT};"  # noqa: F821
        f"  border-radius:10px; padding:6px;"
        f"}}"
        f"QMenu::item {{ padding:8px 12px; border-radius:6px; }}"
        f"QMenu::item:selected {{ background:{rgba(PANEL_NEON_PRIMARY, 56)}; color:{PANEL_TEXT_PRIMARY}; }}"  # noqa: F821
        f"QStatusBar {{ background:{FOOTER_BG}; color:{TEXT_WHITE}; }}"  # noqa: F821
        # ── Propriedades dinâmicas — permitem auto-tema sem rebuild ──────────────
        f"QFrame[theme_bg='card'] {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {PANEL_CARD_BG_START}, stop:0.55 {PANEL_CARD_BG_MID}, stop:1 {PANEL_CARD_BG_END});"
        f"  border:1px solid {rgba(PANEL_NEON_PRIMARY, 64)};"
        f"}}"
        f"QFrame[theme_bg='card_bordered'] {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {PANEL_CARD_BG_START}, stop:0.55 {PANEL_CARD_BG_MID}, stop:1 {PANEL_CARD_BG_END});"
        f"  border:1px solid {rgba(PANEL_NEON_SECONDARY, 78)};"
        f"}}"
        f"QFrame[theme_bg='separator'] {{ background:{BORDER_COLOR}; border:none; }}"  # noqa: F821
        f"QLabel[muted='1'] {{ color:{TEXT_MEDIUM}; background:transparent; }}"  # noqa: F821
        f"QLabel[accent='1'] {{ color:{PANEL_NEON_PRIMARY}; background:transparent; }}"  # noqa: F821
    )
