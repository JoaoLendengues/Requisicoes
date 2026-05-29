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

# ── Paleta clara (padrão) ─────────────────────────────────────────────────────

_LIGHT: dict = {
    # Sidebar / rodapé
    "SIDEBAR_BG":        "#002C6D",
    "SIDEBAR_HOVER":     "#003B8F",
    "SIDEBAR_ACTIVE":    "#0057D8",
    "SIDEBAR_INDICATOR": "#2D7FF9",
    "FOOTER_BG":         "#002C6D",

    # Área de conteúdo
    "CONTENT_BG":        "#F5F7FA",
    "CARD_BG":           "#FFFFFF",
    "INPUT_BG":          "#FFFFFF",
    "SURFACE_SOFT":      "#F8FBFF",

    # Primária
    "PRIMARY":           "#003B8F",
    "PRIMARY_HOVER":     "#0057D8",
    "PRIMARY_LIGHT":     "#2D7FF9",

    # Bordas / tabelas
    "BORDER_COLOR":      "#D9E1EC",
    "TABLE_HEADER_BG":   "#003B8F",
    "TABLE_ALT_ROW":     "#F8FAFD",
    "TABLE_BORDER":      "#D9E1EC",
    "SELECTION_BG":      "#DCE9FF",

    # Texto
    "TEXT_DARK":         "#1E2A3A",
    "TEXT_MEDIUM":       "#6B778C",
    "TEXT_LIGHT":        "#7A8798",
    "TEXT_LABEL":        "#94A0B2",
    "TEXT_WHITE":        "#FFFFFF",

    # Semânticas
    "DANGER":            "#D64545",
    "SUCCESS":           "#2DBE4E",
    "WARNING":           "#F3A01B",

    # Status de requisição
    "STATUS_COLORS": {
        "em_andamento":           "#2D7FF9",
        "prazo_alterado":         "#7C3AED",
        "aguardando_recebimento": "#F3A01B",
        "aguardando_na_fila":     "#C7790A",
        "aguardando_faturamento": "#A16207",
        "em_producao":            "#0057D8",
        "faturado":               "#2DBE4E",
        "cancelada":              "#D64545",
    },

    # ── Tokens: Toast de notificação ──────────────────────────────────────────
    "TOAST_BG":          "#E7ECF3",       # fundo do card (mais escuro para contraste)
    "TOAST_BORDER":      "#D9E1EC",       # borda externa
    "TOAST_TITLE":       "#1E2A3A",       # texto do título
    "TOAST_BODY":        "#6B778C",       # texto da mensagem
    "TOAST_MUTED":       "#94A0B2",       # timestamp / secundário
    "TOAST_CLOSE_FG":    "#94A0B2",       # ícone fechar
    "TOAST_CLOSE_HV":    "#F5F7FA",       # hover fundo fechar
    "TOAST_SHADOW":      "rgba(0,44,109,0.12)",  # sombra suave azul

    # ── Tokens: Drawer de notificações ───────────────────────────────────────
    "DRAWER_BG":         "#F5F7FA",       # fundo geral
    "DRAWER_HEADER":     "#FFFFFF",       # fundo do cabeçalho
    "DRAWER_CARD":       "#FFFFFF",       # fundo de cada card
    "DRAWER_BORDER":     "#D9E1EC",       # bordas dos cards
    "DRAWER_TITLE":      "#1E2A3A",       # título dos cards
    "DRAWER_BODY":       "#6B778C",       # mensagem dos cards
    "DRAWER_MUTED":      "#94A0B2",       # timestamp / secundário
    "DRAWER_SCROLL":     "#D9E1EC",       # handle da barra de rolagem
    "DRAWER_OVERLAY":    "rgba(0,44,109,0.30)",  # overlay semitransparente
    "DRAWER_SHADOW":     "rgba(0,44,109,0.14)",  # sombra lateral
}

# ── Paleta escura (modo dark) ─────────────────────────────────────────────────

