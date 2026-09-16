#!/usr/bin/env bash
# EspIA — verificação de pré-requisitos do ambiente.
#
# Roda ANTES de instalar qualquer coisa, no servidor de destino, e responde a
# uma pergunta só: este ambiente está pronto?
#
#   ./preflight.sh                      # perfil piloto
#   ./preflight.sh --perfil corporativo
#   ./preflight.sh --perfil piloto --json
#
# Saída:  0 = pronto · 1 = há bloqueio · 2 = pronto com ressalvas
#
# Não escreve nada, não instala nada, não precisa de root.

set -uo pipefail

PERFIL="piloto"
FORMATO="texto"
ZONA="seguranca"          # seguranca | dmz
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --perfil) PERFIL="${2:-}"; shift 2 ;;
    --zona)   ZONA="${2:-}";   shift 2 ;;
    --json)   FORMATO="json";  shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 64 ;;
  esac
done

# ── perfis de dimensionamento (seção 14 da arquitetura) ──────────────────────
case "$PERFIL" in
  piloto)        VCPU_MIN=8;  RAM_MIN=16;  DISCO_MIN=200 ;;
  departamental) VCPU_MIN=16; RAM_MIN=48;  DISCO_MIN=500 ;;
  corporativo)   VCPU_MIN=40; RAM_MIN=100; DISCO_MIN=2000 ;;
  *) echo "perfil inválido: $PERFIL (use piloto, departamental ou corporativo)" >&2; exit 64 ;;
esac

OK=0; AVISO=0; FALHA=0
declare -a LINHAS

if [[ -t 1 && "$FORMATO" == "texto" ]]; then
  VERDE=$'\033[92m'; AMARELO=$'\033[93m'; VERMELHO=$'\033[91m'
  CINZA=$'\033[90m'; NEGRITO=$'\033[1m'; FIM=$'\033[0m'
else
  VERDE=""; AMARELO=""; VERMELHO=""; CINZA=""; NEGRITO=""; FIM=""
fi

registrar() {           # registrar <estado> <item> <detalhe>
  local estado="$1" item="$2" detalhe="$3"
  LINHAS+=("$estado|$item|$detalhe")
  case "$estado" in
    ok)     OK=$((OK+1));    [[ $FORMATO == texto ]] && printf '  %s✓%s %-34s %s%s%s\n' "$VERDE" "$FIM" "$item" "$CINZA" "$detalhe" "$FIM" ;;
    aviso)  AVISO=$((AVISO+1)); [[ $FORMATO == texto ]] && printf '  %s!%s %-34s %s\n' "$AMARELO" "$FIM" "$item" "$detalhe" ;;
    falha)  FALHA=$((FALHA+1)); [[ $FORMATO == texto ]] && printf '  %s✗%s %-34s %s\n' "$VERMELHO" "$FIM" "$item" "$detalhe" ;;
  esac
}

secao() { [[ $FORMATO == texto ]] && printf '\n%s%s%s\n%s\n' "$NEGRITO" "$1" "$FIM" "$(printf '─%.0s' {1..66})"; }

[[ $FORMATO == texto ]] && {
  printf '\n%sEspIA — pré-requisitos%s\n' "$NEGRITO" "$FIM"
  printf '%sperfil: %s · zona: %s · host: %s · %s%s\n' \
    "$CINZA" "$PERFIL" "$ZONA" "$(hostname)" "$(date '+%d/%m/%Y %H:%M')" "$FIM"
}

# ── 1. sistema operacional ───────────────────────────────────────────────────
secao "Sistema"

if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  case "${ID:-}" in
    rhel|ol|rocky|almalinux|centos|ubuntu|debian)
      registrar ok "distribuição" "${PRETTY_NAME:-$ID}" ;;
    *)
      registrar aviso "distribuição" "${PRETTY_NAME:-desconhecida} — homologado em RHEL/Oracle/Ubuntu LTS" ;;
  esac
else
  registrar aviso "distribuição" "/etc/os-release ausente"
