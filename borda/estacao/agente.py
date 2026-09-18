#!/usr/bin/env python3
"""Agente de estação do Rastro — núcleo local.

Roda o console na máquina do analista. O que este modo garante, e o artifact
publicado não consegue:

  * A identidade do analista é o USUÁRIO LOGADO NO SISTEMA OPERACIONAL,
    lida pelo servidor e carimbada em cada registro da trilha — o navegador
    não escolhe quem é.
  * A trilha de auditoria fica num SQLite local, sob controle da empresa.
  * As chamadas de IA saem deste processo para a API da Anthropic; a página
    nunca vê a chave.

Uso:
    python3 borda/estacao/agente.py            # http://127.0.0.1:8765
    RASTRO_PORTA=9000 python3 borda/estacao/agente.py

Variáveis:
    ANTHROPIC_API_KEY   chave da API. Sem ela, identidade e trilha funcionam
                        e as funções de IA aparecem desabilitadas na página.
    RASTRO_MODELO       modelo para todas as chamadas (padrão: claude-opus-5)
    RASTRO_PORTA        porta local (padrão: 8765)

Só escuta em 127.0.0.1. Não exponha em rede sem autenticação na frente.
"""
import getpass
import json
import os
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Módulo de DLP server-side (validação de CPF/CNPJ/Luhn). Ainda não ligado ao
# fluxo — hoje a extensão classifica no endpoint e o agente confia. Import
# guardado para não derrubar a estação se o arquivo não for empacotado junto.
try:
    import detectores  # noqa: F401
except ImportError:
    detectores = None

AQUI = Path(__file__).resolve().parent
PAGINA = AQUI / "prototipo.html"
DADOS = AQUI / "dados.js"
BANCO = AQUI / "auditoria.sqlite"
PORTA = int(os.environ.get("RASTRO_PORTA", "8765"))
# Endereço de escuta. 127.0.0.1 = só a própria máquina (modo local original).
# Para o Mac servir os navegadores do Windows no Parallels, use 0.0.0.0.
BIND = os.environ.get("RASTRO_BIND", "127.0.0.1")
MODELO = os.environ.get("RASTRO_MODELO", "claude-opus-5")

# Papel do agente:
#   sem RASTRO_COLETOR  → "central": serve o console e recebe eventos.
#   com RASTRO_COLETOR  → "estação": roda na máquina do usuário, classifica
#                          localmente e encaminha cada evento ao coletor central.
# Na estação, getpass.getuser() é o usuário do Windows logado — identidade
# local e confiável, sem precisar do host de mensagens nativas.
COLETOR = os.environ.get("RASTRO_COLETOR", "").strip().rstrip("/")
PAPEL = "estação" if COLETOR else "central"

# Domínios das ferramentas de IA → nome e status no inventário da empresa.
# A empresa define o que é aprovado; o que não estiver aqui é "Não aprovada".
INVENTARIO_DOMINIOS = {
    "chatgpt.com": ("ChatGPT (OpenAI)", "Não aprovada"),
    "chat.openai.com": ("ChatGPT (OpenAI)", "Não aprovada"),
    "claude.ai": ("Claude (Anthropic)", "Não aprovada"),
    "gemini.google.com": ("Gemini (Google)", "Não aprovada"),
    "copilot.microsoft.com": ("Copilot (Microsoft)", "Aprovada"),
    "m365.cloud.microsoft": ("Copilot (Microsoft)", "Aprovada"),
    "chat.deepseek.com": ("DeepSeek", "Não aprovada"),
    "perplexity.ai": ("Perplexity", "Não aprovada"),
    "poe.com": ("Poe", "Não aprovada"),
    "huggingface.co": ("HuggingChat", "Não aprovada"),
    "meta.ai": ("Meta AI", "Não aprovada"),
    "grok.com": ("Grok (xAI)", "Não aprovada"),
    "x.com": ("Grok (xAI)", "Não aprovada"),
}
LIMITE_TRILHA = 60
LIMITE_EVENTOS = 100
ESCALAR_AUTO = os.environ.get("RASTRO_ESCALAR_AUTO", "1") == "1"

