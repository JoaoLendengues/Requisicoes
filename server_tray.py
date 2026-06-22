"""
Bandeja do sistema para o servidor Requisições App.
Inicie com pythonw.exe (sem janela de terminal).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ROOT     = Path(__file__).parent
LOG_FILE = ROOT / "server.log"
VENV_PY  = ROOT / ".venv" / "Scripts" / "python.exe"
PORT     = 5000


def _circle(color: str) -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    return img


_GREEN  = _circle("#22c55e")
_RED    = _circle("#ef4444")
_YELLOW = _circle("#f59e0b")

_lock   = threading.Lock()
_proc: subprocess.Popen | None = None
_icon: pystray.Icon | None = None
_active = threading.Event()


def _alive() -> bool:
    with _lock:
        return _proc is not None and _proc.poll() is None


def _write_log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "ab") as f:
            f.write(f"[{ts}] {msg}\n".encode("utf-8"))
    except OSError:
        pass


def _sync_icon() -> None:
    if _icon is None:
        return
    if _alive():
        _icon.icon  = _GREEN
        _icon.title = "Requisições App — Servidor rodando"
    else:
        _icon.icon  = _RED
        _icon.title = "Requisições App — Servidor parado"


def _start() -> None:
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return
        py    = str(VENV_PY) if VENV_PY.exists() else sys.executable
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            with open(LOG_FILE, "ab") as lf:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                lf.write(f"\n{'=' * 56}\n[{ts}] Servidor iniciando...\n".encode("utf-8"))
            log_f = open(LOG_FILE, "ab")
            _proc = subprocess.Popen(
                [py, str(ROOT / "run.py")],
                stdout=log_f,
                stderr=log_f,
                cwd=str(ROOT),
                creationflags=flags,
            )
            log_f.close()
        except Exception as exc:
            _write_log(f"ERRO ao iniciar o servidor: {exc}")
    _sync_icon()


def _stop() -> None:
    global _proc
    p = None
    with _lock:
        if _proc is not None and _proc.poll() is None:
            p, _proc = _proc, None
        else:
            _proc = None
    if p is not None:
        p.terminate()
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        _write_log("Servidor encerrado.")
    _sync_icon()


def _restart() -> None:
    _write_log("Reiniciando servidor...")
    _stop()
    time.sleep(1)
    _start()


def _monitor() -> None:
    was = False
    while _active.is_set():
        now = _alive()
        if now != was:
            _sync_icon()
            was = now
        time.sleep(2)


def _on_start(icon, item):
    threading.Thread(target=_start, daemon=True).start()

def _on_stop(icon, item):
    threading.Thread(target=_stop, daemon=True).start()

def _on_restart(icon, item):
    threading.Thread(target=_restart, daemon=True).start()

def _on_terminal(icon, item):
    LOG_FILE.touch()
    title = "Servidor — Requisicoes App"
    cmd   = (
        f"$host.UI.RawUI.WindowTitle = '{title}';"
        f" Get-Content -Path '{LOG_FILE}' -Wait -Tail 50"
    )
    subprocess.Popen(
        ["powershell", "-NoExit", "-Command", cmd],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

def _on_logs(icon, item):
    LOG_FILE.touch()
    os.startfile(str(LOG_FILE))

def _on_browser(icon, item):
    webbrowser.open(f"http://localhost:{PORT}/docs")

def _on_exit(icon, item):
    _active.clear()
    threading.Thread(target=_stop, daemon=True).start()
    icon.stop()


def _build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(
            lambda _: "Servidor rodando — porta 5000" if _alive() else "Servidor parado",
            None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Iniciar servidor",   _on_start,   enabled=lambda _: not _alive()),
        pystray.MenuItem("Parar servidor",     _on_stop,    enabled=lambda _: _alive()),
        pystray.MenuItem("Reiniciar servidor", _on_restart, enabled=lambda _: _alive()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Abrir terminal do servidor", _on_terminal),
        pystray.MenuItem("Ver logs",                   _on_logs),
        pystray.MenuItem("Abrir API no navegador",     _on_browser),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Encerrar", _on_exit),
    )


def main() -> None:
    global _icon
    _active.set()
    threading.Thread(target=_start,   daemon=True).start()
    threading.Thread(target=_monitor, daemon=True).start()
    _icon = pystray.Icon(
        "requisicoes_server",
        _YELLOW,
        "Requisições App — iniciando...",
        menu=_build_menu(),
    )
    _icon.run()


if __name__ == "__main__":
    main()
