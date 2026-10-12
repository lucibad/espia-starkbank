# GerencIA · LLM local (Nível 1) — llamafile + Qwen3

O **primeiro nível de classificação por IA** do conteúdo capturado pela extensão roda
**na própria máquina do servidor**: um modelo **Qwen3** servido pelo **llamafile**
(um único executável, sem instalar runtime). O conteúdo **não sai do perímetro** —
só o resíduo ambíguo sobe para o LLM na nuvem.

## A cascata de classificação

| Nível | Quem | O que faz | Onde roda |
|---|---|---|---|
| **0** | Detectores determinísticos | CPF/CNPJ (dígito), cartão (Luhn), credenciais | na borda (extensão) |
| **1** | **Qwen3 via llamafile** | classifica **tipo** + **sensibilidade** do texto livre | **on-premise (servidor)** |
| **2** | LLM na nuvem (claude-opus-5) | só o resíduo de **baixa confiança** | nuvem |

O Nível 1 só é consultado quando o Nível 0 não resolveu (sem detecção determinística
ou tipo ainda “Conteúdo não classificado”), e só para capturas **com conteúdo**
(extensão e proxy; o agente de rede não tem conteúdo).

## Instalar (uma vez, no servidor)

```bash
cd ~/Downloads/espia
bash llm-local/instalar-llm-local.sh
```

Baixa para `~/.gerencia-llm/` (fora do repositório, ~2,7 GB):

- `llamafile` 0.10.6 — executável único (368 MB), de `mozilla-ai/llamafile`
- `Qwen3-4B-Q4_K_M.gguf` — modelo (2,33 GB), de `Qwen/Qwen3-4B-GGUF` no Hugging Face

## Subir o servidor do modelo

```bash
bash llm-local/rodar-llm-local.sh
```

Sobe uma API **compatível com OpenAI** em `127.0.0.1:8090`. Deixe rodando (é um
serviço). Para checar: `curl http://127.0.0.1:8090/v1/models`.

## Ligar ao GerencIA

O coletor já procura o LLM local automaticamente. Variáveis (opcionais):

| Variável | Padrão | Para quê |
|---|---|---|
| `GERENCIA_LLM_LOCAL` | `http://127.0.0.1:8090` | URL do llamafile |
| `GERENCIA_LLM_TIMEOUT` | `12` | segundos por classificação |
| `GERENCIA_LLM_MIN_CONF` | `0.55` | confiança mínima para aceitar o Nível 1 |
| `GERENCIA_LLM_PORTA` | `8090` | porta do llamafile ao subir |

> O LLM local usa a **8090** de propósito: a **8080** fica livre para o proxy MITM.

## Como saber se está funcionando

Cada captura passa a gravar **`classificado_por`**:

- `borda` — resolvido no Nível 0 (ou LLM local fora do ar);
- `llm-local` — **classificado pelo Qwen3** com confiança suficiente;
- `llm-local-baixa-confianca` — Qwen3 respondeu, mas abaixo do limiar → candidato ao Nível 2.

```bash
sqlite3 dados/espia.db "SELECT classificado_por, COUNT(*) FROM capturas GROUP BY 1;"
```

## Garantias e limites (honesto)

- **Privacidade:** no Nível 1 o conteúdo é processado localmente; nada vai para a nuvem.
- **Degradação:** se o llamafile não estiver no ar, a classificação cai para o Nível 0
  **instantaneamente** (conexão recusada) — o coletor nunca trava por causa do LLM.
- **Desempenho:** um Q4 de 4B classifica textos curtos em ~1–3 s em Mac com Metal
  (`-ngl 999`). Em CPU pura é mais lento; considere o Qwen3-1.7B se precisar.
- **Qualidade:** é um modelo pequeno. Ele acerta bem tipo/sensibilidade de texto claro,
  mas erra em casos sutis — por isso existe o limiar de confiança e o Nível 2.
- O Nível 1 **não substitui** os detectores: PII com dígito verificador continua sendo
  decidida de forma determinística, que é auditável.
