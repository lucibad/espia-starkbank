"""
GerencIA — Pipeline de ingestão e enriquecimento.

Percurso de um evento:

    coletor (gateway/extensão/declarativo/api)
        │
        ▼  texto bruto — existe apenas em memória, nesta função
    fingerprint  ──► assinatura MinHash/SimHash
    detectores   ──► tipos e contagens de dado sensível
        │
        ▼  o texto é descartado aqui
    casamento com o acervo classificado
        │
        ▼
    motor de risco  ──► score + nível + cadeia de evidências
        │
        ▼
    SQLite  (linhagem consultável)  ──►  JSON  (dashboard)

O ponto a defender na banca: depois da linha "o texto é descartado aqui",
o conteúdo confidencial não existe mais no sistema. O que fica é a
identidade da informação, não a informação.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml                       # PyYAML, se estiver instalado
except ModuleNotFoundError:           # senão, o leitor embutido
    from . import yaml_min as yaml

from . import shadow
from .acervo import ACERVO, ACERVO_POR_ID
from .detectores import detectar, mascarar
from .fingerprint import Assinatura, casar
from .motor_risco import MotorRisco
from .simulador import COLABORADORES, COLABORADORES_POR_ID, gerar

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_POLITICA = RAIZ / "config" / "politica.yaml"
DIR_DADOS = RAIZ / "dados"


# ---------------------------------------------------------------------


def carregar_politica(caminho: Path = CAMINHO_POLITICA) -> dict:
    with open(caminho, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def construir_catalogo_assinaturas(politica: dict) -> dict[str, Assinatura]:
    """Indexa o acervo. Numa implantação real, roda uma vez por documento,
    disparado pelo conector do repositório, e nunca mais precisa do texto."""
    cfg = politica["fingerprint"]
    return {
        ativo.id: Assinatura.de_texto(
            ativo.texto, n=cfg["tamanho_shingle"], num_perm=cfg["permutacoes_minhash"]
        )
        for ativo in ACERVO
    }


# ---------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------

ESQUEMA = """
DROP TABLE IF EXISTS ativos;
DROP TABLE IF EXISTS colaboradores;
DROP TABLE IF EXISTS ferramentas;
DROP TABLE IF EXISTS eventos;
DROP TABLE IF EXISTS correspondencias;
DROP TABLE IF EXISTS deteccoes;
DROP TABLE IF EXISTS fatores_risco;
DROP TABLE IF EXISTS shadow_ai;

CREATE TABLE ativos (
  id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, classificacao TEXT,
  area_dona TEXT, repositorio TEXT, n_shingles INTEGER, simhash TEXT
);
CREATE TABLE colaboradores (
  id TEXT PRIMARY KEY, nome TEXT, area TEXT, cargo TEXT, senioridade TEXT
);
CREATE TABLE ferramentas (
  id TEXT PRIMARY KEY, nome TEXT, fornecedor TEXT, tier TEXT,
  treina_com_dados INTEGER, jurisdicao TEXT, fator_risco REAL
);
CREATE TABLE eventos (
  id TEXT PRIMARY KEY, ts TEXT, data TEXT, hora INTEGER, dia_semana INTEGER,
  colaborador_id TEXT, area TEXT, ferramenta_id TEXT, canal TEXT,
  finalidade TEXT, tamanho INTEGER, classificacao_efetiva TEXT,
  score REAL, nivel TEXT, mascaramento_aceito INTEGER,
  n_correspondencias INTEGER, total_pii INTEGER
);
CREATE TABLE correspondencias (
  evento_id TEXT, ativo_id TEXT, jaccard REAL, containment REAL, confianca TEXT
);
CREATE TABLE deteccoes (evento_id TEXT, tipo TEXT, contagem INTEGER);
CREATE TABLE fatores_risco (
  evento_id TEXT, codigo TEXT, rotulo TEXT, tipo TEXT,
  valor REAL, contribuicao REAL, explicacao TEXT, marcos TEXT
);
CREATE TABLE shadow_ai (
  dominio TEXT PRIMARY KEY, catalogada INTEGER, nome TEXT, tier TEXT, severidade TEXT,
  n_usuarios INTEGER, areas TEXT, requisicoes INTEGER, bytes_enviados INTEGER,
  escopos_oauth TEXT, primeiro_visto TEXT, ultimo_visto TEXT, motivos TEXT
);

