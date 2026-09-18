# EspIA

**Rastreabilidade e governança de informações em ferramentas de IA.**
Desafio 2 · Stark Bank.

Roda sobre a **base oficial do desafio** — `Base de Dados — Starkbank apurada 15-09.xlsx`,
com 650 eventos, 160 alertas, 8 ferramentas, 20 tipos de informação, 72 usuários e 14 regras.

> Todos os dados são fictícios, conforme declarado na própria planilha.

---

## Os três números que resumem o projeto

| | |
|---|---|
| **15/15** | casos do gabarito oficial reproduzidos, sem exceção escrita para nenhum deles |
| **10/10** | indicadores que recalculamos batem com a apuração que a própria planilha fez |
| **7/10** | indicadores **declarados** pela organização divergem do que a base mostra |

O primeiro diz que o motor está certo. O segundo diz que a nossa conta está certa.
O terceiro é o que a empresa precisa saber.

---

## A tese

Quase toda solução para este problema rastreia **usos de IA** — "o usuário X acessou a
ferramenta Y às 14h". A EspIA rastreia **informação**: *"Chave/API secret apareceu em
5 ferramentas, com 30 pessoas, 35 vezes — e 3 delas em IA pública"*.

Isso é linhagem de dado, não log de atividade. A busca começa pelo documento, não pelo
funcionário — que é exatamente como a pergunta norteadora do desafio está escrita.

E há uma segunda tese, que a base oficial tornou possível demonstrar:
**a ferramenta não confia na classificação que recebeu.** Ela reaplica as regras, recalcula
os indicadores e audita a rotulagem existente. Foi assim que encontrou os seis achados
descritos abaixo.

---

## O que a auditoria encontrou na base

| | Achado | Impacto |
|---|---|---|
| **A-01** | 38 eventos citam R08 ou R09, cujo texto diz "em ferramenta aprovada" — mas ocorreram em IA Pública A ou B | O nível está certo; a trilha de auditoria, não. Um auditor lendo o registro é induzido a erro |
| **A-02** | 18 eventos fechados com R01/R02 quando a política tem regra específica (R04, R05, R06) | R01 manda "investigar". R04 manda "aplicar resposta de privacidade". A obrigação de LGPD some do registro |
| **A-03** | 8 eventos usaram o Gerador de Imagens com conteúdo Interno ou Confidencial | A ferramenta é "Aprovada apenas para conteúdo público". Deveriam ser Alto por R10 e virar alerta. Não viraram |
| **A-04** | 6 das 14 regras nunca são acionadas | A política aparenta ter catorze controles e opera com oito |
| **A-05** | 47 alertas marcados "Tratado", nenhum com data de tratamento | O indicador de SLA de 24h não é apurável a partir da base |
| **A-06** | 38 eventos numa combinação que nenhuma regra cobre (Interna/Pública em ferramenta não aprovada) | Lacuna de política. A EspIA propõe R15 para fechá-la |

---

## Como o motor decide

As catorze regras vêm da planilha e não estão reescritas no código — os níveis e as ações
são lidos da aba `Regras_Risco`. O que a EspIA acrescenta é a **ordem de precedência**,
porque política escrita em linguagem natural se sobrepõe, e é essa ordem que Compliance audita.

```
R14  rastreabilidade insuficiente → REVISAR
R13  classificação ausente → REVISAR
R03  credencial, em qualquer ferramenta → Crítico
R05  financeiro não divulgado em pública → Crítico
R04  dado pessoal em pública → Crítico (aciona resposta de privacidade)
R06  código confidencial em pública → Alto
R02  crítica em não aprovada → Crítico
R01  confidencial em não aprovada → Crítico
R11  volume elevado → Alto
R10  crítica em aprovada, ou fora da finalidade → Alto
R07  confidencial em aprovada → Médio
R09  interna em aprovada → Baixo
R08  pública em aprovada → Baixo
R12  horário — contexto, nunca eleva sozinho
```

Três decisões que essa ordem codifica:

1. **Rastreabilidade antes de tudo.** Sem usuário, ferramenta ou data confiáveis, classificar
   risco é inventar. O motor devolve REVISAR — que é o que o caso CV13 espera.
