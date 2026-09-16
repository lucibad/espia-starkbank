#!/usr/bin/env python3
"""
EspIA — carga inicial do piloto.

Converte o SQLite que `run.py gerar` produz num arquivo SQL que o PostgreSQL de
produção engole direto. É o que faz o piloto nascer com os 650 eventos da base
oficial já carregados, em vez de um console vazio esperando o primeiro coletor.

    python3 bin/exportar_postgres.py                    # → sql/piloto/900_carga_inicial.sql
    python3 bin/exportar_postgres.py --saida /tmp/x.sql

Por que isso importa na implantação: no primeiro dia, Compliance abre o console
e vê a auditoria da própria rotulagem — os seis achados, os dez indicadores
recalculados. Console vazio no dia um é como o projeto morre.

Só depende da biblioteca padrão.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]      # .../espia
BANCO = RAIZ / "dados" / "espia.db"
SAIDA = RAIZ / "implantacao" / "sql" / "piloto" / "900_carga_inicial.sql"

NIVEIS = {"Baixo", "Médio", "Alto", "Crítico", "REVISAR"}


def lit(v) -> str:
    """Literal SQL. Sem interpolação ingênua: aspas simples dobradas."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--banco", type=Path, default=BANCO)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    args = ap.parse_args()

    if not args.banco.exists():
        print(f"base não encontrada em {args.banco}\n"
              f"rode antes:  python3 run.py gerar", file=sys.stderr)
        return 1

    con = sqlite3.connect(args.banco)
    con.row_factory = sqlite3.Row
    linhas: list[str] = []

    # Chave estrangeira não perdoa: um evento cujo usuário ou ferramenta não
    # existe no cadastro faria a carga inteira falhar. E não deve mesmo entrar
    # com id inventado — é justamente o caso que R13/R14 mandam marcar REVISAR.
    ids_ferramenta = {r["id"] for r in con.execute("SELECT id FROM ferramentas")}
    ids_tipo = {r["id"] for r in con.execute("SELECT id FROM tipos_informacao")}
    ids_usuario = {r["id"] for r in con.execute("SELECT id FROM usuarios")}
    nome_ferramenta = {r["nome"]: r["id"] for r in con.execute("SELECT id,nome FROM ferramentas")}
    nome_tipo = {r["nome"]: r["id"] for r in con.execute("SELECT id,nome FROM tipos_informacao")}

    def fk(valor, validos):
        return valor if valor in validos else None

    def por_nome(valor, mapa, validos):
        if valor in validos:
            return valor
        return mapa.get(valor)

    linhas.append(
        "-- EspIA — carga inicial do piloto.\n"
        f"-- Gerado em {datetime.now():%d/%m/%Y %H:%M} a partir de {args.banco.name}.\n"
        "--\n"
        "-- Todos os dados são fictícios, conforme declarado na própria planilha do\n"
        "-- desafio. Nenhum dado real de cliente entra num piloto — nem aqui, nem\n"
        "-- em homologação. A primeira carga com dado real é a do primeiro coletor.\n"
        "\nBEGIN;\nSET search_path TO espia, public;\n"
    )

    # ── cadastros ────────────────────────────────────────────────────────────
    for r in con.execute("SELECT * FROM ferramentas"):
        linhas.append(
            "INSERT INTO ferramentas (id,nome,tipo,status,publica,logs,controles,finalidade) "
            f"VALUES ({lit(r['id'])},{lit(r['nome'])},{lit(r['tipo'])},{lit(r['status'])},"
            f"{lit(bool(r['publica']))},{lit(r['logs'])},{lit(r['controles'])},{lit(r['finalidade'])}) "
            "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status;")

    for r in con.execute("SELECT * FROM tipos_informacao"):
        linhas.append(
            "INSERT INTO tipos_informacao (id,nome,categoria,classificacao,area_tipica) "
            f"VALUES ({lit(r['id'])},{lit(r['nome'])},{lit(r['categoria'])},"
            f"{lit(r['classificacao'])},{lit(r['area_tipica'])}) "
            "ON CONFLICT (id) DO NOTHING;")

    for r in con.execute("SELECT * FROM usuarios"):
        linhas.append(
            "INSERT INTO usuarios (id,nome,area,cargo,perfil,status) "
            f"VALUES ({lit(r['id'])},{lit(r['nome'])},{lit(r['area'])},"
            f"{lit(r['cargo'])},{lit(r['perfil'])},{lit(r['status'])}) "
            "ON CONFLICT (id) DO NOTHING;")

    # ── política ─────────────────────────────────────────────────────────────
    regras = [dict(r) for r in con.execute("SELECT * FROM regras")]
    conteudo = {
        "origem": "Base de Dados — Starkbank apurada 15-09.xlsx, aba Regras_Risco",
        "regras": {r["id"]: {"nivel": r["nivel"], "acao": r["acao"], "ativa": True}
                   for r in regras},
        "precedencia": ["R14", "R13", "R03", "R05", "R04", "R06", "R02", "R01",
                        "R11", "R10", "R07", "R09", "R08", "R12"],
        "limite_volume": 10,
    }
    linhas.append(
        "INSERT INTO politica_versoes (autor,nota,conteudo,hash,vigente) VALUES ("
        f"{lit('carga inicial')},"
        f"{lit('Política oficial, lida da planilha. A precedência é o que a EspIA acrescenta.')},"
        f"{lit(json.dumps(conteudo, ensure_ascii=False))}::jsonb,"
        f"{lit(hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode()).hexdigest())},true);")

    for r in regras:
        ordem = (conteudo["precedencia"].index(r["id"]) + 1
                 if r["id"] in conteudo["precedencia"] else None)
        nivel = r["nivel"] if r["nivel"] in NIVEIS else None
        linhas.append(
            "INSERT INTO regras (id,tema,texto,nivel,acao,ordem) "
            f"VALUES ({lit(r['id'])},{lit(r['tema'])},{lit(r['texto'])},"
            f"{('NULL' if nivel is None else lit(nivel) + '::nivel_risco')},"
            f"{lit(r['acao'])},{lit(ordem)}) ON CONFLICT (id) DO NOTHING;")

    # ── eventos ──────────────────────────────────────────────────────────────
    achados: dict[str, list] = {}
    for a in con.execute("SELECT * FROM achados_evento"):
        achados.setdefault(a["evento_id"], []).append(
            {"regra": a["regra"], "nivel": a["nivel"], "titulo": a["titulo"],
             "motivo": a["motivo"], "acao": a["acao"], "contextual": bool(a["contextual"])})

    n_ev = 0
    for r in con.execute("SELECT * FROM eventos ORDER BY ts"):
        risco = r["risco_espia"] if r["risco_espia"] in NIVEIS else None
        cadeia = json.dumps(achados.get(r["id"], []), ensure_ascii=False)
        linhas.append(
            "INSERT INTO eventos (id,ocorrido_em,fora_horario,usuario_id,area,ferramenta_id,"
            "informacao_id,sensibilidade,forma_uso,qtd_itens,finalidade,origem,risco,regra,"
            "achados,politica_id) VALUES ("
            f"{lit(r['id'])},{lit(r['ts'])}::timestamptz,{lit(bool(r['fora_horario']))},"
            f"{lit(fk(r['usuario_id'], ids_usuario))},{lit(r['area'])},"
            f"{lit(fk(r['ferramenta_id'], ids_ferramenta))},"
            f"{lit(fk(r['informacao_id'], ids_tipo))},{lit(r['sensibilidade'])},{lit(r['forma_uso'])},"
            f"{lit(r['qtd_itens'] or 1)},{lit(r['finalidade'])},{lit(r['origem'] or 'carga')},"
            f"{('NULL' if risco is None else lit(risco) + '::nivel_risco')},{lit(r['regra_espia'])},"
            f"{lit(cadeia)}::jsonb,(SELECT id FROM politica_versoes WHERE vigente)) "
            "ON CONFLICT DO NOTHING;")
        n_ev += 1

    # ── alertas ──────────────────────────────────────────────────────────────
    n_al = 0
    for r in con.execute("SELECT * FROM alertas"):
        risco = r["risco"] if r["risco"] in NIVEIS else "Alto"
        # Achado A-05: a base traz 47 alertas "Tratado" sem data. O esquema de
        # produção não aceita isso (CHECK alerta_tratado_tem_data), então a
        # carga entra com o estado que a base pode PROVAR: Aberto.
        linhas.append(
            "INSERT INTO alertas (id,evento_id,ocorrido_em,usuario_id,area,ferramenta_id,"
            "informacao_id,risco,regra,evidencia,estado) VALUES ("
            f"{lit(r['id'])},{lit(r['evento_id'])},{lit(r['ts'])}::timestamptz,"
            f"{lit(fk(r['usuario_id'], ids_usuario))},{lit(r['area'])},"
            f"{lit(por_nome(r['ferramenta'], nome_ferramenta, ids_ferramenta))},"
            f"{lit(por_nome(r['informacao'], nome_tipo, ids_tipo))},"
            f"{lit(risco)}::nivel_risco,{lit(r['regra'])},"
            f"{lit(r['evidencia'])},'Aberto') ON CONFLICT (id) DO NOTHING;")
        n_al += 1

    # ── achados de auditoria ─────────────────────────────────────────────────
    n_au = 0
    for r in con.execute("SELECT * FROM auditoria"):
        eventos = [e for e in (r["eventos"] or "").split(",") if e]
        arr = "ARRAY[" + ",".join(lit(e) for e in eventos) + "]::text[]" if eventos else "NULL"
        linhas.append(
            "INSERT INTO achados_auditoria (id,familia,gravidade,titulo,resumo,consequencia,"
            "evidencia,n_eventos,eventos) VALUES ("
            f"{lit(r['id'])},{lit(r['familia'])},{lit(r['gravidade'])},{lit(r['titulo'])},"
            f"{lit(r['resumo'])},{lit(r['consequencia'])},{lit(r['evidencia'])},"
            f"{lit(r['n_eventos'])},{arr}) ON CONFLICT (id) DO NOTHING;")
        n_au += 1

    for r in con.execute("SELECT * FROM indicadores"):
        linhas.append(
            "INSERT INTO indicadores (nome,apurado_em,declarado,apurado,confere,observacao) "
            f"VALUES ({lit(r['nome'])},CURRENT_DATE,{lit(r['declarado'])},{lit(r['apurado'])},"
            f"{lit(bool(r['confere']))},{lit(r['observacao'])}) ON CONFLICT DO NOTHING;")

    linhas.append(
        "\nINSERT INTO trilha (ator,acao,objeto,detalhe) VALUES "
        f"('instalacao','carga inicial','base oficial do desafio',"
        f"'{{\"eventos\":{n_ev},\"alertas\":{n_al},\"achados\":{n_au},\"ficticios\":true}}'::jsonb);")
    linhas.append("\nCOMMIT;")

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    con.close()

    print(f"→ {args.saida}")
    print(f"   {n_ev} eventos · {n_al} alertas · {n_au} achados · {len(regras)} regras")
    print(f"   {args.saida.stat().st_size/1024:.0f} KB")
    print("\n   Carregue com:")
    print("     docker compose exec -T postgres psql -U espia -d espia "
          f"< sql/piloto/{args.saida.name}")
    print("\n   Fica em sql/piloto/, FORA do que o compose monta como init: dado\n   fictício não entra em instalação de produção por descuido de path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
