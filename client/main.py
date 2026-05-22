"""
Ponto de entrada do cliente PySide6.
Execute: .venv/Scripts/python -m client.main
        ou: python run_client.py
"""
import sys
import os

# Garante que o diretório raiz esteja no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from client.core.resolution import res
from client.core.session import session
from client.core import theme
from client.core.dialogs import install_message_box_theme_hooks
from client.views.login_view import LoginView
from client.views.main_window import MainWindow
from client.updater import finalize_pending_update, UpdateChecker
from client.widgets.update_dialog import UpdateAvailableDialog


def _check_for_updates(parent_window) -> None:
    """Inicia verificação silenciosa de atualizações em segundo plano."""
    checker = UpdateChecker(parent=parent_window)
    checker.update_available.connect(
        lambda info: UpdateAvailableDialog(info, parent_window).exec()
    )
    # Mantém referência para evitar garbage collection antes do sinal disparar
    parent_window._update_checker = checker
    checker.start()


def main():
    # Habilita escala de DPI no Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Windows")
    app.setApplicationName("Requisições — Ferragens Pinheiro")
    app.setOrganizationName("Pinheiro Ferragens")

    # Inicializa gerenciador de resolução (precisa de QApplication criada)
    res.init(app)

    # Fonte padrão adaptada à escala
    font = QFont(theme.FONT_PRIMARY, res.font(10))
    if not font.exactMatch():
        font = QFont(theme.FONT_FALLBACK, res.font(10))
    if not font.exactMatch():
        font = QFont("Segoe UI", res.font(10))
    app.setFont(font)

    # Estilo global
    app.setStyleSheet(theme.global_style())
    install_message_box_theme_hooks()

    # Verifica se uma atualização anterior foi concluída (ou falhou)
    update_result = finalize_pending_update()
    if update_result:
        from PySide6.QtWidgets import QMessageBox
        if update_result["status"] == "completed":
            QMessageBox.information(None, "Atualização concluída", update_result["message"])
        else:
            QMessageBox.warning(None, "Atualização com falha", update_result["message"])

    main_window: MainWindow | None = None
    login_view = LoginView()

    def on_switch_user():
        nonlocal main_window
        if main_window is not None:
            main_window = None
        login_view.input_pass.clear()
        login_view.error_label.hide()
        login_view.show()
        login_view.raise_()
        login_view.activateWindow()

    def on_login():
        nonlocal main_window
        login_view.hide()
        main_window = MainWindow()
        main_window.switch_user_requested.connect(on_switch_user)
        main_window.show()
        # Verifica atualizações silenciosamente após o login
        _check_for_updates(main_window)

    login_view.login_success.connect(on_login)

    if res.start_maximized:
        login_view.showMaximized()
    else:
        w = max(900, int(1100 * res.scale))
        h = max(600, int(720  * res.scale))
        login_view.resize(w, h)
        login_view.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
