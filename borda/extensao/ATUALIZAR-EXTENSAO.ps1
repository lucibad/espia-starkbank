#Requires -Version 5.0
<#  GerencIA - atualiza a extensao de borda na estacao (nao precisa de admin).
    Baixa a versao mais recente do GitHub, extrai no caminho fixo e CONFERE que
    e a build certa (com captura de conteudo). No fim, mostra o que recarregar.

    Uso (PowerShell):
      powershell -ExecutionPolicy Bypass -File .\ATUALIZAR-EXTENSAO.ps1
      # ou, offline, apontando um .zip ja baixado:
      powershell -ExecutionPolicy Bypass -File .\ATUALIZAR-EXTENSAO.ps1 -Zip C:\caminho\ext.zip
#>
param(
  [string]$Zip = "",
  [string]$Dest = "C:\GerencIA\extensao",
  [string]$Url  = "https://raw.githubusercontent.com/lucibad/espia-starkbank/main/borda/pacotes/gerencia-extensao-chrome-edge-0.2.1.zip"
)
$ErrorActionPreference = "Stop"

if (-not $Zip) {
  $Zip = Join-Path $env:TEMP "gerencia-extensao.zip"
  Write-Host "Baixando a extensao mais recente..." -ForegroundColor Cyan
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
}

Write-Host "Extraindo para $Dest ..." -ForegroundColor Cyan
if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Dest -Force

# --- Conferencia: e a build certa? ---
$manifest = Join-Path $Dest "manifest.json"
$content  = Join-Path $Dest "content.js"
if (-not (Test-Path $manifest) -or -not (Test-Path $content)) {
  Write-Host "ERRO: arquivos da extensao nao encontrados em $Dest." -ForegroundColor Red; exit 1
}
$versao = (Get-Content $manifest -Raw | Select-String '"version"\s*:\s*"([^"]+)"').Matches.Groups[1].Value
$temConteudo = (Select-String -Path $content -Pattern "enviar_conteudo: true" -Quiet)
$temResposta = (Select-String -Path $content -Pattern "observarResposta" -Quiet)

Write-Host ""
Write-Host "Conferencia da build:" -ForegroundColor Cyan
Write-Host ("  versao          : {0}" -f $versao)
Write-Host ("  captura conteudo: {0}" -f ($(if($temConteudo){"SIM"}else{"NAO"})))
Write-Host ("  captura resposta: {0}" -f ($(if($temResposta){"SIM"}else{"NAO"})))
if (-not ($temConteudo -and $temResposta)) {
  Write-Host "AVISO: esta build NAO captura conteudo. Baixe a 0.2.1 e rode de novo." -ForegroundColor Yellow
} else {
  Write-Host "OK - build com captura de conteudo (prompt + resposta)." -ForegroundColor Green
}

Write-Host ""
Write-Host "AGORA, no navegador (a extensao NAO atualiza sozinha):" -ForegroundColor Cyan
Write-Host "  EDGE/CHROME:" -ForegroundColor White
Write-Host "    1) edge://extensions  (Modo do desenvolvedor LIGADO)"
Write-Host "    2) Remova o GerencIA antigo"
Write-Host "    3) 'Carregar sem pacote' -> $Dest"
Write-Host "    4) No cartao deve aparecer a versao $versao; clique em 'Recarregar'"
Write-Host "  FIREFOX:" -ForegroundColor White
Write-Host "    1) about:debugging#/runtime/this-firefox"
Write-Host "    2) 'Carregar extensao temporaria' -> selecione $Dest\manifest.json"
Write-Host ""
Write-Host "Depois: de F5 na aba do ChatGPT/Gemini antes de digitar." -ForegroundColor Cyan
Write-Host "Confira o coletor no popup da extensao: deve ser http://macbook-pro.local:8765"
