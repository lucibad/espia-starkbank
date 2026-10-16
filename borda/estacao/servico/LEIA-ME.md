# GerencIA · Sensor de Rede — serviço do Windows

Agente que fica na **máquina do usuário** e registra, para governança, **quando a
máquina fala com uma ferramenta de IA — de qualquer programa**, não só do
navegador. Complementa a extensão: a extensão vê o **conteúdo** digitado numa IA
no navegador; o sensor vê a **conexão** (metadado) de qualquer app — ChatGPT de
desktop, Cursor, um script, o Copilot do Windows.

## O que ele vê e o que não vê (sem meia-verdade)

| Vê | Não vê |
|---|---|
| Que a máquina abriu conexão com um endpoint de IA | O **conteúdo** — o tráfego é TLS |
| Qual **ferramenta** (por índice de IPs + cache de DNS) | O texto do prompt / a resposta |
| Qual **processo** (`cursor.exe`, `chrome.exe`, …) | (só metadado; ler conteúdo exigiria MITM, que não fazemos) |
| **Usuário logado** no SO e a **máquina** | |

Três sinais somados, nenhum precisa interceptar tráfego:
1. **Índice de IPs** — resolve os domínios de IA para os IPs atuais e casa as conexões.
2. **Cache de DNS do Windows** (`ipconfig /displaydns`) — prova que a máquina consultou o nome.
3. **Processo dono** da conexão (PID → nome do `.exe`).

Resíduo honesto: um IP de CDN compartilhado pode gerar falso-positivo; cada evento
carrega o sinal que o gerou (`via`: `ip`, `dns`, `ip+dns`) e o coletor trata
metadado sem risco declarado.

## Instalar (como Administrador)

```powershell
powershell -ExecutionPolicy Bypass -File .\instalar-servico.ps1 -Coletor http://10.211.55.2:8765
```

Pede uma **senha** (guardada como PBKDF2-SHA256 em `HKLM\SOFTWARE\GerencIA`,
legível só por SYSTEM/Admin). Instala pywin32 + psutil, registra o serviço como
**LocalSystem**, início automático, reinício se cair, e endurece a ACL.

## Antivírus / Windows Defender

O agente roda um Python como serviço LocalSystem que lê conexões de rede
(`netstat`/psutil) e o cache de DNS. Alguns antivírus — o Defender incluído —
podem marcar esse comportamento como suspeito e **bloquear o serviço**. O jeito
seguro de evitar isso **sem desligar a proteção** é uma **exclusão de pasta**
para o diretório onde o pacote do agente foi instalado (ex.: `C:\GerencIA`):

```powershell
# Como Administrador, na máquina (ajuste o caminho para onde o pacote foi copiado)
Add-MpPreference -ExclusionPath "C:\GerencIA"
Add-MpPreference -ExclusionProcess "python.exe"      # opcional: o processo do agente
```

Para conferir o que já está excluído:

```powershell
(Get-MpPreference).ExclusionPath
(Get-MpPreference).ExclusionProcess
```

**Em massa (GPO/Intune):** a mesma exclusão existe como política — *Computer
Configuration → Administrative Templates → Windows Components → Microsoft
Defender Antivirus → Exclusions → Path Exclusions* (GPO), ou um perfil
*Endpoint security → Antivirus → Exclusions* (Intune). Distribua a exclusão
**junto** com o pacote do agente, antes de ligar o serviço.

> **Alternativa só para teste** — desliga a proteção em tempo real da máquina
> inteira (não recomendado em produção, reduz a segurança de tudo):
> ```powershell
> Set-MpPreference -DisableRealtimeMonitoring $true    # reverter: $false
> ```
> Prefira sempre a exclusão de pasta: ela mantém o antivírus ativo para o resto
> da estação e cobre só o agente.

## Operar

```powershell
.\gerenciar-servico.ps1 -Acao status                      # livre
.\gerenciar-servico.ps1 -Acao pausar      -Senha ******   # exige senha
.\gerenciar-servico.ps1 -Acao continuar   -Senha ******
.\gerenciar-servico.ps1 -Acao parar       -Senha ******
.\gerenciar-servico.ps1 -Acao desinstalar -Senha ******
```

## Até onde a senha protege (honestidade)

- **Usuário comum** (os usuários de teste do Windows): a ACL do serviço **não
  permite** parar nem pausar. Sem chance.
- **Administrador casual**: `sc stop` funciona para admin, mas o caminho
  sancionado é o `gerenciar-servico.ps1`, que **exige a senha**. É a trava pedida.
- **Administrador determinado** (com SYSTEM, safe mode, ou reescrevendo a ACL):
  ainda consegue remover. Blindagem **absoluta** contra o próprio admin da máquina
  exige MDM/EDR com proteção em kernel — fora do escopo deste protótipo. O que
  entregamos eleva a barra de "qualquer um desliga" para "só quem tem a senha".

## Testar sem instalar serviço

```powershell
python sensor.py testar     # uma varredura, imprime o que casou
python sensor.py rodar      # laço em primeiro plano
```
