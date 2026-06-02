from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QWidget,
)

_HOOKS_INSTALLED = False
_ORTHOGRAPHY_FILTER: QObject | None = None
_ORIGINALS: dict[str, object] = {}

_REPLACEMENTS = {
    "requisicoes": "requisições",
    "requisicao": "requisição",
    "producoes": "produções",
    "producao": "produção",
    "maquinas": "máquinas",
    "maquina": "máquina",
    "usuarios": "usuários",
    "usuario": "usuário",
    "configuracoes": "configurações",
    "configuracao": "configuração",
    "informacoes": "informações",
    "informacao": "informação",
    "confirmacoes": "confirmações",
    "confirmacao": "confirmação",
    "operacoes": "operações",
    "operacao": "operação",
    "conclusao": "conclusão",
    "conexao": "conexão",
    "visualizacao": "visualização",
    "atualizacoes": "atualizações",
    "atualizacao": "atualização",
    "historico": "histórico",
    "periodos": "períodos",
    "periodo": "período",
    "codigos": "códigos",
    "codigo": "código",
    "numeros": "números",
    "numero": "número",
    "minimo": "mínimo",
    "maximo": "máximo",
    "ultimos": "últimos",
    "ultimo": "último",
    "media": "média",
    "medias": "médias",
    "rapidos": "rápidos",
    "rapido": "rápido",
    "tecnicos": "técnicos",
    "tecnico": "técnico",
    "automatico": "automático",
    "possivel": "possível",
    "impossivel": "impossível",
    "disponiveis": "disponíveis",
    "disponivel": "disponível",
    "invalidos": "inválidos",
    "invalido": "inválido",
    "validos": "válidos",
    "valido": "válido",
    "manutencao": "manutenção",
    "comunicacao": "comunicação",
    "integracao": "integração",
    "alteracoes": "alterações",
    "alteracao": "alteração",
    "importacao": "importação",
    "exportacao": "exportação",
    "enderecos": "endereços",
    "endereco": "endereço",
    "pagina": "página",
    "paginas": "páginas",
    "industria": "indústria",
    "obrigatorios": "obrigatórios",
    "obrigatorio": "obrigatório",
    "nao": "não",
    "ja": "já",
    "so": "só",
    "tambem": "também",
    "voce": "você",
}

_PATTERNS = [
    (
        re.compile(rf"(?<![\w/\\]){re.escape(source)}(?![\w/\\])", re.IGNORECASE),
        target,
    )
    for source, target in sorted(_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True)
]


def _looks_like_file_or_path(text: str) -> bool:
    lowered = text.casefold()
    if "://" in lowered or "\\\\" in text:
        return True
    if re.search(r"\b[A-Z]:\\", text):
        return True
    if re.search(r"\b[\w\- ]+\.(xlsx|xlsm|pdf|png|jpg|jpeg|bmp|gif|webp|dwg|exe)\b", lowered):
        return True
    if "_" in text and " " not in text:
        return True
    return False


def _apply_case(source: str, target: str) -> str:
    if not source:
        return target
    if source.isupper():
        return target.upper()
    if source.islower():
        return target.lower()
    if source[0].isupper() and source[1:].islower():
        return target[:1].upper() + target[1:]
    return target


def normalize_ui_text(text: object) -> object:
    if not isinstance(text, str):
        return text
    if not text.strip():
        return text
    if _looks_like_file_or_path(text):
        return text

    normalized = text
    for pattern, replacement in _PATTERNS:
        normalized = pattern.sub(lambda match: _apply_case(match.group(0), replacement), normalized)
    return normalized


def _call_original(key: str, target, value) -> None:
    original = _ORIGINALS[key]
    original(target, value)


def _normalize_tooltip(widget: QWidget) -> None:
    tooltip = widget.toolTip()
    normalized = normalize_ui_text(tooltip)
    if normalized != tooltip:
        _call_original("QWidget.setToolTip", widget, normalized)


