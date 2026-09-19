"""
GerencIA — pipeline sobre a base oficial do desafio.

Percurso:

    base/Base_de_Dados_Starkbank_apurada_15-09.xlsx
        │
        ▼  importador (openpyxl ou leitor embutido)
    650 eventos · 160 alertas · 8 ferramentas · 20 tipos · 72 usuários · 14 regras
        │
        ├──► motor de regras R01–R14  ──► risco GerencIA + cadeia de evidências
        ├──► validador                ──► os 15 casos oficiais
        └──► auditoria                ──► indicadores recalculados + defeitos de rotulagem
        │
        ▼
    SQLite (consultável)  ──►  JSON  ──►  painel.html autossuficiente
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from . import auditoria as au
from . import base_oficial as bo
from . import regras as rg
from . import validacao as vl
from . import captura as cp

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "dados"
DIR_PAINEL = RAIZ / "dashboard"

ESQUEMA = """
DROP TABLE IF EXISTS eventos;
DROP TABLE IF EXISTS achados_evento;
DROP TABLE IF EXISTS alertas;
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS ferramentas;
DROP TABLE IF EXISTS tipos_informacao;
DROP TABLE IF EXISTS regras;
DROP TABLE IF EXISTS validacao;
DROP TABLE IF EXISTS indicadores;
DROP TABLE IF EXISTS auditoria;

CREATE TABLE eventos (
  id TEXT PRIMARY KEY, ts TEXT, data TEXT, hora INTEGER, fora_horario INTEGER,
  usuario_id TEXT, area TEXT, ferramenta_id TEXT, ferramenta TEXT,
  informacao_id TEXT, informacao TEXT, sensibilidade TEXT, forma_uso TEXT,
  qtd_itens INTEGER, finalidade TEXT, origem TEXT,
  risco_base TEXT, regra_base TEXT, evidencia_base TEXT, acao_base TEXT,
  risco_espia TEXT, regra_espia TEXT, divergente INTEGER, lacuna TEXT
);
CREATE TABLE achados_evento (
  evento_id TEXT, regra TEXT, nivel TEXT, titulo TEXT, motivo TEXT,
  acao TEXT, contextual INTEGER
);
CREATE TABLE alertas (
  id TEXT PRIMARY KEY, evento_id TEXT, ts TEXT, usuario_id TEXT, area TEXT,
  ferramenta TEXT, informacao TEXT, sensibilidade TEXT, risco TEXT, regra TEXT,
  evidencia TEXT, status TEXT, responsavel TEXT
);
CREATE TABLE usuarios (
  id TEXT PRIMARY KEY, nome TEXT, area TEXT, cargo TEXT, modelo TEXT, perfil TEXT, status TEXT
);
CREATE TABLE ferramentas (
  id TEXT PRIMARY KEY, nome TEXT, tipo TEXT, status TEXT, aprovada INTEGER,
  publica INTEGER, logs TEXT, controles TEXT, finalidade TEXT
);
CREATE TABLE tipos_informacao (
  id TEXT PRIMARY KEY, nome TEXT, categoria TEXT, classificacao TEXT, area_tipica TEXT
);
CREATE TABLE regras (
  id TEXT PRIMARY KEY, tema TEXT, texto TEXT, nivel TEXT, acao TEXT,
  usos_base INTEGER, usos_espia INTEGER
);
CREATE TABLE validacao (
  caso TEXT PRIMARY KEY, area TEXT, ferramenta TEXT, informacao TEXT,
  sensibilidade TEXT, esperado TEXT, obtido TEXT, regra TEXT, passou INTEGER, justificativa TEXT
);
CREATE TABLE indicadores (
  nome TEXT PRIMARY KEY, declarado TEXT, apurado TEXT, planilha TEXT,
  confere INTEGER, divergente INTEGER, observacao TEXT
);
CREATE TABLE auditoria (
  id TEXT PRIMARY KEY, familia TEXT, gravidade TEXT, titulo TEXT, resumo TEXT,
  consequencia TEXT, evidencia TEXT, n_eventos INTEGER, eventos TEXT, detalhe TEXT
);

