@echo off
title GerencIA - Instalacao do Agente de Estacao
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Este instalador precisa de privilegios de administrador.
  echo Solicitando elevacao...
  powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
echo ============================================================
echo   GerencIA - Agente de Estacao (Sensor de Rede)
echo   Instala como Servico do Windows (sobe no boot)
echo ============================================================
echo.
set /p COLETOR="URL do coletor central (ex.: http://10.211.55.2:8765): "
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0servico\instalar-servico.ps1" -Coletor "%COLETOR%"
echo.
pause
