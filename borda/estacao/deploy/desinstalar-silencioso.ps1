#Requires -Version 5.0
<#  GerencIA - desinstalacao SILENCIOSA para GPO / Intune (roda como SYSTEM/Admin).
    A gestao central e a autoridade: NAO pede a senha (a senha protege contra os
    usuarios/admin LOCAIS da maquina, nao contra a politica corporativa).
    Codigos de saida: 0 = ok. #>
param([string]$InstallDir = "")
$ErrorActionPreference = "SilentlyContinue"
$logDir = "$env:ProgramData\GerencIA"; New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir "desinstalacao.log") -Append | Out-Null
$Nome = "GerenciaSensor"
if (-not $InstallDir) { $InstallDir = (Get-ItemProperty "HKLM:\SOFTWARE\GerencIA" -Name SensorInstalar -ErrorAction SilentlyContinue).SensorInstalar }
if (-not $InstallDir) { $InstallDir = "$env:ProgramFiles\GerencIA\Agente" }
$py = (Get-Command py -ErrorAction SilentlyContinue); if ($py){$Py="py";$A=@("-3")}else{$Py="python";$A=@()}
try { Stop-Service $Nome -Force -ErrorAction SilentlyContinue } catch {}
& $Py @A (Join-Path $InstallDir "servico\servico_win.py") remove 2>$null
& sc.exe delete $Nome 2>$null | Out-Null
Remove-Item "HKLM:\SOFTWARE\GerencIA" -Recurse -Force -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable("GERENCIA_COLETOR",$null,"Machine")
[Environment]::SetEnvironmentVariable("GERENCIA_INTERVALO",$null,"Machine")
Remove-Item (Split-Path -Parent $InstallDir) -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[GerencIA] Desinstalado."
Stop-Transcript | Out-Null
exit 0