def _normalize_window_title(widget: QWidget) -> None:
    title = widget.windowTitle()
    normalized = normalize_ui_text(title)
    if normalized != title:
        _call_original("QWidget.setWindowTitle", widget, normalized)


def _normalize_combo_items(combo: QComboBox) -> None:
    for index in range(combo.count()):
        text = combo.itemText(index)
        normalized = normalize_ui_text(text)
        if normalized != text:
            _ORIGINALS["QComboBox.setItemText"](combo, index, normalized)


def _normalize_table_headers(table: QTableWidget) -> None:
    for index in range(table.columnCount()):
        item = table.horizontalHeaderItem(index)
        if item is None:
            continue
        text = item.text()
        normalized = normalize_ui_text(text)
        if normalized != text:
            item.setText(normalized)
    for index in range(table.rowCount()):
        item = table.verticalHeaderItem(index)
        if item is None:
            continue
        text = item.text()
        normalized = normalize_ui_text(text)
        if normalized != text:
            item.setText(normalized)


def _normalize_list_items(list_widget: QListWidget) -> None:
    for index in range(list_widget.count()):
        item = list_widget.item(index)
        if item is None:
            continue
        text = item.text()
        normalized = normalize_ui_text(text)
        if normalized != text:
            item.setText(normalized)


def _normalize_tab_titles(tab_widget: QTabWidget) -> None:
    for index in range(tab_widget.count()):
        text = tab_widget.tabText(index)
        normalized = normalize_ui_text(text)
        if normalized != text:
            tab_widget.setTabText(index, normalized)


def _normalize_message_box(box: QMessageBox) -> None:
    text = box.text()
    normalized_text = normalize_ui_text(text)
    if normalized_text != text:
        _ORIGINALS["QMessageBox.setText"](box, normalized_text)

    informative_text = box.informativeText()
    normalized_informative = normalize_ui_text(informative_text)
    if normalized_informative != informative_text:
        _ORIGINALS["QMessageBox.setInformativeText"](box, normalized_informative)

    detailed_text = box.detailedText()
    normalized_detailed = normalize_ui_text(detailed_text)
    if normalized_detailed != detailed_text:
        _ORIGINALS["QMessageBox.setDetailedText"](box, normalized_detailed)


def _normalize_widget(widget: QWidget) -> None:
    _normalize_window_title(widget)
    _normalize_tooltip(widget)

    if isinstance(widget, QLabel):
        text = widget.text()
        normalized = normalize_ui_text(text)
        if normalized != text:
            _call_original("QLabel.setText", widget, normalized)

    if isinstance(widget, QAbstractButton):
        text = widget.text()
        normalized = normalize_ui_text(text)
        if normalized != text:
            _call_original("QAbstractButton.setText", widget, normalized)

    if isinstance(widget, QGroupBox):
        title = widget.title()
        normalized = normalize_ui_text(title)
        if normalized != title:
            _call_original("QGroupBox.setTitle", widget, normalized)

    if isinstance(widget, QLineEdit):
        placeholder = widget.placeholderText()
        normalized = normalize_ui_text(placeholder)
        if normalized != placeholder:
            _call_original("QLineEdit.setPlaceholderText", widget, normalized)

    if isinstance(widget, QTextEdit):
        placeholder = widget.placeholderText()
        normalized = normalize_ui_text(placeholder)
        if normalized != placeholder:
            _call_original("QTextEdit.setPlaceholderText", widget, normalized)

    if isinstance(widget, QPlainTextEdit):
        placeholder = widget.placeholderText()
        normalized = normalize_ui_text(placeholder)
        if normalized != placeholder:
            _call_original("QPlainTextEdit.setPlaceholderText", widget, normalized)

    if isinstance(widget, QComboBox):
        _normalize_combo_items(widget)

    if isinstance(widget, QTabWidget):
        _normalize_tab_titles(widget)

    if isinstance(widget, QTableWidget):
        _normalize_table_headers(widget)

    if isinstance(widget, QListWidget):
        _normalize_list_items(widget)

    if isinstance(widget, QMessageBox):
        _normalize_message_box(widget)


