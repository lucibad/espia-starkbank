"""
GerencIA — Captura ao vivo (espia-borda) unificada com a base legada.

O Excel da Starkbank é a CARGA LEGADA: o que a empresa já tinha registrado.
As capturas do espia-borda são o PRESENTE: o que acontece agora, nas estações.
Os dois vivem na mesma tabela `eventos`, avaliados pelo mesmo motor de regras,
e aparecem no mesmo painel — distinguidos pela coluna `origem`.

Este módulo é a ponte entre os dois mundos:

  ingerir()          grava uma captura crua (contrato do espia-borda) em `capturas`,
                     tabela que SOBREVIVE ao `gerar` (não está no DROP do esquema).
  anexar_a_base()    lê as capturas e as anexa à Base como `Evento` do GerencIA,
                     enriquecendo o inventário com o que a borda encontrou e a
                     planilha não conhecia (ferramentas reais, tipos detectados,
                     usuários do Windows). O motor avalia tudo com a mesma régua.

Nada aqui altera a base legada. É só acréscimo.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3

from . import base_oficial as bo

ORIGEM_CAPTURA = "Captura ao vivo (espia-borda)"
SENSIBILIDADES = ("Pública", "Interna", "Confidencial", "Crítica")
FONTES_VERIFICADAS = ("so-local", "agente-local", "nativo")

ESQUEMA_CAPTURAS = """
CREATE TABLE IF NOT EXISTS capturas (
  seq              INTEGER PRIMARY KEY AUTOINCREMENT,
  cap_id           TEXT UNIQUE,
  ts               TEXT NOT NULL,   -- ISO 8601, quando o usuário usou a IA
  recebido_em      TEXT NOT NULL,   -- ISO 8601, quando o coletor recebeu
  usuario          TEXT NOT NULL,   -- como veio da estação (nome do Windows)
  identidade_fonte TEXT NOT NULL,   -- so-local | agente-local | nativo | declarado | ausente
  maquina          TEXT NOT NULL,
  dominio          TEXT NOT NULL,
  ferramenta       TEXT NOT NULL,
  status_fer       TEXT NOT NULL,   -- se a estação informou; senão vazio
  forma            TEXT NOT NULL,
  qtd              INTEGER NOT NULL,
  tipo             TEXT NOT NULL,   -- inferido pelos detectores na borda
  sens             TEXT NOT NULL,
  finalidade       TEXT NOT NULL,
  deteccoes        TEXT NOT NULL,   -- JSON [{tipo, contagem, validado}]
  fingerprint      TEXT NOT NULL,   -- JSON {minhash, simhash, n_shingles, hash}
  previa           TEXT NOT NULL,   -- trecho MASCARADO; nunca o conteúdo
  titulo           TEXT NOT NULL,
  modo             TEXT NOT NULL,   -- observacao | mascaramento | bloqueio
  par_id           TEXT,            -- liga o prompt e a resposta do mesmo turno
  papel            TEXT,            -- prompt | resposta
  prompt           TEXT,            -- CONTEUDO da pesquisa (guarda de conteúdo)
  resposta         TEXT,            -- CONTEUDO do retorno da IA
  fonte_captura    TEXT,            -- extensao | agente | mitm (quem capturou)
  classificado_por TEXT             -- borda | llm-local | llm-local-baixa-confianca
);
-- Inventário das IAs externas monitoradas: o admin cadastra e decide o status.
-- É a autoridade sobre nome e aprovação das ferramentas que a planilha não
-- lista (o `dominios_monitorados_url` da política de GPO do espia-borda).
CREATE TABLE IF NOT EXISTS inventario_dominios (
  dominio TEXT PRIMARY KEY,
  nome    TEXT NOT NULL,
  status  TEXT NOT NULL
);
-- Cadastros centrais feitos na tela de Governança do painel 2.0 (status,
-- finalidade, controles, identificador das ferramentas, etc.). Guardamos o
-- bloco inteiro de CAD como um JSON só — a autoridade passa a ser o servidor,
-- não o localStorage de cada navegador.
CREATE TABLE IF NOT EXISTS cadastros (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);
-- Estações conectadas: cada sensor (agente) e cada extensão mandam um "estou
-- vivo" (heartbeat) periódico. Uma linha por (maquina, fonte) com o último
-- contato — é o que alimenta o farol da aba Estações.
CREATE TABLE IF NOT EXISTS estacoes (
  maquina   TEXT NOT NULL,
  fonte     TEXT NOT NULL,          -- agente | extensao
  usuario   TEXT,
  versao    TEXT,
  ultimo_hb TEXT NOT NULL,          -- ISO local do último heartbeat
  PRIMARY KEY (maquina, fonte)
);
"""

CADASTROS_CHAVE = "gerencia-cadastros-v1"
CADASTROS_SECOES = ("classificacoes", "ferramentas", "usuarios", "tipos", "regras", "fontes")

STATUS_VALIDOS = ("Aprovada", "Aprovada condicional",
                  "Aprovada apenas para conteúdo público", "Não aprovada")

# Semente do inventário na primeira execução. Reproduz o que o admin tinha no
# protótipo anterior: só o Copilot (tenant corporativo) nasce aprovado.
INVENTARIO_SEMENTE = {
    "chatgpt.com": ("ChatGPT (OpenAI)", "Não aprovada"),
    "chat.openai.com": ("ChatGPT (OpenAI)", "Não aprovada"),
    "claude.ai": ("Claude (Anthropic)", "Não aprovada"),
    "gemini.google.com": ("Gemini (Google)", "Não aprovada"),
    "copilot.microsoft.com": ("Copilot (Microsoft)", "Aprovada"),
    "m365.cloud.microsoft": ("Copilot (Microsoft)", "Aprovada"),
    "chat.deepseek.com": ("DeepSeek", "Não aprovada"),
    "perplexity.ai": ("Perplexity", "Não aprovada"),
    "www.perplexity.ai": ("Perplexity", "Não aprovada"),
    "poe.com": ("Poe", "Não aprovada"),
    "huggingface.co": ("HuggingChat", "Não aprovada"),
    "meta.ai": ("Meta AI", "Não aprovada"),
    "www.meta.ai": ("Meta AI", "Não aprovada"),
    "grok.com": ("Grok (xAI)", "Não aprovada"),
    "x.com": ("Grok (xAI)", "Não aprovada"),
}

# --- Normalização de ferramenta -------------------------------------------
# A extensão e o agente nomeiam a MESMA IA de formas diferentes (ex.: "ChatGPT"
# vs "ChatGPT (OpenAI)", domínio chatgpt.com vs openai.com). Para o painel não
# duplicar a ferramenta, normalizamos NA INGESTÃO para um nome e um domínio
# canônicos, por sufixo de domínio. A separação por `fonte_captura` é mantida.
# Sufixo de domínio → (nome canônico, domínio canônico alinhado ao inventário).
CANON_DOMINIOS = {
    "chatgpt.com": ("ChatGPT (OpenAI)", "chatgpt.com"),
    "openai.com": ("ChatGPT (OpenAI)", "chatgpt.com"),
    "claude.ai": ("Claude (Anthropic)", "claude.ai"),
    "anthropic.com": ("Claude (Anthropic)", "claude.ai"),
    "gemini.google.com": ("Gemini (Google)", "gemini.google.com"),
    "generativelanguage.googleapis.com": ("Gemini (Google)", "gemini.google.com"),
    "copilot.microsoft.com": ("Copilot (Microsoft)", "copilot.microsoft.com"),
    "m365.cloud.microsoft": ("Copilot (Microsoft)", "copilot.microsoft.com"),
    "deepseek.com": ("DeepSeek", "chat.deepseek.com"),
    "perplexity.ai": ("Perplexity", "perplexity.ai"),
    "poe.com": ("Poe", "poe.com"),
    "huggingface.co": ("HuggingChat", "huggingface.co"),
    "meta.ai": ("Meta AI", "meta.ai"),
    "grok.com": ("Grok (xAI)", "grok.com"),
    "x.ai": ("Grok (xAI)", "grok.com"),
    "x.com": ("Grok (xAI)", "grok.com"),
    "cursor.com": ("Cursor", "cursor.com"),
    "cursor.sh": ("Cursor", "cursor.com"),
}
# Nomes curtos que a extensão às vezes manda sem domínio utilizável.
CANON_NOMES = {
    "chatgpt": ("ChatGPT (OpenAI)", "chatgpt.com"),
    "claude": ("Claude (Anthropic)", "claude.ai"),
    "gemini": ("Gemini (Google)", "gemini.google.com"),
    "copilot": ("Copilot (Microsoft)", "copilot.microsoft.com"),
    "deepseek": ("DeepSeek", "chat.deepseek.com"),
    "perplexity": ("Perplexity", "perplexity.ai"),
    "poe": ("Poe", "poe.com"),
    "huggingchat": ("HuggingChat", "huggingface.co"),
    "meta ai": ("Meta AI", "meta.ai"),
    "grok": ("Grok (xAI)", "grok.com"),
    "cursor": ("Cursor", "cursor.com"),
}


def canonizar_ferramenta(dominio: str, ferramenta: str) -> tuple[str, str]:
    """(nome, domínio) canônicos. Casa por sufixo de domínio; se não houver
    domínio, tenta pelo nome curto. Sem correspondência, devolve o original."""
    d = str(dominio or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    if d:
        for suf, (nome, dom) in CANON_DOMINIOS.items():
            if d == suf or d.endswith("." + suf):
                return nome, dom
    f = str(ferramenta or "").strip().lower()
    if f in CANON_NOMES:
        return CANON_NOMES[f]
    return ferramenta, dominio


def inventario(con: sqlite3.Connection) -> dict:
    """{dominio: {nome, status}}. Semeia na primeira vez."""
    rows = con.execute("SELECT dominio, nome, status FROM inventario_dominios").fetchall()
    if not rows:
        con.executemany("INSERT INTO inventario_dominios VALUES (?,?,?)",
                        [(d, n, s) for d, (n, s) in INVENTARIO_SEMENTE.items()])
        con.commit()
        rows = con.execute("SELECT dominio, nome, status FROM inventario_dominios").fetchall()
    return {d: {"nome": n, "status": s} for d, n, s in rows}


def gravar_inventario(con: sqlite3.Connection, inv: dict) -> dict:
    """Substitui o inventário inteiro pelo que o admin enviou (saneado)."""
    limpo = {}
    for dom, meta in (inv or {}).items():
        if not isinstance(meta, dict):
            continue
        d = str(dom).strip().lower().replace("https://", "").replace("http://", "").split("/")[0][:120]
        if not d:
            continue
        status = meta.get("status") if meta.get("status") in STATUS_VALIDOS else "Não aprovada"
        limpo[d] = {"nome": str(meta.get("nome") or d)[:80], "status": status}
    with con:
        con.execute("DELETE FROM inventario_dominios")
        con.executemany("INSERT INTO inventario_dominios VALUES (?,?,?)",
                        [(d, m["nome"], m["status"]) for d, m in limpo.items()])
    return limpo


def ler_cadastros(con: sqlite3.Connection) -> dict:
    """Devolve o bloco de cadastros centrais {secao: [itens]} (vazio na 1ª vez)."""
    base = {k: [] for k in CADASTROS_SECOES}
    row = con.execute("SELECT valor FROM cadastros WHERE chave=?", (CADASTROS_CHAVE,)).fetchone()
    if row:
        try:
            g = json.loads(row[0]) or {}
            for k in CADASTROS_SECOES:
                if isinstance(g.get(k), list):
                    base[k] = g[k]
        except (ValueError, TypeError):
            pass
    return base


def gravar_cadastros(con: sqlite3.Connection, cad: dict) -> dict:
    """Substitui os cadastros centrais pelo que o painel enviou (só as seções válidas).

    Além de guardar o bloco, espelha as ferramentas que têm domínio + status no
    `inventario_dominios`, para que a mudança de status RECLASSIFIQUE as capturas
    daquela ferramenta no próximo pipeline (ponte cadastro → motor)."""
    limpo = {k: [] for k in CADASTROS_SECOES}
    for k in CADASTROS_SECOES:
        v = (cad or {}).get(k)
        if isinstance(v, list):
            limpo[k] = v[:500]   # teto defensivo
    with con:
        con.execute("INSERT OR REPLACE INTO cadastros (chave, valor) VALUES (?,?)",
                    (CADASTROS_CHAVE, json.dumps(limpo, ensure_ascii=False)))
    _espelhar_ferramentas_no_inventario(con, limpo.get("ferramentas", []))
    return limpo


def _espelhar_ferramentas_no_inventario(con: sqlite3.Connection, ferramentas: list) -> None:
    """Ferramenta com domínio + status vira (ou atualiza) uma entrada do inventário,
    para o motor reclassificar as capturas desse domínio. Sem domínio, só fica no
    cadastro (ex.: ferramentas da planilha que não têm site)."""
    inv = inventario(con)
    mudou = False
    for f in ferramentas or []:
        if not isinstance(f, dict):
            continue
        dom = str(f.get("dominio") or "").strip().lower()
        dom = dom.replace("https://", "").replace("http://", "").split("/")[0][:120]
        status = f.get("status")
        if not dom or status not in STATUS_VALIDOS:
            continue
        nome = str(f.get("nome") or dom)[:80]
        if inv.get(dom) != {"nome": nome, "status": status}:
            inv[dom] = {"nome": nome, "status": status}
            mudou = True
    if mudou:
        gravar_inventario(con, inv)


# Limiares do farol (segundos). Agente faz heartbeat a cada varredura (~60s);
# a extensão, a cada ~5 min. Online = contato fresco; instável = atrasado; offline.
HB_AGENTE = (180, 900)       # <180s online · <900s instável · senão offline
HB_EXTENSAO = (600, 1800)    # <600s online · <1800s instável · senão offline
FONTES_ESTACAO = ("agente", "extensao")


def registrar_heartbeat(con: sqlite3.Connection, maquina: str, fonte: str,
                        usuario: str = "", versao: str = "") -> None:
    """Upsert do 'estou vivo' de um agente/extensão numa estação."""
    maquina = _texto(maquina, 64) or "desconhecida"
    fonte = fonte if fonte in FONTES_ESTACAO else "agente"
    with con:
        con.execute(
            """INSERT INTO estacoes (maquina, fonte, usuario, versao, ultimo_hb)
               VALUES (?,?,?,?,?)
               ON CONFLICT(maquina, fonte) DO UPDATE SET
                 usuario=excluded.usuario, versao=excluded.versao, ultimo_hb=excluded.ultimo_hb""",
            (maquina, fonte, _texto(usuario, 64), _texto(versao, 32),
             dt.datetime.now().replace(microsecond=0).isoformat()))


def _idade_seg(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(iso)).total_seconds()
    except (ValueError, TypeError):
        return None


def _farol(idade: float | None, limites: tuple) -> str:
    if idade is None:
        return "ausente"
    on, instavel = limites
    if idade < on:
        return "online"
    if idade < instavel:
        return "instavel"
    return "offline"


def estacoes_status(con: sqlite3.Connection) -> list[dict]:
    """Uma linha por máquina: faróis do agente e da extensão, 'extensão
    desabilitada' (heartbeat + inferência) e últimos contatos."""
    maquinas: dict[str, dict] = {}

    def _m(nome):
        return maquinas.setdefault(nome or "desconhecida", {
            "maquina": nome or "desconhecida", "usuario": "",
            "hb_agente": None, "hb_extensao": None,
            "versao_agente": "", "versao_extensao": "",
            "ult_evt_agente": None, "ult_evt_extensao": None, "ult_uso_ia": None})

    # Heartbeats
    for r in con.execute("SELECT maquina, fonte, usuario, versao, ultimo_hb FROM estacoes"):
        m = _m(r[0])
        if r[1] == "agente":
            m["hb_agente"] = r[4]; m["versao_agente"] = r[3] or ""
        elif r[1] == "extensao":
            m["hb_extensao"] = r[4]; m["versao_extensao"] = r[3] or ""
        if r[2]:
            m["usuario"] = r[2]
    # Último evento por máquina/fonte (e último uso de IA visto pelo agente)
    for r in con.execute(
            """SELECT maquina, fonte_captura, MAX(COALESCE(recebido_em, ts)) ult
               FROM capturas GROUP BY maquina, fonte_captura"""):
        m = _m(r[0])
        if r[1] == "agente":
            m["ult_evt_agente"] = r[2]; m["ult_uso_ia"] = r[2]
        elif r[1] == "extensao":
            m["ult_evt_extensao"] = r[2]

    saida = []
    for m in maquinas.values():
        fa = _farol(_idade_seg(m["hb_agente"]), HB_AGENTE)
        fe = _farol(_idade_seg(m["hb_extensao"]), HB_EXTENSAO)
        # Inferência: agente vivo (ou viu uso de IA há pouco) e extensão sem
        # heartbeat/fresco => extensão provavelmente desabilitada na estação.
        agente_ativo = fa in ("online", "instavel")
        uso_ia_recente = (_idade_seg(m["ult_uso_ia"]) or 1e9) < HB_AGENTE[1]
        ext_sem_sinal = fe in ("offline", "ausente")
        desabilitada = bool((agente_ativo or uso_ia_recente) and ext_sem_sinal)
        saida.append({
            "maquina": m["maquina"], "usuario": m["usuario"],
            "farol_agente": fa, "farol_extensao": ("desabilitada" if desabilitada else fe),
            "extensao_desabilitada": desabilitada,
            "versao_agente": m["versao_agente"], "versao_extensao": m["versao_extensao"],
            "ultimo_agente": m["hb_agente"] or m["ult_evt_agente"],
            "ultimo_extensao": m["hb_extensao"] or m["ult_evt_extensao"],
        })
    saida.sort(key=lambda x: x["maquina"].lower())
    return saida


