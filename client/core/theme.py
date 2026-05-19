FONT_PRIMARY = "Poppins"
FONT_FALLBACK = "Inter"

SIDEBAR_BG = "#002C6D"
SIDEBAR_HOVER = "#003B8F"
SIDEBAR_ACTIVE = "#0057D8"
SIDEBAR_INDICATOR = "#2D7FF9"
FOOTER_BG = "#002C6D"

CONTENT_BG = "#F5F7FA"
CARD_BG = "#FFFFFF"
INPUT_BG = "#FFFFFF"
SURFACE_SOFT = "#F8FBFF"

PRIMARY = "#003B8F"
PRIMARY_HOVER = "#0057D8"
PRIMARY_LIGHT = "#2D7FF9"

BORDER_COLOR = "#D9E1EC"
TABLE_HEADER_BG = "#003B8F"
TABLE_ALT_ROW = "#F8FAFD"
TABLE_BORDER = "#D9E1EC"
SELECTION_BG = "#DCE9FF"

TEXT_DARK = "#1E2A3A"
TEXT_MEDIUM = "#6B778C"
TEXT_LIGHT = "#7A8798"
TEXT_LABEL = "#94A0B2"
TEXT_WHITE = "#FFFFFF"

DANGER = "#D64545"
SUCCESS = "#2DBE4E"
WARNING = "#F3A01B"

STATUS_COLORS = {
    "em_andamento": PRIMARY_LIGHT,
    "aguardando_recebimento": WARNING,
    "em_producao": PRIMARY_HOVER,
    "cancelada": DANGER,
}

STATUS_LABELS = {
    "em_andamento": "Em Andamento",
    "aguardando_recebimento": "Aguardando Recebimento",
    "em_producao": "Em Producao",
    "cancelada": "Cancelada",
}


def status_style(status: str) -> str:
    color = STATUS_COLORS.get(status, TEXT_MEDIUM)
    return (
        f"background:{color}; color:{TEXT_WHITE}; border-radius:8px; "
        f"padding:4px 12px; font-weight:600;"
    )


def card_style() -> str:
    return (
        f"background:{CARD_BG}; border:1px solid {BORDER_COLOR}; "
        f"border-radius:8px;"
    )


def input_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{"
        f"  background:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"
        f"  padding:7px 10px; font-size:{fs}pt; color:{TEXT_DARK};"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"
        f"}}"
        f"QLineEdit, QTextEdit {{"
        f"  placeholder-text-color:{TEXT_LABEL};"
        f"}}"
        f"QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, "
        f"QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"  border:1px solid {PRIMARY_LIGHT};"
        f"}}"
        f"QComboBox::drop-down, QDateEdit::drop-down {{"
        f"  border:none; width:24px;"
        f"}}"
        f"QComboBox QAbstractItemView, QDateEdit QAbstractItemView {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"
        f"}}"
    )


def primary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{PRIMARY}; color:{TEXT_WHITE}; border:none; border-radius:8px;"
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
        f"QPushButton:pressed {{ background:{SIDEBAR_BG}; }}"
        f"QPushButton:disabled {{ background:#AAB8CE; color:#EEF2F8; }}"
    )


def secondary_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{CARD_BG}; color:{PRIMARY}; border:1px solid {BORDER_COLOR};"
        f"  border-radius:8px; padding:7px 16px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:{SELECTION_BG}; border-color:{PRIMARY_LIGHT}; }}"
        f"QPushButton:pressed {{ background:#CFE0FF; }}"
    )


def danger_btn_style(scale: float = 1.0) -> str:
    fs = max(9, int(11 * scale))
    return (
        f"QPushButton {{"
        f"  background:{DANGER}; color:{TEXT_WHITE}; border:none; border-radius:8px;"
        f"  padding:8px 18px; font-size:{fs}pt; font-weight:600;"
        f"}}"
        f"QPushButton:hover {{ background:#BF3636; }}"
        f"QPushButton:pressed {{ background:#A92F2F; }}"
    )