# ── conhecimento da base: tipos, política, ferramentas ──────────────────
try:
    _BASE = json.loads((AQUI.parent / "dados" / "dados.json").read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    _BASE = {"tipos": {}, "classif": [], "fer_meta": {}}
TIPOS = _BASE.get("tipos", {})          # tipo → {"padrao": sensibilidade}
CLASSIF = _BASE.get("classif", [])      # política de classificação (4 níveis)

try:
    INVENTARIO = json.loads((AQUI / "inventario.json").read_text(encoding="utf-8")).get("dominios", {})
except (OSError, json.JSONDecodeError):
    INVENTARIO = {}

# ── identidade: o usuário logado na máquina ─────────────────────────────
# Em domínio corporativo (AD / Entra ID) este é o login de rede — a fonte
# SRC-04 da própria base. É lido aqui, no servidor, e nunca do navegador.
ANALISTA = getpass.getuser()

# ── IA: só se a chave e o SDK existirem ─────────────────────────────────
cliente = None
try:
    import anthropic  # noqa: E402
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        cliente = anthropic.Anthropic()
except ImportError:
    anthropic = None


# ── trilha em SQLite ────────────────────────────────────────────────────
def abrir_banco():
    con = sqlite3.connect(BANCO)
    con.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,   -- ISO 8601 UTC
            data      TEXT NOT NULL,   -- DD/MM/AAAA local
            hora      TEXT NOT NULL,   -- HH:MM:SS local
            analista  TEXT NOT NULL,   -- usuário do SO, carimbado pelo servidor
            tipo      TEXT NOT NULL,   -- rastreio | classificação
            pergunta  TEXT NOT NULL,
            ia        TEXT NOT NULL,   -- modelo consultado
            resultado TEXT NOT NULL
        )""")
    # Base aprendida: o que o LLM resolveu volta para a IA clássica.
    # Chave = assinatura do caso; a próxima ocorrência é resolvida aqui,
    # sem chamar o modelo. Ver docs/ARQUITETURA.md → "Cascata".
    con.execute("""
        CREATE TABLE IF NOT EXISTS aprendizado (
            assinatura    TEXT PRIMARY KEY,
            nivel         TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            sinais        TEXT NOT NULL,   -- JSON
            ia            TEXT NOT NULL,   -- modelo que ensinou
            analista      TEXT NOT NULL,   -- quem estava operando quando aprendeu
            ts            TEXT NOT NULL,
            contagem      INTEGER NOT NULL DEFAULT 1
        )""")
    # Eventos capturados pela extensão neste navegador/máquina.
    # `trecho` é MASCARADO (CPF, cartão, chave substituídos) e limitado a 120
    # caracteres. O prompt completo não é gravado. Ver extensao/README.md.
    con.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            data       TEXT NOT NULL,
            hora       TEXT NOT NULL,
            usuario    TEXT NOT NULL,   -- usuário do SO
            dominio    TEXT NOT NULL,
            ferramenta TEXT NOT NULL,
            status_fer TEXT NOT NULL,
            forma      TEXT NOT NULL,   -- Prompt | Trecho de documento | Arquivo
            qtd        INTEGER NOT NULL,
            tipo       TEXT NOT NULL,   -- inferido pelos detectores
            sens       TEXT NOT NULL,
            nivel      TEXT NOT NULL,
            regra      TEXT NOT NULL,
            origem     TEXT NOT NULL,   -- regra | aprendido | llm | provisório
            detectores TEXT NOT NULL,   -- JSON {nome: contagem}
            trecho     TEXT NOT NULL,
            titulo     TEXT NOT NULL
        )""")
    # Migração: assinatura de fingerprint (contrato espia-borda). Bancos
    # criados antes desta coluna ganham-na aqui, sem perder dados.
    cols = {r[1] for r in con.execute("PRAGMA table_info(eventos)")}
    if "fingerprint" not in cols:
        con.execute("ALTER TABLE eventos ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
    if "deteccoes" not in cols:
        con.execute("ALTER TABLE eventos ADD COLUMN deteccoes TEXT NOT NULL DEFAULT '[]'")
    # De onde veio a identidade: so-local | agente-local | nativo (verificadas)
    # vs declarado | ausente (não verificadas). Auditoria precisa distinguir.
    if "fonte" not in cols:
        con.execute("ALTER TABLE eventos ADD COLUMN fonte TEXT NOT NULL DEFAULT ''")
    con.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )""")
    con.commit()
    return con


# ── inventário administrável: o admin edita no console, o agente persiste ──
def inventario():
    con = abrir_banco()
    row = con.execute("SELECT valor FROM config WHERE chave='inventario'").fetchone()
    con.close()
    if row:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            pass
    # semente: o mapa padrão vira dict {dominio: {ferramenta, status}}
    return {d: {"ferramenta": f, "status": s} for d, (f, s) in INVENTARIO_DOMINIOS.items()}


def gravar_inventario(inv):
    if not isinstance(inv, dict):
        return False
    limpo = {}
    validos = ("Aprovada", "Aprovada condicional",
               "Aprovada apenas para conteúdo público", "Não aprovada")
    for dom, meta in inv.items():
        if not isinstance(meta, dict):
            continue
        status = meta.get("status")
        limpo[str(dom)[:120]] = {
            "ferramenta": str(meta.get("ferramenta", dom))[:80],
            "status": status if status in validos else "Não aprovada",
        }
    con = abrir_banco()
    with con:
        con.execute("INSERT INTO config (chave,valor) VALUES ('inventario',?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (json.dumps(limpo, ensure_ascii=False),))
    con.close()
    return True


# ── camada 1 no agente: o mesmo motor do console, em Python ─────────────
ANON = ("dados agregados anonimizados", "ticket de atendimento anonimizado")


def camada1(tipo, sens, status_fer, qtd):
    """Devolve (nível, regra, confiança). Idêntico a recl() do console."""
    t = tipo.lower()
    nao_ap = "Não aprovada" in status_fer
    if "secret" in t or "chave" in t:
        return "Crítico", "R03", "alta"
    if nao_ap and sens in ("Confidencial", "Crítica"):
        return "Crítico", "R01/R02", "alta"
    if sens == "Crítica":
        return "Crítico", "R04/R05", "alta"
    if sens == "Confidencial":
        if nao_ap:
            return "Alto", "R01", "alta"
        return ("Alto", "R11", "alta") if qtd >= 10 else ("Médio", "R07", "baixa")
    if sens == "Interna":
        if any(a in t for a in ANON):
            return "Baixo", "R09", "alta"
        return "Médio", "R13", "baixa"
    return "Baixo", "R08", "alta"


def assinatura(tipo, status_fer, sens, finalidade):
    return " | ".join([tipo, status_fer, sens, finalidade])


def buscar_aprendido(assin):
    con = abrir_banco()
    row = con.execute("SELECT nivel, contagem FROM aprendizado WHERE assinatura=?", (assin,)).fetchone()
    if row:
        con.execute("UPDATE aprendizado SET contagem=contagem+1 WHERE assinatura=?", (assin,))
        con.commit()
    con.close()
    return row


POLITICA = (
    "- Pública: informação já divulgada → uso livre.\n"
    "- Interna: operacional não pública → preferir ferramentas corporativas.\n"
    "- Confidencial: negócio, cliente, jurídico → só ferramenta corporativa.\n"
    "- Crítica: segredo, credencial, dado pessoal sensível → nunca em IA pública."
)


def prompt_evento(ev):
    """Monta o prompt de classificação de um evento capturado. Usado quando a
    camada 1 não resolve e não há caso aprendido (escalada ao LLM)."""
    return (
        "Você é um analista de segurança da informação classificando o risco de um "
        "uso de IA corporativa. Responda SOMENTE com JSON, sem comentário.\n\n"
        "POLÍTICA DE CLASSIFICAÇÃO:\n" + POLITICA + "\n\n"
        "NÍVEIS POSSÍVEIS: Baixo | Médio | Alto | Crítico\n\n"
        "EVENTO:\n"
        f"- Tipo de informação inferido: {ev.get('tipo', '')}\n"
        f"- Sensibilidade inferida: {ev.get('sens', '')}\n"
        f"- Ferramenta: {ev.get('ferramenta', '')} ({ev.get('status_fer', '')})\n"
        f"- Forma de uso: {ev.get('forma', '')}\n"
        f"- Volume: {ev.get('qtd', 1)} item(ns)\n"
        f"- Detectores acionados no endpoint: {ev.get('detectores', '{}')}\n"
        f"- Título da aba: {ev.get('titulo', '')}\n\n"
        "Avalie conteúdo e contexto, não só metadados.\n"
        'SCHEMA: {"nivel":"Baixo|Médio|Alto|Crítico","justificativa":"uma frase",'
        '"sinais":["até 3 fatores"]}'
    )


NIVEIS = ("Baixo", "Médio", "Alto", "Crítico")


def aprender(reg):
    nivel = str(reg.get("nivel", ""))
    if nivel not in NIVEIS:
        return False
    assinatura = str(reg.get("assinatura", ""))[:400]
    if not assinatura:
        return False
    sinais = reg.get("sinais", [])
    if not isinstance(sinais, list):
        sinais = []
    con = abrir_banco()
    with con:
        con.execute("""
            INSERT INTO aprendizado (assinatura,nivel,justificativa,sinais,ia,analista,ts,contagem)
            VALUES (?,?,?,?,?,?,?,1)
            ON CONFLICT(assinatura) DO UPDATE SET
                nivel=excluded.nivel, justificativa=excluded.justificativa,
                sinais=excluded.sinais, ia=excluded.ia, ts=excluded.ts,
                contagem=aprendizado.contagem+1
        """, (assinatura, nivel, str(reg.get("justificativa", ""))[:600],
              json.dumps([str(s)[:120] for s in sinais[:3]], ensure_ascii=False),
              str(reg.get("ia", ""))[:80], ANALISTA,
              datetime.now(timezone.utc).isoformat()))
    con.close()
    return True


def ler_aprendizado():
    con = abrir_banco()
    cur = con.execute("SELECT assinatura,nivel,justificativa,sinais,ia,analista,ts,contagem FROM aprendizado")
    itens = []
    for a, n, j, s, ia, an, ts, c in cur.fetchall():
        try:
            sin = json.loads(s)
        except json.JSONDecodeError:
            sin = []
        itens.append({"assinatura": a, "nivel": n, "justificativa": j, "sinais": sin,
                      "ia": ia, "analista": an, "ts": ts, "contagem": c})
    con.close()
    return itens


def gravar(reg):
    agora_local = datetime.now()
    linha = (
        datetime.now(timezone.utc).isoformat(),
        agora_local.strftime("%d/%m/%Y"),
        agora_local.strftime("%H:%M:%S"),
        ANALISTA,                              # ignora o que o cliente mandou
        str(reg.get("tipo", ""))[:40],
        str(reg.get("pergunta", ""))[:500],
        str(reg.get("ia", ""))[:80],
        str(reg.get("resultado", ""))[:200],
    )
    con = abrir_banco()
    with con:
        con.execute("INSERT INTO auditoria (ts,data,hora,analista,tipo,pergunta,ia,resultado) "
                    "VALUES (?,?,?,?,?,?,?,?)", linha)
    con.close()


def ler_trilha():
    con = abrir_banco()
    cur = con.execute("SELECT ts,data,hora,analista,tipo,pergunta,ia,resultado "
                      "FROM auditoria ORDER BY id DESC LIMIT ?", (LIMITE_TRILHA,))
    cols = ["ts", "data", "hora", "analista", "tipo", "pergunta", "ia", "resultado"]
    linhas = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return linhas


# ── ingestão: eventos capturados pela extensão de navegador ─────────────
def identidade_endpoint(corpo, remoto):
    """Quem gerou o evento.

    Quando o agente serve LOCALMENTE (o usuário está na mesma máquina), a
    identidade é o usuário do SO desta máquina — não falsificável pela página.

    Quando o agente serve REMOTAMENTE (o caso do Mac servindo o Windows do
    Parallels), o usuário está noutra máquina e o agente NÃO consegue lê-lo.
    A identidade vem então do endpoint: o host de mensagens nativas do
    Windows informa %USERNAME% (fonte 'nativo', não editável pela página);
    sem ele, a extensão manda um nome declarado (fonte 'declarado',
    falsificável — só para teste). Ver borda/EXTENSAO.md.
    """
    if not remoto:
        return ANALISTA, "so-local"
    u = str(corpo.get("usuario", "")).strip()[:64]
    fonte = corpo.get("usuario_fonte")
    # 'nativo'  = host de mensagens nativas leu %USERNAME% no endpoint.
    # 'agente-local' = um agente de estação, rodando como o usuário, leu o SO.
    # Ambos são confiáveis: a página não os falsifica.
    if u and fonte in ("nativo", "agente-local"):
        return u, fonte
    if u:
        return u, "declarado"
    return "não identificado", "ausente"


def gravar_evento(corpo, usuario, fonte):
    """Classifica um evento capturado pela cascata (regra → aprendido) e grava."""
    dominio = str(corpo.get("dominio", ""))[:120]
    inv = inventario().get(dominio)
    if inv:
        ferramenta, status_fer = inv["ferramenta"], inv["status"]
    else:
        ferramenta, status_fer = (dominio or "Desconhecida"), "Não aprovada"
    tipo = str(corpo.get("tipo", "Conteúdo não classificado"))[:80]
    sens = corpo.get("sens") if corpo.get("sens") in ("Pública", "Interna", "Confidencial", "Crítica") else "Interna"
    forma = str(corpo.get("forma", "Prompt"))[:40]
    try:
        qtd = max(1, int(corpo.get("qtd", 1)))
    except (TypeError, ValueError):
        qtd = 1
    finalidade = str(corpo.get("finalidade", "Uso não declarado"))[:80]

    nivel, regra, conf = camada1(tipo, sens, status_fer, qtd)
    origem = "regra"
    if conf == "baixa":
        aprendido = buscar_aprendido(assinatura(tipo, status_fer, sens, finalidade))
        if aprendido:
            nivel, origem = aprendido[0], "aprendido"
        else:
            origem = "provisório"   # aguarda escalada ao LLM no console

    agora_local = datetime.now()
    # Contrato espia-borda: `deteccoes` é [{tipo, contagem, validado}]; o
    # legado mandava `detectores` como {tipo: contagem}. Aceita os dois.
    deteccoes = corpo.get("deteccoes")
    if isinstance(deteccoes, list):
        detectores = {str(d.get("tipo")): int(d.get("contagem", 1))
                      for d in deteccoes if isinstance(d, dict) and d.get("tipo")}
    else:
        deteccoes = []
        detectores = corpo.get("detectores", {}) if isinstance(corpo.get("detectores"), dict) else {}
    fingerprint = corpo.get("fingerprint") if isinstance(corpo.get("fingerprint"), dict) else {}
    linha = (
        datetime.now(timezone.utc).isoformat(),
        agora_local.strftime("%d/%m/%Y"), agora_local.strftime("%H:%M:%S"),
        usuario, dominio, ferramenta, status_fer, forma, qtd, tipo, sens,
        nivel, regra, origem,
        json.dumps(detectores, ensure_ascii=False)[:400],
        str(corpo.get("previa", corpo.get("trecho", "")))[:200],   # prévia MASCARADA; nunca o conteúdo
        str(corpo.get("titulo", ""))[:200],
        json.dumps(fingerprint, ensure_ascii=False)[:4000],
        json.dumps(deteccoes, ensure_ascii=False)[:1200],
        fonte,
    )
    con = abrir_banco()
    with con:
        con.execute("""INSERT INTO eventos
            (ts,data,hora,usuario,dominio,ferramenta,status_fer,forma,qtd,tipo,sens,
             nivel,regra,origem,detectores,trecho,titulo,fingerprint,deteccoes,fonte)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", linha)
    con.close()
    return {"nivel": nivel, "regra": regra, "origem": origem,
            "ferramenta": ferramenta, "status_fer": status_fer,
            "usuario": usuario, "fonte": fonte}


