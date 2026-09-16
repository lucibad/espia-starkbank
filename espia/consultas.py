"""
EspIA — consultas de linhagem sobre a base oficial.

A pergunta norteadora do desafio é:

    "Se amanhã a empresa precisasse descobrir quais informações confidenciais
     foram utilizadas em ferramentas de IA, ela conseguiria identificar o que foi
     compartilhado, por quem, onde e quando?"

Cada função abaixo responde uma parte dessa pergunta direto do SQLite, sem
depender do painel. Serve para a demonstração e para o caso em que a banca pedir
um corte que a tela não tem.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_DB = RAIZ / "dados" / "espia.db"


def conectar(caminho: Path = CAMINHO_DB) -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------
# A busca reversa
# ---------------------------------------------------------------------


def linhagem(con, termo: str) -> list[dict]:
    """Toda a vida de um tipo de informação (ou de um usuário) dentro de IA."""
    sql = """
    SELECT e.id, e.ts, e.area, e.informacao, e.informacao_id, e.sensibilidade,
           e.ferramenta, e.forma_uso, e.qtd_itens, e.finalidade, e.origem,
           e.risco_espia AS risco, e.regra_espia AS regra,
           e.risco_base, e.divergente,
           u.nome AS pessoa, u.cargo,
           f.status AS status_ferramenta, f.aprovada,
           a.id AS alerta, a.status AS alerta_status
    FROM eventos e
    JOIN usuarios u    ON u.id = e.usuario_id
    JOIN ferramentas f ON f.id = e.ferramenta_id
    LEFT JOIN alertas a ON a.evento_id = e.id
    WHERE e.informacao LIKE ? OR e.informacao_id LIKE ?
       OR u.nome LIKE ?      OR e.usuario_id LIKE ?
    ORDER BY e.ts DESC
    """
    alvo = f"%{termo}%"
    return [dict(r) for r in con.execute(sql, (alvo, alvo, alvo, alvo))]


def exposicao(con) -> list[dict]:
    sql = """
    SELECT e.informacao_id AS id, e.informacao AS nome, e.sensibilidade,
           COUNT(*) AS eventos,
           COUNT(DISTINCT e.usuario_id) AS pessoas,
           COUNT(DISTINCT e.ferramenta_id) AS ferramentas,
           SUM(CASE WHEN f.aprovada = 0 THEN 1 ELSE 0 END) AS fora_politica,
           SUM(CASE WHEN e.risco_espia IN ('Crítico','Alto') THEN 1 ELSE 0 END) AS em_risco,
           MAX(e.ts) AS ultimo
    FROM eventos e JOIN ferramentas f ON f.id = e.ferramenta_id
    GROUP BY e.informacao_id
    ORDER BY em_risco DESC, eventos DESC
    """
    return [dict(r) for r in con.execute(sql)]


def alertas(con, nivel: str = "Crítico", limite: int = 20) -> list[dict]:
    sql = """
    SELECT e.id, e.ts, u.nome AS pessoa, e.area, e.ferramenta, e.informacao,
           e.sensibilidade, e.risco_espia AS risco, e.regra_espia AS regra,
           e.risco_base, e.divergente, a.id AS alerta, a.status, a.responsavel
    FROM eventos e
    JOIN usuarios u ON u.id = e.usuario_id
    LEFT JOIN alertas a ON a.evento_id = e.id
    WHERE e.risco_espia = ?
    ORDER BY e.ts DESC LIMIT ?
    """
    return [dict(r) for r in con.execute(sql, (nivel, limite))]


def evidencia(con, evento_id: str) -> tuple[dict | None, list[dict]]:
    evt = con.execute("""
        SELECT e.*, u.nome AS pessoa, u.cargo, f.status AS status_ferramenta,
               f.controles, f.finalidade AS finalidade_ferramenta,
               a.id AS alerta, a.status AS alerta_status, a.responsavel
        FROM eventos e
        JOIN usuarios u ON u.id = e.usuario_id
        JOIN ferramentas f ON f.id = e.ferramenta_id
        LEFT JOIN alertas a ON a.evento_id = e.id
        WHERE e.id = ?""", (evento_id,)).fetchone()
    if not evt:
        return None, []
    ach = con.execute("""
        SELECT regra, nivel, titulo, motivo, acao, contextual
        FROM achados_evento WHERE evento_id = ?""", (evento_id,)).fetchall()
    return dict(evt), [dict(r) for r in ach]


def indicadores(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM indicadores")]


def auditoria(con) -> list[dict]:
    linhas = []
    for r in con.execute("SELECT * FROM auditoria ORDER BY gravidade, id"):
        d = dict(r)
        d["eventos"] = json.loads(d["eventos"])
        d["detalhe"] = json.loads(d["detalhe"])
        linhas.append(d)
    return linhas


def validacao(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM validacao ORDER BY caso")]


def regras(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM regras ORDER BY id")]


def panorama(con) -> dict:
    q = lambda s, p=(): con.execute(s, p).fetchone()[0]
    total = q("SELECT COUNT(*) FROM eventos")
    return {
        "eventos": total,
        "alertas": q("SELECT COUNT(*) FROM alertas"),
        "usuarios": q("SELECT COUNT(DISTINCT usuario_id) FROM eventos"),
        "ferramentas": q("SELECT COUNT(DISTINCT ferramenta_id) FROM eventos"),
        "nao_aprovadas": q("""SELECT COUNT(*) FROM eventos e JOIN ferramentas f
                              ON f.id=e.ferramenta_id WHERE f.aprovada=0"""),
        "sensiveis": q("""SELECT COUNT(*) FROM eventos
                          WHERE sensibilidade IN ('Confidencial','Crítica')"""),
        "por_risco": {r[0]: r[1] for r in con.execute(
            "SELECT risco_espia, COUNT(*) FROM eventos GROUP BY risco_espia")},
        "por_risco_base": {r[0]: r[1] for r in con.execute(
            "SELECT risco_base, COUNT(*) FROM eventos GROUP BY risco_base")},
        "divergentes": q("SELECT COUNT(*) FROM eventos WHERE divergente=1"),
        "validacao_ok": q("SELECT COUNT(*) FROM validacao WHERE passou=1"),
        "validacao_total": q("SELECT COUNT(*) FROM validacao"),
        "achados": q("SELECT COUNT(*) FROM auditoria"),
        "indicadores_divergentes": q("SELECT COUNT(*) FROM indicadores WHERE divergente=1"),
        "indicadores_conferem": q("SELECT COUNT(*) FROM indicadores WHERE confere=1"),
        "indicadores_total": q("SELECT COUNT(*) FROM indicadores"),
    }


# ---------------------------------------------------------------------
# Impressão
# ---------------------------------------------------------------------

_COR = {"Crítico": "\033[91m", "Alto": "\033[93m", "Médio": "\033[94m",
        "Baixo": "\033[90m", "REVISAR": "\033[96m"}


def cab(texto: str) -> None:
    print(f"\n\033[1m{texto}\033[0m")
    print("─" * min(len(texto), 78))


def marcador(nivel: str) -> str:
    return f"{_COR.get(nivel, '')}●\033[0m"


def imprimir_linhagem(con, termo: str) -> None:
    linhas = linhagem(con, termo)
    if not linhas:
        print(f"Nada encontrado para '{termo}'.")
        return
    primeiro = linhas[0]
    cab(f"{primeiro['informacao']}  —  busca por '{termo}'")
    pessoas = {l["pessoa"] for l in linhas}
    ferramentas = {l["ferramenta"] for l in linhas}
    risco = [l for l in linhas if l["risco"] in ("Crítico", "Alto")]
    fora = [l for l in linhas if not l["aprovada"]]
    print(f"{len(linhas)} uso(s) · {len(pessoas)} pessoa(s) · {len(ferramentas)} ferramenta(s) · "
          f"{len(fora)} fora da política · {len(risco)} em risco alto ou crítico")
    print(f"Último uso: {primeiro['ts'][:16].replace('T', ' ')}\n")
    for l in linhas[:30]:
        div = f"  (base: {l['risco_base']})" if l["divergente"] else ""
        print(f"{marcador(l['risco'])} {l['ts'][:16].replace('T',' ')}  {l['pessoa']:<22} "
              f"{l['ferramenta']:<26} {l['regra']:<5} {l['risco']:<8}{div}")
    if len(linhas) > 30:
        print(f"… e mais {len(linhas) - 30} evento(s)")


def imprimir_evidencia(con, evento_id: str) -> None:
    evt, ach = evidencia(con, evento_id)
    if not evt:
        print(f"Evento {evento_id} não encontrado.")
        return
    cab(f"Evidência — {evento_id}  ·  {evt['risco_espia'].upper()}  ·  regra {evt['regra_espia']}")
    print(f"{evt['pessoa']} ({evt['cargo']}, {evt['area']}) → {evt['ferramenta']} [{evt['status_ferramenta']}]")
    print(f"{evt['ts'][:16].replace('T',' ')} · {evt['informacao']} ({evt['sensibilidade']}) · "
          f"{evt['forma_uso']}, {evt['qtd_itens']} item(ns) · finalidade: {evt['finalidade']}")
    print(f"origem do registro: {evt['origem']}"
          + (f" · alerta {evt['alerta']} ({evt['alerta_status']}, {evt['responsavel']})" if evt["alerta"] else ""))
    if evt["divergente"]:
        print(f"\n\033[93m⚠ a base classificou como {evt['risco_base']} pela regra {evt['regra_base']}\033[0m")
    print()
    for a in ach:
        marca = "  ·" if a["contextual"] else "  ▸"
        print(f"{marca} [{a['regra']}] {a['titulo']}  ({a['nivel']}"
              + (", contexto" if a["contextual"] else "") + ")")
        print(f"      {a['motivo']}")
        print(f"      ação: {a['acao']}\n")
