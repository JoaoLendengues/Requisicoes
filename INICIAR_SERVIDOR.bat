@echo off
title API - Ferragens Pinheiro
color 0A
echo.
echo  ============================================
echo   Sistema de Requisicoes - Ferragens Pinheiro
echo   API rodando em http://0.0.0.0:5000
echo  ============================================
echo.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run.py
) else (
    echo ERRO: Ambiente virtual nao encontrado.
    echo Procurado em ".venv\Scripts\python.exe" e "venv\Scripts\python.exe"
    echo Crie o ambiente virtual antes de iniciar o servidor.
)

echo.
echo  Servidor encerrado.
pause