def global_style() -> str:
    return (
        f"QMainWindow {{"
        f"  background:{CONTENT_BG}; color:{TEXT_DARK};"
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QDialog QWidget {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"
        f"}}"
        f"QWidget {{"
        f"  color:{TEXT_DARK};"
        f"  font-family:'{FONT_PRIMARY}', '{FONT_FALLBACK}', 'Segoe UI';"
        f"}}"
        f"QLabel {{ background:transparent; }}"
        f"QFrame {{ color:{TEXT_DARK}; }}"
        f"QToolTip {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  padding:6px 10px; border-radius:8px;"
        f"}}"
        f"QAbstractItemView {{"
        f"  outline:none; alternate-background-color:{TABLE_ALT_ROW};"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"
        f"}}"
        f"QHeaderView::section {{"
        f"  background:{TABLE_HEADER_BG}; color:{TEXT_WHITE}; padding:8px 10px;"
        f"  border:none; font-weight:600;"
        f"}}"
        f"QTableCornerButton::section {{"
        f"  background:{TABLE_HEADER_BG}; border:none;"
        f"}}"
        f"QTabBar::tab {{"
        f"  background:{CARD_BG}; color:{TEXT_MEDIUM}; border:1px solid {BORDER_COLOR};"
        f"  padding:8px 14px; margin-right:4px; border-top-left-radius:8px; border-top-right-radius:8px;"
        f"}}"
        f"QTabBar::tab:selected {{ background:{PRIMARY}; color:{TEXT_WHITE}; border-color:{PRIMARY}; }}"
        f"QScrollBar:vertical {{ width:10px; background:transparent; margin:2px; }}"
        f"QScrollBar::handle:vertical {{"
        f"  background:{BORDER_COLOR}; border-radius:5px; min-height:36px;"
        f"}}"
        f"QScrollBar::handle:vertical:hover {{ background:{PRIMARY_LIGHT}; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        f"QScrollBar:horizontal {{ height:10px; background:transparent; margin:2px; }}"
        f"QScrollBar::handle:horizontal {{ background:{BORDER_COLOR}; border-radius:5px; }}"
        f"QScrollBar::handle:horizontal:hover {{ background:{PRIMARY_LIGHT}; }}"
        f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        f"QCalendarWidget QWidget {{ background:{CARD_BG}; color:{TEXT_DARK}; }}"
        f"QCalendarWidget QAbstractItemView:enabled {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK};"
        f"  selection-background-color:{PRIMARY}; selection-color:{TEXT_WHITE};"
        f"}}"
        f"QCalendarWidget QToolButton {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:none; padding:6px; border-radius:8px;"
        f"}}"
        f"QCalendarWidget QToolButton:hover {{ background:{SELECTION_BG}; }}"
        f"QCalendarWidget #qt_calendar_navigationbar {{"
        f"  background:{SURFACE_SOFT}; border-bottom:1px solid {BORDER_COLOR};"
        f"}}"
        f"QMessageBox {{"
        f"  background-color:{CARD_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"
        f"}}"
        f"QMessageBox QWidget {{ background-color:{CARD_BG}; color:{TEXT_DARK}; }}"
        f"QMessageBox QLabel {{ background-color:transparent; color:{TEXT_DARK}; padding:2px 0; }}"
        f"QMessageBox QFrame {{ background-color:{CARD_BG}; border:none; }}"
        f"QMessageBox QDialogButtonBox {{ background-color:{CARD_BG}; border-top:1px solid {BORDER_COLOR}; padding-top:10px; }}"
        f"QMessageBox QPushButton {{"
        f"  background:{PRIMARY}; color:{TEXT_WHITE}; border:none;"
        f"  border-radius:8px; padding:7px 16px; min-width:84px; font-weight:600;"
        f"}}"
        f"QMessageBox QPushButton:hover {{ background:{PRIMARY_HOVER}; }}"
        f"QInputDialog, QFileDialog, QColorDialog {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"
        f"}}"
        f"QInputDialog QWidget, QFileDialog QWidget, QColorDialog QWidget {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK};"
        f"}}"
        f"QInputDialog QLabel, QFileDialog QLabel, QColorDialog QLabel {{"
        f"  background-color:transparent; color:{TEXT_DARK};"
        f"}}"
        f"QInputDialog QLineEdit, QInputDialog QTextEdit, QInputDialog QPlainTextEdit,"
        f"QFileDialog QLineEdit, QFileDialog QTextEdit, QFileDialog QPlainTextEdit,"
        f"QColorDialog QLineEdit, QColorDialog QTextEdit, QColorDialog QPlainTextEdit {{"
        f"  background-color:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"
        f"  padding:7px 10px; color:{TEXT_DARK};"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"
        f"}}"
        f"QInputDialog QComboBox, QFileDialog QComboBox, QColorDialog QComboBox,"
        f"QColorDialog QSpinBox, QColorDialog QDoubleSpinBox {{"
        f"  background-color:{INPUT_BG}; border:1px solid {BORDER_COLOR}; border-radius:8px;"
        f"  padding:7px 10px; color:{TEXT_DARK};"
        f"  selection-background-color:{SELECTION_BG}; selection-color:{TEXT_DARK};"
        f"}}"
        f"QFileDialog QListView, QFileDialog QTreeView, QFileDialog QTableView {{"
        f"  background-color:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  alternate-background-color:{TABLE_ALT_ROW};"
        f"}}"
        f"QFileDialog QSplitter::handle {{ background:{BORDER_COLOR}; }}"
        f"QInputDialog QDialogButtonBox, QFileDialog QDialogButtonBox, QColorDialog QDialogButtonBox {{"
        f"  background-color:{CARD_BG}; border-top:1px solid {BORDER_COLOR}; padding-top:10px;"
        f"}}"
        f"QInputDialog QPushButton, QFileDialog QPushButton, QColorDialog QPushButton {{"
        f"  background-color:{PRIMARY}; color:{TEXT_WHITE}; border:none;"
        f"  border-radius:8px; padding:7px 16px; min-width:84px; font-weight:600;"
        f"}}"
        f"QInputDialog QPushButton:hover, QFileDialog QPushButton:hover, QColorDialog QPushButton:hover {{"
        f"  background-color:{PRIMARY_HOVER};"
        f"}}"
        f"QCheckBox {{ spacing:8px; }}"
        f"QCheckBox::indicator {{"
        f"  width:16px; height:16px; border-radius:4px; border:1px solid {BORDER_COLOR};"
        f"  background:{CARD_BG};"
        f"}}"
        f"QCheckBox::indicator:checked {{"
        f"  background:{PRIMARY}; border:1px solid {PRIMARY};"
        f"}}"
        f"QSlider::groove:horizontal {{"
        f"  height:6px; background:{BORDER_COLOR}; border-radius:3px;"
        f"}}"
        f"QSlider::handle:horizontal {{"
        f"  background:{PRIMARY}; width:16px; margin:-6px 0; border-radius:8px;"
        f"}}"
        f"QSlider::sub-page:horizontal {{ background:{PRIMARY_LIGHT}; border-radius:3px; }}"
        f"QMenu {{"
        f"  background:{CARD_BG}; color:{TEXT_DARK}; border:1px solid {BORDER_COLOR};"
        f"  border-radius:8px; padding:6px;"
        f"}}"
        f"QMenu::item {{ padding:8px 12px; border-radius:6px; }}"
        f"QMenu::item:selected {{ background:{SELECTION_BG}; color:{TEXT_DARK}; }}"
        f"QStatusBar {{ background:{FOOTER_BG}; color:{TEXT_WHITE}; }}"
    )
