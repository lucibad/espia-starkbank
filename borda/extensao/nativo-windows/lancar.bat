@echo off
rem Lançador do host de identidade. O navegador chama este .bat; ele passa o
rem controle ao Python, que fala o protocolo de native messaging por stdio.
py -3 "%~dp0identidade.py" 2>nul || python "%~dp0identidade.py"