def garantir_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA_CAPTURAS)
    # Migração: bancos antigos não têm as colunas de conteúdo — adiciona se faltarem.
    cols = {r[1] for r in con.execute("PRAGMA table_info(capturas)")}
    for c in ("par_id", "papel", "prompt", "resposta", "fonte_captura", "classificado_por"):
        if c not in cols:
            con.execute(f"ALTER TABLE capturas ADD COLUMN {c} TEXT")
    con.commit()


def _slug(s: str) -> str:
    # tira acentos antes de reduzir a [a-z0-9]: "não identificado" → "nao-identificado"
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "x"


def _texto(v, n: int) -> str:
    return str(v if v is not None else "")[:n]


# ---------------------------------------------------------------------
# Entrada: o contrato do espia-borda
# ---------------------------------------------------------------------


def ingerir(con: sqlite3.Connection, corpo: dict, usuario: str, identidade_fonte: str) -> str:
    """Grava uma captura crua e devolve seu id (CAP-000001…).

    `usuario` e `identidade_fonte` já vêm resolvidos pelo coletor — a página
    nunca decide quem é o usuário. O corpo é o payload da extensão, saneado.
    """
    sens = corpo.get("sens") if corpo.get("sens") in SENSIBILIDADES else "Interna"
    try:
        qtd = max(1, int(corpo.get("qtd", 1)))
    except (TypeError, ValueError):
        qtd = 1
    deteccoes = corpo.get("deteccoes") if isinstance(corpo.get("deteccoes"), list) else []
    fingerprint = corpo.get("fingerprint") if isinstance(corpo.get("fingerprint"), dict) else {}
    # Quem capturou: explícito (proxy MITM manda fonte_captura), senão inferido —
    # o agente de rede manda origem_sensor/via; a extensão, não.
    fonte_captura = corpo.get("fonte_captura")
    if fonte_captura not in ("extensao", "agente", "mitm"):
        fonte_captura = "agente" if (corpo.get("origem_sensor") or corpo.get("via")) else "extensao"
    agora = dt.datetime.now().replace(microsecond=0).isoformat()
    ts = _texto(corpo.get("ts"), 32) or agora

    # --- Cascata de classificação do CONTEÚDO ---------------------------------
    # Nível 0: detectores determinísticos da borda (CPF/CNPJ/Luhn/credencial).
    # Nível 1: LLM LOCAL (llamafile + Qwen3), on-premise — o conteúdo não sai.
    # Nível 2: LLM na nuvem, só para o resíduo de baixa confiança (marcado aqui).
    tipo = _texto(corpo.get("tipo") or "Conteúdo não classificado", 80)
    classificado_por = "borda"
    conteudo = (corpo.get("prompt") or "") or (corpo.get("resposta") or "")
    if conteudo and fonte_captura in ("extensao", "mitm") and (
            not deteccoes or tipo == "Conteúdo não classificado"):
        from . import classificador_local as cl   # import tardio: sem custo se não usar
        r = cl.classificar(conteudo)
        if r:
            if r["confianca"] >= cl.MIN_CONF:
                tipo, sens = r["tipo"], r["sensibilidade"]
                classificado_por = "llm-local"
            else:
                classificado_por = "llm-local-baixa-confianca"   # candidato ao Nível 2

    # Normaliza a ferramenta: extensão e agente usam nomes/domínios diferentes
    # para a mesma IA; aqui unificamos para o canônico (a fonte segue separada).
    nome_fer, dom_canon = canonizar_ferramenta(
        corpo.get("dominio"), corpo.get("ferramenta") or corpo.get("dominio"))

    cur = con.execute(
        """INSERT INTO capturas (ts,recebido_em,usuario,identidade_fonte,maquina,dominio,
             ferramenta,status_fer,forma,qtd,tipo,sens,finalidade,deteccoes,fingerprint,
             previa,titulo,modo,par_id,papel,prompt,resposta,fonte_captura,classificado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts, agora, _texto(usuario, 64) or "não identificado", _texto(identidade_fonte, 20),
            _texto(corpo.get("maquina"), 64),
            _texto(dom_canon, 120),
            _texto(nome_fer, 80),
            _texto(corpo.get("status_fer"), 60),
            _texto(corpo.get("forma") or "Prompt", 40), qtd,
            tipo, sens,
            _texto(corpo.get("finalidade") or "Não declarada", 80),
            json.dumps(deteccoes, ensure_ascii=False)[:1200],
            json.dumps(fingerprint, ensure_ascii=False)[:4000],
            _texto(corpo.get("previa") or corpo.get("trecho"), 200),
            _texto(corpo.get("titulo"), 200),
            _texto(corpo.get("modo") or "observacao", 20),
            _texto(corpo.get("par_id"), 40),
            _texto(corpo.get("papel"), 12),
            _texto(corpo.get("prompt"), 16000),      # CONTEUDO da pesquisa
            _texto(corpo.get("resposta"), 16000),    # CONTEUDO do retorno da IA
            fonte_captura,
            classificado_por,                        # borda | llm-local | ...
        ),
    )
    cap_id = f"CAP-{cur.lastrowid:06d}"
    con.execute("UPDATE capturas SET cap_id=? WHERE seq=?", (cap_id, cur.lastrowid))
    con.commit()
    return cap_id


def contar(con: sqlite3.Connection) -> int:
    try:
        return con.execute("SELECT COUNT(*) FROM capturas").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


# ---------------------------------------------------------------------
# Saída: capturas viram Eventos da Base, com o inventário enriquecido
# ---------------------------------------------------------------------


def _usuario(base: bo.Base, nome: str) -> bo.Usuario:
    alvo = (nome or "").strip().lower()
    for u in base.usuarios.values():
        if u.nome.strip().lower() == alvo or u.id.lower() == alvo:
            return u
    # Usuário do Windows que a planilha não conhece: entra como externo,
    # sem área. Em produção o SSO/IAM (SRC-04) resolve isso.
    u = bo.Usuario(id=f"USR-EXT-{_slug(nome)}", nome=nome or "não identificado",
                   area="Não mapeada", cargo="", modelo_trabalho="", perfil_acesso="", status="Ativo")
    base.usuarios[u.id] = u
    return u


def _ferramenta(base: bo.Base, nome: str, dominio: str, status_fer: str, inv: dict) -> bo.Ferramenta:
    # 1) ferramenta da planilha, pelo nome (legado)
    alvo = (nome or "").strip().lower()
    for f in base.ferramentas.values():
        if f.nome.strip().lower() == alvo:
            return f
    # 2) ferramenta já registrada por captura anterior do MESMO domínio: o id é
    #    derivado do domínio, então é estável — independe do nome que veio.
    fid = f"IA-EXT-{_slug(dominio or nome)}"
    if fid in base.ferramentas:
        return base.ferramentas[fid]
    # 3) ferramenta real que a planilha não lista. O INVENTÁRIO do admin é a
    #    autoridade sobre nome e status; sem cadastro, vale o que a estação
    #    informou; sem nada, a postura conservadora: pública e não aprovada.
    cad = inv.get((dominio or "").lower())
    status = (cad["status"] if cad else None) or status_fer or "Não aprovada"
    nome_exib = (cad["nome"] if cad else None) or nome or dominio
    aprovada = status.lower().startswith("aprovada")
    f = bo.Ferramenta(
        id=fid, nome=nome_exib,
        tipo="Corporativa" if aprovada else "Pública", status=status,
        uso_principal="Detectada pela borda",
        logs="Sim" if aprovada else "Não",
        controles="Inventário do coletor" if aprovada else "Sem contrato corporativo",
        finalidade_aprovada="Conforme inventário" if aprovada else "Uso não autorizado",
    )
    base.ferramentas[f.id] = f
    return f


def _tipo(base: bo.Base, nome: str, sens: str, deteccoes: list) -> bo.TipoInformacao:
    alvo = (nome or "").strip().lower()
    for t in base.tipos.values():
        if t.nome.strip().lower() == alvo:
            return t
    # Tipo que os detectores da borda nomearam e a planilha não tem.
    # Se veio credencial, a categoria precisa dizer isso: é o que a R03 lê.
    credencial = any(isinstance(d, dict) and d.get("tipo") == "credencial" for d in deteccoes)
    t = bo.TipoInformacao(
        id=f"INF-EXT-{_slug(nome)}", nome=nome or "Conteúdo não classificado",
        categoria="Credencial" if credencial else "Detectado na borda",
        classificacao_padrao=sens if sens in SENSIBILIDADES else "Interna",
        area_tipica="—",
    )
    base.tipos[t.id] = t
    return t


def _parse_ts(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _evidencia(deteccoes: list, identidade_fonte: str, previa: str) -> str:
    partes = []
    for d in deteccoes:
        if isinstance(d, dict) and d.get("tipo"):
            partes.append(f"{d['tipo']}×{d.get('contagem', 1)}" + ("✓" if d.get("validado") else ""))
    det = ("detectores na borda: " + ", ".join(partes)) if partes else "sem padrão sensível detectado"
    ident = "identidade verificada" if identidade_fonte in FONTES_VERIFICADAS else f"identidade {identidade_fonte or 'ausente'}"
    prev = f' · prévia mascarada: "{previa}"' if previa else ""
    return f"{det} · {ident}{prev}"


def anexar_a_base(con: sqlite3.Connection, base: bo.Base) -> int:
    """Converte cada captura em um Evento e o anexa à base. Devolve quantos."""
    try:
        rows = con.execute(
            """SELECT cap_id,ts,usuario,identidade_fonte,dominio,ferramenta,status_fer,forma,qtd,
                      tipo,sens,finalidade,deteccoes,previa FROM capturas ORDER BY seq"""
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    inv = inventario(con)
    n = 0
    for (cap_id, ts, usuario, fonte, dominio, ferramenta, status_fer, forma, qtd,
         tipo, sens, finalidade, deteccoes_json, previa) in rows:
        try:
            deteccoes = json.loads(deteccoes_json or "[]")
        except json.JSONDecodeError:
            deteccoes = []
        u = _usuario(base, usuario)
        f = _ferramenta(base, ferramenta, dominio, status_fer, inv)
        t = _tipo(base, tipo, sens, deteccoes)
        base.eventos.append(bo.Evento(
            id=cap_id, ts=_parse_ts(ts), ts_bruto=ts,
            usuario_id=u.id, area=u.area,
            ferramenta_id=f.id, ferramenta_nome=f.nome,
            informacao_id=t.id, informacao_nome=t.nome,
            sensibilidade=sens, forma_uso=forma, qtd_itens=int(qtd or 1),
            finalidade=finalidade,
            # Captura não tem risco DECLARADO: ela nasce avaliada pelo GerencIA.
            risco_declarado="", regra_declarada="",
            evidencias_declaradas=_evidencia(deteccoes, fonte, previa),
            acao_sugerida="",
            origem_registro=ORIGEM_CAPTURA,
        ))
        n += 1
    return n
