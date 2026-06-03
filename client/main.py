"""
Ponto de entrada do cliente PySide6.
Execute: .venv/Scripts/python -m client.main
        ou: python run_client.py
"""
import sys
import os
import logging
import traceback

# Garante que o diretório raiz esteja no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── Log em arquivo (executável windowed não tem console) ──────────────────────
def _setup_logging() -> None:
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", ROOT), "Requisicoes", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    # Captura exceções não tratadas e grava no log antes de fechar
    def _handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical(
            "Exceção não tratada:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = _handle_exception


_setup_logging()

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase

from client.core.resolution import res
from client.core.session import session
from client.core import theme
from client.core.dialogs import install_dialog_theme_hooks
from client.core.orthography import install_orthography_hooks
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


def _set_windows_timer_resolution() -> None:
    """
    Windows usa resolução de timer de 15.6 ms por padrão (≈64 Hz).
    Reduzir para 1 ms garante que os callbacks do Qt disparem a cada ~16 ms
    (≈60 fps) em vez de cada ~31 ms, tornando animações realmente fluidas.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        import atexit
        atexit.register(ctypes.windll.winmm.timeEndPeriod, 1)
    except Exception:
        pass


def main():
    # Garante timer de 1 ms no Windows → animações a 60 fps reais
    _set_windows_timer_resolution()

    # Habilita escala de DPI no Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # renderização consistente e eficiente em todas as plataformas
    app.setApplicationName("Requisições App")
    app.setOrganizationName("Pinheiro Ferragens")

    # Inicializa gerenciador de resolução (precisa de QApplication criada)
    res.init(app)

    # Registra fontes Inter embutidas no pacote
    _FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
    for _fname in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
        _fpath = os.path.join(_FONT_DIR, _fname)
        if os.path.exists(_fpath):
            QFontDatabase.addApplicationFont(_fpath)

    # Fonte padrão adaptada à escala
    font = QFont(theme.FONT_PRIMARY, res.font(10))
    if not font.exactMatch():
        font = QFont(theme.FONT_FALLBACK, res.font(10))
    app.setFont(font)

    # Estilo global
    app.setStyleSheet(theme.global_style())
    theme.apply_tooltip_palette(app)
    install_orthography_hooks(app)
    install_dialog_theme_hooks(app)

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
        # Avança o rodízio de fundo — mesmo comportamento de abrir o app do zero
        login_view.reload_background()
        # Inicia invisível → fade-in suave enquanto o main faz o fade-out
        login_view.setWindowOpacity(0.0)
        login_view.show()
        login_view.raise_()
        login_view.activateWindow()
        login_view.fade_in()

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
