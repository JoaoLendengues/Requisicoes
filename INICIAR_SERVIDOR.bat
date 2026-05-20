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
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run.py
) else (
    echo Ambiente virtual nao encontrado em "venv".
    echo Crie ou restaure a pasta venv antes de iniciar o servidor.
    pause
)
