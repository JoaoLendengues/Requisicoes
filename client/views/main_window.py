from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox, QFrame,
    QScrollArea,
)
from PySide6.QtCore import Qt, QTimer

from ..core import theme
from ..core.datetime_utils import local_now
from ..core.resolution import res
from ..core.session import session
from ..api import client as api
from ..widgets.sidebar import Sidebar
from ..widgets.notification_toast import ToastManager
from ..widgets.notification_panel import NotificationDrawer
from ..services.notification_listener import NotificationListener
from .requisition_form import RequisitionForm, _run_in_thread
from .history_view import HistoryView
from .dashboard_view import DashboardView
from .technical_panel_view import TechnicalPanelView
from .order_center_view import OrderCenterView
from .production_view import ProductionView
from .settings_view import SettingsView
from .user_center_view import UserCenterView


PAGE_FORM = 0
PAGE_HISTORY = 1
PAGE_DASHBOARD = 2
PAGE_TECHNICAL = 3
PAGE_ORDER_CENTER = 4
PAGE_PRODUCTION = 5
PAGE_USER_CENTER = 6
PAGE_SETTINGS = 7


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = res.scale
        self._threads: list = []
        self._unread_count = 0
        self._listener: NotificationListener | None = None
        self._shown_notif_ids: set[int] = set()   # evita toast duplicado
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
        self._refresh_session_profile()
        self._start_notification_listener()

    def _setup_ui(self):
        self.setStyleSheet(f"background:{theme.CONTENT_BG};")
        central = QWidget()
        self._central = central
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self.scale)
        self.sidebar.nav_clicked.connect(self._on_nav)
        self.sidebar.logout_clicked.connect(self._logout)
        self.sidebar.bell_clicked.connect(self._show_notification_panel)
        self.sidebar.theme_toggled.connect(self._on_theme_toggle)
        root.addWidget(self.sidebar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{theme.SIDEBAR_BG}; color:{theme.SIDEBAR_BG}; border:none;")
        root.addWidget(sep)

        # ── Área de conteúdo com scroll ───────────────────────────────────────
        # O QScrollArea garante que qualquer view seja acessível por rolagem
        # quando a janela for menor que o conteúdo (escala alta, tela pequena).
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{theme.CONTENT_BG};")
        # Tamanho mínimo escalado: abaixo disso o scroll entra em ação
        self.stack.setMinimumSize(
            max(760, int(860 * self.scale)),
            max(520, int(600 * self.scale)),
        )

        scroll_main = QScrollArea()
        scroll_main.setWidgetResizable(True)
        scroll_main.setFrameShape(QFrame.Shape.NoFrame)
        scroll_main.setStyleSheet(
            f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}"
            f"QScrollBar:vertical {{"
            f"  width:8px; background:transparent;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background:rgba(0,0,0,0.18); border-radius:4px; min-height:32px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background:rgba(0,0,0,0.32); }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
            f"QScrollBar:horizontal {{"
            f"  height:8px; background:transparent;"
            f"}}"
            f"QScrollBar::handle:horizontal {{"
            f"  background:rgba(0,0,0,0.18); border-radius:4px; min-width:32px;"
            f"}}"
            f"QScrollBar::handle:horizontal:hover {{ background:rgba(0,0,0,0.32); }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        )
        scroll_main.setWidget(self.stack)
        root.addWidget(scroll_main, 1)

        self.form_view = RequisitionForm(self.scale)
        self.history_view = HistoryView(self.scale)
        self.dashboard_view = DashboardView(self.scale)
        self.technical_panel_view = TechnicalPanelView(self.scale)
        self.order_center_view = OrderCenterView(self.scale)
        self.production_view = ProductionView(self.scale)
        self.user_center_view = UserCenterView(self.scale)
        self.settings_view = SettingsView(self.scale)

        self.stack.addWidget(self.form_view)
        self.stack.addWidget(self.history_view)
        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.technical_panel_view)
        self.stack.addWidget(self.order_center_view)
        self.stack.addWidget(self.production_view)
        self.stack.addWidget(self.user_center_view)
        self.stack.addWidget(self.settings_view)

        self.history_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "history")
        )
        self.order_center_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "order_center")
        )
        self.production_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "production")
        )
        self.form_view.save_requested.connect(self._save_requisition)
        self.settings_view.scale_changed.connect(self._on_scale_changed)

        if not session.can_access_dashboard:
            dash_btn = self.sidebar._nav_btns.get("dashboard")
            if dash_btn:
                dash_btn.setEnabled(False)
                dash_btn.setToolTip("Acesso restrito a gerentes e administradores")

        if not session.can_access_technical_panel:
            technical_btn = self.sidebar._nav_btns.get("tecnico")
            if technical_btn:
                technical_btn.setEnabled(False)
                technical_btn.setToolTip("Acesso restrito a administradores")

        if not session.can_access_order_center:
            orders_btn = self.sidebar._nav_btns.get("pedidos")
            if orders_btn:
                orders_btn.setEnabled(False)
                orders_btn.setToolTip("Acesso restrito a administradores, gerentes e vendedores")

        if not session.can_access_production:
            production_btn = self.sidebar._nav_btns.get("producao")
            if production_btn:
                production_btn.setEnabled(False)
                production_btn.setToolTip("Acesso restrito a administradores, produção e indústria")

        if not session.can_manage_users:
            users_btn = self.sidebar._nav_btns.get("usuarios")
            if users_btn:
                users_btn.setEnabled(False)
                users_btn.setToolTip("Acesso restrito a administradores")

        if not session.can_access_settings:
            settings_btn = self.sidebar._nav_btns.get("config")
            if settings_btn:
                settings_btn.setEnabled(False)
                settings_btn.setToolTip("Acesso restrito a administradores")

    def _setup_statusbar(self):
        bar = self.statusBar()
        bar.setStyleSheet(
            f"background:{theme.FOOTER_BG}; color:{theme.TEXT_WHITE};"
            f"font-size:{max(8, int(9 * self.scale))}pt; padding:0 12px;"
        )
        bar.showMessage(
            f"pinheiroferragens.com.br  |  SIA e Taguatinga  |  "
            f"Sistema de Requisições Pinheiro Ferragens  |  "
            f"Usuário: {session.user_name}  |  "
            f"{local_now().strftime('%d/%m/%Y  %H:%M')}"
        )

    def _refresh_session_profile(self):
        thread, worker = _run_in_thread(
            api.get_me,
            on_result=self._apply_session_profile,
            on_error=lambda _msg: None,
        )
        self._threads.append((thread, worker))

    def _apply_session_profile(self, data: dict):
        session.update_profile(data)
        self.sidebar.refresh_user()
        self.form_view.refresh_logged_user()
        self._setup_statusbar()

    def _on_nav(self, key: str):
        mapping = {
            "nova": PAGE_FORM,
            "historico": PAGE_HISTORY,
            "dashboard": PAGE_DASHBOARD,
            "tecnico": PAGE_TECHNICAL,
            "pedidos": PAGE_ORDER_CENTER,
            "producao": PAGE_PRODUCTION,
            "usuarios": PAGE_USER_CENTER,
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

        if page == PAGE_DASHBOARD and session.can_access_dashboard:
            self.dashboard_view.refresh()
        elif page == PAGE_DASHBOARD:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "O Painel Gerencial é restrito a gerentes e administradores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_TECHNICAL and session.can_access_technical_panel:
            self.technical_panel_view.refresh()
        elif page == PAGE_TECHNICAL:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "O Painel Técnico é restrito a administradores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_ORDER_CENTER and session.can_access_order_center:
            self.order_center_view.refresh()
        elif page == PAGE_ORDER_CENTER:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "A Central de Pedidos e restrita a administradores, gerentes e vendedores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_PRODUCTION and session.can_access_production:
            self.production_view.refresh()
        elif page == PAGE_PRODUCTION:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "A tela de Produção é restrita a administradores, produção e indústria.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_USER_CENTER and session.can_manage_users:
            self.user_center_view.refresh()
        elif page == PAGE_USER_CENTER:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "A Central de Usuários é restrita a administradores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_SETTINGS and not session.can_access_settings:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "As configuracoes sao restritas a administradores.",
            )
            self._highlight_current_page()
            return

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
            PAGE_TECHNICAL: "tecnico",
            PAGE_ORDER_CENTER: "pedidos",
            PAGE_PRODUCTION: "producao",
            PAGE_USER_CENTER: "usuarios",
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

    def _open_requisition(self, req_id: int, source: str = "history"):
        thread, worker = _run_in_thread(
            api.get_requisition,
            req_id,
            on_result=lambda data, current_source=source: self._load_req_into_form(data, current_source),
            on_error=lambda msg: QMessageBox.critical(self, "Erro", msg),
        )
        self._threads.append((thread, worker))

    def _load_req_into_form(self, data: dict, source: str = "history"):
        self.form_view.load_requisition(
            data,
            read_only=session.should_open_requisition_read_only(source),
        )
        self.stack.setCurrentIndex(PAGE_FORM)
        self.sidebar._highlight("nova")

    # ── Notificações ─────────────────────────────────────────────────────────

    def _start_notification_listener(self):
        """
        Inicia o listener SSE e o poll de segurança do badge.

        Fluxo de entrega garantida:
        1. Ao conectar ao SSE, o servidor envia todas as não lidas do banco
        2. _on_notification exibe toast + atualiza badge para cada evento
        3. _shown_notif_ids evita toast duplicado (SSE inicial vs push)
        4. Poll de 60s sincroniza o badge caso o SSE esteja indisponível
        """
        self._listener = NotificationListener(self)
        self._listener.notification_received.connect(self._on_notification)
        self._listener.start()

        # Poll de segurança a cada 60s para manter o badge correto
        self._notif_timer = QTimer(self)
        self._notif_timer.setInterval(60_000)
        self._notif_timer.timeout.connect(self._sync_badge)
        self._notif_timer.start()

    def _on_notification(self, data: dict):
        """
        Processa cada evento SSE recebido.

        Inclui tanto eventos iniciais (não lidas do banco ao conectar)
        quanto pushes em tempo real. _shown_notif_ids garante que o
        toast apareça exatamente uma vez por notificação.
        """
        nid = data.get("id")
        if nid:
            if nid in self._shown_notif_ids:
                return          # já exibido — ignora
            self._shown_notif_ids.add(nid)

        self._unread_count += 1
        self.sidebar.set_notification_count(self._unread_count)
        self._toast_manager.show(data, on_action=self._on_toast_action)

    def _on_toast_action(self, req_id):
        """Abre a requisição ao clicar no toast."""
        if req_id:
            self._open_requisition(req_id)

    def _sync_badge(self):
        """Poll de segurança: sincroniza badge com a contagem real do banco."""
        thread, worker = _run_in_thread(
            api.notification_unread_count,
            on_result=lambda r: self._update_badge(r.get("count", 0)),
            on_error=lambda _: None,
        )
        self._threads.append((thread, worker))

    def _update_badge(self, count: int):
        self._unread_count = count
        self.sidebar.set_notification_count(count)

    def _show_notification_panel(self):
        thread, worker = _run_in_thread(
            api.list_notifications,
            on_result=self._open_notification_drawer,
            on_error=lambda msg: QMessageBox.warning(self, "Erro", msg),
        )
        self._threads.append((thread, worker))

    def _open_notification_drawer(self, notifications: list):
        drawer = NotificationDrawer(notifications, self._central)
        drawer.mark_all_requested.connect(self._mark_all_read)
        drawer.open_req_requested.connect(self._open_requisition)
        drawer.mark_one_requested.connect(self._mark_one_read)
        drawer.open_drawer()

    def _mark_all_read(self):
        thread, worker = _run_in_thread(
            api.mark_all_notifications_read,
            on_result=lambda _: self._reset_badge(),
            on_error=lambda _: None,
        )
        self._threads.append((thread, worker))

    def _mark_one_read(self, notif_id: int):
        thread, worker = _run_in_thread(
            api.mark_one_notification_read,
            notif_id,
            on_result=lambda _: self._sync_badge(),
            on_error=lambda _: None,
        )
        self._threads.append((thread, worker))

    def _reset_badge(self):
        self._unread_count = 0
        self._shown_notif_ids.clear()
        self.sidebar.set_notification_count(0)

    # ── Escala ───────────────────────────────────────────────────────────────

    def _on_theme_toggle(self, dark: bool):
        """Salva preferência, aplica tema e reconstrói a janela."""
        from PySide6.QtWidgets import QApplication
        res.save(dark_mode=dark)
        theme.set_dark(dark)
        QApplication.instance().setStyleSheet(theme.global_style())
        self._notif_timer.stop()
        if self._listener:
            self._listener.stop()
        new_win = MainWindow()
        new_win.show()
        self.close()

    def _on_scale_changed(self, _new_scale: float):
        """Reconstrói a janela principal com a nova escala sem reiniciar o processo.

        A sessão do usuário é mantida (singleton). Uma nova MainWindow é criada
        já lendo res.scale atualizado, e a janela atual é fechada em seguida.
        """
        self._notif_timer.stop()
        if self._listener:
            self._listener.stop()
        new_win = MainWindow()
        new_win.show()
        self.close()

    # ── Logout ───────────────────────────────────────────────────────────────

    def _logout(self):
        reply = QMessageBox.question(
            self,
            "Sair",
            "Deseja encerrar a sessão?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._notif_timer.stop()
            if self._listener:
                self._listener.stop()
            session.logout()
            self.close()
