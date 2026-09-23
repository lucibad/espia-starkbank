@echo off
title GerencIA - Desinstalacao do Agente
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
powershell -ExecutionPolicy Bypass -File "%~dp0servico\gerenciar-servico.ps1" -Acao desinstalar
pause