CREATE INDEX idx_evt_ativo ON correspondencias(ativo_id);
CREATE INDEX idx_evt_ts ON eventos(ts);
CREATE INDEX idx_evt_nivel ON eventos(nivel);
"""


# ---------------------------------------------------------------------


def executar(semente: int | None = None, verboso: bool = True) -> dict:
    politica = carregar_politica()
    cfg_fp = politica["fingerprint"]
    motor = MotorRisco(politica)
    tiers = {f["id"]: f["tier"] for f in politica["ferramentas_ia"]}
    ferramentas_por_id = {f["id"]: f for f in politica["ferramentas_ia"]}

    if verboso:
        print("→ indexando acervo…")
    catalogo = construir_catalogo_assinaturas(politica)

    if verboso:
        print("→ simulando 90 dias de rede corporativa…")
    kwargs = {"semente": semente} if semente is not None else {}
    eventos_brutos, registros_proxy, concessoes = gerar(tiers, **kwargs)

    if verboso:
        print(f"   {len(eventos_brutos)} eventos de IA, {len(registros_proxy)} registros de proxy, "
              f"{len(concessoes)} concessões OAuth")
        print("→ enriquecendo eventos (fingerprint + detectores + risco)…")

    # Janela de reincidência: (colaborador, ferramenta) -> timestamps
    historico: dict[tuple[str, str], list[datetime]] = defaultdict(list)

    processados = []
    for i, bruto in enumerate(eventos_brutos):
        if verboso and i and i % 1500 == 0:
            print(f"   {i}/{len(eventos_brutos)}")

        # --- tudo o que toca o texto acontece dentro deste bloco --------
        assinatura = Assinatura.de_texto(
            bruto.texto, n=cfg_fp["tamanho_shingle"], num_perm=cfg_fp["permutacoes_minhash"]
        )
        deteccoes = detectar(bruto.texto)
        correspondencias = casar(
            assinatura, catalogo,
            limiar=cfg_fp["limiar_correspondencia"],
            limiar_alta=cfg_fp["limiar_alta_confianca"],
        )
        tamanho = len(bruto.texto)
        _, n_mascaradas = mascarar(bruto.texto) if bruto.mascaramento_aceito else ("", 0)
        # --- a partir daqui o texto não é mais referenciado -------------

        chave = (bruto.colaborador_id, bruto.ferramenta_id)
        limite = bruto.ts - timedelta(days=7)
        similares = sum(1 for t in historico[chave] if t >= limite)
        historico[chave].append(bruto.ts)

        avaliacao = motor.avaliar(
            ts=bruto.ts,
            ferramenta_id=bruto.ferramenta_id,
            canal=bruto.canal,
            finalidade=bruto.finalidade,
            finalidade_aprovada=bruto.finalidade_aprovada,
            mascaramento_aceito=bruto.mascaramento_aceito,
            tamanho_texto=tamanho,
            correspondencias=correspondencias,
            ativos=ACERVO_POR_ID,
            deteccoes=deteccoes,
            eventos_similares_7d=similares,
        )

        col = COLABORADORES_POR_ID[bruto.colaborador_id]
        classificacoes = [ACERVO_POR_ID[c.ativo_id].classificacao for c in correspondencias]
        pesos = politica["classificacao"]
        efetiva = (
            max(classificacoes, key=lambda c: pesos[c]["peso"]) if classificacoes
            else ("confidencial" if any(d.tipo in ("cpf", "email", "telefone") for d in deteccoes) else "publico")
        )

        processados.append({
            "bruto": bruto,
            "col": col,
            "correspondencias": correspondencias,
            "deteccoes": deteccoes,
            "avaliacao": avaliacao,
            "tamanho": tamanho,
            "classificacao_efetiva": efetiva,
            "n_mascaradas": n_mascaradas,
        })

    if verboso:
        print("→ correlacionando Shadow AI…")
    dominios_catalogados = {}
    for f in politica["ferramentas_ia"]:
        for d in f["dominios"]:
            dominios_catalogados[d] = (f["nome"], f["tier"])
    descobertas = shadow.descobrir(
        registros_proxy, concessoes, dominios_catalogados, COLABORADORES_POR_ID
    )

    if verboso:
        print("→ gravando SQLite…")
    DIR_DADOS.mkdir(exist_ok=True)
    caminho_db = DIR_DADOS / "espia.db"
    if caminho_db.exists():
        caminho_db.unlink()
    con = sqlite3.connect(caminho_db)
    con.executescript(ESQUEMA)

    con.executemany(
        "INSERT INTO ativos VALUES (?,?,?,?,?,?,?,?)",
        [(a.id, a.nome, a.categoria, a.classificacao, a.area_dona, a.repositorio,
          catalogo[a.id].n_shingles, hex(catalogo[a.id].simhash)) for a in ACERVO],
    )
    con.executemany(
        "INSERT INTO colaboradores VALUES (?,?,?,?,?)",
        [(c.id, c.nome, c.area, c.cargo, c.senioridade) for c in COLABORADORES],
    )
    con.executemany(
        "INSERT INTO ferramentas VALUES (?,?,?,?,?,?,?)",
        [(f["id"], f["nome"], f["fornecedor"], f["tier"], int(bool(f["treina_com_dados"])),
          f["jurisdicao"], f["fator_risco"]) for f in politica["ferramentas_ia"]],
    )

    linhas_evt, linhas_corr, linhas_det, linhas_fat = [], [], [], []
    for p in processados:
        b, a = p["bruto"], p["avaliacao"]
        total_pii = sum(d.contagem for d in p["deteccoes"] if d.tipo in ("cpf", "email", "telefone", "chave_pix_aleatoria"))
        linhas_evt.append((
            b.id, b.ts.isoformat(), b.ts.date().isoformat(), b.ts.hour, b.ts.weekday(),
            b.colaborador_id, p["col"].area, b.ferramenta_id, b.canal, b.finalidade,
            p["tamanho"], p["classificacao_efetiva"], a.score, a.nivel,
            int(b.mascaramento_aceito), len(p["correspondencias"]), total_pii,
        ))
        for c in p["correspondencias"]:
            linhas_corr.append((b.id, c.ativo_id, c.jaccard, c.containment, c.confianca))
        for d in p["deteccoes"]:
            linhas_det.append((b.id, d.tipo, d.contagem))
        for f in a.fatores:
            linhas_fat.append((b.id, f.codigo, f.rotulo, f.tipo, f.valor, f.contribuicao,
                               f.explicacao, json.dumps(f.marcos)))

    con.executemany("INSERT INTO eventos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas_evt)
    con.executemany("INSERT INTO correspondencias VALUES (?,?,?,?,?)", linhas_corr)
    con.executemany("INSERT INTO deteccoes VALUES (?,?,?)", linhas_det)
    con.executemany("INSERT INTO fatores_risco VALUES (?,?,?,?,?,?,?,?)", linhas_fat)

    linhas_shadow = []
    for f in descobertas:
        sev, motivos = f.severidade()
        linhas_shadow.append((
            f.dominio, int(f.catalogada), f.nome_catalogo or f.aplicativo_oauth or f.dominio,
            f.tier or "nao_catalogada",
            sev, f.n_usuarios, json.dumps(sorted(f.areas)), f.requisicoes, f.bytes_enviados,
            json.dumps(sorted(f.escopos_oauth)), f.primeiro_visto.isoformat(),
            f.ultimo_visto.isoformat(), json.dumps(motivos),
        ))
    con.executemany("INSERT INTO shadow_ai VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", linhas_shadow)
    con.commit()

    if verboso:
        print("→ exportando JSON do dashboard…")
    payload = montar_payload(con, politica, processados, descobertas)
    (DIR_DADOS / "dashboard.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    con.close()

    caminho_painel = exportar_painel(payload)

    if verboso:
        n_crit = sum(1 for p in processados if p["avaliacao"].nivel == "critico")
        n_alto = sum(1 for p in processados if p["avaliacao"].nivel == "alto")
        nao_cat = sum(1 for f in descobertas if not f.catalogada)
        print(f"\n✓ {len(processados)} eventos · {n_crit} críticos · {n_alto} altos")
        print(f"✓ {len(descobertas)} ferramentas de IA vistas na rede, {nao_cat} fora do cadastro")
        print(f"✓ banco:  {caminho_db}")
        print(f"✓ painel: {caminho_painel}")
        print("\nPara abrir o painel:  python3 run.py painel")

    return payload


# ---------------------------------------------------------------------
# Painel local
# ---------------------------------------------------------------------

DIR_PAINEL = RAIZ / "dashboard"


def exportar_painel(payload: dict) -> Path:
    """Gera um painel.html autossuficiente — um arquivo só, que abre com dois cliques.

    O `index.html` do repositório é o corpo da página, escrito para ser publicado.
    Aqui ele é embrulhado num documento HTML completo com os dados embutidos, de
    modo que o resultado funcione offline, por file://, e possa ser enviado por
    e-mail sem nada em volta.
    """
    corpo = (DIR_PAINEL / "index.html").read_text(encoding="utf-8")

    dados = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # </script> dentro de uma string JSON encerraria a tag cedo demais.
    dados = dados.replace("</", "<\\/")

    # o corpo referencia dados.js; aqui os dados entram na própria página
    corpo = corpo.replace(
        '<script src="dados.js"></script>',
        f"<script>window.EspIA={dados};</script>",
    )

    doc = (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<style>:root{color-scheme:light dark}img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + corpo + "\n</body>\n</html>\n"
    )

    destino = DIR_PAINEL / "painel.html"
    destino.write_text(doc, encoding="utf-8")

    # também atualiza o dados.js, usado pela versão publicada
    (DIR_PAINEL / "dados.js").write_text(
        "window.EspIA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8",
    )
    return destino


# ---------------------------------------------------------------------
# Payload do dashboard
# ---------------------------------------------------------------------


def montar_payload(con, politica, processados, descobertas) -> dict:
    cur = con.cursor()

    def linhas(sql, params=()):
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # Eventos enviados na íntegra para o dashboard poder filtrar no cliente,
    # mas sem nenhum conteúdo — só metadados e ponteiros.
    eventos = linhas("SELECT * FROM eventos ORDER BY ts")
    corr_por_evento: dict[str, list] = defaultdict(list)
    for r in linhas("SELECT * FROM correspondencias"):
        corr_por_evento[r["evento_id"]].append(r)
    det_por_evento: dict[str, list] = defaultdict(list)
    for r in linhas("SELECT * FROM deteccoes"):
        det_por_evento[r["evento_id"]].append({"tipo": r["tipo"], "contagem": r["contagem"]})
    fat_por_evento: dict[str, list] = defaultdict(list)
    for r in linhas("SELECT * FROM fatores_risco"):
        fat_por_evento[r["evento_id"]].append({
            "codigo": r["codigo"], "rotulo": r["rotulo"], "tipo": r["tipo"],
            "valor": r["valor"], "contribuicao": r["contribuicao"],
            "explicacao": r["explicacao"], "marcos": json.loads(r["marcos"]),
        })

    for e in eventos:
        e["correspondencias"] = [
            {"ativo_id": c["ativo_id"], "score": round(max(c["jaccard"], c["containment"]), 3),
             "confianca": c["confianca"]}
            for c in corr_por_evento.get(e["id"], [])
        ]
        e["deteccoes"] = det_por_evento.get(e["id"], [])
        # Fatores só para o que é alto/crítico — é onde a evidência importa,
        # e evita inflar o payload em 10x.
        if e["nivel"] in ("critico", "alto"):
            e["fatores"] = fat_por_evento.get(e["id"], [])

    # Série temporal diária por nível
    serie: dict[str, dict] = {}
    for e in eventos:
        d = serie.setdefault(e["data"], {"data": e["data"], "total": 0, "critico": 0, "alto": 0, "medio": 0, "baixo": 0})
        d["total"] += 1
        d[e["nivel"]] += 1

    return {
        "meta": {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "organizacao": politica["organizacao"]["nome"],
            "aviso": "Dados 100% sintéticos, gerados para o Desafio 2. Nenhuma informação real.",
            "periodo": {"inicio": eventos[0]["data"], "fim": eventos[-1]["data"]},
        },
        "politica": {
            "classificacao": politica["classificacao"],
            "categorias": politica["categorias_informacao"],
            "motor_risco": politica["motor_risco"],
            "marcos": politica["organizacao"]["marcos_regulatorios"],
            "privacidade": politica["privacidade"],
        },
        "ativos": linhas("SELECT * FROM ativos"),
        "colaboradores": linhas("SELECT * FROM colaboradores"),
        "ferramentas": [
            {**f, "dominios": f["dominios"]} for f in politica["ferramentas_ia"]
        ],
        "eventos": eventos,
        "serie_diaria": sorted(serie.values(), key=lambda d: d["data"]),
        "shadow_ai": [
            {**r, "areas": json.loads(r["areas"]), "escopos_oauth": json.loads(r["escopos_oauth"]),
             "motivos": json.loads(r["motivos"])}
            for r in linhas("SELECT * FROM shadow_ai")
        ],
        "shadow_por_area": shadow.resumo_por_area(descobertas, COLABORADORES_POR_ID),
    }