_DARK: dict = {
    # Sidebar / rodapé
    "SIDEBAR_BG":        "#0F1929",
    "SIDEBAR_HOVER":     "#1A2640",
    "SIDEBAR_ACTIVE":    "#1D3461",
    "SIDEBAR_INDICATOR": "#3B82F6",
    "FOOTER_BG":         "#0F1929",

    # Área de conteúdo
    "CONTENT_BG":        "#111827",
    "CARD_BG":           "#1E293B",
    "INPUT_BG":          "#1E293B",
    "SURFACE_SOFT":      "#162032",

    # Primária
    "PRIMARY":           "#2563EB",
    "PRIMARY_HOVER":     "#3B82F6",
    "PRIMARY_LIGHT":     "#60A5FA",

    # Bordas / tabelas
    "BORDER_COLOR":      "#334155",
    "TABLE_HEADER_BG":   "#1D3461",
    "TABLE_ALT_ROW":     "#162032",
    "TABLE_BORDER":      "#334155",
    "SELECTION_BG":      "#1E3A5F",

    # Texto
    "TEXT_DARK":         "#F1F5F9",
    "TEXT_MEDIUM":       "#94A3B8",
    "TEXT_LIGHT":        "#64748B",
    "TEXT_LABEL":        "#475569",
    "TEXT_WHITE":        "#FFFFFF",

    # Semânticas
    "DANGER":            "#EF4444",
    "SUCCESS":           "#22C55E",
    "WARNING":           "#EAB308",

    # Status de requisição
    "STATUS_COLORS": {
        "em_andamento":           "#60A5FA",
        "prazo_alterado":         "#A78BFA",
        "aguardando_recebimento": "#FBBF24",
        "aguardando_na_fila":     "#F59E0B",
        "aguardando_faturamento": "#D97706",
        "em_producao":            "#3B82F6",
        "faturado":               "#22C55E",
        "cancelada":              "#EF4444",
    },

    # ── Tokens: Toast de notificação ──────────────────────────────────────────
    "TOAST_BG":          "#1E293B",
    "TOAST_BORDER":      "#334155",
    "TOAST_TITLE":       "#F1F5F9",
    "TOAST_BODY":        "#94A3B8",
    "TOAST_MUTED":       "#475569",
    "TOAST_CLOSE_FG":    "#64748B",
    "TOAST_CLOSE_HV":    "#334155",
    "TOAST_SHADOW":      "rgba(0,0,0,0.40)",

    # ── Tokens: Drawer de notificações ───────────────────────────────────────
    "DRAWER_BG":         "#0F172A",
    "DRAWER_HEADER":     "#1E293B",
    "DRAWER_CARD":       "#1E293B",
    "DRAWER_BORDER":     "rgba(255,255,255,0.08)",
    "DRAWER_TITLE":      "#F1F5F9",
    "DRAWER_BODY":       "#64748B",
    "DRAWER_MUTED":      "#475569",
    "DRAWER_SCROLL":     "rgba(255,255,255,0.15)",
    "DRAWER_OVERLAY":    "rgba(0,0,0,0.50)",
    "DRAWER_SHADOW":     "rgba(0,0,0,0.50)",
}

# ── STATUS_LABELS (igual em ambos os modos) ───────────────────────────────────

STATUS_LABELS: dict = {
    "em_andamento":           "Em Andamento",
    "prazo_alterado":         "Prazo Alterado",
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


def set_dark(dark: bool) -> None:
    """
    Alterna entre modo escuro e claro.
    Após chamar, faça um soft-restart da MainWindow para reconstruir os widgets.
    """
    global is_dark
    is_dark = dark
    _apply_palette(_DARK if dark else _LIGHT)


# Aplica paleta clara como padrão ao importar o módulo
_apply_palette(_LIGHT)


# ── Helpers de estilo ─────────────────────────────────────────────────────────

def status_style(status: str) -> str:
    color = STATUS_COLORS.get(status, TEXT_MEDIUM)  # noqa: F821
    return (
        f"background:{color}; color:{TEXT_WHITE}; border-radius:8px; "  # noqa: F821
        f"padding:4px 12px; font-weight:600;"
    )


def card_style() -> str:
    return (
        f"background:{CARD_BG}; border:1px solid {BORDER_COLOR}; "  # noqa: F821
        f"border-radius:8px;"
    )


def input_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"  # noqa: F821
        f"  padding:7px 10px; font-size:{fs}pt; color:{TEXT_DARK};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QLineEdit, QTextEdit {{"
        f"  placeholder-text-color:{TEXT_LABEL};"  # noqa: F821
        f"}}"
        f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, "
        f"QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"  border:1px solid {PRIMARY_LIGHT};"  # noqa: F821
        f"}}"
        f"QComboBox::drop-down, QDateEdit::drop-down {{"
        f"  border:none; width:24px;"
        f"}}"
        f"QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
    )


def primary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{PRIMARY}; color:{TEXT_WHITE}; border:none; border-radius:8px;"  # noqa: F821
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"  # noqa: F821
        f"QPushButton:pressed {{ background:{SIDEBAR_BG}; }}"  # noqa: F821
        f"QPushButton:disabled {{ background:#AAB8CE; color:#EEF2F8; }}"
    )


def secondary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{CARD_BG}; color:{PRIMARY}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  border-radius:8px; padding:7px 16px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:{SELECTION_BG}; border-color:{PRIMARY_LIGHT}; }}"  # noqa: F821
        f"QPushButton:pressed {{ background:#CFE0FF; }}"
    )


