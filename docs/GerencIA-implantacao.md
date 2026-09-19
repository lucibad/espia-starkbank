# GerencIA — Implantação

**Como isso é instalado no ambiente do banco.**
Desafio 2 · Stark Bank · Rastreabilidade e Governança de Informações em IA

> Documento operacional. A arquitetura está em `GerencIA-arquitetura.md`; aqui
> está a sequência de instalação, os chamados que precisam ser abertos e o
> critério de aceite de cada etapa.

---

## Sumário

1. [A resposta curta](#1-a-resposta-curta)
2. [O que o banco precisa providenciar](#2-o-que-o-banco-precisa-providenciar)
3. [Os três ambientes](#3-os-três-ambientes)
4. [Dia 1 — laboratório](#4-dia-1--laboratório)
5. [Semana 1 — piloto](#5-semana-1--piloto)
6. [Semanas 2 a 6 — onda 0 em produção](#6-semanas-2-a-6--onda-0-em-produção)
7. [O que muda na rede](#7-o-que-muda-na-rede)
8. [Como os coletores entram](#8-como-os-coletores-entram)
9. [Segredos, certificados e identidade](#9-segredos-certificados-e-identidade)
10. [Instalação sem contêiner](#10-instalação-sem-contêiner)
11. [Atualização e retorno](#11-atualização-e-retorno)
12. [Backup e continuidade](#12-backup-e-continuidade)
13. [Operação do dia a dia](#13-operação-do-dia-a-dia)
14. [Critérios de aceite, por onda](#14-critérios-de-aceite-por-onda)
15. [O que costuma dar errado](#15-o-que-costuma-dar-errado)
16. [Pessoas e prazos](#16-pessoas-e-prazos)

---

## 1. A resposta curta

Três servidores, um banco PostgreSQL, uma VLAN sem saída para a internet e um
pequeno host na DMZ que manda as notificações. Nenhuma GPU, nenhum serviço de
nuvem, nenhuma chamada a provedor de IA.

```bash
cd implantacao
./bin/preflight.sh --perfil piloto      # o ambiente está pronto?
cp .env.exemplo .env && vim .env        # registro interno, SSO, SIEM
./bin/instalar.sh --perfil piloto --onda 0
./bin/verificar.sh --fluxo              # um evento de ponta a ponta
```

O que faz isso caber em quatro comandos é a escolha de IA clássica: scikit-learn
em CPU, PostgreSQL comum, Python puro no núcleo. **3,6 milhões de eventos por
ano é uma tabela, não um data lake.** Toda a complexidade que não existe aqui é
complexidade que o banco não vai operar por dez anos.

E há uma ordem que não se inverte: **coletor entra depois que o motor prova que
acerta.** A instalação não libera o console para Compliance antes de reproduzir
os 15 casos oficiais — `bin/verificar.sh --gabarito` é bloqueio, não relatório.

---

## 2. O que o banco precisa providenciar

Peça tudo de uma vez. Cada item abaixo vira um chamado numa fila diferente, e
levá-los em dias diferentes é o que transforma seis semanas em quatro meses.

### Infraestrutura

| Item | Piloto (100 usuários) | Corporativo (2.000) |
|---|---|---|
| Servidores de aplicação | 1 × (8 vCPU, 16 GB, 200 GB SSD) | 3 × (16 vCPU, 32 GB, 500 GB SSD) |
| PostgreSQL | no mesmo servidor | 8 vCPU, 32 GB, 500 GB SSD, com réplica |
| Host na DMZ | 1 × (2 vCPU, 2 GB) | 1 × (2 vCPU, 2 GB) |
| Armazenamento de objeto | 100 GB | 2 TB |
| GPU | **nenhuma** | **nenhuma** |

Sistema: RHEL 9, Oracle Linux 9 ou Ubuntu 22.04/24.04 LTS. Kernel ≥ 5.10 com
cgroups v2. Runtime: Docker ou Podman, com compose. O `preflight.sh` verifica
tudo isso e recusa a instalação se faltar.

### Rede

Uma VLAN de segurança nova, **sem rota para a internet**, e as 18 liberações da
planilha `implantacao/rede/regras-firewall.csv`. Essa planilha é feita para ser
anexada ao chamado sem edição: tem origem, destino, porta, sentido,
justificativa e em que onda cada regra passa a ser necessária.

### Acessos

- Registro de imagens interno (Harbor, Artifactory ou equivalente) com
  permissão de push para a esteira e de pull para os servidores.
- Um *client* OIDC no SSO corporativo, com os grupos `espia-analista`,
  `espia-compliance` e `espia-auditor`.
- Três pares de certificado da PKI interna (servidor + um por coletor).
- Um destino syslog TLS no SIEM.
- Uma conta de serviço no DLP com permissão de leitura de eventos.

### Decisões que não são técnicas

Estas travam a instalação mais do que qualquer item acima, e por isso entram na
primeira reunião, não na última:

1. **Quem é o dono do alerta.** SegInfo, Compliance ou a área do usuário. Sem
   dono, o alerta fica aberto e o indicador de SLA nasce quebrado — que é
   exatamente o achado A-05 da base atual.
2. **O que acontece com o funcionário.** A posição do projeto é *preventiva,
   nunca punitiva*, e ela precisa estar escrita antes da primeira notificação,
   não depois do primeiro caso.
3. **O comunicado interno.** A extensão de navegador toca a estação das pessoas.
   A primeira pergunta de todo funcionário é "então vocês leem o que eu
   digito?". A resposta honesta é não — a classificação acontece na estação e
   só a assinatura sai — e ela precisa ser dada pela empresa, antes da
   instalação, não pelo suporte, depois.

---

## 3. Os três ambientes

| | Laboratório | Homologação | Produção |
|---|---|---|---|
| Dados | base oficial, fictícia | fictícia + eventos sintéticos | reais |
| Coletores | nenhum | um, de mentira | todos |
| Notificação | desligada | canal de teste | canais reais |
| Quem usa | o time do projeto | SegInfo e Compliance | todo mundo |
| Sobe em | 1 dia | 1 semana | 6 semanas |

**Dado real nunca entra em laboratório nem em homologação.** A carga inicial dos
dois é a base fictícia do desafio, por `bin/exportar_postgres.py` — e é isso que
permite testar à vontade sem pedir autorização a ninguém.

---

## 4. Dia 1 — laboratório

Objetivo: ver o sistema funcionando, com os 650 eventos da base oficial, numa
máquina qualquer. Serve para a demonstração à banca e para o time se familiarizar.

```bash
# 1. gera a base a partir da planilha oficial (~2 s)
python3 run.py gerar
python3 testes.py            # 37 verificações
python3 testes_paridade.py   # motor Python × motor do navegador

# 2. converte para PostgreSQL
python3 implantacao/bin/exportar_postgres.py
#    → 650 eventos · 160 alertas · 6 achados · 14 regras

# 3. sobe
cd implantacao && cp .env.exemplo .env
./bin/instalar.sh --perfil piloto --onda 0
docker compose exec -T postgres psql -U espia -d espia < sql/piloto/900_carga_inicial.sql
```

**O que o console mostra no primeiro minuto** é o argumento do projeto inteiro:
não uma tela vazia esperando dado, mas a auditoria da rotulagem que a
organização já tem — os seis achados, os dez indicadores recalculados, os 7 de
10 indicadores declarados que divergem da base.

Duas coisas que a carga faz de propósito, e que valem ser ditas:

- Os 47 alertas marcados "Tratado" **sem data de tratamento** entram como
  `Aberto`. O esquema de produção tem um `CHECK` que proíbe fechar alerta sem
  carimbo de tempo. A carga não pode declarar tratado o que a base não prova.
- Evento sem usuário, ferramenta ou tipo reconhecível entra com campo nulo, não
  com id inventado. É o caso que R13 e R14 mandam marcar **REVISAR**.

---

## 5. Semana 1 — piloto

Cem usuários de uma área só — de preferência uma que já use IA e tenha gestor
disposto. Um coletor: o DLP, que não exige nada nas estações.

```
segunda    preflight nos servidores, chamados de rede abertos (todos)
terça      instalação da onda 0, carga inicial, SSO ligado
quarta     conector DLP no servidor de DLP, em modo somente leitura
quinta     primeiro evento real; bin/verificar.sh --fluxo
sexta      SegInfo abre o console pela primeira vez
```

**Os 15 dias seguintes são modo sombra.** O sistema classifica, registra e
**não notifica ninguém**. É o tempo de descobrir os falsos positivos com a
equipe, e não com a diretoria. `MODO_SOMBRA=true` no `.env` é o que garante isso,
e ele só vira `false` quando a taxa de falso positivo em Crítico estiver abaixo
de 10% medida por desfecho.

Critério de saída do piloto — os três, não dois:

1. `bin/verificar.sh --gabarito` passa 15/15 contra a instalação real.
2. Pelo menos 200 eventos reais coletados, com a área conferindo por amostragem.
3. A área piloto responde que o alerta que recebeu fazia sentido.

---

## 6. Semanas 2 a 6 — onda 0 em produção

A onda 0 sobe **sem modelo nenhum**. Só regras. É uma escolha, não uma etapa
intermediária: ao fim dela já existe em produção algo que responde à pergunta
norteadora do desafio, e todo modelo que vier depois terá contra o que ser
comparado.

```bash
./bin/preflight.sh --perfil corporativo
./bin/instalar.sh --perfil corporativo --onda 0
./bin/verificar.sh && ./bin/verificar.sh --isolamento && ./bin/verificar.sh --gabarito
```

O que sobe: ingestão, motor de regras, PostgreSQL, os dois consoles, o
encaminhador para o SIEM. O que **não** sobe: inferência e treinador — eles só
entram com `--onda 2`, e mesmo lá, em modo sombra primeiro.

A promoção entre ondas é um comando, e é reversível:

```bash
make onda2 PERFIL=corporativo     # liga a classificação automática, em sombra
make onda3                        # liga a detecção de anomalia
make onda4                        # priorização, risco preditivo, Telegram e WhatsApp
```

---

## 7. O que muda na rede

O desenho tem uma frase só: **a VLAN de segurança não sai para a internet, e a
internet não entra em lugar nenhum.** A única saída do sistema inteiro é um host
pequeno na DMZ, com allowlist de três domínios.

```
Rede corporativa ──mTLS, só entrada──▶ VLAN de Segurança ──fila──▶ DMZ ──proxy──▶ 3 domínios
   coletores                             núcleo + banco          gateway de
   consoles                              consoles                notificação
```

As 18 regras estão em `implantacao/rede/regras-firewall.csv`, com a tradução
para nftables em `nftables-exemplo.conf`. Duas delas existem para ser auditadas,
não para liberar nada:

| | |
|---|---|
| **FW-17** | NEGAR internet → VLAN de Segurança. O sistema não tem superfície externa |
| **FW-18** | NEGAR VLAN de Segurança → internet. Nenhuma exceção, nem "só para testar" |

`bin/verificar.sh --isolamento` testa isso de dentro de cada contêiner, e o
teste **passa quando a saída falha**. Ele fica no `make` para ser rodado depois
de toda mudança de firewall, porque afrouxamento temporário que ninguém desfez é
como isolamento de rede morre.

### O gateway de notificação

Mora na DMZ e é a menor peça do sistema, de propósito. Não tem acesso ao banco,
não tem acesso ao armazenamento de objeto, e a mensagem que ele envia carrega
**identificador, severidade e link interno** — nunca conteúdo.

> Se esse host for comprometido, o atacante ganha uma fila de identificadores e
> três webhooks. Não ganha um único dado do banco.

Por isso o alerta chega assim: *"GerencIA · Crítico · ALT-0421 · abrir"*. O que
aconteceu está no console, atrás do SSO. **O alerta não pode virar o vazamento.**

Sobre o WhatsApp, que é a integração que mais atrasa projeto: **somente Meta
Cloud API, via BSP homologado**. Biblioteca não oficial está fora de questão num
banco regulado. O template precisa de aprovação da Meta, que leva semanas e é um
prazo externo — **comece o processo na onda 1 para usar na onda 4.**

---

## 8. Como os coletores entram

Em ordem de atrito crescente. Os dois primeiros não tocam em nenhuma estação, e
é por isso que eles vêm primeiro: entregam visibilidade em dias, sem depender da
janela de mudança do time de endpoint.

| Ordem | Coletor | Onde | Toca a estação | Onda | Prazo típico |
|---|---|---|---|---|---|
| 1 | Conector DLP | servidor de DLP | não | 0 | 2 dias |
| 2 | Coletor de SWG | servidor de proxy | não | 0 | 2 dias |
| 3 | Gateway de IA | gateway aprovado | não | 2 | 1 semana |
| 4 | Extensão de navegador | estações, por GPO/MDM | **sim** | 2 | 3 a 6 semanas |
| 5 | SDK | aplicações internas | não | 3 | por aplicação |

As configurações prontas estão em `implantacao/coletores/`. O que todo coletor
envia: identificador, usuário, ferramenta, tipo de informação, contagens,
assinatura MinHash/SimHash e horário. O que nenhum envia: **o texto**. Em nenhum
coletor, em nenhuma onda, em nenhuma circunstância.

Duas notas que economizam retrabalho:

- **O mapeamento de rótulos do DLP é decisão de Compliance, não de
  infraestrutura.** O DLP classifica *arquivo*; o GerencIA raciocina sobre
  *informação*. O bloco `mapeamento:` do `dlp-conector.yaml` é onde essa
  tradução vive, e errá-la contamina tudo que vem depois.
- **O coletor de SWG é o que descobre shadow AI.** Ele gera evento para domínio
  de ferramenta conhecida e, principalmente, para domínio de IA que **não está
  no cadastro**. É assim que a ferramenta não autorizada aparece: por log, não
  por denúncia.

A extensão entra em **modo observação por 15 dias** antes de qualquer oferta de
mascaramento, e nunca em modo bloqueio na primeira temporada. A ordem
`observacao → mascaramento → bloqueio` não pula etapa.

---

## 9. Segredos, certificados e identidade

```bash
./bin/segredos.sh        # gera o que é gerável, modo 600, em segredos/
```

Cinco segredos são gerados na hora (banco, objeto, JWT, fila). Três vêm de fora
(Telegram, Slack, WhatsApp) e o script cria o arquivo vazio — os canais
correspondentes ficam desligados até serem preenchidos, e **o resto do sistema
sobe normalmente**.

Senha não vai em variável de ambiente. Variável de ambiente aparece em
`docker inspect`, em `ps` e no log de quem depurou às duas da manhã. Tudo entra
como arquivo em `/run/secrets`.

**Certificados: um par por coletor, não um par para todos.** Assim, revogar o
certificado de um servidor de DLP comprometido não derruba a coleta inteira, e a
trilha mostra qual coletor enviou cada evento. Autoassinado serve para o
laboratório e para mais nada — o mTLS é o que impede qualquer host da rede de
injetar evento falso.

O `preflight.sh` recusa a instalação com certificado a menos de 30 dias do
vencimento. Certificado que expira num domingo derruba a coleta sem ninguém
perceber até segunda.

### Papéis

Quatro, e nenhum deles é "administrador que vê tudo" (`sql/002_rbac.sql`):

| Papel | Vê | Muda |
|---|---|---|
| Analista | alertas e eventos **da sua área** | desfecho do alerta |
| Compliance | tudo | a política — não o desfecho |
| Auditor | tudo, inclusive a trilha | nada |
| Serviço | o que os contêineres precisam | evento e alerta |

A segregação por área é *Row Level Security* no PostgreSQL, não filtro na tela:
controle de acesso implementado só no front-end é contornável pela API.

E há uma visão chamada `meu_risco`. O modelo de risco preditivo é preventivo,
nunca punitivo, tecnicamente segregado do RH — e **a pessoa tem direito de ver o
próprio score**. Essa visão é o que torna esse direito real em vez de retórico.

---

## 10. Instalação sem contêiner

Alguns bancos não permitem contêiner em determinadas camadas, ou a área de
infraestrutura padroniza pacote e systemd. O núcleo é Python puro e não depende
de nada que o contêiner forneça: `implantacao/systemd/` tem a unidade
instanciada, o *target* e o endurecimento (`ProtectSystem=strict`,
`SystemCallFilter=@system-service`, `CapabilityBoundingSet=` vazio).

**Quando escolher systemd:** quando a DBA já opera PostgreSQL corporativo. Não
faz sentido subir um Postgres em contêiner ao lado de um time que já tem padrão
de backup, réplica e *tuning* — aponte o `PGHOST` para a instância deles e
instale só os serviços de aplicação.

O `pip install` usa `--no-index --find-links`: os pacotes vêm do espelho interno,
porque a VLAN não alcança o PyPI, e isso é recurso, não limitação.

---

## 11. Atualização e retorno

```bash
vim .env                                 # TAG=1.1.0
./bin/instalar.sh --perfil corporativo --onda 2
```

Idempotente: rodar de novo atualiza, não duplica. A instalação para na primeira
etapa que falhar, porque meia instalação num ambiente de segurança é pior que
nenhuma.

**Retorno em um minuto:** volte a `TAG` e rode de novo. O que torna isso seguro é
o esquema ser compatível para trás dentro de uma versão maior — migração que
apaga coluna espera a versão seguinte, com a anterior já fora de produção.

**A política tem o seu próprio retorno, e é mais importante.** Toda publicação
guarda autor, data, nota e o *diff*, e restaura em um clique pelo console de
políticas. Antes de publicar, o console simula a mudança contra os 650 eventos e
**bloqueia a publicação se a política editada deixar de reproduzir algum dos 15
casos oficiais**. Um alerta de junho precisa poder ser relido com a política que
valia em junho — sem isso a trilha não se sustenta, e é por isso que
`politica_versoes` é tabela, não arquivo de configuração.

---

## 12. Backup e continuidade

```bash
./bin/backup.sh               # dump cifrado + objetos + segredos
./bin/backup.sh --verificar   # restaura o último dump num banco descartável
```

O segundo comando é a metade que as pessoas esquecem. **Backup que nunca foi
restaurado não é backup, é esperança** — e num sistema cuja função é servir de
prova em auditoria, isso não serve. Rode o `--verificar` toda semana, por cron.

Os segredos são cifrados à parte, com chave diferente, e guardados em mídia
separada do dump. Dump e chave no mesmo lugar é um arquivo, não dois.

| | |
|---|---|
| RPO | 0 para evento (fila persistente), 5 min para agregado |
| RTO | 15 min com failover automático (Patroni) |
| Retenção | evento 5 anos, alerta e trilha 7 — declarado no esquema, não num documento que ninguém lê |
| Expurgo | `DROP PARTITION` mensal, não `DELETE` de milhões de linhas |

**Degradação:** sem inferência, o sistema opera só com regras. Sem notificação,
os alertas continuam registrados e o console funciona. Cada camada cai sem
derrubar a de baixo — é projeto, não sorte.

---

## 13. Operação do dia a dia

| Quando | O quê |
|---|---|
| Diário | `make verificar`; fila de alertas Críticos zerada no dia |
| Diário | **volume de eventos por fonte** — queda abrupta é coletor caído, não gente virtuosa |
| Semanal | `make restauro`; revisão de falso positivo com SegInfo |
| Mensal | criação das partições do trimestre seguinte; rotação de log |
| Trimestral | retreino com desfechos acumulados; revisão da política com Compliance |
| Semestral | teste de restauração completa; revisão de acessos |

**O alarme mais importante do sistema não é técnico.** Queda de volume de
eventos quase nunca significa que as pessoas pararam de usar IA. Significa que
um coletor caiu — e um sistema de rastreabilidade cego é pior que nenhum,
porque o silêncio dele é lido como "está tudo bem". Isso é alarme de severidade
alta, não gráfico no painel.

---

## 14. Critérios de aceite, por onda

Escritos como bloqueio, não como relatório. Se não passar, não promove.

| Onda | Aceite | Como se verifica |
|---|---|---|
| **0** | 15/15 casos oficiais na instalação real | `make gabarito` |
| **0** | isolamento de rede confirmado de dentro dos contêineres | `make isolamento` |
| **0** | evento de ponta a ponta em menos de 30 s | `make fluxo` |
| **1** | 100% dos alertas fechados com data de tratamento | `CHECK` no banco |
| **1** | alerta chega no Slack em menos de 60 s, sem conteúdo | inspeção da mensagem |
| **2** | classificador com abstenção: erro < 5% no que ele aceita classificar | relatório do treinador |
| **2** | extensão em observação por 15 dias antes do mascaramento | data da mudança de modo |
| **3** | anomalia em sombra por 30 dias antes de elevar nível | registro do modelo |
| **4** | modelo de prioridade com ao menos um trimestre de desfechos | contagem em `alertas.desfecho` |

---

## 15. O que costuma dar errado

Cinco, em ordem de frequência. Todos já estão previstos em algum ponto do
pacote, e mesmo assim vale escrever:

1. **Os chamados de rede em fila.** É o caminho crítico, sempre. Por isso as 18
   regras vêm numa planilha pronta para anexar, e por isso a onda 0 começa com
   os dois coletores que não dependem do time de endpoint.
2. **O relógio.** Máquina fora de NTP gera R12 falso e quebra a ordem
   cronológica da trilha. Horário de evento é prova. O `preflight.sh` trata
   como bloqueio, não aviso.
3. **A partição futura que ninguém criou.** Falta de partição derruba a
   ingestão. A rotina mensal cria doze meses à frente, e a falha dela é alarme.
4. **O mapeamento do DLP feito pela infraestrutura.** Rótulo mapeado errado
   contamina classificação, indicador e alerta — e ninguém percebe por meses.
   É decisão de Compliance.
5. **A extensão instalada sem comunicado.** É o único jeito garantido de
   transformar uma ferramenta de governança em conflito trabalhista. O
   comunicado sai antes da instalação, e diz a verdade: a classificação
   acontece na estação, e o texto não sai dela.

---

## 16. Pessoas e prazos

| Papel | Dedicação | Quando |
|---|---|---|
| Infraestrutura | 50% | semanas 1 a 3 |
| Redes e segurança | 20% | semanas 1 a 2, e a cada onda |
| SegInfo (dono do produto) | 30% | contínuo |
| Compliance | 20% | mapeamento, política, comunicado |
| Desenvolvimento | 100% | contínuo, 2 pessoas |
| Endpoint | 30% | onda 2, na extensão |
| Cientista de dados | 50% | ondas 2 a 4 |

**Onda 0 em produção: 6 semanas.** Arquitetura completa: 6 a 8 meses.

E vale terminar pelo que essas seis semanas entregam, porque é a única coisa que
justifica o resto: ao fim delas o banco consegue perguntar *"onde essa
informação apareceu, em que ferramenta, com quem, quantas vezes"* — que é a
pergunta do desafio — e obter a resposta com evidência, sem depender de ninguém
ter preenchido um formulário.

---

*Documento operacional do projeto GerencIA. Todos os dados usados em laboratório
e homologação são fictícios, conforme declarado na planilha oficial do desafio.*
