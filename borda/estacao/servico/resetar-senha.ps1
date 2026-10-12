#Requires -Version 5.0
<#  GerencIA - RESET da senha do serviço (para quem esqueceu).
    Roda como Administrador. NÃO exige a senha antiga: o hash fica no registro
    (HKLM\SOFTWARE\GerencIA), que o administrador da máquina pode reescrever.
    Grava uma nova senha no mesmo formato PBKDF2-SHA256 que o gerenciador espera.

    Uso (PowerShell como administrador):
      powershell -ExecutionPolicy Bypass -File .\resetar-senha.ps1
      powershell -ExecutionPolicy Bypass -File .\resetar-senha.ps1 -Senha "NovaSenhaForte"
#>
param([string]$Senha = "")
$ErrorActionPreference = "Stop"
$reg = "HKLM:\SOFTWARE\GerencIA"

function Admin? { ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator) }
if (-not (Admin?)) { Write-Host "Precisa ser Administrador. Reabra o PowerShell como administrador." -ForegroundColor Red; exit 1 }
if (-not (Test-Path $reg)) { Write-Host "Registro $reg nao existe — o servico pode nao estar instalado." -ForegroundColor Yellow; exit 1 }

if (-not $Senha) {
  $s1 = Read-Host "Nova senha" -AsSecureString
  $Senha = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
}
if ($Senha.Length -lt 6) { Write-Host "Senha muito curta (minimo 6)." -ForegroundColor Red; exit 1 }

$salt = New-Object byte[] 16
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
$iter = 120000
$k = New-Object Security.Cryptography.Rfc2898DeriveBytes($Senha,$salt,$iter,[Security.Cryptography.HashAlgorithmName]::SHA256)
Set-ItemProperty $reg -Name "SensorSalt" -Value ([Convert]::ToBase64String($salt))
Set-ItemProperty $reg -Name "SensorHash" -Value ([Convert]::ToBase64String($k.GetBytes(32)))
Set-ItemProperty $reg -Name "SensorIter" -Value $iter
Write-Host "OK. Senha redefinida. Ja pode usar o gerenciar-servico.ps1 com a nova senha." -ForegroundColor Green
