from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QMessageBox, QFrame, QScrollArea, QLabel, QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect, QPushButton,
)
from PySide6.QtCore import Qt, QTimer, QEasingCurve, QPropertyAnimation, QDate, Signal, QPoint
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
from .system_updates_view import SystemUpdatesDialog
from .user_center_view import UserCenterView
from .feedback_view import FeedbackView


import os
import sys

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


# ── Barra de título customizada ───────────────────────────────────────────────

class _CustomTitleBar(QWidget):
    """Barra de título temática que substitui a barra nativa do Windows.

    Suporta:
    - Arrastar para mover (drag-to-move)
    - Duplo clique para maximizar / restaurar
    - Botões Min / Max / Fechar com hover temático
    - Atualização automática de cores ao trocar o tema
    """

    BORDER_PX = 5  # largura da borda de resize (usada também no nativeEvent)

    def __init__(self, main_window: QWidget, scale: float) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._scale = scale
        self._drag_start: QPoint | None = None
        h = max(30, int(32 * scale))
        self.setFixedHeight(h)
        self._build(scale, h)
        theme.themed(self, self._apply_theme)

    def _build(self, s: float, h: int) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(0)

        self._lbl = QLabel("Requisições App")
        lay.addWidget(self._lbl)
        lay.addStretch()

        bw = max(40, int(46 * s))
        self._btn_min = QPushButton("─")
        self._btn_max = QPushButton("□")
        self._btn_cls = QPushButton("✕")

        self._btn_min.setToolTip("Minimizar")
        self._btn_max.setToolTip("Maximizar")
        self._btn_cls.setToolTip("Fechar")

        for btn in (self._btn_min, self._btn_max, self._btn_cls):
            btn.setFixedSize(bw, h)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(btn)

        self._btn_min.clicked.connect(self._mw.showMinimized)
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_cls.clicked.connect(self._mw.close)

    def _apply_theme(self) -> None:
        s    = self._scale
        fpt  = max(8, int(9 * s))
        bfpt = max(10, int(11 * s))

        if theme.is_dark:
            bg          = theme.SIDEBAR_BG
            fg          = theme.TEXT_WHITE
            hover_ctrl  = "rgba(255,255,255,22)"
        else:
            bg          = theme.CARD_BG
            fg          = "#111111"
            hover_ctrl  = "rgba(0,0,0,10)"

        self.setStyleSheet(f"background:{bg}; border:none;")
        self._lbl.setStyleSheet(
            f"color:{fg}; font-size:{fpt}pt; font-weight:600; background:transparent;"
        )
        _base = (
            f"QPushButton {{ background:transparent; border:none;"
            f"  color:{fg}; font-size:{bfpt}pt; font-weight:400; }}"
        )
        self._btn_min.setStyleSheet(_base + f"QPushButton:hover {{ background:{hover_ctrl}; }}")
        self._btn_max.setStyleSheet(_base + f"QPushButton:hover {{ background:{hover_ctrl}; }}")
        self._btn_cls.setStyleSheet(_base + "QPushButton:hover { background:#C42B1C; color:#FFF; }")

    def _toggle_max(self) -> None:
        if self._mw.isMaximized():
            self._mw.showNormal()
        else:
            self._mw.showMaximized()

    def sync_max_btn(self) -> None:
        """Atualiza ícone/tooltip do botão maximizar ao mudar estado da janela."""
        if self._mw.isMaximized():
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("Restaurar")
        else:
            self._btn_max.setText("□")
            self._btn_max.setToolTip("Maximizar")

    # ── Drag para mover ───────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start is not None
            and not self._mw.isMaximized()
        ):
            delta = event.globalPosition().toPoint() - self._drag_start
            self._mw.move(self._mw.pos() + delta)
            self._drag_start = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)


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
        # Remove barra nativa — usamos _CustomTitleBar no lugar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
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
        self.statusBar().hide()
        self.setWindowTitle("Requisições App")
        # Sombra DWM no Windows (frameless não tem sombra por padrão)
        self._enable_dwm_shadow()
        if res.start_maximized:
            self.showMaximized()
        else:
            width = max(640, int(1280 * self.scale))
            height = max(480, int(800 * self.scale))
            self.resize(width, height)
        self._toast_manager = ToastManager(self)
        self._pending_update_info: dict | None = None
        self._bg_update_checker = None
        self._refresh_session_profile()
        self._start_notification_listener()
        self._navigate_to_home()
        QTimer.singleShot(600, self._maybe_show_onboarding)
        self._start_bg_update_timer()

    def _setup_ui(self):
        self.setStyleSheet(f"background:{theme.CONTENT_BG};")
        central = QWidget()
        self._central = central
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Barra de título customizada
        self._title_bar = _CustomTitleBar(self, self.scale)
        outer.addWidget(self._title_bar)

        # Área de conteúdo principal (sidebar + stack)
        content_widget = QWidget()
        root = QHBoxLayout(content_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addWidget(content_widget, 1)

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
            "atualizacoes":       True,
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

    # ── Janela frameless ──────────────────────────────────────────────────────

    def changeEvent(self, event) -> None:
        """Sincroniza o ícone do botão max/restore ao mudar estado da janela."""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "_title_bar"):
                self._title_bar.sync_max_btn()
        super().changeEvent(event)

    def _enable_dwm_shadow(self) -> None:
        """Habilita sombra DWM para janela frameless no Windows."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            DWMWA_NCRENDERING_POLICY = 2
            hwnd = int(self.winId())
            val = ctypes.c_int(2)  # DWMNCRP_ENABLED
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_NCRENDERING_POLICY,
                ctypes.byref(val), ctypes.sizeof(val),
            )
        except Exception:
            pass

    def nativeEvent(self, event_type: bytes, message) -> tuple:
        """Habilita redimensionamento nativo por bordas no Windows (WM_NCHITTEST)."""
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            try:
                import ctypes
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084 and not self.isMaximized():  # WM_NCHITTEST
                    b = _CustomTitleBar.BORDER_PX
                    lp = msg.lParam
                    cx = ctypes.c_short(lp & 0xFFFF).value
                    cy = ctypes.c_short((lp >> 16) & 0xFFFF).value
                    geo = self.frameGeometry()
                    l = cx <= geo.left()   + b
                    r = cx >= geo.right()  - b
                    t = cy <= geo.top()    + b
                    d = cy >= geo.bottom() - b
                    if t and l: return True, 13  # HTTOPLEFT
                    if t and r: return True, 14  # HTTOPRIGHT
                    if d and l: return True, 16  # HTBOTTOMLEFT
                    if d and r: return True, 17  # HTBOTTOMRIGHT
                    if t:       return True, 12  # HTTOP
                    if d:       return True, 15  # HTBOTTOM
                    if l:       return True, 10  # HTLEFT
                    if r:       return True, 11  # HTRIGHT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

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
        if key == "atualizacoes":
            if self._pending_update_info is not None:
                info = self._pending_update_info
                self._pending_update_info = None
                self.sidebar.set_update_badge(False)
                from ..widgets.update_dialog import UpdateAvailableDialog
                UpdateAvailableDialog(info, parent=self).exec()
            else:
                SystemUpdatesDialog(parent=self).exec()
            return

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

        # Bloqueia repintura do stack durante toda a operação de troca:
        # sem isso, o widget filho recém-criado (parent=self.stack) fica
        # brevemente visível em (0,0) antes de insertWidget ocultá-lo,
        # causando um flash de janelinha no Windows.
        self.stack.setUpdatesEnabled(False)
        try:
            view = self._create_view_for_page(page)
            setattr(self, attr, view)

            # Troca o placeholder pela view real mantendo o índice correto
            placeholder = self.stack.widget(page)
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self.stack.insertWidget(page, view)
        finally:
            self.stack.setUpdatesEnabled(True)

        self._connect_view_signals(page, view)

    def _create_view_for_page(self, page: int):
        """Instancia a view correspondente ao índice ``page``."""
        # parent=self.stack evita que a view seja criada como janela top-level no
        # Windows — sem parent o Qt cria um HWND independente que pisca brevemente
        # antes do insertWidget reparenteá-la para dentro do stack.
        if page == PAGE_HISTORY:
            return HistoryView(self.scale, parent=self.stack)
        if page == PAGE_DASHBOARD:
            return DashboardView(self.scale, parent=self.stack)
        if page == PAGE_TECHNICAL:
            return TechnicalPanelView(self.scale, parent=self.stack)
        if page == PAGE_ORDER_CENTER:
            return OrderCenterView(self.scale, parent=self.stack)
        if page == PAGE_DELIVERY_CENTER:
            return DeliveryCenterView(self.scale, parent=self.stack)
        if page == PAGE_PINHEIRO_INDUSTRIA:
            return ProductionView(
                self.scale,
                destinations=("Pinheiro Indústria",),
                title="PINHEIRO INDÚSTRIA",
                subtitle="Acompanhamento operacional das requisições enviadas para a Pinheiro Indústria.",
                parent=self.stack,
            )
        if page == PAGE_AR:
            return ProductionView(
                self.scale,
                destinations=("A&R",),
                title="A&R",
                subtitle="Acompanhamento operacional das requisições enviadas para a A&R.",
                parent=self.stack,
            )
        if page == PAGE_USER_CENTER:
            return UserCenterView(self.scale, parent=self.stack)
        if page == PAGE_SETTINGS:
            return SettingsView(self.scale, parent=self.stack)
        if page == PAGE_FEEDBACK:
            return FeedbackView(self.scale, parent=self.stack)
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

    # ── Verificação periódica de atualizações ────────────────────────────────

    def _start_bg_update_timer(self) -> None:
        """Timer que verifica novas versões a cada 3 horas em segundo plano."""
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(3 * 60 * 60 * 1000)
        self._update_timer.timeout.connect(self._run_bg_update_check)
        self._update_timer.start()

    def _run_bg_update_check(self) -> None:
        """Dispara UpdateChecker em background. Ignora se já há check em andamento
        ou se já existe uma atualização pendente aguardando o usuário."""
        if self._pending_update_info is not None:
            return
        if self._bg_update_checker is not None and self._bg_update_checker.isRunning():
            return
        from ..updater import UpdateChecker
        self._bg_update_checker = UpdateChecker(parent=self)
        self._bg_update_checker.update_available.connect(self._on_bg_update_found)
        self._bg_update_checker.start()

    def _on_bg_update_found(self, info: dict) -> None:
        """Nova versão detectada pelo timer periódico: sinaliza via badge + toast."""
        self._pending_update_info = info
        self.sidebar.set_update_badge(True)
        version = info.get("version", "?")
        self._toast_manager.show(
            {
                "type": "update_available",
                "title": f"Nova versão disponível — v{version}",
                "body": "Clique em Atualizações para instalar agora.",
            }
        )

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
        # Abre o drawer imediatamente (vazio) para feedback instantâneo,
        # depois popula quando a rede responder.
        drawer = NotificationDrawer([], self._central)
        drawer.mark_all_requested.connect(self._mark_all_read)
        drawer.open_req_requested.connect(self._open_requisition)
        drawer.mark_one_requested.connect(self._mark_one_read)
        drawer.delete_requested.connect(self._delete_notification)
        drawer.open_drawer()
        self._active_drawer = drawer

        thread, worker = _run_in_thread(
            api.list_notifications,
            on_result=self._populate_notification_drawer,
            on_error=lambda msg: None,
        )
        self._track_thread(thread, worker)

    def _populate_notification_drawer(self, notifications: list):
        drawer = getattr(self, "_active_drawer", None)
        if drawer is None:
            return
        drawer.populate(notifications)

    def _mark_all_read(self):
        # Interrompe na hora os pop-ups das não lidas que ainda estavam
        # enfileirados — o usuário pediu para parar de subir ao marcar todas.
        self._toast_manager.clear()
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

    def _delete_notification(self, notif_id: int):
        thread, worker = _run_in_thread(
            api.delete_notification,
            notif_id,
            on_result=lambda _: self._sync_badge(),
            on_error=lambda _: None,
        )
        self._track_thread(thread, worker)

    def _reset_badge(self):
        self._unread_count = 0
        # Não limpa _shown_notif_ids: evita re-pop de notificações já exibidas
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
            return lambda: mw.sidebar._nav_btns.get(key)

        def bell():
            return mw.sidebar._bell

        def form(attr):
            return lambda: getattr(mw.form_view, attr, None)

        def hist(attr):
            return lambda: getattr(mw.history_view, attr, None) if mw.history_view else None

        def ar(attr, key=None):
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
            return lambda: getattr(mw.delivery_center_view, attr, None) if mw.delivery_center_view else None

        def dash(attr):
            return lambda: getattr(mw.dashboard_view, attr, None) if mw.dashboard_view else None

        def cfg(attr, idx=None):
            def _get():
                view = mw.settings_view
                if view is None:
                    return None
                val = getattr(view, attr, None)
                if idx is not None and isinstance(val, list):
                    return val[idx] if len(val) > idx else None
                return val
            return _get

        def fb(attr):
            return lambda: getattr(mw.feedback_view, attr, None) if mw.feedback_view else None

        # ── Passo de boas-vindas ──────────────────────────────────────────────
        welcome = TourStep(
            title="Bem-vindo ao Sistema de Requisições!",
            body=(
                "Este tour apresenta <b>todas as funcionalidades</b> disponíveis para o seu perfil, "
                "tela por tela, passo a passo.<br><br>"
                "Clique em <b>Próximo</b> para começar, ou "
                "<b>Pular tour</b> para ir direto ao sistema.<br><br>"
                "Você pode rever este guia a qualquer momento em "
                "<b>Configurações → Ajuda e Acessibilidade</b>."
            ),
            tooltip_side="center",
        )

        # ── Blocos reutilizáveis ──────────────────────────────────────────────

        steps_nova = [
            TourStep(
                "Nova Requisição",
                "Tela central do sistema — onde toda requisição de compra nasce. "
                "Preencha o PED, selecione o cliente, adicione os itens, defina o prazo "
                "e salve. O <b>PDF é gerado automaticamente</b> na pasta de rede.",
                nav("nova"), "right", "nova",
            ),
            TourStep(
                "Número do PED — Criar ou Buscar",
                "Campo obrigatório. Digite apenas o número (somente dígitos) do pedido.<br><br>"
                "<b>PED já existente:</b> o sistema localiza e abre automaticamente a requisição "
                "para edição — funciona como <b>busca direta</b> sem precisar ir ao Histórico.<br>"
                "<b>PED novo:</b> um formulário em branco é criado para preenchimento.<br><br>"
                "O cursor é posicionado aqui automaticamente ao abrir a tela. "
                "Se quiser verificar um pedido já feito, basta digitar o PED aqui.",
                form("input_ped"), "bottom",
            ),
            TourStep(
                "Lupa 🔍 — Busca de Requisições",
                "Botão ao lado do formulário que abre a <b>janela de busca completa</b>. "
                "Use quando não sabe o número do PED ou quer localizar um pedido "
                "pelo nome do cliente, pela obra ou por qualquer outra informação.<br><br>"
                "<b>Clique no botão agora</b> para explorar o diálogo — "
                "você pode continuar o tour depois, clicando em Próximo.",
                form("btn_search_req"), "left", None, 12,
            ),
            TourStep(
                "Lupa 🔍 — Filtros Disponíveis",
                "Dentro do diálogo de busca você pode filtrar por:<br><br>"
                "• <b>PED</b> — número do pedido<br>"
                "• <b>Cliente</b> — nome ou CNPJ<br>"
                "• <b>Obra</b> — nome da obra vinculada<br>"
                "• <b>Vendedor</b> — nome ou código<br>"
                "• <b>Status</b> e <b>período de emissão</b><br><br>"
                "Clique em qualquer linha do resultado para abrir a requisição "
                "diretamente no formulário.",
                form("btn_search_req"), "left", None, 12,
            ),
            TourStep(
                "Busca de Cliente",
                "Pesquise por <b>nome</b>, <b>código</b> ou <b>CNPJ</b> do cliente. "
                "A lista filtra nos +112 mil cadastros em tempo real enquanto você digita.<br><br>"
                "Selecione o cliente na lista suspensa para vinculá-lo ao pedido. "
                "Campo obrigatório para salvar.",
                form("client_search"), "bottom",
            ),
            TourStep(
                "Nome da Obra",
                "Identifica o projeto ou obra vinculada a esta requisição. "
                "Aparece no PDF e pode ser usado como filtro nos Relatórios.<br><br>"
                "Exemplo: <i>OBRA RUA DAS FLORES 123</i> ou <i>REFORMA LOJA CENTRO</i>.",
                form("input_obra"), "bottom",
            ),
            TourStep(
                "Tabela de Itens",
                "Adicione os materiais da requisição. Cada linha tem: "
                "<b>posição</b>, código do produto, descrição, quantidade e peso.<br><br>"
                "Pressione <b>Enter</b> para confirmar cada linha e avançar para a próxima. "
                "O peso total é somado automaticamente.",
                form("item_table"), "top",
            ),
            TourStep(
                "Prazo de Entrega",
                "Data de entrega acordada com o cliente. "
                "O sistema bloqueia datas abaixo do <b>prazo mínimo</b> "
                "configurado em Configurações → Sistema.<br><br>"
                "Pedidos com prazo vencido aparecem em <b>vermelho</b> "
                "no Painel Gerencial e na Central de Pedidos.",
                form("input_prazo"), "bottom",
            ),
            TourStep(
                "Tipo de Entrega — Retirada",
                "Marque quando o cliente virá buscar o pedido no balcão. "
                "Ao marcar, o campo de endereço fica oculto.",
                form("chk_retirada"), "right",
            ),
            TourStep(
                "Tipo de Entrega — Entrega",
                "Marque quando o pedido será levado à obra pela logística. "
                "Ao marcar, o campo de <b>endereço</b> torna-se obrigatório "
                "e o pedido aparece na tela <b>Entregas</b> para a equipe responsável.",
                form("chk_entrega"), "right",
            ),
            TourStep(
                "Endereço de Entrega",
                "Endereço completo para o motorista. Obrigatório quando 'Entrega' está marcado.<br><br>"
                "Inclua rua, número, bairro e cidade para evitar erros de rota.",
                form("input_address"), "bottom",
            ),
            TourStep(
                "Telefone de Contato",
                "Telefone do responsável na obra. "
                "Usado pela logística para confirmar horário de entrega.",
                form("input_fone"), "bottom",
            ),
            TourStep(
                "Observações",
                "Instruções especiais de fabricação, detalhes técnicos ou "
                "informações adicionais para a produção.<br><br>"
                "Aparecem em destaque no PDF. Use para informar materiais específicos, "
                "tratamentos superficiais ou atenções do cliente.",
                form("input_obs"), "top",
            ),
            TourStep(
                "Editor de Desenho",
                "Clique para abrir o editor de croquis integrado. "
                "Ferramentas disponíveis: <b>caneta livre</b>, <b>linha</b>, "
                "<b>seta</b>, <b>retângulo</b>, <b>cota em MM</b> e <b>texto</b>.<br><br>"
                "O desenho é exportado diretamente no PDF. Use para cotas de dobra, "
                "medidas especiais ou esquemas técnicos.",
                form("btn_canvas"), "top",
            ),
            TourStep(
                "Assinatura Digital",
                "Captura a assinatura do responsável pelo pedido diretamente na tela. "
                "A imagem é incluída no PDF final, "
                "servindo como confirmação formal do pedido.",
                form("btn_sign"), "top",
            ),
            TourStep(
                "Salvar Requisição",
                "Registra a requisição no banco de dados e <b>gera o PDF automaticamente</b> "
                "na pasta de rede configurada. Atalho: <b>Ctrl+S</b>.<br><br>"
                "Uma requisição salva fica em status <i>Rascunho</i> — para enviá-la "
                "à produção, use o botão <b>Enviar para Produção</b>.",
                form("btn_save"), "top",
            ),
            TourStep(
                "Enviar para Produção",
                "Move o pedido para a fila de produção "
                "(<b>A&R</b> ou <b>Pinheiro Indústria</b>, conforme destino). "
                "Só fica ativo <b>após salvar</b>.<br><br>"
                "Ao clicar, o status muda para <i>Aguardando Recebimento</i> "
                "e a produção recebe notificação automática.",
                form("btn_production"), "top",
            ),
            TourStep(
                "Imprimir PDF",
                "Abre o PDF gerado para visualização ou impressão. "
                "Útil para enviar por WhatsApp ou imprimir uma via física. "
                "Se o PDF ainda não existe, ele é criado antes de abrir.",
                form("btn_print"), "top",
            ),
        ]

        steps_hist = [
            TourStep(
                "Relatórios / Histórico",
                "Acesse <b>qualquer requisição</b> já criada no sistema. "
                "Filtre por status, vendedor, cliente, data ou PED. "
                "Duplo clique em uma linha para abrir a requisição completa.",
                nav("historico"), "right", "historico",
            ),
            TourStep(
                "Campo de Busca",
                "Pesquise por <b>número do PED</b>, nome do cliente ou nome da obra. "
                "Combine com os filtros de status e período (data inicial / final) "
                "para resultados mais precisos. "
                "Pressione <b>Enter</b> ou aguarde 1 segundo para iniciar a busca.",
                hist("input_search"), "bottom",
            ),
            TourStep(
                "Tabela de Resultados",
                "Clique no cabeçalho de qualquer coluna para ordenar os resultados. "
                "Linhas em <b>vermelho</b> indicam requisições com prazo vencido. "
                "Duplo clique em uma linha para abrir a requisição completa.",
                hist("table"), "top",
            ),
            TourStep(
                "Exportar Excel",
                "Exporta todas as linhas visíveis para uma planilha Excel.<br><br>"
                "<b>Atenção:</b> aplique os filtros desejados antes de exportar — "
                "a exportação reflete exatamente o que está na tela (máximo 300 linhas). "
                "Para relatórios maiores, reduza o período de busca.",
                hist("export_btn"), "bottom",
            ),
        ]

        # ── Central de Pedidos ──────────────────────────────────────────────────
        steps_pedidos = [
            TourStep(
                "Central de Pedidos",
                "Acompanhe todos os pedidos em andamento organizados por status. "
                "Cada seção agrupa pedidos por fase do fluxo de produção: "
                "recebimento, produção, finalização, cancelados e atrasados.",
                nav("pedidos"), "right", "pedidos",
            ),
            TourStep(
                "Filtros de Seção — Chips",
                "Cada chip ativa ou desativa a exibição de uma seção inteira da Central. "
                "Clique nos chips para mostrar apenas as fases que deseja acompanhar: "
                "<b>Aguardando Recebimento</b>, <b>Em Produção</b>, <b>Finalizados</b>, "
                "<b>Cancelados</b> ou <b>Atrasados</b>.<br><br>"
                "Útil para focar em uma fase específica do fluxo sem distrações.",
                order("_filter_chips", "aguardando_recebimento"), "bottom",
            ),
            TourStep(
                "Aplicar / Redefinir Filtro",
                "<b>APLICAR:</b> exibe somente as seções com chips marcados — "
                "as demais ficam ocultas.<br>"
                "<b>TODOS:</b> reativa todas as seções de uma vez, "
                "voltando à visão completa do fluxo.",
                order("_btn_apply_filter"), "bottom",
            ),
            TourStep(
                "Aguardando Recebimento",
                "Pedidos já enviados para produção mas <b>ainda não confirmados</b>. "
                "Exibe PED, cliente, vendedor, peso, destino e horário do envio.<br><br>"
                "Duplo clique para abrir a requisição e ver todos os detalhes.",
                order("_section_cards", "aguardando_recebimento"), "right",
            ),
            TourStep(
                "Em Produção",
                "Pedidos recebidos e atualmente sendo fabricados. "
                "Exibe a máquina alocada, o destino (A&R ou Indústria) e o prazo.<br><br>"
                "Acompanhe o andamento e identifique pedidos parados há muito tempo.",
                order("_section_cards", "em_producao"), "left",
            ),
            TourStep(
                "Finalizados",
                "Pedidos concluídos pela produção. "
                "Disponíveis para consulta e reimpressão de PDF.<br><br>"
                "Inclui pedidos com status <i>Finalizado</i>, <i>Faturado</i> "
                "e <i>Aguardando Faturamento</i>.",
                order("_section_cards", "faturados"), "left",
            ),
            TourStep(
                "Cancelados",
                "Pedidos cancelados em qualquer fase do fluxo. "
                "Exibe o motivo do cancelamento e quem cancelou.<br><br>"
                "Útil para auditoria e para entender o padrão de cancelamentos da equipe.",
                order("_section_cards", "cancelados"), "left",
            ),
            TourStep(
                "Atrasados",
                "Pedidos ainda em aberto com prazo de entrega <b>já vencido</b>. "
                "Destacados em vermelho para facilitar a identificação urgente.<br><br>"
                "Tome ação imediata: acione a produção ou comunique o cliente.",
                order("_section_cards", "atrasados"), "left",
            ),
        ]

        # ── A&R ────────────────────────────────────────────────────────────────
        steps_ar = [
            TourStep(
                "Tela A&R — Sua Tela Principal",
                "Painel operacional da A&R. "
                "Aqui você recebe pedidos, gerencia a fila de cada máquina "
                "e registra as finalizações de produção.",
                nav("ar"), "right", "ar",
            ),
            TourStep(
                "Contadores em Tempo Real",
                "Totalizadores no topo: "
                "<b>Aguardando Recebimento</b> — pedidos enviados ainda não confirmados, e "
                "<b>Em Produção</b> — pedidos ativos nas máquinas agora.<br><br>"
                "Os números atualizam a cada clique em <b>ATUALIZAR</b>.",
                ar("summary_waiting_receipt", "card"), "bottom",
            ),
            TourStep(
                "Painel — Aguardando Recebimento",
                "Lista os pedidos enviados pelo vendedor que <b>ainda não foram confirmados</b> "
                "fisicamente na A&R.<br><br>"
                "Para confirmar: selecione o pedido na tabela e clique em <b>'Receber'</b>. "
                "O pedido entra na fila da máquina selecionada e o vendedor é notificado "
                "automaticamente.",
                ar("waiting_receipt_panel", "card"), "right",
            ),
            TourStep(
                "Seletor de Máquina",
                "Este dropdown é o <b>ponto central de operação</b> da tela. "
                "Selecione aqui a máquina que quer visualizar ou operar.<br><br>"
                "Cada opção no dropdown mostra:<br>"
                "• <b>Nome da máquina</b><br>"
                "• <b>Quantidade em produção</b> no momento<br>"
                "• <b>Quantidade na fila</b> aguardando<br><br>"
                "Troque a máquina selecionada a qualquer momento — "
                "o painel de conteúdo abaixo atualiza instantaneamente "
                "sem recarregar a tela inteira.",
                ar("_machine_combo"), "bottom", None, 36,
            ),
            TourStep(
                "Status da Máquina",
                "Pill ao lado do seletor que indica o estado operacional da máquina escolhida:<br><br>"
                "🟢 <b>Funcionando</b> — máquina disponível para receber pedidos<br>"
                "🔴 <b>Manutenção</b> — máquina indisponível; pedidos não podem ser alocados a ela<br><br>"
                "O status é definido pelo administrador em "
                "<b>Configurações → Cadastro de Máquinas</b>.",
                ar("_machine_status_pill"), "bottom", None, 24,
            ),
            TourStep(
                "Painel da Máquina — Fila e Em Produção",
                "Painel da máquina selecionada com duas seções integradas:<br>"
                "• <b>Fila da Máquina:</b> pedidos aguardando iniciar nesta máquina. "
                "Selecione um e clique <b>'Iniciar'</b> para mover para Em Produção.<br>"
                "• <b>Em Produção:</b> pedidos rodando agora nesta máquina. "
                "Selecione e clique <b>'Finalizar'</b> para concluir ou "
                "<b>'Devolver'</b> para retornar à fila.<br><br>"
                "Cada linha exibe PED, cliente, peso, prazo e tempo decorrido em produção.",
                ar("_machine_content_frame"), "top",
            ),
            TourStep(
                "Atualizar",
                "Recarrega todos os pedidos e o status de todas as máquinas "
                "com dados atualizados do servidor. "
                "Use sempre que outro operador fizer uma alteração que você ainda não vê na tela.",
                ar("refresh_btn"), "bottom",
            ),
        ]

        # ── Pinheiro Indústria ──────────────────────────────────────────────────
        steps_pin = [
            TourStep(
                "Pinheiro Indústria — Sua Tela Principal",
                "Painel operacional da Pinheiro Indústria. "
                "Mesma estrutura da A&R: receba pedidos, gerencie a fila "
                "por máquina e registre as finalizações.",
                nav("pinheiro_industria"), "right", "pinheiro_industria",
            ),
            TourStep(
                "Contadores em Tempo Real",
                "Totalizadores: "
                "<b>Aguardando Recebimento</b> e <b>Em Produção</b> na Pinheiro Indústria.<br><br>"
                "Atualizam a cada clique em <b>ATUALIZAR</b>.",
                pin("summary_waiting_receipt", "card"), "bottom",
            ),
            TourStep(
                "Painel — Aguardando Recebimento",
                "Lista os pedidos enviados pelo vendedor que <b>ainda não foram confirmados</b> "
                "fisicamente na Indústria.<br><br>"
                "Selecione o pedido na tabela e clique em <b>'Receber'</b> para confirmar. "
                "O pedido entra na fila da máquina selecionada e o vendedor é notificado.",
                pin("waiting_receipt_panel", "card"), "right",
            ),
            TourStep(
                "Seletor de Máquina",
                "Este dropdown é o <b>ponto central de operação</b> da tela. "
                "Selecione aqui a máquina da Indústria que quer visualizar ou operar.<br><br>"
                "Cada opção mostra nome da máquina, "
                "<b>quantidade em produção</b> e <b>quantidade na fila</b>. "
                "Troque a qualquer momento — o painel abaixo atualiza instantaneamente.",
                pin("_machine_combo"), "bottom", None, 36,
            ),
            TourStep(
                "Status da Máquina",
                "Pill ao lado do seletor com o estado operacional da máquina escolhida:<br><br>"
                "🟢 <b>Funcionando</b> — disponível para receber pedidos<br>"
                "🔴 <b>Manutenção</b> — indisponível; pedidos não podem ser alocados<br><br>"
                "Status definido pelo administrador em <b>Configurações → Cadastro de Máquinas</b>.",
                pin("_machine_status_pill"), "bottom", None, 24,
            ),
            TourStep(
                "Painel da Máquina — Fila e Em Produção",
                "Painel da máquina selecionada com as mesmas seções da A&R:<br>"
                "• <b>Fila:</b> pedidos aguardando iniciar — selecione e clique <b>'Iniciar'</b>.<br>"
                "• <b>Em Produção:</b> pedidos ativos — <b>'Finalizar'</b> ou <b>'Devolver'</b>.",
                pin("_machine_content_frame"), "top",
            ),
            TourStep(
                "Atualizar",
                "Recarrega pedidos e máquinas da Pinheiro Indústria com dados atualizados.",
                pin("refresh_btn"), "bottom",
            ),
        ]

        # ── Feedbacks ───────────────────────────────────────────────────────────
        steps_feedback_base = [
            TourStep(
                "Feedbacks",
                "Tela para reportar problemas, sugestões e elogios sobre o sistema. "
                "Todos os usuários podem enviar feedbacks e visualizar os públicos.<br><br>"
                "Use para comunicar bugs, solicitar melhorias ou "
                "registrar elogios ao sistema.",
                nav("feedback"), "right", "feedback",
            ),
            TourStep(
                "Escrever Feedback",
                "Caixa de composição no topo da tela. "
                "Selecione a categoria, defina a visibilidade e escreva a mensagem.<br><br>"
                "Seja específico: informe em qual tela o problema ocorreu, "
                "o que você tentou fazer e o que aconteceu ao invés.",
                fb("compose_card"), "top",
            ),
            TourStep(
                "Categoria do Feedback",
                "Classifique o feedback antes de enviar:<br>"
                "🐛 <b>Bug</b> — algo que não funciona como deveria<br>"
                "⚠️ <b>Problema</b> — dificuldade de uso ou comportamento inesperado<br>"
                "💡 <b>Sugestão</b> — ideia de melhoria ou nova funcionalidade<br>"
                "👍 <b>Elogio</b> — algo que funcionou bem e merece reconhecimento",
                fb("combo_category"), "bottom",
            ),
            TourStep(
                "Tornar Público",
                "Quando marcado, todos os usuários verão o feedback na aba <b>Públicos</b>. "
                "Quando desmarcado, apenas o administrador tem acesso (via Caixa de Entrada).<br><br>"
                "Use feedbacks privados para reportar situações sensíveis ou específicas.",
                fb("chk_public"), "bottom",
            ),
            TourStep(
                "Campo de Texto",
                "Descreva o feedback com o máximo de detalhes possível "
                "(limite: 1000 caracteres).<br><br>"
                "O contador no canto inferior esquerdo mostra quantos caracteres já foram usados. "
                "O sistema bloqueia o envio se o campo estiver vazio.",
                fb("input_feedback"), "top",
            ),
            TourStep(
                "Enviar Feedback",
                "Clique em <b>ENVIAR</b> para registrar o feedback. "
                "O administrador é notificado automaticamente sobre novos feedbacks.<br><br>"
                "Após o envio, o campo é limpo e o feedback aparece em <b>Meus feedbacks</b>.",
                fb("btn_send"), "bottom",
            ),
            TourStep(
                "Aba — Públicos",
                "Exibe todos os feedbacks marcados como públicos por qualquer usuário. "
                "Consulte antes de enviar para evitar enviar um feedback duplicado "
                "e acompanhe o andamento de solicitações que você também tem interesse.",
                fb("btn_tab_public"), "bottom",
            ),
            TourStep(
                "Aba — Meus Feedbacks",
                "Lista somente os feedbacks que você enviou. "
                "Acompanhe o status de cada um: "
                "<b>Nova</b>, <b>Em análise</b>, <b>Resolvida</b> ou <b>Descartada</b>.",
                fb("btn_tab_mine"), "bottom",
            ),
        ]

        steps_feedback_admin_extra = [
            TourStep(
                "Aba — Caixa de Entrada (Admin)",
                "Exibe todos os feedbacks recebidos, públicos e privados, em ordem de chegada. "
                "Clique em qualquer card para selecioná-lo e usar as ações da barra inferior.<br><br>"
                "Use os chips abaixo das abas para filtrar por categoria e status.",
                fb("btn_tab_inbox"), "bottom",
            ),
            TourStep(
                "Filtros por Categoria e Status",
                "Chips de filtro visíveis na Caixa de Entrada:<br>"
                "• <b>CATEGORIA:</b> Bug, Problema, Sugestão, Elogio<br>"
                "• <b>STATUS:</b> Nova, Em análise, Resolvida, Descartada<br><br>"
                "Combine os dois filtros para focar nos feedbacks mais relevantes.",
                fb("chips_container"), "bottom",
            ),
            TourStep(
                "Alterar Status do Feedback (Admin)",
                "Com um feedback selecionado na lista, use esta barra para "
                "atualizar o status e comunicar ao usuário o andamento:<br>"
                "• <b>Em análise</b> — sendo investigado<br>"
                "• <b>Resolvida</b> — corrigido ou implementado<br>"
                "• <b>Descartada</b> — fora do escopo ou inválido",
                fb("action_bar"), "bottom",
            ),
        ]

        # ── Configurações base ──────────────────────────────────────────────────
        steps_cfg_base = [
            TourStep(
                "Configurações",
                "Ajuste a aparência, gerencie sua conta e acesse as opções do sistema.",
                nav("config"), "right", "config",
            ),
            TourStep(
                "Aba — Ajuda e Acessibilidade",
                "Ajuste a <b>escala visual</b> (tamanho geral da interface de 60% a 175%), "
                "o <b>tamanho da fonte</b> e o <b>tamanho dos pop-ups de notificação</b>.<br><br>"
                "Inclui o botão <b>'Ver Guia Rápido'</b> para rever este tour a qualquer momento "
                "e a opção de modo escuro.",
                cfg("_tab_btns", 0), "bottom",
            ),
            TourStep(
                "Aba — Conta",
                "Altere sua senha de acesso: informe a <b>senha atual</b>, "
                "a <b>nova senha</b> (mínimo 6 caracteres) e confirme.<br><br>"
                "Recomenda-se trocar periodicamente por segurança. "
                "Se esquecer a senha, contate o administrador.",
                cfg("_tab_btns", 1), "bottom",
            ),
        ]

        step_cfg_save = TourStep(
            "Salvar Configurações",
            "Aplica e persiste todas as alterações feitas em qualquer aba. "
            "<b>Lembre-se de clicar aqui</b> antes de sair da tela de configurações.",
            cfg("btn_save"), "top",
        )

        # ── Notificações ─────────────────────────────────────────────────────────
        step_notif = TourStep(
            "Notificações em Tempo Real",
            "O <b>sino</b> no menu lateral recebe alertas automáticos do servidor "
            "conforme os eventos acontecem — sem precisar recarregar nenhuma tela.<br><br>"
            "Tipos de alerta: pedido enviado à produção, recebido, finalizado, "
            "prazo de entrega alterado, faturamento pendente, backup com erro.<br><br>"
            "Um <b>badge vermelho</b> exibe a quantidade de alertas não lidos. "
            "Clique no sino para abrir o painel lateral e ver o histórico. "
            "Clique em <b>'Marcar todas como lidas'</b> para limpar o badge. "
            "Cada notificação pode ser clicada para navegar direto ao pedido correspondente.",
            bell, "right",
        )

        # ── Atualizações ─────────────────────────────────────────────────────────
        step_update = TourStep(
            "Atualizações do Sistema",
            "Quando uma nova versão estiver disponível, o sistema avisa automaticamente. "
            "Clique neste botão para <b>verificar manualmente</b> — uma janela abrirá com "
            "a versão instalada e um botão de verificação.<br><br>"
            "O processo é automático: o sistema fecha, aplica a atualização e reabre na nova versão. "
            "Suas configurações e dados são preservados entre versões.",
            nav("atualizacoes"), "right",
        )

        # ════════════════════════════════════════════════════════════════════════
        # Admin
        # ════════════════════════════════════════════════════════════════════════
        if role == "admin":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                *steps_nova,
                # ── Painel Gerencial ──────────────────────────────────────────
                TourStep(
                    "Painel Gerencial",
                    "Visão executiva da operação com indicadores-chave, "
                    "alertas e gráficos comparativos. "
                    "Clique em <b>ATUALIZAR</b> para recarregar todos os dados.",
                    nav("dashboard"), "right", "dashboard",
                ),
                TourStep(
                    "IAR Geral — Índice de Aproveitamento",
                    "Indicador principal: porcentagem de requisições que chegaram "
                    "à produção em relação ao total emitido no período.<br><br>"
                    "Inclui filtro de datas para analisar períodos específicos. "
                    "Um IAR baixo pode indicar cancelamentos excessivos ou "
                    "pedidos travados antes de chegar à produção.",
                    dash("iar_card"), "bottom",
                ),
                TourStep(
                    "Métricas Operacionais",
                    "8 indicadores atualizados a cada refresh:<br>"
                    "• <b>Pedidos em Produção</b> e <b>em Atraso</b><br>"
                    "• <b>Finalizados Hoje</b> e <b>Requisições do Dia</b><br>"
                    "• <b>Produção A&R</b> e <b>Pinheiro Indústria</b> (filas ativas)<br>"
                    "• <b>Sem Confirmação há +1h</b> — alerta de ação imediata<br>"
                    "• <b>Tempo Médio de Finalização</b> — referência de desempenho",
                    dash("radar_multi_panel_card"), "top",
                ),
                TourStep(
                    "Radar Comparativo e Filtros Avançados",
                    "Gráficos de radar comparativos e filtros no painel inferior:<br>"
                    "• <b>Período:</b> semanal, mensal, trimestral ou intervalo personalizado<br>"
                    "• <b>Destino:</b> A&R, Pinheiro Indústria ou Todos<br>"
                    "• <b>Radar por máquina</b> — compare desempenho entre equipamentos<br><br>"
                    "Use para identificar gargalos e tomar decisões operacionais embasadas.",
                    dash("radar_multi_panel_card"), "left",
                ),
                # ── Central de Pedidos ────────────────────────────────────────
                *steps_pedidos,
                # ── A&R ───────────────────────────────────────────────────────
                *steps_ar,
                # ── Pinheiro Indústria ────────────────────────────────────────
                *steps_pin,
                # ── Entregas ──────────────────────────────────────────────────
                TourStep(
                    "Tela de Entregas",
                    "Agenda logística: todos os pedidos marcados com 'Entrega' "
                    "prontos para sair. "
                    "A equipe de logística gerencia prazos e confirma as entregas aqui.",
                    nav("entregas"), "right", "entregas",
                ),
                TourStep(
                    "Vista Lista / Cronograma",
                    "<b>Lista:</b> todos os pedidos pendentes em ordem de prazo.<br>"
                    "<b>Cronograma:</b> visão calendário organizada por data de entrega.",
                    delivery("_btn_view_list"), "bottom",
                ),
                TourStep(
                    "Tabela e Ações de Entrega",
                    "Selecione pedidos para acionar as ações:<br>"
                    "<b>Alterar Prazo</b> — nova data com motivo obrigatório (vendedor notificado)<br>"
                    "<b>Marcar Entregue</b> — registra a entrega e finaliza o pedido<br>"
                    "<b>Cancelar Entrega</b> — reverte uma entrega confirmada por engano",
                    delivery("table"), "top",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                *steps_hist,
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                *steps_feedback_admin_extra,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                TourStep(
                    "Aba — Sistema",
                    "Configure a <b>URL do servidor</b> e teste a conexão com o backend. "
                    "Ajuste o <b>prazo mínimo de entrega</b>, "
                    "os <b>alertas de faturamento</b> e os <b>motivos de cancelamento</b>.<br><br>"
                    "O <b>Painel Técnico</b> monitora em tempo real: "
                    "conexões ativas, tempo de resposta e histórico de erros do servidor.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                TourStep(
                    "Aba — Backup",
                    "Configure o <b>backup automático</b> do banco PostgreSQL: "
                    "horário diário e períodos de retenção (diário, semanal e mensal).<br><br>"
                    "Clique em <b>'Executar Agora'</b> para forçar um backup imediato.",
                    cfg("_tab_btns", 3), "bottom",
                ),
                TourStep(
                    "Aba — Usuários",
                    "Cadastre, edite e desative usuários. "
                    "Defina o cargo de cada um: Vendedor, Gerente, A&R, Indústria ou Entrega.<br><br>"
                    "Você pode forçar a troca de senha no próximo login "
                    "ao criar ou redefinir o acesso.",
                    cfg("_tab_btns", 4), "bottom",
                ),
                TourStep(
                    "Aba — Clientes",
                    "Cadastre clientes individualmente ou <b>importe em lote</b> por planilha Excel. "
                    "Clientes inativos não aparecem na busca da Nova Requisição.",
                    cfg("_tab_btns", 5), "bottom",
                ),
                TourStep(
                    "Aba — Cadastro de Máquinas",
                    "Gerencie as máquinas disponíveis na A&R e na Pinheiro Indústria. "
                    "Máquinas em manutenção não aparecem como opção no seletor de máquinas.",
                    cfg("_tab_btns", 6), "bottom",
                ),
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # ════════════════════════════════════════════════════════════════════════
        # Gerente
        # ════════════════════════════════════════════════════════════════════════
        if role == "gerente":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                *steps_nova,
                # ── Painel Gerencial ──────────────────────────────────────────
                TourStep(
                    "Painel Gerencial",
                    "Visão executiva da operação com indicadores em tempo real. "
                    "Clique em <b>ATUALIZAR</b> para recarregar os dados.",
                    nav("dashboard"), "right", "dashboard",
                ),
                TourStep(
                    "IAR Geral — Índice de Aproveitamento",
                    "Indicador principal: porcentagem de requisições que chegaram "
                    "à produção em relação ao total emitido no período.<br><br>"
                    "Ajuste as datas do filtro para analisar períodos específicos.",
                    dash("iar_card"), "bottom",
                ),
                TourStep(
                    "Métricas e Radar Comparativo",
                    "8 métricas operacionais: pedidos em produção, em atraso, "
                    "finalizados hoje, requisições do dia, filas A&R e Indústria, "
                    "pedidos sem confirmação há mais de 1h e tempo médio de finalização.<br><br>"
                    "O painel radar compara desempenho entre máquinas e períodos.",
                    dash("radar_multi_panel_card"), "top",
                ),
                # ── Central de Pedidos ────────────────────────────────────────
                *steps_pedidos,
                # ── A&R ───────────────────────────────────────────────────────
                *steps_ar,
                # ── Pinheiro Indústria ────────────────────────────────────────
                *steps_pin,
                # ── Entregas ──────────────────────────────────────────────────
                TourStep(
                    "Tela de Entregas",
                    "Agenda logística dos pedidos prontos para entrega. "
                    "Gerencie prazos, confirme entregas e acompanhe o status da logística.",
                    nav("entregas"), "right", "entregas",
                ),
                TourStep(
                    "Tabela e Ações de Entrega",
                    "Selecione pedidos para alterar prazo, confirmar entrega ou cancelar entrega.<br>"
                    "Vistas Lista e Cronograma disponíveis no topo da tela.",
                    delivery("table"), "top",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                *steps_hist,
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                TourStep(
                    "Aba — Sistema",
                    "Configure a URL do servidor, o prazo mínimo de entrega "
                    "e os alertas de faturamento.",
                    cfg("_tab_btns", 2), "bottom",
                ),
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # ════════════════════════════════════════════════════════════════════════
        # Vendedor
        # ════════════════════════════════════════════════════════════════════════
        if role == "vendedor":
            return [
                welcome,
                # ── Nova Requisição ───────────────────────────────────────────
                *steps_nova,
                # ── Central de Pedidos ────────────────────────────────────────
                *steps_pedidos,
                # ── Histórico ─────────────────────────────────────────────────
                *steps_hist,
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # ════════════════════════════════════════════════════════════════════════
        # Produção — A&R
        # ════════════════════════════════════════════════════════════════════════
        if role == "producao":
            return [
                welcome,
                # ── A&R ───────────────────────────────────────────────────────
                *steps_ar,
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Relatórios",
                    "Consulte qualquer requisição do sistema por PED, cliente ou status. "
                    "Duplo clique para abrir em modo leitura.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED ou nome do cliente para localizar uma requisição. "
                    "Combine com os filtros de status e período.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique para abrir os detalhes completos da requisição.",
                    hist("table"), "top",
                ),
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # ════════════════════════════════════════════════════════════════════════
        # Pinheiro Indústria
        # ════════════════════════════════════════════════════════════════════════
        if role == "industria":
            return [
                welcome,
                # ── Pinheiro Indústria ────────────────────────────────────────
                *steps_pin,
                # ── Central de Pedidos ────────────────────────────────────────
                *steps_pedidos,
                # ── Nova Requisição — Modo Leitura ────────────────────────────
                TourStep(
                    "Nova Requisição — Modo Leitura",
                    "Seu perfil permite <b>consultar</b> os detalhes de qualquer requisição, "
                    "mas <b>não editar</b>. "
                    "Use para verificar especificações técnicas, peso e observações antes de produzir.",
                    nav("nova"), "right", "nova",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Relatórios",
                    "Consulte qualquer requisição por PED, cliente ou status. "
                    "Duplo clique para abrir em modo leitura.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite o número do PED ou nome do cliente. "
                    "Combine com os filtros de status e período.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Clique nos cabeçalhos para ordenar. "
                    "Duplo clique para abrir os detalhes completos.",
                    hist("table"), "top",
                ),
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # ════════════════════════════════════════════════════════════════════════
        # Entregas (logística)
        # ════════════════════════════════════════════════════════════════════════
        if role in ("entregas", "entrega"):
            return [
                welcome,
                # ── Entregas ──────────────────────────────────────────────────
                TourStep(
                    "Entregas — Sua Tela Principal",
                    "Agenda logística: todos os pedidos prontos para entrega ao cliente. "
                    "Aqui você gerencia prazos, confirma entregas e acompanha o histórico.",
                    nav("entregas"), "right", "entregas",
                ),
                TourStep(
                    "Vista Lista / Cronograma",
                    "<b>Lista:</b> todos os pedidos pendentes em ordem de prazo de entrega.<br>"
                    "<b>Cronograma:</b> visão calendário organizada por data — "
                    "útil para planejar rotas do dia.",
                    delivery("_btn_view_list"), "bottom",
                ),
                TourStep(
                    "Tabela de Pedidos para Entrega",
                    "Lista os pedidos com entrega pendente. "
                    "Selecione um pedido para habilitar os botões de ação. "
                    "Duplo clique abre os detalhes completos da requisição.",
                    delivery("table"), "top",
                ),
                TourStep(
                    "Alterar Prazo de Entrega",
                    "Com um pedido selecionado, clique aqui para definir uma nova data. "
                    "É obrigatório informar um <b>motivo</b> para a alteração.<br><br>"
                    "O vendedor responsável é notificado automaticamente da mudança.",
                    delivery("btn_change_deadline"), "bottom",
                ),
                TourStep(
                    "Marcar como Entregue",
                    "Confirma que o pedido foi entregue ao cliente. "
                    "A data e hora são registradas no histórico e o status muda para <b>Finalizado</b>.<br><br>"
                    "Você pode selecionar múltiplos pedidos e marcar todos de uma vez.",
                    delivery("btn_mark_delivered"), "bottom",
                ),
                TourStep(
                    "Cancelar Entrega",
                    "Reverte uma entrega confirmada por engano, "
                    "devolvendo o pedido para a lista de pendentes.",
                    delivery("btn_cancel_delivered"), "bottom",
                ),
                # ── Nova Requisição (leitura) ──────────────────────────────────
                TourStep(
                    "Nova Requisição — Modo Leitura",
                    "Seu perfil permite <b>consultar</b> os detalhes de qualquer requisição, "
                    "mas <b>não editar</b>. "
                    "Use para verificar o endereço, itens e observações antes de sair para entrega.",
                    nav("nova"), "right", "nova",
                ),
                # ── Histórico ─────────────────────────────────────────────────
                TourStep(
                    "Relatórios",
                    "Consulte qualquer requisição por PED, cliente ou status. "
                    "Útil para verificar o histórico de entregas de um cliente específico.",
                    nav("historico"), "right", "historico",
                ),
                TourStep(
                    "Campo de Busca",
                    "Digite PED, nome do cliente ou endereço para localizar uma requisição.",
                    hist("input_search"), "bottom",
                ),
                TourStep(
                    "Tabela de Resultados",
                    "Duplo clique para abrir os detalhes completos em modo leitura.",
                    hist("table"), "top",
                ),
                # ── Feedbacks ─────────────────────────────────────────────────
                *steps_feedback_base,
                # ── Configurações ─────────────────────────────────────────────
                *steps_cfg_base,
                step_cfg_save,
                # ── Notificações + Atualizações ───────────────────────────────
                step_notif,
                step_update,
            ]

        # Fallback genérico
        return [
            welcome,
            TourStep(
                "Nova Requisição",
                "Crie e gerencie requisições de compra.",
                nav("nova"), "right", "nova",
            ),
            TourStep(
                "Histórico",
                "Busque e filtre todas as requisições por PED, cliente ou status.",
                nav("historico"), "right", "historico",
            ),
            TourStep(
                "Configurações",
                "Personalize a aparência e gerencie sua conta.",
                nav("config"), "right", "config",
            ),
            step_update,
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
