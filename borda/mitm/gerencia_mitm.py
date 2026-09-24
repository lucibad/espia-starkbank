"""
GerencIA · addon de MITM para captura de CONTEÚDO de IA.

Roda dentro do mitmproxy:  mitmdump -s gerencia_mitm.py
Intercepta o tráfego JÁ DESCRIPTOGRAFADO (a CA do mitmproxy precisa estar
instalada nas estações) e, para os domínios de IA, extrai o PROMPT e a RESPOSTA
e envia ao coletor GerencIA como captura de conteúdo (fonte_captura=mitm).

    GERENCIA_COLETOR   coletor (padrão http://127.0.0.1:8765)

AVISO honesto: isto é interceptação TLS, uma capacidade de proxy/DLP corporativo.
Use SÓ em máquinas corporativas gerenciadas, com aprovação de Segurança/Compliance
e ciência dos usuários. Lê o conteúdo em claro — é o objetivo e o risco. Serviços
com certificate pinning podem recusar a conexão interceptada.
"""
import json
import os
import urllib.request

from mitmproxy import http, ctx

COLETOR = os.environ.get("GERENCIA_COLETOR", "http://127.0.0.1:8765").rstrip("/")
LIMITE = 16000

# Sufixo de host → nome da ferramenta.
FERRAMENTAS = {
    "openai.com": "ChatGPT (OpenAI)", "chatgpt.com": "ChatGPT (OpenAI)",
    "anthropic.com": "Claude (Anthropic)", "claude.ai": "Claude (Anthropic)",
    "gemini.google.com": "Gemini (Google)",
    "generativelanguage.googleapis.com": "Gemini (Google)",
    "copilot.microsoft.com": "Copilot (Microsoft)",
    "deepseek.com": "DeepSeek", "perplexity.ai": "Perplexity", "poe.com": "Poe",
    "huggingface.co": "HuggingChat", "meta.ai": "Meta AI",
    "x.ai": "Grok (xAI)", "grok.com": "Grok (xAI)",
}
# Endpoints que carregam a conversa (evita estáticos/telemetria).
PISTAS_API = ("conversation", "chat", "completion", "generate", "messages",
              "backend-api", "stream", "ask", "prompt")


def _tool(host: str):
    host = (host or "").lower()
    for suf, nome in FERRAMENTAS.items():
        if host == suf or host.endswith("." + suf):
            return nome
    return None


def _textos(obj, saida):
    """Coleta recursivamente strings legíveis de um JSON aninhado."""
    if isinstance(obj, str):
        if len(obj) > 1:
            saida.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _textos(v, saida)
    elif isinstance(obj, list):
        for v in obj:
            _textos(v, saida)


def _de_json(txt: str) -> str:
    try:
        s = []
        _textos(json.loads(txt), s)
        return " ".join(s)
    except Exception:
        return txt


def _prompt(flow: http.HTTPFlow) -> str:
    ct = flow.request.headers.get("content-type", "")
    body = flow.request.get_text(strict=False) or ""
    return (_de_json(body) if "json" in ct else body)[:LIMITE].strip()


def _resposta(flow: http.HTTPFlow) -> str:
    ct = flow.response.headers.get("content-type", "")
    txt = flow.response.get_text(strict=False) or ""
    if "event-stream" in ct:                       # SSE (ChatGPT etc.): junta os deltas
        pedacos = []
        for ln in txt.splitlines():
            if ln.startswith("data:"):
                d = ln[5:].strip()
                if d and d != "[DONE]":
                    pedacos.append(_de_json(d))
        return " ".join(pedacos)[:LIMITE].strip()
    if "json" in ct:
        return _de_json(txt)[:LIMITE].strip()
    return txt[:LIMITE].strip()


def response(flow: http.HTTPFlow):
    nome = _tool(flow.request.pretty_host)
    if not nome or flow.request.method not in ("POST", "PUT"):
        return
    caminho = flow.request.path.lower()
    if not any(p in caminho for p in PISTAS_API):
        return
    prompt = _prompt(flow)
    resposta = _resposta(flow)
    if not prompt and not resposta:
        return
    ip = flow.client_conn.peername[0] if flow.client_conn.peername else ""
    evt = {
        "ferramenta": nome, "dominio": flow.request.pretty_host,
        "usuario": ip, "maquina": ip,
        "forma": "MITM (proxy)", "modo": "mitm",
        "fonte_captura": "mitm", "origem_mitm": True,
        "prompt": prompt, "resposta": resposta,
        "tipo": "Conteúdo capturado via proxy",
    }
    try:
        req = urllib.request.Request(
            COLETOR + "/api/ingest", data=json.dumps(evt).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        ctx.log.info(f"[GerencIA] {nome}: prompt {len(prompt)}c / resposta {len(resposta)}c -> coletor")
    except Exception as e:
        ctx.log.warn(f"[GerencIA] falha ao enviar ao coletor: {e}")
