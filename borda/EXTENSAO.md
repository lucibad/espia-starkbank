# Extensão de navegador — captura de uso de IA

A extensão é o **olho do agente dentro do navegador**. Ela observa quando o
usuário envia conteúdo a uma ferramenta de IA (em Chrome, Edge ou Firefox),
roda os detectores de DLP no próprio endpoint e reporta ao agente — que
identifica o usuário, classifica pela cascata e grava.

É o que fecha os 22,8% de registro manual da base: em produção, o uso é
capturado no momento em que acontece, não declarado depois.

## Esta extensão é o `espia-borda` do EspIA

O projeto oficial é o **EspIA** (`~/Downloads/espia`). A política de GPO dele
(`implantacao/coletores/extensao-gpo.json`) especifica um coletor de borda
chamado `espia-borda` — mas o código desse coletor não existia. Esta extensão
**é** esse coletor, implementado fielmente ao contrato:

| Item do contrato do EspIA | Aqui |
|---|---|
| `enviar_conteudo: false` | o texto nunca sai da máquina; vão só metadados e assinaturas |
| `detectores: cpf, cnpj, cartao_luhn, credencial` | `detectores.js` — porte de `espia/detectores.py`, **com validação de dígito e Luhn** |
| `fingerprint_local: true` | `fingerprint.js` — porte de `espia/fingerprint.py`: shingles, MinHash, SimHash calculados na borda |
| `modo: observacao` | modo atual; `mascaramento` e `bloqueio` são os próximos, nesta ordem |
| `ingestao_url …/eventos` | o coletor recebe `POST /eventos` |
| `aviso_ao_usuario` / mascarar | `mascarar()` portado ("negocie, não bloqueie") — a oferta ao usuário é o próximo passo |

**Por que um protótipo de laptop?** A ingestão de produção do EspIA é um stack
Docker (Postgres, Redis, MinIO, `espia-ingestao:8443`) com imagens de um
registro interno do banco e certificados da PKI interna. Ela **não roda fora
do ambiente do banco**. O coletor `borda/estacao/agente.py` é a versão de laptop que
prova o `espia-borda` funcionando — mesma espec, mesmos detectores, mesmo
fingerprint — para a demonstração no Parallels.

### Fase 2 — casar a assinatura com o acervo

O que o fingerprint promete de fato é responder *"de qual documento da
empresa isto veio?"*: o servidor compara a assinatura do prompt com as do
acervo catalogado (`espia/fingerprint.py: casar()`, por Jaccard/containment).
Isso ainda **não** está no coletor de laptop, e tem um detalhe técnico que
decide se vai funcionar: **paridade de hash**. O EspIA em Python usa
`blake2b`; a borda em JS usa FNV-1a 64 bits (o navegador não tem blake2b
síncrono). Assinaturas só são comparáveis se os dois lados usarem o **mesmo**
hash — então o catálogo do acervo para o coletor de laptop precisa ser gerado
com o mesmo FNV-1a da extensão (ou a extensão ganhar um blake2b em JS). O
algoritmo é o do EspIA; só a função de hash precisa ser unificada.

## Dois modos de implantação

O mesmo `agente.py` roda em dois papéis. A diferença muda quem lê a identidade
e para onde a extensão aponta.

| | **Mac central** | **Agente na estação** |
|---|---|---|
| Onde roda o cérebro | só no Mac | em cada Windows (encaminha ao Mac) |
| Na máquina Windows | extensão + host de identidade nativo | extensão + `agente.py` (pacote `rastro-agente`) |
| Extensão aponta para | `http://10.211.55.2:8765` (o Mac) | `http://127.0.0.1:8765` (agente local) |
| Identidade do usuário | host nativo lê `%USERNAME%` | o agente, rodando como o usuário, lê o SO |
| Fonte marcada | `nativo` | `agente-local` |
| Fiel à arquitetura de produção | parcial | sim — "um agente por máquina" |

O modo estação é o da doc de arquitetura: o agente classifica localmente, guarda
uma cópia e encaminha ao coletor central. É também o mais limpo para identidade —
como o agente roda na sessão do usuário, `getpass.getuser()` já é o usuário certo,
sem host nativo. Instalação em `borda/estacao/` (pacote `rastro-agente-win.zip`);
passo a passo no `LEIA-ME.txt` de lá.

## A topologia deste teste (modo Mac central)

```
   MacBook (host)                         Windows no Parallels
┌────────────────────┐   HTTP /api/ingest   ┌─────────────────────────┐
│ borda/estacao/agente.py      │◀─────────────────────│ Chrome / Edge / Firefox │
│ RASTRO_BIND=0.0.0.0│   10.211.55.2:8765   │  + extensão Rastro       │
│ SQLite, IA, config │                      │  + host de identidade    │
│ console + admin    │─────────────────────▶│  (vários usuários Win)   │
└────────────────────┘   console em          └─────────────────────────┘
                         http://10.211.55.2:8765
```

- **Mac = servidor.** Roda o agente e o console de administração.
- **Windows = estações.** Cada usuário do Windows roda os navegadores com a
  extensão. O IP do Windows é `10.211.55.x`; o Mac host, na rede compartilhada
  do Parallels, é **`10.211.55.2`** — é para lá que a extensão aponta.

## Passo a passo

### 1. No Mac — subir o coletor do EspIA aberto à rede do Parallels

O coletor central é o do **EspIA** (projeto oficial): ele grava as capturas na
mesma base da planilha e regenera o painel do EspIA a cada evento.

