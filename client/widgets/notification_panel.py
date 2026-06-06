"""
Drawer lateral de notificações.

NotificationDrawer — painel que desliza da direita sobre o conteúdo principal.
                     Usa os tokens DRAWER_* de theme.py (suporte a dark mode).
_Overlay           — camada semitransparente com fade; fecha o drawer ao clicar.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core import theme
from ..core.datetime_utils import LOCAL_TIMEZONE, parse_datetime
from ..core.resolution import res
from .smooth_scroll import apply_smooth_scroll

# ── Constantes ────────────────────────────────────────────────────────────────

DRAWER_WIDTH = 400
ANIM_MS      = 280

_ICONS: dict[str, str] = {
    "nova_requisicao":   "🏭",
    "em_producao":       "⚙️",
    "finalizada":        "✅",
    "cancelada":         "❌",
    "prod_cancelada":    "⚠️",
    "requisicao_parada": "⏰",
}

_ACCENT: dict[str, str] = {
    "nova_requisicao":   "#2563EB",
    "em_producao":       "#16A34A",
    "finalizada":        "#16A34A",
    "cancelada":         "#DC2626",
    "prod_cancelada":    "#D97706",
    "requisicao_parada": "#D97706",
}

_ICONS.update({
    "faturado": "💰",
    "finalizado": "✅",
    "machine_status": "🛠️",
})

_ACCENT.update({
    "faturado": "#16A34A",
    "finalizado": "#10B981",
    "machine_status": "#2563EB",
})

_DEFAULT_ACCENT = "#2563EB"


def _blend_color(base_hex: str, tint_hex: str, tint_alpha: int) -> str:
    """Mistura tint_hex sobre base_hex com alpha (0-255) e retorna #RRGGBB."""
    base = QColor(base_hex)
    tint = QColor(tint_hex)
    a = max(0.0, min(1.0, float(tint_alpha) / 255.0))
    r = int(round(base.red() * (1.0 - a) + tint.red() * a))
    g = int(round(base.green() * (1.0 - a) + tint.green() * a))
    b = int(round(base.blue() * (1.0 - a) + tint.blue() * a))
    return f"#{r:02X}{g:02X}{b:02X}"


# ── Helper: timestamp relativo ────────────────────────────────────────────────

def _relative_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = parse_datetime(iso)
        if dt is None:
            return ""
        diff = (datetime.now(LOCAL_TIMEZONE) - dt).total_seconds()
        if diff < 60:
            return "agora"
        if diff < 3_600:
            return f"há {int(diff / 60)} min"
        if diff < 86_400:
            return f"há {int(diff / 3_600)}h"
        if diff < 172_800:
            return "ontem"
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return ""


# ── Overlay ───────────────────────────────────────────────────────────────────

class _Overlay(QWidget):
    """Fundo semitransparente com fade — fecha o drawer ao ser clicado."""

    clicked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(f"background: {theme.DRAWER_OVERLAY};")
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._anim_in = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim_in.setDuration(ANIM_MS)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_out = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim_out.setDuration(ANIM_MS)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self.hide)

    def fade_in(self):
        self._anim_out.stop()
        self.show()
        self.raise_()
        self._anim_in.setStartValue(self._effect.opacity())
        self._anim_in.start()

    def fade_out(self):
        self._anim_in.stop()
        self._anim_out.setStartValue(self._effect.opacity())
        self._anim_out.start()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


# ── Drawer ────────────────────────────────────────────────────────────────────

