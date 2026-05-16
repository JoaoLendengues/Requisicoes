from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QStatusBar, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QTimer
from PySide6.QtGui import QFont

from ..core import theme
from ..core.resolution import res
from ..core.session import session
from ..api import client as api
from ..widgets.sidebar import Sidebar
from .requisition_form import RequisitionForm, _run_in_thread
from .history_view import HistoryView
from .dashboard_view import DashboardView
from .settings_view import SettingsView

PAGE_FORM      = 0
PAGE_HISTORY   = 1
PAGE_DASHBOARD = 2
PAGE_SETTINGS  = 3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scale = res.scale
        self._threads: list = []
        self._setup_ui()
        self._setup_statusbar()
        self.setWindowTitle("Sistema de Requisições — Ferragens Pinheiro")
        if res.start_maximized:
            self.showMaximized()
        else:
            w = max(1024, int(1280 * self.scale))
            h = max(700,  int(800  * self.scale))
            self.resize(w, h)

    # ── UI principal ──────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setStyleSheet(f"background:{theme.CONTENT_BG};")
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self.scale)
        self.sidebar.nav_clicked.connect(self._on_nav)
        self.sidebar.logout_clicked.connect(self._logout)
        root.addWidget(self.sidebar)

        # Separador vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{theme.BORDER_COLOR};")
        root.addWidget(sep)

        # Stack de views
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{theme.CONTENT_BG};")
        root.addWidget(self.stack, 1)

        # Páginas
        self.form_view      = RequisitionForm(self.scale)
        self.history_view   = HistoryView(self.scale)
        self.dashboard_view = DashboardView(self.scale)
        self.settings_view  = SettingsView(self.scale)

        self.stack.addWidget(self.form_view)       # 0
        self.stack.addWidget(self.history_view)    # 1
        self.stack.addWidget(self.dashboard_view)  # 2
        self.stack.addWidget(self.settings_view)   # 3

        self.history_view.open_requisition.connect(self._open_requisition)
        self.form_view.save_requested.connect(self._save_requisition)

        # Dashboard só para gerente/admin
        if not session.is_manager_or_admin:
            dash_btn = self.sidebar._nav_btns.get("dashboard")
            if dash_btn:
                dash_btn.setEnabled(False)
                dash_btn.setToolTip("Acesso restrito a gerentes")

    # ── Status bar (rodapé) ───────────────────────────────────────────────────
    def _setup_statusbar(self):
        bar = self.statusBar()
        bar.setStyleSheet(
            f"background:{theme.SIDEBAR_BG}; color:{theme.TEXT_LIGHT};"
            f"font-size:{max(8,int(9*self.scale))}pt; padding:0 12px;"
        )
        bar.showMessage(
            f"pinheiroferragens.com.br  |  SIA e Taguatinga  |  "
            f"Sistema de Requisições Pinheiro Ferragens  |  "
            f"Usuário: {session.user_name}  |  "
            f"{datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

    # ── Navegação ─────────────────────────────────────────────────────────────
    def _on_nav(self, key: str):
        mapping = {
            "nova":       PAGE_FORM,
            "historico":  PAGE_HISTORY,
            "dashboard":  PAGE_DASHBOARD,
            "config":     PAGE_SETTINGS,
        }
        page = mapping.get(key, PAGE_FORM)

        if page == PAGE_FORM and key == "nova":
            self.form_view.reset()

        if page == PAGE_HISTORY:
            self.history_view.refresh()

        if page == PAGE_DASHBOARD and session.is_manager_or_admin:
            self.dashboard_view.refresh()
        elif page == PAGE_DASHBOARD:
            QMessageBox.warning(self, "Acesso negado",
                                "O Dashboard é restrito a gerentes e administradores.")
            return

        self.stack.setCurrentIndex(page)

    def _save_requisition(self):
        if self.stack.currentIndex() != PAGE_FORM:
            return
        data = self.form_view.get_form_data()

        if not data.get("client_id"):
            QMessageBox.warning(self, "Atenção", "Selecione um cliente antes de salvar.")
            return

        canvas_json = self.form_view._canvas_json
        client      = self.form_view.client_search.get_selected()
        obs         = self.form_view.input_obs.toPlainText().strip()

        if self.form_view.req_id:
            req_id = self.form_view.req_id
            t, w = _run_in_thread(
                api.update_requisition, req_id, data,
                on_result=lambda r: self._after_save(r, canvas_json, client, obs),
                on_error=self._on_save_error,
            )
        else:
            t, w = _run_in_thread(
                api.create_requisition, data,
                on_result=lambda r: self._after_save(r, canvas_json, client, obs),
                on_error=self._on_save_error,
            )
        self._threads.append((t, w))

    def _after_save(self, req: dict, canvas_json: str,
                    client: dict | None = None, obs: str = ""):
        req_id = req["id"]
        self.form_view.req_id = req_id
        t, w = _run_in_thread(
            api.update_canvas, req_id, canvas_json,
            on_result=lambda _: self._on_fully_saved(req, canvas_json, client, obs),
            on_error=lambda _: self._on_fully_saved(req, canvas_json, client, obs),
        )
        self._threads.append((t, w))

    def _on_fully_saved(self, req: dict, canvas_json: str,
                        client: dict | None, obs: str):
        pdf_path = self._generate_pdf_sync(req, client, obs, canvas_json)
        self._show_saved(pdf_path)

    def _generate_pdf_sync(self, req: dict, client: dict | None,
                            obs: str, canvas_json: str = "{}") -> str:
        """Gera o PDF localmente (operação rápida, sem thread).
        Retorna o caminho gerado ou '' se não configurado/erro."""
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
        except Exception as e:
            QMessageBox.warning(
                self, "Aviso",
                f"Requisição salva, mas o PDF não pôde ser gerado:\n{e}",
            )
            return ""

    def _show_saved(self, pdf_path: str = ""):
        msg = "✅  Requisição salva com sucesso!"
        if pdf_path:
            msg += f"\n\n📄  PDF gerado em:\n{pdf_path}"
        QMessageBox.information(self, "Requisição Salva", msg)

    def _on_save_error(self, msg: str):
        QMessageBox.critical(self, "Erro ao salvar", msg)

    # ── Abrir requisição do histórico ─────────────────────────────────────────
    def _open_requisition(self, req_id: int):
        t, w = _run_in_thread(
            api.get_requisition, req_id,
            on_result=self._load_req_into_form,
            on_error=lambda e: QMessageBox.critical(self, "Erro", e),
        )
        self._threads.append((t, w))

    def _load_req_into_form(self, data: dict):
        self.form_view.load_requisition(data)
        self.stack.setCurrentIndex(PAGE_FORM)
        self.sidebar._highlight("nova")

    # ── Logout ────────────────────────────────────────────────────────────────
    def _logout(self):
        reply = QMessageBox.question(
            self, "Sair",
            "Deseja encerrar a sessão?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            session.logout()
            self.close()