def ler_eventos(limite=200):
    con = abrir_banco()
    cur = con.execute("""SELECT ts,data,hora,usuario,dominio,ferramenta,status_fer,
        forma,qtd,tipo,sens,nivel,regra,origem,detectores,trecho,titulo,
        fingerprint,deteccoes,fonte
        FROM eventos ORDER BY id DESC LIMIT ?""", (limite,))
    cols = ["ts", "data", "hora", "usuario", "dominio", "ferramenta", "status_fer",
            "forma", "qtd", "tipo", "sens", "nivel", "regra", "origem",
            "detectores", "trecho", "titulo", "fingerprint", "deteccoes", "fonte"]
    linhas = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    return linhas


# ── estação → coletor central ───────────────────────────────────────────
def encaminhar(corpo, usuario):
    """Envia o evento ao coletor central, em segundo plano. Best-effort: se o
    Mac estiver fora, o evento já está gravado localmente na estação."""
    import threading
    import urllib.request

    payload = dict(corpo)
    payload["usuario"] = usuario
    payload["usuario_fonte"] = "agente-local"   # o coletor confia nesta fonte
    payload["maquina"] = socket.gethostname()

    def _post():
        try:
            req = urllib.request.Request(
                COLETOR + "/api/ingest",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=4).read()
        except Exception:
            pass   # coletor indisponível; a cópia local permanece

    threading.Thread(target=_post, daemon=True).start()


