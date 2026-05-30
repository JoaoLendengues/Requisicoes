"""Painel técnico com indicadores de disponibilidade e diagnóstico rápido."""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..api import client as api
from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea
from ..core.datetime_utils import (
    format_datetime as _format_datetime,
    format_header_date as _format_header_date,
    local_now,
    parse_datetime as _parse_datetime,
)
from ..core.session import session
from .dashboard_view import (
    _flat_secondary_btn_style,
    _make_shadow_card,
    _rgba,
)


def _format_storage(bytes_value: object) -> str:
    try:
        total = int(bytes_value or 0)
    except (TypeError, ValueError):
        return "-"

    if total <= 0:
        return "-"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(total)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024.0
    if unit in {"GB", "TB"}:
        return f"{size:.1f} {unit}"
    return f"{int(size)} {unit}"


class TechnicalWorker(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def run(self):
        try:
            self.result.emit(api.get_technical_panel_summary())
        except api.APIError as exc:
            self.error.emit(exc.detail)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class TechnicalPanelView(QWidget):
    guide_requested = Signal()

    def __init__(self, scale: float = 1.0, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.scale = scale
        # ``embedded`` = exibido dentro de outra tela (ex.: aba Sistema das
        # Configurações). Nesse modo dispensamos a moldura própria (scroll e
        # fundo de tela cheia) para integrar ao container hospedeiro.
        self._embedded = embedded
        self._page_scroll = None
        self._threads: list[tuple[QThread, QObject]] = []
        self._metric_labels: dict[str, QLabel] = {}
        self._metric_details: dict[str, QLabel] = {}
        self._setup_ui()
        if session.can_access_technical_panel:
            self.refresh()

    def _setup_ui(self):
        s = self.scale
        embedded = self._embedded
        self.setObjectName("technicalPanelView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _view_bg = "transparent" if embedded else theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#technicalPanelView {{ background:{_view_bg}; }}")

        root = QVBoxLayout(self)
        if embedded:
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                    max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))

        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Painel Técnico")
        title.setStyleSheet(
            f"font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Monitoramento rápido da aplicação, do banco de dados e da disponibilidade operacional."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", "1")
        subtitle.setStyleSheet(
            f"font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(max(10, int(12 * s)))

        info_card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(16, int(18 * s)),
            hover_background=theme.CARD_BG,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setProperty("muted", "1")
        date_hint.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; font-weight:700; background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"font-size:{max(13, int(16 * s))}pt; font-weight:800; background:transparent;"
        )
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setProperty("muted", "1")
        self.updated_label.setStyleSheet(
            f"font-size:{max(7, int(8 * s))}pt; background:transparent;"
        )
        info_layout.addWidget(date_hint)
        info_layout.addWidget(self.date_label)
        info_layout.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("ATUALIZAR")
        self.refresh_btn.setFixedHeight(max(38, int(44 * s)))
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        self.refresh_btn.clicked.connect(self.refresh)
        header_right.addWidget(info_card)
        header_right.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignTop)

        # Botão ? — abre o guia rápido desta tela.
        # No modo embarcado (aba Sistema das Configurações) o guia já é provido
        # pela própria tela de Configurações, então não duplicamos o botão.
        sz_g = max(24, int(28 * s))
        self.btn_guide = QPushButton("?")
        self.btn_guide.setToolTip("Abrir guia rápido")
        self.btn_guide.setFixedSize(sz_g, sz_g)
        self.btn_guide.setStyleSheet(
            f"font-size:{max(10, int(11 * s))}pt; font-weight:700;"
            f"color:{theme.TEXT_MEDIUM}; background:transparent;"
            f"border:1px solid {theme.BORDER_COLOR};"
            f"border-radius:{sz_g // 2}px; padding:0;"
        )
        self.btn_guide.clicked.connect(self.guide_requested)
        if not embedded:
            header_right.addWidget(self.btn_guide, 0, Qt.AlignmentFlag.AlignTop)
        else:
            self.btn_guide.hide()

        header.addLayout(header_right)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        root.addWidget(self.error_label)

        self._page_content = QWidget()
        self._page_content.setObjectName("technicalPanelContent")
        self._page_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _content_bg = "transparent" if embedded else theme.CONTENT_BG
        self._page_content.setStyleSheet(
            f"QWidget#technicalPanelContent {{ background:{_content_bg}; }}"
        )

        if embedded:
            # Sem scroll próprio: o container hospedeiro (aba Sistema) já rola.
            root.addWidget(self._page_content)
        else:
            self._page_scroll = SmoothScrollArea()
            self._page_scroll.setWidgetResizable(True)
            self._page_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{theme.CONTENT_BG}; }}")
            self._page_scroll.viewport().setStyleSheet(f"background:{theme.CONTENT_BG}; border:none;")
            root.addWidget(self._page_scroll, 1)
            self._page_scroll.setWidget(self._page_content)

        layout = QVBoxLayout(self._page_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(12, int(16 * s)))

        # Definição de cada métrica: cor de destaque, título e texto de apoio.
        defs = {
            "system_online":         (theme.SUCCESS,       "Sistema Online/Offline",    "Status atual de disponibilidade da aplicação."),
            "database_connected":    (theme.SUCCESS,       "Banco de dados conectado?", "Verificação instantânea de acesso ao banco."),
            "last_backup_at":        (theme.WARNING,       "Último backup",             "Horário mais recente de backup localizado no ambiente."),
            "requisitions_today":    (theme.PRIMARY_HOVER, "Requisições hoje",          "Requisições registradas no dia atual."),
            "error_count_today":     (theme.DANGER,        "Quantidade de erros hoje",  "Total de respostas com erro registradas hoje."),
            "average_response_ms":   (theme.BORDER_COLOR,  "Tempo médio de resposta",   "Média das respostas HTTP processadas hoje."),
            "available_space_bytes": (theme.PRIMARY,       "Espaço disponível",         "Espaço livre no armazenamento principal da aplicação."),
        }

        def _card(key: str) -> QFrame:
            color, title_text, helper_text = defs[key]
            return self._build_metric_card(color, title_text, helper_text, key)

        def _grid(keys: list[str], columns: int) -> QGridLayout:
            g = QGridLayout()
            g.setHorizontalSpacing(max(12, int(16 * s)))
            g.setVerticalSpacing(max(12, int(16 * s)))
            for column in range(columns):
                g.setColumnStretch(column, 1)
            for i, key in enumerate(keys):
                g.addWidget(_card(key), i // columns, i % columns)
            return g

        # Seções rotuladas (mesmo padrão visual das seções da aba Configurações).
        self._section_widgets = []

        # ── Disponibilidade ──────────────────────────────────────────────────
        layout.addWidget(self._add_section_label("Disponibilidade"))
        layout.addWidget(self._add_section_separator())
        layout.addLayout(_grid(["system_online", "database_connected", "last_backup_at"], 3))

        # ── Desempenho & Recursos ────────────────────────────────────────────
        layout.addSpacing(max(4, int(6 * s)))
        layout.addWidget(self._add_section_label("Desempenho & Recursos"))
        layout.addWidget(self._add_section_separator())
        layout.addLayout(_grid(
            ["requisitions_today", "error_count_today",
             "average_response_ms", "available_space_bytes"], 4))

        # ── Usuários ─────────────────────────────────────────────────────────
        layout.addSpacing(max(4, int(6 * s)))
        layout.addWidget(self._add_section_label("Usuários"))
        layout.addWidget(self._add_section_separator())
        layout.addWidget(
            self._build_metric_card(
                theme.PRIMARY,
                "Usuários logados",
                "Usuários conectados no momento e horário do último login.",
                "connected_users",
                prominent=True,
            )
        )
        layout.addStretch()

    def _add_section_label(self, text: str) -> QLabel:
        s = self.scale
        lbl = QLabel(text.upper())
        lbl.setProperty("role", "tech_section")
        lbl.setStyleSheet(
            f"font-size:{max(9, int(10 * s))}pt; font-weight:800;"
            f"color:{theme.TEXT_MEDIUM}; letter-spacing:1px; background:transparent;"
        )
        self._section_widgets.append(("label", lbl))
        return lbl

    def _add_section_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{theme.BORDER_COLOR}; border:none;")
        self._section_widgets.append(("sep", sep))
        return sep

    def _build_metric_card(
        self,
        color: str,
        title: str,
        helper_text: str,
        key: str,
        prominent: bool = False,
    ) -> QFrame:
        s = self.scale
        card = _make_shadow_card(
            s,
            theme.CARD_BG,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background=theme.CARD_BG,
        )
        if prominent:
            card.setMinimumHeight(max(180, int(210 * s)))
        layout = QVBoxLayout(card)
        if prominent:
            layout.setContentsMargins(
                max(20, int(26 * s)),
                max(18, int(24 * s)),
                max(20, int(26 * s)),
                max(18, int(22 * s)),
            )
            layout.setSpacing(max(8, int(10 * s)))
        else:
            layout.setContentsMargins(
                max(16, int(20 * s)),
                max(15, int(18 * s)),
                max(16, int(20 * s)),
                max(14, int(18 * s)),
            )
            layout.setSpacing(max(6, int(8 * s)))

        value_label = QLabel("-")
        value_label.setWordWrap(True)
        value_label.setStyleSheet(
            f"font-size:{max(24, int(32 * s)) if prominent else max(18, int(24 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"font-size:{max(10, int(13 * s)) if prominent else max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "1")
        helper_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s)) if prominent else max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        detail_label = QLabel("")
        detail_label.setWordWrap(True)
        detail_label.hide()
        detail_label.setProperty("muted", "1")
        detail_label.setStyleSheet(
            f"font-size:{max(8, int(9 * s)) if prominent else max(7, int(8 * s))}pt;"
            f"background:transparent; border:none; line-height:1.35;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(6, int(8 * s)) if prominent else max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"stop:0 {_rgba(color, 235)}, stop:0.5 {_rgba(color, 155)}, stop:1 {_rgba(color, 235)});"
            f"border:none; border-radius:{max(2, int(3 * s))}px;"
        )

        layout.addWidget(value_label)
        layout.addWidget(title_label)
        layout.addWidget(helper_label)
        layout.addWidget(detail_label)
        layout.addStretch()
        layout.addWidget(accent_line)

        self._metric_labels[key] = value_label
        self._metric_details[key] = detail_label
        return card

    def refresh(self):
        self._set_loading(True)
        self.error_label.hide()

        worker = TechnicalWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result.connect(self._populate)
        worker.error.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_thread(t, w))
        thread.finished.connect(lambda: self._set_loading(False))
        thread.start()
        self._threads.append((thread, worker))

    def _cleanup_thread(self, thread: QThread, worker: QObject):
        self._threads = [pair for pair in self._threads if pair != (thread, worker)]

    def _set_loading(self, loading: bool):
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.updated_label.setText("Atualizando dados...")
            self.date_label.setText(_format_header_date())

    def _show_error(self, message: str):
        self.error_label.setText(f"Não foi possível carregar o painel técnico.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta inválida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        current = _parse_datetime(payload.get("generated_at")) or local_now()
        self.date_label.setText(_format_header_date(current))
        self.updated_label.setText(f"Atualizado em {_format_datetime(current)}")

        self._set_metric("system_online", "Online" if stats.get("system_online") else "Offline")
        self._set_metric("connected_users", str(stats.get("connected_users") or 0))
        self._set_metric("requisitions_today", str(stats.get("requisitions_today") or 0))
        self._set_metric_detail("connected_users", self._format_logged_users(payload.get("logged_users")))

        average_response = stats.get("average_response_ms")
        self._set_metric(
            "average_response_ms",
            f"{int(average_response)} ms" if average_response not in (None, "") else "-",
        )

        last_backup_at = stats.get("last_backup_at")
        self._set_metric(
            "last_backup_at",
            _format_datetime(last_backup_at) if _parse_datetime(last_backup_at) else "Não identificado",
        )
        self._set_metric("database_connected", "Sim" if stats.get("database_connected") else "Não")
        self._set_metric("available_space_bytes", _format_storage(stats.get("available_space_bytes")))
        self._set_metric("error_count_today", str(stats.get("error_count_today") or 0))

    def _set_metric(self, key: str, value: str):
        label = self._metric_labels.get(key)
        if label is not None:
            label.setText(value)

    def _set_metric_detail(self, key: str, value: str):
        label = self._metric_details.get(key)
        if label is None:
            return
        text = str(value or "").strip()
        label.setText(text)
        label.setVisible(bool(text))

    def _format_logged_users(self, rows: object) -> str:
        users = rows if isinstance(rows, list) else []
        if not users:
            return "Nenhum usuário conectado."

        lines: list[str] = []
        for row in users:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "Usuário")
            last_login = _format_datetime(row.get("last_login_at"))
            lines.append(f"{name} | último login: {last_login}")
        return "\n".join(lines)

    def apply_theme(self) -> None:
        s = self.scale
        bg = "transparent" if self._embedded else theme.CONTENT_BG
        self.setStyleSheet(f"QWidget#technicalPanelView {{ background:{bg}; }}")
        if self._page_scroll is not None:
            self._page_scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{bg}; }}")
            self._page_scroll.viewport().setStyleSheet(f"background:{bg}; border:none;")
        self._page_content.setStyleSheet(f"QWidget#technicalPanelContent {{ background:{bg}; }}")
        self.refresh_btn.setStyleSheet(_flat_secondary_btn_style(s))
        for kind, widget in getattr(self, "_section_widgets", []):
            if kind == "label":
                widget.setStyleSheet(
                    f"font-size:{max(9, int(10 * s))}pt; font-weight:800;"
                    f"color:{theme.TEXT_MEDIUM}; letter-spacing:1px; background:transparent;"
                )
            else:
                widget.setStyleSheet(f"background:{theme.BORDER_COLOR}; border:none;")
        self.error_label.setStyleSheet(
            f"background:{_rgba(theme.DANGER, 18)}; color:{theme.DANGER};"
            f"border:1px solid {_rgba(theme.DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
