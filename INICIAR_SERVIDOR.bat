@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" server_tray.py
) else if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" server_tray.py
) else (
    echo ERRO: Ambiente virtual nao encontrado.
    echo Procurado em ".venv\Scripts\pythonw.exe"
    pause
)
