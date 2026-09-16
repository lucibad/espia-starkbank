# Certificados

Três arquivos, emitidos pela **PKI interna do banco**. Autoassinado serve para
o laboratório e para mais nada: o mTLS dos coletores é o que impede qualquer
host da rede de injetar evento falso no sistema, e um certificado que não
encadeia na CA do banco não prova nada.

| Arquivo | O que é | Quem emite |
|---|---|---|
| `ca-interna.crt` | CA que assina tudo | PKI corporativa |
| `espia.crt` / `.key` | servidor (ingestão e consoles) | PKI, SAN com os dois nomes |
| `coletor-*.crt` / `.key` | um par por coletor | PKI, um por host de coletor |

**Um par por coletor, não um par para todos.** Assim, revogar o certificado de
um servidor de DLP comprometido não derruba a coleta inteira — e a trilha
mostra qual coletor enviou cada evento.

A chave privada é modo `600`. O `preflight.sh` verifica, e trata permissão
frouxa como bloqueio, não como aviso.

Renovação: 90 dias antes do vencimento, por chamado. O `preflight.sh` recusa a
instalação com certificado a menos de 30 dias do fim, porque um certificado que
expira num domingo derruba a coleta sem ninguém perceber até segunda.
