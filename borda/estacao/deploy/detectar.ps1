# GerencIA - script de DETECCAO para Intune (Win32 app).
# Saida 0 + texto = instalado; saida 1 = nao instalado.
$Versao = "0.2.0"
$svc = Get-Service -Name "GerenciaSensor" -ErrorAction SilentlyContinue
$reg = (Get-ItemProperty "HKLM:\SOFTWARE\GerencIA" -Name SensorVersao -ErrorAction SilentlyContinue).SensorVersao
if ($svc -and $reg -eq $Versao) { Write-Output "GerencIA Sensor $Versao instalado"; exit 0 }
exit 1
