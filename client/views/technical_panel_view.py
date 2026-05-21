"""Painel tecnico com indicadores de disponibilidade e diagnostico rapido."""

from datetime import datetime

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
from ..core.session import session
from .dashboard_view import (
    DASH_BG,
    DASH_BORDER,
    DASH_DANGER,
    DASH_MUTED,
    DASH_PRIMARY,
    DASH_SECONDARY,
    DASH_SLATE,
    DASH_SUCCESS,
    DASH_SURFACE,
    DASH_TEXT,
    DASH_WARNING,
    _flat_secondary_btn_style,
    _format_datetime,
    _format_header_date,
    _make_shadow_card,
    _parse_datetime,
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
    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._threads: list[tuple[QThread, QObject]] = []
        self._metric_labels: dict[str, QLabel] = {}
        self._metric_details: dict[str, QLabel] = {}
        self._setup_ui()
        if session.can_access_technical_panel:
            self.refresh()

    def _setup_ui(self):
        s = self.scale
        self.setObjectName("technicalPanelView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#technicalPanelView {{ background:{DASH_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(max(18, int(24 * s)), max(18, int(24 * s)),
                                max(18, int(24 * s)), max(18, int(24 * s)))
        root.setSpacing(max(14, int(18 * s)))

        header = QHBoxLayout()
        header.setSpacing(max(12, int(16 * s)))

        title_col = QVBoxLayout()
        title_col.setSpacing(max(4, int(5 * s)))
        title = QLabel("Painel Tecnico")
        title.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(18, int(24 * s))}pt; font-weight:800;"
        )
        subtitle = QLabel(
            "Monitoramento rapido da aplicacao, do banco de dados e da disponibilidade operacional."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(10 * s))}pt;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, 1)

        header_right = QHBoxLayout()
        header_right.setSpacing(max(10, int(12 * s)))

        info_card = _make_shadow_card(
            s,
            DASH_SURFACE,
            border_color=None,
            radius=max(16, int(18 * s)),
            hover_background=DASH_SURFACE,
        )
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(max(14, int(16 * s)), max(10, int(12 * s)),
                                       max(14, int(16 * s)), max(10, int(12 * s)))
        info_layout.setSpacing(max(2, int(3 * s)))

        date_hint = QLabel("DATA ATUAL")
        date_hint.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; font-weight:700;"
            f"background:transparent;"
        )
        self.date_label = QLabel(_format_header_date())
        self.date_label.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(13, int(16 * s))}pt; font-weight:800;"
            f"background:transparent;"
        )
        self.updated_label = QLabel("Atualizando dados...")
        self.updated_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(7, int(8 * s))}pt; background:transparent;"
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
        header.addLayout(header_right)
        root.addLayout(header)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"background:{_rgba(DASH_DANGER, 18)}; color:{DASH_DANGER};"
            f"border:1px solid {_rgba(DASH_DANGER, 48)}; border-radius:16px;"
            f"padding:12px 14px; font-size:{max(8, int(9 * s))}pt; font-weight:600;"
        )
        root.addWidget(self.error_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{DASH_BG}; }}")
        scroll.viewport().setStyleSheet(f"background:{DASH_BG}; border:none;")
        root.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("technicalPanelContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet(f"QWidget#technicalPanelContent {{ background:{DASH_BG}; }}")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(16, int(18 * s)))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(max(12, int(16 * s)))
        metrics.setVerticalSpacing(max(12, int(16 * s)))
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        card_defs = [
            ("system_online", DASH_SUCCESS, "Sistema Online/Offline", "Status atual de disponibilidade da aplicacao."),
            ("requisitions_today", DASH_SECONDARY, "Requisicoes hoje", "Requisicoes registradas no dia atual."),
            ("average_response_ms", DASH_SLATE, "Tempo medio de resposta", "Media das respostas HTTP processadas hoje."),
            ("last_backup_at", DASH_WARNING, "Ultimo backup", "Horario mais recente de backup localizado no ambiente."),
            ("database_connected", DASH_SUCCESS, "Banco de dados conectado?", "Verificacao instantanea de acesso ao banco."),
            ("available_space_bytes", DASH_PRIMARY, "Espaco disponivel", "Espaco livre no armazenamento principal da aplicacao."),
            ("error_count_today", DASH_DANGER, "Quantidade de erros hoje", "Total de respostas com erro registradas hoje."),
        ]

        for index, (key, color, title_text, helper_text) in enumerate(card_defs):
            metrics.addWidget(
                self._build_metric_card(color, title_text, helper_text, key),
                index // 4,
                index % 4,
            )

        info_note = _make_shadow_card(
            s,
            DASH_SURFACE,
            border_color=DASH_BORDER,
            radius=max(18, int(20 * s)),
            hover_background=DASH_SURFACE,
        )
        info_note_layout = QVBoxLayout(info_note)
        info_note_layout.setContentsMargins(max(16, int(20 * s)), max(14, int(18 * s)),
                                            max(16, int(20 * s)), max(14, int(18 * s)))
        info_note_layout.setSpacing(max(6, int(8 * s)))

        note_title = QLabel("Leitura tecnica")
        note_title.setStyleSheet(
            f"color:{DASH_TEXT}; font-size:{max(10, int(12 * s))}pt; font-weight:800;"
        )
        note_body = QLabel(
            "Este painel mostra indicadores operacionais em tempo real. Ultimo backup pode aparecer como "
            "'Nao identificado' quando o ambiente ainda nao expoe uma rotina de backup catalogada."
        )
        note_body.setWordWrap(True)
        note_body.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(9 * s))}pt;"
        )
        info_note_layout.addWidget(note_title)
        info_note_layout.addWidget(note_body)
        layout.addWidget(info_note)
        layout.addStretch()
        layout.addWidget(
            self._build_metric_card(
                DASH_PRIMARY,
                "Usuarios logados",
                "Usuarios conectados no momento e horario do ultimo login.",
                "connected_users",
                prominent=True,
            )
        )

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
            DASH_SURFACE,
            border_color=None,
            radius=max(18, int(20 * s)),
            hover_background="#FBFDFF",
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
            f"color:{DASH_TEXT}; font-size:{max(24, int(32 * s)) if prominent else max(18, int(24 * s))}pt;"
            f"font-weight:800; background:transparent; border:none;"
        )

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color:{DASH_PRIMARY}; font-size:{max(10, int(13 * s)) if prominent else max(9, int(11 * s))}pt;"
            f"font-weight:700; background:transparent; border:none;"
        )

        helper_label = QLabel(helper_text)
        helper_label.setWordWrap(True)
        helper_label.setStyleSheet(
            f"color:{DASH_MUTED}; font-size:{max(8, int(9 * s)) if prominent else max(7, int(8 * s))}pt;"
            f"background:transparent; border:none;"
        )

        detail_label = QLabel("")
        detail_label.setWordWrap(True)
        detail_label.hide()
        detail_label.setStyleSheet(
            f"color:{DASH_SLATE}; font-size:{max(8, int(9 * s)) if prominent else max(7, int(8 * s))}pt;"
            f"background:transparent; border:none; line-height:1.35;"
        )

        accent_line = QFrame()
        accent_line.setFixedHeight(max(6, int(8 * s)) if prominent else max(4, int(5 * s)))
        accent_line.setStyleSheet(
            f"background:{color}; border:none; border-radius:{max(2, int(3 * s))}px;"
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
        self.error_label.setText(f"Nao foi possivel carregar o painel tecnico.\n\n{message}")
        self.error_label.show()

    def _populate(self, payload: object):
        if not isinstance(payload, dict):
            self._show_error("Resposta invalida do servidor.")
            return

        stats = payload.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}

        generated_at = _parse_datetime(payload.get("generated_at"))
        self.date_label.setText(_format_header_date(generated_at or datetime.now()))
        self.updated_label.setText(f"Atualizado em {_format_datetime(payload.get('generated_at'))}")

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
            _format_datetime(last_backup_at) if _parse_datetime(last_backup_at) else "Nao identificado",
        )
        self._set_metric("database_connected", "Sim" if stats.get("database_connected") else "Nao")
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
            return "Nenhum usuario conectado."

        lines: list[str] = []
        for row in users:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "Usuario")
            last_login = _format_datetime(row.get("last_login_at"))
            lines.append(f"{name} | ultimo login: {last_login}")
        return "\n".join(lines)
