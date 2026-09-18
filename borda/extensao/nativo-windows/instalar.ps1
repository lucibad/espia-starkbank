<#
  Instala o host de identidade do Rastro no Windows (por usuário, sem admin).

  Registra o host para Chrome, Edge e Firefox, apontando para lancar.bat nesta
  mesma pasta. Rode UMA VEZ POR USUÁRIO do Windows que for testar — cada
  usuário registra em HKCU (o próprio perfil), e é por isso que %USERNAME%
  reportado passa a ser o usuário certo.

  Uso (no PowerShell, dentro desta pasta):
    # Chrome/Edge precisam do ID que aparece em chrome://extensions (modo dev):
    .\instalar.ps1 -ChromiumIds "abcdefghijklmnopabcdefghijklmnop"
    # Firefox não precisa de ID (usa o id fixo do manifesto).

  Vários IDs (Chrome e Edge geram IDs diferentes p/ a mesma pasta):
    .\instalar.ps1 -ChromiumIds "id_do_chrome","id_do_edge"
#>
param(
  [string[]] $ChromiumIds = @()
)

$ErrorActionPreference = "Stop"
$pasta   = Split-Path -Parent $MyInvocation.MyCommand.Path
$lancar  = Join-Path $pasta "lancar.bat"
$nome    = "com.starkbank.rastro.identidade"
$geckoId = "rastro@starkbank.desafio2"

# ---- manifesto para Chrome/Edge (allowed_origins com os IDs informados) ----
$origins = @($ChromiumIds | ForEach-Object { "chrome-extension://$_/" })
$mChrome = [ordered]@{
  name           = $nome
  description    = "Rastro - identidade do usuario do Windows"
  path           = $lancar
  type           = "stdio"
  allowed_origins = $origins
}
$arqChrome = Join-Path $pasta "manifesto-chromium.json"
$mChrome | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $arqChrome

# ---- manifesto para Firefox (allowed_extensions com o id fixo) ----
$mFox = [ordered]@{
  name              = $nome
  description       = "Rastro - identidade do usuario do Windows"
  path              = $lancar
  type              = "stdio"
  allowed_extensions = @($geckoId)
}
$arqFox = Join-Path $pasta "manifesto-firefox.json"
$mFox | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $arqFox

function Registrar($base, $arq) {
  $key = "$base\$nome"
  New-Item -Path $key -Force | Out-Null
  Set-ItemProperty -Path $key -Name "(Default)" -Value $arq
}

# Chrome e Edge usam o manifesto chromium; Firefox o dele.
Registrar "HKCU:\Software\Google\Chrome\NativeMessagingHosts"   $arqChrome
Registrar "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts"  $arqChrome
Registrar "HKCU:\Software\Mozilla\NativeMessagingHosts"         $arqFox

Write-Host "Host de identidade registrado para o usuario:" $env:USERNAME
Write-Host "  lancador : $lancar"
if ($ChromiumIds.Count -eq 0) {
  Write-Warning "Nenhum ID de extensao Chromium informado. Chrome/Edge nao vao"
  Write-Warning "conseguir chamar o host ate voce rodar de novo com -ChromiumIds."
  Write-Warning "Pegue o ID em chrome://extensions (Modo do desenvolvedor)."
} else {
  Write-Host "  Chrome/Edge liberados para:" ($ChromiumIds -join ", ")
}
Write-Host "Firefox liberado para a extensao id:" $geckoId
Write-Host "Feche e reabra o navegador para ele reler o registro."