2. **A regra mais específica descreve; a mais severa decide.** Código confidencial numa IA
   pública dispara R01 (Crítico) e R06 (Alto). O nível é Crítico, e as duas ficam registradas,
   porque R06 é o que diz que há exposição de propriedade intelectual em jogo.
3. **Contexto é evidência, não agravante.** R12 nunca eleva sozinha — é o que a própria regra diz.

**As regras específicas vêm antes das genéricas** — R05, R04 e R06 antes de R02 e R01. Elas dão
o mesmo nível, mas obrigam ação diferente: R04 manda aplicar resposta de privacidade, R01 manda
apenas investigar. Citar a genérica faz a obrigação de LGPD sumir do registro.

Resultado, medido contra os 650 eventos:

| | |
|---|---|
| Mesmo **nível** de risco que a base | 642/650 = **98,8%** |
| Mesma **regra** citada | 626/650 = **96,3%** |

E as divergências não são ruído — são exatamente os achados de auditoria. As 8 de nível são o
A-03; das 24 de regra, 16 são o A-02 (regra específica no lugar da genérica) e 8 são o A-03.

---

## Como rodar

**Não é preciso instalar nada.** Basta Python 3.9 ou superior.

```bash
python3 run.py gerar       # lê a planilha, aplica as regras, audita, monta o painel (~2 s)
python3 run.py painel      # abre o painel no navegador
python3 run.py coletor     # recebe as capturas do espia-borda e regenera o painel a cada uma
python3 testes.py          # 37 verificações
python3 testes_paridade.py # confere o motor Python contra o motor do navegador
```

### Legado e presente, um painel só

A planilha é a **carga legada** — o que a empresa já tinha registrado. As capturas do
coletor de borda (`espia-borda`, a extensão de navegador) são o **presente**. As duas
entram na mesma tabela `eventos`, passam pelo mesmo motor de regras e aparecem no mesmo
painel, distinguidas pela coluna `origem` (`Captura ao vivo (espia-borda)`).

```bash
ESPIA_BIND=0.0.0.0 python3 run.py coletor   # aberto à rede: recebe das estações (Parallels, LAN)
```

O `gerar` **não apaga mais** o `dados/espia.db`: recria só as tabelas derivadas, e a tabela
`capturas` sobrevive. A identidade de quem usou a IA é resolvida **no coletor**, nunca pela
página: local pelo usuário do SO; remota pelo que o agente de estação ou o host nativo do
Windows informou (`agente-local` / `nativo`); um nome só declarado fica marcado como tal.
Concordância e auditoria continuam medidas **só sobre o legado** — captura não tem risco
declarado para divergir, e os indicadores declarados são da planilha.

### O painel

# ┌──────────────────────────────────────────────────────────┐
# │  Abra  dashboard/painel.html  — dois cliques, e pronto.  │
# └──────────────────────────────────────────────────────────┘

Um arquivo só, com os dados dentro. Funciona offline e vai por e-mail inteiro.
O `index.html` ao lado **não é o painel** — é o corpo da versão publicada na web.

**Sete vistas:** Panorama · Rastrear (a busca reversa) · Alertas (com cadeia de evidências) ·
**Auditoria** · **Validação** · Política · Inventário.

**Vista Captura** (só servida pelo coletor, `run.py coletor`) — o painel de administração da
captura ao vivo: **Usuário × IA × tipo de alerta** (cada captura avaliada pelo motor, com a
identidade marcada como verificada ou não), o pivot **Quem usou o quê** (contagem e pior risco por
par usuário/ferramenta) e o **Inventário das IAs monitoradas**, editável só na máquina do coletor.
Cadastrar um domínio ou mudar seu status (Aprovada / condicional / só conteúdo público / Não
aprovada) **reclassifica as capturas daquela ferramenta pelo mesmo motor** na regeneração seguinte —
aprovar o ChatGPT leva suas capturas de “Crítico R02” a “Alto R10”, pela própria precedência do EspIA.
O inventário é a autoridade sobre nome e status das ferramentas que a planilha não lista (o
`dominios_monitorados_url` da política de GPO); as oito da planilha aparecem ao lado, somente leitura.
Aberto como arquivo, sem coletor, a vista explica como subir o servidor e aponta para Alertas.

