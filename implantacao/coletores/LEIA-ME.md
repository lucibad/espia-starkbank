# Coletores — o que instalar em cada ponto, e nessa ordem

A ordem importa. Os dois primeiros coletores **não exigem nada nas estações**,
e é por isso que eles vêm primeiro: entregam visibilidade em dias, sem depender
da janela de mudança do time de endpoint, que costuma ser o caminho crítico.

| Ordem | Coletor | Onde | Exige mudança na estação | Onda |
|---|---|---|---|---|
| 1 | Conector DLP | Servidor de DLP | não | 0 |
| 2 | Coletor de SWG/proxy | Servidor de proxy | não | 0 |
| 3 | Gateway de IA | Gateway aprovado | não | 2 |
| 4 | Extensão de navegador | Estações, por GPO/MDM | **sim** | 2 |
| 5 | SDK em aplicação interna | Repositórios internos | não | 3 |

**O que todo coletor envia, e o que nenhum envia.** Envia: identificador do
evento, usuário, ferramenta, tipo de informação, contagens, assinatura
MinHash/SimHash, horário. Não envia: o texto. Em nenhum coletor, em nenhuma
onda, em nenhuma circunstância. A classificação acontece na borda; o que
atravessa a rede é o resultado dela.

---

## 1. Conector DLP

O DLP já classifica. O conector traduz o evento dele para o contrato do
EspIA e entrega por mTLS. Arquivo: `dlp-conector.yaml`.

Ponto de atenção: o DLP classifica **arquivo**; o EspIA raciocina sobre
**informação**. O mapeamento entre o rótulo do DLP e os 20 tipos da planilha é
a única parte que exige decisão humana, e está no bloco `mapeamento:`. Faça-o
com Compliance, não com a infraestrutura.

## 2. Coletor de SWG / proxy

Lê o log do proxy e gera evento para cada acesso a domínio de ferramenta de IA
conhecida — e, mais importante, **desconhecida**: é assim que se descobre shadow
AI. Arquivo: `swg-syslog.conf`.

Este coletor vê o acesso, não o conteúdo. Ele responde "quem usou o quê",
nunca "o que foi colado". Diga isso na apresentação antes que perguntem.

## 3. Extensão de navegador

É o único componente que toca a estação, e por isso é o que exige mais cuidado
político. Instale por GPO (Edge/Chrome no Windows) ou MDM (macOS), em modo
**somente observação** por 15 dias, antes de qualquer oferta de mascaramento.

Arquivos: `extensao-gpo.json` (Windows/AD) e `extensao-mdm.mobileconfig` (macOS).

A extensão calcula fingerprint e roda os detectores **localmente**. O que sai da
estação é a assinatura e as contagens. Vale escrever isso na comunicação interna
que anuncia a instalação, porque a primeira pergunta de todo funcionário é "então
vocês leem o que eu digito?", e a resposta honesta é não.

## 4. SDK em aplicação interna

Uma chamada, nas aplicações que usam IA por API. Registra o mesmo contrato de
evento. Serve para o que nenhum coletor de borda enxerga: a aplicação que chama
a API do modelo direto do servidor.
