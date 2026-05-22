from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from . import theme


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
    # Mantém o padrão atual no modo escuro; a padronização customizada é só no claro.
    if theme.is_dark:
        return box

    box.setStyleSheet(_message_box_style())
    for button in box.buttons():
        if isinstance(button, QPushButton):
            button.setStyleSheet(_message_box_button_style())
            button.setAutoDefault(False)
    return box


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
