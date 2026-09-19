#!/usr/bin/env bash
# GerencIA — instalação.
#
#   ./instalar.sh --perfil piloto --onda 0
#   ./instalar.sh --perfil corporativo --onda 2
#   ./instalar.sh --zona dmz
#   ./instalar.sh --simular          # mostra o que faria, não executa
#
# Idempotente: rodar de novo atualiza, não duplica. Cada etapa é verificada
# antes da seguinte, e a instalação para na primeira que falhar — meia
# instalação num ambiente de segurança é pior que nenhuma.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERFIL="piloto"; ONDA="0"; ZONA="seguranca"; SIMULAR=0; PULAR_PREFLIGHT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --perfil) PERFIL="$2"; shift 2 ;;
    --onda)   ONDA="$2";   shift 2 ;;
    --zona)   ZONA="$2";   shift 2 ;;
    --simular) SIMULAR=1;  shift ;;
    --sem-preflight) PULAR_PREFLIGHT=1; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 64 ;;
  esac
done

NEGRITO=$'\033[1m'; VERDE=$'\033[92m'; VERMELHO=$'\033[91m'; CINZA=$'\033[90m'; FIM=$'\033[0m'
etapa()  { printf '\n%s▸ %s%s\n' "$NEGRITO" "$1" "$FIM"; }
nota()   { printf '  %s%s%s\n' "$CINZA" "$1" "$FIM"; }
morrer() { printf '\n%s✗ %s%s\n\n' "$VERMELHO" "$1" "$FIM"; exit 1; }
rodar()  { if (( SIMULAR )); then printf '  %s$ %s%s\n' "$CINZA" "$*" "$FIM"; else "$@"; fi; }

cd "$RAIZ"

printf '\n%sEspIA — instalação%s\n' "$NEGRITO" "$FIM"
printf '%sperfil %s · onda %s · zona %s%s%s\n' "$CINZA" "$PERFIL" "$ONDA" "$ZONA" \
       "$( ((SIMULAR)) && echo ' · SIMULAÇÃO' )" "$FIM"

# ── 1. pré-requisitos ────────────────────────────────────────────────────────
etapa "1/7  Pré-requisitos"
if (( PULAR_PREFLIGHT )); then
  nota "pulado por --sem-preflight (você assume o risco)"
else
  set +e; "$RAIZ/bin/preflight.sh" --perfil "$PERFIL" --zona "$ZONA" >/tmp/espia-preflight.txt 2>&1; rc=$?; set -e
  case $rc in
    0) nota "ambiente pronto" ;;
    2) nota "pronto com ressalvas — veja /tmp/espia-preflight.txt" ;;
    *) cat /tmp/espia-preflight.txt
       morrer "o ambiente tem bloqueios. Resolva-os e rode de novo." ;;
  esac
fi

# ── 2. configuração ──────────────────────────────────────────────────────────
etapa "2/7  Configuração"
ENVFILE=".env"; COMPOSE="docker-compose.yml"
[[ "$ZONA" == "dmz" ]] && { ENVFILE=".env.dmz"; COMPOSE="docker-compose.dmz.yml"; }

[[ -f "$ENVFILE" ]] || morrer "$ENVFILE não existe. Copie de ${ENVFILE}.exemplo e preencha."
nota "usando $ENVFILE e $COMPOSE"

for v in REGISTRO TAG; do
  grep -qE "^${v}=..*" "$ENVFILE" || morrer "$v não está preenchido em $ENVFILE"
done
nota "registro: $(grep -E '^REGISTRO=' "$ENVFILE" | cut -d= -f2-)"

# ── 3. segredos ──────────────────────────────────────────────────────────────
etapa "3/7  Segredos"
rodar "$RAIZ/bin/segredos.sh"

# ── 4. certificados ──────────────────────────────────────────────────────────
etapa "4/7  Certificados"
for f in certs/ca-interna.crt certs/espia.crt certs/espia.key; do
  [[ -r "$f" ]] || morrer "$f ausente. Emita pela PKI interna — não use autoassinado em produção."
done
if command -v openssl >/dev/null 2>&1; then
  FIM_VAL="$(openssl x509 -in certs/espia.crt -enddate -noout 2>/dev/null | cut -d= -f2)"
  nota "certificado válido até $FIM_VAL"
  openssl x509 -in certs/espia.crt -checkend 2592000 -noout >/dev/null 2>&1 \
    || morrer "o certificado expira em menos de 30 dias. Renove antes de instalar."
fi

# ── 5. imagens ───────────────────────────────────────────────────────────────
etapa "5/7  Imagens"
DC=(docker compose)
docker compose version >/dev/null 2>&1 || DC=(docker-compose)
rodar "${DC[@]}" -f "$COMPOSE" --env-file "$ENVFILE" pull
nota "imagens vindas do registro interno; nada foi buscado na internet"

# ── 6. subida ────────────────────────────────────────────────────────────────
etapa "6/7  Subida"
PERFIS=()
case "$ONDA" in
  0|1) nota "ondas 0 e 1 sobem SEM nenhum modelo — só regras. É de propósito." ;;
  2)   PERFIS=(--profile onda2) ;;
  3)   PERFIS=(--profile onda2 --profile onda3) ;;
  4)   PERFIS=(--profile completo) ;;
  *)   morrer "onda inválida: $ONDA (0 a 4)" ;;
esac
rodar "${DC[@]}" -f "$COMPOSE" --env-file "$ENVFILE" "${PERFIS[@]}" up -d --remove-orphans

if (( ! SIMULAR )); then
  nota "aguardando os serviços ficarem saudáveis..."
  for _ in $(seq 1 60); do
    if ! "${DC[@]}" -f "$COMPOSE" --env-file "$ENVFILE" ps --format '{{.Health}}' 2>/dev/null \
         | grep -qE 'starting|unhealthy'; then break; fi
    sleep 5
  done
fi

# ── 7. verificação ───────────────────────────────────────────────────────────
etapa "7/7  Verificação"
if (( SIMULAR )); then
  nota "simulação: verificação não executada"
else
  set +e; "$RAIZ/bin/verificar.sh" --zona "$ZONA"; rc=$?; set -e
  (( rc != 0 )) && morrer "a instalação subiu mas não passou na verificação. Não libere o acesso ainda."
fi

printf '\n%s✓ Instalado.%s\n\n' "$VERDE" "$FIM"
if [[ "$ZONA" == "seguranca" ]]; then
  cat <<'PROXIMO'
  Próximos passos, nesta ordem:

    1. Abra os chamados de rede com rede/regras-firewall.csv — todos de uma vez.
    2. Ligue o primeiro coletor (DLP) e confirme evento chegando:
         bin/verificar.sh --fluxo
    3. Carregue a política oficial e rode o gabarito:
         docker compose exec nucleo espia validar
       15/15 é o critério de aceite. Menos que isso, não siga.
    4. Só então libere o console para Compliance.

  O sistema entra em modo sombra: classifica, registra e NÃO notifica ninguém,
  por 15 dias. É o tempo de descobrir os falsos positivos com a equipe, e não
  com a diretoria.
PROXIMO
fi