```bash
cd ~/Downloads/espia
ESPIA_BIND=0.0.0.0 python3 run.py coletor
```

Ele imprime os IPs alcançáveis pelas estações (Parallels primeiro). Confirme, de
dentro do Windows, que `http://10.211.55.2:8765/api/saude` responde. Se não
responder, veja **Rede** abaixo. O painel unificado (legado + capturas) fica em
`http://127.0.0.1:8765/` no Mac — o mesmo de `python3 run.py painel`.

> O `borda/estacao/agente.py` deste repositório também sabe ser coletor central
> (`RASTRO_BIND=0.0.0.0`), mas ele grava num banco próprio, separado do EspIA.
> Use-o no Mac só se quiser o console de protótipo em vez do painel oficial.

### 2. No Windows — instalar a extensão (uma vez por navegador)

Copie a pasta `borda/extensao/` para o Windows (pasta compartilhada do Parallels serve).

- **Chrome / Edge:** abra `chrome://extensions` (ou `edge://extensions`), ligue
  o **Modo do desenvolvedor**, clique **Carregar sem compactação** e aponte para
  a pasta `borda/extensao/`. Anote o **ID** que aparece.
- **Firefox:** abra `about:debugging#/runtime/this-firefox` → **Carregar
  complemento temporário** → selecione `extensao/manifest.json`.

Abra o popup da extensão e confirme o endereço do agente
(`http://10.211.55.2:8765`). O status deve ficar **conectado**.

### 3. No Windows — instalar o host de identidade (uma vez POR USUÁRIO)

Sem isso, a extensão não sabe o usuário do Windows e cai no nome declarado
(falsificável). O host lê `%USERNAME%` e devolve ao navegador.

Requer **Python no Windows**. No PowerShell, dentro de `extensao/nativo-windows/`:

```powershell
# Chrome/Edge exigem o(s) ID(s) da extensão (do passo 2):
.\instalar.ps1 -ChromiumIds "ID_do_chrome","ID_do_edge"
```

Feche e reabra o navegador. No popup, **Usuário** deve aparecer em verde
(fonte: nativo). Repita o `instalar.ps1` logado como cada usuário do Windows
que for testar — cada um registra no próprio perfil (HKCU), e é assim que
`Usuário Fictício 05` e os demais aparecem corretamente atribuídos.

### 4. No Mac — administrar

Abra `http://10.211.55.2:8765` (ou `http://127.0.0.1:8765` no próprio Mac). No
rodapé aparece a área **Administração**, visível só no modo local:

- **Usos de IA capturados** — cada envio que os agentes reportam, em tempo real:
  hora, usuário do Windows, ferramenta (⚠ não aprovada / ✓ aprovada), tipo,
  sensibilidade e risco.
- **Inventário de ferramentas** — o admin marca o que é aprovado. A mudança
  vale para os próximos eventos. Editável **só na máquina do agente** — um
  endpoint remoto não altera a política (retorna 403).

## Identidade — o que é confiável

| Situação | Fonte | Confiável? |
|---|---|---|
| Host nativo instalado (Windows) | `%USERNAME%` lido pelo host | sim — a página não edita |
| Sem host nativo | nome declarado no popup | não — só para teste |
| Console aberto no próprio Mac | usuário do SO do Mac | sim (mas é o admin, não o usuário Windows) |

O agente, ao receber um evento **remoto**, confia no usuário que o host nativo
do endpoint informou — ele não tem como ler o usuário de outra máquina. Essa é
a mudança de fronteira em relação ao modo 100% local: a confiança passa a ser
no endpoint. Em produção isso se sustenta com rede corporativa e/ou mTLS entre
agente e coletor central.

## Privacidade — o que sai da máquina

Os detectores (`detectores.js`) rodam **antes** de qualquer envio e mascaram o
que é sensível. O que trafega:

- domínio, ferramenta, forma de uso, volume, título da aba
- nomes dos padrões detectados e a contagem (ex.: `{"api_key":1}`)
- uma **prévia de ~100 caracteres com os trechos sensíveis mascarados** (`••••`)

O texto completo do prompt **nunca** é enviado. Um log de auditoria que copia o
segredo seria mais uma cópia do segredo.

## Rede (Parallels)

- Se `http://10.211.55.2:8765` não abre do Windows: confirme que o agente subiu
  com `RASTRO_BIND=0.0.0.0` e que o Firewall do macOS permite conexões de
  entrada para o Python (Ajustes → Rede → Firewall).
- O IP `10.211.55.2` é o padrão da rede **Compartilhada** do Parallels. Se o
  Windows estiver em rede **Bridge**, use o IP do Mac na LAN; o agente imprime
  um palpite ao subir com `RASTRO_BIND=0.0.0.0`.

## Limitações honestas

- **Captura genérica por heurística.** A extensão detecta envio por Enter,
  clique em botão de enviar e colagem grande. Sites de IA mudam o DOM com
  frequência; algum envio pode escapar ou duplicar (há uma janela de 800 ms
  anti-duplicação). Não é um gancho oficial de cada produto.
- **Carga temporária.** Carregada em modo desenvolvedor/temporário, some ao
  reiniciar o Firefox e fica marcada como não confiável no Chrome. Distribuição
  real é por política de grupo (arquivo `.crx`/assinado), fora do escopo do teste.
- **Não bloqueia nada.** É visibilidade e governança, não prevenção. Bloqueio
  ativo continua fora do escopo do Sprint.
