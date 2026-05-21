"""
Drawer lateral de notificações.

NotificationDrawer — painel que desliza da direita sobre o conteúdo principal.
                     Usa os tokens DRAWER_* de theme.py (suporte a dark mode).
_Overlay           — camada semitransparente com fade; fecha o drawer ao clicar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..core import theme

# ── Constantes ────────────────────────────────────────────────────────────────

DRAWER_WIDTH = 400
ANIM_MS      = 260

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

_DEFAULT_ACCENT = "#2563EB"


# ── Helper: timestamp relativo ────────────────────────────────────────────────

def _relative_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - dt).total_seconds()
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
        self._setup()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _setup(self):
        parent = self.parent()

        # Overlay
        self._overlay = _Overlay(parent)
        self._overlay.clicked.connect(self.close_drawer)
        self._overlay.setGeometry(0, 0, parent.width(), parent.height())
        self._overlay.hide()

        # Drawer
        self.setFixedWidth(DRAWER_WIDTH)
        self.setStyleSheet(
            f"QWidget {{ background: {theme.DRAWER_BG}; }}"
            f"QFrame {{ border: none; }}"
        )

        # Sombra lateral (esquerda)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 44, 109, 40 if not theme.is_dark else 160))
        shadow.setOffset(-6, 0)
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)
        self._build_list(root)
        self._build_footer(root)

        # Animações
        self._anim_open = QPropertyAnimation(self, b"pos", self)
        self._anim_open.setDuration(ANIM_MS)
        self._anim_open.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_close = QPropertyAnimation(self, b"pos", self)
        self._anim_close.setDuration(ANIM_MS)
        self._anim_close.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_close.finished.connect(self._on_closed)

        self.move(parent.width(), 0)
        self.resize(DRAWER_WIDTH, parent.height())
        self.hide()

    def _build_header(self, root: QVBoxLayout):
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(
            f"background: {theme.DRAWER_HEADER};"
            f"border-bottom: 1px solid {theme.DRAWER_BORDER};"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 0, 14, 0)
        hlay.setSpacing(10)

        title = QLabel("🔔  Notificações")
        title.setStyleSheet(
            f"color: {theme.DRAWER_TITLE};"
            f"font-size: 11pt; font-weight: 700;"
            f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
            f"background: transparent;"
        )
        hlay.addWidget(title, 1)

        if self._notifications:
            btn_all = QPushButton("Marcar todas")
            btn_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_all.setStyleSheet(
                f"QPushButton {{"
                f"  background: {theme.PRIMARY}; color: {theme.TEXT_WHITE};"
                f"  border: none; border-radius: 6px;"
                f"  padding: 5px 12px; font-size: 8pt; font-weight: 600;"
                f"  font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
                f"}}"
                f"QPushButton:hover {{ background: {theme.PRIMARY_HOVER}; }}"
            )
            btn_all.clicked.connect(self._on_mark_all)
            hlay.addWidget(btn_all)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {theme.TEXT_LABEL};"
            f"  border: none; border-radius: 14px; font-size: 13px;"
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
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {theme.DRAWER_BG}; }}"
            f"QScrollBar:vertical {{"
            f"  width: 5px; background: transparent; margin: 0;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {theme.DRAWER_SCROLL}; border-radius: 2px; min-height: 28px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.BORDER_COLOR}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background: {theme.DRAWER_BG};")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(14, 14, 14, 14)
        vlay.setSpacing(8)

        if not self._notifications:
            lbl = QLabel("Nenhuma notificação não lida  🎉")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {theme.TEXT_LABEL}; font-size: 10pt;"
                f"padding: 60px 20px; background: transparent;"
                f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
            )
            vlay.addWidget(lbl)
        else:
            for n in self._notifications:
                vlay.addWidget(self._make_card(n))

        vlay.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _build_footer(self, root: QVBoxLayout):
        count = len(self._notifications)
        if not count:
            return
        s = "notificação não lida" if count == 1 else "notificações não lidas"
        footer = QLabel(f"{count} {s}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"background: {theme.DRAWER_HEADER};"
            f"color: {theme.TEXT_LABEL}; font-size: 8pt;"
            f"padding: 8px;"
            f"border-top: 1px solid {theme.DRAWER_BORDER};"
            f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
        )
        root.addWidget(footer)

    def _make_card(self, n: dict) -> QFrame:
        ntype  = n.get("type", "")
        accent = _ACCENT.get(ntype, _DEFAULT_ACCENT)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{"
            f"  background: {theme.DRAWER_CARD};"
            f"  border: 1px solid {theme.DRAWER_BORDER};"
            f"  border-left: 4px solid {accent};"
            f"  border-radius: 8px;"
            f"}}"
            f"QLabel {{ background: transparent; }}"
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)

        # ── Linha superior: ícone + título + ponto + timestamp ──
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel(_ICONS.get(ntype, "🔔"))
        icon_lbl.setStyleSheet("font-size: 15px;")
        icon_lbl.setFixedWidth(22)
        top.addWidget(icon_lbl)

        title_lbl = QLabel(n.get("title", ""))
        title_lbl.setStyleSheet(
            f"font-weight: 700; font-size: 9pt; color: {theme.DRAWER_TITLE};"
            f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
        )
        title_lbl.setWordWrap(True)
        top.addWidget(title_lbl, 1)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent}; font-size: 7px;")
        top.addWidget(dot)

        ts = _relative_time(n.get("created_at"))
        if ts:
            ts_lbl = QLabel(ts)
            ts_lbl.setStyleSheet(
                f"color: {theme.DRAWER_MUTED}; font-size: 7pt;"
                f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
            )
            top.addWidget(ts_lbl)

        lay.addLayout(top)

        # ── Mensagem ──
        msg = n.get("message", "")
        if msg:
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"color: {theme.DRAWER_BODY}; font-size: 8pt;"
                f"font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
                f"padding-left: 30px;"
            )
            msg_lbl.setWordWrap(True)
            lay.addWidget(msg_lbl)

        # ── Botões de ação ──
        nid    = n.get("id")
        req_id = n.get("requisition_id")

        if nid or req_id:
            btns = QHBoxLayout()
            btns.setSpacing(6)
            btns.setContentsMargins(30, 2, 0, 0)
            btns.addStretch()

            if nid:
                btn_read = QPushButton("Marcar como lida")
                btn_read.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_read.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: transparent; color: {theme.TEXT_LABEL};"
                    f"  border: 1px solid {theme.DRAWER_BORDER}; border-radius: 5px;"
                    f"  padding: 3px 10px; font-size: 7pt;"
                    f"  font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
                    f"}}"
                    f"QPushButton:hover {{"
                    f"  color: {theme.TEXT_MEDIUM}; border-color: {theme.TEXT_LABEL};"
                    f"}}"
                )
                btn_read.clicked.connect(lambda checked=False, i=nid: self._on_mark_one(i))
                btns.addWidget(btn_read)

            if req_id:
                btn_open = QPushButton("Abrir requisição")
                btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_open.setStyleSheet(
                    f"QPushButton {{"
                    f"  background: {theme.SELECTION_BG}; color: {theme.PRIMARY};"
                    f"  border: 1px solid {theme.PRIMARY_LIGHT}; border-radius: 5px;"
                    f"  padding: 3px 10px; font-size: 7pt; font-weight: 600;"
                    f"  font-family: '{theme.FONT_PRIMARY}', '{theme.FONT_FALLBACK}', 'Segoe UI';"
                    f"}}"
                    f"QPushButton:hover {{ background: #ccdcff; }}"
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

        self.resize(DRAWER_WIDTH, ph)
        self.move(pw, 0)
        self.show()
        self.raise_()

        self._anim_open.setStartValue(QPoint(pw, 0))
        self._anim_open.setEndValue(QPoint(pw - DRAWER_WIDTH, 0))
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
