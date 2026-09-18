<#
  Instala o AGENTE DE ESTAÇÃO do Rastro nesta máquina Windows, para o usuário
  logado. O agente:
    - lê o usuário do Windows (voce) direto do sistema — identidade confiável,
      sem host de mensagens nativas;
    - roda a camada 1 localmente e guarda uma cópia em SQLite;
    - encaminha cada evento ao COLETOR central (o Mac).

  Roda ao iniciar a sessão do usuário (atalho na pasta Inicializar). Como cada
  usuário do Windows inicia o seu próprio agente, %USERNAME% é sempre o certo.

  Uso (PowerShell, nesta pasta), logado como o usuário que vai testar:
    .\instalar-agente.ps1
    .\instalar-agente.ps1 -Coletor "http://10.211.55.2:8765" -Porta 8765

  Requer Python no Windows (py -3 ou python no PATH).
#>
param(
  [string] $Coletor = "http://10.211.55.2:8765",
  [int]    $Porta   = 8765
)

$ErrorActionPreference = "Stop"
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path (Join-Path $pasta "agente.py"))) {
  throw "agente.py não está nesta pasta. Extraia o pacote inteiro e rode aqui."
}

# checa Python
$py = $null
foreach ($c in @("py -3", "python", "pythonw")) {
  try { & cmd /c "$c --version" *> $null; if ($LASTEXITCODE -eq 0) { $py = $c; break } } catch {}
}
if (-not $py) { throw "Python não encontrado no PATH. Instale em https://www.python.org e reabra o PowerShell." }

# gera o lançador com o coletor/porta escolhidos
$bat = Join-Path $pasta "iniciar-agente.bat"
@"
@echo off
rem Lancador gerado por instalar-agente.ps1
set RASTRO_COLETOR=$Coletor
set RASTRO_PORTA=$Porta
cd /d "%~dp0"
start "" /min pythonw agente.py 2>nul || start "" /min python agente.py
"@ | Set-Content -Encoding OEM $bat

# atalho na pasta Inicializar (por usuário) → roda a cada login
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "Rastro Agente.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $pasta
$sc.WindowStyle = 7            # minimizado
$sc.Description = "Rastro - agente de estacao"
$sc.Save()

# inicia agora
Start-Process -FilePath $bat -WindowStyle Minimized

Write-Host ""
Write-Host "Agente de estacao instalado para o usuario:" $env:USERNAME
Write-Host "  coletor central : $Coletor"
Write-Host "  porta local     : $Porta   (aponte a extensao deste PC para http://127.0.0.1:$Porta)"
Write-Host "  inicia no login : $lnk"
Write-Host ""
Write-Host "Confira em http://127.0.0.1:$Porta/api/saude (deve responder ok)."
Write-Host "No modo estacao a extensao NAO precisa do host de identidade nativo:"
Write-Host "o proprio agente ja le o usuario do Windows."
