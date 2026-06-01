"""Tela de Feedbacks — design moderno com métricas, chips e cards."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..core.session import session
from ..widgets.smooth_scroll import SmoothScrollArea

MAX_FEEDBACK_LEN = 1000

CATEGORY_OPTIONS = (
    ("🐛 Bug", "bug"),
    ("⚠️ Problema", "problema"),
    ("💡 Sugestão", "sugestao"),
    ("👍 Elogio", "elogio"),
)
CATEGORY_LABELS = {value: label for label, value in CATEGORY_OPTIONS}
CATEGORY_EMOJI = {
    "bug":      "🐛",
    "problema": "⚠️",
    "sugestao": "💡",
    "elogio":   "👍",
}

STATUS_OPTIONS = (
    ("Nova",        "nova"),
    ("Em análise",  "em_analise"),
    ("Resolvida",   "resolvida"),
    ("Descartada",  "descartada"),
)
STATUS_LABELS = {value: label for label, value in STATUS_OPTIONS}


def _rgba(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _status_color(status_value: str) -> str:
    return {
        "nova":       theme.PRIMARY_HOVER,
        "em_analise": theme.WARNING,
        "resolvida":  theme.SUCCESS,
        "descartada": theme.TEXT_MEDIUM,
    }.get(status_value, theme.BORDER_COLOR)


def _category_color(category_value: str) -> str:
    return {
        "bug":      theme.DANGER,
        "problema": theme.WARNING,
        "sugestao": theme.PRIMARY,
        "elogio":   theme.SUCCESS,
    }.get(category_value, theme.BORDER_COLOR)


def _fmt_datetime(value: object) -> str:
    if not value:
        return "—"
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return text


def _apply_shadow(widget: QWidget, blur: int = 24, y_offset: int = 4, alpha: int = 22) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    color = QColor(theme.TEXT_DARK)
    color.setAlpha(alpha)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)


# ── Workers HTTP ──────────────────────────────────────────────────────────────

class _ApiWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _Callback(QObject):
    result = Signal(object)
    error = Signal(str)


def _run_in_thread(fn, *args, on_result=None, on_error=None, **kwargs):
    worker = _ApiWorker(fn, *args, **kwargs)
    thread = QThread()
    cb = _Callback()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.result.connect(cb.result)
    worker.error.connect(cb.error)
    worker.finished.connect(thread.quit)
    if on_result:
        cb.result.connect(on_result)
    if on_error:
        cb.error.connect(on_error)
    worker._cb = cb
    thread.start()
    return thread, worker


# ── Card de feedback (item da lista) ──────────────────────────────────────────

class _FeedbackCard(QFrame):
    """Card visual de um único feedback. Lista usada no estilo "feed"."""

    clicked = Signal(int)  # feedback_id
    react_requested = Signal(int, object)  # (feedback_id, "like"/"dislike"/None)

    def __init__(
        self,
        data: dict,
        scale: float,
        show_author: bool,
        current_user_id: int = 0,
        show_reactions: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.data = data
        self.scale = scale
        self.feedback_id = int(data.get("id") or 0)
        self.is_selected = False
        self.current_user_id = int(current_user_id or 0)
        self.show_reactions = show_reactions
        self._build_ui(show_author)

    def _build_ui(self, show_author: bool):
        s = self.scale
        cat = str(self.data.get("category") or "sugestao")
        stt = str(self.data.get("status") or "nova")
        cat_color = _category_color(cat)
        stt_color = _status_color(stt)

        self.setObjectName("feedbackCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_style(cat_color)
        _apply_shadow(self)

        root = QHBoxLayout(self)
        root.setContentsMargins(
            max(14, int(16 * s)), max(12, int(14 * s)),
            max(14, int(16 * s)), max(12, int(14 * s)),
        )
        root.setSpacing(max(10, int(12 * s)))

        # ── Emoji grande à esquerda ─────────────────────────────────────────
        emoji = QLabel(CATEGORY_EMOJI.get(cat, "💬"))
        emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji.setFixedSize(max(40, int(48 * s)), max(40, int(48 * s)))
        emoji.setStyleSheet(
            f"background:{_rgba(cat_color, 28)}; border:1px solid {_rgba(cat_color, 60)};"
            f"border-radius:{max(20, int(24 * s))}px;"
            f"font-size:{max(16, int(20 * s))}pt;"
        )
        root.addWidget(emoji, 0, Qt.AlignmentFlag.AlignTop)

        # ── Bloco central: autor + categoria + mensagem ─────────────────────
        center = QVBoxLayout()
        center.setSpacing(max(3, int(4 * s)))

        # Linha do topo: autor (se admin) + categoria + data
        top_row = QHBoxLayout()
        top_row.setSpacing(max(6, int(8 * s)))

        if show_author:
            author = QLabel(str(self.data.get("user_name") or "—"))
            author.setStyleSheet(
                f"color:{theme.TEXT_DARK}; font-weight:700;"
                f"font-size:{max(10, int(11 * s))}pt; background:transparent;"
            )
            top_row.addWidget(author)

            sep = QLabel("•")
            sep.setStyleSheet(
                f"color:{theme.TEXT_LIGHT}; background:transparent;"
                f"font-size:{max(8, int(10 * s))}pt;"
            )
            top_row.addWidget(sep)

        cat_label = QLabel(CATEGORY_LABELS.get(cat, cat).upper())
        cat_label.setStyleSheet(
            f"color:{cat_color}; font-weight:700; letter-spacing:0.5px;"
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        top_row.addWidget(cat_label)

        top_row.addStretch(1)

        date_label = QLabel(_fmt_datetime(self.data.get("created_at")))
        date_label.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; background:transparent;"
            f"font-size:{max(8, int(9 * s))}pt;"
        )
        top_row.addWidget(date_label)
        center.addLayout(top_row)

        # Mensagem
        msg = QLabel(str(self.data.get("message") or "").strip())
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color:{theme.TEXT_DARK}; background:transparent;"
            f"font-size:{max(9, int(10 * s))}pt; line-height:1.4;"
        )
        center.addWidget(msg)

        # Linha do rodapé: status pill + (resolvido por, se houver)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(max(8, int(10 * s)))

        status_pill = QLabel(STATUS_LABELS.get(stt, stt))
        status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_pill.setStyleSheet(
            f"background:{_rgba(stt_color, 35)}; color:{stt_color};"
            f"border-radius:999px; padding:3px 12px; font-weight:700;"
            f"font-size:{max(7, int(8 * s))}pt;"
        )
        bottom_row.addWidget(status_pill)

        read_by = self.data.get("read_by_name")
        if read_by:
            mark = QLabel(f"por {read_by}")
            mark.setStyleSheet(
                f"color:{theme.TEXT_LIGHT}; background:transparent;"
                f"font-size:{max(7, int(8 * s))}pt; font-style:italic;"
            )
            bottom_row.addWidget(mark)

        bottom_row.addStretch(1)

        # ── Like / Dislike ───────────────────────────────────────────────
        if self.show_reactions:
            is_own = self.current_user_id and (self.current_user_id == int(self.data.get("user_id") or 0))
            my_reaction = self.data.get("my_reaction")
            likes = int(self.data.get("likes") or 0)
            dislikes = int(self.data.get("dislikes") or 0)

            btn_like = QPushButton(f"👍  {likes}")
            btn_like.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_like.setEnabled(not is_own)
            btn_like.setStyleSheet(self._reaction_btn_style(active=(my_reaction == "like"), kind="like"))
            btn_like.clicked.connect(
                lambda _checked=False: self.react_requested.emit(
                    self.feedback_id, None if my_reaction == "like" else "like"
                )
            )

            btn_dislike = QPushButton(f"👎  {dislikes}")
            btn_dislike.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_dislike.setEnabled(not is_own)
            btn_dislike.setStyleSheet(self._reaction_btn_style(active=(my_reaction == "dislike"), kind="dislike"))
            btn_dislike.clicked.connect(
                lambda _checked=False: self.react_requested.emit(
                    self.feedback_id, None if my_reaction == "dislike" else "dislike"
                )
            )

            bottom_row.addWidget(btn_like)
            bottom_row.addWidget(btn_dislike)

        center.addLayout(bottom_row)

        root.addLayout(center, 1)

    def _reaction_btn_style(self, active: bool, kind: str) -> str:
        s = self.scale
        accent = theme.SUCCESS if kind == "like" else theme.DANGER
        if active:
            return (
                f"QPushButton {{"
                f"  background:{_rgba(accent, 35)}; color:{accent};"
                f"  border:1px solid {_rgba(accent, 80)}; border-radius:999px;"
                f"  padding:3px 12px; font-weight:700;"
                f"  font-size:{max(8, int(9 * s))}pt;"
                f"}}"
                f"QPushButton:hover {{ background:{_rgba(accent, 55)}; }}"
                f"QPushButton:disabled {{ color:{theme.TEXT_LIGHT}; background:transparent;"
                f"  border:1px dashed {theme.BORDER_COLOR}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background:transparent; color:{theme.TEXT_MEDIUM};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:999px;"
            f"  padding:3px 12px; font-weight:600;"
            f"  font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QPushButton:hover {{ background:{_rgba(accent, 20)}; color:{accent};"
            f"  border:1px solid {_rgba(accent, 60)}; }}"
            f"QPushButton:disabled {{ color:{theme.TEXT_LIGHT}; background:transparent;"
            f"  border:1px dashed {theme.BORDER_COLOR}; }}"
        )

    def _refresh_style(self, accent_color: str):
        # Selected vs idle vs hover são gerenciados por QSS via property
        self.setStyleSheet(
            f"QFrame#feedbackCard {{"
            f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"  border-left:4px solid {accent_color}; border-radius:12px;"
            f"}}"
            f"QFrame#feedbackCard[selected=\"true\"] {{"
            f"  background:{_rgba(theme.PRIMARY, 14)};"
            f"  border:1px solid {_rgba(theme.PRIMARY, 80)};"
            f"  border-left:4px solid {accent_color};"
            f"}}"
            f"QFrame#feedbackCard:hover {{"
            f"  background:{theme.SURFACE_SOFT};"
            f"}}"
        )

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.feedback_id)
        super().mousePressEvent(event)


# ── View principal ────────────────────────────────────────────────────────────

class FeedbackView(QWidget):
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, object]] = []
        self._admin_rows: list[dict] = []
        self._mine_rows: list[dict] = []
        self._public_rows: list[dict] = []
        # Filtros como chips (aplicáveis a inbox e public)
        self._active_category = ""   # "" = todas
        self._active_status = ""     # "" = todos
        # Card selecionado (admin)
        self._selected_id: int | None = None
        # Cards atuais na lista (pra atualizar seleção/refresh)
        self._cards_in_view: list[_FeedbackCard] = []
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        s = self.scale

        # Scroll-root para a tela inteira (evita corte em telas pequenas)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._page_scroll = SmoothScrollArea()
        self._page_scroll.setWidgetResizable(True)
        self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._page_scroll)

        self._page_content = QWidget()
        self._page_content.setObjectName("feedbackContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._page_scroll.setWidget(self._page_content)

        self.root_layout = QVBoxLayout(self._page_content)
        self.root_layout.setContentsMargins(
            max(18, int(22 * s)), max(18, int(22 * s)),
            max(18, int(22 * s)), max(18, int(22 * s)),
        )
        self.root_layout.setSpacing(max(14, int(16 * s)))

        # ── Cabeçalho ────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(max(3, int(4 * s)))
        self.title = QLabel("Feedbacks")
        self.subtitle = QLabel(
            "Sua opinião é o que faz o sistema melhorar. Reporte bugs, problemas, sugestões ou um elogio."
        )
        self.subtitle.setWordWrap(True)
        title_col.addWidget(self.title)
        title_col.addWidget(self.subtitle)
        header.addLayout(title_col, 1)
        self.root_layout.addLayout(header)

        # ── Métricas (admin) ─────────────────────────────────────────────────
        self.metrics_row = QHBoxLayout()
        self.metrics_row.setSpacing(max(10, int(12 * s)))
        self._metric_widgets: dict[str, tuple[QFrame, QLabel]] = {}
        for status_key, label, _value in (
            ("nova",        "Novas",        "0"),
            ("em_analise",  "Em análise",   "0"),
            ("resolvida",   "Resolvidas",   "0"),
            ("descartada",  "Descartadas",  "0"),
        ):
            card, value_lbl = self._build_metric_card(status_key, label, "0")
            self._metric_widgets[status_key] = (card, value_lbl)
            self.metrics_row.addWidget(card, 1)
        self.metrics_container = QWidget()
        self.metrics_container.setLayout(self.metrics_row)
        self.root_layout.addWidget(self.metrics_container)

        # ── Compose box (envio) — discreto ──────────────────────────────────
        self.compose_card = QFrame()
        self.compose_card.setObjectName("composeCard")
        self.compose_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _apply_shadow(self.compose_card)
        compose_lay = QVBoxLayout(self.compose_card)
        compose_lay.setContentsMargins(
            max(14, int(16 * s)), max(12, int(14 * s)),
            max(14, int(16 * s)), max(12, int(14 * s)),
        )
        compose_lay.setSpacing(max(8, int(10 * s)))

        compose_top = QHBoxLayout()
        self.compose_title = QLabel("Enviar feedback")
        compose_top.addWidget(self.compose_title)
        compose_top.addStretch(1)
        # Combo categoria à direita do título
        self.combo_category = QComboBox()
        self.combo_category.setFixedHeight(max(30, int(34 * s)))
        for label, value in CATEGORY_OPTIONS:
            self.combo_category.addItem(label, value)
        self.combo_category.setCurrentIndex(2)  # default Sugestão
        compose_top.addWidget(self.combo_category)
        compose_lay.addLayout(compose_top)

        # Checkbox de publicação
        public_row = QHBoxLayout()
        self.chk_public = QCheckBox("Tornar público (visível para todos os usuários)")
        self.chk_public.setChecked(True)
        public_row.addWidget(self.chk_public)
        public_row.addStretch(1)
        compose_lay.addLayout(public_row)

        self.input_feedback = QTextEdit()
        self.input_feedback.setPlaceholderText(
            "Descreva o que aconteceu, em qual tela, o que esperava... (até 1000 caracteres)"
        )
        self.input_feedback.textChanged.connect(self._on_text_changed)
        self.input_feedback.setMinimumHeight(max(90, int(110 * s)))
        self.input_feedback.setMaximumHeight(max(140, int(170 * s)))
        compose_lay.addWidget(self.input_feedback)

        compose_bottom = QHBoxLayout()
        self.counter = QLabel(f"0/{MAX_FEEDBACK_LEN}")
        compose_bottom.addWidget(self.counter)
        compose_bottom.addStretch(1)
        self.btn_send = QPushButton("ENVIAR")
        self.btn_send.setFixedHeight(max(34, int(38 * s)))
        self.btn_send.clicked.connect(self._send_feedback)
        compose_bottom.addWidget(self.btn_send)
        compose_lay.addLayout(compose_bottom)
        self.root_layout.addWidget(self.compose_card)

        # ── Toggle entre "Caixa de entrada" (admin) e "Meus feedbacks" ──────
        self.tab_row = QHBoxLayout()
        self.tab_row.setSpacing(max(6, int(8 * s)))
        self.btn_tab_inbox = QPushButton("Caixa de entrada")
        self.btn_tab_inbox.setCheckable(True)
        self.btn_tab_inbox.clicked.connect(lambda: self._switch_tab("inbox"))
        self.btn_tab_public = QPushButton("Públicos")
        self.btn_tab_public.setCheckable(True)
        self.btn_tab_public.clicked.connect(lambda: self._switch_tab("public"))
        self.btn_tab_mine = QPushButton("Meus feedbacks")
        self.btn_tab_mine.setCheckable(True)
        self.btn_tab_mine.clicked.connect(lambda: self._switch_tab("mine"))
        self.tab_row.addWidget(self.btn_tab_inbox)
        self.tab_row.addWidget(self.btn_tab_public)
        self.tab_row.addWidget(self.btn_tab_mine)
        self.tab_row.addStretch(1)
        # Ação à direita do toggle
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setFixedHeight(max(30, int(34 * s)))
        self.btn_refresh.clicked.connect(self.refresh)
        self.tab_row.addWidget(self.btn_refresh)
        self.root_layout.addLayout(self.tab_row)

        # ── Chips de filtro (visíveis só no inbox de admin) ─────────────────
        self.chips_container = QWidget()
        chips_lay = QHBoxLayout(self.chips_container)
        chips_lay.setContentsMargins(0, 0, 0, 0)
        chips_lay.setSpacing(max(6, int(8 * s)))

        self._chips_cat: dict[str, QPushButton] = {}
        self._chips_stt: dict[str, QPushButton] = {}

        cat_label = QLabel("CATEGORIA")
        cat_label.setProperty("muted", "1")
        cat_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
        )
        chips_lay.addWidget(cat_label)
        all_chip = self._make_chip("Todas", "", "cat")
        chips_lay.addWidget(all_chip)
        self._chips_cat[""] = all_chip
        for label, value in CATEGORY_OPTIONS:
            chip = self._make_chip(label, value, "cat")
            chips_lay.addWidget(chip)
            self._chips_cat[value] = chip

        chips_lay.addSpacing(max(10, int(14 * s)))

        st_label = QLabel("STATUS")
        st_label.setProperty("muted", "1")
        st_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
        )
        chips_lay.addWidget(st_label)
        all_st_chip = self._make_chip("Todos", "", "stt")
        chips_lay.addWidget(all_st_chip)
        self._chips_stt[""] = all_st_chip
        for label, value in STATUS_OPTIONS:
            chip = self._make_chip(label, value, "stt")
            chips_lay.addWidget(chip)
            self._chips_stt[value] = chip

        chips_lay.addStretch(1)
        self.root_layout.addWidget(self.chips_container)

        # ── Lista (cards) ────────────────────────────────────────────────────
        self.list_scroll = SmoothScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_scroll.setMinimumHeight(max(280, int(320 * s)))
        self._list_inner = QWidget()
        self.list_layout = QVBoxLayout(self._list_inner)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(max(8, int(10 * s)))
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(self._list_inner)
        self.root_layout.addWidget(self.list_scroll, 1)

        # ── Ação sobre feedback selecionado (admin only) ────────────────────
        self.action_bar = QFrame()
        self.action_bar.setObjectName("actionBar")
        self.action_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        action_lay = QHBoxLayout(self.action_bar)
        action_lay.setContentsMargins(
            max(14, int(16 * s)), max(8, int(10 * s)),
            max(14, int(16 * s)), max(8, int(10 * s)),
        )
        action_lay.setSpacing(max(8, int(10 * s)))
        action_label = QLabel("Status do feedback selecionado:")
        action_label.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-weight:600;"
            f"font-size:{max(8, int(9 * s))}pt; background:transparent;"
        )
        action_lay.addWidget(action_label)
        action_lay.addStretch(1)
        self.combo_new_status = QComboBox()
        self.combo_new_status.setFixedHeight(max(30, int(34 * s)))
        for label, value in STATUS_OPTIONS:
            self.combo_new_status.addItem(label, value)
        action_lay.addWidget(self.combo_new_status)
        self.btn_apply_status = QPushButton("APLICAR")
        self.btn_apply_status.setFixedHeight(max(30, int(34 * s)))
        self.btn_apply_status.clicked.connect(self._apply_status_change)
        action_lay.addWidget(self.btn_apply_status)
        self.root_layout.addWidget(self.action_bar)

        # Estado inicial
        self._current_tab = "inbox" if session.is_admin else "public"
        self._sync_tab_buttons()
        self._apply_role_visibility()
        self._update_chip_styles()
        self.apply_theme()
        self._update_action_bar_state()

    # ── Helpers visuais ───────────────────────────────────────────────────────
    def _build_metric_card(self, status_key: str, label: str, initial_value: str):
        s = self.scale
        color = _status_color(status_key)
        card = QFrame()
        card.setObjectName("metricCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(
            f"QFrame#metricCard {{"
            f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"  border-radius:14px;"
            f"}}"
            f"QFrame#metricCard:hover {{"
            f"  background:{theme.SURFACE_SOFT};"
            f"  border:1px solid {_rgba(color, 80)};"
            f"}}"
            f"QFrame#metricCard[selected=\"true\"] {{"
            f"  border:2px solid {color};"
            f"  background:{_rgba(color, 14)};"
            f"}}"
        )
        _apply_shadow(card, blur=18, y_offset=3, alpha=18)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(
            max(12, int(14 * s)), max(10, int(12 * s)),
            max(12, int(14 * s)), max(10, int(12 * s)),
        )
        lay.setSpacing(max(2, int(3 * s)))

        # Linha topo: emoji + label
        top = QHBoxLayout()
        top.setSpacing(max(6, int(8 * s)))
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color:{color}; font-size:{max(12, int(14 * s))}pt; background:transparent;"
        )
        top.addWidget(dot)
        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-weight:700; letter-spacing:0.5px;"
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        top.addWidget(lbl)
        top.addStretch(1)
        lay.addLayout(top)

        value_lbl = QLabel(initial_value)
        value_lbl.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-weight:800;"
            f"font-size:{max(22, int(28 * s))}pt; background:transparent;"
        )
        lay.addWidget(value_lbl)

        # Filtra pelo status ao clicar
        card.mousePressEvent = lambda _ev, k=status_key: self._toggle_metric_filter(k)
        return card, value_lbl

    def _make_chip(self, label: str, value: str, kind: str) -> QPushButton:
        s = self.scale
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setFixedHeight(max(26, int(30 * s)))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _checked=False, v=value, k=kind: self._set_filter(k, v))
        return btn

    def _chip_style(self, active: bool, accent: str | None = None) -> str:
        s = self.scale
        if active:
            color = accent or theme.PRIMARY
            return (
                f"QPushButton {{"
                f"  background:{color}; color:#FFFFFF;"
                f"  border:1px solid {color}; border-radius:999px;"
                f"  padding:3px 12px; font-weight:700;"
                f"  font-size:{max(8, int(9 * s))}pt;"
                f"}}"
                f"QPushButton:hover {{ background:{_rgba(color, 220)}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background:transparent; color:{theme.TEXT_MEDIUM};"
            f"  border:1px solid {theme.BORDER_COLOR}; border-radius:999px;"
            f"  padding:3px 12px; font-weight:600;"
            f"  font-size:{max(8, int(9 * s))}pt;"
            f"}}"
            f"QPushButton:hover {{ background:{theme.SURFACE_SOFT}; color:{theme.TEXT_DARK}; }}"
        )

    def _update_chip_styles(self):
        for value, chip in self._chips_cat.items():
            active = (value == self._active_category)
            accent = _category_color(value) if value else theme.PRIMARY
            chip.setChecked(active)
            chip.setStyleSheet(self._chip_style(active, accent))
        for value, chip in self._chips_stt.items():
            active = (value == self._active_status)
            accent = _status_color(value) if value else theme.PRIMARY
            chip.setChecked(active)
            chip.setStyleSheet(self._chip_style(active, accent))

    def _set_filter(self, kind: str, value: str):
        if kind == "cat":
            self._active_category = value
        else:
            self._active_status = value
        self._update_chip_styles()
        self._update_metric_selection()
        self._refresh_list()

    def _toggle_metric_filter(self, status_key: str):
        # Clicar num card alterna o filtro de status entre o card e "todos"
        if self._active_status == status_key:
            self._active_status = ""
        else:
            self._active_status = status_key
        self._update_chip_styles()
        self._update_metric_selection()
        self._refresh_list()

    def _update_metric_selection(self):
        for key, (card, _lbl) in self._metric_widgets.items():
            card.setProperty("selected", "true" if self._active_status == key else "false")
            card.style().unpolish(card)
            card.style().polish(card)

    def _apply_role_visibility(self):
        is_admin = session.is_admin
        self.metrics_container.setVisible(is_admin)
        self.btn_tab_inbox.setVisible(is_admin)
        # Action bar (mudar status) só faz sentido no inbox do admin
        self.action_bar.setVisible(is_admin and self._current_tab == "inbox")
        # Sem inbox para não-admin
        if not is_admin and self._current_tab == "inbox":
            self._current_tab = "public"
        # Chips: inbox (admin) e public (todos)
        self.chips_container.setVisible(self._current_tab in ("inbox", "public"))

    def _sync_tab_buttons(self):
        self.btn_tab_inbox.setChecked(self._current_tab == "inbox")
        self.btn_tab_public.setChecked(self._current_tab == "public")
        self.btn_tab_mine.setChecked(self._current_tab == "mine")

    # ── Compose / envio ───────────────────────────────────────────────────────
    def _on_text_changed(self):
        text = self.input_feedback.toPlainText()
        if len(text) > MAX_FEEDBACK_LEN:
            trimmed = text[:MAX_FEEDBACK_LEN]
            cursor = self.input_feedback.textCursor()
            pos = min(cursor.position(), MAX_FEEDBACK_LEN)
            self.input_feedback.blockSignals(True)
            self.input_feedback.setPlainText(trimmed)
            cursor.setPosition(pos)
            self.input_feedback.setTextCursor(cursor)
            self.input_feedback.blockSignals(False)
            text = trimmed
        n = len(text)
        self.counter.setText(f"{n}/{MAX_FEEDBACK_LEN}")
        # Cor: passa de amarelo a vermelho conforme se aproxima do limite
        if n >= MAX_FEEDBACK_LEN:
            color = theme.DANGER
        elif n >= MAX_FEEDBACK_LEN - 100:
            color = theme.WARNING
        else:
            color = theme.TEXT_LIGHT
        self.counter.setStyleSheet(
            f"color:{color}; background:transparent;"
            f"font-size:{max(8, int(9 * self.scale))}pt; font-weight:600;"
        )

    def _send_feedback(self):
        text = self.input_feedback.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Feedbacks", "Escreva uma mensagem antes de enviar.")
            return
        if len(text) > MAX_FEEDBACK_LEN:
            QMessageBox.warning(self, "Feedbacks", f"O limite é de {MAX_FEEDBACK_LEN} caracteres.")
            return
        category = self.combo_category.currentData() or "sugestao"
        is_public = bool(self.chk_public.isChecked())
        self.btn_send.setEnabled(False)
        thread, worker = _run_in_thread(
            api.create_feedback, text, category, is_public,
            on_result=self._on_feedback_sent,
            on_error=self._on_feedback_send_error,
        )
        self._threads.append((thread, worker))

    def _on_feedback_sent(self, _data: dict):
        self.btn_send.setEnabled(True)
        self.input_feedback.clear()
        self.counter.setText(f"0/{MAX_FEEDBACK_LEN}")
        self.chk_public.setChecked(True)
        QMessageBox.information(self, "Feedbacks", "Feedback enviado com sucesso.")
        self._load_my_feedbacks()
        self._load_public_feedbacks()
        if session.is_admin:
            self._load_admin_feedbacks()

    def _on_feedback_send_error(self, msg: str):
        self.btn_send.setEnabled(True)
        QMessageBox.critical(self, "Feedbacks", msg)

    # ── Loads ─────────────────────────────────────────────────────────────────
    def _load_my_feedbacks(self):
        thread, worker = _run_in_thread(
            api.list_my_feedbacks,
            on_result=self._on_my_feedbacks_loaded,
            on_error=lambda msg: QMessageBox.warning(self, "Feedbacks", msg),
        )
        self._threads.append((thread, worker))

    def _on_my_feedbacks_loaded(self, rows: list[dict]):
        self._mine_rows = [r for r in (rows or []) if isinstance(r, dict)]
        if self._current_tab == "mine":
            self._refresh_list()

    def _load_admin_feedbacks(self):
        if not session.is_admin:
            return
        thread, worker = _run_in_thread(
            api.list_feedbacks,
            on_result=self._on_admin_feedbacks_loaded,
            on_error=lambda msg: QMessageBox.warning(self, "Feedbacks", msg),
        )
        self._threads.append((thread, worker))

    def _load_public_feedbacks(self):
        thread, worker = _run_in_thread(
            api.list_public_feedbacks,
            on_result=self._on_public_feedbacks_loaded,
            on_error=lambda msg: QMessageBox.warning(self, "Feedbacks", msg),
        )
        self._threads.append((thread, worker))

    def _on_public_feedbacks_loaded(self, rows: list[dict]):
        self._public_rows = [r for r in (rows or []) if isinstance(r, dict)]
        if self._current_tab == "public":
            self._refresh_list()

    def _mark_public_as_read(self):
        """Marca todos os feedbacks públicos como lidos no servidor."""
        thread, worker = _run_in_thread(
            api.mark_feedbacks_read,
            on_result=lambda _r: self._notify_unread_changed(0),
            on_error=lambda _msg: None,
        )
        self._threads.append((thread, worker))

    def _notify_unread_changed(self, count: int):
        """Notifica o main_window que o contador mudou (para atualizar o badge no sidebar)."""
        parent = self.window()
        if parent is not None and hasattr(parent, "set_feedback_unread_count"):
            try:
                parent.set_feedback_unread_count(int(count))
            except Exception:
                pass

    def _on_admin_feedbacks_loaded(self, rows: list[dict]):
        self._admin_rows = [r for r in (rows or []) if isinstance(r, dict)]
        self._update_metrics()
        if self._current_tab == "inbox":
            self._refresh_list()

    def _update_metrics(self):
        counts = {"nova": 0, "em_analise": 0, "resolvida": 0, "descartada": 0}
        for row in self._admin_rows:
            stt = str(row.get("status") or "nova")
            if stt in counts:
                counts[stt] += 1
        for key, (_card, value_lbl) in self._metric_widgets.items():
            value_lbl.setText(str(counts.get(key, 0)))

    # ── Lista (cards) ─────────────────────────────────────────────────────────
    def _switch_tab(self, tab: str):
        if tab == "inbox" and not session.is_admin:
            tab = "public"
        self._current_tab = tab
        self._sync_tab_buttons()
        self.chips_container.setVisible(tab in ("inbox", "public"))
        self.action_bar.setVisible(session.is_admin and tab == "inbox")
        self._selected_id = None
        self._update_action_bar_state()
        self._refresh_list()
        # Ao abrir a aba "Públicos", marca tudo como lido e atualiza o badge
        if tab == "public":
            self._mark_public_as_read()

    def _refresh_list(self):
        # Remove cards atuais (mantém o stretch final)
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards_in_view = []

        if self._current_tab == "inbox":
            rows = self._filtered_admin_rows()
            show_author = True
        elif self._current_tab == "public":
            rows = self._filtered_public_rows()
            show_author = True
        else:
            rows = self._mine_rows
            show_author = False

        if not rows:
            empty = self._build_empty_state()
            self.list_layout.insertWidget(self.list_layout.count() - 1, empty)
            return

        current_uid = int(getattr(session, "user_id", 0) or 0)
        for row in rows:
            card = _FeedbackCard(
                row,
                self.scale,
                show_author=show_author,
                current_user_id=current_uid,
                show_reactions=True,
            )
            card.clicked.connect(self._on_card_clicked)
            card.react_requested.connect(self._on_react_requested)
            if self._selected_id and card.feedback_id == self._selected_id:
                card.set_selected(True)
            self._cards_in_view.append(card)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)

    def _filtered_admin_rows(self) -> list[dict]:
        cat = self._active_category
        stt = self._active_status
        return [
            r for r in self._admin_rows
            if (not cat or str(r.get("category") or "") == cat)
            and (not stt or str(r.get("status") or "") == stt)
        ]

    def _filtered_public_rows(self) -> list[dict]:
        cat = self._active_category
        stt = self._active_status
        return [
            r for r in self._public_rows
            if (not cat or str(r.get("category") or "") == cat)
            and (not stt or str(r.get("status") or "") == stt)
        ]

    def _on_react_requested(self, feedback_id: int, reaction: object):
        # reaction = "like" | "dislike" | None (toggle off)
        thread, worker = _run_in_thread(
            api.react_feedback, int(feedback_id), reaction,
            on_result=lambda _r: self._reload_current_tab(),
            on_error=lambda msg: QMessageBox.warning(self, "Feedbacks", msg),
        )
        self._threads.append((thread, worker))

    def _reload_current_tab(self):
        if self._current_tab == "inbox":
            self._load_admin_feedbacks()
        elif self._current_tab == "public":
            self._load_public_feedbacks()
        else:
            self._load_my_feedbacks()

    def _build_empty_state(self) -> QWidget:
        s = self.scale
        wrap = QFrame()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(20, 40, 20, 40)
        lay.setSpacing(max(8, int(10 * s)))
        icon = QLabel("💬")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"font-size:{max(32, int(42 * s))}pt; background:transparent;"
        )
        text = QLabel(
            "Nada por aqui ainda." if self._current_tab == "mine"
            else "Nenhum feedback encontrado com os filtros atuais."
        )
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(10, int(11 * s))}pt;"
            f"background:transparent;"
        )
        lay.addWidget(icon)
        lay.addWidget(text)
        return wrap

    def _on_card_clicked(self, feedback_id: int):
        self._selected_id = feedback_id
        for card in self._cards_in_view:
            card.set_selected(card.feedback_id == feedback_id)
        self._update_action_bar_state()

    def _update_action_bar_state(self):
        rows = self._filtered_admin_rows() if self._current_tab == "inbox" else []
        selected = next((r for r in rows if int(r.get("id") or 0) == (self._selected_id or 0)), None)
        ok = selected is not None
        self.combo_new_status.setEnabled(ok)
        self.btn_apply_status.setEnabled(ok)
        if ok:
            current_status = str(selected.get("status") or "nova")
            i = self.combo_new_status.findData(current_status)
            if i >= 0:
                self.combo_new_status.setCurrentIndex(i)

    def _apply_status_change(self):
        if not self._selected_id:
            return
        new_status = self.combo_new_status.currentData() or "nova"
        rows = self._filtered_admin_rows()
        selected = next((r for r in rows if int(r.get("id") or 0) == self._selected_id), None)
        if not selected:
            return
        if str(selected.get("status") or "") == new_status:
            QMessageBox.information(self, "Feedbacks", "O feedback já está nesse status.")
            return
        self.btn_apply_status.setEnabled(False)
        thread, worker = _run_in_thread(
            api.update_feedback_status, self._selected_id, new_status,
            on_result=lambda _r: self._on_status_change_done(),
            on_error=self._on_status_change_error,
        )
        self._threads.append((thread, worker))

    def _on_status_change_done(self):
        QMessageBox.information(
            self,
            "Feedbacks",
            "Status atualizado com sucesso. O autor recebeu uma notificação.",
        )
        self._load_admin_feedbacks()

    def _on_status_change_error(self, msg: str):
        QMessageBox.critical(self, "Feedbacks", msg)
        self.btn_apply_status.setEnabled(True)

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    def refresh(self):
        self._apply_role_visibility()
        self._load_my_feedbacks()
        self._load_public_feedbacks()
        if session.is_admin:
            self._load_admin_feedbacks()
        # Marca como lido se a tela aberta no momento for "Públicos"
        if self._current_tab == "public":
            self._mark_public_as_read()

    def apply_theme(self):
        s = self.scale
        bg = theme.CONTENT_BG
        self._page_content.setStyleSheet(
            f"QWidget#feedbackContent {{ background:{bg}; }}"
        )
        self._page_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{bg}; }}"
        )
        self._page_scroll.viewport().setStyleSheet(f"background:{bg};")
        self.list_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{bg}; }}"
        )
        self.list_scroll.viewport().setStyleSheet(f"background:{bg};")
        self._list_inner.setStyleSheet(f"background:{bg};")

        # Header
        self.title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(20, int(26 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.subtitle.setStyleSheet(
            f"color:{theme.TEXT_MEDIUM}; font-size:{max(9, int(11 * s))}pt;"
            f"background:transparent;"
        )

        # Compose
        self.compose_card.setStyleSheet(
            f"QFrame#composeCard {{"
            f"  background:{theme.CARD_BG}; border:1px solid {theme.BORDER_COLOR};"
            f"  border-radius:14px;"
            f"}}"
        )
        self.compose_title.setStyleSheet(
            f"color:{theme.TEXT_DARK}; font-size:{max(11, int(13 * s))}pt; font-weight:700;"
            f"background:transparent;"
        )
        self.counter.setStyleSheet(
            f"color:{theme.TEXT_LIGHT}; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
            f"background:transparent;"
        )
        self.combo_category.setStyleSheet(theme.input_style(s))
        self.input_feedback.setStyleSheet(theme.input_style(s))
        self.btn_send.setStyleSheet(theme.primary_btn_style(s))

        # Toggle tabs
        for btn, key in (
            (self.btn_tab_inbox, "inbox"),
            (self.btn_tab_public, "public"),
            (self.btn_tab_mine, "mine"),
        ):
            active = (self._current_tab == key)
            btn.setStyleSheet(self._chip_style(active, theme.PRIMARY))
            btn.setFixedHeight(max(30, int(34 * s)))

        # Checkbox público
        self.chk_public.setStyleSheet(
            f"QCheckBox {{ color:{theme.TEXT_MEDIUM};"
            f"  font-size:{max(8, int(9 * s))}pt; background:transparent;"
            f"  spacing:8px; }}"
        )

        self.btn_refresh.setStyleSheet(theme.secondary_btn_style(s))

        # Chips e métricas: já são restilizados em _update_chip_styles e nos próprios setStyleSheet.
        self._update_chip_styles()

        # Action bar
        self.action_bar.setStyleSheet(
            f"QFrame#actionBar {{"
            f"  background:{_rgba(theme.PRIMARY, 8)}; border:1px solid {_rgba(theme.PRIMARY, 28)};"
            f"  border-radius:12px;"
            f"}}"
        )
        self.combo_new_status.setStyleSheet(theme.input_style(s))
        self.btn_apply_status.setStyleSheet(theme.primary_btn_style(s))
