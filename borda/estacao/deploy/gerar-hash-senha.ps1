#Requires -Version 5.0
<#  Gera o hash PBKDF2-SHA256 de uma senha, para implantacao silenciosa (GPO/Intune)
    sem colocar a senha em texto claro no script de distribuicao.
    Uso:  .\gerar-hash-senha.ps1                 (pergunta a senha)
          .\gerar-hash-senha.ps1 -Senha "MinhaSenhaForte"
#>
param([string]$Senha = "", [int]$Iter = 120000)
if (-not $Senha) {
  $s = Read-Host "Senha a proteger" -AsSecureString
  $Senha = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
if ($Senha.Length -lt 6) { Write-Host "Senha muito curta (minimo 6)." -ForegroundColor Red; exit 1 }
$salt = New-Object byte[] 16
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
$k = New-Object Security.Cryptography.Rfc2898DeriveBytes($Senha,$salt,$Iter,[Security.Cryptography.HashAlgorithmName]::SHA256)
$saltB64 = [Convert]::ToBase64String($salt)
$hashB64 = [Convert]::ToBase64String($k.GetBytes(32))
Write-Host ""
Write-Host "SaltB64 : $saltB64"
Write-Host "HashB64 : $hashB64"
Write-Host "Iter    : $Iter"
Write-Host ""
Write-Host "Cole na linha de comando da implantacao (a senha em texto NAO vai junto):" -ForegroundColor Cyan
Write-Host "  -SenhaHashB64 `"$hashB64`" -SaltB64 `"$saltB64`" -IterParam $Iter"
