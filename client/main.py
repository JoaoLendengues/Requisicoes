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
from client.views.login_view import LoginView
from client.views.main_window import MainWindow


def main():
    # Habilita escala de DPI no Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Requisições — Ferragens Pinheiro")
    app.setOrganizationName("Pinheiro Ferragens")

    # Inicializa gerenciador de resolução (precisa de QApplication criada)
    res.init(app)

    # Fonte padrão adaptada à escala
    font = QFont("Segoe UI", res.font(10))
    app.setFont(font)

    # Estilo global
    app.setStyleSheet(
        "QToolTip { background:#1B2B4B; color:#fff; border:none; padding:4px 8px; }"
        "QScrollBar:vertical { width:8px; background:#F1F5F9; border-radius:4px; }"
        "QScrollBar::handle:vertical { background:#CBD5E1; border-radius:4px; min-height:30px; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        "QScrollBar:horizontal { height:8px; background:#F1F5F9; border-radius:4px; }"
        "QScrollBar::handle:horizontal { background:#CBD5E1; border-radius:4px; }"
        "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }"
    )

    main_window: MainWindow | None = None
    login_view = LoginView()

    def on_login():
        nonlocal main_window
        login_view.hide()
        main_window = MainWindow()
        main_window.show()

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
