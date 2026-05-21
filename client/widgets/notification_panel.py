"""
Drawer lateral de notificações.

NotificationDrawer — painel que desliza da direita sobre o conteúdo principal.
_Overlay           — camada semitransparente com fade; fecha o drawer ao clicar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGraphicsDropShadowEffect
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

# ── Constantes ────────────────────────────────────────────────────────────────

DRAWER_WIDTH = 420
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
    "nova_requisicao":   "#3B82F6",
    "em_producao":       "#22C55E",
    "finalizada":        "#22C55E",
    "cancelada":         "#EF4444",
    "prod_cancelada":    "#EAB308",
    "requisicao_parada": "#EAB308",
}

_DEFAULT_ACCENT = "#3B82F6"


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
    """Fundo semitransparente com fade; fecha o drawer ao ser clicado."""

    clicked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.50);")
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
    """Painel lateral que desliza da direita, listando notificações não lidas."""

    mark_all_requested = Signal()
    open_req_requested = Signal(int)
    mark_one_requested = Signal(int)   # emite notification id
    closed             = Signal()

    def __init__(self, notifications: list, parent: QWidget):
        super().__init__(parent)
        self._notifications = notifications
        self._closing       = False
        self._setup()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _setup(self):
        parent = self.parent()

        # Overlay (cobre todo o parent)
        self._overlay = _Overlay(parent)
        self._overlay.clicked.connect(self.close_drawer)
        self._overlay.setGeometry(0, 0, parent.width(), parent.height())
        self._overlay.hide()

        # Drawer
        self.setFixedWidth(DRAWER_WIDTH)
        self.setStyleSheet("QWidget { background: #0F172A; }")

        # Sombra lateral esquerda
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(-4, 0)
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)
        self._build_list(root)
        self._build_footer(root)

        # Animações: guarda referências para reutilizar
        self._anim_open = QPropertyAnimation(self, b"pos", self)
        self._anim_open.setDuration(ANIM_MS)
        self._anim_open.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_close = QPropertyAnimation(self, b"pos", self)
        self._anim_close.setDuration(ANIM_MS)
        self._anim_close.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_close.finished.connect(self._on_closed)

        # Posição inicial fora da tela (à direita)
        self.move(parent.width(), 0)
        self.resize(DRAWER_WIDTH, parent.height())
        self.hide()

    def _build_header(self, root: QVBoxLayout):
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet(
            "background: #1E293B;"
            "border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(20, 0, 14, 0)
        hlay.setSpacing(10)

        title = QLabel("🔔  Notificações")
        title.setStyleSheet(
            "color: #F1F5F9; font-size: 12pt; font-weight: bold; background: transparent;"
        )
        hlay.addWidget(title, 1)

        if self._notifications:
            btn_all = QPushButton("Marcar todas")
            btn_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_all.setStyleSheet(
                "QPushButton { background: #3B82F6; color: #fff; border: none;"
                "  border-radius: 6px; padding: 6px 14px; font-size: 8pt; font-weight: 600; }"
                "QPushButton:hover { background: #2563EB; }"
            )
            btn_all.clicked.connect(self._on_mark_all)
            hlay.addWidget(btn_all)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 30)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #64748B;"
            "  border: none; border-radius: 15px; font-size: 14px; }"
            "QPushButton:hover { background: #334155; color: #F1F5F9; }"
        )
        btn_close.clicked.connect(self.close_drawer)
        hlay.addWidget(btn_close)

        root.addWidget(header)

    def _build_list(self, root: QVBoxLayout):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical {"
            "  width: 4px; background: transparent; margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,0.15); border-radius: 2px; min-height: 24px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.28); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
        )

        container = QWidget()
        container.setStyleSheet("background: #0F172A;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(16, 16, 16, 16)
        vlay.setSpacing(10)

        if not self._notifications:
            lbl = QLabel("Nenhuma notificação não lida  🎉")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "color: #334155; font-size: 11pt; padding: 60px 20px; background: transparent;"
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
            "background: #1E293B; color: #475569; font-size: 8pt;"
            "padding: 8px; border-top: 1px solid rgba(255,255,255,0.06);"
        )
        root.addWidget(footer)

    def _make_card(self, n: dict) -> QFrame:
        ntype  = n.get("type", "")
        accent = _ACCENT.get(ntype, _DEFAULT_ACCENT)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{"
            f"  background: #1E293B;"
            f"  border: 1px solid rgba(255,255,255,0.08);"
            f"  border-left: 4px solid {accent};"
            f"  border-radius: 10px;"
            f"}}"
            f"QLabel {{ background: transparent; }}"
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(6)

        # ── Linha superior: ícone + título + ponto não lida + timestamp ──
        top = QHBoxLayout()
        top.setSpacing(8)

        icon_lbl = QLabel(_ICONS.get(ntype, "🔔"))
        icon_lbl.setStyleSheet("font-size: 16px;")
        top.addWidget(icon_lbl)

        title_lbl = QLabel(n.get("title", ""))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 9pt; color: #F1F5F9;")
        title_lbl.setWordWrap(True)
        top.addWidget(title_lbl, 1)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent}; font-size: 8px;")
        top.addWidget(dot)

        ts = _relative_time(n.get("created_at"))
        if ts:
            ts_lbl = QLabel(ts)
            ts_lbl.setStyleSheet("color: #475569; font-size: 8pt;")
            top.addWidget(ts_lbl)

        lay.addLayout(top)

        # ── Mensagem ──
        msg = n.get("message", "")
        if msg:
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet("color: #64748B; font-size: 8pt;")
            msg_lbl.setWordWrap(True)
            lay.addWidget(msg_lbl)

        # ── Botões de ação (alinhados à direita) ──
        nid    = n.get("id")
        req_id = n.get("requisition_id")

        if nid or req_id:
            btns = QHBoxLayout()
            btns.setSpacing(6)
            btns.addStretch()

            if nid:
                btn_read = QPushButton("Marcar como lida")
                btn_read.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_read.setStyleSheet(
                    "QPushButton { background: transparent; color: #475569;"
                    "  border: 1px solid #334155; border-radius: 5px;"
                    "  padding: 3px 10px; font-size: 8pt; }"
                    "QPushButton:hover { color: #94A3B8; border-color: #475569; }"
                )
                btn_read.clicked.connect(lambda checked=False, i=nid: self._on_mark_one(i))
                btns.addWidget(btn_read)

            if req_id:
                btn_open = QPushButton("Abrir requisição")
                btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_open.setStyleSheet(
                    f"QPushButton {{ background: {accent}22; color: {accent};"
                    f"  border: 1px solid {accent}55; border-radius: 5px;"
                    f"  padding: 3px 10px; font-size: 8pt; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {accent}44; }}"
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
