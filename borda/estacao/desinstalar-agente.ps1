<#
  Remove o agente de estação do usuário logado: tira o atalho da inicialização
  e encerra o processo do agente. O SQLite local (auditoria.sqlite) é mantido;
  apague-o à mão se quiser zerar a cópia local.
#>
$ErrorActionPreference = "SilentlyContinue"
$startup = [Environment]::GetFolderPath("Startup")
Remove-Item (Join-Path $startup "Rastro Agente.lnk") -Force
# encerra pythonw/python rodando agente.py
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "agente\.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "Agente de estacao removido da inicializacao do usuario:" $env:USERNAME