CREATE INDEX idx_ev_data ON eventos(data);
CREATE INDEX idx_ev_risco ON eventos(risco_espia);
CREATE INDEX idx_ev_info ON eventos(informacao_id);
CREATE INDEX idx_ev_user ON eventos(usuario_id);
CREATE INDEX idx_ach_ev ON achados_evento(evento_id);
"""


def executar(caminho_base: Path | None = None, verboso: bool = True) -> dict:
    if verboso:
        print("→ lendo a base oficial…")
    base = bo.carregar(caminho_base or bo.CAMINHO_PADRAO)
    if verboso:
        print(f"   {len(base.eventos)} eventos · {len(base.alertas)} alertas · "
              f"{len(base.ferramentas)} ferramentas · {len(base.usuarios)} usuários "
              f"· {len(base.regras)} regras   [{base.leitor}]")

    # O Excel é a CARGA LEGADA. As capturas do espia-borda já persistidas em
    # `capturas` são o PRESENTE e entram na MESMA base, para o motor avaliar
    # legado e presente com a mesma régua. Nada da base legada é alterado.
    DIR_DADOS.mkdir(exist_ok=True)
    caminho_db = DIR_DADOS / "espia.db"
    con = sqlite3.connect(caminho_db, timeout=10)
    cp.garantir_esquema(con)
    n_capturas = cp.anexar_a_base(con, base)
    if verboso and n_capturas:
        print(f"   + {n_capturas} evento(s) capturados ao vivo (espia-borda) anexados à base")

    if verboso:
        print("→ aplicando as regras R01–R14…")
    motor = rg.MotorRegras(base)
    avaliacoes: dict[str, rg.Avaliacao] = {}
    for e in base.eventos:
        av = motor.avaliar_evento(e)
        avaliacoes[e.id] = av
        e.risco_espia = av.nivel
        e.regra_espia = av.regra_principal

    # Concordância e auditoria são sobre a base LEGADA: captura não tem risco
    # declarado para divergir, e os indicadores declarados são da planilha.
    legado = [e for e in base.eventos if e.origem_registro != cp.ORIGEM_CAPTURA]
    concord_nivel = sum(1 for e in legado if e.risco_espia == e.risco_declarado)
    concord_regra = sum(1 for e in legado if e.regra_espia == e.regra_declarada)

    if verboso:
        n = len(legado)
        print(f"   concordância de nível com a base legada: {concord_nivel}/{n} "
              f"({100*concord_nivel/n:.1f}%)")

    if verboso:
        print("→ validando contra os 15 casos oficiais…")
    validador = vl.Validador(base)
    resumo_val = validador.resumo()
    if verboso:
        print(f"   {resumo_val['passaram']}/{resumo_val['total']} casos reproduzidos"
              + (f"  FALHAS: {resumo_val['falharam']}" if resumo_val["falharam"] else ""))

    if verboso:
        print("→ auditando a base…")
    import dataclasses as _dc
    audit = au.Auditoria(_dc.replace(base, eventos=legado))
    indicadores = audit.indicadores()
    achados = audit.achados()
    if verboso:
        divergentes = sum(1 for i in indicadores if i.divergente)
        print(f"   {divergentes} de {len(indicadores)} indicadores declarados divergem da base")
        print(f"   {len(achados)} achados de auditoria")

    if verboso:
        print("→ gravando SQLite…")
    # Não apaga mais o arquivo: o ESQUEMA recria só as tabelas derivadas.
    # A tabela `capturas` (o presente) sobrevive ao `gerar`.
    con.executescript(ESQUEMA)
    _gravar(con, base, avaliacoes, resumo_val, indicadores, achados)
    con.commit()

    if verboso:
        print("→ exportando painel…")
    payload = _payload(base, avaliacoes, resumo_val, indicadores, achados,
                       concord_nivel, concord_regra)
    (DIR_DADOS / "dashboard.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    con.close()

    caminho_painel = exportar_painel(payload)

    if verboso:
        crit = sum(1 for e in base.eventos if e.risco_espia == "Crítico")
        alto = sum(1 for e in base.eventos if e.risco_espia == "Alto")
        print(f"\n✓ {len(base.eventos)} eventos · {crit} críticos · {alto} altos")
        print(f"✓ {resumo_val['passaram']}/{resumo_val['total']} casos de validação oficiais")
        print(f"✓ {len(achados)} achados de auditoria sobre a própria base")
        print(f"✓ banco:  {caminho_db}")
        print(f"✓ painel: {caminho_painel}")
        print("\nPara abrir o painel:  python3 run.py painel")

    return payload


# ---------------------------------------------------------------------


def _gravar(con, base, avaliacoes, resumo_val, indicadores, achados) -> None:
    con.executemany(
        "INSERT INTO eventos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(
            e.id, e.ts.isoformat() if e.ts else "", e.data, e.hora, int(e.fora_horario),
            e.usuario_id, e.area, e.ferramenta_id, e.ferramenta_nome,
            e.informacao_id, e.informacao_nome, e.sensibilidade, e.forma_uso,
            e.qtd_itens, e.finalidade, e.origem_registro,
            e.risco_declarado, e.regra_declarada, e.evidencias_declaradas, e.acao_sugerida,
            e.risco_espia, e.regra_espia, int(e.divergente),
            avaliacoes[e.id].lacuna or "",
        ) for e in base.eventos],
    )
    con.executemany(
        "INSERT INTO achados_evento VALUES (?,?,?,?,?,?,?)",
        [(eid, a.regra, a.nivel, a.titulo, a.motivo, a.acao, int(a.contextual))
         for eid, av in avaliacoes.items() for a in av.achados],
    )
    con.executemany(
        "INSERT INTO alertas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(a.id, a.evento_id, a.ts_bruto, a.usuario_id, a.area, a.ferramenta, a.informacao,
          a.sensibilidade, a.risco, a.regra, a.evidencia, a.status, a.responsavel)
         for a in base.alertas],
    )
    con.executemany(
        "INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)",
        [(u.id, u.nome, u.area, u.cargo, u.modelo_trabalho, u.perfil_acesso, u.status)
         for u in base.usuarios.values()],
    )
    con.executemany(
        "INSERT INTO ferramentas VALUES (?,?,?,?,?,?,?,?,?)",
        [(f.id, f.nome, f.tipo, f.status, int(f.aprovada), int(f.publica), f.logs,
          f.controles, f.finalidade_aprovada) for f in base.ferramentas.values()],
    )
    con.executemany(
        "INSERT INTO tipos_informacao VALUES (?,?,?,?,?)",
        [(t.id, t.nome, t.categoria, t.classificacao_padrao, t.area_tipica)
         for t in base.tipos.values()],
    )
    usos_base = Counter(e.regra_declarada for e in base.eventos)
    usos_prov = Counter(a.regra for av in avaliacoes.values() for a in av.achados)
    con.executemany(
        "INSERT INTO regras VALUES (?,?,?,?,?,?,?)",
        [(r.id, r.tema, r.texto, r.nivel_esperado, r.acao_esperada,
          usos_base.get(r.id, 0), usos_prov.get(r.id, 0)) for r in base.regras.values()],
    )
    con.executemany(
        "INSERT INTO validacao VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(x.caso, x.area, x.ferramenta, x.informacao, x.sensibilidade, x.esperado,
          x.obtido, x.regra, int(x.passou), x.justificativa)
         for x in resumo_val["resultados"]],
    )
    con.executemany(
        "INSERT INTO indicadores VALUES (?,?,?,?,?,?,?)",
        [(i.nome, i.declarado, i.apurado, i.planilha, int(i.confere), int(i.divergente),
          i.observacao) for i in indicadores],
    )
    con.executemany(
        "INSERT INTO auditoria VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(a.id, a.familia, a.gravidade, a.titulo, a.resumo, a.consequencia, a.evidencia,
          len(a.eventos), json.dumps(a.eventos), json.dumps(a.detalhe, ensure_ascii=False))
         for a in achados],
    )


# ---------------------------------------------------------------------


def _payload(base, avaliacoes, resumo_val, indicadores, achados,
             concord_nivel, concord_regra) -> dict:
    usos_base = Counter(e.regra_declarada for e in base.eventos)
    usos_prov_principal = Counter(e.regra_espia for e in base.eventos)
    usos_prov_todas = Counter(a.regra for av in avaliacoes.values() for a in av.achados)

    alerta_por_evento = {a.evento_id: a for a in base.alertas}

    eventos = []
    for e in base.eventos:
        av = avaliacoes[e.id]
        alerta = alerta_por_evento.get(e.id)
        eventos.append({
            "id": e.id, "ts": e.ts.isoformat() if e.ts else "", "data": e.data,
            "hora": e.hora, "fora_horario": int(e.fora_horario),
            "usuario_id": e.usuario_id, "area": e.area,
            "ferramenta_id": e.ferramenta_id, "ferramenta": e.ferramenta_nome,
            "informacao_id": e.informacao_id, "informacao": e.informacao_nome,
            "sensibilidade": e.sensibilidade, "forma_uso": e.forma_uso,
            "qtd": e.qtd_itens, "finalidade": e.finalidade, "origem": e.origem_registro,
            "risco_base": e.risco_declarado, "regra_base": e.regra_declarada,
            "evidencia_base": e.evidencias_declaradas, "acao_base": e.acao_sugerida,
            "risco": e.risco_espia, "regra": e.regra_espia,
            "divergente": int(e.divergente), "lacuna": av.lacuna or "",
            "achados": [{
                "regra": a.regra, "nivel": a.nivel, "titulo": a.titulo,
                "motivo": a.motivo, "acao": a.acao, "contextual": int(a.contextual),
            } for a in av.achados],
            "alerta": ({"id": alerta.id, "status": alerta.status,
                        "responsavel": alerta.responsavel} if alerta else None),
        })

    serie: dict[str, dict] = {}
    for e in base.eventos:
        d = serie.setdefault(e.data, {"data": e.data, "total": 0,
                                      "Crítico": 0, "Alto": 0, "Médio": 0, "Baixo": 0,
                                      "REVISAR": 0})
        d["total"] += 1
        d[e.risco_espia] = d.get(e.risco_espia, 0) + 1

    return {
        "meta": {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "organizacao": "Stark Bank",
            "fonte": "Base de Dados — Starkbank apurada 15-09.xlsx (base oficial do Desafio 2)",
            "leitor": base.leitor,
            "aviso": "Dados fictícios, declarado na própria planilha. Nenhuma informação real.",
            "periodo": {"inicio": base.periodo[0], "fim": base.periodo[1]},
            "totais": {
                "eventos": len(base.eventos), "alertas": len(base.alertas),
                "legado": sum(1 for e in base.eventos if e.origem_registro != cp.ORIGEM_CAPTURA),
                "capturas": sum(1 for e in base.eventos if e.origem_registro == cp.ORIGEM_CAPTURA),
                "usuarios": len(base.usuarios), "ferramentas": len(base.ferramentas),
                "tipos": len(base.tipos), "regras": len(base.regras), "areas": len(base.areas),
            },
            "concordancia": {
                # numerador e denominador sobre a MESMA base: a legada
                "nivel": concord_nivel, "regra": concord_regra,
                "total": sum(1 for e in base.eventos if e.origem_registro != cp.ORIGEM_CAPTURA),
            },
        },
        "politica": {
            "classificacoes": base.classificacoes,
            "regras": [{
                "id": r.id, "tema": r.tema, "texto": r.texto, "nivel": r.nivel_esperado,
                "acao": r.acao_esperada, "usos_base": usos_base.get(r.id, 0),
                "usos_principal": usos_prov_principal.get(r.id, 0),
                "usos_total": usos_prov_todas.get(r.id, 0),
            } for r in base.regras.values()],
            "propostas": rg.PROPOSTAS,
            "precedencia": [
                f"{rid} · {rg.DESCRICAO_PRECEDENCIA.get(rid, '')}"
                for rid in rg.PRECEDENCIA
            ],
        },
        "ferramentas": [{
            "id": f.id, "nome": f.nome, "tipo": f.tipo, "status": f.status,
            "aprovada": int(f.aprovada), "publica": int(f.publica), "logs": f.logs,
            "controles": f.controles, "finalidade": f.finalidade_aprovada,
            "uso_principal": f.uso_principal,
        } for f in base.ferramentas.values()],
        "tipos": [{
            "id": t.id, "nome": t.nome, "categoria": t.categoria,
            "classificacao": t.classificacao_padrao, "area_tipica": t.area_tipica,
        } for t in base.tipos.values()],
        "usuarios": [{
            "id": u.id, "nome": u.nome, "area": u.area, "cargo": u.cargo,
            "modelo": u.modelo_trabalho, "perfil": u.perfil_acesso,
        } for u in base.usuarios.values()],
        "eventos": eventos,
        "alertas": [{
            "id": a.id, "evento_id": a.evento_id, "ts": a.ts_bruto, "usuario_id": a.usuario_id,
            "area": a.area, "ferramenta": a.ferramenta, "informacao": a.informacao,
            "sensibilidade": a.sensibilidade, "risco": a.risco, "regra": a.regra,
            "evidencia": a.evidencia, "status": a.status, "responsavel": a.responsavel,
        } for a in base.alertas],
        "serie_diaria": sorted(serie.values(), key=lambda d: d["data"]),
        "validacao": [{
            "caso": x.caso, "area": x.area, "ferramenta": x.ferramenta,
            "informacao": x.informacao, "sensibilidade": x.sensibilidade,
            "esperado": x.esperado, "obtido": x.obtido, "regra": x.regra,
            "passou": int(x.passou), "justificativa": x.justificativa,
            "achados": x.achados,
            # ids resolvidos: o console de políticas reavalia os casos no navegador
            "ferramenta_id": x.ferramenta_id, "informacao_id": x.informacao_id,
            "qtd": x.qtd_itens,
        } for x in resumo_val["resultados"]],
        "indicadores": [{
            "nome": i.nome, "declarado": i.declarado, "apurado": i.apurado,
            "planilha": i.planilha, "confere": int(i.confere),
            "divergente": int(i.divergente), "observacao": i.observacao,
        } for i in indicadores],
        "auditoria": [{
            "id": a.id, "familia": a.familia, "gravidade": a.gravidade, "titulo": a.titulo,
            "resumo": a.resumo, "consequencia": a.consequencia, "evidencia": a.evidencia,
            "eventos": a.eventos, "detalhe": a.detalhe,
        } for a in achados],
        "fontes": [{
            "id": f.id, "nome": f.nome, "dados": f.dados, "formato": f.formato,
            "confiabilidade": f.confiabilidade, "atualizacao": f.atualizacao,
        } for f in base.fontes],
    }


# ---------------------------------------------------------------------


def exportar_painel(payload: dict) -> Path:
    """Monta o painel.html autossuficiente — um arquivo, com os dados dentro."""
    corpo = (DIR_PAINEL / "index.html").read_text(encoding="utf-8")
    dados = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    corpo = corpo.replace('<script src="dados.js"></script>',
                          f"<script>window.EspIA={dados};</script>")
    doc = (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<style>:root{color-scheme:light dark}img{max-width:100%}[hidden]{display:none!important}</style>\n"
        "</head>\n<body>\n" + corpo + "\n</body>\n</html>\n"
    )
    destino = DIR_PAINEL / "painel.html"
    destino.write_text(doc, encoding="utf-8")
    (DIR_PAINEL / "dados.js").write_text(
        "window.EspIA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";",
        encoding="utf-8")
    return destino
