from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox, QFrame,
    QScrollArea, QLabel, QGraphicsOpacityEffect, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QTimer, QEasingCurve, QPropertyAnimation, QDate, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence

from ..core import theme
from ..widgets.smooth_scroll import SmoothScrollArea
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
from .delivery_center_view import DeliveryCenterView
from .production_view import ProductionView
from .settings_view import SettingsView
from .user_center_view import UserCenterView
from .feedback_view import FeedbackView


import os

from ..core.pdf_folders import vendor_subfolder as _vendor_subfolder


def _vendor_pdf_folder(
    base_folder: str,
    user_code: str,
    user_name: str,
    user_role: str = "",
    req_vendor_code: str = "",
    req_vendor_name: str = "",
) -> str:
    """Retorna base_folder/<SUBPASTA_VENDEDOR>."""
    return os.path.join(
        base_folder,
        _vendor_subfolder(user_code, user_name, user_role, req_vendor_code, req_vendor_name),
    )


PAGE_FORM = 0
PAGE_HISTORY = 1
PAGE_DASHBOARD = 2
PAGE_TECHNICAL = 3
PAGE_ORDER_CENTER = 4
PAGE_PINHEIRO_INDUSTRIA = 5
PAGE_AR = 6
PAGE_USER_CENTER = 7
PAGE_SETTINGS = 8
PAGE_FEEDBACK = 9
PAGE_DELIVERY_CENTER = 10