fi

KERNEL="$(uname -r)"
if printf '%s\n5.10\n' "${KERNEL%%-*}" | sort -V | head -1 | grep -q '^5\.10$'; then
  registrar ok "kernel" "$KERNEL"
else
  registrar aviso "kernel" "$KERNEL — recomendado ≥ 5.10 (cgroups v2)"
fi

if [[ -d /sys/fs/cgroup/cgroup.controllers ]] || grep -qs cgroup2 /proc/filesystems; then
  registrar ok "cgroups v2" "disponível"
else
  registrar aviso "cgroups v2" "não detectado — limites de recurso podem não valer"
fi

# ── 2. capacidade ────────────────────────────────────────────────────────────
secao "Capacidade (perfil $PERFIL)"

VCPU="$(nproc 2>/dev/null || echo 0)"
if (( VCPU >= VCPU_MIN )); then
  registrar ok "vCPU" "$VCPU (mínimo $VCPU_MIN)"
else
  registrar falha "vCPU" "$VCPU — o perfil $PERFIL pede $VCPU_MIN"
fi

RAM="$(awk '/MemTotal/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0)"
if (( RAM >= RAM_MIN )); then
  registrar ok "memória" "${RAM} GB (mínimo ${RAM_MIN} GB)"
else
  registrar falha "memória" "${RAM} GB — o perfil $PERFIL pede ${RAM_MIN} GB"
fi

ALVO="${ESPIA_DADOS:-/var/lib/espia}"
PONTO="$ALVO"; while [[ ! -d "$PONTO" && "$PONTO" != "/" ]]; do PONTO="$(dirname "$PONTO")"; done
DISCO="$(df -BG --output=avail "$PONTO" 2>/dev/null | tail -1 | tr -dc '0-9')"
DISCO="${DISCO:-0}"
if (( DISCO >= DISCO_MIN )); then
  registrar ok "disco em $PONTO" "${DISCO} GB livres (mínimo ${DISCO_MIN} GB)"
else
  registrar falha "disco em $PONTO" "${DISCO} GB livres — o perfil $PERFIL pede ${DISCO_MIN} GB"
fi

if command -v lsblk >/dev/null 2>&1 && lsblk -dno ROTA "$(df --output=source "$PONTO" 2>/dev/null | tail -1)" 2>/dev/null | grep -q '^0$'; then
  registrar ok "armazenamento" "SSD/NVMe"
else
  registrar aviso "armazenamento" "não confirmado como SSD — o PostgreSQL do EspIA pede SSD"
fi

# ── 3. runtime de contêiner ──────────────────────────────────────────────────
secao "Runtime"

RUNTIME=""
for c in docker podman; do command -v "$c" >/dev/null 2>&1 && { RUNTIME="$c"; break; }; done

if [[ -z "$RUNTIME" ]]; then
  registrar falha "runtime de contêiner" "nem docker nem podman encontrados"
else
  VER="$("$RUNTIME" --version 2>/dev/null | head -1)"
  registrar ok "runtime de contêiner" "$VER"
  if "$RUNTIME" info >/dev/null 2>&1; then
    registrar ok "daemon" "respondendo"
  else
    registrar falha "daemon" "$RUNTIME instalado mas não responde (serviço parado, ou usuário fora do grupo)"
  fi
  if "$RUNTIME" compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 \
     || command -v podman-compose >/dev/null 2>&1; then
    registrar ok "compose" "disponível"
  else
    registrar falha "compose" "ausente — o pacote de instalação é um compose"
  fi
fi

if command -v python3 >/dev/null 2>&1; then
  PV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
  if python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    registrar ok "python3" "$PV"
  else
    registrar falha "python3" "$PV — o núcleo pede 3.9 ou superior"
  fi
else
  registrar falha "python3" "ausente"
fi

# ── 4. portas ────────────────────────────────────────────────────────────────
secao "Portas"

if [[ "$ZONA" == "dmz" ]]; then
  PORTAS=(8443)
