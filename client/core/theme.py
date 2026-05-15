# ── Paleta — Dark Mode ────────────────────────────────────────────────────────
SIDEBAR_BG        = "#0B1120"   # quase preto azulado
SIDEBAR_HOVER     = "#161E30"
SIDEBAR_ACTIVE    = "#1D4ED8"   # azul royal
SIDEBAR_INDICATOR = "#60A5FA"   # azul claro

CONTENT_BG        = "#0F172A"   # fundo principal (slate-900)
CARD_BG           = "#1E293B"   # cards / painéis (slate-800)
INPUT_BG          = "#0F172A"   # fundo dos campos

PRIMARY           = "#3B82F6"   # azul-500 (mais brilhante no dark)
PRIMARY_HOVER     = "#2563EB"

BORDER_COLOR      = "#334155"   # slate-700
TABLE_HEADER_BG   = "#0B1120"
TABLE_ALT_ROW     = "#243044"
TABLE_BORDER      = "#2A3F6F"
SELECTION_BG      = "#1E3A6E"   # linha selecionada em tabelas

TEXT_DARK         = "#F1F5F9"   # texto principal (quase branco)
TEXT_MEDIUM       = "#CBD5E1"   # texto secundário
TEXT_LIGHT        = "#94A3B8"   # texto auxiliar / placeholders
TEXT_LABEL        = "#64748B"   # labels menores
TEXT_WHITE        = "#FFFFFF"

DANGER            = "#EF4444"
SUCCESS           = "#22C55E"

# ── Status ────────────────────────────────────────────────────────────────────
STATUS_COLORS = {
    "rascunho":            "#6B7280",
    "emitida":             "#2563EB",
    "recebida_producao":   "#0EA5E9",
    "em_fabricacao":       "#F59E0B",
    "pronta":              "#8B5CF6",
    "em_rota":             "#14B8A6",
    "aguardando_retirada": "#EAB308",
    "concluida":           "#22C55E",
    "cancelada":           "#EF4444",
}

STATUS_LABELS = {
    "rascunho":            "Rascunho",
    "emitida":             "Emitida",
    "recebida_producao":   "Recebida",
    "em_fabricacao":       "Em Fabricação",
    "pronta":              "Pronta",
    "em_rota":             "Em Rota",
    "aguardando_retirada": "Ag. Retirada",
    "concluida":           "Concluída",
    "cancelada":           "Cancelada",
}


def status_style(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6B7280")
    return (
        f"background:{color}; color:#fff; border-radius:4px; "
        f"padding:3px 10px; font-weight:bold;"
    )


# ── Stylesheets ───────────────────────────────────────────────────────────────
def card_style() -> str:
    return (
        f"background:{CARD_BG}; border:1px solid {BORDER_COLOR}; "
        f"border-radius:8px;"
    )


def input_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:5px;"
        f"  padding:5px 8px; font-size:{fs}pt; color:{TEXT_DARK};"
        f"}}"
        f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{"
        f"  border:1px solid {PRIMARY};"
        f"}}"
        f"QComboBox::drop-down {{ border:none; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  selection-background-color:{PRIMARY};"
        f"}}"
        f"QDateEdit::drop-down {{ border:none; }}"
        f"QDateEdit QAbstractItemView {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK};"
        f"}}"
    )


def primary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{PRIMARY}; color:#fff; border:none; border-radius:6px;"
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background:#1a40c0; }}"
        f"QPushButton:disabled {{ background:#2d4070; color:#64748b; }}"
    )


def secondary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:transparent; color:{PRIMARY}; border:1px solid {PRIMARY};"
        f"  border-radius:6px; padding:7px 16px; font-size:{fs}pt; font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{ background:#1e3a5f; }}"
    )


def danger_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DANGER}; color:#fff; border:none; border-radius:6px;"
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{ background:#dc2626; }}"
    )


def global_style() -> str:
    """Stylesheet global aplicado no QApplication."""
    return (
        f"QMainWindow, QWidget {{ background:{CONTENT_BG}; color:{TEXT_DARK}; }}"
        f"QToolTip {{ background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  padding:4px 8px; }}"
        # Scrollbars
        f"QScrollBar:vertical {{ width:8px; background:{CONTENT_BG}; border-radius:4px; }}"
        f"QScrollBar::handle:vertical {{ background:{BORDER_COLOR}; border-radius:4px; min-height:30px; }}"
        f"QScrollBar::handle:vertical:hover {{ background:{TEXT_LABEL}; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        f"QScrollBar:horizontal {{ height:8px; background:{CONTENT_BG}; border-radius:4px; }}"
        f"QScrollBar::handle:horizontal {{ background:{BORDER_COLOR}; border-radius:4px; }}"
        f"QScrollBar::handle:horizontal:hover {{ background:{TEXT_LABEL}; }}"
        f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        # Menu / calendário do QDateEdit
        f"QCalendarWidget QWidget {{ background:{CARD_BG}; color:{TEXT_DARK}; }}"
        f"QCalendarWidget QAbstractItemView:enabled {{ background:{CARD_BG}; color:{TEXT_DARK};"
        f"  selection-background-color:{PRIMARY}; selection-color:#fff; }}"
        f"QCalendarWidget QToolButton {{ background:{SIDEBAR_BG}; color:{TEXT_DARK}; }}"
        f"QCalendarWidget #qt_calendar_navigationbar {{ background:{SIDEBAR_BG}; }}"
        f"QMessageBox {{ background:{CARD_BG}; }}"
        f"QMessageBox QLabel {{ color:{TEXT_DARK}; }}"
        f"QMessageBox QPushButton {{ background:{PRIMARY}; color:#fff; border:none;"
        f"  border-radius:5px; padding:6px 16px; min-width:70px; }}"
        f"QMessageBox QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
    )
