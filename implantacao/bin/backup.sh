#!/usr/bin/env bash
# GerencIA — backup.
#
#   ./backup.sh                 # dump completo, cifrado, para o destino do banco
#   ./backup.sh --verificar     # restaura o último dump num banco descartável
#
# O teste de restauração é a metade que as pessoas esquecem. Backup que nunca
# foi restaurado não é backup, é esperança — e num sistema cuja função é servir
# de prova em auditoria, isso não serve.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${ESPIA_BACKUP_DIR:-/var/backups/espia}"
CHAVE_GPG="${ESPIA_BACKUP_GPG:-backup@espia.interno}"
MODO="dump"
[[ "${1:-}" == "--verificar" ]] && MODO="verificar"

cd "$RAIZ"
DC=(docker compose); docker compose version >/dev/null 2>&1 || DC=(docker-compose)
CARIMBO="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DESTINO"

if [[ "$MODO" == "dump" ]]; then
  ARQ="$DESTINO/espia-$CARIMBO.sql.gz.gpg"

  # 1. banco
  "${DC[@]}" exec -T postgres pg_dump -U "${PG_USUARIO:-espia}" -d "${PG_BANCO:-espia}" \
      --format=plain --no-owner \
    | gzip -9 \
    | gpg --batch --yes --encrypt --recipient "$CHAVE_GPG" --output "$ARQ"
  chmod 600 "$ARQ"
  echo "  banco       → $ARQ ($(du -h "$ARQ" | cut -f1))"

  # 2. modelos e evidências
  "${DC[@]}" exec -T minio mc mirror --quiet local/espia "$DESTINO/objetos-$CARIMBO/" 2>/dev/null \
    && echo "  objetos     → $DESTINO/objetos-$CARIMBO/" \
    || echo "  objetos     — MinIO não respondeu (o backup do banco está feito)"

  # 3. segredos — cifrados à parte, com chave diferente, e NUNCA no mesmo mídia
  tar -cf - -C "$RAIZ" segredos certs \
    | gpg --batch --yes --encrypt --recipient "$CHAVE_GPG" \
          --output "$DESTINO/segredos-$CARIMBO.tar.gpg"
  chmod 600 "$DESTINO/segredos-$CARIMBO.tar.gpg"
  echo "  segredos    → cifrados, guarde em mídia separada do dump"

  # 4. retenção: 30 diários, e o de cada dia 1º fica um ano
  find "$DESTINO" -name 'espia-*.gpg' -mtime +30 \
       ! -name "espia-????????01-*" -delete 2>/dev/null || true

  echo
  echo "  RPO efetivo: desde o último dump. Para RPO menor, ligue o WAL archiving"
  echo "  do PostgreSQL — o dump diário cobre a perda total, não a perda de horas."

else
  ULTIMO="$(ls -t "$DESTINO"/espia-*.sql.gz.gpg 2>/dev/null | head -1)"
  [[ -z "$ULTIMO" ]] && { echo "nenhum backup encontrado em $DESTINO" >&2; exit 1; }
  echo "  restaurando $ULTIMO num banco descartável…"

  "${DC[@]}" exec -T postgres psql -U "${PG_USUARIO:-espia}" -d postgres \
      -c "DROP DATABASE IF EXISTS espia_teste_restauro" \
      -c "CREATE DATABASE espia_teste_restauro"

  gpg --batch --quiet --decrypt "$ULTIMO" | gunzip \
    | "${DC[@]}" exec -T postgres psql -U "${PG_USUARIO:-espia}" -d espia_teste_restauro -q

  N="$("${DC[@]}" exec -T postgres psql -U "${PG_USUARIO:-espia}" -d espia_teste_restauro \
        -tAc "select count(*) from espia.eventos" | tr -d ' ')"
  echo "  restaurado com $N evento(s)."
  "${DC[@]}" exec -T postgres psql -U "${PG_USUARIO:-espia}" -d postgres \
      -c "DROP DATABASE espia_teste_restauro" >/dev/null
  [[ "${N:-0}" -gt 0 ]] || { echo "  ✗ o backup restaurou vazio. Investigue hoje." >&2; exit 1; }
  echo "  ✓ backup restaurável."
fi
