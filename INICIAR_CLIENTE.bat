@echo off
title Requisicoes - Ferragens Pinheiro
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run_client.py
) else (
    echo Ambiente virtual nao encontrado em "venv".
    echo Crie ou restaure a pasta venv antes de iniciar o cliente.
    pause
)
