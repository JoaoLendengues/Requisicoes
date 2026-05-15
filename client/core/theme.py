# ── Paleta de cores ───────────────────────────────────────────────────────────
SIDEBAR_BG        = "#1B2B4B"
SIDEBAR_HOVER     = "#243a5e"
SIDEBAR_ACTIVE    = "#1E40AF"
SIDEBAR_INDICATOR = "#60A5FA"
CONTENT_BG        = "#E8ECF2"
CARD_BG           = "#FFFFFF"
PRIMARY           = "#1B4FD8"
PRIMARY_HOVER     = "#1a3fa8"
BORDER_COLOR      = "#CBD5E1"
TEXT_DARK         = "#0A0F1E"
TEXT_MEDIUM       = "#1F2937"
TEXT_LIGHT        = "#374151"
TEXT_LABEL        = "#4B5563"
TEXT_WHITE        = "#FFFFFF"
INPUT_BG          = "#F8FAFC"
DANGER            = "#EF4444"
SUCCESS           = "#22C55E"
TABLE_HEADER_BG   = "#1B2B4B"
TABLE_ALT_ROW     = "#F1F5F9"

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


# ── Stylesheets globais ───────────────────────────────────────────────────────
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
    )


def primary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{PRIMARY}; color:#fff; border:none; border-radius:6px;"
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background:#162f96; }}"
        f"QPushButton:disabled {{ background:#93acd4; }}"
    )


def secondary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:transparent; color:{PRIMARY}; border:1px solid {PRIMARY};"
        f"  border-radius:6px; padding:7px 16px; font-size:{fs}pt; font-weight:bold;"
        f"}}"
        f"QPushButton:hover {{ background:#EFF6FF; }}"
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
