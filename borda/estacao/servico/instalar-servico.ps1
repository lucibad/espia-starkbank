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
function Atualiza-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
function Install-Python {
  # 1) winget forcando a fonte 'winget' (o msstore costuma faltar em maquinas corporativas)
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Tentando via winget (fonte winget)..." -ForegroundColor Cyan
    try { & winget install -e --id Python.Python.3.12 --source winget --scope machine --silent `
                 --accept-package-agreements --accept-source-agreements --disable-interactivity 2>$null | Out-Null } catch {}
    Atualiza-Path
    if (Resolve-Python) { return }
  }
  # 2) download direto do python.org (nao depende de winget nem da Store)
  $ver = "3.12.7"
  $arch = if ($env:PROCESSOR_ARCHITECTURE -match 'ARM64') { "arm64" } else { "amd64" }
  $url = "https://www.python.org/ftp/python/$ver/python-$ver-$arch.exe"
  $exe = Join-Path $env:TEMP "python-$ver-$arch.exe"
  Write-Host "Baixando o Python $ver de python.org..." -ForegroundColor Cyan
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    Write-Host "Instalando o Python (silencioso, para todos os usuarios)..." -ForegroundColor Cyan
    Start-Process -FilePath $exe -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","Include_launcher=1","Include_test=0" -Wait
    Atualiza-Path
  } catch { Write-Host "Falha ao baixar/instalar o Python: $_" -ForegroundColor Yellow }
}

$P = Resolve-Python
if (-not $P) {
  Write-Host "Python nao encontrado (o 'python' do sistema e apenas o atalho da Microsoft Store)." -ForegroundColor Yellow
  Install-Python
  $P = Resolve-Python
}
if (-not $P) {
  Write-Host "Nao consegui obter o Python automaticamente. Instale o Python 3.9+ e rode o INSTALAR.bat de novo:" -ForegroundColor Red
  Write-Host "  https://www.python.org/downloads/  (marque 'Add python.exe to PATH')" -ForegroundColor Red
  Write-Host "Dica: desative o atalho falso em Configuracoes > Aplicativos > Configuracoes avancadas" -ForegroundColor Red
  Write-Host "      de aplicativo > Aliases de execucao de aplicativo (desligue os 'python.exe')." -ForegroundColor Red
  exit 3
}
$Py = $P.Exe; $PyArgs = $P.Args
Write-Host "Python: $Py $($PyArgs -join ' ')" -ForegroundColor Cyan
& $Py @PyArgs -m pip install --quiet --upgrade pywin32 psutil
# pos-instalacao do pywin32: copia pywintypes/pythoncom p/ system32 e registra o
# host de servico. O modulo nao e importavel por -m; achamos o script e rodamos.
try {
  $scriptsDir = (& $Py @PyArgs -c "import sysconfig;print(sysconfig.get_path('scripts'))").Trim()
  $post = Join-Path $scriptsDir "pywin32_postinstall.py"
  if (Test-Path $post) { & $Py @PyArgs $post -install -silent | Out-Null }
  else { Write-Warning "pywin32_postinstall.py nao encontrado em $scriptsDir (o servico pode ainda assim iniciar)." }
} catch { Write-Warning "pos-instalacao do pywin32 falhou: $_" }

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
# So SYSTEM e Administradores leem o hash. Usa SIDs universais (independem do
# idioma do Windows: 'Administradores' em pt-BR, 'Administrators' em en-US, etc.).
# Passo de defesa em profundidade: se falhar, NAO aborta a instalacao do servico.
try {
  $acl = Get-Acl $reg
  $acl.SetAccessRuleProtection($true,$false)
  $sids = @(
    (New-Object Security.Principal.SecurityIdentifier ([Security.Principal.WellKnownSidType]::LocalSystemSid, $null)),
    (New-Object Security.Principal.SecurityIdentifier ([Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null))
  )
  foreach ($sid in $sids) {
    $acl.AddAccessRule((New-Object Security.AccessControl.RegistryAccessRule($sid,"FullControl","ContainerInherit,ObjectInherit","None","Allow")))
  }
  Set-Acl $reg $acl
} catch {
  Write-Warning "Nao foi possivel endurecer a ACL do registro ($_). O servico segue instalado; a senha continua protegendo."
}

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