**Recorte compartilhado** — no Panorama e em Alertas há filtros de **risco (criticidade), área,
usuário e período** (De/Até). É um só estado: o que se filtra numa vista vale na outra. No Panorama, todos os
blocos recalculam sobre o recorte — KPIs, série diária (montada no navegador a partir dos
eventos filtrados), área × sensibilidade, ferramentas e alertas por situação. Concordância
com a base e validação seguem globais, porque são medidas da base legada, não do recorte.

### O console de políticas

`dashboard/console-politicas.html` é a aplicação que Compliance usa para editar a política.
Precisa de `dados.js` e `motor.js` na mesma pasta — os três vêm no pacote.

O que ele faz que um editor comum não faz:

- **Simula antes de publicar.** Toda mudança é aplicada aos 650 eventos na hora, mostrando
  quantos mudam de nível, quantos viram alerta e quantos saem da fila.
- **Trava no gabarito.** Se a política editada deixar de reproduzir algum dos 15 casos oficiais,
  a publicação é bloqueada e o console diz qual caso quebrou.
- **Versiona.** Cada publicação guarda autor, data, nota e o diff, com restauração em um clique.

O motor de regras roda duas vezes no projeto — em Python, no pipeline, e em JavaScript, no
console. `python3 testes_paridade.py` prova que os dois concordam evento a evento; se
divergissem, a simulação estaria mentindo.

### E como isso é instalado no banco

```bash
cd implantacao
./bin/preflight.sh --perfil piloto        # o ambiente está pronto?
./bin/instalar.sh --perfil piloto --onda 0
./bin/verificar.sh --fluxo                # um evento de ponta a ponta
make lint                                 # verifica os próprios artefatos
```

Três servidores, um PostgreSQL, uma VLAN sem saída para a internet e um host
pequeno na DMZ que manda as notificações. Nenhuma GPU, nenhuma nuvem. O runbook
inteiro está em `docs/EspIA-implantacao.md`; o pacote executável, em
`implantacao/`.

Duas travas que valem citar na apresentação:

- `make gabarito` **bloqueia a liberação do console** se a instalação real não
  reproduzir os 15 casos oficiais.
- `make isolamento` testa a saída para a internet de dentro de cada contêiner —
  e **passa quando a saída falha.**

### Consultas pelo terminal

```bash
python3 run.py panorama                      # os números do período
python3 run.py validar                       # os 15 casos oficiais
python3 run.py auditar                       # indicadores e achados
python3 run.py regras                        # quantas vezes cada regra dispara
python3 run.py rastrear "Chave/API secret"   # ← A BUSCA REVERSA
python3 run.py evidencia EVT-00434           # por que este evento é risco
python3 run.py alertas Crítico 20
python3 run.py exposicao
```

O banco é SQLite comum — `sqlite3 dados/espia.db` responde qualquer corte que o painel
não tenha. Útil se a banca pedir algo na hora.

### A camada de captura

```bash
python3 run.py classificar "texto que iria para a IA"
```

Na base oficial, as colunas `Tipo informação` e `Sensibilidade` já chegam preenchidas — o
dicionário de dados diz que a origem é "Classificador/DLP". Este comando demonstra a camada
que produz esse resultado automaticamente: fingerprint MinHash/SimHash contra o acervo
classificado, mais detectores de CPF, CNPJ, cartão (Luhn) e credencial. O texto analisado
nunca é gravado — só a assinatura e as contagens.

---

## Estrutura

