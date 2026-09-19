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
  modo             TEXT NOT NULL    -- observacao | mascaramento | bloqueio
);
-- Inventário das IAs externas monitoradas: o admin cadastra e decide o status.
-- É a autoridade sobre nome e aprovação das ferramentas que a planilha não
-- lista (o `dominios_monitorados_url` da política de GPO do espia-borda).
CREATE TABLE IF NOT EXISTS inventario_dominios (
  dominio TEXT PRIMARY KEY,
  nome    TEXT NOT NULL,
  status  TEXT NOT NULL
);
"""

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


def garantir_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA_CAPTURAS)
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
    agora = dt.datetime.now().replace(microsecond=0).isoformat()
    ts = _texto(corpo.get("ts"), 32) or agora

    cur = con.execute(
        """INSERT INTO capturas (ts,recebido_em,usuario,identidade_fonte,maquina,dominio,
             ferramenta,status_fer,forma,qtd,tipo,sens,finalidade,deteccoes,fingerprint,
             previa,titulo,modo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ts, agora, _texto(usuario, 64) or "não identificado", _texto(identidade_fonte, 20),
            _texto(corpo.get("maquina"), 64),
            _texto(corpo.get("dominio"), 120),
            _texto(corpo.get("ferramenta") or corpo.get("dominio"), 80),
            _texto(corpo.get("status_fer"), 60),
            _texto(corpo.get("forma") or "Prompt", 40), qtd,
            _texto(corpo.get("tipo") or "Conteúdo não classificado", 80), sens,
            _texto(corpo.get("finalidade") or "Não declarada", 80),
            json.dumps(deteccoes, ensure_ascii=False)[:1200],
            json.dumps(fingerprint, ensure_ascii=False)[:4000],
            _texto(corpo.get("previa") or corpo.get("trecho"), 200),
            _texto(corpo.get("titulo"), 200),
            _texto(corpo.get("modo") or "observacao", 20),
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
