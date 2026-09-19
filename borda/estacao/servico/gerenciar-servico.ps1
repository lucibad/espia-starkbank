#Requires -Version 5.0
<#  GerencIA - gerencia o Servico do Sensor de Rede.
    status     -> livre (nao pede senha)
    pausar / continuar / parar / desinstalar -> exigem a SENHA definida na instalacao.

    Ex.:  .\gerenciar-servico.ps1 -Acao status
          .\gerenciar-servico.ps1 -Acao pausar     -Senha ******
          .\gerenciar-servico.ps1 -Acao desinstalar -Senha ******
#>
param(
  [Parameter(Mandatory=$true)][ValidateSet("status","pausar","continuar","parar","desinstalar")]
  [string]$Acao,
  [string]$Senha = ""
)
$ErrorActionPreference = "Stop"
$Nome = "GerenciaSensor"
$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$reg  = "HKLM:\SOFTWARE\GerencIA"

function Admin? { ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator) }

function Confere-Senha {
  if (-not (Test-Path $reg)) { Write-Host "Servico nao instalado (sem registro de senha)." -ForegroundColor Red; exit 1 }
  if (-not $Senha) {
    $s = Read-Host "Senha" -AsSecureString
    $Senha = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
  }
  $salt = [Convert]::FromBase64String((Get-ItemProperty $reg).SensorSalt)
  $alvo = [Convert]::FromBase64String((Get-ItemProperty $reg).SensorHash)
  $iter = [int](Get-ItemProperty $reg).SensorIter
  $k = New-Object Security.Cryptography.Rfc2898DeriveBytes($Senha,$salt,$iter,[Security.Cryptography.HashAlgorithmName]::SHA256)
  $h = $k.GetBytes(32)
  $ok = $true; for ($i=0;$i -lt 32;$i++){ if ($h[$i] -ne $alvo[$i]){ $ok=$false } }  # comparacao de tempo fixo
  if (-not $ok) { Write-Host "Senha incorreta. Acao negada." -ForegroundColor Red; exit 1 }
}

if ($Acao -eq "status") {
  $s = Get-Service $Nome -ErrorAction SilentlyContinue
  if (-not $s) { Write-Host "Servico '$Nome' nao esta instalado." -ForegroundColor Yellow; exit 0 }
  Write-Host "Servico:  $($s.DisplayName)"
  Write-Host "Estado:   $($s.Status)"
  Write-Host "Inicio:   $((Get-CimInstance Win32_Service -Filter "Name='$Nome'").StartMode)"
  Write-Host "Coletor:  $([Environment]::GetEnvironmentVariable('GERENCIA_COLETOR','Machine'))"
  exit 0
}

if (-not (Admin?)) { Write-Host "Esta acao precisa de Administrador." -ForegroundColor Red; exit 1 }
Confere-Senha    # daqui pra baixo, so com a senha correta

switch ($Acao) {
  "pausar"      { Suspend-Service $Nome; Write-Host "Servico pausado." -ForegroundColor Green }
  "continuar"   { Resume-Service  $Nome; Write-Host "Servico retomado." -ForegroundColor Green }
  "parar"       { Stop-Service    $Nome -Force; Write-Host "Servico parado." -ForegroundColor Green }
  "desinstalar" {
    try { Stop-Service $Nome -Force -ErrorAction SilentlyContinue } catch {}
    $py = (Get-Command py -ErrorAction SilentlyContinue); if ($py){$Py="py";$A=@("-3")}else{$Py="python";$A=@()}
    & $Py @A (Join-Path $Aqui "servico_win.py") remove
    Remove-Item $reg -Recurse -Force -ErrorAction SilentlyContinue
    [Environment]::SetEnvironmentVariable("GERENCIA_COLETOR",$null,"Machine")
    Write-Host "Servico desinstalado e senha removida." -ForegroundColor Green
  }
}
