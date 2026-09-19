# borda/ — o coletor de borda do GerencIA (`espia-borda`)

É o único componente que toca a estação do usuário. Dois pedaços:

| Pasta | O que é | Onde roda |
|---|---|---|
| `extensao/` | Extensão de navegador (Chrome, Edge, Firefox — Manifest V3). Observa o envio de prompts às IAs, roda os **detectores** (porte de `espia/detectores.py`, com validação de dígito e Luhn) e o **fingerprint** (porte de `espia/fingerprint.py`) **na máquina**, e reporta ao coletor só metadados, contagens e assinaturas. O texto não sai. | navegador da estação |
| `estacao/` | Agente de estação. Lê o usuário logado no SO (identidade confiável, sem host nativo), classifica localmente com as regras e **encaminha** cada evento ao coletor central. Instalador PowerShell cria autostart por usuário. | Windows da estação |

O coletor central é o do GerencIA: `ESPIA_BIND=0.0.0.0 python3 run.py coletor`. Ele grava as
capturas na mesma base da planilha e regenera o painel — vista **Captura**.

Passo a passo, topologia (Mac servidor + estações Windows), modos de identidade e limites
honestos: **[EXTENSAO.md](EXTENSAO.md)**. Instalação nas estações: `estacao/LEIA-PRIMEIRO.txt`.

Contrato de referência: `implantacao/coletores/extensao-gpo.json` (política de GPO do espia-borda).