class NotificationDrawer(QWidget):
    """Painel lateral que desliza da direita listando notificações não lidas."""

    mark_all_requested = Signal()
    open_req_requested = Signal(int)
    mark_one_requested = Signal(int)
    closed             = Signal()

    def __init__(self, notifications: list, parent: QWidget):
        super().__init__(parent)
        self._notifications = notifications
        self._closing       = False
        # Fator de acessibilidade (tamanho dos pop-ups/painel)
        self._factor = res.notification_factor
        self._width  = max(1, round(DRAWER_WIDTH * self._factor))
        self._setup()

    # Helpers de escala
    def _sc(self, value: float) -> int:
        return max(1, round(value * self._factor))

    def _pt(self, value: float) -> int:
        return max(7, round(value * self._factor))

    # ── Build ─────────────────────────────────────────────────────────────────

    def _setup(self):
        parent = self.parent()

        # Overlay
        self._overlay = _Overlay(parent)
        self._overlay.clicked.connect(self.close_drawer)
        self._overlay.setGeometry(0, 0, parent.width(), parent.height())
        self._overlay.hide()

        # Drawer container
        self.setFixedWidth(self._width)
        self.setObjectName("notifDrawer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#notifDrawer {{ background: {theme.DRAWER_BG}; }}"
            f"QWidget#notifDrawer QLabel, QWidget#notifDrawer QPushButton {{"
            f"  font-family: 'Inter', 'Segoe UI';"
            f"  font-weight: 700;"
            f"}}"
            f"QFrame {{ border: none; }}"
        )

        # Sombra lateral esquerda
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 44, 109, 50 if not theme.is_dark else 200))
        shadow.setOffset(-8, 0)
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)
        self._build_list(root)
        self._build_footer(root)

        # Animações deslizamento
        self._anim_open = QPropertyAnimation(self, b"pos", self)
        self._anim_open.setDuration(ANIM_MS)
        self._anim_open.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_close = QPropertyAnimation(self, b"pos", self)
        self._anim_close.setDuration(ANIM_MS)
        self._anim_close.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_close.finished.connect(self._on_closed)

        self.move(parent.width(), 0)
        self.resize(self._width, parent.height())
        self.hide()

    def _build_header(self, root: QVBoxLayout):
        # Barra de acento no topo
        accent_bar = QFrame()
        accent_bar.setObjectName("drawerAccent")
        accent_bar.setFixedHeight(3)
        accent_bar.setStyleSheet(
            f"QFrame#drawerAccent {{ background: {theme.PRIMARY}; border: none; }}"
        )
        root.addWidget(accent_bar)

        # Cabeçalho
        header = QWidget()
        header.setObjectName("drawerHeader")
        header.setFixedHeight(62)
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setStyleSheet(
            f"QWidget#drawerHeader {{"
            f"  background: {theme.DRAWER_HEADER};"
            f"  border-bottom: 1px solid {theme.DRAWER_BORDER};"
            f"}}"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(18, 0, 14, 0)
        hlay.setSpacing(10)

        # Ícone + título + badge de contagem
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setContentsMargins(0, 0, 0, 0)

        bell = QLabel("🔔")
        bell.setStyleSheet("font-size: 15px; background: transparent;")
        title_row.addWidget(bell)

        title = QLabel("Notificações")
        title.setStyleSheet(
            f"color: {theme.DRAWER_TITLE}; font-size: 11pt; font-weight: 700;"
            f"background: transparent;"
            f"font-family: 'Inter', 'Segoe UI';"
        )
        title_row.addWidget(title)

        count = len(self._notifications)
        if count:
            badge = QLabel(str(count))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setMinimumWidth(26)
            badge.setFixedHeight(22)
            badge.setStyleSheet(
                f"background: {theme.DANGER}; color: #fff; border-radius: 11px;"
                f"padding: 2px 8px; font-size: 9pt; font-weight: 700;"
                f"font-family: 'Inter', 'Segoe UI';"
            )
            title_row.addWidget(badge)

        hlay.addLayout(title_row, 1)

        # Botão "Marcar todas" — estilo ghost
        if self._notifications:
            btn_all = QPushButton("Marcar todas")
            btn_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_all.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent; color: {theme.PRIMARY};"
                f"  border: 1px solid {theme.PRIMARY}; border-radius: 6px;"
                f"  padding: 4px 11px; font-size: 8pt; font-weight: 700;"
                f"  font-family: 'Inter', 'Segoe UI';"
                f"}}"
                f"QPushButton:hover {{ background: {theme.SELECTION_BG}; }}"
            )
            btn_all.clicked.connect(self._on_mark_all)
            hlay.addWidget(btn_all)

        # Botão fechar
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 30)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {theme.TEXT_LABEL};"
            f"  border: none; border-radius: 15px; font-size: 13px;"
            f"  font-family: 'Inter', 'Segoe UI';"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {theme.BORDER_COLOR}; color: {theme.TEXT_DARK};"
            f"}}"
        )
        btn_close.clicked.connect(self.close_drawer)
        hlay.addWidget(btn_close)

        root.addWidget(header)

    def _build_list(self, root: QVBoxLayout):
        scroll = QScrollArea()
        apply_smooth_scroll(scroll)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {theme.DRAWER_BG}; }}"
            f"QScrollBar:vertical {{"
            f"  width: 6px; background: transparent; margin: 4px 2px;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {theme.DRAWER_SCROLL}; border-radius: 3px; min-height: 32px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.BORDER_COLOR}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )

        container = QWidget()
        container.setObjectName("drawerListContainer")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(
            f"QWidget#drawerListContainer {{ background: {theme.DRAWER_BG}; }}"
        )
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(14, 16, 14, 16)
        vlay.setSpacing(10)

        if not self._notifications:
            self._build_empty_state(vlay)
        else:
            for n in self._notifications:
                vlay.addWidget(self._make_card(n))

        vlay.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _build_empty_state(self, vlay: QVBoxLayout):
        """Estado vazio: ícone grande + textos centralizados."""
        wrapper = QWidget()
        wrapper_lay = QVBoxLayout(wrapper)
        wrapper_lay.setContentsMargins(20, 46, 20, 36)
        wrapper_lay.setSpacing(8)
        wrapper_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        emoji_lbl = QLabel("🎉")
        emoji_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji_lbl.setStyleSheet(
            "font-size: 42px; background: transparent;"
        )
        wrapper_lay.addWidget(emoji_lbl)

        title_lbl = QLabel("Tudo em dia!")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {theme.DRAWER_TITLE}; font-size: 13pt; font-weight: 700;"
            f"background: transparent;"
            f"font-family: 'Inter', 'Segoe UI';"
        )
        wrapper_lay.addWidget(title_lbl)

        sub_lbl = QLabel("Não há notificações\nnão lidas no momento.")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)
        sub_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        sub_lbl.setMaximumWidth(self._width - self._sc(84))
        sub_lbl.setMinimumHeight(44)
        sub_lbl.setStyleSheet(
            f"color: {theme.DRAWER_MUTED}; font-size: 9pt;"
            f"background: transparent;"
            f"font-family: 'Inter', 'Segoe UI';"
        )
        wrapper_lay.addWidget(sub_lbl)

        vlay.addWidget(wrapper)

    def _build_footer(self, root: QVBoxLayout):
        count = len(self._notifications)
        if not count:
            return

        s = "notificação não lida" if count == 1 else "notificações não lidas"

        footer = QWidget()
        footer.setObjectName("drawerFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        footer.setStyleSheet(
            f"QWidget#drawerFooter {{"
            f"  background: {theme.DRAWER_HEADER};"
            f"  border-top: 1px solid {theme.DRAWER_BORDER};"
            f"}}"
        )
        flay = QHBoxLayout(footer)
        flay.setContentsMargins(18, 10, 18, 10)
        flay.setSpacing(8)

        count_lbl = QLabel(f"{count} {s}")
        count_lbl.setStyleSheet(
            f"color: {theme.TEXT_LABEL}; font-size: 8pt;"
            f"background: transparent;"
            f"font-family: 'Inter', 'Segoe UI';"
        )
        flay.addWidget(count_lbl, 1)

        root.addWidget(footer)

    def _make_card(self, n: dict) -> QFrame:
        ntype  = n.get("type", "")
        accent = _ACCENT.get(ntype, _DEFAULT_ACCENT)

        card = QFrame()
        card.setObjectName("drawerNotifCard")
        card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        led_bg_top = _blend_color(theme.DRAWER_CARD, accent, 58)
        led_bg_bottom = _blend_color(theme.DRAWER_CARD, accent, 20)
        led_hover_top = _blend_color(theme.DRAWER_CARD, accent, 74)
        led_hover_bottom = _blend_color(theme.DRAWER_CARD, accent, 28)

        card.setStyleSheet(
            f"QFrame#drawerNotifCard {{"
            f"  background: qlineargradient("
            f"    x1:0, y1:0, x2:1, y2:1,"
            f"    stop:0 {led_bg_top},"
            f"    stop:0.52 {theme.DRAWER_CARD},"
            f"    stop:1 {led_bg_bottom}"
            f"  );"
            f"  border: 1px solid {theme.DRAWER_BORDER} !important;"
            f"  border-radius: 10px;"
            f"}}"
            f"QFrame#drawerNotifCard:hover {{"
            f"  background: qlineargradient("
            f"    x1:0, y1:0, x2:1, y2:1,"
            f"    stop:0 {led_hover_top},"
            f"    stop:0.52 {theme.DRAWER_CARD},"
            f"    stop:1 {led_hover_bottom}"
            f"  );"
            f"  border-color: {accent} !important;"
            f"}}"
            f"QLabel {{ background: transparent; border: none !important; }}"
            f"QPushButton {{ background: transparent; }}"
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(self._sc(14), self._sc(12), self._sc(12), self._sc(11))
        lay.setSpacing(self._sc(6))

        # ── Linha superior: ícone + título + dot + timestamp ──
        top = QHBoxLayout()
        top.setSpacing(self._sc(8))
        top.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel(_ICONS.get(ntype, "🔔"))
        icon_lbl.setStyleSheet(
            f"font-size: {self._sc(16)}px; background: transparent; border: none;"
        )
        icon_lbl.setFixedWidth(self._sc(24))
        top.addWidget(icon_lbl)

        title_lbl = QLabel(n.get("title", ""))
        title_lbl.setStyleSheet(
            f"font-weight: 700; font-size: {self._pt(10)}pt; color: {theme.DRAWER_TITLE};"
            f"background: transparent; border: none;"
            f"font-family: 'Inter', 'Segoe UI';"
        )
        title_lbl.setWordWrap(True)
        top.addWidget(title_lbl, 1)

        # Dot colorido de não lida
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {accent}; font-size: {self._sc(9)}px; background: transparent; border: none;"
        )
        top.addWidget(dot)

        ts = _relative_time(n.get("created_at"))
        if ts:
            ts_lbl = QLabel(ts)
            ts_lbl.setStyleSheet(
                f"color: {theme.DRAWER_MUTED}; font-size: {self._pt(8)}pt; background: transparent; border: none;"
                f"font-family: 'Inter', 'Segoe UI';"
            )
            top.addWidget(ts_lbl)

        lay.addLayout(top)

        # ── Mensagem ──
        msg = n.get("message", "")
        if msg:
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"color: {theme.DRAWER_BODY}; font-size: {self._pt(9)}pt;"
                f"background: transparent; border: none;"
                f"font-family: 'Inter', 'Segoe UI';"
                f"padding-left: {self._sc(32)}px;"
            )
            msg_lbl.setWordWrap(True)
            lay.addWidget(msg_lbl)

        # ── Botões de ação ──
        nid    = n.get("id")
        req_id = n.get("requisition_id")

        if nid or req_id:
            btns = QHBoxLayout()
            btns.setSpacing(self._sc(6))
            btns.setContentsMargins(self._sc(32), self._sc(2), 0, 0)
            btns.addStretch()

            _btn_pad = f"padding: {self._sc(3)}px {self._sc(10)}px; font-size: {self._pt(7)}pt;"

            if nid:
                btn_read = QPushButton("✓  Marcar lida")
                btn_read.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_read.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: transparent; color: {theme.TEXT_LABEL};"
                    f"  border: 1px solid {theme.DRAWER_BORDER}; border-radius: {self._sc(5)}px;"
                    f"  {_btn_pad}"
                    f"  font-family: 'Inter', 'Segoe UI';"
                    f"}}"
                    f"QPushButton:hover {{"
                    f"  color: {theme.SUCCESS}; border-color: {theme.SUCCESS};"
                    f"  background: transparent;"
                    f"}}"
                )
                btn_read.clicked.connect(lambda checked=False, i=nid: self._on_mark_one(i))
                btns.addWidget(btn_read)

            if req_id:
                btn_open = QPushButton("Abrir  →")
                btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_open.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: {theme.PRIMARY}; color: #fff;"
                    f"  border: none; border-radius: {self._sc(5)}px;"
                    f"  {_btn_pad} font-weight: 700;"
                    f"  font-family: 'Inter', 'Segoe UI';"
                    f"}}"
                    f"QPushButton:hover {{ background: {theme.PRIMARY_HOVER}; }}"
                )
                btn_open.clicked.connect(lambda checked=False, rid=req_id: self._on_open(rid))
                btns.addWidget(btn_open)

            lay.addLayout(btns)

        return card

    # ── Animação ──────────────────────────────────────────────────────────────

    def open_drawer(self):
        parent = self.parent()
        pw, ph = parent.width(), parent.height()

        self._overlay.setGeometry(0, 0, pw, ph)
        self._overlay.fade_in()

        self.resize(self._width, ph)
        self.move(pw, 0)
        self.show()
        self.raise_()

        self._anim_open.setStartValue(QPoint(pw, 0))
        self._anim_open.setEndValue(QPoint(pw - self._width, 0))
        self._anim_open.start()

    def close_drawer(self):
        if self._closing:
            return
        self._closing = True

        self._overlay.fade_out()

        pw = self.parent().width()
        self._anim_close.setStartValue(self.pos())
        self._anim_close.setEndValue(QPoint(pw, 0))
        self._anim_close.start()

    def _on_closed(self):
        self.hide()
        self.closed.emit()
        self._overlay.deleteLater()
        self.deleteLater()

    # ── Ações ─────────────────────────────────────────────────────────────────

    def _on_mark_all(self):
        self.mark_all_requested.emit()
        self.close_drawer()

    def _on_mark_one(self, nid: int):
        self.mark_one_requested.emit(nid)
        self.close_drawer()

    def _on_open(self, req_id: int):
        self.open_req_requested.emit(req_id)
        self.close_drawer()
