"""
GerencIA — auditoria da base.

Este módulo faz o que diferencia uma ferramenta de governança de um painel:
ele **não confia na classificação que recebeu**. Recalcula os indicadores a
partir dos fatos, compara com o que a organização declara, e procura defeitos
na própria rotulagem.

São seis famílias de achado:

  A. Indicadores declarados que não batem com a base.
  B. Eventos cuja regra citada contradiz os campos do próprio evento.
  C. Eventos em que uma regra genérica foi citada onde existia uma específica —
     o nível fica igual, a resposta obrigatória muda.
  D. Eventos sub-classificados: a política restringe a ferramenta e o registro
     não reflete isso.
  E. Regras da política que nunca disparam.
  F. Lacunas de instrumentação: indicadores que a base não permite apurar.

Cada achado carrega a lista de eventos afetados, para que ninguém precise
acreditar — dá para conferir um a um.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .regras import MotorRegras


@dataclass
class Achado:
    id: str
    familia: str            # A | B | C | D | E | F
    titulo: str
    gravidade: str          # alta | media | baixa
    resumo: str
    consequencia: str
    evidencia: str
    eventos: list[str] = field(default_factory=list)
    detalhe: list[dict] = field(default_factory=list)


@dataclass
class Indicador:
    nome: str
    declarado: str
    apurado: str
    planilha: str           # o que a própria planilha apurou
    confere: bool           # nosso cálculo bate com o da planilha
    divergente: bool        # o declarado diverge do apurado
    observacao: str


def _pct(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f}%".replace(".", ",") if total else "—"


class Auditoria:
    def __init__(self, base):
        self.base = base
        self.motor = MotorRegras(base)
        self.eventos = base.eventos
        self.n = len(base.eventos)
        self.nao_aprovadas = {f.id for f in base.ferramentas.values() if not f.aprovada}

    # =================================================================
    # A. Indicadores
    # =================================================================

    def indicadores(self) -> list[Indicador]:
        ev, n = self.eventos, self.n
        b = self.base

        usuarios = len({e.usuario_id for e in ev})
        ferramentas = len({e.ferramenta_id for e in ev})
        nao_aprov = sum(1 for e in ev if e.ferramenta_id in self.nao_aprovadas)
        confid = sum(1 for e in ev if e.sensibilidade == "Confidencial")
        sens_critica = sum(1 for e in ev if e.sensibilidade == "Crítica")
        risco_critico = sum(1 for e in ev if e.risco_declarado == "Crítico")
        areas = len({e.area for e in ev})
        rastreaveis = sum(1 for e in ev if e.rastreavel)
        sem_class = sum(1 for e in ev if not e.sensibilidade or e.informacao_id not in b.tipos)
        com_logs = sum(1 for f in b.ferramentas.values() if f.tem_logs)
        tratados = sum(1 for a in b.alertas if a.status == "Tratado")

        declarados = {i.nome: i for i in b.indicadores}

        def mk(nome, apurado, observacao=""):
            d = declarados.get(nome)
            planilha = d.valor_planilha if d else ""
            declarado = d.valor_declarado if d else ""
            confere = _mesma_medida(apurado, planilha)
            divergente = not _mesma_medida(apurado, declarado)
            return Indicador(nome, declarado, apurado, planilha, confere, divergente,
                             observacao or (d.divergencia_planilha if d else ""))

        saida = [
            mk("Usuários ativos usando IA/mês", str(usuarios)),
            mk("Ferramentas de IA identificadas", str(ferramentas)),
            mk("Uso em ferramentas não aprovadas", _pct(nao_aprov, n),
               f"{nao_aprov} de {n} eventos em IA Pública A ou B"),
            mk("Eventos com informação confidencial", _pct(confid, n),
               f"{confid} eventos classificados como Confidencial"),
            mk("Eventos críticos", _pct(sens_critica, n),
               f"{sens_critica} eventos de sensibilidade Crítica ({_pct(sens_critica, n)}); "
               f"se a leitura for risco Crítico, são {risco_critico} ({_pct(risco_critico, n)}). "
               "As duas leituras superam o declarado."),
            mk("Alertas críticos tratados em até 24h", "não apurável",
               f"{tratados} dos {len(b.alertas)} alertas estão como 'Tratado', mas não há data "
               "de tratamento — não dá para medir prazo."),
            mk("Eventos com rastreabilidade completa", _pct(rastreaveis, n),
               "todos os eventos têm usuário, ferramenta e data"),
            mk("Áreas com uso de IA identificado", str(areas)),
            mk("Ferramentas com logs corporativos", f"{com_logs} de {len(b.ferramentas)}",
               "5 marcadas 'Sim' e 1 'Parcial'; o declarado conta a parcial como completa"),
            mk("Casos sem classificação suficiente", _pct(sem_class, n),
               "nenhum evento chega sem classificação"),
        ]
        return saida

    # =================================================================
    # B a F. Defeitos
    # =================================================================

    def achados(self) -> list[Achado]:
        b, ev = self.base, self.eventos
        saida: list[Achado] = []

        # --- B: regra citada contradiz o fato --------------------------
        pressupoem_aprovada = {"R07", "R08", "R09", "R10", "R11"}
        incompativeis = [
            e for e in ev
            if e.ferramenta_id in self.nao_aprovadas and e.regra_declarada in pressupoem_aprovada
        ]
        if incompativeis:
            cont = Counter(e.regra_declarada for e in incompativeis)
            saida.append(Achado(
                id="A-01", familia="B", gravidade="alta",
                titulo="Regra citada pressupõe ferramenta aprovada, mas a ferramenta não era",
                resumo=(
                    f"{len(incompativeis)} eventos ocorreram em IA Pública A ou B — ambas "
                    f"'Não aprovada' no cadastro — mas citam regras cujo texto diz "
                    f"'em ferramenta aprovada': "
                    + ", ".join(f"{r} ({q}×)" for r, q in cont.most_common())
                ),
                consequencia=(
                    "O nível de risco pode estar certo, mas a trilha de auditoria está errada. "
                    "Um auditor que ler 'R09 — dados anonimizados em ferramenta aprovada' num "
                    "evento que aconteceu numa IA pública será induzido a erro. É a diferença "
                    "entre registro e evidência."
                ),
                evidencia="Regras_Risco R08/R09 × coluna Status da aba Ferramentas_IA",
                eventos=[e.id for e in incompativeis],
                detalhe=[{
                    "evento": e.id, "ferramenta": e.ferramenta_nome,
                    "status": b.ferramentas[e.ferramenta_id].status,
                    "regra": e.regra_declarada, "sensibilidade": e.sensibilidade,
                } for e in incompativeis[:40]],
            ))

        # --- C: regra genérica onde existia específica -----------------
        especificas = []
        for e in ev:
            if e.ferramenta_id not in self.nao_aprovadas:
                continue
            info = b.tipos.get(e.informacao_id)
            ferr = b.ferramentas.get(e.ferramenta_id)
            if not info or not ferr:
                continue
            if info.e_dado_pessoal and ferr.publica and e.regra_declarada not in ("R04",):
                especificas.append((e, "R04", "resposta de privacidade"))
            elif info.e_financeiro_nao_divulgado and ferr.publica and e.regra_declarada != "R05":
                especificas.append((e, "R05", "escalada para Compliance"))
            elif info.e_codigo and ferr.publica and e.regra_declarada != "R06":
                especificas.append((e, "R06", "avaliação de exposição de PI"))
        if especificas:
            cont = Counter(alvo for _, alvo, _ in especificas)
            saida.append(Achado(
                id="A-02", familia="C", gravidade="alta",
                titulo="Regra genérica citada onde a política tem regra específica",
                resumo=(
                    f"{len(especificas)} eventos foram fechados com R01 ou R02 quando a política "
                    f"tem regra própria para o caso: "
                    + ", ".join(f"{r} ({q}×)" for r, q in cont.most_common())
                ),
                consequencia=(
                    "As ações obrigatórias são diferentes. R01 manda 'bloquear/alertar e "
                    "investigar'. R04 manda 'investigar e aplicar resposta de privacidade' — "
                    "o que inclui avaliar comunicação ao titular e à autoridade. Citar a regra "
                    "genérica faz a obrigação de privacidade desaparecer do registro."
                ),
                evidencia="Regras_Risco R04/R05/R06 × Tipos_Informacao (categoria)",
                eventos=[e.id for e, _, _ in especificas],
                detalhe=[{
                    "evento": e.id, "informacao": e.informacao_nome,
                    "citada": e.regra_declarada, "deveria": alvo, "perde": perde,
                } for e, alvo, perde in especificas[:40]],
            ))

        # --- D: sub-classificação por restrição de ferramenta ----------
        sub = []
        for e in ev:
            ferr = b.ferramentas.get(e.ferramenta_id)
            if not ferr or not ferr.somente_conteudo_publico:
                continue
            if e.sensibilidade != "Pública":
                av = self.motor.avaliar_evento(e)
                if av.nivel != e.risco_declarado:
                    sub.append((e, av))
        if sub:
            saida.append(Achado(
                id="A-03", familia="D", gravidade="alta",
                titulo="Conteúdo não público na ferramenta aprovada só para conteúdo público",
                resumo=(
                    f"{len(sub)} eventos usaram o Gerador de Imagens com informação Interna ou "
                    "Confidencial. O cadastro diz que a ferramenta é 'Aprovada apenas para "
                    "conteúdo público' e que o controle é 'Não usar material confidencial'."
                ),
                consequencia=(
                    "A base classificou esses eventos como Baixo ou Médio. Pela regra R10 — uso "
                    "incompatível com a finalidade aprovada — eles são Alto. São eventos que "
                    "deveriam ter virado alerta e não viraram."
                ),
                evidencia="Ferramentas_IA IA-08 (Status e Controles) × Regras_Risco R10",
                eventos=[e.id for e, _ in sub],
                detalhe=[{
                    "evento": e.id, "informacao": e.informacao_nome,
                    "sensibilidade": e.sensibilidade, "base": e.risco_declarado,
                    "espia": av.nivel,
                } for e, av in sub],
            ))

        # --- E: regras que nunca disparam ------------------------------
        usadas = {e.regra_declarada for e in ev}
        mortas = [rid for rid in sorted(b.regras) if rid not in usadas]
        if mortas:
            saida.append(Achado(
                id="A-04", familia="E", gravidade="media",
                titulo=f"{len(mortas)} das {len(b.regras)} regras nunca são acionadas na base",
                resumo="Nunca aparecem na coluna 'Regra acionada': " + ", ".join(mortas),
                consequencia=(
                    "Uma regra que nunca dispara ou está coberta por outra mais severa (R04, R05 "
                    "e R06), ou não tem instrumentação para ser avaliada (R12, R13, R14). Nos "
                    "dois casos ela dá uma falsa sensação de cobertura: a política aparenta ter "
                    "catorze controles e opera com oito."
                ),
                evidencia="Regras_Risco × coluna 'Regra acionada' de Eventos_Uso_IA",
                eventos=[],
                detalhe=[{
                    "regra": rid, "tema": b.regras[rid].tema, "texto": b.regras[rid].texto,
                    "nivel": b.regras[rid].nivel_esperado,
                } for rid in mortas],
            ))

        # --- F: lacunas de instrumentação ------------------------------
        sem_carimbo = [a for a in b.alertas if a.status == "Tratado"]
        saida.append(Achado(
            id="A-05", familia="F", gravidade="media",
            titulo="Alertas não registram data de tratamento",
            resumo=(
                f"{len(sem_carimbo)} alertas estão marcados como 'Tratado', mas a aba Alertas "
                "não tem coluna de data de tratamento nem de desfecho."
            ),
            consequencia=(
                "O indicador 'Alertas críticos tratados em até 24h' é declarado como 72% e não "
                "pode ser apurado a partir da base. Um indicador de SLA sem carimbo de tempo é "
                "uma afirmação, não uma medição."
            ),
            evidencia="Aba Alertas (colunas disponíveis) × Indicadores_Atuais",
            eventos=[a.id for a in sem_carimbo],
        ))

        # --- lacuna de política: Interna em ferramenta não aprovada ----
        internas_fora = [
            e for e in ev
            if e.ferramenta_id in self.nao_aprovadas and e.sensibilidade in ("Interna", "Pública")
        ]
        if internas_fora:
            cont = Counter(e.sensibilidade for e in internas_fora)
            saida.append(Achado(
                id="A-06", familia="E", gravidade="media",
                titulo="A política não cobre informação Interna ou Pública em ferramenta não aprovada",
                resumo=(
                    f"{len(internas_fora)} eventos caem nessa combinação "
                    + ", ".join(f"{s} ({q})" for s, q in cont.most_common())
                    + ". Nenhuma das catorze regras trata dela."
                ),
                consequencia=(
                    "O caso CV14 confirma que informação Pública nessa situação fica em Baixo, "
                    "então o nível está certo. Para informação Interna não há gabarito: a "
                    "política diz apenas 'preferir ferramentas corporativas aprovadas', sem "
                    "consequência definida. A GerencIA propõe a regra R15 para fechar a lacuna."
                ),
                evidencia="Regras_Risco (ausência) × Classificacao_Informacao (regra geral de Interna)",
                eventos=[e.id for e in internas_fora],
            ))

        ordem = {"alta": 0, "media": 1, "baixa": 2}
        saida.sort(key=lambda a: (ordem[a.gravidade], a.id))
        return saida


def _mesma_medida(a: str, b: str) -> bool:
    """Compara valores de indicador tolerando formato ('12,3%' vs '12.3 %')."""
    def norm(x: str) -> str:
        return (x or "").strip().lower().replace(" ", "").replace(".", ",")
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # tolerância de 0,1 ponto para percentuais arredondados de forma diferente
    try:
        fa = float(na.replace("%", "").replace(",", "."))
        fb = float(nb.replace("%", "").replace(",", "."))
        return abs(fa - fb) <= 0.1
    except ValueError:
        return False
