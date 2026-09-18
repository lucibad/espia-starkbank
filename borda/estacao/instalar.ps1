<#
  Instalador raiz do Rastro para Windows. Orquestra os dois modos.

  MODO ESTAÇÃO (recomendado — "um agente por máquina"):
    O agente roda nesta máquina, lê o usuário do Windows sozinho, classifica
    localmente e encaminha ao coletor central (o Mac). A extensão aponta para
    o agente local (127.0.0.1). Não precisa do host de identidade nativo.

      .\instalar.ps1 -Modo estacao
      .\instalar.ps1 -Modo estacao -Coletor "http://10.211.55.2:8765"

  MODO EXTENSAO (Mac central):
    Só a extensão + o host de identidade nativo nesta máquina; o cérebro fica
    no Mac. Precisa do(s) ID(s) da extensão (de chrome://extensions).

      .\instalar.ps1 -Modo extensao -ChromiumIds "id_do_chrome","id_do_edge"

  Em ambos os modos, CARREGAR a extensão no navegador é manual (os navegadores
  não deixam um script instalar extensão sem loja) — os passos são impressos.
#>
param(
  [ValidateSet("estacao", "extensao")]
  [string]   $Modo = "estacao",
  [string]   $Coletor = "http://10.211.55.2:8765",
  [int]      $Porta = 8765,
  [string[]] $ChromiumIds = @()
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path

function PassosExtensao {
  Write-Host ""
  Write-Host "=== Carregar a extensao (manual, uma vez por navegador) ==="
  Write-Host "Chrome/Edge: abra chrome://extensions (ou edge://extensions),"
  Write-Host "  ligue 'Modo do desenvolvedor', 'Carregar sem compactacao' e"
  Write-Host "  aponte para a pasta:  $(Join-Path $raiz "..\extensao")"
  Write-Host "Firefox: about:debugging#/runtime/this-firefox -> 'Carregar"
  Write-Host "  complemento temporario' -> selecione extensao\manifest.json"
  Write-Host ""
}

if ($Modo -eq "estacao") {
  Write-Host ">>> Modo ESTACAO para o usuario: $env:USERNAME"
  & (Join-Path $raiz "instalar-agente.ps1") -Coletor $Coletor -Porta $Porta
  PassosExtensao
  Write-Host "No popup da extensao, aponte o agente para:  http://127.0.0.1:$Porta"
  Write-Host "(Neste modo NAO instale o host de identidade nativo.)"
}
elseif ($Modo -eq "extensao") {
  Write-Host ">>> Modo EXTENSAO (Mac central) para o usuario: $env:USERNAME"
  & (Join-Path $raiz "..\extensao\nativo-windows\instalar.ps1") -ChromiumIds $ChromiumIds
  PassosExtensao
  Write-Host "No popup da extensao, aponte o agente para:  $Coletor"
}