class MainWindow(QMainWindow):
    switch_user_requested = Signal()

    def __init__(self):
        super().__init__()
        self.scale = res.effective_scale
        self._allow_close_without_prompt = False
        self._threads: list = []
        self._unread_count = 0
        self._listener: NotificationListener | None = None
        self._shown_notif_ids: set[int] = set()   # evita toast duplicado
        self._theme_transition_overlay: QLabel | None = None
        self._theme_transition_anim: QPropertyAnimation | None = None
        self._nav_overlay: QLabel | None = None
        self._setup_ui()
        self._setup_hidden_shortcuts()
        self._setup_statusbar()
        self.setWindowTitle("Sistema de Requisições - Ferragens Pinheiro")
        if res.start_maximized:
            self.showMaximized()
        else:
            width = max(640, int(1280 * self.scale))
            height = max(480, int(800 * self.scale))
            self.resize(width, height)
        self._toast_manager = ToastManager(self)
        self._refresh_session_profile()
        self._start_notification_listener()
        self._navigate_to_home()
        QTimer.singleShot(600, self._maybe_show_onboarding)

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
        self.sidebar.switch_user_clicked.connect(self._switch_user)
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
            max(480, int(860 * self.scale)),
            max(360, int(600 * self.scale)),
        )

        self._scroll_main = SmoothScrollArea()
        self._scroll_main.setWidgetResizable(True)
        self._scroll_main.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_main.setStyleSheet(
            f"QScrollArea {{ background:{theme.CONTENT_BG}; border:none; }}"
            f"QScrollBar:vertical {{"
            f"  width:8px; background:transparent;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 58)}; border-radius:4px; min-height:32px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 96)}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
            f"QScrollBar:horizontal {{"
            f"  height:8px; background:transparent;"
            f"}}"
            f"QScrollBar::handle:horizontal {{"
            f"  background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 58)}; border-radius:4px; min-width:32px;"
            f"}}"
            f"QScrollBar::handle:horizontal:hover {{ background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 96)}; }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        )
        self._scroll_main.setWidget(self.stack)
        root.addWidget(self._scroll_main, 1)

        # ── Inicialização lazy das views ─────────────────────────────────────
        # Apenas o formulário (tela inicial) é criado agora.
        # As demais views são instanciadas na primeira navegação via _ensure_view,
        # evitando que o startup bloqueie a UI enquanto constrói widgets não usados.
        self.form_view = RequisitionForm(self.scale)
        self.history_view: HistoryView | None = None
        self.dashboard_view: DashboardView | None = None
        self.technical_panel_view: TechnicalPanelView | None = None
        self.order_center_view: OrderCenterView | None = None
        self.delivery_center_view: DeliveryCenterView | None = None
        self.pinheiro_industria_view: ProductionView | None = None
        self.ar_view: ProductionView | None = None
        self.user_center_view: UserCenterView | None = None
        self.settings_view: SettingsView | None = None
        self.feedback_view: FeedbackView | None = None

        self.stack.addWidget(self.form_view)       # PAGE_FORM = 0
        from PySide6.QtWidgets import QWidget as _QW
        for _ in range(10):                        # páginas 1-10: placeholders leves
            self.stack.addWidget(_QW())

        # Sinal do formulário conectado imediatamente (único que precisa existir já)
        self.form_view.save_requested.connect(self._save_requisition)
        self.form_view.guide_requested.connect(
            lambda: self._show_screen_guide("nova", force=True)
        )

        # ── Visibilidade dos botões da sidebar por perfil ─────────────────────
        nav_visible = {
            "nova":               True,  # todos veem; A&R e Indústria em leitura
            "dashboard":          session.can_access_dashboard,
            "pedidos":            session.can_access_order_center,
            "entregas":           session.can_access_delivery_center,
            "pinheiro_industria": session.can_access_industria,
            "ar":                 session.can_access_ar,
            "historico":          True,
            "config":             True,
            "feedback":           True,
        }
        for key, visible in nav_visible.items():
            btn = self.sidebar._nav_btns.get(key)
            if btn:
                btn.setVisible(visible)
        self.sidebar.refresh_separators()

    def _setup_hidden_shortcuts(self) -> None:
        # Atalhos intencionais "ocultos": não exibem dicas na interface.
        shortcuts = {
            "Ctrl+1": lambda: self._on_nav("nova"),
            "Ctrl+2": lambda: self._on_nav("pedidos"),
            "Ctrl+3": lambda: self._on_nav("ar"),
            "Ctrl+4": lambda: self._on_nav("pinheiro_industria"),
            "Ctrl+5": lambda: self._on_nav("dashboard"),
            "Ctrl+6": lambda: self._on_nav("historico"),
            "Ctrl+7": self._toggle_theme_shortcut,
            "Ctrl+8": self._switch_user,
            "Ctrl+9": self._logout,
            "Ctrl+P": self._print_shortcut,
        }

        self._shortcut_actions: list[QAction] = []
        for sequence, callback in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self._shortcut_actions.append(action)

    def _toggle_theme_shortcut(self) -> None:
        self._on_theme_toggle(not theme.is_dark)

    def _print_shortcut(self) -> None:
        if hasattr(self, "form_view") and hasattr(self.form_view, "btn_print") and self.form_view.btn_print.isEnabled():
            self.form_view.btn_print.click()

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
        self._track_thread(thread, worker)

    def _apply_session_profile(self, data: dict):
        session.update_profile(data)
        self.sidebar.refresh_user()
        self.form_view.refresh_logged_user()
        self._setup_statusbar()

    def _nav_transition(self, page: int) -> None:
        """Cross-fade suave ao trocar de página no stack (160 ms, OutCubic).

        Lazy theme: se a view de destino tiver tema pendente (marcada em
        _on_theme_toggle), reaplica antes da navegação. O custo (~30–330 ms)
        fica mascarado pela animação de fade.
        """
        if self.stack.currentIndex() == page:
            return

        # Cancela overlay anterior se o usuário clicar rápido
        if self._nav_overlay is not None:
            self._nav_overlay.deleteLater()
            self._nav_overlay = None

        # Reaplica tema na view de destino se estiver "dirty" (oculta durante toggle)
        self._consume_theme_dirty(page)

        pixmap = self.stack.grab()
        self.stack.setCurrentIndex(page)

        if pixmap.isNull():
            return

        overlay = QLabel(self.stack)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setScaledContents(True)
        overlay.setPixmap(pixmap)
        overlay.setGeometry(self.stack.rect())
        overlay.raise_()
        overlay.show()
        self._nav_overlay = overlay

        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(1.0)
        overlay.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", overlay)
        anim.setDuration(140)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuart)

        def _done():
            overlay.deleteLater()
            self._nav_overlay = None

        anim.finished.connect(_done)
        overlay._anim = anim   # mantém referência viva durante a animação
        anim.start()

    def _on_nav(self, key: str):
        mapping = {
            "nova":               PAGE_FORM,
            "historico":          PAGE_HISTORY,
            "dashboard":          PAGE_DASHBOARD,
            "tecnico":            PAGE_TECHNICAL,
            "pedidos":            PAGE_ORDER_CENTER,
            "entregas":           PAGE_DELIVERY_CENTER,
            "pinheiro_industria": PAGE_PINHEIRO_INDUSTRIA,
            "ar":                 PAGE_AR,
            "usuarios":           PAGE_USER_CENTER,
            "config":             PAGE_SETTINGS,
            "feedback":           PAGE_FEEDBACK,
        }
        page = mapping.get(key, PAGE_FORM)

        # Garante que a view existe antes de tentar navegar para ela
        self._ensure_view(page)

        # Guards defensivos — botões já estão ocultos para roles sem acesso,
        # mas mantemos a verificação como camada de segurança extra.
        guards = {
            PAGE_DASHBOARD:          session.can_access_dashboard,
            PAGE_TECHNICAL:          session.can_access_technical_panel,
            PAGE_ORDER_CENTER:       session.can_access_order_center,
            PAGE_DELIVERY_CENTER:    session.can_access_delivery_center,
            PAGE_PINHEIRO_INDUSTRIA: session.can_access_industria,
            PAGE_AR:                 session.can_access_ar,
            PAGE_USER_CENTER:        session.can_manage_users,
        }
        if page in guards and not guards[page]:
            return
        if key in self.sidebar._nav_btns:
            self.sidebar._highlight(key)

        if key == "nova":
            if session.is_view_only:
                # A&R e Indústria: apenas visualização, sem resetar o formulário.
                # Se nenhuma requisição estiver carregada, exibe aviso no form.
                if not self.form_view.req_id:
                    lock_message = (
                        "Selecione uma requisição em Entregas ou Relatórios para visualizar."
                        if session.role == "entregas"
                        else "Selecione uma requisição no Histórico ou na Central de Pedidos para visualizar."
                    )
                    self.form_view._set_form_locked(
                        True,
                        lock_message,
                    )
                self._nav_transition(PAGE_FORM)
                return
            if not self._confirm_new_requisition():
                self._nav_transition(PAGE_FORM)
                self.sidebar._highlight("nova")
                return
            self.form_view.reset()

        if page == PAGE_HISTORY:
            self.history_view.refresh()
        elif page == PAGE_DASHBOARD:
            self.dashboard_view.refresh()
        elif page == PAGE_TECHNICAL:
            self.technical_panel_view.refresh()
        elif page == PAGE_ORDER_CENTER:
            self.order_center_view.refresh()
        elif page == PAGE_DELIVERY_CENTER:
            self.delivery_center_view.refresh()
        elif page == PAGE_PINHEIRO_INDUSTRIA:
            self.pinheiro_industria_view.refresh()
        elif page == PAGE_AR:
            self.ar_view.refresh()
        elif page == PAGE_USER_CENTER:
            self.user_center_view.refresh()
        elif page == PAGE_SETTINGS:
            self.settings_view.refresh_operational_settings()
        elif page == PAGE_FEEDBACK:
            self.feedback_view.refresh()

        self._nav_transition(page)
        # 1ª visita manual a esta tela → dispara o tutorial dela (uma vez).
        self._maybe_show_screen_guide(key)

    def _navigate_to_home(self) -> None:
        """Navega para a página inicial correta de acordo com o perfil."""
        if not session.is_view_only:
            return  # admin/gerente/vendedor já partem em PAGE_FORM por padrão
        if session.role == "entregas":
            self._ensure_view(PAGE_DELIVERY_CENTER)
            self.stack.setCurrentIndex(PAGE_DELIVERY_CENTER)
            self.sidebar._highlight("entregas")
            self.delivery_center_view.refresh()
            return
        if session.can_access_ar:
            self._ensure_view(PAGE_AR)
            self.stack.setCurrentIndex(PAGE_AR)
            self.sidebar._highlight("ar")
            self.ar_view.refresh()
        else:
            self._ensure_view(PAGE_PINHEIRO_INDUSTRIA)
            self.stack.setCurrentIndex(PAGE_PINHEIRO_INDUSTRIA)
            self.sidebar._highlight("pinheiro_industria")
            self.pinheiro_industria_view.refresh()

    # ── Lazy loading de views ─────────────────────────────────────────────────

    def _ensure_view(self, page: int) -> None:
        """Cria e registra a view de ``page`` se ainda não foi inicializada.

        Substitui o placeholder leve no QStackedWidget pela view real e conecta
        os sinais correspondentes.  Chamada antes de qualquer navegação.
        """
        _attr = {
            PAGE_HISTORY:            "history_view",
            PAGE_DASHBOARD:          "dashboard_view",
            PAGE_TECHNICAL:          "technical_panel_view",
            PAGE_ORDER_CENTER:       "order_center_view",
            PAGE_DELIVERY_CENTER:    "delivery_center_view",
            PAGE_PINHEIRO_INDUSTRIA: "pinheiro_industria_view",
            PAGE_AR:                 "ar_view",
            PAGE_USER_CENTER:        "user_center_view",
            PAGE_SETTINGS:           "settings_view",
            PAGE_FEEDBACK:           "feedback_view",
        }
        attr = _attr.get(page)
        if attr is None or getattr(self, attr) is not None:
            return  # PAGE_FORM ou já criada

        view = self._create_view_for_page(page)
        setattr(self, attr, view)

        # Troca o placeholder pela view real mantendo o índice correto
        placeholder = self.stack.widget(page)
        self.stack.removeWidget(placeholder)
        placeholder.deleteLater()
        self.stack.insertWidget(page, view)

        self._connect_view_signals(page, view)

    def _create_view_for_page(self, page: int):
        """Instancia a view correspondente ao índice ``page``."""
        if page == PAGE_HISTORY:
            return HistoryView(self.scale)
        if page == PAGE_DASHBOARD:
            return DashboardView(self.scale)
        if page == PAGE_TECHNICAL:
            return TechnicalPanelView(self.scale)
        if page == PAGE_ORDER_CENTER:
            return OrderCenterView(self.scale)
        if page == PAGE_DELIVERY_CENTER:
            return DeliveryCenterView(self.scale)
        if page == PAGE_PINHEIRO_INDUSTRIA:
            return ProductionView(
                self.scale,
                destinations=("Pinheiro Indústria",),
                title="PINHEIRO INDÚSTRIA",
                subtitle="Acompanhamento operacional das requisições enviadas para a Pinheiro Indústria.",
            )
        if page == PAGE_AR:
            return ProductionView(
                self.scale,
                destinations=("A&R",),
                title="A&R",
                subtitle="Acompanhamento operacional das requisições enviadas para a A&R.",
            )
        if page == PAGE_USER_CENTER:
            return UserCenterView(self.scale)
        if page == PAGE_SETTINGS:
            return SettingsView(self.scale)
        if page == PAGE_FEEDBACK:
            return FeedbackView(self.scale)
        raise ValueError(f"Página desconhecida: {page}")

    def _connect_view_signals(self, page: int, view) -> None:
        """Conecta os sinais da view recém-criada.

        Botão "?" de cada tela abre o tutorial DAQUELA tela (force=True), em
        vez do guia geral. O guia geral fica reservado para o botão
        "Ver Guia Rápido" em Configurações.
        """
        if page == PAGE_HISTORY:
            view.open_requisition.connect(
                lambda req_id: self._open_requisition(req_id, "history")
            )
            view.guide_requested.connect(
                lambda: self._show_screen_guide("historico", force=True)
            )
        elif page == PAGE_ORDER_CENTER:
            view.open_requisition.connect(
                lambda req_id: self._open_requisition(req_id, "order_center")
            )
            view.guide_requested.connect(
                lambda: self._show_screen_guide("pedidos", force=True)
            )
        elif page == PAGE_DELIVERY_CENTER:
            view.open_requisition.connect(
                lambda req_id: self._open_requisition(req_id, "delivery_center")
            )
            view.guide_requested.connect(
                lambda: self._show_screen_guide("entregas", force=True)
            )
        elif page == PAGE_DASHBOARD:
            view.guide_requested.connect(
                lambda: self._show_screen_guide("dashboard", force=True)
            )
        elif page == PAGE_TECHNICAL:
            view.guide_requested.connect(
                lambda: self._show_screen_guide("tecnico", force=True)
            )
        elif page == PAGE_USER_CENTER:
            view.guide_requested.connect(
                lambda: self._show_screen_guide("usuarios", force=True)
            )
        elif page == PAGE_PINHEIRO_INDUSTRIA:
            view.open_requisition.connect(
                lambda req_id: self._open_requisition(req_id, "production")
            )
            view.guide_requested.connect(
                lambda: self._show_screen_guide("pinheiro_industria", force=True)
            )
        elif page == PAGE_AR:
            view.open_requisition.connect(
                lambda req_id: self._open_requisition(req_id, "production")
            )
            view.guide_requested.connect(
                lambda: self._show_screen_guide("ar", force=True)
            )
        elif page == PAGE_SETTINGS:
            view.scale_changed.connect(self._on_scale_changed)
            view.font_size_changed.connect(lambda: self._on_scale_changed(res.scale))
            # Em Configurações o botão "Ver Guia Rápido" reabre o guia GERAL
            # (visão de todas as telas) — mantém comportamento original.
            view.show_guide_requested.connect(self.show_onboarding)

    # ─────────────────────────────────────────────────────────────────────────

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
            PAGE_DELIVERY_CENTER: "entregas",
            PAGE_PINHEIRO_INDUSTRIA: "pinheiro_industria",
            PAGE_AR: "ar",
            PAGE_USER_CENTER: "usuarios",
            PAGE_SETTINGS: "config",
            PAGE_FEEDBACK: "feedback",
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
        signature_png = getattr(self.form_view, "_signature_png_bytes", None)

        if self.form_view.req_id:
            req_id = self.form_view.req_id
            thread, worker = _run_in_thread(
                api.update_requisition,
                req_id,
                data,
                on_result=lambda req: self._after_save(
                    req,
                    canvas_json,
                    client,
                    obs,
                    signature_png,
                ),
                on_error=self._on_save_error,
            )
        else:
            thread, worker = _run_in_thread(
                api.create_requisition,
                data,
                on_result=lambda req: self._after_save(
                    req,
                    canvas_json,
                    client,
                    obs,
                    signature_png,
                ),
                on_error=self._on_save_error,
            )
        self._track_thread(thread, worker)

    def _after_save(self, req: dict, canvas_json: str,
                    client: dict | None = None, obs: str = "",
                    signature_png_bytes: bytes | None = None):
        # O canvas (desenho) já foi gravado junto na transação da requisição
        # (campo canvas_json no payload de create/update). Não há mais uma
        # segunda chamada que pudesse falhar em silêncio: vai direto ao PDF.
        self.form_view.req_id = req["id"]
        self.form_view._req_vendor_code = str(req.get("vendor_code") or "")
        self.form_view._req_vendor_name = str(req.get("vendor_name") or "")
        self.form_view._req_vendor_whatsapp = str(
            req.get("vendor_whatsapp")
            or (req.get("vendor") or {}).get("whatsapp")
            or ""
        )
        self.form_view._refresh_header_vendor_label()
        self.form_view._generate_qr()
        # Atualiza a versão carregada (trava otimista) com o updated_at recém
        # retornado, para que um próximo salvamento do mesmo usuário não conflite.
        self.form_view._loaded_updated_at = req.get("updated_at")
        self._on_fully_saved(req, canvas_json, client, obs, signature_png_bytes)

    def _on_fully_saved(self, req: dict, canvas_json: str,
                        client: dict | None, obs: str,
                        signature_png_bytes: bytes | None = None):
        pdf_path = self._generate_pdf_sync(
            req,
            client,
            obs,
            canvas_json,
            signature_png_bytes=signature_png_bytes,
        )
        self._show_saved(pdf_path)

    def _generate_pdf_sync(self, req: dict, client: dict | None,
                           obs: str, canvas_json: str = "{}",
                           signature_png_bytes: bytes | None = None) -> str:
        try:
            from ..services.pdf_generator import generate_pdf, HAS_REPORTLAB, PdfPublishError
        except ImportError:
            return ""
        if not HAS_REPORTLAB:
            return ""

        from ..core.resolution import res as _res
        from ..core.session import session as _session

        base_folder = _res.pdf_folder.strip()
        if not base_folder:
            return ""

        folder = _vendor_pdf_folder(
            base_folder,
            _session.user_code,
            _session.user_name,
            _session.role,
            str(req.get("vendor_code") or ""),
            str(req.get("vendor_name") or ""),
        )

        try:
            return generate_pdf(
                req,
                client,
                obs,
                folder,
                canvas_json,
                signature_png_bytes=signature_png_bytes,
            )
        except PdfPublishError as exc:
            # O PDF foi gerado localmente, mas não publicou na pasta de rede.
            QMessageBox.warning(
                self,
                "PDF não salvo na rede",
                f"A requisição foi salva normalmente.\n\n{exc}",
            )
            return ""
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Aviso",
                f"Requisição salva, mas houve um problema ao gerar o PDF:\n{exc}",
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
        self._track_thread(thread, worker)

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
        self._notif_timer.timeout.connect(self._sync_feedback_badge)
        self._notif_timer.start()

        # Primeira sincronização do badge de feedbacks (logo após o login)
        QTimer.singleShot(1_500, self._sync_feedback_badge)

    def _on_notification(self, data: dict):
        """
        Processa cada evento SSE recebido.

        Inclui tanto eventos iniciais (não lidas do banco ao conectar)
        quanto pushes em tempo real. _shown_notif_ids garante que o
        toast apareça exatamente uma vez por notificação.

        Apenas eventos com id real (registros do banco) incrementam o badge.
        Eventos virtuais como stuck_requisition_events (id=None) exibem
        toast mas não alteram o contador — a central não os exibe.
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
        self._track_thread(thread, worker)

    def _update_badge(self, count: int):
        self._unread_count = count
        self.sidebar.set_notification_count(count)

    def _sync_feedback_badge(self):
        """Atualiza o badge vermelho ao lado do botão Feedbacks."""
        thread, worker = _run_in_thread(
            api.get_feedback_unread_count,
            on_result=lambda r: self.set_feedback_unread_count(int(r.get("unread", 0) or 0)),
            on_error=lambda _: None,
        )
        self._track_thread(thread, worker)

    def set_feedback_unread_count(self, count: int):
        """Chamado pela FeedbackView (após mark-read) e pelo poll periódico."""
        self.sidebar.set_feedback_unread_count(count)

    def _show_notification_panel(self):
        thread, worker = _run_in_thread(
            api.list_notifications,
            on_result=self._open_notification_drawer,
            on_error=lambda msg: QMessageBox.warning(self, "Erro", msg),
        )
        self._track_thread(thread, worker)

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
        self._track_thread(thread, worker)

    def _mark_one_read(self, notif_id: int):
        thread, worker = _run_in_thread(
            api.mark_one_notification_read,
            notif_id,
            on_result=lambda _: self._sync_badge(),
            on_error=lambda _: None,
        )
        self._track_thread(thread, worker)

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
        state = {"scale_label": selected_scale}
        if hasattr(self.settings_view, "input_url"):
            state["url"] = self.settings_view.input_url.text()
        if hasattr(self.settings_view, "input_pending_invoice_days"):
            state["pending_invoice_alert_days"] = self.settings_view.input_pending_invoice_days.value()
        return state

    def _restore_settings_state(self, state: dict) -> None:
        if hasattr(self.settings_view, "input_url"):
            self.settings_view.input_url.setText(state.get("url") or "")
        if hasattr(self.settings_view, "input_pending_invoice_days"):
            self.settings_view.input_pending_invoice_days.setValue(
                int(state.get("pending_invoice_alert_days") or 1)
            )
        selected_scale = state.get("scale_label")
        for label, btn in self.settings_view._scale_btns.items():
            btn.setChecked(label == selected_scale)

    def _capture_user_center_state(self) -> dict:
        return {
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
        elif current_page == PAGE_FEEDBACK:
            state["feedback"] = {
                "text": self.feedback_view.input_feedback.toPlainText(),
            }
        return state

    def _restore_ui_state(self, state: dict) -> None:
        current_page = state.get("current_page", PAGE_FORM)
        self._ensure_view(current_page)   # garante que a view existe antes de restaurar
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
        elif current_page == PAGE_DELIVERY_CENTER:
            self.delivery_center_view.refresh()
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
        elif current_page == PAGE_FEEDBACK:
            feedback_state = state.get("feedback") or {}
            self.feedback_view.input_feedback.setPlainText(feedback_state.get("text") or "")
            self.feedback_view.refresh()

    def _build_replacement_window(self) -> "MainWindow":
        state = self._capture_ui_state()
        old_central = self.takeCentralWidget()
        if old_central is not None:
            old_central.deleteLater()
        self.scale = res.effective_scale
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

    def _track_thread(self, thread: "QThread", worker: "QObject") -> None:
        """Rastreia (thread, worker) em self._threads e agenda a remocao
        automatica quando o thread terminar.

        Substitui o padrao antigo `self._threads.append((t, w))`, que nunca
        removia nada da lista — causava acumulo de tuplas referenciando objetos
        ja deletados pelo cleanup do _run_in_thread. Em sessoes longas
        (vendedor com app aberto o dia inteiro), a lista podia crescer com
        centenas de entradas mortas.
        """
        pair = (thread, worker)
        self._threads.append(pair)

        def _drop():
            try:
                self._threads.remove(pair)
            except ValueError:
                pass

        thread.finished.connect(_drop)

    def _get_current_view(self):
        """Retorna a view visível no stack, ou None."""
        views = [
            self.form_view, self.history_view, self.dashboard_view,
            self.technical_panel_view, self.order_center_view,
            self.pinheiro_industria_view, self.ar_view,
            self.user_center_view, self.settings_view, self.feedback_view,
            self.delivery_center_view,
        ]
        idx = self.stack.currentIndex()
        return views[idx] if 0 <= idx < len(views) else None

    # ── Lazy theme: views ocultas só re-estilizam quando o usuário navega ────
    def _mark_other_views_theme_dirty(self) -> None:
        """Marca todas as views como precisando reaplicar tema, exceto a atual.

        Chamado em _on_theme_toggle: a view atual e a sidebar já receberam o
        novo tema imediatamente; as outras esperam o usuário navegar pra elas.
        Economia: ~700–1000 ms de trabalho diferido fora do caminho crítico.
        """
        all_views = [
            self.form_view, self.history_view, self.dashboard_view,
            self.technical_panel_view, self.order_center_view, self.delivery_center_view,
            self.pinheiro_industria_view, self.ar_view,
            self.user_center_view, self.settings_view, self.feedback_view,
        ]
        current = self._get_current_view()
        for v in all_views:
            if v is not None and v is not current:
                v._theme_dirty = True  # type: ignore[attr-defined]

    def _consume_theme_dirty(self, page: int) -> None:
        """Se a view de destino está com tema pendente, aplica antes da navegação.

        Custo típico: 30–100 ms (Dashboard pode chegar a 330). Mascarado pela
        animação de cross-fade do _nav_transition.
        """
        views_by_page = {
            PAGE_FORM:               getattr(self, "form_view", None),
            PAGE_HISTORY:            getattr(self, "history_view", None),
            PAGE_DASHBOARD:          getattr(self, "dashboard_view", None),
            PAGE_TECHNICAL:          getattr(self, "technical_panel_view", None),
            PAGE_ORDER_CENTER:       getattr(self, "order_center_view", None),
            PAGE_DELIVERY_CENTER:    getattr(self, "delivery_center_view", None),
            PAGE_PINHEIRO_INDUSTRIA: getattr(self, "pinheiro_industria_view", None),
            PAGE_AR:                 getattr(self, "ar_view", None),
            PAGE_USER_CENTER:        getattr(self, "user_center_view", None),
            PAGE_SETTINGS:           getattr(self, "settings_view", None),
            PAGE_FEEDBACK:           getattr(self, "feedback_view", None),
        }
        view = views_by_page.get(page)
        if view is not None and getattr(view, "_theme_dirty", False):
            self._apply_theme_to_view_buffered(view)
            view._theme_dirty = False  # type: ignore[attr-defined]

    def _apply_theme_to_view_buffered(self, view) -> None:
        """Aplica tema na view com updates suspensos (evita repaint intermediário).

        setUpdatesEnabled(False) ao redor do apply_theme + _refresh_shadows_for
        elimina o flicker e os repaints parciais que o Qt dispara a cada
        setStyleSheet. Ganho típico: -30 a -50% em telas com QTableWidget
        populado (Histórico, Dashboard, A&R, Pinheiro Indústria).
        """
        view.setUpdatesEnabled(False)
        try:
            view.apply_theme()
            self._refresh_shadows_for(view)
        finally:
            view.setUpdatesEnabled(True)

    def _refresh_shadows_for(self, root) -> None:
        """Atualiza a cor dos QGraphicsDropShadowEffect dentro de um widget."""
        for child in root.findChildren(QWidget):
            effect = child.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                alpha = effect.color().alpha()
                color = QColor(theme.PANEL_SHADOW)
                color.setAlpha(alpha)
                effect.setColor(color)

    def _apply_theme_immediate(self) -> None:
        """Aplica tema apenas ao sidebar e à view atual (~30ms)."""
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
            f"  background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 58)}; border-radius:4px; min-height:32px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{ background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 96)}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
            f"QScrollBar:horizontal {{"
            f"  height:8px; background:transparent;"
            f"}}"
            f"QScrollBar::handle:horizontal {{"
            f"  background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 58)}; border-radius:4px; min-width:32px;"
            f"}}"
            f"QScrollBar::handle:horizontal:hover {{ background:{theme.rgba(theme.PANEL_NEON_PRIMARY, 96)}; }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}"
        )
        # Aplica o global_style ANTES das views — assim cada setStyleSheet
        # inline das views já trabalha com a paleta global atualizada (evita
        # ~150 ms de re-resolução dupla do QSS pelo Qt).
        app = QApplication.instance()
        app.setStyleSheet(theme.global_style())
        self.sidebar.apply_theme()
        current = self._get_current_view()
        if current is not None:
            # setUpdatesEnabled(False) suspende repaint enquanto reaplica os
            # styles. Vital em telas pesadas (Histórico, Dashboard, A&R,
            # Pinheiro Indústria) onde cada setStyleSheet de tabela disparava
            # repaint completo, somando centenas de ms.
            self._apply_theme_to_view_buffered(current)
        self._refresh_shadows_for(self.sidebar)
        self._setup_statusbar()

    def _on_theme_toggle(self, dark: bool):
        """
        Troca de tema com transição visual quase instantânea.

        Estratégia: cross-fade entre dois pixmaps (tema antigo → tema novo).
        Em vez de fade-out de um pixmap só (380ms), dissolvemos o pixmap antigo
        sobre o pixmap novo em ~120ms — sensação de troca decidida.

        Sequência:
        1. grab() do estado atual (tema antigo) → old_pixmap
        2. Mostra overlay COM old_pixmap (cobre a janela)
        3. processEvents() — overlay garante que não há flash visível
        4. Aplica tema novo (sidebar + view atual + global) — invisível
        5. Marca outras views como dirty (lazy)
        6. Move overlay temporariamente para fora da tela; grab() → new_pixmap
        7. Cross-fade: overlay vira new_pixmap; cria top_overlay com old_pixmap
           e anima opacity 1.0 → 0.0 em ~120ms.
        8. Cleanup de ambos overlays.
        """
        from PySide6.QtWidgets import QApplication

        old_pixmap = self.grab()
        cover = self._show_frozen_overlay(old_pixmap)
        QApplication.processEvents()

        # res.save() escreve no disco — adiado para depois do cross-fade
        # para nao adicionar I/O ao caminho critico da animacao.
        theme.set_dark(dark)

        # Aplica tema na view atual + sidebar + global (cover ainda visível)
        self._apply_theme_immediate()
        # Demais views: lazy — aplicam sozinhas quando o usuário navegar
        self._mark_other_views_theme_dirty()
        QApplication.processEvents()

        # Captura snapshot do tema NOVO sem o overlay no caminho — move o
        # overlay para fora da tela momentaneamente (mais barato que hide/show
        # e sem flicker observável).
        new_pixmap = self._grab_without_overlay(cover)
        self._start_cross_fade(cover, old_pixmap, new_pixmap, duration_ms=120)

        # I/O da preferencia: depois do toggle visual terminar.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, lambda d=dark: res.save(dark_mode=d))

    def _grab_without_overlay(self, overlay):
        """Captura um pixmap da janela sem o overlay aparecer.

        Em vez de hide()/show() (que dispara repaint visível), movemos o
        overlay para fora da viewport e voltamos. Praticamente sem custo.
        """
        if overlay is None:
            return self.grab()
        original_pos = overlay.pos()
        overlay.move(-99999, -99999)
        pix = self.grab()
        overlay.move(original_pos)
        return pix

    def _start_cross_fade(self, cover, old_pixmap, new_pixmap, duration_ms: int = 120):
        """Cross-fade entre old_pixmap (em top_overlay) e new_pixmap (em cover).

        cover já está visível com old_pixmap. Substituímos seu pixmap por
        new_pixmap (atrás) e criamos um top_overlay com old_pixmap por cima,
        animando opacity 1→0. O usuário vê os dois temas se cruzando suavemente.
        """
        from PySide6.QtWidgets import QApplication, QLabel
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        if cover is None or new_pixmap.isNull():
            # Fallback: fade-out simples
            self._start_overlay_fadeout(cover, on_complete=None)
            return

        # Atrás: pixmap do tema NOVO (estado final)
        cover.setPixmap(new_pixmap)

        # Em cima: pixmap do tema ANTIGO que vai se dissolver
        top = QLabel(self)
        top.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top.setScaledContents(True)
        top.setPixmap(old_pixmap)
        top.setGeometry(self.rect())
        top.raise_()
        top.show()

        effect = QGraphicsOpacityEffect(top)
        effect.setOpacity(1.0)
        top.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", top)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _cleanup():
            top.deleteLater()
            if cover is not None:
                cover.deleteLater()
            self._theme_transition_overlay = None
            self._theme_transition_anim = None

        anim.finished.connect(_cleanup)
        self._theme_transition_anim = anim
        anim.start()

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
            self._stop_runtime_services()
            session.logout()
            self._allow_close_without_prompt = True
            self.close()

    def _switch_user(self):
        reply = ask_confirmation(
            self,
            "Trocar usuário",
            "Deseja encerrar a sessão atual e voltar para a tela de login?",
            yes_text="Sim",
            no_text="Não",
        )
        if not reply:
            return
        self._stop_runtime_services()
        session.logout()

        # Mostra o login (opacity 0, vai fazer fade-in) antes de sumir
        self.switch_user_requested.emit()

        # Faz o fade-out desta janela e fecha ao terminar
        self._switch_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._switch_anim.setDuration(220)
        self._switch_anim.setStartValue(1.0)
        self._switch_anim.setEndValue(0.0)
        self._switch_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._switch_anim.finished.connect(self._close_without_confirmation)
        self._switch_anim.start()

    def _close_without_confirmation(self):
        self._allow_close_without_prompt = True
        self.close()

    # ── Tour guiado (spotlight) ───────────────────────────────────────────────

    def _home_screen_key(self) -> str:
        """Tela inicial do perfil (mesma lógica de _navigate_to_home)."""
        if session.is_view_only:
            if session.role == "entregas":
                return "entregas"
            return "ar" if session.can_access_ar else "pinheiro_industria"
        return "nova"

    def _maybe_show_onboarding(self) -> None:
        """No primeiro login do perfil: boas-vindas + tutorial da TELA INICIAL.
        As demais telas se explicam sozinhas na 1ª visita manual."""
        if res.guide_shown(session.role):
            return
        from ..widgets.spotlight_overlay import SpotlightOverlay
        welcome, _order, groups = self._split_tour_steps(self._build_tour_steps(session.role))
        home = self._home_screen_key()
        steps = list(welcome) + groups.get(home, [])
        if not steps:
            res.mark_guide_shown(session.role)
            return
        role = session.role
        overlay = SpotlightOverlay(
            self, steps, self.scale, role=role,
            on_finish=lambda r=role, k=home: (
                res.mark_guide_shown(r), res.mark_screen_guide_shown(r, k)
            ),
        )
        overlay.start()

    def show_onboarding(self) -> None:
        """Reabre o guia GERAL completo (boas-vindas + visão geral de todas as
        telas). Chamado pelo botão 'Ver Guia Rápido' em Configurações."""
        self._start_overview_tour()

    def _start_overview_tour(self) -> None:
        from ..widgets.spotlight_overlay import SpotlightOverlay
        steps = self._general_overview_steps(session.role)
        if not steps:
            return
        role = session.role
        overlay = SpotlightOverlay(
            self, steps, self.scale, role=role,
            on_finish=lambda r=role: res.mark_guide_shown(r),
        )
        overlay.start()

    def _show_screen_guide(self, key: str, force: bool = False) -> None:
        """Mostra o tutorial detalhado de UMA tela. force=True (botão '?')
        ignora o marcador de 'já visto'."""
        from ..widgets.spotlight_overlay import SpotlightOverlay
        role = session.role
        if not force and res.screen_guide_shown(role, key):
            return
        steps = self._screen_guide_steps(role, key)
        if not steps:
            return
        overlay = SpotlightOverlay(
            self, steps, self.scale, role=role,
            on_finish=lambda r=role, k=key: res.mark_screen_guide_shown(r, k),
        )
        overlay.start()

    def _maybe_show_screen_guide(self, key: str) -> None:
        """Na PRIMEIRA visita manual a uma tela, dispara seu tutorial (uma vez).
        Adiado até o fim da transição de navegação."""
        role = session.role
        if not key or res.screen_guide_shown(role, key):
            return
        QTimer.singleShot(450, lambda k=key: self._show_screen_guide(k))

    @staticmethod
    def _split_tour_steps(steps: list):
        """Divide a lista plana em (boas-vindas, ordem_de_telas, {tela: passos}).
        Cada passo com navigate_key inicia o grupo de uma tela."""
        welcome: list = []
        order: list = []
        groups: dict = {}
        current = None
        for st in steps:
            key = getattr(st, "navigate_key", None)
            if key:
                current = key
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append(st)
            elif current is None:
                welcome.append(st)
            else:
                groups[current].append(st)
        return welcome, order, groups

    def _general_overview_steps(self, role: str) -> list:
        """Guia geral: boas-vindas + o 1º passo (visão geral) de cada tela."""
        welcome, order, groups = self._split_tour_steps(self._build_tour_steps(role))
        steps = list(welcome)
        for key in order:
            if groups.get(key):
                steps.append(groups[key][0])
        return steps

    def _screen_guide_steps(self, role: str, key: str) -> list:
        """Tutorial detalhado de uma tela específica."""
        _, _, groups = self._split_tour_steps(self._build_tour_steps(role))
        return groups.get(key, [])

    def _build_tour_steps(self, role: str) -> list:
        from ..widgets.spotlight_overlay import TourStep

        mw = self

        # ── Getters de widgets ────────────────────────────────────────────────
        def nav(key):
            """Getter para botão da barra lateral."""
            return lambda: mw.sidebar._nav_btns.get(key)

        def bell():
            return mw.sidebar._bell

        def form(attr):
            """Getter para atributo do formulário."""
            return lambda: getattr(mw.form_view, attr, None)

        def hist(attr):
            """Getter para atributo do histórico (carregado sob demanda)."""
            return lambda: getattr(mw.history_view, attr, None) if mw.history_view else None

        def ar(attr, key=None):
            """Getter para widget da view A&R (carregada sob demanda)."""
            def _get():
                view = mw.ar_view
                if view is None:
                    return None
                val = getattr(view, attr, None)
                if key is not None and isinstance(val, dict):
                    return val.get(key)
                return val
            return _get

        def pin(attr, key=None):
            """Getter para widget da view Pinheiro Indústria (carregada sob demanda)."""
            def _get():
                view = mw.pinheiro_industria_view
                if view is None:
                    return None
                val = getattr(view, attr, None)
                if key is not None and isinstance(val, dict):
                    return val.get(key)
                return val
            return _get

        def order(attr, key=None):
            """Getter para widget da Central de Pedidos (carregada sob demanda)."""
            def _get():
                view = mw.order_center_view
                if view is None:
                    return None
                val = getattr(view, attr, None)
                if key is not None and isinstance(val, dict):
                    return val.get(key)
                return val
            return _get

        def delivery(attr):
            """Getter para widget da Central de Entregas (carregada sob demanda)."""
            return lambda: getattr(mw.delivery_center_view, attr, None) if mw.delivery_center_view else None

        def dash(attr):
            """Getter para widget do Dashboard (carregado sob demanda)."""
            return lambda: getattr(mw.dashboard_view, attr, None) if mw.dashboard_view else None

        def cfg(attr, idx=None):
            """Getter para widget de Configurações (carregado sob demanda)."""
            def _get():
                view = mw.settings_view
                if view is None:
                    return None
                val = getattr(view, attr, None)
                if idx is not None and isinstance(val, list):
                    return val[idx] if len(val) > idx else None
                return val
            return _get

        # ── Passo de boas-vindas (sem spotlight) ──────────────────────────────
        welcome = TourStep(
            title="Bem-vindo ao Sistema de Requisições!",
            body=(
                "Este tour rápido apresenta as principais funcionalidades "
                "disponíveis para o seu perfil.<br><br>"
                "Clique em <b>Próximo</b> para começar, ou "
                "<b>Pular tour</b> para ir direto ao sistema."
            ),
            tooltip_side="center",
        )

        # ── Passos por perfil ─────────────────────────────────────────────────
        if role == "admin":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                TourStep(
                    "Nova Requisição",
                    "Crie e edite pedidos de compra. Preencha o PED, "
                    "selecione o cliente, adicione os itens e defina o prazo. "
                    "O <b>PDF é gerado automaticamente</b> ao salvar.",
                    nav("nova"), "right", "nova",
                ),
                TourStep(
                    "Número do PED",
                    "Digite aqui o número do pedido. "
                    "É o campo principal e <b>obrigatório</b> para salvar.",
                    form("input_ped"), "bottom",
                ),
                TourStep(
                    "Busca de Cliente",
                    "Pesquise pelo nome, CNPJ ou código do cliente. "
                    "O sistema busca nos <b>+112 mil cadastros</b> enquanto você digita.",
                    form("client_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Itens",
                    "Adicione os itens da requisição: descrição, quantidade e unidade. "
                    "Pressione <b>Enter</b> para confirmar cada linha e avançar.",
                    form("item_table"), "top",
                ),
                TourStep(
                    "Prazo de Entrega",
                    "Defina a data de entrega esperada. "
                    "Pedidos com prazo vencido aparecem em vermelho no dashboard.",
                    form("input_prazo"), "bottom",
                ),
                TourStep(
                    "Editor de Desenho",
                    "Clique no canvas para desenhar croquis e cotas diretamente "
                    "na requisição. O desenho é exportado no PDF final.",
                    form("canvas_preview"), "top",
                ),
                TourStep(
                    "Salvar / Imprimir",
                    "Salvar registra a requisição e gera o PDF automaticamente. "
                    "Imprimir abre o PDF gerado para impressão ou envio.",
                    form("btn_save"), "top",
                ),
                # ── Central de Usuários ───────────────────────────────────────
                TourStep(
                    "Central de Usuários",
                    "Em <b>Configurações → Usuários</b> você cadastra, edita e "
                    "desativa membros da equipe e define o nível de acesso: "
                    "<b>Vendedor, Gerente, A&R, Indústria ou Entrega</b>.",
                    nav("config"), "right", "config",
                ),
                # ── Painel Gerencial ──────────────────────────────────────────
                TourStep(
                    "Painel Gerencial",
                    "Visão executiva da operação: pedidos em produção, "
                    "atrasos, faturamentos e ritmo diário.",
                    nav("dashboard"), "right", "dashboard",
                ),
                TourStep(
                    "Ranking de Vendedores",
                    "Volume de requisições emitidas por vendedor no período. "
                    "Identifique quem está mais ativo.",
                    dash("vendors_card"), "right",
                ),
                TourStep(
                    "Pedidos sem Confirmação",
                    "Pedidos aguardando retorno da produção há mais de <b>1 hora</b>. "
                    "Ação imediata necessária.",
                    dash("alerts_card"), "left",
                ),
                TourStep(
                    "Máquinas da A&R",
                    "Ranking das máquinas da A&R por volume de operações. "
                    "Identifique gargalos de produção.",
                    dash("machines_ar_card"), "right",
                ),
                TourStep(
                    "Máquinas da Indústria",
                    "Ranking das máquinas da Pinheiro Indústria. "
                    "Compare o desempenho entre as duas filiais.",
                    dash("machines_industria_card"), "left",
                ),
                TourStep(
                    "Últimas Requisições",
                    "Visão rápida das requisições mais recentes do sistema. "
                    "Duplo clique para abrir qualquer uma.",
                    dash("recent_card"), "top",
                ),
                # ── Central de Pedidos ────────────────────────────────────────
                TourStep(
                    "Central de Pedidos",
                    "Acompanhe todos os pedidos em andamento por status: "
                    "aguardando recebimento, em produção, faturamento e cancelados.",
                    nav("pedidos"), "right", "pedidos",
                ),
                TourStep(
                    "Aguardando Recebimento",
                    "Pedidos enviados para produção ainda não confirmados. "
                    "Duplo clique para abrir e acompanhar.",
                    order("_section_cards", "aguardando_recebimento"), "right",
                ),
                TourStep(
                    "Em Produção",
                    "Pedidos que já foram recebidos e estão sendo produzidos. "
                    "Acompanhe em qual destino cada um está.",
                    order("_section_cards", "em_producao"), "left",
                ),
                TourStep(
                    "Pedidos Finalizados",
                    "Pedidos já finalizados. Disponíveis para consulta e "
                    "reimpressão do PDF quando necessário.",
                    order("_section_cards", "faturados"), "left",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Histórico / Busca",
                    "Busque qualquer requisição por status, cliente, data ou PED. "
                    "Clique duas vezes para abrir e editar.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED, nome do cliente ou obra. "
                    "Combine com os filtros de status e período para resultados precisos.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique em uma linha para abrir a requisição completa.",
                    hist("table"), "top",
                ),
                # ── Configurações ─────────────────────────────────────────────
                TourStep(
                    "Configurações",
                    "Gerencie backup automático, escala da interface, "
                    "senha de acesso e alertas de faturamento.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Aba Aparência",
                    "Ajuste a <b>escala da interface</b> e o <b>tamanho de fonte</b> "
                    "para se adaptar a qualquer resolução de tela.",
                    cfg("_tab_btns", 0), "bottom",
                ),
                TourStep(
                    "Aba Conta",
                    "Altere sua senha de acesso. "
                    "Recomendado trocar periodicamente por segurança.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Aba Sistema",
                    "Configure a <b>URL do servidor</b> e teste a conexão com o backend, "
                    "ajuste os alertas de faturamento e o prazo mínimo de entrega. "
                    "Aqui também fica o <b>Painel Técnico</b>, com a saúde do servidor "
                    "em tempo real: conexão, tempo de resposta, uso de disco e erros.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                TourStep(
                    "Aba Login",
                    "Personalize o <b>fundo da tela de login</b> com imagens da empresa. "
                    "Adicione, remova e visualize as imagens disponíveis.",
                    cfg("_tab_btns", 3), "bottom",
                ),
                TourStep(
                    "Aba Backup",
                    "Configure o <b>backup automático</b> do banco de dados: "
                    "horário de execução e retenção diária, semanal e mensal.",
                    cfg("_tab_btns", 4), "bottom",
                ),
                TourStep(
                    "Aba Usuários",
                    "Cadastre, edite e desative os usuários do sistema e "
                    "defina o nível de acesso de cada um.",
                    cfg("_tab_btns", 5), "bottom",
                ),
                TourStep(
                    "Aba Clientes",
                    "Cadastre clientes individualmente ou <b>importe em lote</b> "
                    "por planilha Excel, e mantenha a base de clientes atualizada.",
                    cfg("_tab_btns", 6), "bottom",
                ),
                TourStep(
                    "Aba Ajuda",
                    "Verifique atualizações disponíveis e acesse "
                    "o <b>Guia Rápido</b> novamente a qualquer momento.",
                    cfg("_tab_btns", 7), "bottom",
                ),
                TourStep(
                    "Salvar Configurações",
                    "Após ajustar as preferências, clique em "
                    "<b>Salvar Configurações</b> para aplicar as mudanças.",
                    cfg("btn_save"), "top",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "O sino exibe alertas em tempo real para eventos do sistema. "
                    "Um <b>badge vermelho</b> indica notificações não lidas.",
                    bell, "right",
                ),
            ]

        if role == "gerente":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                TourStep(
                    "Nova Requisição",
                    "Crie requisições para qualquer vendedor da equipe. "
                    "Como gerente, você tem acesso a <b>todos os pedidos</b>.",
                    nav("nova"), "right", "nova",
                ),
                TourStep(
                    "Número do PED",
                    "Digite o número do pedido gerado no sistema de vendas. "
                    "Campo <b>obrigatório</b> para salvar.",
                    form("input_ped"), "bottom",
                ),
                TourStep(
                    "Busca de Cliente",
                    "Pesquise pelo nome, CNPJ ou código do cliente. "
                    "O sistema busca nos <b>+112 mil cadastros</b> enquanto você digita.",
                    form("client_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Itens",
                    "Adicione os itens da requisição. "
                    "Pressione <b>Enter</b> para confirmar cada linha e avançar.",
                    form("item_table"), "top",
                ),
                TourStep(
                    "Prazo de Entrega",
                    "Defina a data de entrega. "
                    "Pedidos vencidos aparecem em destaque no dashboard.",
                    form("input_prazo"), "bottom",
                ),
                TourStep(
                    "Editor de Desenho",
                    "Desenhe croquis e cotas diretamente na requisição. "
                    "O desenho é incluído no PDF final.",
                    form("canvas_preview"), "top",
                ),
                TourStep(
                    "Salvar / Imprimir",
                    "Salvar registra a requisição e envia o PDF para a pasta "
                    "de rede do vendedor responsável.",
                    form("btn_save"), "top",
                ),
                # ── Painel Gerencial ──────────────────────────────────────────
                TourStep(
                    "Painel Gerencial",
                    "Indicadores executivos da operação: pedidos em produção, "
                    "atrasos, faturamentos e ritmo diário.",
                    nav("dashboard"), "right", "dashboard",
                ),
                TourStep(
                    "Ranking de Vendedores",
                    "Volume de requisições emitidas por vendedor. "
                    "Identifique quem está mais ativo no período.",
                    dash("vendors_card"), "right",
                ),
                TourStep(
                    "Pedidos sem Confirmação",
                    "Pedidos aguardando retorno da produção há mais de <b>1 hora</b>. "
                    "Acompanhe para evitar atrasos.",
                    dash("alerts_card"), "left",
                ),
                TourStep(
                    "Máquinas em Operação",
                    "Ranking das máquinas da A&R e da Indústria por volume. "
                    "Identifique gargalos operacionais.",
                    dash("machines_ar_card"), "right",
                ),
                TourStep(
                    "Últimas Requisições",
                    "Visão rápida das requisições mais recentes. "
                    "Duplo clique para abrir qualquer uma.",
                    dash("recent_card"), "top",
                ),
                # ── Central de Pedidos ────────────────────────────────────────
                TourStep(
                    "Central de Pedidos",
                    "Todos os pedidos por status operacional. "
                    "Acompanhe do recebimento ao faturamento.",
                    nav("pedidos"), "right", "pedidos",
                ),
                TourStep(
                    "Aguardando Recebimento",
                    "Pedidos enviados para produção aguardando confirmação.",
                    order("_section_cards", "aguardando_recebimento"), "right",
                ),
                TourStep(
                    "Em Produção",
                    "Pedidos já recebidos e em andamento na fábrica.",
                    order("_section_cards", "em_producao"), "left",
                ),
                TourStep(
                    "Pedidos Finalizados",
                    "Histórico de pedidos já finalizados para consulta.",
                    order("_section_cards", "faturados"), "left",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Histórico / Busca",
                    "Acesse qualquer requisição já criada. "
                    "Filtre por status, cliente, data ou PED.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED, nome do cliente ou obra "
                    "para localizar rapidamente qualquer requisição.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar por qualquer coluna. "
                    "Duplo clique na linha para abrir a requisição.",
                    hist("table"), "top",
                ),
                # ── Configurações ─────────────────────────────────────────────
                TourStep(
                    "Configurações",
                    "Ajuste a escala da interface, altere sua senha "
                    "e configure alertas de faturamento.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Aparência",
                    "Ajuste a escala e o tamanho de fonte para sua resolução.",
                    cfg("_tab_btns", 0), "bottom",
                ),
                TourStep(
                    "Conta",
                    "Altere sua senha de acesso. Recomendado trocar periodicamente.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Sistema",
                    "Configure alertas de faturamento e visualize as opções de conexão com o servidor.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                TourStep(
                    "Ajuda",
                    "Verifique atualizações disponíveis e acesse o <b>Guia Rápido</b> novamente.",
                    cfg("_tab_btns", 3), "bottom",
                ),
                TourStep(
                    "Salvar",
                    "Clique em <b>Salvar Configurações</b> para aplicar as mudanças.",
                    cfg("btn_save"), "top",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "Receba alertas em tempo real sobre pedidos, "
                    "produções e faturamentos.",
                    bell, "right",
                ),
            ]

        if role == "vendedor":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                TourStep(
                    "Nova Requisição",
                    "Sua tela principal. Preencha o PED, selecione o cliente, "
                    "adicione os itens e salve. "
                    "O PDF vai automaticamente para a pasta da rede.",
                    nav("nova"), "right", "nova",
                ),
                TourStep(
                    "Número do PED",
                    "Digite o número do pedido gerado no sistema de vendas. "
                    "Campo <b>obrigatório</b> — sem PED não é possível salvar.",
                    form("input_ped"), "bottom",
                ),
                TourStep(
                    "Busca de Cliente",
                    "Pesquise pelo nome, CNPJ ou código do cliente. "
                    "O sistema busca nos <b>+112 mil cadastros</b> em tempo real.",
                    form("client_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Itens",
                    "Adicione cada item: descrição, quantidade e unidade. "
                    "Pressione <b>Enter</b> para confirmar e avançar para o próximo.",
                    form("item_table"), "top",
                ),
                TourStep(
                    "Prazo de Entrega",
                    "Informe a data de entrega combinada com o cliente. "
                    "O setor de produção verá esse prazo.",
                    form("input_prazo"), "bottom",
                ),
                TourStep(
                    "Observações",
                    "Use este campo para instruções especiais de produção, "
                    "detalhes da obra ou qualquer informação adicional.",
                    form("input_obs"), "top",
                ),
                TourStep(
                    "Editor de Desenho",
                    "Clique aqui para desenhar croquis e medidas. "
                    "Ferramentas: caneta, linha, seta, retângulo e cota MM. "
                    "O desenho vai incluído no PDF.",
                    form("canvas_preview"), "top",
                ),
                TourStep(
                    "Salvar",
                    "Clique em <b>Salvar</b> para registrar a requisição. "
                    "O PDF é gerado e enviado para a sua pasta de rede.",
                    form("btn_save"), "top",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Histórico",
                    "Todas as suas requisições ficam aqui. "
                    "Filtre por status ou data e clique duas vezes "
                    "para reabrir qualquer pedido.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Encontre rapidamente uma requisição pelo número do PED, "
                    "nome do cliente ou obra.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique para reabrir e editar a requisição.",
                    hist("table"), "top",
                ),
                # ── Configurações ─────────────────────────────────────────────
                TourStep(
                    "Configurações",
                    "Ajuste a escala da interface e altere sua senha de acesso.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Aparência",
                    "Escolha a escala e o tamanho de fonte "
                    "mais confortáveis para a sua tela.",
                    cfg("_tab_btns", 0), "bottom",
                ),
                TourStep(
                    "Conta",
                    "Altere sua senha de acesso pelo campo <b>Nova Senha</b>.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Ajuda",
                    "Verifique atualizações disponíveis e acesse "
                    "o <b>Guia Rápido</b> novamente a qualquer momento.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "Receba alertas quando sua requisição entrar em produção, "
                    "for finalizada ou faturada.",
                    bell, "right",
                ),
            ]

        if role == "producao":
            return [
                welcome,
                # ── Tela A&R ──────────────────────────────────────────────────
                TourStep(
                    "Fila A&R",
                    "Sua tela principal. Acompanhe todos os pedidos "
                    "enviados para produção na <b>A&R</b>.",
                    nav("ar"), "right", "ar",
                ),
                TourStep(
                    "Contadores de Status",
                    "Totais em tempo real: <b>Aguardando Recebimento</b>, "
                    "<b>Aguardando na Fila</b> e <b>Em Produção</b>.",
                    ar("summary_waiting_receipt", "card"), "bottom",
                ),
                TourStep(
                    "Aguardando Recebimento",
                    "Pedidos enviados pelo vendedor mas ainda não recebidos. "
                    "Selecione um e clique <b>Receber</b> "
                    "para confirmar a chegada do material.",
                    ar("waiting_receipt_panel", "card"), "right",
                ),
                TourStep(
                    "Aguardando na Fila",
                    "Pedidos já recebidos esperando uma máquina ficar livre. "
                    "Selecione e clique <b>Enviar para Máquina</b> "
                    "para iniciar a produção.",
                    ar("waiting_queue_panel", "card"), "left",
                ),
                TourStep(
                    "Máquinas em Produção",
                    "Cada card representa uma máquina ativa com o pedido em andamento. "
                    "Clique no pedido para <b>finalizar</b> ou <b>devolver para a fila</b>.",
                    ar("machines_widget"), "top",
                ),
                TourStep(
                    "Atualizar",
                    "Clique em <b>ATUALIZAR</b> para recarregar todos os pedidos "
                    "e máquinas com os dados mais recentes.",
                    ar("refresh_btn"), "bottom",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Histórico",
                    "Busque qualquer requisição por PED, cliente ou status. "
                    "Clique duas vezes para abrir os detalhes completos.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED ou nome do cliente "
                    "para localizar uma requisição específica.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique para abrir a requisição completa.",
                    hist("table"), "top",
                ),
                # ── Configurações ─────────────────────────────────────────────
                TourStep(
                    "Configurações",
                    "Ajuste a escala da interface e altere sua senha de acesso.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Conta",
                    "Altere sua senha de acesso pelo campo <b>Nova Senha</b>.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Ajuda",
                    "Verifique atualizações disponíveis e acesse "
                    "o <b>Guia Rápido</b> novamente a qualquer momento.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "Receba alertas quando novos pedidos chegarem "
                    "à fila da A&R.",
                    bell, "right",
                ),
            ]

        if role == "industria":
            return [
                welcome,
                # ── Tela Pinheiro Indústria ────────────────────────────────────
                TourStep(
                    "Pinheiro Indústria",
                    "Sua tela principal. Acompanhe todos os pedidos "
                    "destinados à <b>Pinheiro Indústria</b>.",
                    nav("pinheiro_industria"), "right", "pinheiro_industria",
                ),
                TourStep(
                    "Contadores de Status",
                    "Totais em tempo real: <b>Aguardando Recebimento</b>, "
                    "<b>Aguardando na Fila</b> e <b>Em Produção</b>.",
                    pin("summary_waiting_receipt", "card"), "bottom",
                ),
                TourStep(
                    "Aguardando Recebimento",
                    "Pedidos enviados pelo vendedor mas ainda não recebidos. "
                    "Selecione um e clique <b>Receber</b> "
                    "para confirmar a chegada do material.",
                    pin("waiting_receipt_panel", "card"), "right",
                ),
                TourStep(
                    "Aguardando na Fila",
                    "Pedidos recebidos aguardando máquina disponível. "
                    "Selecione e clique <b>Enviar para Máquina</b> "
                    "para iniciar a produção.",
                    pin("waiting_queue_panel", "card"), "left",
                ),
                TourStep(
                    "Máquinas em Produção",
                    "Cada card representa uma máquina ativa. "
                    "Clique no pedido para <b>finalizar</b> "
                    "ou <b>devolver para a fila</b>.",
                    pin("machines_widget"), "top",
                ),
                TourStep(
                    "Atualizar",
                    "Clique em <b>ATUALIZAR</b> para recarregar todos os pedidos "
                    "e máquinas com os dados mais recentes.",
                    pin("refresh_btn"), "bottom",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Histórico",
                    "Busque qualquer requisição por PED, cliente ou status. "
                    "Clique duas vezes para abrir os detalhes completos.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED ou nome do cliente "
                    "para localizar uma requisição específica.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique para abrir a requisição completa.",
                    hist("table"), "top",
                ),
                # ── Configurações ─────────────────────────────────────────────
                TourStep(
                    "Configurações",
                    "Ajuste a escala da interface e altere sua senha de acesso.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Conta",
                    "Altere sua senha de acesso pelo campo <b>Nova Senha</b>.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Ajuda",
                    "Verifique atualizações disponíveis e acesse "
                    "o <b>Guia Rápido</b> novamente a qualquer momento.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "Receba alertas quando novos pedidos chegarem "
                    "à fila da Indústria.",
                    bell, "right",
                ),
            ]

        if role == "entregas":
            return [
                welcome,
                # ── Central de Entregas ───────────────────────────────────────
                TourStep(
                    "Entregas",
                    "Acompanhe os pedidos marcados para entrega, com prazos, "
                    "status e confirmação final da entrega.",
                    nav("entregas"), "right", "entregas",
                ),
                TourStep(
                    "Agenda de Entregas",
                    "Selecione um pedido para alterar o prazo ou registrar "
                    "a conclusão quando ele já estiver finalizado.",
                    delivery("table"), "top",
                ),
                TourStep(
                    "Nova Requisição",
                    "Seu perfil abre a tela de requisição em modo leitura, "
                    "sem permitir edição direta dos dados.",
                    nav("nova"), "right", "nova",
                ),
                TourStep(
                    "Relatórios",
                    "Use os relatórios para consultar requisições e abrir os "
                    "detalhes em modo leitura.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Configurações",
                    "Esse perfil mantém acesso às abas de aparência, conta "
                    "e ajuda/acessibilidade.",
                    nav("config"), "right", "config",
                ),
                TourStep(
                    "Conta",
                    "Altere sua senha de acesso pelo campo <b>Nova Senha</b>.",
                    cfg("_tab_btns", 1), "bottom",
                ),
                TourStep(
                    "Ajuda",
                    "Verifique atualizações disponíveis e acesse "
                    "o <b>Guia Rápido</b> novamente a qualquer momento.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                # ── Notificações ──────────────────────────────────────────────
                TourStep(
                    "Notificações",
                    "Receba alertas quando novos pedidos chegarem "
                    "para entrega.",
                    bell, "right",
                ),
            ]

        # Fallback genérico
        return [
            welcome,
            TourStep(
                "Nova Requisição",
                "Crie e gerencie requisições.",
                nav("nova"), "right", "nova",
            ),
            TourStep(
                "Histórico",
                "Busque e filtre todas as requisições.",
                nav("historico"), "right", "historico",
            ),
            TourStep(
                "Configurações",
                "Personalize a aparência e gerencie sua conta.",
                nav("config"), "right", "config",
            ),
        ]

    def _stop_runtime_services(self):
        if hasattr(self, "_notif_timer") and self._notif_timer is not None:
            self._notif_timer.stop()
        if self._listener:
            self._listener.stop()

    def closeEvent(self, event):
        if self._allow_close_without_prompt:
            super().closeEvent(event)
            return

        should_close = ask_confirmation(
            self,
            "Fechar sistema",
            "Deseja realmente fechar o sistema?",
            yes_text="Sim",
            no_text="Não",
        )
        if not should_close:
            event.ignore()
            return

        self._stop_runtime_services()
        self._allow_close_without_prompt = True
        super().closeEvent(event)
