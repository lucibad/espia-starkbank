#!/usr/bin/env bash
# GerencIA — geração dos segredos locais.
#
# Cria segredos/ com um arquivo por segredo, modo 600. É esse diretório que o
# compose monta em /run/secrets. Nada de senha em variável de ambiente: variável
# de ambiente aparece em `docker inspect`, em `ps` e no log de quem depurou.
#
#   ./segredos.sh              # gera os que faltam, não toca nos existentes
#   ./segredos.sh --girar pg_senha
#
# Os tokens de canal (Telegram, Slack, WhatsApp) NÃO são gerados aqui — vêm de
# fora. O script cria o arquivo vazio e avisa que falta preencher.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$RAIZ/segredos"
GIRAR="${2:-}"
[[ "${1:-}" == "--girar" ]] || GIRAR=""

GERADOS=(pg_senha minio_chave minio_segredo jwt_assinatura fila_senha)
EXTERNOS=(telegram_token slack_webhook whatsapp_token)

mkdir -p "$DIR"
chmod 700 "$DIR"

aleatorio() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-48}"; }

for s in "${GERADOS[@]}"; do
  alvo="$DIR/$s"
  if [[ -s "$alvo" && "$GIRAR" != "$s" ]]; then
    echo "  = $s  (já existe, mantido)"
    continue
  fi
  if [[ -s "$alvo" ]]; then
    cp -p "$alvo" "$alvo.anterior.$(date +%Y%m%d%H%M%S)"
    chmod 600 "$alvo".anterior.*
    echo "  ~ $s  (girado; a cópia anterior fica ao lado, para a transição)"
  else
    echo "  + $s"
  fi
  printf '%s' "$(aleatorio 48)" > "$alvo"
  chmod 600 "$alvo"
done

FALTAM=0
for s in "${EXTERNOS[@]}"; do
  alvo="$DIR/$s"
  if [[ -s "$alvo" ]]; then
    chmod 600 "$alvo"
    echo "  = $s  (preenchido)"
  else
    : > "$alvo"; chmod 600 "$alvo"
    echo "  ? $s  (vazio — preencha com o valor fornecido pela equipe de canais)"
    FALTAM=$((FALTAM+1))
  fi
done

echo
echo "  segredos em: $DIR"
echo "  permissão:   $(stat -c '%a' "$DIR" 2>/dev/null || stat -f '%Lp' "$DIR")"
echo
echo "  Adicione ao backup COM CRIPTOGRAFIA separada, e ao .gitignore. Estes"
echo "  arquivos nunca entram em repositório, nem em ticket, nem em anexo."

if (( FALTAM > 0 )); then
  echo
  echo "  Faltam $FALTAM token(s) externo(s). Os canais correspondentes ficam"
  echo "  desligados até serem preenchidos — o resto do sistema sobe normalmente."
fi