else
  PORTAS=(8443 8081 8082 8083 5432 6379 9000)
fi

em_uso() {
  if command -v ss >/dev/null 2>&1; then ss -lntH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
  elif command -v netstat >/dev/null 2>&1; then netstat -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
  else return 2; fi
}
for p in "${PORTAS[@]}"; do
  em_uso "$p"; r=$?
  case $r in
    0) registrar falha "porta $p" "já está em uso" ;;
    1) registrar ok "porta $p" "livre" ;;
    *) registrar aviso "porta $p" "não foi possível verificar (sem ss/netstat)" ;;
  esac
done

# ── 5. relógio ───────────────────────────────────────────────────────────────
secao "Relógio"

# Data e hora do evento são prova. Máquina fora de sincronia gera R12 falso e
# quebra a ordem cronológica da trilha de auditoria.
if command -v timedatectl >/dev/null 2>&1; then
  if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    registrar ok "NTP" "sincronizado ($(timedatectl show -p Timezone --value 2>/dev/null))"
  else
    registrar falha "NTP" "relógio NÃO sincronizado — horário de evento é prova, não pode derivar"
  fi
elif command -v chronyc >/dev/null 2>&1 && chronyc tracking >/dev/null 2>&1; then
  registrar ok "NTP" "chrony respondendo"
else
  registrar aviso "NTP" "não verificável neste host — confirme com a infraestrutura"
fi

# ── 6. rede ──────────────────────────────────────────────────────────────────
secao "Rede"

# Na VLAN de Segurança, saída para a internet é DEFEITO, não recurso.
testar_saida() {
  local destino="1.1.1.1"
  if command -v timeout >/dev/null 2>&1; then
    timeout 3 bash -c "exec 3<>/dev/tcp/$destino/443" 2>/dev/null && return 0 || return 1
  fi
  return 2
}
testar_saida; saida=$?
if [[ "$ZONA" == "seguranca" ]]; then
  case $saida in
    0) registrar falha "isolamento da VLAN" "este host ALCANÇA a internet — a VLAN de Segurança não pode ter rota de saída" ;;
    1) registrar ok "isolamento da VLAN" "sem rota para a internet, como deve ser" ;;
    *) registrar aviso "isolamento da VLAN" "não verificável" ;;
  esac
else
  case $saida in
    0) registrar ok "saída da DMZ" "alcança a internet (será restrita por allowlist no proxy)" ;;
    1) registrar falha "saída da DMZ" "o gateway de notificação precisa alcançar o proxy de saída" ;;
    *) registrar aviso "saída da DMZ" "não verificável" ;;
  esac
fi

resolver() { getent hosts "$1" >/dev/null 2>&1; }
for h in ${ESPIA_HOSTS_DEPENDENCIA:-}; do
  if resolver "$h"; then registrar ok "DNS $h" "resolve"
  else registrar falha "DNS $h" "não resolve — declare no DNS interno antes de instalar"; fi
done
[[ -z "${ESPIA_HOSTS_DEPENDENCIA:-}" ]] && \
  registrar aviso "DNS das dependências" "defina ESPIA_HOSTS_DEPENDENCIA=\"sso.banco dlp.banco siem.banco\" para checar"

# ── 7. certificados e segredos ───────────────────────────────────────────────
secao "Certificados e segredos"

CA="${ESPIA_CA:-$RAIZ/certs/ca-interna.crt}"
CRT="${ESPIA_CRT:-$RAIZ/certs/espia.crt}"
KEY="${ESPIA_KEY:-$RAIZ/certs/espia.key}"

if [[ -r "$CA" ]]; then registrar ok "CA interna" "$CA"
else registrar falha "CA interna" "ausente em $CA — o mTLS dos coletores depende dela"; fi

