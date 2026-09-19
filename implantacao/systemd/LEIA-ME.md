# Instalação sem contêiner

Alguns bancos não permitem contêiner em determinadas camadas, ou a área de
infraestrutura padroniza pacote e systemd. O GerencIA roda dos dois jeitos: o
núcleo é Python puro e não depende de nada que o contêiner forneça.

A diferença prática é só onde ficam as dependências:

| | Contêiner | systemd |
|---|---|---|
| Dependências | na imagem | num virtualenv em `/opt/espia/venv` |
| Configuração | `.env` + compose | `/etc/espia/espia.env` |
| Segredos | `/run/secrets` | `/etc/espia/segredos/`, modo 600, dono `espia` |
| Atualização | troca de tag e `up -d` | RPM/DEB e `systemctl restart espia.target` |
| PostgreSQL | contêiner | instância do banco, que a DBA já sabe operar |

**Quando escolher systemd:** quando a DBA já opera PostgreSQL corporativo. Não
faz sentido subir um Postgres em contêiner ao lado de um time que já tem
padrão de backup, réplica e tuning. Aponte o `PGHOST` para a instância deles e
instale só os serviços de aplicação.

## Sequência

```bash
useradd -r -s /sbin/nologin espia
install -d -o espia -g espia -m 750 /opt/espia /etc/espia /var/lib/espia
install -d -o espia -g espia -m 700 /etc/espia/segredos

python3 -m venv /opt/espia/venv
/opt/espia/venv/bin/pip install --no-index --find-links /mnt/pacotes espia-*.whl
# --no-index: os pacotes vêm do espelho interno. A VLAN não alcança o PyPI.

cp espia.env.exemplo /etc/espia/espia.env && chmod 640 /etc/espia/espia.env
cp *.service *.target /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now espia.target
```

O `preflight.sh` e o `verificar.sh` funcionam igual nos dois modos.
