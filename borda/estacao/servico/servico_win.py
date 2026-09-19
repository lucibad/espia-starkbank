#!/usr/bin/env python3
"""
GerencIA · sensor como Serviço do Windows.

Roda o sensor de rede (../sensor.py) como um serviço de verdade, gerido pelo
Gerenciador de Serviços do Windows (SCM): sobe sozinho no boot, antes de
qualquer usuário logar, e reinicia se cair. Requer pywin32 (o instalador
instala). Este arquivo é a ponte com o SCM; a trava de senha para pausar /
desinstalar fica no gerenciar-servico.ps1, que é o caminho sancionado.

O laço em si é o sensor.rodar(); aqui só o embrulhamos no ciclo de vida do
serviço (iniciar / parar / pausar / continuar).
"""
from __future__ import annotations

import os
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_ESTACAO = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ_ESTACAO)   # para importar sensor.py

NOME_SERVICO = "GerenciaSensor"
NOME_EXIBICAO = "GerencIA · Sensor de Rede"
DESCRICAO = ("Governança de uso de IA (Desafio 2 · Stark Bank). Registra METADADO "
             "de conexões a ferramentas de IA — nunca o conteúdo. Pausar ou "
             "desinstalar exige a senha do administrador (gerenciar-servico.ps1).")

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    TEM_PYWIN32 = True
except ImportError:
    TEM_PYWIN32 = False


if TEM_PYWIN32:

    class GerenciaSensor(win32serviceutil.ServiceFramework):
        _svc_name_ = NOME_SERVICO
        _svc_display_name_ = NOME_EXIBICAO
        _svc_description_ = DESCRICAO
        # Aceita pausar/continuar além de parar.
        _svc_accepted_ = (win32service.SERVICE_ACCEPT_STOP |
                          win32service.SERVICE_ACCEPT_PAUSE_CONTINUE)

        def __init__(self, args):
            super().__init__(args)
            self._parar = win32event.CreateEvent(None, 0, 0, None)
            self._pausado = threading.Event()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._parar)

        def SvcPause(self):
            self.ReportServiceStatus(win32service.SERVICE_PAUSE_PENDING)
            self._pausado.set()
            self.ReportServiceStatus(win32service.SERVICE_PAUSED)

        def SvcContinue(self):
            self._pausado.clear()
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        def SvcDoRun(self):
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (self._svc_name_, ""))
            import sensor
            import win32event as _we
            sensor._reindexar(forcar=True)
            # Laço próprio (não sensor.rodar(), para poder pausar e parar limpo).
            while _we.WaitForSingleObject(self._parar, sensor.INTERVALO * 1000) == _we.WAIT_TIMEOUT:
                if self._pausado.is_set():
                    continue
                try:
                    sensor.varrer(imprimir=False)
                except Exception as e:
                    servicemanager.LogErrorMsg(f"GerenciaSensor: falha na varredura: {e}")


def ponte_servico(args: list[str]) -> None:
    """Encaminha install/start/stop/remove/debug ao pywin32."""
    if not TEM_PYWIN32:
        print("pywin32 não encontrado. Instale com:  pip install pywin32", file=sys.stderr)
        sys.exit(2)
    win32serviceutil.HandleCommandLine(GerenciaSensor, argv=[sys.argv[0]] + args)


if __name__ == "__main__":
    ponte_servico(sys.argv[1:])
