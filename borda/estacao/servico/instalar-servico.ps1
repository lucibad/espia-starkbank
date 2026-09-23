#Requires -Version 5.0
<#  GerencIA - instala o Sensor de Rede como Servico do Windows.
    Rode como Administrador (botao direito > Executar como administrador),
    ou:  powershell -ExecutionPolicy Bypass -File .\instalar-servico.ps1 -Coletor http://10.211.55.2:8765

    O servico:
      * sobe no boot, antes de qualquer usuario logar, e reinicia se cair;
      * roda como LocalSystem (nao depende de usuario logado);
      * so pode ser pausado/parado/desinstalado com a SENHA definida aqui,
        pelo gerenciar-servico.ps1. Usuarios comuns nao conseguem para-lo.
#>
param(
  [string]$Coletor = "",
  [string]$Senha   = "",
  [string]$SenhaHashB64 = "",   # modo silencioso (GPO/Intune): senha ja hasheada
  [string]$SaltB64 = "",
  [int]$IterParam = 0,
  [int]$Intervalo  = 15
)
$ErrorActionPreference = "Stop"
$Nome = "GerenciaSensor"
$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$Servico = Join-Path $Aqui "servico_win.py"

function Admin? { ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator) }
$souSystem = [Security.Principal.WindowsIdentity]::GetCurrent().IsSystem
if (-not (Admin?) -and -not $souSystem) { Write-Host "Precisa ser Administrador (ou SYSTEM via GPO/Intune)." -ForegroundColor Red; exit 1 }

# --- Python (robusto: ignora o atalho falso da Microsoft Store; instala se faltar) ---
function Test-Python($exe, $prefixo) {
  try {
    $out = & $exe @prefixo -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out -and ($out -notmatch 'WindowsApps')) { return $true }
  } catch {}
  return $false
}
function Resolve-Python {
  if (Test-Python "py" @("-3")) { return @{ Exe = "py"; Args = @("-3") } }
  foreach ($c in @("python","python3")) {
    foreach ($cmd in (Get-Command $c -All -ErrorAction SilentlyContinue |
                      Where-Object { $_.Source -and ($_.Source -notmatch 'WindowsApps') })) {
      if (Test-Python $cmd.Source @()) { return @{ Exe = $cmd.Source; Args = @() } }
    }
  }
  return $null
}
$P = Resolve-Python
if (-not $P) {
  Write-Host "Python nao encontrado (o 'python' do sistema e apenas o atalho da Microsoft Store)." -ForegroundColor Yellow
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Instalando Python 3.12 via winget (pode demorar um pouco)..." -ForegroundColor Cyan
    & winget install -e --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
    $P = Resolve-Python
  }
}
if (-not $P) {
  Write-Host "Nao consegui obter o Python. Instale o Python 3.9+ e rode o INSTALAR.bat de novo:" -ForegroundColor Red
  Write-Host "  https://www.python.org/downloads/  (marque 'Add python.exe to PATH')" -ForegroundColor Red
  Write-Host "  ou:  winget install -e --id Python.Python.3.12 --scope machine" -ForegroundColor Red
  Write-Host "Dica: desative o atalho falso em Configuracoes > Aplicativos > Configuracoes avancadas" -ForegroundColor Red
  Write-Host "      de aplicativo > Aliases de execucao de aplicativo (desligue os 'python.exe')." -ForegroundColor Red
  exit 3
}
$Py = $P.Exe; $PyArgs = $P.Args
Write-Host "Python: $Py $($PyArgs -join ' ')" -ForegroundColor Cyan
& $Py @PyArgs -m pip install --quiet --upgrade pywin32 psutil
# pos-instalacao do pywin32 (registra os servicos do Windows)
try { & $Py @PyArgs -m pywin32_postinstall -install | Out-Null } catch {}

# --- Senha (PBKDF2-SHA256) ---
if ($SenhaHashB64 -and $SaltB64) {
  # Modo silencioso (GPO/Intune): a senha ja veio hasheada - o texto nunca trafega.
  $saltB64 = $SaltB64; $hashB64 = $SenhaHashB64
  $iter = if ($IterParam -gt 0) { $IterParam } else { 120000 }
} else {
  if (-not $Senha) {
    $s1 = Read-Host "Defina a SENHA para pausar/desinstalar o servico" -AsSecureString
    $Senha = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
  }
  if ($Senha.Length -lt 6) { Write-Host "Senha muito curta (minimo 6)." -ForegroundColor Red; exit 1 }
  $salt = New-Object byte[] 16
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
  $iter = 120000
  $k = New-Object Security.Cryptography.Rfc2898DeriveBytes($Senha,$salt,$iter,[Security.Cryptography.HashAlgorithmName]::SHA256)
  $saltB64 = [Convert]::ToBase64String($salt); $hashB64 = [Convert]::ToBase64String($k.GetBytes(32))
}
$reg = "HKLM:\SOFTWARE\GerencIA"
New-Item -Path $reg -Force | Out-Null
Set-ItemProperty $reg -Name "SensorSalt" -Value $saltB64
Set-ItemProperty $reg -Name "SensorHash" -Value $hashB64
Set-ItemProperty $reg -Name "SensorIter" -Value $iter
# So SYSTEM e Administradores leem o hash.
$acl = Get-Acl $reg
$acl.SetAccessRuleProtection($true,$false)
foreach ($id in "NT AUTHORITY\SYSTEM","BUILTIN\Administrators") {
  $acl.AddAccessRule((New-Object Security.AccessControl.RegistryAccessRule($id,"FullControl","ContainerInherit,ObjectInherit","None","Allow")))
}
Set-Acl $reg $acl

# --- Variaveis de ambiente da maquina (o servico as le no boot) ---
[Environment]::SetEnvironmentVariable("GERENCIA_COLETOR",$Coletor,"Machine")
[Environment]::SetEnvironmentVariable("GERENCIA_INTERVALO","$Intervalo","Machine")

# --- Instala o servico ---
Write-Host "Instalando o servico $Nome ..." -ForegroundColor Cyan
& $Py @PyArgs $Servico --startup=auto install
# Reinicio automatico se cair (nao cobre parada legitima).
& sc.exe failure $Nome reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
& sc.exe description $Nome "GerencIA - sensor de uso de IA (metadado). Pausar/desinstalar exige senha." | Out-Null

# --- ACL: usuarios comuns NAO param/pausam; SYSTEM e Admin sim (via senha, no gerenciador) ---
$sddl = "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCLCSWRPWPDTLOCRRC;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWLOCRRC;;;AU)"
& sc.exe sdset $Nome $sddl | Out-Null

Start-Service $Nome
Write-Host ""
Write-Host "OK. Servico '$Nome' instalado e rodando." -ForegroundColor Green
Write-Host "  Coletor:   $(if($Coletor){$Coletor}else{'(nao definido - so registra localmente)'})"
Write-Host "  Estado:    $((Get-Service $Nome).Status)"
Write-Host "  Gerenciar: .\gerenciar-servico.ps1 -Acao status"
Write-Host "  Parar/pausar/desinstalar exige a senha (gerenciar-servico.ps1)."
Write-Host ""
Write-Host "Aviso honesto: a trava de senha + ACL impede usuarios comuns e" -ForegroundColor Yellow
Write-Host "administradores casuais. Um administrador determinado, com acesso" -ForegroundColor Yellow
Write-Host "fisico/SYSTEM, ainda pode remover. Blindagem total exige MDM/EDR." -ForegroundColor Yellow
