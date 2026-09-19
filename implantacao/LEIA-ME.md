# implantacao/

O que instala o GerencIA no ambiente do banco. O runbook completo está em
`docs/GerencIA-implantacao.md`; aqui está o mapa dos arquivos.

```bash
./bin/preflight.sh --perfil piloto        # o ambiente está pronto?
cp .env.exemplo .env && vim .env
./bin/instalar.sh --perfil piloto --onda 0
./bin/verificar.sh --fluxo
```

## Os arquivos

```
bin/
  preflight.sh          26+ verificações do ambiente. Não escreve nada, não precisa de root.
  instalar.sh           Idempotente, para na primeira falha. --simular mostra sem executar.
  verificar.sh          Saúde · fluxo de ponta a ponta · isolamento de rede · gabarito.
  segredos.sh           Gera os segredos locais, modo 600. Nunca em variável de ambiente.
  backup.sh             Dump cifrado, e --verificar restaura para provar que presta.
  exportar_postgres.py  Converte o SQLite do protótipo na carga inicial do piloto.

docker-compose.yml      Núcleo, VLAN de Segurança. Rede interna sem gateway.
docker-compose.dmz.yml  Gateway de notificação, DMZ. A única peça com saída.
.env.exemplo            Variáveis. Senha não entra aqui.

sql/
  001_esquema.sql       Esquema de produção: partição por mês, trilha append-only,
                        política versionada, retenção declarada no próprio esquema.
  002_rbac.sql          Quatro papéis e Row Level Security por área.
  piloto/               Carga fictícia. Fora do que o compose monta como init, de propósito.

rede/
  regras-firewall.csv   18 regras, prontas para anexar ao chamado.
  nftables-exemplo.conf A mesma coisa em linguagem de firewall.
  allowlist-proxy.txt   Três domínios. Se crescer, alguém mudou o desenho.

coletores/              DLP, SWG, extensão por GPO e por MDM. Ordem de atrito crescente.
systemd/                A instalação sem contêiner, com endurecimento.
nginx/espia.conf     Publicação dos dois consoles, com CSP e sem cache.
certs/                  Vazio. Os certificados vêm da PKI interna.
```

## Verificação dos próprios artefatos

```bash
make lint
```

Roda sem ambiente nenhum: sintaxe de todos os scripts, YAML do compose, JSON da
política de GPO, contagem das regras de firewall e — o que mais importa — o SQL
contra o **parser real do PostgreSQL** (`pglast`). Esquema que não parseia é
instalação que falha às três da manhã.

## Três coisas que este pacote assume

1. **A VLAN de Segurança não sai para a internet.** `bin/verificar.sh
   --isolamento` testa isso de dentro de cada contêiner, e o teste passa quando
   a saída falha.
2. **A notificação não pode virar o vazamento.** A mensagem carrega ID,
   severidade e link interno. O que aconteceu está no console, atrás do SSO.
3. **O motor prova que acerta antes de o console abrir.** `make gabarito` é
   bloqueio: 15/15 casos oficiais na instalação real, ou não libera.
