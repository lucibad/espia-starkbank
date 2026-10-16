# Como o agente de estação identifica *qual IA* está sendo usada

> Documento técnico · GerencIA · sensor de rede (`borda/estacao/sensor.py`)

## Resposta curta

A chave de identificação é o **nome de domínio (hostname) do serviço de IA** — não
o conteúdo, não o IP cru. O agente mantém uma tabela de **sufixos de domínio
conhecidos → nome amigável da ferramenta** (`DOMINIOS_IA`) e procura esses sufixos
em dois lugares da própria máquina:

1. **Cache de DNS do Windows** (`ipconfig /displaydns`) — a prova de que a máquina
   *consultou* aquele hostname. É a **autoridade** no Windows.
2. **Conexões TCP ativas** (`psutil`/`netstat`), casadas por **IP** contra um índice
   `IP → ferramenta` que o agente monta resolvendo os domínios conhecidos.

Em uma frase: **mapeamos por DNS/domínio**; o IP e o processo são sinais de apoio.
Nada do conteúdo trafegado é lido (o tráfego é TLS).

---

## A tabela-chave: domínio → ferramenta

O núcleo da identificação é o dicionário `DOMINIOS_IA` (sufixo de domínio → nome):

```python
DOMINIOS_IA = {
    "openai.com": "ChatGPT (OpenAI)",
    "chatgpt.com": "ChatGPT (OpenAI)",
    "anthropic.com": "Claude (Anthropic)",
    "claude.ai": "Claude (Anthropic)",
    "gemini.google.com": "Gemini (Google)",
    "generativelanguage.googleapis.com": "Gemini (Google)",
    "copilot.microsoft.com": "Copilot (Microsoft)",
    "deepseek.com": "DeepSeek",
    "perplexity.ai": "Perplexity",
    "poe.com": "Poe",
    "huggingface.co": "HuggingChat",
    "meta.ai": "Meta AI",
    "x.ai": "Grok (xAI)",
    "grok.com": "Grok (xAI)",
    "cursor.sh": "Cursor",
    "cursor.com": "Cursor",
}
```

O casamento é por **sufixo**: `host == suf` ou `host.endswith("." + suf)`. Assim
`chat.openai.com`, `api.openai.com` e `openai.com` caem todos em "ChatGPT (OpenAI)".

> **Importante:** o agente só decide *qual ferramenta* é. Ele **não** decide se ela
> é aprovada ou não — esse status vem do **inventário no coletor**
> (`inventario_dominios`), e pode ser ajustado na tela de Governança. O agente
> observa; a política classifica.

---

## Os três sinais, em ordem de confiança

| # | Sinal | Como obtém | O que prova | Força |
|---|---|---|---|---|
| 1 | **Hostname no cache de DNS** | `ipconfig /displaydns` → regex de hosts → `_casar_suf` | A máquina **resolveu** aquele nome de IA | **Forte** (sem ruído de CDN) |
| 2 | **IP da conexão ativa** | `psutil.net_connections` / `netstat`, casado no índice `IP→ferramenta` | Há conexão aberta para um IP daquela IA | Médio (IP de CDN é compartilhado) |
| 3 | **Processo dono da conexão** | PID da conexão → `psutil.Process(pid).name()` / `tasklist` | De qual **aplicativo** partiu (ex.: `chrome.exe`, `Code.exe`) | Enriquecimento |

### Por que o DNS é a autoridade (e não o IP)

IPs de IA ficam atrás de **CDN** (Cloudflare, Google, Azure). Um mesmo IP serve
várias empresas — identificar "qual IA" só pelo IP gera **falso-positivo**. O nome
consultado no DNS, não. Por isso, no Windows:

- **com cache de DNS disponível** → a lista de hosts consultados é a verdade; as
  conexões ativas só acrescentam o **processo**;
- **sem cache** (macOS/Linux, ou cache vazio) → cai no índice de IPs, *best-effort*.

O campo `via` do evento registra qual caminho identificou: `dns`, `ip+dns` ou `ip`.

