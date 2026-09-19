#!/usr/bin/env bash
# GerencIA · borda — empacota a extensão para instalação nos navegadores.
# Chrome e Edge usam o mesmo MV3; Firefox 121+ também, com browser_specific_settings.
# Gera os .zip em borda/pacotes/.
set -euo pipefail
cd "$(dirname "$0")"
EXT="extensao"
OUT="pacotes"
VER=$(grep -o '"version": *"[^"]*"' "$EXT/manifest.json" | head -1 | grep -oE '[0-9.]+')
mkdir -p "$OUT"
limpar() { find "$EXT" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true; find "$EXT" -name '.DS_Store' -delete 2>/dev/null || true; }
limpar
# Chrome + Edge (idênticos): tudo, menos o host nativo específico de Windows fica junto (é usado só se instalado).
z_chrome="$OUT/gerencia-extensao-chrome-edge-$VER.zip"
z_fire="$OUT/gerencia-extensao-firefox-$VER.zip"
rm -f "$z_chrome" "$z_fire"
( cd "$EXT" && zip -qr -X "../$z_chrome" . -x '*.DS_Store' -x '*__pycache__*' )
( cd "$EXT" && zip -qr -X "../$z_fire"   . -x '*.DS_Store' -x '*__pycache__*' )
echo "  $z_chrome    ($(du -h "$z_chrome" | cut -f1))"
echo "  $z_fire      ($(du -h "$z_fire" | cut -f1))"
echo "  versão empacotada: $VER"