# ── chamada de IA ───────────────────────────────────────────────────────
def extrair_json(texto):
    """A instrução pede JSON puro; tolera cercas de código por segurança."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return json.loads(t.strip())


def perguntar(prompt):
    """Retorna (payload, erro). Erros seguem os códigos que a página já trata."""
    if cliente is None:
        return None, {"code": "not_granted",
                      "message": "IA indisponível: defina ANTHROPIC_API_KEY e reinicie o servidor."}
    try:
        resp = cliente.messages.create(
            model=MODELO,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        return None, {"code": "rate_limited", "message": "Limite de requisições atingido."}
    except anthropic.AuthenticationError:
        return None, {"code": "not_granted", "message": "Chave da API inválida."}
    except anthropic.APIStatusError as e:
        return None, {"code": "api_error", "message": f"Erro da API ({e.status_code})."}
    except anthropic.APIConnectionError:
        return None, {"code": "api_error", "message": "Sem conexão com a API."}

    if resp.stop_reason == "refusal":
        return None, {"code": "refused", "message": "O modelo recusou a solicitação."}

    texto = "".join(b.text for b in resp.content if b.type == "text")
    try:
        return extrair_json(texto), None
    except (json.JSONDecodeError, ValueError):
        return None, {"code": "invalid_json", "message": "Resposta não estruturada.", "text": texto}


# ── HTTP ────────────────────────────────────────────────────────────────
class Rastro(BaseHTTPRequestHandler):
    def _cors(self):
        # A extensão reporta a partir dos domínios das ferramentas de IA.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, corpo, status=200):
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _arquivo(self, caminho, tipo):
        if not caminho.exists():
            return self._json({"code": "not_found"}, 404)
        dados = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 200_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota in ("/", "/index.html", "/prototipo.html"):
            if not PAGINA.exists():   # estação sem os arquivos do console
                return self._json({"papel": PAPEL, "console": False,
                                   "message": "agente de estação — sem console"}, 200)
            return self._arquivo(PAGINA, "text/html; charset=utf-8")
        if rota == "/dados.js":
            return self._arquivo(DADOS, "application/javascript; charset=utf-8")
        if rota == "/config.js":
            cfg = {"analista": ANALISTA, "ia": cliente is not None, "modelo": MODELO}
            js = "window.RASTRO_LOCAL=" + json.dumps(cfg, ensure_ascii=False) + ";\n"
            dados = js.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(dados)
        if rota == "/api/auditoria":
            return self._json({"itens": ler_trilha()})
        if rota == "/api/aprendizado":
            return self._json({"itens": ler_aprendizado()})
        if rota == "/api/eventos":
            return self._json({"itens": ler_eventos()})
        if rota == "/api/saude":
            return self._json({"ok": True, "ia": cliente is not None,
                               "modelo": MODELO, "analista_local": ANALISTA})
        if rota == "/api/config":
            return self._json({"inventario": inventario(), "modelo": MODELO,
                               "ia": cliente is not None, "analista_local": ANALISTA})
        return self._json({"code": "not_found"}, 404)

    def _remoto(self):
        ip = self.client_address[0]
        return ip not in ("127.0.0.1", "::1", "localhost")

    def do_POST(self):
        rota = self.path.split("?")[0]
        corpo = self._corpo()
        # /eventos é o contrato do espia-borda; /api/ingest é o alias legado.
        if rota in ("/eventos", "/api/ingest"):
            usuario, fonte = identidade_endpoint(corpo, self._remoto())
            try:
                r = gravar_evento(corpo, usuario, fonte)
            except Exception as e:  # nunca derruba o agente por um evento malformado
                return self._json({"code": "erro_ingest", "message": str(e)[:120]}, 400)
            # Estação: encaminha ao coletor central o mesmo evento, já com a
            # identidade local resolvida (só eventos da própria extensão local).
            if COLETOR and not self._remoto():
                encaminhar(corpo, usuario)
            return self._json({"ok": True, "papel": PAPEL, **r})
        if rota == "/api/config":
            # Só o admin, na própria máquina do agente, edita o inventário.
            if self._remoto():
                return self._json({"code": "somente_local",
                                   "message": "config só é editável na máquina do agente"}, 403)
            ok = gravar_inventario(corpo.get("inventario", {}))
            return self._json({"ok": ok, "inventario": inventario()}, 200 if ok else 400)
        if rota == "/api/aprendizado":
            ok = aprender(corpo)
            return self._json({"ok": ok}, 200 if ok else 400)
        if rota == "/api/ia":
            prompt = str(corpo.get("prompt", ""))[:20_000]
            if not prompt:
                return self._json({"code": "invalid_request", "message": "prompt vazio"}, 400)
            payload, erro = perguntar(prompt)
            if erro:
                status = 403 if erro["code"] == "not_granted" else 502
                return self._json(erro, status)
            return self._json({"json": payload, "modelo": MODELO})
        if rota == "/api/auditoria":
            gravar(corpo)
            return self._json({"ok": True, "analista": ANALISTA})
        return self._json({"code": "not_found"}, 404)

    def log_message(self, fmt, *args):
        # silencia o log padrão; a trilha de auditoria é o registro que importa
        pass


def enderecos_para_convidados():
    """IPs deste Mac que uma VM consegue alcançar, do mais provável ao menos.

    Parallels cria interfaces próprias: a rede Compartilhada põe o host em
    10.211.55.x e a Host-Only em 10.37.129.x. Esses vêm primeiro — é o que o
    Windows convidado alcança com certeza. O IP de saída (Wi-Fi/LAN) vem por
    último: só serve se a VM estiver em modo Bridge. gethostbyname não entra
    aqui porque costuma devolver 127.0.0.1.
    """
    achados = []
    try:
        import subprocess
        saida = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
        import re
        for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", saida):
            if ip.startswith("10.211.55."):
                achados.append((ip, "Parallels · rede Compartilhada"))
            elif ip.startswith("10.37.129."):
                achados.append((ip, "Parallels · Host-Only"))
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and all(ip != a for a, _ in achados):
            achados.append((ip, "LAN/Wi-Fi · só se a VM estiver em Bridge"))
    except OSError:
        pass
    return achados or [("10.211.55.2", "padrão do Parallels · confirme com ifconfig")]


def main():
    if PAPEL == "central" and (not PAGINA.exists() or not DADOS.exists()):
        sys.exit("ERRO: modo central precisa do console; rode a partir da raiz e gere os dados com dados/extrair.py")
    abrir_banco().close()
    srv = ThreadingHTTPServer((BIND, PORTA), Rastro)
    print(f"Rastro · agente {PAPEL.upper()} ouvindo em {BIND}:{PORTA}")
    if PAPEL == "estação":
        print(f"  usuário desta estação (Windows logado): {ANALISTA}")
        print(f"  encaminhando eventos ao coletor central: {COLETOR}")
        print(f"  aponte a extensão deste PC para: http://127.0.0.1:{PORTA}")
    print(f"  console local: http://127.0.0.1:{PORTA}" if PAGINA.exists() else "  (sem console neste agente)")
    if BIND == "0.0.0.0":
        for ip, rotulo in enderecos_para_convidados():
            print(f"  do Windows (Parallels), aponte para este Mac em: http://{ip}:{PORTA}  [{rotulo}]")
    else:
        print("  (só 127.0.0.1 — para servir o Windows do Parallels, rode com RASTRO_BIND=0.0.0.0)")
    print(f"  analista local (usuário do SO deste Mac): {ANALISTA}")
    print(f"  trilha e base aprendida: {BANCO}")
    print(f"  IA: {'ligada · ' + MODELO if cliente else 'DESLIGADA (defina ANTHROPIC_API_KEY)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
