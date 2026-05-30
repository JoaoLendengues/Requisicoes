"""
Ponto de entrada do servidor.
Execute: python run.py
"""

from __future__ import annotations

import os
import subprocess
import sys

import uvicorn


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")


def _using_project_venv() -> bool:
    return os.path.normcase(sys.executable) == os.path.normcase(VENV_PYTHON)


def _relaunch_with_project_venv() -> None:
    if not os.path.exists(VENV_PYTHON) or _using_project_venv():
        return

    result = subprocess.call([VENV_PYTHON, os.path.abspath(__file__), *sys.argv[1:]])
    raise SystemExit(result)


if __name__ == "__main__":
    _relaunch_with_project_venv()
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        # NÃO usar workers > 1: o SSE manager usa asyncio.Queue em memória.
        # Com múltiplos processos, cada worker teria sua própria fila e notificações
        # enviadas de um worker não chegariam a usuários conectados em outro.
        # Para escalar horizontalmente, seria necessário um broker externo (ex: Redis Pub/Sub).
    )
