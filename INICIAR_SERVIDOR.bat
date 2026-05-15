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
call .venv\Scripts\activate
py run.py
pause
