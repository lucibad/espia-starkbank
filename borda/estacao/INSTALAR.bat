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

rem Se estiver rodando de um caminho de rede (\\Mac\Home, \\servidor...), copia
rem para o disco local: o servico precisa de um caminho local para subir no boot.
set "RUNDIR=%~dp0"
set "PREFIXO=%RUNDIR:~0,2%"
if "%PREFIXO%"=="\\" (
  echo Caminho de rede detectado. Copiando para C:\GerencIA ...
  xcopy "%~dp0*" "C:\GerencIA\GerencIA-Agente-Estacao\" /E /I /Y >nul
  set "RUNDIR=C:\GerencIA\GerencIA-Agente-Estacao\"
  echo.
)

set /p COLETOR="URL do coletor central (ex.: http://macbook-pro.local:8765): "
echo.
powershell -ExecutionPolicy Bypass -File "%RUNDIR%servico\instalar-servico.ps1" -Coletor "%COLETOR%"
echo.
echo Instalacao concluida (ou veja as mensagens acima). Pasta local: %RUNDIR%
pause
