from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox, QFrame,
    QScrollArea, QLabel, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, QEasingCurve, QPropertyAnimation, QDate

from ..core import theme
from ..core.dialogs import ask_confirmation
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
PAGE_PINHEIRO_INDUSTRIA = 5
PAGE_AR = 6
PAGE_USER_CENTER = 7
PAGE_SETTINGS = 8


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = res.scale
        self._threads: list = []
        self._unread_count = 0
        self._listener: NotificationListener | None = None
        self._shown_notif_ids: set[int] = set()   # evita toast duplicado
        self._theme_transition_overlay: QLabel | None = None
        self._theme_transition_anim: QPropertyAnimation | None = None
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

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.VLine)
        self._sep.setFixedWidth(1)
        self._sep.setStyleSheet(f"background:{theme.SIDEBAR_BG}; color:{theme.SIDEBAR_BG}; border:none;")
        root.addWidget(self._sep)

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

        self._scroll_main = QScrollArea()
        self._scroll_main.setWidgetResizable(True)
        self._scroll_main.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_main.setStyleSheet(
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
        self._scroll_main.setWidget(self.stack)
        root.addWidget(self._scroll_main, 1)

        self.form_view = RequisitionForm(self.scale)
        self.history_view = HistoryView(self.scale)
        self.dashboard_view = DashboardView(self.scale)
        self.technical_panel_view = TechnicalPanelView(self.scale)
        self.order_center_view = OrderCenterView(self.scale)
        self.pinheiro_industria_view = ProductionView(
            self.scale,
            destinations=("Pinheiro Indústria",),
            title="PINHEIRO INDÚSTRIA",
            subtitle="Acompanhamento operacional das requisições enviadas para a Pinheiro Indústria.",
        )
        self.ar_view = ProductionView(
            self.scale,
            destinations=("A&R"),
            title="A&R",
            subtitle="Acompanhamento operacional das requisições enviadas para a A&R.",
        )
        self.user_center_view = UserCenterView(self.scale)
        self.settings_view = SettingsView(self.scale)

        self.stack.addWidget(self.form_view)
        self.stack.addWidget(self.history_view)
        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.technical_panel_view)
        self.stack.addWidget(self.order_center_view)
        self.stack.addWidget(self.pinheiro_industria_view)
        self.stack.addWidget(self.ar_view)
        self.stack.addWidget(self.user_center_view)
        self.stack.addWidget(self.settings_view)

        self.history_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "history")
        )
        self.order_center_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "order_center")
        )
        self.pinheiro_industria_view.open_requisition.connect(
            lambda req_id: self._open_requisition(req_id, "production")
        )
        self.ar_view.open_requisition.connect(
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

        visible_production_destinations = set(session.visible_production_destinations)

        pinheiro_btn = self.sidebar._nav_btns.get("pinheiro_industria")
        if pinheiro_btn and "Pinheiro Indústria" not in visible_production_destinations:
            pinheiro_btn.setEnabled(False)
            pinheiro_btn.setToolTip("Acesso restrito a administradores, indústria e entrega")

        ar_btn = self.sidebar._nav_btns.get("ar")
        if ar_btn and "A&R" not in visible_production_destinations:
            ar_btn.setEnabled(False)
            ar_btn.setToolTip("Acesso restrito a administradores e produção")

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
            "pinheiro_industria": PAGE_PINHEIRO_INDUSTRIA,
            "ar": PAGE_AR,
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
                "A Central de Pedidos é restrita a administradores, gerentes e vendedores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_PINHEIRO_INDUSTRIA and "Pinheiro Indústria" in set(session.visible_production_destinations):
            self.pinheiro_industria_view.refresh()
        elif page == PAGE_PINHEIRO_INDUSTRIA:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "A tela da Pinheiro Indústria é restrita a administradores, indústria e entrega.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_AR and "A&R" in set(session.visible_production_destinations):
            self.ar_view.refresh()
        elif page == PAGE_AR:
            QMessageBox.warning(
                self,
                "Acesso negado",
                "A tela da A&R é restrita a administradores e produção.",
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
                "As configurações são restritas a administradores.",
            )
            self._highlight_current_page()
            return

        if page == PAGE_SETTINGS and session.can_access_settings:
            self.settings_view.refresh_operational_settings()

        self.stack.setCurrentIndex(page)

    def _confirm_new_requisition(self) -> bool:
        if not self.form_view.has_unsaved_data():
            return True

        reply = ask_confirmation(
            self,
            "Nova requisição",
            "Deseja iniciar uma nova requisição?\n\n"
            "Os dados atuais serão perdidos se ainda não estiverem salvos.",
            yes_text="Sim",
            no_text="Não",
        )
        return reply

    def _highlight_current_page(self):
        mapping = {
            PAGE_FORM: "nova",
            PAGE_HISTORY: "historico",
            PAGE_DASHBOARD: "dashboard",
            PAGE_TECHNICAL: "tecnico",
            PAGE_ORDER_CENTER: "pedidos",
            PAGE_PINHEIRO_INDUSTRIA: "pinheiro_industria",
            PAGE_AR: "ar",
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

    def _capture_form_state(self) -> dict:
        client = self.form_view.client_search.get_selected()
        lock_message = ""
        if hasattr(self.form_view, "lock_label") and self.form_view.lock_label.isVisible():
            lock_message = self.form_view.lock_label.text()
        return {
            "req_id": self.form_view.req_id,
            "data": self.form_view.get_form_data(),
            "client": dict(client) if client else None,
            "client_text": self.form_view.client_search.input.text(),
            "canvas_json": self.form_view._canvas_json,
            "status": getattr(self.form_view.status_badge, "_status", "em_andamento"),
            "locked": not self.form_view.input_ped.isEnabled(),
            "lock_message": lock_message,
        }

    def _restore_form_state(self, state: dict) -> None:
        data = state.get("data") or {}
        client = state.get("client")
        client_text = state.get("client_text") or ""

        self.form_view.req_id = state.get("req_id")
        self.form_view.input_ped.setText((data.get("ped_number") or "").strip())
        self.form_view.input_obra.setText(data.get("obra") or "")
        self.form_view._set_phone_text(data.get("phone") or "")
        self.form_view.input_address.setText(data.get("delivery_address") or "")

        delivery = data.get("delivery_date")
        if delivery:
            qd = QDate.fromString(str(delivery)[:10], "yyyy-MM-dd")
            if qd.isValid():
                self.form_view.input_prazo.setDate(qd)

        self.form_view.chk_retirada.setChecked(bool(data.get("retirada")))
        self.form_view.chk_entrega.setChecked(bool(data.get("entrega")))
        self.form_view.item_table.set_items(data.get("items", []))
        self.form_view.input_obs.setPlainText(data.get("obs") or "")
        self.form_view._canvas_json = state.get("canvas_json") or "{}"
        self.form_view._update_canvas_preview()
        self.form_view.status_badge.set_status(state.get("status") or "em_andamento")

        search = self.form_view.client_search
        search.input.blockSignals(True)
        search.input.setText(client_text)
        search.input.blockSignals(False)
        search._selected = dict(client) if client else None

        if state.get("locked"):
            self.form_view._set_form_locked(True, state.get("lock_message") or "")
        else:
            self.form_view._set_form_locked(False)

    def _capture_settings_state(self) -> dict:
        selected_scale = next(
            (label for label, btn in self.settings_view._scale_btns.items() if btn.isChecked()),
            res.scale_label,
        )
        return {
            "url": self.settings_view.input_url.text(),
            "ods_path": self.settings_view.input_ods_path.text(),
            "products_path": self.settings_view.input_products_path.text(),
            "pending_invoice_alert_days": self.settings_view.input_pending_invoice_days.value(),
            "scale_label": selected_scale,
        }

    def _restore_settings_state(self, state: dict) -> None:
        self.settings_view.input_url.setText(state.get("url") or "")
        self.settings_view.input_ods_path.setText(state.get("ods_path") or "")
        self.settings_view.input_products_path.setText(state.get("products_path") or "")
        self.settings_view.input_pending_invoice_days.setValue(
            int(state.get("pending_invoice_alert_days") or 1)
        )
        selected_scale = state.get("scale_label")
        for label, btn in self.settings_view._scale_btns.items():
            btn.setChecked(label == selected_scale)

    def _capture_user_center_state(self) -> dict:
        return {
            "import_path": self.user_center_view.input_import_path.text(),
            "search": self.user_center_view.search_input.text(),
            "selected_user_id": self.user_center_view._selected_user_id,
            "form_status": self.user_center_view.form_status.text(),
            "code": self.user_center_view.input_code.text(),
            "name": self.user_center_view.input_name.text(),
            "contact": self.user_center_view.input_contact.text(),
            "sector": self.user_center_view.input_sector.text(),
            "role": self.user_center_view.combo_role.currentData(),
            "password": self.user_center_view.input_password.text(),
            "password_confirm": self.user_center_view.input_password_confirm.text(),
            "active": self.user_center_view.check_active.isChecked(),
            "disable_enabled": self.user_center_view.btn_disable.isEnabled(),
        }

    def _restore_user_center_state(self, state: dict) -> None:
        self.user_center_view.input_import_path.setText(state.get("import_path") or "")
        self.user_center_view.search_input.setText(state.get("search") or "")
        self.user_center_view._selected_user_id = state.get("selected_user_id")
        self.user_center_view.form_status.setText(state.get("form_status") or "Novo usuário")
        self.user_center_view.input_code.setText(state.get("code") or "")
        self.user_center_view.input_name.setText(state.get("name") or "")
        self.user_center_view.input_contact.setText(state.get("contact") or "")
        self.user_center_view.input_sector.setText(state.get("sector") or "")
        role = state.get("role")
        role_index = self.user_center_view.combo_role.findData(role)
        if role_index >= 0:
            self.user_center_view.combo_role.setCurrentIndex(role_index)
        self.user_center_view.input_password.setText(state.get("password") or "")
        self.user_center_view.input_password_confirm.setText(state.get("password_confirm") or "")
        self.user_center_view.check_active.setChecked(bool(state.get("active")))
        self.user_center_view.btn_disable.setEnabled(bool(state.get("disable_enabled")))

    def _capture_ui_state(self) -> dict:
        current_page = self.stack.currentIndex()
        state = {"current_page": current_page}
        if current_page == PAGE_FORM:
            state["form"] = self._capture_form_state()
        elif current_page == PAGE_HISTORY:
            state["history"] = {
                "status": self.history_view.combo_status.currentData() or "",
                "search": self.history_view.input_search.text(),
            }
        elif current_page == PAGE_SETTINGS:
            state["settings"] = self._capture_settings_state()
        elif current_page == PAGE_USER_CENTER:
            state["user_center"] = self._capture_user_center_state()
        return state

    def _restore_ui_state(self, state: dict) -> None:
        current_page = state.get("current_page", PAGE_FORM)
        self.stack.setCurrentIndex(current_page)
        self._highlight_current_page()
        self.sidebar.set_notification_count(self._unread_count)
        self.sidebar.refresh_user()
        self.form_view.refresh_logged_user()
        self._setup_statusbar()

        if current_page == PAGE_HISTORY:
            history_state = state.get("history") or {}
            status = history_state.get("status") or ""
            search = history_state.get("search") or ""
            combo_index = max(0, self.history_view.combo_status.findData(status))
            self.history_view.combo_status.setCurrentIndex(combo_index)
            self.history_view.input_search.setText(search)
            self.history_view.refresh()
        elif current_page == PAGE_DASHBOARD:
            self.dashboard_view.refresh()
        elif current_page == PAGE_TECHNICAL:
            self.technical_panel_view.refresh()
        elif current_page == PAGE_ORDER_CENTER:
            self.order_center_view.refresh()
        elif current_page == PAGE_PINHEIRO_INDUSTRIA:
            self.pinheiro_industria_view.refresh()
        elif current_page == PAGE_AR:
            self.ar_view.refresh()
        elif current_page == PAGE_USER_CENTER:
            self.user_center_view.refresh()
            self._restore_user_center_state(state.get("user_center") or {})
        elif current_page == PAGE_SETTINGS:
            self._restore_settings_state(state.get("settings") or {})
        elif current_page == PAGE_FORM:
            self._restore_form_state(state.get("form") or {})

    def _build_replacement_window(self) -> "MainWindow":
        state = self._capture_ui_state()
        old_central = self.takeCentralWidget()
        if old_central is not None:
            old_central.deleteLater()
        self.scale = res.scale
        self._setup_ui()
        self._restore_ui_state(state)
        return self

    def _show_frozen_overlay(self, pixmap) -> QLabel | None:
        """
        Exibe um overlay com o screenshot do estado anterior da janela.
        Não inicia nenhuma animação — o overlay fica estático até
        _start_overlay_fadeout() ser chamado.
        Retorna o QLabel criado, ou None se o pixmap for nulo.
        """
        if pixmap.isNull():
            return None

        # Cancela overlay anterior se existir
        if self._theme_transition_anim is not None:
            self._theme_transition_anim.stop()
            self._theme_transition_anim = None
        if self._theme_transition_overlay is not None:
            self._theme_transition_overlay.deleteLater()
            self._theme_transition_overlay = None

        overlay = QLabel(self)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setScaledContents(True)
        overlay.setPixmap(pixmap)
        overlay.setGeometry(self.rect())
        overlay.raise_()
        overlay.show()
        self._theme_transition_overlay = overlay
        return overlay

    def _start_overlay_fadeout(self, overlay: QLabel | None, on_complete=None):
        """
        Inicia o fade-out no overlay já visível.
        on_complete é chamado após a animação terminar (ou imediatamente se não
        houver overlay), permitindo diferir trabalho pesado para após a transição.
        """
        if overlay is None or not overlay.isVisible():
            if on_complete:
                on_complete()
            return

        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(1.0)
        overlay.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", overlay)
        anim.setDuration(380)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _cleanup():
            overlay.deleteLater()
            self._theme_transition_overlay = None
            self._theme_transition_anim = None
            if on_complete:
                on_complete()

        anim.finished.connect(_cleanup)
        self._theme_transition_anim = anim
        anim.start()

    def _apply_theme_to_all(self) -> None:
        """Re-aplica apenas os estilos inline dependentes do tema — ~50 ms."""
        from PySide6.QtWidgets import QApplication

        bg = theme.CONTENT_BG
        self.setStyleSheet(f"background:{bg};")
        self._sep.setStyleSheet(
            f"background:{theme.SIDEBAR_BG}; color:{theme.SIDEBAR_BG}; border:none;"
        )
        self.stack.setStyleSheet(f"background:{bg};")
        self._scroll_main.setStyleSheet(
            f"QScrollArea {{ background:{bg}; border:none; }}"
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
        self.sidebar.apply_theme()
        self.form_view.apply_theme()
        self.history_view.apply_theme()
        self.dashboard_view.apply_theme()
        self.technical_panel_view.apply_theme()
        self.order_center_view.apply_theme()
        self.pinheiro_industria_view.apply_theme()
        self.ar_view.apply_theme()
        self.user_center_view.apply_theme()
        self.settings_view.apply_theme()
        self._setup_statusbar()

    def _get_current_view(self):
        """Retorna a view visível no stack, ou None."""
        views = [
            self.form_view, self.history_view, self.dashboard_view,
            self.technical_panel_view, self.order_center_view,
            self.pinheiro_industria_view, self.ar_view,
            self.user_center_view, self.settings_view,
        ]
        idx = self.stack.currentIndex()
        return views[idx] if 0 <= idx < len(views) else None

    def _apply_theme_immediate(self) -> None:
        """Aplica tema apenas ao sidebar e à view atual (~30ms)."""
        bg = theme.CONTENT_BG
        self.setStyleSheet(f"background:{bg};")
        self._sep.setStyleSheet(
            f"background:{theme.SIDEBAR_BG}; color:{theme.SIDEBAR_BG}; border:none;"
        )
        self.stack.setStyleSheet(f"background:{bg};")
        self._scroll_main.setStyleSheet(
            f"QScrollArea {{ background:{bg}; border:none; }}"
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
        self.sidebar.apply_theme()
        current = self._get_current_view()
        if current is not None:
            current.apply_theme()
        self._setup_statusbar()

    def _apply_theme_remaining(self) -> None:
        """Aplica global stylesheet + views ocultas. Chamado após o fade-out."""
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(theme.global_style())
        current = self._get_current_view()
        for view in (
            self.form_view, self.history_view, self.dashboard_view,
            self.technical_panel_view, self.order_center_view,
            self.pinheiro_industria_view, self.ar_view,
            self.user_center_view, self.settings_view,
        ):
            if view is not current:
                view.apply_theme()

    def _on_theme_toggle(self, dark: bool):
        """
        Troca de tema com transição visual responsiva.

        Sequência:
        1. Screenshot da janela atual
        2. Overlay aparece imediatamente (cobre a janela)
        3. processEvents() — força a pintura do overlay ANTES do re-estilo
        4. Re-aplica estilos apenas no sidebar e na view atual (~30ms)
        5. Fade-out inicia imediatamente; views ocultas + global stylesheet
           são aplicados no cleanup do fade, sem bloquear a animação.
        """
        from PySide6.QtWidgets import QApplication

        previous_frame = self.grab()
        overlay = self._show_frozen_overlay(previous_frame)
        QApplication.processEvents()

        res.save(dark_mode=dark)
        theme.set_dark(dark)

        # Fase rápida: apenas o que o usuário vê agora
        self._apply_theme_immediate()

        # Fade-out começa imediatamente; o restante é diferido para o cleanup
        self._start_overlay_fadeout(overlay, on_complete=self._apply_theme_remaining)

    def _on_scale_changed(self, _new_scale: float):
        """Reconstrói o conteúdo da janela principal com a nova escala."""
        self._build_replacement_window()

    # ── Logout ───────────────────────────────────────────────────────────────

    def _logout(self):
        reply = ask_confirmation(
            self,
            "Sair",
            "Deseja encerrar a sessão?",
            yes_text="Sim",
            no_text="Não",
        )
        if reply:
            self._notif_timer.stop()
            if self._listener:
                self._listener.stop()
            session.logout()
            self.close()
