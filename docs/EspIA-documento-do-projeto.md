# EspIA — Documento do Projeto

**Desafio 2 · Stark Bank — Rastreabilidade e Governança de Informações em IA**

Registro do raciocínio, das decisões e do protótipo, construído sobre a **base oficial do
desafio**.

Versão de 16/09/2026.

> **Aviso, e ele é parte da entrega:** todos os dados são fictícios, conforme declarado na
> própria planilha fornecida pela Stark Bank. Nenhuma informação real foi utilizada.

---

## Sumário

1. [Resumo executivo](#1-resumo-executivo)
2. [O desafio](#2-o-desafio)
3. [A base oficial](#3-a-base-oficial)
4. [As duas teses](#4-as-duas-teses)
5. [O motor das regras](#5-o-motor-das-regras)
6. [Validação contra o gabarito](#6-validação-contra-o-gabarito)
7. [A auditoria da base](#7-a-auditoria-da-base)
8. [Os números](#8-os-números)
9. [O que foi construído](#9-o-que-foi-construído)
10. [Roteiro de apresentação](#10-roteiro-de-apresentação)
11. [Cobertura dos requisitos](#11-cobertura-dos-requisitos)
12. [Limites honestos](#12-limites-honestos)
13. [Decisões de projeto](#13-decisões-de-projeto)
14. [Como rodar](#14-como-rodar) · [14-A. A arquitetura](#14-a-a-arquitetura-de-implantação) · [14-B. A instalação](#14-b-a-instalação-no-ambiente)
15. [Próximos passos](#15-próximos-passos)
16. [Histórico de versões](#16-histórico-de-versões)

---

## 1. Resumo executivo

A EspIA lê a base oficial do desafio — 650 eventos de uso de IA, 160 alertas, 8 ferramentas,
20 tipos de informação, 72 usuários e 14 regras —, reaplica a política do zero, torna a
informação rastreável pelo nome do documento e **audita a rotulagem que recebeu**.

**Três números que sustentam tudo o que vem depois:**

| | |
|---|---|
| **15/15** | casos do gabarito oficial reproduzidos, sem exceção escrita para nenhum deles |
| **10/10** | indicadores que recalculamos batem com a apuração que a própria planilha fez |
| **7/10** | indicadores **declarados** pela organização divergem do que a base mostra |

O primeiro diz que o motor está certo. O segundo diz que a nossa conta está certa. O terceiro
é o que a empresa precisa saber — e o mais grave dele: **eventos críticos, declarado 6,8%,
apurado 16,6%. Duas vírgula quatro vezes mais.**

Além disso, seis achados de rotulagem na própria base, três deles de gravidade alta.

---

## 2. O desafio

O enunciado pede uma solução capaz de **identificar, registrar, classificar e acompanhar** as
informações utilizadas em ferramentas de IA, respondendo de forma simples:

> Qual informação foi utilizada? · Quem utilizou? · Em qual ferramenta de IA? · Quando? ·
> Para qual finalidade? · Qual o nível de sensibilidade? · Existe risco?

E encerra com a pergunta norteadora:

> *Se amanhã a empresa precisasse descobrir quais informações confidenciais foram utilizadas em
> ferramentas de IA, ela conseguiria identificar o que foi compartilhado, por quem, onde e quando?*

Um ponto do enunciado muda o desenho da solução: **o desafio não é impedir o uso da IA.** É
permitir usá-la com segurança, rastreabilidade e governança. Qualquer proposta que na prática
dificulte o uso está respondendo à pergunta errada.

---

## 3. A base oficial

`Base de Dados — Starkbank apurada 15-09.xlsx`, doze abas:

| Aba | Conteúdo |
|---|---|
| `Eventos_Uso_IA` | **650 eventos**, 17 colunas cada |
| `Alertas` | **160 alertas**, com situação e responsável |
| `Ferramentas_IA` | **8 ferramentas**, com status de aprovação, controles e logs |
| `Tipos_Informacao` | **20 tipos**, com classificação padrão e categoria |
| `Usuarios_Areas` | **72 usuários** em 12 áreas |
| `Regras_Risco` | **14 regras** (R01–R14), com nível esperado e ação |
| `Casos_Validacao` | **15 casos** com o resultado esperado — um gabarito |
| `Indicadores_Atuais` | 10 indicadores declarados, com meta e responsável |
| `Divergencias_Apuradas` | a apuração que a própria planilha fez sobre si mesma |
| `Classificacao_Informacao` | os 4 níveis e a regra geral de cada um |
| `Fontes_Logs` | 7 fontes que alimentam a rastreabilidade |
| `Dicionario_Dados` | origem e sensibilidade de cada campo |

Período: **01/06 a 08/09/2026**, 100 dias.

### Duas leituras da base que orientam o projeto

**1. A planilha é a saída de uma camada que já existe.** As colunas `Tipo informação` e
`Sensibilidade` chegam preenchidas, e o dicionário de dados diz que a origem delas é
*"Classificador/DLP"*. A EspIA consome essa saída, aplica as regras, audita e torna
consultável.

**2. A captura já é híbrida na prática.** Os 650 eventos vieram de quatro caminhos:

| Origem do registro | Eventos |
|---|---|
| DLP / segurança | 177 |
| Log de aplicação | 163 |
| Proxy corporativo | 162 |
| Registro manual | 148 |

Nenhum vê tudo sozinho — e os 148 de registro manual são exatamente a parcela que depende de
alguém lembrar de declarar. É o argumento contra a solução de formulário, feito com o dado da
própria casa.

---

## 4. As duas teses

### 4.1 Rastrear informação, não usos

| | |
|---|---|
| **O que quase todos vão fazer** | "O usuário X acessou a ferramenta Y às 14h" |
| **O que a EspIA faz** | *"Chave/API secret apareceu em 5 ferramentas, com 11 pessoas, 35 vezes — 3 delas em IA pública"* |

A primeira frase é log de atividade. A segunda é **linhagem de dado**. A busca começa pelo
documento, não pelo funcionário — que é como a pergunta norteadora está escrita.

**A frase para a banca:**
> *"A pergunta do desafio era se a empresa conseguiria descobrir isso amanhã. Ela consegue em
> quatro segundos — e a resposta vem pelo nome do documento, não pelo nome da pessoa."*

### 4.2 Não confiar na classificação recebida

Esta é a tese que a base oficial tornou demonstrável, e é o que separa uma ferramenta de
governança de um painel bonito.

A base já traz uma coluna `Risco` preenchida por um motor de regras. A EspIA **reaplica as
catorze regras do zero**, compara com o que está lá, recalcula os dez indicadores declarados e
procura defeitos na rotulagem.

**A frase:**
> *"Um painel que só desenha o que recebeu herda todos os erros da fonte. Este reaplica as
> regras e nos diz onde a fonte errou."*

---

## 5. O motor das regras

As catorze regras vêm da planilha e **não estão reescritas no código** — os níveis e as ações
são lidos da aba `Regras_Risco`. Se Compliance editar a planilha e rodar `python3 run.py gerar`,
o motor muda de comportamento sem uma linha de código tocada.

O que a EspIA acrescenta é a **ordem de precedência**, porque política escrita em linguagem
natural se sobrepõe e se contradiz — e é essa ordem que uma auditoria questiona.

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

### Três decisões que essa ordem codifica

**1. Rastreabilidade antes de tudo.** Se não dá para confiar em quem, onde ou o quê, atribuir
risco é inventar. R14 e R13 devolvem REVISAR — que é exatamente o que o caso CV13 espera.

**2. A regra mais específica descreve; a mais severa decide.** Código-fonte confidencial numa
IA pública dispara R01 (Crítico) e R06 (Alto) ao mesmo tempo. O nível é o mais severo. Mas as
duas ficam registradas, porque R06 é o que informa que há exposição de propriedade intelectual
a avaliar. Descartar a regra específica descarta a resposta específica.

**3. Contexto é evidência, não agravante.** R12 nunca eleva o nível sozinha — é o que a própria
regra diz. Ela entra na cadeia de evidências e ajuda quem investiga.

### O resultado

| | |
|---|---|
| Concordância de **nível** com a base | 642/650 = **98,8%** |
| Concordância de **regra citada** | 626/650 = **96,3%** |
| Divergências de nível | **8**, todas o achado A-03 |
| Divergências de regra | **24** — 16 são o achado A-02, 8 são o A-03 |

As divergências não são ruído: **são exatamente os dois achados de auditoria.** Onde a base cita
R01 e a política tem R04, nosso motor cita R04 — e é por isso que a concordância de regra é menor
que a de nível. Um motor que concordasse 100% com a base estaria repetindo o defeito dela.

---

## 6. Validação contra o gabarito

A aba `Casos_Validacao` traz quinze situações com o resultado que a Stark Bank espera de
qualquer solução. É um gabarito — e rodar o motor contra ele transforma "nosso motor está
correto" de opinião em afirmação verificável.

**15 de 15 reproduzidos**, sem exceção escrita para nenhum caso.

Três casos mostram por que a precedência importa:

| Caso | Situação | Esperado | Por que a ordem decide |
|---|---|---|---|
| **CV12** | Credencial numa ferramenta **aprovada** | CRÍTICO | Se a precedência começasse pela ferramenta, daria Médio. Como R03 vem antes de tudo que fala em ferramenta, dá Crítico |
| **CV13** | Ferramenta desconhecida, informação sem classificação | REVISAR | Nenhuma regra de conteúdo se aplica. A resposta certa é recusar-se a classificar, não arbitrar |
| **CV14** | Informação pública numa IA **não aprovada** | BAIXO | A política não tem regra para isso; o gabarito é quem resolve a lacuna |

---

## 7. A auditoria da base

Seis achados, cada um com os eventos afetados listados para conferência.

### A-01 · Regra citada pressupõe ferramenta aprovada, mas a ferramenta não era
**38 eventos** · gravidade alta

Ocorreram em IA Pública A ou B — ambas "Não aprovada" no cadastro — mas citam R09 (29×) ou
R08 (9×), cujo texto diz explicitamente *"em ferramenta aprovada"*.

**Por que importa:** o nível de risco pode estar certo, mas a trilha de auditoria está errada.
Um auditor que ler *"R09 — dados anonimizados em ferramenta aprovada"* num evento que aconteceu
numa IA pública será induzido a erro. É a diferença entre registro e evidência.

### A-02 · Regra genérica citada onde a política tem regra específica
**18 eventos** · gravidade alta

Fechados com R01 ou R02 quando existia regra própria: R04 (11×), R05 (5×), R06 (2×).

**Por que importa:** as ações obrigatórias são diferentes. R01 manda *"bloquear/alertar e
investigar"*. R04 manda *"investigar e aplicar resposta de privacidade"* — o que inclui avaliar
comunicação ao titular e à autoridade. Citar a regra genérica faz a obrigação de privacidade
desaparecer do registro.

### A-03 · Conteúdo não público na ferramenta aprovada só para conteúdo público
**8 eventos** · gravidade alta

O Gerador de Imagens tem status *"Aprovada apenas para conteúdo público"* e controle
*"Não usar material confidencial"*. Oito eventos o usaram com informação Interna ou
Confidencial, e a base os classificou como Baixo ou Médio.

**Por que importa:** pela regra R10 — uso incompatível com a finalidade aprovada — são Alto.
São eventos que deveriam ter virado alerta e não viraram. Estas são as 8 divergências do motor.

### A-04 · Seis das catorze regras nunca são acionadas
gravidade média

Nunca aparecem na coluna `Regra acionada`: R04, R05, R06, R12, R13, R14.

**Por que importa:** ou a regra está coberta por outra mais severa (R04, R05, R06), ou não tem
instrumentação para ser avaliada (R12, R13, R14). Nos dois casos ela dá falsa sensação de
cobertura: a política aparenta ter catorze controles e opera com oito.

### A-05 · Alertas não registram data de tratamento
**47 alertas** · gravidade média

Estão marcados como "Tratado", mas a aba não tem coluna de data de tratamento nem de desfecho.

**Por que importa:** o indicador *"Alertas críticos tratados em até 24h"* é declarado como 72% e
não pode ser apurado a partir da base. Um indicador de SLA sem carimbo de tempo é uma afirmação,
não uma medição.

### A-06 · A política não cobre Interna ou Pública em ferramenta não aprovada
**38 eventos** · gravidade média

Nenhuma das catorze regras trata dessa combinação. Para Pública o caso CV14 dá o gabarito
(Baixo); para Interna não há referência.

### As três propostas de política

| | Proposta | Por quê |
|---|---|---|
| **R15** | Informação Interna em IA não aprovada → Médio | Fecha a lacuna do A-06 |
| **R16** | Toda regra citada deve ser compatível com o fato registrado | Impede o A-01 de voltar a acontecer |
| **R17** | Todo alerta deve registrar data de tratamento e desfecho | Torna o indicador de SLA apurável |

---

## 8. Os números

### Indicadores: declarado × realidade

| Indicador | Declarado | Apurado | Diverge? |
|---|---|---|---|
| Usuários ativos usando IA/mês | 61 | **72** | sim, −11 |
| Ferramentas de IA identificadas | 8 | 8 | não |
| Uso em ferramentas não aprovadas | 12,4% | 12,3% | não |
| Eventos com informação confidencial | 28,7% | **34,8%** | sim, −6,1 p.p. |
| Eventos críticos | 6,8% | **16,6%** | sim, **2,4×** |
| Alertas críticos tratados em até 24h | 72% | **não apurável** | sim |
| Eventos com rastreabilidade completa | 84% | **100%** | sim (para melhor) |
| Áreas com uso de IA identificado | 12 | 12 | não |
| Ferramentas com logs corporativos | 6 de 8 | **5 de 8** | sim |
| Casos sem classificação suficiente | 4,2% | **0,0%** | sim (para melhor) |

**Todos os dez** valores que recalculamos batem com a apuração da própria planilha. É isso que
autoriza confiar na coluna do meio.

Nota sobre "Eventos críticos": o indicador não define se *crítico* se refere ao risco ou à
sensibilidade. As duas leituras dão 11,4% (risco) e 16,6% (sensibilidade) — **ambas muito acima
dos 6,8% declarados**. Um indicador ambíguo é um indicador que ninguém consegue contestar.

### Distribuição de sensibilidade

| Classificação | Eventos | % |
|---|---|---|
| Interna | 273 | 42,0% |
| Confidencial | 226 | 34,8% |
| Crítica | 108 | 16,6% |
| Pública | 43 | 6,6% |

### Risco

| Nível | EspIA | Base |
|---|---|---|
| Crítico | 74 | 74 |
| Alto | **94** | 86 |
| Médio | 172 | 174 |
| Baixo | 310 | 316 |

### Alertas

160 alertas, um para cada evento Alto ou Crítico da base.

| Situação | | Responsável | |
|---|---|---|---|
| Aberto | 58 | Compliance | 48 |
| Em análise | 55 | Privacidade | 42 |
| Tratado | 47 | Segurança | 41 |
| | | Gestor da área | 29 |

### Ferramentas

| Ferramenta | Status | Eventos |
|---|---|---|
| Assistente Corporativo A | Aprovada | 259 |
| Copiloto de Produtividade | Aprovada | 169 |
| Plataforma de Dados IA | Aprovada condicional | 68 |
| **IA Pública B** | **Não aprovada** | **51** |
| Assistente de Código | Aprovada condicional | 32 |
| **IA Pública A** | **Não aprovada** | **29** |
| Assistente Jurídico | Aprovada | 24 |
| Gerador de Imagens | Aprovada só para conteúdo público | 18 |

### Informação mais usada

| Tipo | Classificação | Eventos |
|---|---|---|
| Ata de reunião interna | Interna | 173 |
| Dados agregados anonimizados | Interna | 89 |
| Dados cadastrais de cliente | Confidencial | 51 |
| Estratégia de lançamento | Confidencial | 39 |
| **Chave/API secret** | **Crítica** | **35** |

---

## 9. O que foi construído

### Pipeline Python — sem dependências obrigatórias

| Módulo | Função |
|---|---|
| `base_oficial.py` | Importa as 12 abas para o modelo interno |
| `regras.py` | R01–R14 com precedência declarada e cadeia de evidências |
| `validacao.py` | Os 15 casos do gabarito |
| `auditoria.py` | Indicadores recalculados + os seis achados |
| `pipeline_oficial.py` | Orquestração, SQLite, exportação, montagem do painel |
| `consultas.py` | Linhagem, exposição, alertas, evidência |
| `xlsx_min.py` | Leitor de XLSX embutido, verificado contra o openpyxl |
| `yaml_min.py` | Leitor de YAML embutido, verificado contra o PyYAML |
| `fingerprint.py`, `detectores.py` | Camada de captura: MinHash/SimHash, CPF/CNPJ/Luhn/credencial, mascaramento |

O projeto roda com **Python 3.9 e nada mais**. Se openpyxl e PyYAML estiverem instalados, são
usados; se não, os leitores embutidos assumem com resultado idêntico — verificado nos testes.
Um protótipo que depende de um `pip install` dar certo pode não rodar na máquina do auditório.

### Console de políticas — a aplicação de Compliance

`dashboard/console-politicas.html`. Onde a política é editada, e o que ele faz que um editor
comum não faz:

| | |
|---|---|
| **Simula antes de publicar** | Toda mudança é aplicada aos 650 eventos na hora: quantos mudam de nível, quantos viram alerta, quantos saem da fila |
| **Trava no gabarito** | Se a política editada deixar de reproduzir algum dos 15 casos oficiais, a publicação é bloqueada e o console diz qual caso quebrou |
| **Versiona** | Cada publicação guarda autor, data, nota e o diff, com restauração em um clique |
| **Mostra a precedência** | A ordem é editável, com a explicação de por que ela muda a ação obrigatória |

O motor de regras existe duas vezes no projeto: em Python, no pipeline, e em JavaScript, no
console. `python3 testes_paridade.py` prova que os dois concordam evento a evento e caso a caso
— se divergissem, a simulação estaria mentindo, que é pior do que não ter simulação.

**A demonstração que vale fazer ao vivo:** mude R07 de Médio para Alto. O console mostra na hora
que 172 eventos passariam a alertar, que a fila dobraria — e bloqueia a publicação, porque quatro
casos do gabarito (CV05, CV08, CV09, CV11) esperam Médio. Endurecer a política não é sempre
melhorá-la, e o console não deixa esquecer disso.

### Painel — sete vistas

| Vista | Para quê |
|---|---|
| **Panorama** | Indicadores, série diária por risco, área × sensibilidade, destino da informação |
| **Rastrear** | A busca reversa, por tipo de informação ou por pessoa |
| **Alertas** | Fila com sete filtros + cadeia de evidências regra a regra |
| **Auditoria** | Indicadores recalculados e os seis achados, com os eventos afetados |
| **Validação** | Os quinze casos do gabarito, com a cadeia de cada um |
| **Política** | As catorze regras, a precedência, e as três propostas |
| **Inventário** | Ferramentas, tipos de informação e fontes de log |

Filtros da vista Alertas: **Risco, Área, Usuário, Ferramenta, Tipo de informação, Situação do
alerta e Divergência** — cobrindo, um a um, o que o enunciado exige. Uma linha em português
descreve o recorte ativo, para que ele entre num relatório sem precisar de captura de tela.

### Testes

`python3 testes.py` — **37 verificações**, entre elas:

- os leitores embutidos de XLSX e YAML produzem resultado idêntico ao openpyxl e ao PyYAML;
- as doze abas são lidas com as contagens exatas da planilha;
- a distribuição de sensibilidade bate com a aba `Divergencias_Apuradas` (273/226/108/43);
- os 15 casos do gabarito passam;
- a concordância com a base é ≥ 98%;
- R03 vence "ferramenta aprovada"; R14 vence tudo; R12 não eleva sozinha;
- os 10 indicadores recalculados batem com a apuração da planilha;
- todo achado declara consequência e onde é verificável.

---

## 10. Roteiro de apresentação

**8 a 10 minutos.**

### 1. Abertura (1 min) — a armadilha
*"A solução óbvia é um formulário onde o colaborador declara o que usou. Não funciona: ninguém
preenche, e o risco mora exatamente no que não foi declarado. A base de vocês já mostra isso —
148 dos 650 eventos vieram de registro manual; os outros 502, de DLP, proxy e log de aplicação.
A captura já é híbrida na prática. Só falta alguém ligar as pontas."*

### 2. A virada (1 min) — rastrear informação
Abra **Rastrear**, digite `Chave/API secret`.
*"Trinta e cinco usos, onze pessoas, cinco ferramentas, três delas fora da política. A pergunta
do desafio era se a empresa conseguiria descobrir isso amanhã. A busca começa pelo nome do
documento, não pelo nome da pessoa."*

### 3. A prova (1,5 min) — o gabarito
Abra **Validação**.
*"A planilha traz quinze casos com o resultado que vocês esperam. Nosso motor reproduz os
quinze, sem exceção escrita para nenhum. CV12 e CV13 são os que provam a ordem de precedência:
credencial vence ferramenta aprovada, e falta de rastreabilidade vence tudo."*

### 4. O achado (3 min) — a auditoria
Abra **Auditoria**. Este é o coração da apresentação.

*"Recalculamos os dez indicadores declarados. Os dez batem com a apuração que a própria planilha
fez — é isso que autoriza confiar no resto. E sete dos dez divergem do que a organização
declara. O mais grave: eventos críticos, declarado 6,8%, apurado 16,6%. Duas vírgula quatro
vezes mais."*

Depois desça para os achados:

*"E fomos além dos números, para a rotulagem. Trinta e oito eventos citam uma regra cujo texto
diz 'em ferramenta aprovada' — mas aconteceram em IA pública. Dezoito foram fechados com a regra
genérica quando havia regra específica: R04 manda aplicar resposta de privacidade, R01 não. E
oito usaram o gerador de imagens, que só é aprovado para conteúdo público, com material
confidencial — classificados como Baixo, deveriam ser Alto."*

### 5. A evidência (1,5 min) — por que isto é risco
Clique num evento crítico em **Alertas**.
*"Cada alerta abre a cadeia: as regras que se aplicaram, o que cada uma diz, e a ação que a
política obriga. Compliance audita isto. A pessoa avaliada contesta isto. Um alerta sem essa
cadeia é opinião."*

### 6. O fecho (1 min) — a política é da empresa
Abra **Política**.
*"As catorze regras não estão escritas no nosso código. São lidas da planilha de vocês. Mudem a
aba Regras_Risco, rodem um comando, e o motor muda de comportamento. O que acrescentamos foi a
ordem de precedência — e ela está declarada na tela, não escondida."*

### Se sobrar tempo
`python3 run.py classificar "..."` — mostra a camada que preencheria automaticamente as colunas
`Tipo informação` e `Sensibilidade`, que hoje dependem de DLP e registro manual.

### Preparação da demo
- Leve o **`painel.html` num pendrive**. Ele é um arquivo só, funciona offline, sem Python e sem
  internet. É o plano B para Wi-Fi ruim.
- Tenha um terminal aberto na pasta, com `python3 run.py auditar` pronto para rodar, caso peçam
  para ver o dado cru.

---

## 11. Cobertura dos requisitos

| Requisito do enunciado | Onde está | Status |
|---|---|---|
| Registrar quais ferramentas de IA estão sendo utilizadas | vista Inventário | ✅ |
| Identificar quais informações são compartilhadas | vista Rastrear + `fingerprint.py` | ✅ |
| Classificar por nível de sensibilidade | `Tipos_Informacao` + vista Política | ✅ |
| Usuário, área, ferramenta, data e finalidade | esquema `eventos` | ✅ |
| Histórico que permita rastrear o fluxo | `linhagem()` + vista Rastrear | ✅ |
| Identificar situações de risco | `regras.py` | ✅ |
| Alertas para usos críticos ou fora das regras | vista Alertas | ✅ |
| Filtros por área, usuário, ferramenta, tipo, período e risco | sete filtros | ✅ |
| Indicadores de acompanhamento | vista Auditoria — recalculados | ✅ |
| Apoiar auditorias e investigações | SQLite + cadeia de evidências | ✅ |
| Evidências de por que algo é risco | regras aplicáveis com motivo e ação | ✅ |
| A empresa define classificações e regras | tudo lido da planilha | ✅ |
| Demonstração com dados reais autorizados, anonimizados ou sintéticos | a base oficial | ✅ |

---

## 12. Limites honestos

Diga estes antes que perguntem. Declarar limite conhecido lê como maturidade.

| Limite | Detalhe |
|---|---|
| **O fingerprint não é exercitado pela base** | A planilha entrega a classificação pronta. A camada que a produziria é demonstrada por `run.py classificar` e pelos testes, não pelos 650 eventos |
| **Varredura linear** | Serve para o acervo de demonstração; em escala vira índice LSH por bandas. A matemática é a mesma |
| **Paráfrase não é detectada** | O fingerprint pega recorte, reformatação e colagem — não quem reescreve com as próprias palavras |
| **R10 é aplicada como a base a aplica** | O texto da regra fala em finalidade incompatível; a base usa para informação crítica em ambiente aprovado. Mantivemos o comportamento da base e registramos a divergência no achado A-04 |
| **Sem enquadramento regulatório** | A base não tem coluna de marco legal, e preferimos não inferir o que a planilha não afirma |
| **Sem filtro de período no painel** | A base cobre 100 dias contínuos; o filtro foi substituído por Situação do alerta, que a base tem e é mais acionável |
| **As propostas R15–R17 não estão aplicadas** | São recomendações, exibidas na vista Política. Aplicá-las mudaria os números, e misturar o que a política diz com o que sugerimos tiraria a comparabilidade |

---

## 13. Decisões de projeto

### Cor = risco. Densidade = classificação.
No painel, a **matiz** é reservada exclusivamente para severidade de risco. A **classificação**
da informação usa densidade de tinta, sem matiz: Pública é contorno, Interna é preenchimento
leve, Confidencial é médio, Crítica é sólido. Duas escalas de cor competindo na mesma tela
tornam ambas ilegíveis.

### A política vive na planilha, não no código
O motor lê níveis e ações da aba `Regras_Risco`. O código tem a **ordem de precedência** e a
lógica de aplicação; não tem os textos das regras. Editar a planilha muda o comportamento.

### A vista Política é somente leitura
A política de risco precisa viver num arquivo versionado, com histórico de quem mudou o quê.
Se fosse um formulário na tela, qualquer pessoa com acesso ao painel poderia afrouxar um limiar
na véspera de uma auditoria sem deixar rastro.

### Zero dependências
Python 3.9 e nada mais. Os leitores de XLSX e YAML embutidos são verificados contra openpyxl e
PyYAML nos testes. Um `pip install` que falha no dia da apresentação custa mais do que os dois
módulos custaram para escrever.

### O painel local é um arquivo só
`dashboard/painel.html` carrega os dados dentro de si. Abre com dois cliques, funciona offline,
vai por e-mail inteiro, roda em qualquer computador sem Python.

### REVISAR não é um nível de risco
É a recusa de atribuir um. Quando a rastreabilidade ou a classificação faltam, o motor devolve
REVISAR em vez de arbitrar — e o caso CV13 confirma que é o comportamento esperado.

---

## 14. Como rodar

### O painel, sem instalar nada

Descompacte o pacote e abra **`dashboard/painel.html`** — dois cliques. Ele já vem montado, com
os dados dentro, e funciona sem internet e sem Python.

O `index.html` ao lado é o corpo da versão publicada na web. Com o `dados.js` na mesma pasta
— e ele vem no pacote — os dois funcionam igual; se por algum motivo o `dados.js` faltar, o
`index.html` mostra uma tela com um botão que leva ao `painel.html`.

### O pipeline

Requisito: **Python 3.9 ou superior.** Nada além disso.

```bash
cd espia
python3 run.py gerar      # lê a planilha, aplica as regras, audita, monta o painel (~2 s)
python3 run.py painel     # abre o painel no navegador
python3 testes.py         # 37 verificações
```

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
python3 run.py classificar "texto que iria para a IA"
```

O banco é SQLite comum — `sqlite3 dados/espia.db` responde qualquer corte que o painel não
tenha. Vale ter isso na manga se a banca pedir algo na hora.

### Estrutura do pacote

```
base/                    A planilha oficial do desafio.
dashboard/               painel.html (o que você abre) + index.html e dados.js.
dados/                   SQLite e JSON gerados.
docs/                    Este documento.
espia/                Os módulos Python.
run.py                   CLI.
testes.py                37 verificações.
```

---

## 14-A. A arquitetura de implantação

Este documento descreve o protótipo. O documento irmão —
**`EspIA-arquitetura.md`** — descreve o sistema de produção que ele antecipa:

- **On-premise total.** A VLAN de segurança não tem rota para a internet; a única saída é um
  proxy na DMZ com allowlist de três domínios.
- **Quatro modelos de IA clássica**, todos em CPU e todos explicáveis: detecção de anomalia
  comportamental (Isolation Forest), classificação automática da informação (TF-IDF + SVM
  calibrado, com direito de abstenção), priorização da fila de alertas (LightGBM com
  ranqueamento) e risco preditivo por usuário e área (regressão logística).
- **A regra é o piso; o modelo é o teto.** O modelo nunca rebaixa o que uma regra estabeleceu,
  e nunca cria um evento Crítico sozinho — Crítico aciona CISO e DPO, e essa decisão precisa de
  base determinística.
- **Notificação multicanal** — Slack, Telegram, WhatsApp via BSP oficial, e-mail e SIEM — com
  uma regra que define o desenho: a mensagem que sai da rede leva identificador e severidade,
  nunca o conteúdo. Um alerta que descreve o vazamento por WhatsApp é, ele mesmo, o vazamento.
- **Dimensionamento honesto:** 3,6 milhões de eventos por ano é uma tabela PostgreSQL comum.
  Nada de Kafka, Spark ou GPU.
- **Roadmap em cinco ondas**, com algo em produção ao fim da primeira, em seis semanas.

---

## 14-B. A instalação no ambiente

Arquitetura responde *como o sistema é*. A pergunta seguinte é sempre *como isso entra aqui* —
e essa é a que trava projeto. O terceiro documento, **`EspIA-implantacao.md`**, é o runbook,
e `implantacao/` é o pacote que o executa:

```bash
cd implantacao
./bin/preflight.sh --perfil piloto        # 26+ verificações, antes de instalar nada
./bin/instalar.sh --perfil piloto --onda 0
./bin/verificar.sh --fluxo                # um evento de ponta a ponta
```

O que está lá dentro: os dois `docker-compose` (núcleo na VLAN sem saída, gateway na DMZ), o
esquema PostgreSQL de produção — partição por mês, trilha *append-only* por regra do banco,
política versionada, retenção declarada no próprio esquema —, os quatro papéis com *Row Level
Security* por área, as 18 regras de firewall numa planilha pronta para anexar ao chamado, as
configurações dos quatro coletores, e a instalação alternativa por systemd para quem não usa
contêiner.

Quatro decisões que este pacote materializa, e que valem mais que os arquivos:

1. **Coletor entra depois que o motor prova que acerta.** `make gabarito` roda os 15 casos
   oficiais contra a instalação real e **bloqueia** a liberação do console se algum falhar.
2. **O isolamento é testado, não declarado.** `make isolamento` tenta sair para a internet de
   dentro de cada contêiner — e o teste passa quando a saída falha. Afrouxamento "só para
   testar" que ninguém desfez é como isolamento de rede morre.
3. **A carga inicial não mente.** Os 47 alertas marcados "Tratado" sem data de tratamento
   entram como `Aberto`, porque o esquema tem um `CHECK` que proíbe fechar alerta sem carimbo
   de tempo. A instalação não declara tratado o que a base não prova — é o achado A-05 virando
   restrição de banco.
4. **Backup que nunca foi restaurado não é backup.** `make restauro` restaura o último dump num
   banco descartável e conta as linhas. Num sistema cuja função é servir de prova em auditoria,
   esperança não serve.

E as três coisas que atrasam a implantação são de gente, não de máquina: quem é o dono do
alerta, o que acontece com o funcionário, e o comunicado interno que precede a extensão de
navegador. Estão na primeira seção do runbook por isso.

---

## 15. Próximos passos

Em ordem de retorno sobre esforço:

1. **Aplicar as propostas R15–R17** à planilha e mostrar o antes e depois — prova que o ciclo
   de governança fecha, e é a resposta natural para "e agora, o que a empresa faz com isso?".
2. **Carimbo de tratamento nos alertas**, resolvendo o A-05 e tornando o indicador de SLA real.
3. **Protótipo mínimo da extensão** de navegador, ainda que só detecte a colagem e ofereça o
   mascaramento. Ver isso acontecendo ao vivo vale mais que qualquer slide.
4. **Índice LSH** no lugar da varredura linear, transformando a objeção de escala em número.
5. **Exportação do recorte filtrado** em CSV ou PDF, para o caso de uso de auditoria.

---

## 16. Histórico de versões

| Data | O que mudou |
|---|---|
| **13/09/2026** | Primeira versão. Conceito, arquitetura de captura híbrida, motor de risco com score ponderado e cadeia de evidências, sobre uma base sintética de 90 dias gerada por código |
| **15/09/2026** | **Reconstrução sobre a base oficial do desafio.** Importador das 12 abas, motor das 14 regras com precedência declarada, validação contra os 15 casos do gabarito, auditoria com recálculo dos indicadores e seis achados de rotulagem. Painel refeito com sete vistas |
| **16/09/2026** | Correções de entrega: o pacote passou a incluir o `dados.js`, e o `index.html` ganhou aviso e link para o `painel.html` quando aberto sem dados |
| **16/09/2026** | **Console de políticas e arquitetura de implantação.** Precedência corrigida para citar a regra específica antes da genérica (o defeito que o achado A-02 aponta), motor portado para o navegador com teste de paridade, console com simulação e trava no gabarito, e o documento `EspIA-arquitetura.md` com os quatro modelos de IA clássica e a topologia on-premise |
| **16/09/2026** | **Pacote de implantação.** `EspIA-implantacao.md` (runbook de 16 seções) e `implantacao/`: preflight do ambiente, instalação idempotente por onda, verificação de fluxo e de isolamento, esquema PostgreSQL de produção com trilha append-only e política versionada, RBAC com Row Level Security, 18 regras de firewall, configuração dos quatro coletores, backup com teste de restauração e a alternativa por systemd |

---

## Apêndice — glossário

| Termo | O que significa aqui |
|---|---|
| **Linhagem** | O caminho completo de uma informação dentro de ferramentas de IA |
| **Precedência** | A ordem em que as regras são avaliadas quando mais de uma se aplica |
| **Cadeia de evidências** | As regras aplicáveis a um evento, cada uma com motivo e ação obrigatória |
| **REVISAR** | Não é um nível de risco: é a recusa de atribuir um, quando não há base para tanto |
| **Shingle** | N-grama de palavras sobrepostas, usado antes de gerar a assinatura |
| **MinHash / SimHash** | Assinaturas que reconhecem um documento sem guardá-lo |
| **Containment** | Fração do prompt que veio de um ativo conhecido — mais útil que Jaccard aqui |
| **Status da ferramenta** | Classe de homologação: aprovada, aprovada condicional, aprovada só para conteúdo público, não aprovada |

---

*Documento gerado em 16/09/2026. Base: a planilha oficial do Desafio 2, com dados fictícios.*
