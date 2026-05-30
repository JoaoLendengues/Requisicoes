"""Atalho para iniciar o cliente: python run_client.py"""

from __future__ import annotations

import os
import subprocess
import sys


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(ROOT_DIR, "venv", "Scripts", "python.exe")


def _using_project_venv() -> bool:
    return os.path.normcase(sys.executable) == os.path.normcase(VENV_PYTHON)


def _relaunch_with_project_venv() -> None:
    if not os.path.exists(VENV_PYTHON) or _using_project_venv():
        return

    result = subprocess.call([VENV_PYTHON, os.path.abspath(__file__), *sys.argv[1:]])
    raise SystemExit(result)


def _load_main():
    try:
        from client.main import main
        return main
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            raise SystemExit(
                "PySide6 nao foi encontrado neste Python.\n"
                "Abra pelo arquivo INICIAR_CLIENTE.bat ou use:\n"
                r"venv\Scripts\python.exe run_client.py"
            ) from exc
        raise


if __name__ == "__main__":
    _relaunch_with_project_venv()
    _load_main()()
