#!/usr/bin/env bash
# Sobe o LLM local (Qwen3 via llamafile) com API compatível com OpenAI em :8080.
# O GerencIA aponta para ele com GERENCIA_LLM_LOCAL (padrão http://127.0.0.1:8080).
set -euo pipefail
DEST="${GERENCIA_LLM_DIR:-$HOME/.gerencia-llm}"
PORTA="${GERENCIA_LLM_PORTA:-8090}"
MODELO="$DEST/Qwen3-4B-Q4_K_M.gguf"
[ -x "$DEST/llamafile" ] || { echo "llamafile não instalado. Rode: bash llm-local/instalar-llm-local.sh"; exit 1; }
[ -f "$MODELO" ] || { echo "modelo não encontrado em $MODELO"; exit 1; }
echo "GerencIA · LLM local (Qwen3) em 127.0.0.1:$PORTA — classificação Nível 1, on-premise"
exec "$DEST/llamafile" -m "$MODELO" --server \
     --host 127.0.0.1 --port "$PORTA" -c 4096 -ngl 999
