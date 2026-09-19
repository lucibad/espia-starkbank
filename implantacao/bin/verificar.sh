#!/usr/bin/env bash
# GerencIA — verificação pós-instalação.
#
#   ./verificar.sh                # saúde dos serviços
#   ./verificar.sh --fluxo        # injeta um evento de teste e segue o caminho dele
#   ./verificar.sh --isolamento   # confirma que a VLAN não alcança a internet
#   ./verificar.sh --gabarito     # roda os 15 casos oficiais contra a instalação
#
# O teste que importa é o --fluxo: ele prova que um evento sai do coletor, passa
# pelas regras e vira alerta. Serviço "saudável" que não processa evento é
# serviço que não faz nada.

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZONA="seguranca"; MODO="saude"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --zona) ZONA="$2"; shift 2 ;;
    --fluxo) MODO="fluxo"; shift ;;
    --isolamento) MODO="isolamento"; shift ;;
    --gabarito) MODO="gabarito"; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 64 ;;
  esac
done

VERDE=$'\033[92m'; VERMELHO=$'\033[91m'; CINZA=$'\033[90m'; NEGRITO=$'\033[1m'; FIM=$'\033[0m'
FALHA=0
ok()  { printf '  %s✓%s %s\n' "$VERDE" "$FIM" "$1"; }
nok() { printf '  %s✗%s %s\n' "$VERMELHO" "$FIM" "$1"; FALHA=$((FALHA+1)); }

cd "$RAIZ"
COMPOSE="docker-compose.yml"; ENVFILE=".env"
[[ "$ZONA" == "dmz" ]] && { COMPOSE="docker-compose.dmz.yml"; ENVFILE=".env.dmz"; }
DC=(docker compose); docker compose version >/dev/null 2>&1 || DC=(docker-compose)
dc() { "${DC[@]}" -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }

printf '\n%sVerificação — %s%s\n' "$NEGRITO" "$MODO" "$FIM"
printf '%s\n' "$(printf '─%.0s' {1..60})"

case "$MODO" in

saude)
  ESTADO="$(dc ps --format '{{.Service}}\t{{.State}}\t{{.Health}}' 2>/dev/null)"
  [[ -z "$ESTADO" ]] && { nok "nenhum serviço em execução"; exit 1; }
  while IFS=$'\t' read -r svc estado saude; do
    [[ -z "$svc" ]] && continue
    if [[ "$estado" == "running" && ( -z "$saude" || "$saude" == "healthy" ) ]]; then
      ok "$svc"
    else
      nok "$svc — estado=$estado saúde=${saude:-n/d}"
    fi
  done <<< "$ESTADO"

  # O banco tem de ter esquema, não só estar de pé.
  if dc exec -T postgres psql -U "${PG_USUARIO:-espia}" -d "${PG_BANCO:-espia}" \
       -tAc "select count(*) from information_schema.tables where table_schema='espia'" 2>/dev/null \
       | grep -qE '^[1-9]'; then
    ok "esquema espia criado"
  else
    nok "esquema espia ausente — o init SQL não rodou"
  fi
  ;;

fluxo)
  # Evento sintético, marcado como teste, com informação classificada Crítica em
  # ferramenta não aprovada: tem de virar Crítico por R02 e gerar alerta.
  ID="TESTE-$(date +%s)"
  CORPO=$(cat <<JSON
{"id":"$ID","origem":"verificacao","usuario":"svc.espia.teste",
 "ferramenta_id":"IA-99","informacao_id":"INFO-TESTE-CRITICA",
 "sensibilidade":"Crítica","aprovada":false,"qtd_itens":1,
 "ocorrido_em":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","teste":true}
JSON
)
  RESP="$(curl -sS --max-time 20 \
      --cacert certs/ca-interna.crt \
      --cert certs/coletor-teste.crt --key certs/coletor-teste.key \
      -H 'Content-Type: application/json' -d "$CORPO" \
      "https://${HOST_INGESTAO:-localhost}:8443/eventos" 2>&1)" || true

  if grep -q '"aceito"' <<<"$RESP"; then ok "ingestão aceitou o evento"
  else nok "ingestão recusou ou não respondeu: ${RESP:0:200}"; fi

  sleep 8
  NIVEL="$(dc exec -T postgres psql -U "${PG_USUARIO:-espia}" -d "${PG_BANCO:-espia}" \
        -tAc "select risco, regra from espia.eventos where id='$ID'" 2>/dev/null | tr -d ' ')"
  case "$NIVEL" in
    Crítico\|R02*) ok "motor de regras classificou como Crítico por R02" ;;
    "")            nok "o evento não chegou ao banco em 8 s — veja a fila e o enriquecedor" ;;
    *)             nok "classificação inesperada: $NIVEL (esperado Crítico|R02)" ;;
  esac

  ALERTA="$(dc exec -T postgres psql -U "${PG_USUARIO:-espia}" -d "${PG_BANCO:-espia}" \
        -tAc "select count(*) from espia.alertas where evento_id='$ID'" 2>/dev/null | tr -d ' ')"
  [[ "$ALERTA" == "1" ]] && ok "alerta gerado" || nok "alerta não gerado (encontrados: ${ALERTA:-0})"

  printf '\n  %sLimpeza:%s o evento fica no banco com teste=true e é expurgado\n' "$CINZA" "$FIM"
  printf '  %spela rotina diária. Não conte-o nos indicadores.%s\n' "$CINZA" "$FIM"
  ;;

isolamento)
  # Este teste PASSA quando a saída falha. Não é engano.
  if timeout 4 bash -c 'exec 3<>/dev/tcp/1.1.1.1/443' 2>/dev/null; then
    nok "este host alcança a internet — a VLAN de Segurança não pode ter rota de saída"
  else
    ok "sem rota para a internet"
  fi
  for c in $(dc ps --services 2>/dev/null); do
    if dc exec -T "$c" sh -c 'timeout 4 wget -q -O- https://1.1.1.1 >/dev/null 2>&1' 2>/dev/null; then
      nok "o contêiner $c consegue sair para a internet"
    else
      ok "$c isolado"
    fi
  done
  ;;

gabarito)
  # O mesmo critério de aceite do protótipo, rodando contra a instalação real.
  SAIDA="$(dc exec -T nucleo espia validar 2>&1)" || true
  printf '%s\n' "$SAIDA" | tail -20
  if grep -qE '15/15|15 de 15' <<<"$SAIDA"; then
    ok "15/15 casos oficiais reproduzidos pela instalação"
  else
    nok "a instalação NÃO reproduz o gabarito — não libere para Compliance"
  fi
  ;;
esac

printf '\n'
if (( FALHA )); then
  printf '%s%d verificação(ões) falharam.%s\n\n' "$VERMELHO" "$FALHA" "$FIM"
  exit 1
fi
printf '%sTudo verificado.%s\n\n' "$VERDE" "$FIM"