---

## Fluxo de uma varredura (`varrer`, a cada 60 s)

```
1. _reindexar()      # resolve cada domínio de DOMINIOS_IA → IPs públicos atuais
                     #   (socket.getaddrinfo), monta _ip_index = { ip: ferramenta }
                     #   cache de 10 min
2. _usuario_logado() # quem está logado (dono do explorer.exe → quser → getpass)
3. _cache_dns()      # Windows: hosts de IA no cache → { host: ferramenta }
4. _conexoes()       # conexões TCP ESTABLISHED de saída → (ip, porta, pid)
5. casa tudo:
     Windows+cache → autoridade = hosts do DNS; processo vem da conexão
     senão         → ferramentas pelos IPs das conexões
6. dedup por (usuario, ferramenta) na JANELA (8 h): 1 evento por uso/sessão
7. _enviar(evt) → POST para o coletor (/api/ingest)
```

### Chave de deduplicação

```python
_visto: dict[tuple, float]   # (usuario, ferramenta) → timestamp do último envio
JANELA = 28800               # 8 horas (GERENCIA_JANELA)
```

Isso evita inundar a base: um mesmo usuário usando a mesma IA gera **um** registro
por janela de 8 h, não um por minuto.

---

## O que o agente envia (payload do evento)

```jsonc
{
  "ts": "2026-10-16T13:20:00",          // hora LOCAL
  "usuario": "jsilva",                   // login do Windows resolvido na estação
  "usuario_fonte": "agente-local",
  "maquina": "PC-FINANCEIRO-07",
  "dominio": "chatgpt.com",             // domínio base (chave do inventário)
  "ferramenta": "ChatGPT (OpenAI)",     // nome amigável (da tabela DOMINIOS_IA)
  "processo": "chrome.exe",             // aplicativo dono da conexão (se houver)
  "ip": "104.18.x.x", "porta": 443,
  "via": "ip+dns",                      // como foi identificado
  "host": "chatgpt.com",               // hostname exato consultado
  "forma": "Conexão de rede",
  "tipo": "Uso de IA detectado na rede",
  "sens": "", "conteudo": "",           // VAZIOS: o agente não lê conteúdo
  "origem_sensor": "Sensor de rede (GerencIA)"
}
```

No coletor, `dominio` é casado com o **inventário** para decidir o status
(aprovada / não aprovada / condicional), e o evento entra no painel ao lado das
capturas da extensão.

---

## Limites honestos (o que o agente **não** faz)

- **Não lê conteúdo.** O tráfego é TLS; o agente vê *metadado* (nome, IP, processo,
  horário), nunca o prompt. Para conteúdo existem a **extensão** (no navegador) e o
  **proxy MITM** (opcional, corporativo).
- **IA fora da lista não é identificada.** Só mapeia os sufixos de `DOMINIOS_IA`.
  Incluir uma nova IA = acrescentar uma linha nessa tabela (e, se quiser status,
  cadastrá-la no inventário/Governança).
- **Sem cache de DNS fora do Windows**, a identificação cai para IP (best-effort) e
  pode perder itens ou herdar o ruído de CDN.
- **IA embarcada em outro domínio** (ex.: um Copilot dentro de um portal próprio da
  empresa) só aparece se o hostname bater com a tabela.

---

## Como estender

- **Nova ferramenta de IA:** adicione `"dominio.exemplo": "Nome Amigável"` em
  `DOMINIOS_IA` (sensor) e, para o status, cadastre o domínio no inventário pela
  tela de Governança do painel.
- **Mudar a janela de dedup:** variável de ambiente `GERENCIA_JANELA` (segundos).
- **Mudar o intervalo de varredura:** `GERENCIA_INTERVALO` (segundos, padrão 60).

---

*Arquivo de referência do código:* `borda/estacao/sensor.py` —
`DOMINIOS_IA`, `_casar_suf`, `_reindexar`, `_cache_dns`, `_conexoes`, `varrer`.
