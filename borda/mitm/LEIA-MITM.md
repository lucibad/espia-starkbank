# GerencIA · Cenário MITM (interceptação TLS) — captura de conteúdo em qualquer app

Este é o único jeito de ler o **conteúdo** (prompt e resposta) do tráfego de IA
**fora do navegador** (app de desktop, Cursor, scripts), porque o tráfego é TLS.
É a mesma técnica de um proxy/SWG/DLP corporativo: um proxy com uma **CA própria**
instalada nas máquinas descriptografa o tráfego, lê, e recriptografa.

> ⚠️ **Leia antes de ligar.** Isto intercepta **todo** o TLS da máquina — não só IA:
> e‑mail, banco, tudo passa em claro pelo proxy. É uma decisão de **Segurança/Compliance**,
> só em **máquinas corporativas gerenciadas** e com **ciência dos usuários** (aviso de
> monitoramento). Muitos serviços usam *certificate pinning* e vão **recusar** a conexão
> interceptada (o app quebra). Para o desafio, use no seu Windows de teste do Parallels.

## Peças

- `gerencia_mitm.py` — addon do mitmproxy: extrai prompt/resposta das IAs e envia
  ao coletor GerencIA (`fonte_captura=mitm`, aparece no painel como **Proxy**).

## Passo 1 — instalar e rodar o mitmproxy (no Mac servidor)

```bash
python3 -m pip install --user mitmproxy
cd ~/Downloads/espia
GERENCIA_COLETOR=http://127.0.0.1:8765 \
  mitmdump -s borda/mitm/gerencia_mitm.py --listen-host 0.0.0.0 --listen-port 8080
```

O proxy sobe na porta **8080**. Deixe rodando. Na primeira execução ele gera a CA em
`~/.mitmproxy/` — o arquivo que interessa é **`mitmproxy-ca-cert.cer`**.

## Passo 2 — instalar a CA do mitmproxy na estação Windows

Copie `~/.mitmproxy/mitmproxy-ca-cert.cer` para o Windows e, num **PowerShell como
administrador**, instale na raiz confiável da **máquina**:

```powershell
certutil -addstore -f Root C:\caminho\mitmproxy-ca-cert.cer
```

Em massa (GPO): *Computer Configuration ▸ Policies ▸ Windows Settings ▸ Security
Settings ▸ Public Key Policies ▸ Trusted Root Certification Authorities ▸ Import*.

> O Firefox usa o **próprio** repositório de CAs: importe em
> *Configurações ▸ Privacidade ▸ Certificados ▸ Ver certificados ▸ Autoridades ▸ Importar*.

## Passo 3 — apontar o tráfego da estação para o proxy

Windows (Configurações ▸ Rede ▸ Proxy ▸ Configuração manual): servidor
`10.211.55.2` (ou `macbook-pro.local`), porta `8080`. Ou por linha de comando:

```powershell
netsh winhttp set proxy proxy-server="10.211.55.2:8080"
# navegadores seguem o proxy do sistema; para reverter:  netsh winhttp reset proxy
```

## Passo 4 — testar

Com o mitmdump rodando e o proxy configurado, use o ChatGPT/Gemini na estação.
No terminal do mitmdump deve aparecer:

```
[GerencIA] ChatGPT (OpenAI): prompt 42c / resposta 380c -> coletor
```

No painel (`http://macbook-pro.local:8765/` ▸ **Captura**): a captura vem com
**Origem: Proxy** e o conteúdo no card **Conteúdo capturado**.

## Identidade (honestidade)

O proxy central conhece o **IP** da estação, não o usuário do SO — então a captura
vem identificada por **máquina/IP** (`identidade: proxy`). Para amarrar ao **usuário
logado** há duas opções:

1. Rodar o mitmproxy **em cada estação** (local) — aí o addon pode ler o usuário do SO.
2. **Correlacionar** o IP+horário do proxy com a sessão que o **agente** de estação
   reporta (o agente já sabe o usuário logado).

## Reverter tudo

```powershell
netsh winhttp reset proxy
certutil -delstore Root "mitmproxy"     # remove a CA
```
E encerre o `mitmdump` (Ctrl+C).

## Onde isso se encaixa

| Camada | Vê conteúdo | Cobre | Invasivo |
|---|---|---|---|
| Extensão | ✅ | só navegador | baixo |
| Agente de rede | ❌ (TLS) | qualquer app | baixo |
| **MITM (este)** | ✅ | qualquer app | **alto** |
