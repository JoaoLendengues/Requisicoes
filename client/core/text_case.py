from PySide6.QtWidgets import QLineEdit, QTextEdit


def normalize_upper_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).upper()


def bind_uppercase_line_edit(field: QLineEdit) -> None:
    def _apply(text: str) -> None:
        normalized = normalize_upper_text(text)
        if normalized == text:
            return

        cursor_pos = field.cursorPosition()
        field.blockSignals(True)
        field.setText(normalized)
        field.setCursorPosition(min(cursor_pos, len(normalized)))
        field.blockSignals(False)

    field.textChanged.connect(_apply)


def bind_uppercase_text_edit(field: QTextEdit) -> None:
    def _apply() -> None:
        text = field.toPlainText()
        normalized = normalize_upper_text(text)
        if normalized == text:
            return

        cursor = field.textCursor()
        cursor_pos = cursor.position()
        field.blockSignals(True)
        field.setPlainText(normalized)
        cursor = field.textCursor()
        cursor.setPosition(min(cursor_pos, len(normalized)))
        field.setTextCursor(cursor)
        field.blockSignals(False)

    field.textChanged.connect(_apply)