if [[ -r "$CRT" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    if openssl x509 -in "$CRT" -checkend 2592000 -noout >/dev/null 2>&1; then
      registrar ok "certificado do servidor" "válido por mais de 30 dias"
    else
      registrar falha "certificado do servidor" "expira em menos de 30 dias (ou é ilegível)"
    fi
  else
    registrar aviso "certificado do servidor" "presente, openssl ausente para validar"
  fi
else
  registrar falha "certificado do servidor" "ausente em $CRT"
fi

if [[ -r "$KEY" ]]; then
  MODO="$(stat -c '%a' "$KEY" 2>/dev/null || stat -f '%Lp' "$KEY" 2>/dev/null)"
  if [[ "$MODO" == "600" || "$MODO" == "400" ]]; then
    registrar ok "chave privada" "modo $MODO"
  else
    registrar falha "chave privada" "modo $MODO — precisa ser 600"
  fi
else
  registrar falha "chave privada" "ausente em $KEY"
fi

if [[ -d "$RAIZ/segredos" ]]; then
  ABERTOS="$(find "$RAIZ/segredos" -type f ! -perm 600 ! -perm 400 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$ABERTOS" == "0" ]]; then registrar ok "segredos" "todos com permissão restrita"
  else registrar falha "segredos" "$ABERTOS arquivo(s) com permissão frouxa em segredos/"; fi
else
  registrar aviso "segredos" "pasta ainda não criada — rode bin/segredos.sh"
fi

# ── 8. imagens ───────────────────────────────────────────────────────────────
secao "Imagens"

REGISTRO="${ESPIA_REGISTRO:-}"
if [[ -z "$REGISTRO" ]]; then
  registrar aviso "registro interno" "ESPIA_REGISTRO não definido — as imagens têm de vir de um registro interno, não da internet"
elif [[ -n "$RUNTIME" ]] && "$RUNTIME" info >/dev/null 2>&1; then
  if "$RUNTIME" pull "$REGISTRO/espia-ingestao:${ESPIA_TAG:-latest}" >/dev/null 2>&1; then
    registrar ok "registro interno" "$REGISTRO acessível"
  else
    registrar falha "registro interno" "$REGISTRO não respondeu ao pull de teste"
  fi
else
  registrar aviso "registro interno" "$REGISTRO declarado, sem runtime para testar"
fi

# ── resumo ───────────────────────────────────────────────────────────────────
if [[ $FORMATO == json ]]; then
  printf '{"perfil":"%s","zona":"%s","host":"%s","ok":%d,"avisos":%d,"falhas":%d,"itens":[' \
    "$PERFIL" "$ZONA" "$(hostname)" "$OK" "$AVISO" "$FALHA"
  sep=""
  for l in "${LINHAS[@]}"; do
    IFS='|' read -r e i d <<<"$l"
    printf '%s{"estado":"%s","item":"%s","detalhe":"%s"}' "$sep" "$e" "$i" "${d//\"/\'}"
    sep=","
  done
  printf ']}\n'
else
  printf '\n%s\n' "$(printf '─%.0s' {1..66})"
  printf '  %s%d ok%s · %s%d aviso(s)%s · %s%d bloqueio(s)%s\n' \
    "$VERDE" "$OK" "$FIM" "$AMARELO" "$AVISO" "$FIM" "$VERMELHO" "$FALHA" "$FIM"
  if (( FALHA > 0 )); then
    printf '\n  %sNão instale ainda.%s Cada bloqueio acima vira um chamado para a\n' "$NEGRITO" "$FIM"
    printf '  infraestrutura. Leve todos de uma vez, não um por dia.\n\n'
  elif (( AVISO > 0 )); then
    printf '\n  Ambiente utilizável. Os avisos não impedem a instalação, mas\n'
    printf '  cada um deles é uma pergunta que a auditoria vai fazer depois.\n\n'
  else
    printf '\n  %sAmbiente pronto.%s  Próximo passo:  bin/instalar.sh --perfil %s\n\n' "$VERDE" "$FIM" "$PERFIL"
  fi
fi

(( FALHA > 0 )) && exit 1
(( AVISO > 0 )) && exit 2
exit 0
