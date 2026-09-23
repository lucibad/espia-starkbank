#!/usr/bin/env bash
# GerencIA · borda — empacota o que vai para a estação do usuário.
#   1) as extensões de navegador (Chrome/Edge e Firefox)
#   2) o pacote de instalação do agente-sensor (serviço do Windows) + manual
# Saída em borda/pacotes/.
set -euo pipefail
cd "$(dirname "$0")"
OUT="pacotes"; mkdir -p "$OUT"
limpar(){ find "$1" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
          find "$1" -name '.DS_Store' -delete 2>/dev/null || true; }

# ---------- 1) extensão ----------
EXT="extensao"; limpar "$EXT"
VER=$(grep -o '"version": *"[^"]*"' "$EXT/manifest.json" | head -1 | grep -oE '[0-9.]+')
for alvo in chrome-edge firefox; do
  z="$OUT/gerencia-extensao-$alvo-$VER.zip"; rm -f "$z"
  ( cd "$EXT" && zip -qr -X "../$z" . -x '*.DS_Store' -x '*__pycache__*' )
  echo "  $z"
done

# ---------- 2) agente de estação (serviço do Windows) ----------
E="estacao"; limpar "$E"
STAGE="$OUT/.stage-estacao/GerencIA-Agente-Estacao"
rm -rf "$OUT/.stage-estacao"; mkdir -p "$STAGE/servico"
cp "$E/sensor.py" "$E/INSTALAR.bat" "$E/DESINSTALAR.bat" "$E/LEIA-PRIMEIRO.txt" "$STAGE/"
cp "$E/servico/servico_win.py" "$E/servico/instalar-servico.ps1" \
   "$E/servico/gerenciar-servico.ps1" "$E/servico/LEIA-ME.md" "$STAGE/servico/"
[ -f "$E/manual/Manual-Instalacao-Estacao.pdf" ] && cp "$E/manual/Manual-Instalacao-Estacao.pdf" "$STAGE/"
z="$OUT/GerencIA-Agente-Estacao.zip"; rm -f "$z"
( cd "$OUT/.stage-estacao" && zip -qr -X "../GerencIA-Agente-Estacao.zip" "GerencIA-Agente-Estacao" -x '*.DS_Store' )
rm -rf "$OUT/.stage-estacao"
echo "  $z"
echo "  (o manual em PDF se regenera do HTML em estacao/manual/ com um navegador headless)"
