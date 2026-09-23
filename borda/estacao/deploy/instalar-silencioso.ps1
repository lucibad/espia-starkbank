#Requires -Version 5.0
<#  GerencIA - instalacao SILENCIOSA do agente para GPO / Intune.
    Sem prompts. Roda como SYSTEM (GPO startup / Intune) ou Administrador.
    Copia o agente para uma pasta fixa local e registra o servico.

    Exemplos:
      # com a senha pre-hasheada (recomendado - nao expoe o texto):
      powershell -ExecutionPolicy Bypass -File .\instalar-silencioso.ps1 `
        -Coletor http://10.211.55.2:8765 `
        -SenhaHashB64 "..." -SaltB64 "..." -IterParam 120000

      # com a senha em texto (mais simples, menos seguro no script de GPO):
      powershell -ExecutionPolicy Bypass -File .\instalar-silencioso.ps1 `
        -Coletor http://10.211.55.2:8765 -Senha "MinhaSenhaForte"

    Codigos de saida: 0 = ok, !=0 = falha (para o Intune detectar).
#>
param(
  [Parameter(Mandatory=$true)][string]$Coletor,
  [string]$Senha = "",
  [string]$SenhaHashB64 = "",
  [string]$SaltB64 = "",
  [int]$IterParam = 0,
  [int]$Intervalo = 15,
  [string]$InstallDir = "$env:ProgramFiles\GerencIA\Agente",
  [string]$Origem = ""
)
$ErrorActionPreference = "Stop"
$Versao = "0.2.0"
$logDir = "$env:ProgramData\GerencIA"; New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Transcript -Path (Join-Path $logDir "instalacao.log") -Append | Out-Null
try {
  if (-not $Origem) { $Origem = Split-Path -Parent $PSScriptRoot }  # raiz do pacote (contem sensor.py e servico\)
  Write-Host "[GerencIA] Origem=$Origem  InstallDir=$InstallDir  Coletor=$Coletor"

  # 1) copia o agente para a pasta fixa local (o servico aponta para ela)
  New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "servico") | Out-Null
  Copy-Item (Join-Path $Origem "sensor.py") $InstallDir -Force
  Copy-Item (Join-Path $Origem "servico\*") (Join-Path $InstallDir "servico") -Recurse -Force

  # 2) registra o servico usando o instalador ja testado, em modo nao-interativo
  $inst = Join-Path $InstallDir "servico\instalar-servico.ps1"
  $spArgs = @("-Coletor",$Coletor,"-Intervalo",$Intervalo)
  if ($SenhaHashB64 -and $SaltB64) { $spArgs += @("-SenhaHashB64",$SenhaHashB64,"-SaltB64",$SaltB64,"-IterParam",$IterParam) }
  elseif ($Senha) { $spArgs += @("-Senha",$Senha) }
  else { throw "Informe -Senha ou (-SenhaHashB64 -SaltB64)." }
  & powershell -ExecutionPolicy Bypass -File $inst @spArgs
  if ($LASTEXITCODE -ne 0) { throw "instalar-servico.ps1 retornou $LASTEXITCODE" }

  # 3) marcadores para deteccao (Intune) e desinstalacao
  Set-ItemProperty "HKLM:\SOFTWARE\GerencIA" -Name "SensorVersao" -Value $Versao
  Set-ItemProperty "HKLM:\SOFTWARE\GerencIA" -Name "SensorInstalar" -Value $InstallDir
  Write-Host "[GerencIA] Instalacao concluida (v$Versao)."
  Stop-Transcript | Out-Null
  exit 0
} catch {
  Write-Host "[GerencIA] FALHA: $_" -ForegroundColor Red
  Stop-Transcript | Out-Null
  exit 1
}
