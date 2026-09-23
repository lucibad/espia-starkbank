# GerencIA · Implantação em massa (GPO / Intune)

Instalação **silenciosa**, sem prompts, para distribuir o agente-sensor a muitas
estações de uma vez. Os scripts rodam como **SYSTEM** (é como GPO e Intune executam)
ou como Administrador. O agente é **copiado para uma pasta fixa local**
(`C:\Program Files\GerencIA\Agente`) e registrado como serviço a partir dela.

## Scripts

| Script | Para quê |
|---|---|
| `gerar-hash-senha.ps1` | Gera o hash PBKDF2 da senha **antes**, para o texto não trafegar no script de distribuição. |
| `instalar-silencioso.ps1` | Instala sem prompts. Retorna 0 = ok, ≠0 = falha. Loga em `C:\ProgramData\GerencIA\instalacao.log`. |
| `desinstalar-silencioso.ps1` | Remove sem senha — a gestão central é a autoridade (a senha protege contra o usuário/admin **local**, não contra a política corporativa). |
| `detectar.ps1` | Detecção para o Intune (Win32 app): saída 0 = instalado. |

## Passo 0 — gere o hash da senha (uma vez, numa máquina sua)

```powershell
.\gerar-hash-senha.ps1 -Senha "MinhaSenhaForte"
```
Ele imprime `-SenhaHashB64 "..." -SaltB64 "..." -IterParam 120000`. Guarde essa linha;
a senha em texto **não** vai para o GPO/Intune.

## GPO (Startup Script — roda como SYSTEM no boot)

1. Copie a pasta `GerencIA-Agente-Estacao` para um compartilhamento lido pelas máquinas
   (ex.: `\\servidor\deploy\GerencIA-Agente-Estacao`).
2. **Group Policy Management** → GPO → *Computer Configuration ▸ Policies ▸ Windows Settings
   ▸ Scripts ▸ Startup* → **PowerShell Scripts** → Add.
3. Script Name:
   `\\servidor\deploy\GerencIA-Agente-Estacao\deploy\instalar-silencioso.ps1`
   Parameters:
   ```
   -Coletor http://10.211.55.2:8765 -SenhaHashB64 "..." -SaltB64 "..." -IterParam 120000
   ```
4. Requisito nas estações: **Python 3.9+** (distribua-o pela mesma GPO se necessário; o
   script instala `pywin32` e `psutil` sozinho). A máquina instala no próximo boot.

Remoção: troque o script de Startup por `desinstalar-silencioso.ps1` (sem parâmetros),
ou rode-o uma vez via *Scheduled Task* como SYSTEM.

## Intune (Aplicativo Win32)

1. Empacote a pasta com o **Microsoft Win32 Content Prep Tool**:
   ```
   IntuneWinAppUtil.exe -c .\GerencIA-Agente-Estacao -s deploy\instalar-silencioso.ps1 -o .\saida
   ```
   (gera o `.intunewin` — a ferramenta roda no Windows; não é gerada aqui.)
2. No Intune, **Apps ▸ Windows ▸ Add ▸ Windows app (Win32)** e configure:
   - **Install command:**
     ```
     powershell.exe -ExecutionPolicy Bypass -File deploy\instalar-silencioso.ps1 -Coletor http://10.211.55.2:8765 -SenhaHashB64 "..." -SaltB64 "..." -IterParam 120000
     ```
   - **Uninstall command:**
     ```
     powershell.exe -ExecutionPolicy Bypass -File deploy\desinstalar-silencioso.ps1
     ```
   - **Install behavior:** System.
   - **Detection rule → Use a custom detection script:** envie `deploy\detectar.ps1`.
   - **Requirements:** Windows 10/11 64-bit; Python 3.9+ presente (ou distribua o Python
     como dependência).

## O que fica gravado na estação

- Serviço `GerenciaSensor` (**GerencIA · Sensor de Rede**), início automático, como LocalSystem.
- `HKLM\SOFTWARE\GerencIA`: `SensorSalt`, `SensorHash`, `SensorIter` (senha), `SensorVersao`,
  `SensorInstalar` (pasta) — legíveis só por SYSTEM/Admin.
- Variáveis de máquina `GERENCIA_COLETOR`, `GERENCIA_INTERVALO`.
- Logs em `C:\ProgramData\GerencIA\`.

## Honestidade
A senha protege contra **usuário comum e admin local casual**. A gestão central
(GPO/Intune, como SYSTEM) é a autoridade e desinstala sem senha — por isso o
`desinstalar-silencioso.ps1` não a pede. Blindagem absoluta contra um admin local
determinado exige MDM/EDR com proteção em kernel.