```
base/                    A planilha oficial do desafio.

espia/
  base_oficial.py        Importa as 12 abas para o modelo interno.
  regras.py              R01–R14 com precedência declarada e cadeia de evidências.
  validacao.py           Os 15 casos do gabarito.
  auditoria.py           Indicadores recalculados + os seis achados.
  pipeline_oficial.py    Orquestração, SQLite, exportação, montagem do painel.
  captura.py             Capturas do espia-borda unificadas com o legado (tabela `capturas`).
  coletor.py             Servidor de ingestão do espia-borda (`run.py coletor`).
  consultas.py           Linhagem, exposição, alertas, evidência.
  xlsx_min.py            Leitor de XLSX embutido — o projeto roda sem pip install.
  yaml_min.py            Leitor de YAML embutido, pelo mesmo motivo.

  fingerprint.py         MinHash, SimHash, shingles, containment.   ┐ camada de captura,
  detectores.py          CPF/CNPJ/Luhn/credencial e mascaramento.   │ demonstrada por
  acervo.py, simulador.py, shadow.py, motor_risco.py, pipeline.py   ┘ run.py classificar

run.py                   CLI.
testes.py                37 verificações de sanidade.
testes_paridade.py       Paridade entre o motor Python e o do navegador.
dashboard/
  painel.html            O painel de investigação (abra este).
  console-politicas.html O console de políticas de Compliance.
  motor.js               O motor de regras portado para o navegador.
  index.html, dados.js   Corpo e dados da versão publicada na web.
docs/
  EspIA-documento-do-projeto.md   O projeto.
  EspIA-arquitetura.md            A arquitetura de implantação on-premise.
  EspIA-implantacao.md            Como isso é instalado no ambiente do banco.

implantacao/
  bin/preflight.sh       26+ verificações do ambiente. Roda antes de tudo.
  bin/instalar.sh        Instalação idempotente, por onda.
  bin/verificar.sh       Saúde · fluxo · isolamento de rede · gabarito.
  bin/backup.sh          Dump cifrado — e a restauração que prova que ele presta.
  docker-compose.yml     Núcleo, na VLAN sem saída.
  docker-compose.dmz.yml Gateway de notificação, a única peça com saída.
  sql/                   Esquema de produção, RBAC, carga inicial do piloto.
  rede/                  18 regras de firewall, prontas para o chamado.
  coletores/             DLP, SWG, extensão por GPO e MDM.
  systemd/               A instalação sem contêiner, endurecida.
```

---

## O que o desafio pede e onde está

| Requisito | Onde |
|---|---|
| Registrar quais ferramentas de IA estão sendo utilizadas | vista **Inventário** + aba Ferramentas_IA |
| Identificar quais informações são compartilhadas | vista **Rastrear** + `fingerprint.py` |
| Classificar por nível de sensibilidade | `Tipos_Informacao` + vista **Política** |
| Usuário, área, ferramenta, data e finalidade | esquema `eventos`, todas as colunas |
| Histórico que permita rastrear o fluxo | `linhagem()` + vista **Rastrear** |
| Identificar situações de risco | `regras.py` |
| Alertas para usos críticos ou fora das regras | vista **Alertas** + tabela `alertas` |
| Filtros por área, usuário, ferramenta, tipo, situação e risco | sete filtros na vista Alertas |
| Indicadores de acompanhamento | vista **Auditoria** — recalculados, não repetidos |
| Apoiar auditorias e investigações | SQLite + `evidencia()` + vista **Auditoria** |
| Evidências de por que algo é risco | cadeia de regras aplicáveis, com motivo e ação |
| A empresa define classificações e regras | tudo lido da planilha; o código não tem as regras escritas |

---

## Limites honestos

Diga estes na apresentação, antes que perguntem.

- **O fingerprint não é exercitado pela base oficial.** A planilha entrega a classificação
  pronta; a camada que a produziria é demonstrada por `run.py classificar` e pelos testes,
  não pelos 650 eventos.
- **A varredura de correspondência é linear.** Serve para o acervo de demonstração; em escala
  vira índice LSH por bandas. A matemática é a mesma.
- **Paráfrase não é detectada.** O fingerprint pega recorte, reformatação e colagem — não pega
  quem reescreve o documento com as próprias palavras.
- **R10 é aplicada como a base a aplica**, não como o texto dela diz. O texto fala em finalidade
  incompatível; a base usa a regra para informação crítica em ambiente aprovado. Mantivemos o
  comportamento da base e registramos a divergência no achado A-04.
- **Os marcos regulatórios não aparecem nesta versão.** A base oficial não tem coluna de
  enquadramento legal, e preferimos não inferir o que a planilha não afirma.
- **O fingerprint da borda ainda não casa com o acervo.** A extensão calcula MinHash/SimHash
  na máquina do usuário com FNV-1a (o navegador não tem blake2b síncrono); o acervo em Python
  usa blake2b. Assinaturas só são comparáveis com o mesmo hash — unificar essa função é o
  passo que falta para a captura responder *"de qual documento veio"*, e não só *"é sensível"*.
