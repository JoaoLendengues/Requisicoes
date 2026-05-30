from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from . import theme


class _MessageBoxShortcutFilter(QObject):
    """Atalhos escondidos para caixas de diálogo: S=Sim, N=Não, O=OK."""

    def eventFilter(self, obj, event):
        if not isinstance(obj, QMessageBox):
            return False
        if event.type() != QEvent.Type.KeyPress:
            return False

        if event.modifiers() not in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.ShiftModifier,
        ):
            return False

        key_map = {
            Qt.Key.Key_S: "s",
            Qt.Key.Key_N: "n",
            Qt.Key.Key_O: "o",
        }
        letter = key_map.get(event.key())
        if not letter:
            return False

        btn = _resolve_message_box_button(obj, letter)
        if btn is None or not btn.isEnabled():
            return False
        btn.click()
        return True


def _clean_button_text(text: str) -> str:
    return (text or "").replace("&", "").strip().lower()


def _resolve_message_box_button(box: QMessageBox, letter: str):
    candidates: list[tuple[int, QPushButton]] = []

    for button in box.buttons():
        if not isinstance(button, QPushButton):
            continue
        std = box.standardButton(button)
        role = box.buttonRole(button)
        txt = _clean_button_text(button.text())

        priority = 99
        if letter == "s":
            if std == QMessageBox.StandardButton.Yes:
                priority = 0
            elif role == QMessageBox.ButtonRole.YesRole:
                priority = 1
            elif txt.startswith("s"):
                priority = 2
        elif letter == "n":
            if std == QMessageBox.StandardButton.No:
                priority = 0
            elif role == QMessageBox.ButtonRole.NoRole:
                priority = 1
            elif role == QMessageBox.ButtonRole.RejectRole:
                priority = 2
            elif txt.startswith("n"):
                priority = 3
        elif letter == "o":
            if std == QMessageBox.StandardButton.Ok:
                priority = 0
            elif role == QMessageBox.ButtonRole.AcceptRole:
                priority = 1
            elif txt.startswith("o") or txt == "ok":
                priority = 2

        if priority < 99:
            candidates.append((priority, button))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


_MESSAGE_BOX_SHORTCUT_FILTER = _MessageBoxShortcutFilter()


def _message_box_style() -> str:
    return (
        f"QMessageBox {{"
        f"  background-color:{theme.CARD_BG}; border:1px solid {theme.PRIMARY_LIGHT}; border-radius:10px;"
        f"}}"
        f"QMessageBox QWidget {{ background-color:{theme.CARD_BG}; color:{theme.TEXT_DARK}; }}"
        f"QMessageBox QLabel {{ background-color:transparent; color:{theme.TEXT_DARK}; padding:2px 0; }}"
        f"QMessageBox QFrame {{ background-color:{theme.CARD_BG}; border:none; }}"
        f"QMessageBox QDialogButtonBox {{"
        f"  background-color:{theme.CARD_BG}; border-top:1px solid {theme.BORDER_COLOR}; padding-top:10px;"
        f"}}"
    )


def _message_box_button_style() -> str:
    return (
        f"QPushButton {{"
        f"  background:{theme.SIDEBAR_BG};"
        f"  background-color:{theme.SIDEBAR_BG};"
        f"  background-image:none;"
        f"  color:{theme.TEXT_WHITE};"
        f"  border:1px solid {theme.SIDEBAR_BG};"
        f"  border-radius:8px;"
        f"  padding:7px 16px;"
        f"  min-width:84px;"
        f"  min-height:34px;"
        f"  font-weight:600;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background:{theme.SIDEBAR_HOVER};"
        f"  background-color:{theme.SIDEBAR_HOVER};"
        f"  border-color:{theme.SIDEBAR_HOVER};"
        f"}}"
        f"QPushButton:pressed {{"
        f"  background:{theme.SIDEBAR_ACTIVE};"
        f"  background-color:{theme.SIDEBAR_ACTIVE};"
        f"  border-color:{theme.SIDEBAR_ACTIVE};"
        f"}}"
        f"QPushButton:focus, QPushButton:default {{"
        f"  background:{theme.SIDEBAR_BG};"
        f"  background-color:{theme.SIDEBAR_BG};"
        f"  color:{theme.TEXT_WHITE};"
        f"  border:1px solid {theme.SIDEBAR_ACTIVE};"
        f"}}"
        f"QPushButton:disabled {{"
        f"  background:{theme.BORDER_COLOR};"
        f"  background-color:{theme.BORDER_COLOR};"
        f"  color:{theme.TEXT_LABEL};"
        f"  border:1px solid {theme.BORDER_COLOR};"
        f"}}"
    )


def apply_message_box_theme(box: QMessageBox) -> QMessageBox:
    box.setStyleSheet(_message_box_style())
    box.installEventFilter(_MESSAGE_BOX_SHORTCUT_FILTER)
    for button in box.buttons():
        if isinstance(button, QPushButton):
            button.setStyleSheet(_message_box_button_style())
            button.setAutoDefault(False)
    return box


def _exec_themed_message_box(
    parent: QWidget | None,
    title: str,
    text: str,
    icon: QMessageBox.Icon,
    buttons: QMessageBox.StandardButton,
    default_button: QMessageBox.StandardButton,
) -> QMessageBox.StandardButton:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(icon)
    box.setText(text)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setStandardButtons(buttons)
    if default_button != QMessageBox.StandardButton.NoButton:
        box.setDefaultButton(default_button)
    apply_message_box_theme(box)
    box.exec()
    clicked = box.clickedButton()
    return box.standardButton(clicked) if clicked else QMessageBox.StandardButton.NoButton


def install_message_box_theme_hooks() -> None:
    """Padroniza QMessageBox.* para o estilo do app em todas as caixas de diálogo."""
    if getattr(QMessageBox, "_fp_theme_hooks_installed", False):
        return

    def _information(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return _exec_themed_message_box(
            parent, title, text, QMessageBox.Icon.Information, buttons, default_button
        )

    def _warning(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return _exec_themed_message_box(
            parent, title, text, QMessageBox.Icon.Warning, buttons, default_button
        )

    def _critical(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return _exec_themed_message_box(
            parent, title, text, QMessageBox.Icon.Critical, buttons, default_button
        )

    def _question(
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        return _exec_themed_message_box(
            parent, title, text, QMessageBox.Icon.Question, buttons, default_button
        )

    QMessageBox.information = staticmethod(_information)
    QMessageBox.warning = staticmethod(_warning)
    QMessageBox.critical = staticmethod(_critical)
    QMessageBox.question = staticmethod(_question)
    QMessageBox._fp_theme_hooks_installed = True


def ask_confirmation(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    yes_text: str = "Sim",
    no_text: str = "Não",
    default_to_yes: bool = False,
) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    box.setTextFormat(Qt.TextFormat.PlainText)

    yes_button = box.addButton(yes_text, QMessageBox.ButtonRole.YesRole)
    no_button = box.addButton(no_text, QMessageBox.ButtonRole.NoRole)

    box.setDefaultButton(yes_button if default_to_yes else no_button)
    box.setEscapeButton(no_button)
    apply_message_box_theme(box)
    box.exec()
    return box.clickedButton() == yes_button
