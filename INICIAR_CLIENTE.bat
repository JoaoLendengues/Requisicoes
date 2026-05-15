@echo off
title Requisicoes - Ferragens Pinheiro
cd /d "%~dp0"
call .venv\Scripts\activate
py run_client.py
