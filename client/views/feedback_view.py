from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QFrame

from ..core import theme


class FeedbackView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self.title = QLabel("FEEDBACKS")
        self.title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(12, int(16 * self.scale))}pt; font-weight:700;"
        )
        root.addWidget(self.title)

        self.subtitle = QLabel(
            "Use este campo para enviar problemas, elogios, bugs e sugestoes."
        )
        self.subtitle.setWordWrap(True)
        self.subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * self.scale))}pt;"
        )
        root.addWidget(self.subtitle)

        self.box = QFrame()
        self.box.setStyleSheet(theme.card_style())
        box_layout = QVBoxLayout(self.box)
        box_layout.setContentsMargins(12, 12, 12, 12)
        box_layout.setSpacing(8)

        self.input_feedback = QTextEdit()
        self.input_feedback.setPlaceholderText(
            "Digite aqui seu feedback..."
        )
        self.input_feedback.setMinimumHeight(max(260, int(320 * self.scale)))
        self.input_feedback.setStyleSheet(theme.input_style(self.scale))
        box_layout.addWidget(self.input_feedback)

        root.addWidget(self.box, 1)

    def refresh(self):
        return

    def apply_theme(self):
        self._setup_ui_styles()

    def _setup_ui_styles(self):
        self.title.setStyleSheet(
            f"color:{theme.PRIMARY}; font-size:{max(12, int(16 * self.scale))}pt; font-weight:700;"
        )
        self.subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * self.scale))}pt;"
        )
        self.box.setStyleSheet(theme.card_style())
        self.input_feedback.setStyleSheet(theme.input_style(self.scale))
