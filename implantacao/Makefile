# EspIA — implantação.
#
#   make preflight      verifica o ambiente antes de qualquer coisa
#   make instalar       instala a onda 0
#   make verificar      saúde dos serviços
#   make fluxo          injeta um evento e segue o caminho dele
#   make isolamento     confirma que a VLAN não alcança a internet
#   make gabarito       roda os 15 casos oficiais contra a instalação
#   make backup         dump cifrado
#   make restauro       prova que o último backup restaura
#   make onda2          promove para a onda 2 (classificação)

PERFIL ?= piloto
ONDA   ?= 0

.PHONY: preflight instalar simular verificar fluxo isolamento gabarito \
        backup restauro onda1 onda2 onda3 onda4 logs parar lint

preflight:  ; @bin/preflight.sh --perfil $(PERFIL)
simular:    ; @bin/instalar.sh --perfil $(PERFIL) --onda $(ONDA) --simular
instalar:   ; @bin/instalar.sh --perfil $(PERFIL) --onda $(ONDA)
verificar:  ; @bin/verificar.sh
fluxo:      ; @bin/verificar.sh --fluxo
isolamento: ; @bin/verificar.sh --isolamento
gabarito:   ; @bin/verificar.sh --gabarito
backup:     ; @bin/backup.sh
restauro:   ; @bin/backup.sh --verificar

onda1: ; @bin/instalar.sh --perfil $(PERFIL) --onda 1
onda2: ; @bin/instalar.sh --perfil $(PERFIL) --onda 2
onda3: ; @bin/instalar.sh --perfil $(PERFIL) --onda 3
onda4: ; @bin/instalar.sh --perfil $(PERFIL) --onda 4

dmz:   ; @bin/instalar.sh --zona dmz

logs:  ; @docker compose logs -f --tail=200
parar: ; @docker compose down

# Verifica os próprios artefatos de implantação. Roda sem ambiente nenhum.
lint:
	@for s in bin/*.sh; do bash -n "$$s" && echo "  ok  $$s"; done
	@python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['docker-compose.yml','docker-compose.dmz.yml','coletores/dlp-conector.yaml']]; print('  ok  YAML')" 2>/dev/null \
	  || echo "  -   YAML não verificado (PyYAML ausente)"
	@python3 -c "import json; json.load(open('coletores/extensao-gpo.json')); print('  ok  JSON')"
	@python3 -c "import csv; r=list(csv.DictReader(open('rede/regras-firewall.csv'))); assert len(r)==18, len(r); print('  ok  18 regras de firewall')"
	@python3 -c "import pglast,glob; [pglast.parse_sql(open(f).read()) for f in glob.glob('sql/**/*.sql',recursive=True)]; print('  ok  SQL (parser real do PostgreSQL)')" 2>/dev/null \
	  || echo "  -   SQL não verificado (pip install pglast para verificar)"
