#!/usr/bin/env bash
# GerencIA · instala o LLM LOCAL (Nível 1 de classificação): llamafile + Qwen3.
# Os binários ficam FORA do repositório, em ~/.gerencia-llm/ (são ~2,7 GB).
set -euo pipefail
DEST="${GERENCIA_LLM_DIR:-$HOME/.gerencia-llm}"
LLAMAFILE_VER="0.10.6"
LLAMAFILE_URL="https://github.com/mozilla-ai/llamafile/releases/download/${LLAMAFILE_VER}/llamafile-${LLAMAFILE_VER}"
MODELO_URL="https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
MODELO_ARQ="Qwen3-4B-Q4_K_M.gguf"

mkdir -p "$DEST"
echo "Instalando em: $DEST"

if [ ! -x "$DEST/llamafile" ]; then
  echo "→ baixando llamafile ${LLAMAFILE_VER} (368 MB)…"
  curl -L --fail --progress-bar "$LLAMAFILE_URL" -o "$DEST/llamafile.part"
  chmod +x "$DEST/llamafile.part"; mv "$DEST/llamafile.part" "$DEST/llamafile"
else
  echo "→ llamafile já presente"
fi

if [ ! -f "$DEST/$MODELO_ARQ" ]; then
  echo "→ baixando Qwen3-4B (2,33 GB) do Hugging Face…"
  curl -L --fail --progress-bar "$MODELO_URL" -o "$DEST/$MODELO_ARQ.part"
  mv "$DEST/$MODELO_ARQ.part" "$DEST/$MODELO_ARQ"
else
  echo "→ modelo Qwen3 já presente"
fi

echo
echo "OK. Instalado:"
ls -lh "$DEST" | awk 'NR>1{print "  "$NF"  ("$5")"}'
echo
echo "Para subir o servidor:  bash llm-local/rodar-llm-local.sh"