def danger_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DANGER}; color:{TEXT_WHITE}; border:none; border-radius:8px;"  # noqa: F821
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:#BF3636; }}"
        f"QPushButton:pressed {{ background:#A92F2F; }}"
    )


def global_style() -> str:
    return (
        f"QMainWindow {{"
        f"  background:{CONTENT_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog QWidget {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QWidget {{"
        f"  color:{TEXT_DARK};"  # noqa: F821
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QLabel {{ background:transparent; color:{TEXT_DARK}; }}"  # noqa: F821
        f"QFrame {{ color:{TEXT_DARK}; }}"  # noqa: F821
        f"QToolTip {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  padding:6px 10px; border-radius:8px;"
        f"}}"
        f"QAbstractItemView {{"
        f"  outline:none; alternate-background-color:{TABLE_ALT_ROW};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QHeaderView::section {{"
        f"  background:{TABLE_HEADER_BG}; color:{TEXT_WHITE}; padding:8px 10px;"  # noqa: F821
        f"  border:none; font-weight:600;"
        f"}}"
        f"QTableCornerButton::section {{"
        f"  background:{TABLE_HEADER_BG}; border:none;"  # noqa: F821
        f"}}"
        f"QTabBar::tab {{"
        f"  background:{CARD_BG}; color:{TEXT_MEDIUM}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  padding:8px 14px; margin-right:4px; border-top-left-radius:8px; border-top-right-radius:8px;"
        f"}}"
        f"QTabBar::tab:selected {{ background:{PRIMARY}; color:{TEXT_WHITE}; border-color:{PRIMARY}; }}"  # noqa: F821
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
        f"QCalendarWidget QWidget {{ background:{CARD_BG}; color:{TEXT_DARK}; }}"  # noqa: F821
        f"QCalendarWidget QAbstractItemView:enabled {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK};"  # noqa: F821
        f"  selection-background-color:{PRIMARY}; selection-color:{TEXT_WHITE};"  # noqa: F821
        f"}}"
        f"QCalendarWidget QToolButton {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:none; padding:6px; border-radius:8px;"  # noqa: F821
        f"}}"
        f"QCalendarWidget QToolButton:hover {{ background:{SELECTION_BG}; }}"  # noqa: F821
        f"QCalendarWidget #qt_calendar_navigationbar {{"
        f"  background:{SURFACE_SOFT}; border-bottom:1px solid {BORDER_COLOR};"  # noqa: F821
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
        f"  background:{INPUT_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  border-radius:8px; padding:7px 10px;"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{"
        f"  border:1px solid {PRIMARY_LIGHT};"  # noqa: F821
        f"}}"
        f"QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only {{"
        f"  background:{SURFACE_SOFT}; color:{TEXT_MEDIUM};"  # noqa: F821
        f"}}"
        f"QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{INPUT_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  border-radius:8px; padding:7px 10px;"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"  border:1px solid {PRIMARY_LIGHT};"  # noqa: F821
        f"}}"
        f"QComboBox::drop-down, QDateEdit::drop-down {{"
        f"  border:none; width:24px;"
        f"}}"
        f"QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"  # noqa: F821
        f"}}"
        f"QCheckBox {{ spacing:8px; }}"
        f"QCheckBox::indicator {{"
        f"  width:16px; height:16px; border-radius:4px; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  background:{CARD_BG};"  # noqa: F821
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
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"  # noqa: F821
        f"  border-radius:8px; padding:6px;"
        f"}}"
        f"QMenu::item {{ padding:8px 12px; border-radius:6px; }}"
        f"QMenu::item:selected {{ background:{SELECTION_BG}; color:{TEXT_DARK}; }}"  # noqa: F821
        f"QStatusBar {{ background:{FOOTER_BG}; color:{TEXT_WHITE}; }}"  # noqa: F821
        # ── Propriedades dinâmicas — permitem auto-tema sem rebuild ──────────────
        f"QFrame[theme_bg='card'] {{ background:{CARD_BG}; border:none; }}"  # noqa: F821
        f"QFrame[theme_bg='card_bordered'] {{ background:{CARD_BG}; border:1px solid {BORDER_COLOR}; }}"  # noqa: F821
        f"QFrame[theme_bg='separator'] {{ background:{BORDER_COLOR}; border:none; }}"  # noqa: F821
        f"QLabel[muted='1'] {{ color:{TEXT_MEDIUM}; background:transparent; }}"  # noqa: F821
        f"QLabel[accent='1'] {{ color:{PRIMARY}; background:transparent; }}"  # noqa: F821
    )
