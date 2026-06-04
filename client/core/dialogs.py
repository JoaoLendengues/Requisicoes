from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QPainterPath, QPalette, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QMessageBox,
    QPushButton,
    QWidget,
)

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
_DIALOG_THEME_FILTER: QObject | None = None


def _dialog_surface_style() -> str:
    primary_fg = "#04111F" if theme.is_dark else theme.TEXT_WHITE
    return (
        f"QDialog[fp_dialog='1'] {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        f"    stop:0 {theme.PANEL_CARD_BG_START}, stop:0.56 {theme.PANEL_CARD_BG_MID}, stop:1 {theme.PANEL_CARD_BG_END});"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {theme.rgba(theme.PANEL_NEON_PRIMARY, 94)};"
        f"  border-radius:18px;"
        f"}}"
        f"QDialog[fp_dialog='1'] QWidget {{ background:transparent; color:{theme.PANEL_TEXT_PRIMARY}; }}"
        f"QDialog[fp_dialog='1'] QLabel {{ background:transparent; color:{theme.PANEL_TEXT_PRIMARY}; }}"
        f"QDialog[fp_dialog='1'] QLabel#qt_msgbox_label,"
        f"QDialog[fp_dialog='1'] QLabel#qt_msgbox_informativelabel,"
        f"QDialog[fp_dialog='1'] QLabel#qt_msgboxex_detailedtext {{"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"  font-weight:600;"
        f"}}"
        f"QDialog[fp_dialog='1'] QFrame {{ background:transparent; border-color:{theme.PANEL_BORDER_SOFT}; }}"
        f"QDialog[fp_dialog='1'] QAbstractScrollArea,"
        f"QDialog[fp_dialog='1'] QListWidget,"
        f"QDialog[fp_dialog='1'] QListView,"
        f"QDialog[fp_dialog='1'] QTreeView,"
        f"QDialog[fp_dialog='1'] QTableView {{"
        f"  background:{theme.PANEL_SURFACE_BG};"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {theme.PANEL_BORDER_SOFT};"
        f"  border-radius:14px;"
        f"  selection-background-color:{theme.rgba(theme.PANEL_NEON_PRIMARY, 64)};"
        f"  selection-color:{theme.PANEL_TEXT_PRIMARY};"
        f"}}"
        f"QDialog[fp_dialog='1'] QHeaderView::section {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {theme.PANEL_TABLE_HEADER_START}, stop:1 {theme.PANEL_TABLE_HEADER_END});"
        f"  color:{theme.PANEL_TEXT_PRIMARY if theme.is_dark else theme.TEXT_WHITE};"
        f"  border:none; padding:8px 10px; font-weight:700;"
        f"}}"
        f"QDialog[fp_dialog='1'] QDialogButtonBox {{"
        f"  border-top:1px solid {theme.PANEL_BORDER_SOFT};"
        f"  margin-top:8px; padding-top:12px;"
        f"}}"
        f"QDialog[fp_dialog='1'] QProgressBar {{"
        f"  background:{theme.PANEL_SURFACE_ALT};"
        f"  border:1px solid {theme.PANEL_BORDER_SOFT};"
        f"  border-radius:9px;"
        f"  min-height:10px;"
        f"}}"
        f"QDialog[fp_dialog='1'] QProgressBar::chunk {{"
        f"  background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {theme.PANEL_NEON_PRIMARY}, stop:1 {theme.PANEL_NEON_SECONDARY});"
        f"  border-radius:8px;"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton {{"
        f"  background:{theme.PANEL_SURFACE_BG};"
        f"  color:{theme.PANEL_TEXT_PRIMARY};"
        f"  border:1px solid {theme.rgba(theme.PANEL_NEON_PRIMARY, 110)};"
        f"  border-radius:14px;"
        f"  padding:9px 18px;"
        f"  min-height:36px;"
        f"  font-weight:700;"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton:hover {{"
        f"  background:{theme.PANEL_SURFACE_ALT};"
        f"  border-color:{theme.PANEL_NEON_SECONDARY};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton:pressed {{"
        f"  background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 26)};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton:disabled {{"
        f"  background:{theme.rgba(theme.PANEL_BORDER_SOFT, 40)};"
        f"  color:{theme.PANEL_TEXT_MUTED};"
        f"  border-color:{theme.PANEL_BORDER_SOFT};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton:default {{"
        f"  border:1px solid {theme.PANEL_NEON_SECONDARY};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='primary'] {{"
        f"  background:{theme.PRIMARY};"
        f"  color:{primary_fg};"
        f"  border:none;"
        f"  font-weight:800;"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='primary']:hover {{"
        f"  background:{theme.PRIMARY_HOVER};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='primary']:pressed {{"
        f"  background:{theme.rgba(theme.PRIMARY, 220)};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='danger'] {{"
        f"  background:{theme.DANGER};"
        f"  color:{theme.TEXT_WHITE};"
        f"  border:none;"
        f"  font-weight:800;"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='danger']:hover {{"
        f"  background:{theme.QColor(theme.DANGER).lighter(112).name()};"
        f"}}"
        f"QDialog[fp_dialog='1'] QPushButton[dialog_kind='danger']:pressed {{"
        f"  background:{theme.QColor(theme.DANGER).darker(118).name()};"
        f"}}"
    )


def _dialog_button_kind_from_role(role: object) -> str:
    role_name = getattr(role, "name", str(role)).split(".")[-1]
    if role_name in {"AcceptRole", "YesRole", "ApplyRole"}:
        return "primary"
    if role_name == "DestructiveRole":
        return "danger"
    return "secondary"


def _apply_button_kind(button: QPushButton, kind: str) -> None:
    button.setProperty("dialog_kind", kind)
    button.style().unpolish(button)
    button.style().polish(button)


def _style_dialog_buttons(dialog: QDialog) -> None:
    if isinstance(dialog, QMessageBox):
        for button in dialog.buttons():
            if isinstance(button, QPushButton):
                _apply_button_kind(button, _dialog_button_kind_from_role(dialog.buttonRole(button)))
        return

    for button_box in dialog.findChildren(QDialogButtonBox):
        for button in button_box.buttons():
            if isinstance(button, QPushButton):
                _apply_button_kind(button, _dialog_button_kind_from_role(button_box.buttonRole(button)))


class _DragMoveFilter(QObject):
    """Permite arrastar um QDialog sem barra de título: clique-segure-arraste
    em qualquer área que não seja um botão/input ativo.

    Instalado uma única vez por diálogo (controlado por `_fp_drag_filter`)."""

    def __init__(self, dialog: QDialog):
        super().__init__(dialog)
        self._dialog = dialog
        self._press_offset: QPoint | None = None

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                # Só inicia drag se o clique NÃO foi num widget interativo.
                child = self._dialog.childAt(event.position().toPoint())
                if not isinstance(child, (QPushButton,)):
                    g = event.globalPosition().toPoint()
                    self._press_offset = g - self._dialog.frameGeometry().topLeft()
                    return False  # não consome — deixa o widget receber também
        elif event.type() == QEvent.Type.MouseMove and self._press_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                g = event.globalPosition().toPoint()
                self._dialog.move(g - self._press_offset)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._press_offset = None
        return False


# Raio (px) dos cantos arredondados do diálogo frameless. Casa com o
# border-radius:18px aplicado em _dialog_surface_style.
_DIALOG_RADIUS = 18


class _DialogResizeMaskFilter(QObject):
    """Reaplica a máscara arredondada quando o diálogo é redimensionado.

    Diálogos podem mudar de tamanho conforme o conteúdo (ex: QMessageBox
    cresce com texto longo). Sem reaplicar a mask, o arredondado fica
    desalinhado com a nova geometria — voltam os cantos pretos.
    """

    def __init__(self, dialog: QDialog, radius: int):
        super().__init__(dialog)
        self._radius = radius

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Resize:
            try:
                _apply_rounded_mask(obj, self._radius)
            except Exception:
                pass
        return False


def _install_frameless_chrome(dialog: QDialog) -> None:
    """Aplica frameless + sombra + drag + máscara arredondada no QDialog/QMessageBox.

    Idempotente: marca o diálogo com `_fp_frameless_applied` para não repetir
    quando `apply_dialog_theme` é chamado várias vezes pelo filter (Polish/Show)."""
    if dialog.property("_fp_frameless_applied"):
        return
    # Mantém Dialog mas tira a barra de título nativa do Windows.
    dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    # Sem a barra nativa, perdemos a sombra do Windows. Compensamos com sombra Qt.
    if dialog.graphicsEffect() is None:
        shadow = QGraphicsDropShadowEffect(dialog)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 8)
        color = QColor(0, 0, 0)
        color.setAlpha(140)
        shadow.setColor(color)
        dialog.setGraphicsEffect(shadow)
    # Drag manual em qualquer parte que não seja botão.
    drag_filter = _DragMoveFilter(dialog)
    dialog.installEventFilter(drag_filter)
    dialog.setProperty("_fp_drag_filter", drag_filter)  # mantém referência viva
    # Máscara arredondada — corta fisicamente os 4 cantos do dialog. Sem isso,
    # o border-radius:18px do QSS desenha os cantos arredondados DENTRO do
    # retângulo da janela, mas os pixels dos 4 cantos externos ficam visíveis
    # com a cor padrão da palette (pretos no tema dark — as "flechas pretas").
    # Aplicada agora e reaplicada via event filter em cada Resize.
    _apply_rounded_mask(dialog, _DIALOG_RADIUS)
    mask_filter = _DialogResizeMaskFilter(dialog, _DIALOG_RADIUS)
    dialog.installEventFilter(mask_filter)
    dialog.setProperty("_fp_dialog_mask_filter", mask_filter)
    dialog.setProperty("_fp_frameless_applied", True)


def apply_dialog_theme(dialog: QDialog) -> QDialog:
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setProperty("fp_dialog", "1")
    dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    # Frameless + sombra + drag — substituem a barra de título nativa do Windows
    # com o look limpo do app. Idempotente.
    _install_frameless_chrome(dialog)

    base_style = dialog.property("_fp_dialog_base_style")
    if base_style is None:
        base_style = dialog.styleSheet() or ""
        dialog.setProperty("_fp_dialog_base_style", base_style)

    dialog.setStyleSheet(f"{base_style}\n{_dialog_surface_style()}".strip())
    _style_dialog_buttons(dialog)
    return dialog


def _animate_dialog_entrance(dialog: QDialog) -> None:
    """Anima a entrada do diálogo: fade-in + pop sutil (escala 96% → 100%).

    Roda em paralelo (~200ms). Usa `windowOpacity` em vez de
    `QGraphicsOpacityEffect` porque o diálogo já tem `QGraphicsDropShadowEffect`
    (Qt só permite UM efeito gráfico por widget).
    """
    # Esconde IMEDIATAMENTE (antes do próximo paint) pra evitar flash visual.
    dialog.setWindowOpacity(0.0)

    # Aguarda o layout calcular a geometria final (Show vem antes do layout
    # estabilizar; sem isso, capturamos um rect vazio/incorreto).
    def _start_animation():
        final_geo = dialog.geometry()
        if final_geo.width() <= 0 or final_geo.height() <= 0:
            # diálogo ainda não posicionado — restaura visibilidade e desiste
            dialog.setWindowOpacity(1.0)
            return

        # Geometria inicial: 96% do tamanho final, mesmo centro
        cx = final_geo.center().x()
        cy = final_geo.center().y()
        scale = 0.96
        sw = max(1, int(final_geo.width() * scale))
        sh = max(1, int(final_geo.height() * scale))
        start_geo = QRect(cx - sw // 2, cy - sh // 2, sw, sh)

        dialog.setGeometry(start_geo)

        opacity_anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        opacity_anim.setDuration(180)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        geo_anim = QPropertyAnimation(dialog, b"geometry", dialog)
        geo_anim.setDuration(200)
        geo_anim.setStartValue(start_geo)
        geo_anim.setEndValue(final_geo)
        # OutBack dá um leve "overshoot" que adiciona vida sem exagero.
        geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Mantém as animações vivas até terminarem (sem ref, GC mata cedo).
        dialog.setProperty("_fp_anim_opacity", opacity_anim)
        dialog.setProperty("_fp_anim_geo", geo_anim)
        opacity_anim.start()
        geo_anim.start()

    # 0ms = próximo tick do event loop, depois do layout
    QTimer.singleShot(0, _start_animation)


class _DialogThemeFilter(QObject):
    def eventFilter(self, obj, event):
        if not isinstance(obj, QDialog):
            return False
        if event.type() == QEvent.Type.Polish:
            apply_dialog_theme(obj)
        elif event.type() == QEvent.Type.Show:
            apply_dialog_theme(obj)
            # Anima a entrada só na primeira exibição (evita reanimar se o
            # diálogo for escondido/reaparecido em outro fluxo).
            if not obj.property("_fp_anim_played"):
                obj.setProperty("_fp_anim_played", True)
                _animate_dialog_entrance(obj)
        return False


def _inject_dialog_option(
    args: tuple,
    kwargs: dict,
    *,
    option_index: int,
    flag: object,
) -> tuple[tuple, dict]:
    args_list = list(args)
    if "options" in kwargs:
        kwargs["options"] = kwargs.get("options") | flag
        return tuple(args_list), kwargs
    if len(args_list) > option_index:
        args_list[option_index] = args_list[option_index] | flag
        return tuple(args_list), kwargs
    kwargs["options"] = flag
    return tuple(args_list), kwargs


def _patch_static_dialogs() -> None:
    if getattr(QFileDialog, "_fp_theme_hooks_installed", False):
        return

    original_get_open_file_name = QFileDialog.getOpenFileName
    original_get_open_file_names = QFileDialog.getOpenFileNames
    original_get_save_file_name = QFileDialog.getSaveFileName
    original_get_existing_directory = QFileDialog.getExistingDirectory
    original_get_color = QColorDialog.getColor
    original_get_font = QFontDialog.getFont

    def _get_open_file_name(*args, **kwargs):
        args, kwargs = _inject_dialog_option(args, kwargs, option_index=5, flag=QFileDialog.Option.DontUseNativeDialog)
        return original_get_open_file_name(*args, **kwargs)

    def _get_open_file_names(*args, **kwargs):
        args, kwargs = _inject_dialog_option(args, kwargs, option_index=5, flag=QFileDialog.Option.DontUseNativeDialog)
        return original_get_open_file_names(*args, **kwargs)

    def _get_save_file_name(*args, **kwargs):
        args, kwargs = _inject_dialog_option(args, kwargs, option_index=5, flag=QFileDialog.Option.DontUseNativeDialog)
        return original_get_save_file_name(*args, **kwargs)

    def _get_existing_directory(*args, **kwargs):
        args, kwargs = _inject_dialog_option(args, kwargs, option_index=3, flag=QFileDialog.Option.DontUseNativeDialog)
        return original_get_existing_directory(*args, **kwargs)

    def _get_color(*args, **kwargs):
        args, kwargs = _inject_dialog_option(
            args,
            kwargs,
            option_index=3,
            flag=QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        return original_get_color(*args, **kwargs)

    def _get_font(*args, **kwargs):
        args, kwargs = _inject_dialog_option(
            args,
            kwargs,
            option_index=3,
            flag=QFontDialog.FontDialogOption.DontUseNativeDialog,
        )
        return original_get_font(*args, **kwargs)

    QFileDialog.getOpenFileName = staticmethod(_get_open_file_name)
    QFileDialog.getOpenFileNames = staticmethod(_get_open_file_names)
    QFileDialog.getSaveFileName = staticmethod(_get_save_file_name)
    QFileDialog.getExistingDirectory = staticmethod(_get_existing_directory)
    QColorDialog.getColor = staticmethod(_get_color)
    QFontDialog.getFont = staticmethod(_get_font)
    QFileDialog._fp_theme_hooks_installed = True


def _message_box_style() -> str:
    return _dialog_surface_style()


def _message_box_button_style() -> str:
    return ""


def apply_message_box_theme(box: QMessageBox) -> QMessageBox:
    apply_dialog_theme(box)
    box.installEventFilter(_MESSAGE_BOX_SHORTCUT_FILTER)
    _style_dialog_buttons(box)
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


# Raio (px) dos cantos arredondados do popup de QComboBox. Casa com o
# border-radius aplicado em theme.py QComboBox QAbstractItemView.
_COMBO_POPUP_RADIUS = 10


def _apply_rounded_mask(widget: QWidget, radius: int) -> None:
    """Aplica máscara arredondada no widget — corta fisicamente os 4 cantos.

    A mask é em coordenadas locais (`widget.rect()`), então acompanha a
    posição do widget na tela; só precisa ser reaplicada se o tamanho mudar.
    """
    rect = widget.rect()
    if rect.width() <= 0 or rect.height() <= 0:
        return
    path = QPainterPath()
    path.addRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
    region = QRegion(path.toFillPolygon().toPolygon())
    widget.setMask(region)


class _ComboPopupResizeMaskFilter(QObject):
    """Reaplica a máscara arredondada quando o container do popup é redimensionado.

    O Qt pode redimensionar o popup do QComboBox conforme o número de items
    ou após o show inicial. Sem reaplicar a mask, o arredondado fica
    desalinhado com a nova geometria.
    """

    def __init__(self, container: QWidget, radius: int):
        super().__init__(container)
        self._radius = radius

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            try:
                _apply_rounded_mask(obj, self._radius)
            except Exception:
                pass
        return False


def _install_resize_remask_filter(container: QWidget, radius: int) -> None:
    """Instala o filtro de re-mask uma única vez por container (idempotente)."""
    if container.property("_fp_combo_remask_filter"):
        return
    filt = _ComboPopupResizeMaskFilter(container, radius)
    container.installEventFilter(filt)
    container.setProperty("_fp_combo_remask_filter", filt)  # mantém ref viva


def install_combo_popup_chrome() -> None:
    """Limpa o chrome do popup de TODOS os QComboBox.

    Bug que esta função resolve: em Windows + Fusion, o popup do QComboBox
    aparece com "4 cantos pretos" ao redor da view. Causa: o **container**
    da janela popup (parent da QAbstractItemView) é pintado com
    `palette().window()` do tema, que no dark mode resolve pra preto. Quando
    a view tem `border-radius`, os pixels dos cantos não cobertos pelo
    arredondado mostram o preto do container.

    NÃO usamos `WA_TranslucentBackground` + `FramelessWindowHint` no popup
    (tentativa anterior em 067f577): em Windows o composit não suporta alpha
    em janelas `Qt.Popup`, renderizando o popup inteiro como retângulo PRETO
    opaco — pior do que o problema original.

    Estratégia segura, sem mexer em window flags nem translucency:
    1. `setFrameShape(NoFrame)` na view → borda vem só do QSS.
    2. Força a cor de fundo do **popup container** (parent da view) pra
       PANEL_SURFACE_BG via palette + autoFillBackground. Assim mesmo que
       o QSS interno do view tenha border-radius, os "cantos" do container
       aparecem na cor do tema, não pretos.

    Idempotente: instala o patch uma única vez por processo.
    """
    if getattr(QComboBox, "_fp_combo_chrome_installed", False):
        return

    original_show_popup = QComboBox.showPopup
    original_hide_popup = QComboBox.hidePopup

    def _patched_show_popup(self):
        # Se o popup ainda está animando o fechamento de uma seleção anterior,
        # cancela a animação de saída e reseta opacity/geometry pra abertura
        # começar do zero. Evita "tremida" se o usuário abre/seleciona/abre rápido.
        prev_view = self.view()
        if prev_view is not None:
            prev_container = prev_view.parentWidget()
            if prev_container is not None:
                for prop in ("_fp_combo_close_anim_opacity", "_fp_combo_close_anim_geo"):
                    anim = prev_container.property(prop)
                    if anim is not None:
                        try:
                            anim.stop()
                        except Exception:
                            pass

        original_show_popup(self)
        view = self.view()
        if view is None:
            return
        # 1) Remove o frame interno da QListView/AbstractItemView para que
        #    a borda venha exclusivamente do QSS (que respeita o tema).
        try:
            view.setFrameShape(QFrame.Shape.NoFrame)
        except Exception:
            pass
        # 2) Força o background do CONTAINER do popup (parent do view) pra
        #    cor do tema. Sem isso o Fusion pinta preto nos cantos onde o
        #    border-radius do view não cobre.
        container = None
        try:
            container = view.parentWidget()
            if container is not None:
                surface_color = QColor(theme.PANEL_SURFACE_BG)
                pal = container.palette()
                pal.setColor(QPalette.ColorRole.Window, surface_color)
                pal.setColor(QPalette.ColorRole.Base, surface_color)
                container.setPalette(pal)
                container.setAutoFillBackground(True)
        except Exception:
            container = None
        # 2.5) Aplica máscara arredondada no container — corta fisicamente os
        #      4 cantos da janela popup, permitindo border-radius no QSS sem
        #      mostrar abas nos cantos. Reaplica via eventFilter em Resize
        #      pra cobrir mudanças de tamanho do popup.
        if container is not None:
            try:
                _apply_rounded_mask(container, _COMBO_POPUP_RADIUS)
                _install_resize_remask_filter(container, _COMBO_POPUP_RADIUS)
            except Exception:
                pass
        # 3) Animação de entrada: fade-in + leve slide-down (6px). Usa
        #    windowOpacity no container do popup (top-level Qt.Popup) — o DWM
        #    gerencia, não tem o bug do composit do WA_TranslucentBackground.
        if container is not None:
            try:
                _animate_combo_popup_entrance(container)
            except Exception:
                # Em qualquer falha, garante que o popup fique visível.
                try:
                    container.setWindowOpacity(1.0)
                except Exception:
                    pass

    def _patched_hide_popup(self):
        view = self.view()
        if view is None:
            original_hide_popup(self)
            return
        container = view.parentWidget()
        if container is None:
            original_hide_popup(self)
            return
        try:
            _animate_combo_popup_exit(container, lambda: original_hide_popup(self))
        except Exception:
            # Qualquer falha → fecha de imediato (comportamento original).
            original_hide_popup(self)

    QComboBox.showPopup = _patched_show_popup
    QComboBox.hidePopup = _patched_hide_popup
    QComboBox._fp_combo_chrome_installed = True


def _animate_combo_popup_entrance(container: QWidget) -> None:
    """Anima entrada do popup do QComboBox: fade-in 140ms + slide-down 6px.

    - windowOpacity 0 → 1 (OutCubic, 140ms)
    - geometria desloca de y-6 → y final (OutCubic, 160ms)

    Roda em CADA showPopup (o popup pode ser reusado entre aberturas, e cada
    abertura merece a animação). Refs ficam guardadas no container até a
    proxima abertura (ou GC junto com o container).
    """
    final_geo = container.geometry()
    if final_geo.width() <= 0 or final_geo.height() <= 0:
        return

    start_geo = QRect(
        final_geo.x(),
        final_geo.y() - 6,
        final_geo.width(),
        final_geo.height(),
    )

    container.setWindowOpacity(0.0)
    container.setGeometry(start_geo)

    opacity_anim = QPropertyAnimation(container, b"windowOpacity", container)
    opacity_anim.setDuration(140)
    opacity_anim.setStartValue(0.0)
    opacity_anim.setEndValue(1.0)
    opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    geo_anim = QPropertyAnimation(container, b"geometry", container)
    geo_anim.setDuration(160)
    geo_anim.setStartValue(start_geo)
    geo_anim.setEndValue(final_geo)
    geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # Mantém refs vivas até as anims terminarem (sem isso, GC mata cedo).
    container.setProperty("_fp_combo_anim_opacity", opacity_anim)
    container.setProperty("_fp_combo_anim_geo", geo_anim)
    opacity_anim.start()
    geo_anim.start()


def _animate_combo_popup_exit(container: QWidget, do_hide) -> None:
    """Anima saída do popup do QComboBox: fade-out 140ms + slide-up 6px.

    Espelha _animate_combo_popup_entrance, mas no sentido inverso:
    - windowOpacity 1 → 0 (InCubic, 140ms)
    - geometria desloca de y → y-6 (InCubic, 160ms)

    `do_hide` é uma callable que chama o `hidePopup` original do Qt. A gente
    adia essa chamada até a animação terminar — assim o popup permanece
    visível enquanto desaparece suavemente. Depois resetamos
    windowOpacity/geometry pra que a próxima abertura comece do estado limpo.
    """
    current_geo = container.geometry()
    if current_geo.width() <= 0 or current_geo.height() <= 0:
        do_hide()
        return

    target_geo = QRect(
        current_geo.x(),
        current_geo.y() - 6,
        current_geo.width(),
        current_geo.height(),
    )
    start_opacity = container.windowOpacity()
    if start_opacity <= 0.0:
        start_opacity = 1.0  # se já estava 0 por algum motivo, anima do 1

    opacity_anim = QPropertyAnimation(container, b"windowOpacity", container)
    opacity_anim.setDuration(140)
    opacity_anim.setStartValue(start_opacity)
    opacity_anim.setEndValue(0.0)
    opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    geo_anim = QPropertyAnimation(container, b"geometry", container)
    geo_anim.setDuration(160)
    geo_anim.setStartValue(current_geo)
    geo_anim.setEndValue(target_geo)
    geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    def _on_finished(saved_geo=current_geo):
        # 1) Fecha o popup de verdade (chamada Qt original).
        try:
            do_hide()
        except Exception:
            pass
        # 2) Reseta estado pra próxima abertura começar limpa
        #    (windowOpacity=1 + geometria final original).
        try:
            container.setWindowOpacity(1.0)
            container.setGeometry(saved_geo)
        except Exception:
            pass

    # Usa o `finished` da opacity (que termina primeiro) pra disparar o hide.
    # Geo continua animando até completar — sem efeito visual já que opacity=0.
    opacity_anim.finished.connect(_on_finished)

    container.setProperty("_fp_combo_close_anim_opacity", opacity_anim)
    container.setProperty("_fp_combo_close_anim_geo", geo_anim)
    opacity_anim.start()
    geo_anim.start()


def install_dialog_theme_hooks(app: QApplication | None = None) -> None:
    install_message_box_theme_hooks()
    install_combo_popup_chrome()
    _patch_static_dialogs()

    global _DIALOG_THEME_FILTER
    target_app = app or QApplication.instance()
    if target_app is None:
        return
    if getattr(target_app, "_fp_dialog_theme_filter_installed", False):
        return

    _DIALOG_THEME_FILTER = _DialogThemeFilter()
    target_app.installEventFilter(_DIALOG_THEME_FILTER)
    target_app._fp_dialog_theme_filter_installed = True


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
