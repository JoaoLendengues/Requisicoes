from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox, QFrame,
    QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea,
)
from PySide6.QtCore import Qt, Signal

from ..core import theme
from ..core.resolution import res
from ..core.session import session
from ..api import client as api
from ..widgets.sidebar import Sidebar
from ..widgets.notification_toast import ToastManager
from ..services.notification_listener import NotificationListener
from .requisition_form import RequisitionForm, _run_in_thread
from .history_view import HistoryView
from .dashboard_view import DashboardView
from .production_view import ProductionView
from .settings_view import SettingsView


PAGE_FORM = 0
PAGE_HISTORY = 1
PAGE_DASHBOARD = 2
PAGE_PRODUCTION = 3
PAGE_SETTINGS = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = res.scale
        self._threads: list = []
        self._unread_count = 0
        self._listener: NotificationListener | None = None
        self._setup_ui()
        self._setup_statusbar()
        self.setWindowTitle("Sistema de Requisições - Ferragens Pinheiro")
        if res.start_maximized:
            self.showMaximized()
        else:
            width = max(1024, int(1280 * self.scale))
            height = max(700, int(800 * self.scale))
            self.resize(width, height)
        self._toast_manager = ToastManager(self)
        self._start_notification_listener()

    def _setup_ui(self):
        self.setStyleSheet(f"background:{theme.CONTENT_BG};")
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self.scale)
        self.sidebar.nav_clicked.connect(self._on_nav)
        self.sidebar.logout_clicked.connect(self._logout)
        self.sidebar.bell_clicked.connect(self._show_notification_panel)
        root.addWidget(self.sidebar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{theme.BORDER_COLOR};")
        root.addWidget(sep)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{theme.CONTENT_BG};")
        root.addWidget(self.stack, 1)

        self.form_view = RequisitionForm(self.scale)
        self.history_view = HistoryView(self.scale)
        self.dashboard_view = DashboardView(self.scale)
        self.production_view = ProductionView(self.scale)
        self.settings_view = SettingsView(self.scale)

        self.stack.addWidget(self.form_view)
        self.stack.addWidget(self.history_view)
        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.production_view)
        self.stack.addWidget(self.settings_view)

        self.history_view.open_requisition.connect(self._open_requisition)
        self.production_view.open_requisition.connect(self._open_requisition)
        self.form_view.save_requested.connect(self._save_requisition)

        if not session.is_manager_or_admin:
            dash_btn = self.sidebar._nav_btns.get("dashboard")
            if dash_btn:
                dash_btn.setEnabled(False)
                dash_btn.setToolTip("Acesso restrito a gerentes")

    def _setup_statusbar(self):
        bar = self.statusBar()
        bar.setStyleSheet(
            f"background:{theme.SIDEBAR_BG}; color:{theme.TEXT_LIGHT};"
            f"font-size:{max(8, int(9 * self.scale))}pt; padding:0 12px;"
        )
        bar.showMessage(
            f"pinheiroferragens.com.br  |  SIA e Taguatinga  |  "
            f"Sistema de Requisições Pinheiro Ferragens  |  "
            f"Usuário: {session.user_name}  |  "
            f"{datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

    def _on_nav(self, key: str):
        mapping = {
            "nova": PAGE_FORM,
            "historico": PAGE_HISTORY,
            "dashboard": PAGE_DASHBOARD,
            "producao": PAGE_PRODUCTION,
            "config": PAGE_SETTINGS,
        }
        page = mapping.get(key, PAGE_FORM)

        if key == "nova":
            if not self._confirm_new_requisition():
                self.stack.setCurrentIndex(PAGE_FORM)
                self.sidebar._highlight("nova")
                return
            self.form_view.reset()

        if page == PAGE_HISTORY:
            self.history_view.refresh()

        if page == PAGE_DASHBOARD and session.is_manager_or_admin:
            self.dashboard_view.refresh()
        elif page == PAGE_DASHBOARD:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "O Dashboard é restrito a gerentes e administradores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_PRODUCTION:
            self.production_view.refresh()

        self.stack.setCurrentIndex(page)

    def _confirm_new_requisition(self) -> bool:
        if not self.form_view.has_unsaved_data():
            return True

        reply = QMessageBox.question(
            self,
            "Nova requisição",
            "Deseja iniciar uma nova requisição?\n\n"
            "Os dados atuais serão perdidos se ainda não estiverem salvos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _highlight_current_page(self):
        mapping = {
            PAGE_FORM: "nova",
            PAGE_HISTORY: "historico",
            PAGE_DASHBOARD: "dashboard",
            PAGE_PRODUCTION: "producao",
            PAGE_SETTINGS: "config",
        }
        self.sidebar._highlight(mapping.get(self.stack.currentIndex(), "nova"))

    def _save_requisition(self):
        if self.stack.currentIndex() != PAGE_FORM:
            return

        data = self.form_view.get_form_data()
        ped_number = (data.get("ped_number") or "").strip()

        if not ped_number or not ped_number.isdigit() or int(ped_number) == 0:
            QMessageBox.warning(
                self,
                "Atenção",
                "Informe um número de PED válido antes de salvar.",
            )
            return

        if not data.get("client_id"):
            QMessageBox.warning(
                self,
                "Atenção",
                "Selecione um cliente antes de salvar.",
            )
            return

        canvas_json = self.form_view._canvas_json
        client = self.form_view.client_search.get_selected()
        obs = self.form_view.input_obs.toPlainText().strip()

        if self.form_view.req_id:
            req_id = self.form_view.req_id
            thread, worker = _run_in_thread(
                api.update_requisition,
                req_id,
                data,
                on_result=lambda req: self._after_save(req, canvas_json, client, obs),
                on_error=self._on_save_error,
            )
        else:
            thread, worker = _run_in_thread(
                api.create_requisition,
                data,
                on_result=lambda req: self._after_save(req, canvas_json, client, obs),
                on_error=self._on_save_error,
            )
        self._threads.append((thread, worker))

    def _after_save(self, req: dict, canvas_json: str,
                    client: dict | None = None, obs: str = ""):
        req_id = req["id"]
        self.form_view.req_id = req_id
        thread, worker = _run_in_thread(
            api.update_canvas,
            req_id,
            canvas_json,
            on_result=lambda _: self._on_fully_saved(req, canvas_json, client, obs),
            on_error=lambda _: self._on_fully_saved(req, canvas_json, client, obs),
        )
        self._threads.append((thread, worker))

    def _on_fully_saved(self, req: dict, canvas_json: str,
                        client: dict | None, obs: str):
        pdf_path = self._generate_pdf_sync(req, client, obs, canvas_json)
        self._show_saved(pdf_path)

    def _generate_pdf_sync(self, req: dict, client: dict | None,
                           obs: str, canvas_json: str = "{}") -> str:
        try:
            from ..services.pdf_generator import generate_pdf, HAS_REPORTLAB
        except ImportError:
            return ""
        if not HAS_REPORTLAB:
            return ""

        from ..core.resolution import res as _res

        folder = _res.pdf_folder.strip()
        if not folder:
            return ""

        try:
            return generate_pdf(req, client, obs, folder, canvas_json)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Aviso",
                f"Requisição salva, mas o PDF não pôde ser gerado:\n{exc}",
            )
            return ""

    def _show_saved(self, pdf_path: str = ""):
        message = "Requisição salva com sucesso!"
        if pdf_path:
            message += f"\n\nPDF gerado em:\n{pdf_path}"
        QMessageBox.information(self, "Requisição salva", message)

    def _on_save_error(self, msg: str):
        QMessageBox.critical(self, "Erro ao salvar", msg)

    def _open_requisition(self, req_id: int):
        thread, worker = _run_in_thread(
            api.get_requisition,
            req_id,
            on_result=self._load_req_into_form,
            on_error=lambda msg: QMessageBox.critical(self, "Erro", msg),
        )
        self._threads.append((thread, worker))

    def _load_req_into_form(self, data: dict):
        self.form_view.load_requisition(data)
        self.stack.setCurrentIndex(PAGE_FORM)
        self.sidebar._highlight("nova")

    # ── Notificações ─────────────────────────────────────────────────────────

    def _start_notification_listener(self):
        self._listener = NotificationListener(self)
        self._listener.notification_received.connect(self._on_notification)
        self._listener.start()

        # Carrega contagem inicial de não lidas
        thread, worker = _run_in_thread(
            api.notification_unread_count,
            on_result=lambda r: self.sidebar.set_notification_count(r.get("count", 0)),
            on_error=lambda _: None,
        )
        self._threads.append((thread, worker))

    def _on_notification(self, data: dict):
        # Incrementa badge
        self._unread_count += 1
        self.sidebar.set_notification_count(self._unread_count)

        # Exibe toast
        self._toast_manager.show(data, on_action=self._on_toast_action)

    def _on_toast_action(self, req_id):
        """Abre a requisição clicada no toast."""
        if req_id:
            self._open_requisition(req_id)

    def _show_notification_panel(self):
        thread, worker = _run_in_thread(
            api.list_notifications,
            on_result=self._open_notification_dialog,
            on_error=lambda msg: QMessageBox.warning(self, "Erro", msg),
        )
        self._threads.append((thread, worker))

    def _open_notification_dialog(self, notifications: list):
        dlg = _NotificationPanel(notifications, self)
        dlg.mark_all_requested.connect(self._mark_all_read)
        dlg.open_req_requested.connect(self._open_requisition)
        dlg.exec()

    def _mark_all_read(self):
        thread, worker = _run_in_thread(
            api.mark_all_notifications_read,
            on_result=lambda _: self._reset_badge(),
            on_error=lambda _: None,
        )
        self._threads.append((thread, worker))

    def _reset_badge(self):
        self._unread_count = 0
        self.sidebar.set_notification_count(0)

    # ── Logout ───────────────────────────────────────────────────────────────

    def _logout(self):
        reply = QMessageBox.question(
            self,
            "Sair",
            "Deseja encerrar a sessão?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._listener:
                self._listener.stop()
            session.logout()
            self.close()


# ── Painel de notificações ────────────────────────────────────────────────────

_ICONS = {
    "nova_requisicao":   "🏭",
    "em_producao":       "⚙️",
    "finalizada":        "✅",
    "cancelada":         "❌",
    "prod_cancelada":    "⚠️",
    "requisicao_parada": "⏰",
}


class _NotificationPanel(QDialog):
    mark_all_requested = Signal()
    open_req_requested = Signal(int)

    def __init__(self, notifications: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notificações")
        self.setMinimumWidth(460)
        self.setMaximumHeight(560)
        self.setStyleSheet(
            f"QDialog {{ background: {theme.CONTENT_BG}; }}"
            f"QLabel {{ color: {theme.TEXT_DARK}; }}"
        )
        self._build(notifications)

    def _build(self, notifications: list):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # cabeçalho
        header = QWidget()
        header.setStyleSheet(f"background: {theme.SIDEBAR_BG};")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 12, 16, 12)

        title = QLabel("🔔  Notificações")
        title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #F1F5F9;")
        hlay.addWidget(title, 1)

        if notifications:
            btn_all = QPushButton("Marcar todas como lidas")
            btn_all.setStyleSheet(
                f"QPushButton {{ background: {theme.PRIMARY}; color: #fff; border: none;"
                f"  border-radius: 5px; padding: 5px 12px; font-size: 9pt; }}"
                f"QPushButton:hover {{ background: {theme.PRIMARY_HOVER}; }}"
            )
            btn_all.clicked.connect(self._on_mark_all)
            hlay.addWidget(btn_all)

        root.addWidget(header)

        # lista
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        container.setStyleSheet(f"background: {theme.CONTENT_BG};")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(12, 8, 12, 8)
        vlay.setSpacing(6)

        if not notifications:
            empty = QLabel("Nenhuma notificação não lida 🎉")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {theme.TEXT_LIGHT}; font-size: 10pt; padding: 40px;")
            vlay.addWidget(empty)
        else:
            for n in notifications:
                vlay.addWidget(self._make_card(n))

        vlay.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def _make_card(self, n: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {theme.CARD_BG}; border: 1px solid {theme.BORDER_COLOR};"
            f"  border-radius: 8px; }}"
            f"QLabel {{ background: transparent; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        icon = QLabel(_ICONS.get(n.get("type", ""), "🔔"))
        icon.setStyleSheet("font-size: 16px;")
        lay.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(2)

        title = QLabel(n.get("title", ""))
        title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #F1F5F9;")
        text.addWidget(title)

        msg = QLabel(n.get("message", ""))
        msg.setStyleSheet(f"font-size: 8pt; color: {theme.TEXT_LIGHT};")
        msg.setWordWrap(True)
        text.addWidget(msg)

        lay.addLayout(text, 1)

        req_id = n.get("requisition_id")
        if req_id:
            btn = QPushButton("Abrir")
            btn.setFixedWidth(60)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {theme.PRIMARY};"
                f"  border: 1px solid {theme.PRIMARY}; border-radius: 4px;"
                f"  padding: 4px 8px; font-size: 8pt; }}"
                f"QPushButton:hover {{ background: #1e3a5f; }}"
            )
            btn.clicked.connect(lambda checked=False, rid=req_id: self._on_open(rid))
            lay.addWidget(btn)

        return card

    def _on_mark_all(self):
        self.mark_all_requested.emit()
        self.accept()

    def _on_open(self, req_id: int):
        self.open_req_requested.emit(req_id)
        self.accept()
