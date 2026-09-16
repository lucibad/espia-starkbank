"""
EspIA — Motor de risco com cadeia de evidências.

O último requisito do desafio é o mais exigente: "disponibilizar evidências
que permitam compreender por que determinada utilização foi classificada
como risco". Uma caixa-preta que devolve "risco alto" não atende.

Aqui o score é uma fórmula legível, declarada no politica.yaml, e cada
evento carrega a lista de fatores que o construíram — com a contribuição
numérica de cada um. Compliance consegue auditar; a pessoa acusada consegue
contestar.

    score = peso_classificacao × fator_ferramenta × Π(multiplicadores)
            + Σ(agravantes) + Σ(atenuantes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .detectores import Deteccao, TIPOS_PII

# Rótulos legíveis — a evidência é lida por Compliance e pela pessoa avaliada,
# então nenhuma chave interna com underscore pode vazar para o texto.
ROTULO_TIER = {
    "corporativa": "corporativa",
    "homologada": "homologada",
    "tolerada": "tolerada — aceita só para informação pública ou interna",
    "nao_homologada": "não homologada",
}
ROTULO_CANAL = {
    "gateway": "gateway de IA da empresa",
    "extensao": "extensão de navegador",
    "declarativo": "registro declarativo",
    "api": "API interna",
}
# "Informação Crítico" não existe em português — a concordância importa
# num documento que pode virar peça de processo disciplinar.
CLASSIFICACAO_FEM = {
    "publico": "pública", "interno": "interna",
    "confidencial": "confidencial", "critico": "crítica",
}


@dataclass
class Fator:
    """Um item da cadeia de evidências."""

    codigo: str
    rotulo: str
    tipo: str           # "base" | "multiplicador" | "agravante" | "atenuante"
    valor: float        # multiplicador (×) ou pontos (+/-)
    contribuicao: float  # quantos pontos este fator acrescentou ao score final
    explicacao: str
    marcos: list[str] = field(default_factory=list)


@dataclass
class Avaliacao:
    score: float
    nivel: str
    rotulo: str
    acao: str
    fatores: list[Fator]

    def resumo(self) -> str:
        principais = sorted(self.fatores, key=lambda f: -abs(f.contribuicao))[:3]
        return " · ".join(f.rotulo for f in principais)


class MotorRisco:
    def __init__(self, politica: dict):
        self.politica = politica
        self.mr = politica["motor_risco"]
        self.classificacao = politica["classificacao"]
        self.ferramentas = {f["id"]: f for f in politica["ferramentas_ia"]}
        self.categorias = politica["categorias_informacao"]
        self.niveis = sorted(self.mr["niveis"], key=lambda n: -n["min"])

    # -----------------------------------------------------------------
    def avaliar(
        self,
        *,
        ts: datetime,
        ferramenta_id: str,
        canal: str,
        finalidade: str | None,
        finalidade_aprovada: bool,
        mascaramento_aceito: bool,
        tamanho_texto: int,
        correspondencias: list,        # list[Correspondencia]
        ativos: dict,                  # id -> Ativo
        deteccoes: list[Deteccao],
        eventos_similares_7d: int,
    ) -> Avaliacao:
        fatores: list[Fator] = []
        ferramenta = self.ferramentas.get(ferramenta_id, {})

        # --- BASE: a classificação mais alta entre os ativos casados -----
        if correspondencias:
            classificacoes = [ativos[c.ativo_id].classificacao for c in correspondencias if c.ativo_id in ativos]
            pior = max(classificacoes, key=lambda c: self.classificacao[c]["peso"])
            peso_base = self.classificacao[pior]["peso"]
            ativo_topo = ativos[correspondencias[0].ativo_id]
            marcos = self.categorias.get(ativo_topo.categoria, {}).get("marcos", [])
            nome_pior = ativos[
                next(c.ativo_id for c in correspondencias if ativos[c.ativo_id].classificacao == pior)
            ].nome
            n = len(correspondencias)
            quantos = "1 ativo" if n == 1 else f"{n} ativos"
            explicacao = (
                f"O conteúdo enviado corresponde a {quantos} do acervo. "
                f"O mais sensível é \"{nome_pior}\", classificado como "
                f"{self.classificacao[pior]['rotulo']} "
                f"(correspondência de {correspondencias[0].score:.0%}, "
                f"confiança {'alta' if correspondencias[0].confianca == 'alta' else 'média'})."
            )
        elif any(d.tipo in TIPOS_PII for d in deteccoes):
            pior = "confidencial"
            peso_base = self.classificacao["confidencial"]["peso"]
            marcos = ["LGPD"]
            explicacao = (
                "Nenhum ativo do acervo foi reconhecido, mas o conteúdo contém dado pessoal "
                "identificável. Tratado como Confidencial por padrão."
            )
        else:
            pior = "publico"
            peso_base = self.classificacao["publico"]["peso"]
            marcos = []
            explicacao = "Nenhum ativo do acervo nem dado pessoal reconhecido no conteúdo."

        fator_ferramenta = float(ferramenta.get("fator_risco", 2.5))
        score = peso_base * fator_ferramenta

        fatores.append(
            Fator(
                codigo="base_classificacao",
                rotulo=f"Informação {CLASSIFICACAO_FEM.get(pior, self.classificacao[pior]['rotulo'].lower())}",
                tipo="base",
                valor=peso_base,
                # Só o peso da classificação. O efeito da ferramenta é
                # contabilizado no fator seguinte, para não contar duas vezes.
                contribuicao=float(peso_base),
                explicacao=explicacao,
                marcos=marcos,
            )
        )
        fatores.append(
            Fator(
                codigo="fator_ferramenta",
                rotulo=f"{ferramenta.get('nome', ferramenta_id)} — ferramenta "
                       f"{ROTULO_TIER.get(ferramenta.get('tier'), 'não catalogada').split(' —')[0]}",
                tipo="multiplicador",
                valor=fator_ferramenta,
                contribuicao=round(peso_base * (fator_ferramenta - 1), 2),
                explicacao=(
                    f"A política classifica esta ferramenta como "
                    f"{ROTULO_TIER.get(ferramenta.get('tier'), 'não catalogada')}. "
                    + (ferramenta.get("observacao") or
                       f"Jurisdição: {ferramenta.get('jurisdicao', 'desconhecida')}. "
                       f"Retenção declarada: {ferramenta.get('retencao_dias', 'não informada')} dias.")
                ),
            )
        )

        # --- MULTIPLICADORES -------------------------------------------
        mult = self.mr["multiplicadores"]

        def aplicar(codigo: str, rotulo: str, explicacao: str, marcos_: list[str] | None = None):
            nonlocal score
            m = mult[codigo]
            antes = score
            score *= m
            fatores.append(
                Fator(codigo, rotulo, "multiplicador", m, round(score - antes, 2), explicacao, marcos_ or [])
            )

        if ferramenta.get("treina_com_dados"):
            aplicar(
                "treina_com_dados",
                "Fornecedor treina modelo com os dados enviados",
                "Os termos da ferramenta permitem uso do conteúdo para treinamento. "
                "O dado deixa de ser recuperável — não há como pedir exclusão do que já virou peso do modelo.",
            )

        if ferramenta.get("jurisdicao") in ("China", "Rússia", "desconhecida"):
            aplicar(
                "jurisdicao_sem_adequacao",
                f"Transferência internacional — {ferramenta.get('jurisdicao')}",
                "Transferência para jurisdição sem decisão de adequação reconhecida, "
                "sem cláusulas contratuais padrão nem garantias equivalentes.",
                ["LGPD"],
            )

        fim_de_semana = ts.weekday() >= 5
        if ts.hour >= 22 or ts.hour < 6 or fim_de_semana:
            aplicar(
                "fora_horario",
                "Fora do horário comercial",
                f"Uso registrado em {ts.strftime('%d/%m/%Y %H:%M')}"
                + (" (fim de semana)." if fim_de_semana else " (madrugada).")
                + " Não é irregular por si só, mas reduz a chance de revisão por pares.",
            )

        if canal in ("extensao", "declarativo"):
            aplicar(
                "canal_nao_gerenciado",
                "Canal fora do gateway corporativo",
                f"Capturado por {ROTULO_CANAL.get(canal, canal)} — o tráfego não passou pelo gateway "
                "de IA da empresa, logo não houve filtro, log de resposta nem controle de retenção.",
            )

        if tamanho_texto > 8000:
            aplicar(
                "volume_alto",
                f"Volume alto ({tamanho_texto:,} caracteres)".replace(",", "."),
                "Volume compatível com colagem de documento inteiro, não com consulta pontual.",
            )

        if eventos_similares_7d >= 3:
            aplicar(
                "reincidencia",
                f"Reincidência — {eventos_similares_7d} usos semelhantes em 7 dias",
                "Padrão repetido com a mesma ferramenta e a mesma classe de informação. "
                "Indica processo de trabalho estabelecido, não descuido isolado.",
            )

        if finalidade is None:
            aplicar(
                "sem_finalidade_declarada",
                "Finalidade não declarada",
                "Sem finalidade registrada não é possível avaliar necessidade nem proporcionalidade — "
                "requisitos de tratamento sob a LGPD.",
                ["LGPD"],
            )

        # --- AGRAVANTES -------------------------------------------------
        agr = self.mr["agravantes"]
        total_pii = sum(d.contagem for d in deteccoes if d.tipo in TIPOS_PII)

        if total_pii >= 20:
            score += agr["pii_em_volume"]
            fatores.append(
                Fator(
                    "pii_em_volume",
                    f"{total_pii} identificadores pessoais no mesmo envio",
                    "agravante",
                    agr["pii_em_volume"],
                    float(agr["pii_em_volume"]),
                    "Volume de dado pessoal caracteriza tratamento em massa, não consulta individual. "
                    "Exige base legal própria e registro na operação de tratamento.",
                    ["LGPD"],
                )
            )

        if any(d.tipo == "cartao" for d in deteccoes):
            n = sum(d.contagem for d in deteccoes if d.tipo == "cartao")
            score += agr["dado_cartao"]
            fatores.append(
                Fator(
                    "dado_cartao",
                    f"{n} número(s) de cartão validado(s) por Luhn",
                    "agravante",
                    agr["dado_cartao"],
                    float(agr["dado_cartao"]),
                    "Dado de portador de cartão em ferramenta fora do ambiente certificado "
                    "quebra o escopo PCI DSS e é evento reportável.",
                    ["PCI_DSS"],
                )
            )

        if any(d.tipo == "credencial" for d in deteccoes):
            score += agr["credencial"]
            fatores.append(
                Fator(
                    "credencial",
                    "Credencial ou segredo de ambiente no conteúdo",
                    "agravante",
                    agr["credencial"],
                    float(agr["credencial"]),
                    "String de credencial detectada. Independente do resto, exige revogação "
                    "e rotação imediata da chave exposta.",
                    ["BCB_CIBER"],
                )
            )

        criticos = [c for c in correspondencias if c.ativo_id in ativos and ativos[c.ativo_id].classificacao == "critico"]
        if len(criticos) >= 2:
            score += agr["multiplos_ativos_criticos"]
            fatores.append(
                Fator(
                    "multiplos_ativos_criticos",
                    f"{len(criticos)} ativos críticos no mesmo envio",
                    "agravante",
                    agr["multiplos_ativos_criticos"],
                    float(agr["multiplos_ativos_criticos"]),
                    "Combinar ativos críticos amplia o dano: o conjunto revela mais do que a soma das partes.",
                )
            )

        # --- ATENUANTES -------------------------------------------------
        ate = self.mr["atenuantes"]
        if mascaramento_aceito:
            score += ate["mascaramento_aceito"]
            fatores.append(
                Fator(
                    "mascaramento_aceito",
                    "Colaborador aceitou enviar versão mascarada",
                    "atenuante",
                    ate["mascaramento_aceito"],
                    float(ate["mascaramento_aceito"]),
                    "A extensão ofereceu a versão anonimizada no momento do envio e a pessoa aceitou. "
                    "O identificador pessoal não saiu da empresa.",
                )
            )
        if finalidade_aprovada:
            score += ate["finalidade_aprovada"]
            fatores.append(
                Fator(
                    "finalidade_aprovada",
                    "Caso de uso pré-aprovado pelo Comitê de IA",
                    "atenuante",
                    ate["finalidade_aprovada"],
                    float(ate["finalidade_aprovada"]),
                    "Finalidade consta na lista de usos aprovados para esta classe de informação.",
                )
            )

        score = max(0.0, round(score, 2))

        for n in self.niveis:
            if score >= n["min"]:
                return Avaliacao(score, n["nivel"], n["rotulo"], n["acao"], fatores)

        ultimo = self.niveis[-1]
        return Avaliacao(score, ultimo["nivel"], ultimo["rotulo"], ultimo["acao"], fatores)