def _normalize_widget_tree(root: QWidget) -> None:
    _normalize_widget(root)
    for child in root.findChildren(QWidget):
        _normalize_widget(child)


def _patch_text_setters() -> None:
    if _HOOKS_INSTALLED:
        return

    _ORIGINALS["QWidget.setWindowTitle"] = QWidget.setWindowTitle
    _ORIGINALS["QWidget.setToolTip"] = QWidget.setToolTip
    _ORIGINALS["QLabel.setText"] = QLabel.setText
    _ORIGINALS["QAbstractButton.setText"] = QAbstractButton.setText
    _ORIGINALS["QGroupBox.setTitle"] = QGroupBox.setTitle
    _ORIGINALS["QLineEdit.setPlaceholderText"] = QLineEdit.setPlaceholderText
    _ORIGINALS["QTextEdit.setPlaceholderText"] = QTextEdit.setPlaceholderText
    _ORIGINALS["QPlainTextEdit.setPlaceholderText"] = QPlainTextEdit.setPlaceholderText
    _ORIGINALS["QComboBox.addItem"] = QComboBox.addItem
    _ORIGINALS["QComboBox.addItems"] = QComboBox.addItems
    _ORIGINALS["QComboBox.insertItem"] = QComboBox.insertItem
    _ORIGINALS["QComboBox.setItemText"] = QComboBox.setItemText
    _ORIGINALS["QTabWidget.setTabText"] = QTabWidget.setTabText
    _ORIGINALS["QMessageBox.setText"] = QMessageBox.setText
    _ORIGINALS["QMessageBox.setInformativeText"] = QMessageBox.setInformativeText
    _ORIGINALS["QMessageBox.setDetailedText"] = QMessageBox.setDetailedText
    _ORIGINALS["QProgressDialog.setLabelText"] = QProgressDialog.setLabelText
    _ORIGINALS["QAction.setText"] = QAction.setText
    _ORIGINALS["QAction.setToolTip"] = QAction.setToolTip
    _ORIGINALS["QAction.setStatusTip"] = QAction.setStatusTip

    def _window_title(self, title: str) -> None:
        _ORIGINALS["QWidget.setWindowTitle"](self, normalize_ui_text(title))

    def _tooltip(self, tooltip: str) -> None:
        _ORIGINALS["QWidget.setToolTip"](self, normalize_ui_text(tooltip))

    def _label_text(self, text: str) -> None:
        _ORIGINALS["QLabel.setText"](self, normalize_ui_text(text))

    def _button_text(self, text: str) -> None:
        _ORIGINALS["QAbstractButton.setText"](self, normalize_ui_text(text))

    def _group_title(self, title: str) -> None:
        _ORIGINALS["QGroupBox.setTitle"](self, normalize_ui_text(title))

    def _line_placeholder(self, text: str) -> None:
        _ORIGINALS["QLineEdit.setPlaceholderText"](self, normalize_ui_text(text))

    def _textedit_placeholder(self, text: str) -> None:
        _ORIGINALS["QTextEdit.setPlaceholderText"](self, normalize_ui_text(text))

    def _plaintext_placeholder(self, text: str) -> None:
        _ORIGINALS["QPlainTextEdit.setPlaceholderText"](self, normalize_ui_text(text))

    def _combo_add_item(self, *args) -> None:
        if len(args) == 1:
            _ORIGINALS["QComboBox.addItem"](self, normalize_ui_text(args[0]))
            return
        if len(args) == 2 and isinstance(args[0], str):
            text, user_data = args
            _ORIGINALS["QComboBox.addItem"](self, normalize_ui_text(text), user_data)
            return
        if len(args) >= 2:
            icon = args[0]
            text = normalize_ui_text(args[1])
            remaining = args[2:]
            _ORIGINALS["QComboBox.addItem"](self, icon, text, *remaining)
            return
        _ORIGINALS["QComboBox.addItem"](self, *args)

    def _combo_add_items(self, texts) -> None:
        _ORIGINALS["QComboBox.addItems"](self, [normalize_ui_text(text) for text in texts])

    def _combo_insert_item(self, index: int, *args) -> None:
        if len(args) == 1:
            _ORIGINALS["QComboBox.insertItem"](self, index, normalize_ui_text(args[0]))
            return
        if len(args) == 2 and isinstance(args[0], str):
            text, user_data = args
            _ORIGINALS["QComboBox.insertItem"](self, index, normalize_ui_text(text), user_data)
            return
        if len(args) >= 2:
            icon = args[0]
            text = normalize_ui_text(args[1])
            remaining = args[2:]
            _ORIGINALS["QComboBox.insertItem"](self, index, icon, text, *remaining)
            return
        _ORIGINALS["QComboBox.insertItem"](self, index, *args)

    def _combo_set_item_text(self, index: int, text: str) -> None:
        _ORIGINALS["QComboBox.setItemText"](self, index, normalize_ui_text(text))

    def _tab_text(self, index: int, text: str) -> None:
        _ORIGINALS["QTabWidget.setTabText"](self, index, normalize_ui_text(text))

    def _message_box_text(self, text: str) -> None:
        _ORIGINALS["QMessageBox.setText"](self, normalize_ui_text(text))

    def _message_box_informative(self, text: str) -> None:
        _ORIGINALS["QMessageBox.setInformativeText"](self, normalize_ui_text(text))

    def _message_box_detailed(self, text: str) -> None:
        _ORIGINALS["QMessageBox.setDetailedText"](self, normalize_ui_text(text))

    def _progress_label(self, text: str) -> None:
        _ORIGINALS["QProgressDialog.setLabelText"](self, normalize_ui_text(text))

    def _action_text(self, text: str) -> None:
        _ORIGINALS["QAction.setText"](self, normalize_ui_text(text))

    def _action_tooltip(self, text: str) -> None:
        _ORIGINALS["QAction.setToolTip"](self, normalize_ui_text(text))

    def _action_status_tip(self, text: str) -> None:
        _ORIGINALS["QAction.setStatusTip"](self, normalize_ui_text(text))

    QWidget.setWindowTitle = _window_title
    QWidget.setToolTip = _tooltip
    QLabel.setText = _label_text
    QAbstractButton.setText = _button_text
    QGroupBox.setTitle = _group_title
    QLineEdit.setPlaceholderText = _line_placeholder
    QTextEdit.setPlaceholderText = _textedit_placeholder
    QPlainTextEdit.setPlaceholderText = _plaintext_placeholder
    QComboBox.addItem = _combo_add_item
    QComboBox.addItems = _combo_add_items
    QComboBox.insertItem = _combo_insert_item
    QComboBox.setItemText = _combo_set_item_text
    QTabWidget.setTabText = _tab_text
    QMessageBox.setText = _message_box_text
    QMessageBox.setInformativeText = _message_box_informative
    QMessageBox.setDetailedText = _message_box_detailed
    QProgressDialog.setLabelText = _progress_label
    QAction.setText = _action_text
    QAction.setToolTip = _action_tooltip
    QAction.setStatusTip = _action_status_tip


class _OrthographyFilter(QObject):
    def eventFilter(self, obj, event):
        if isinstance(obj, QWidget) and event.type() in (
            QEvent.Type.Show,
            QEvent.Type.Polish,
        ):
            _normalize_widget_tree(obj)
        return False


def install_orthography_hooks(app: QApplication | None = None) -> None:
    global _HOOKS_INSTALLED, _ORTHOGRAPHY_FILTER
    if _HOOKS_INSTALLED:
        return

    _patch_text_setters()
    _ORTHOGRAPHY_FILTER = _OrthographyFilter()

    target_app = app or QApplication.instance()
    if target_app is not None:
        target_app.installEventFilter(_ORTHOGRAPHY_FILTER)

    _HOOKS_INSTALLED = True
