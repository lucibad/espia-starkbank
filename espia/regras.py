"""
EspIA — motor das regras oficiais R01 a R14.

As catorze regras vêm da aba `Regras_Risco` da planilha do desafio. Elas são
declarativas e, como toda política escrita em linguagem natural, **se sobrepõem
e se contradizem em alguns pontos**. Um motor precisa resolver isso de forma
explícita, porque é essa resolução que Compliance vai auditar.

Três decisões de precedência, e o motivo de cada uma:

1. **Rastreabilidade antes de tudo.** R14 (log incompleto) e R13 (sem
   classificação) são avaliadas primeiro. Se não dá para confiar em quem, onde
   ou o quê, classificar risco é inventar. O resultado é REVISAR — que é o que
   o caso CV13 espera.

2. **A regra mais específica descreve melhor; a mais severa define o nível.**
   Código-fonte confidencial numa IA pública dispara R01 (Crítico) e R06 (Alto)
   ao mesmo tempo. O nível é o mais severo — Crítico. Mas as duas ficam
   registradas, porque R06 explica *o que* está em jogo: exposição de
   propriedade intelectual.

3. **Contexto é evidência, não agravante.** R12 (horário fora do padrão) nunca
   eleva o nível sozinho — é o que a própria regra diz. Ela entra na cadeia de
   evidências e ajuda quem investiga.

O motor devolve, para cada evento, o nível, a regra principal, todas as regras
aplicáveis e a explicação de cada uma.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordem de severidade. REVISAR não é um nível de risco: é a recusa de atribuir
# um, quando não há base para tanto.
SEVERIDADE = {"Baixo": 0, "Médio": 1, "Alto": 2, "Crítico": 3}
NIVEIS = ["Crítico", "Alto", "Médio", "Baixo"]

# A ordem de precedência, declarada. Quando mais de uma regra se aplica, o NÍVEL
# é o da mais severa e a REGRA PRINCIPAL é a primeira desta lista entre as que
# empataram na severidade.
#
# R05, R04 e R06 vêm antes de R01 e R02 de propósito: são as regras específicas.
# Elas dão o mesmo nível que as genéricas, mas a ação obrigatória é outra — R04
# manda aplicar resposta de privacidade, R01 manda apenas investigar. Citar a
# genérica faz a obrigação de privacidade sumir do registro, que é exatamente o
# defeito que a auditoria encontrou na base (achado A-02).
PRECEDENCIA = [
    "R14",  # rastreabilidade insuficiente
    "R13",  # classificação ausente
    "R03",  # credencial, em qualquer ferramenta
    "R05",  # financeiro não divulgado em pública
    "R04",  # dado pessoal em pública
    "R06",  # código confidencial em pública
    "R02",  # crítica em não aprovada
    "R01",  # confidencial em não aprovada
    "R11",  # volume elevado
    "R10",  # crítica em aprovada, ou fora da finalidade
    "R07",  # confidencial em aprovada
    "R09",  # interna em aprovada
    "R08",  # pública em aprovada
    "R12",  # horário — contexto, nunca eleva sozinho
]

# Texto curto de cada posição, para o painel mostrar a ordem sem repetir a lista.
DESCRICAO_PRECEDENCIA = {
    "R14": "rastreabilidade insuficiente → REVISAR",
    "R13": "classificação ausente → REVISAR",
    "R03": "credencial, em qualquer ferramenta → Crítico",
    "R05": "financeiro não divulgado em pública → Crítico",
    "R04": "dado pessoal em pública → Crítico (aciona resposta de privacidade)",
    "R06": "código confidencial em pública → Alto",
    "R02": "crítica em não aprovada → Crítico",
    "R01": "confidencial em não aprovada → Crítico",
    "R11": "volume elevado → Alto",
    "R10": "crítica em aprovada, ou fora da finalidade → Alto",
    "R07": "confidencial em aprovada → Médio",
    "R09": "interna em aprovada → Baixo",
    "R08": "pública em aprovada → Baixo",
    "R12": "horário — contexto, nunca eleva sozinho",
}

# Limite de volume para R11. A base usa 10 itens; deixado nomeado para que
# Compliance possa mexer sem procurar no meio do código.
LIMITE_VOLUME = 10

SENSIVEIS = {"Confidencial", "Crítica"}


@dataclass
class Achado:
    """Uma regra que se aplicou ao evento."""

    regra: str
    nivel: str          # "Crítico" | "Alto" | "Médio" | "Baixo" | "REVISAR"
    titulo: str
    motivo: str
    acao: str
    contextual: bool = False   # entra como evidência, não eleva o nível


@dataclass
class Avaliacao:
    nivel: str
    regra_principal: str
    achados: list[Achado] = field(default_factory=list)
    lacuna: str | None = None   # a política não cobre esta combinação

    @property
    def regras(self) -> list[str]:
        return [a.regra for a in self.achados]

    @property
    def evidencia(self) -> str:
        return "; ".join(a.titulo for a in self.achados)


class MotorRegras:
    """Aplica as regras oficiais a um evento da base."""

    def __init__(self, base):
        self.base = base
        self.regras = base.regras

    def _r(self, rid: str) -> tuple[str, str]:
        r = self.regras.get(rid)
        return (r.nivel_esperado if r else "Médio", r.acao_esperada if r else "")

    # -----------------------------------------------------------------

    def avaliar(
        self,
        *,
        ferramenta_id: str,
        informacao_id: str,
        sensibilidade: str,
        qtd_itens: int = 1,
        fora_horario: bool = False,
        rastreavel: bool = True,
    ) -> Avaliacao:
        achados: list[Achado] = []
        lacuna: str | None = None

        ferr = self.base.ferramentas.get(ferramenta_id)
        info = self.base.tipos.get(informacao_id)
        sens = (sensibilidade or "").strip()

        # --- 1. rastreabilidade ---------------------------------------
        if not rastreavel or ferr is None:
            nivel, acao = self._r("R14")
            achados.append(Achado(
                "R14", "REVISAR", "Rastreabilidade insuficiente",
                "O evento não tem usuário, ferramenta ou data confiáveis. Sem isso não é "
                "possível atribuir risco — e atribuir mesmo assim seria inventar.",
                acao or "Sinalizar baixa rastreabilidade",
            ))
            return Avaliacao("REVISAR", "R14", achados)

        if info is None or sens not in ("Pública", "Interna", "Confidencial", "Crítica"):
            nivel, acao = self._r("R13")
            achados.append(Achado(
                "R13", "REVISAR", "Classificação ausente ou insuficiente",
                "O conteúdo não tem classificação suficiente para decidir. A política manda "
                "revisar, não arbitrar um nível.",
                acao or "REVISAR",
            ))
            return Avaliacao("REVISAR", "R13", achados)

        aprovada = ferr.aprovada

        # --- 2. credencial, em qualquer ferramenta --------------------
        if info.e_credencial:
            _, acao = self._r("R03")
            achados.append(Achado(
                "R03", "Crítico", "Credencial ou segredo identificado",
                f"{info.nome} foi inserido em {ferr.nome}. A regra R03 não abre exceção para "
                "ferramenta aprovada — o caso CV12 confirma isso. A credencial deve ser "
                "considerada comprometida.",
                acao,
            ))

        # --- 3. informação em ferramenta não aprovada -----------------
        if not aprovada:
            if sens == "Crítica":
                _, acao = self._r("R02")
                achados.append(Achado(
                    "R02", "Crítico", "Informação crítica em ferramenta não aprovada",
                    f"{info.nome} ({sens}) em {ferr.nome}, que a governança classifica como "
                    f"'{ferr.status}'. Sem contrato corporativo, não há controle de retenção "
                    "nem garantia sobre uso do conteúdo.",
                    acao,
                ))
            elif sens == "Confidencial":
                _, acao = self._r("R01")
                achados.append(Achado(
                    "R01", "Crítico", "Informação confidencial em ferramenta não aprovada",
                    f"{info.nome} ({sens}) em {ferr.nome} ('{ferr.status}').",
                    acao,
                ))

            # regras específicas que explicam POR QUE é grave — e que mudam a resposta
            if info.e_financeiro_nao_divulgado and ferr.publica:
                _, acao = self._r("R05")
                achados.append(Achado(
                    "R05", "Crítico", "Resultado financeiro não divulgado em ferramenta pública",
                    "Informação financeira ainda não divulgada ao mercado. Além do risco de "
                    "vazamento, há exposição a uso indevido de informação privilegiada.",
                    acao,
                ))
            if info.e_dado_pessoal and ferr.publica:
                _, acao = self._r("R04")
                achados.append(Achado(
                    "R04", "Crítico", "Dado pessoal identificável em IA pública",
                    f"{info.nome} é dado pessoal. A resposta não é só de segurança: aciona o "
                    "procedimento de privacidade, com avaliação de comunicação ao titular e "
                    "à autoridade.",
                    acao,
                ))
            if info.e_codigo and ferr.publica and sens == "Confidencial":
                _, acao = self._r("R06")
                achados.append(Achado(
                    "R06", "Alto", "Código confidencial em ferramenta pública",
                    "R06 prevê nível Alto, mas R01 já classifica o mesmo fato como Crítico. "
                    "Prevalece o mais severo; R06 fica registrada porque indica o que precisa "
                    "ser avaliado: exposição de propriedade intelectual.",
                    acao,
                ))

            # lacuna: a política não tem regra para Interna/Pública em não aprovada
            if sens in ("Interna", "Pública"):
                lacuna = (
                    f"Informação {sens} em ferramenta não aprovada não tem regra própria na "
                    "política. R08 e R09 falam explicitamente em 'ferramenta aprovada'."
                )
                if sens == "Pública":
                    _, acao = self._r("R08")
                    achados.append(Achado(
                        "R08", "Baixo", "Informação pública (ferramenta não aprovada)",
                        "O caso CV14 confirma que informação pública em ferramenta não aprovada "
                        "fica em Baixo. Mas a regra citada, R08, pressupõe ferramenta aprovada — "
                        "a classificação está certa e a citação, não.",
                        acao,
                    ))
                else:
                    _, acao = self._r("R09")
                    achados.append(Achado(
                        "R09", "Baixo", "Informação interna (ferramenta não aprovada)",
                        "Sem regra própria na política. R09 pressupõe ferramenta aprovada; "
                        "aplicá-la aqui mantém o nível Baixo mas registra uma justificativa "
                        "que não corresponde ao fato.",
                        acao,
                    ))

        # --- 4. ferramenta aprovada -----------------------------------
        else:
            if qtd_itens >= LIMITE_VOLUME and sens in SENSIVEIS:
                _, acao = self._r("R11")
                achados.append(Achado(
                    "R11", "Alto", f"Volume elevado — {qtd_itens} itens",
                    f"{qtd_itens} itens de informação {sens} num único uso. Volume desse porte "
                    "não é consulta pontual: é transferência de acervo.",
                    acao,
                ))

            if sens == "Crítica":
                _, acao = self._r("R10")
                achados.append(Achado(
                    "R10", "Alto", "Informação crítica em ambiente aprovado",
                    f"{info.nome} ({sens}) em {ferr.nome}. Ambiente aprovado reduz a exposição, "
                    "mas informação crítica exige finalidade validada e registro — a política "
                    "não a libera por padrão em nenhuma ferramenta.",
                    acao,
                ))
            elif sens == "Confidencial":
                _, acao = self._r("R07")
                achados.append(Achado(
                    "R07", "Médio", "Confidencial em ferramenta aprovada",
                    f"Uso previsto pela política: {info.nome} em {ferr.nome}, que é "
                    f"'{ferr.status}'. Registrar e validar finalidade e acesso.",
                    acao,
                ))
            elif sens == "Interna":
                _, acao = self._r("R09")
                achados.append(Achado(
                    "R09", "Baixo", "Informação interna em ferramenta aprovada",
                    f"{info.nome} em ambiente aprovado. Permitido conforme finalidade.",
                    acao,
                ))
            else:  # Pública
                _, acao = self._r("R08")
                achados.append(Achado(
                    "R08", "Baixo", "Informação pública em ferramenta aprovada",
                    f"{info.nome} em {ferr.nome}. Registrar sem alerta.",
                    acao,
                ))

            # restrição específica do Gerador de Imagens
            if ferr.somente_conteudo_publico and sens != "Pública":
                _, acao = self._r("R10")
                achados.append(Achado(
                    "R10", "Alto", "Uso fora da finalidade aprovada da ferramenta",
                    f"{ferr.nome} é aprovada apenas para conteúdo público, e o conteúdo é "
                    f"{sens}.",
                    acao,
                ))

        # --- 5. contexto (nunca eleva sozinho) ------------------------
        if fora_horario:
            _, acao = self._r("R12")
            achados.append(Achado(
                "R12", "Baixo", "Uso fora do horário padrão",
                "Registrado fora do horário comercial ou em fim de semana. A própria R12 diz "
                "que isso não aumenta o risco sozinho — entra como contexto para quem investiga.",
                acao, contextual=True,
            ))

        # --- desfecho ---------------------------------------------------
        # O nível é o da regra mais severa; a regra principal é a primeira da
        # ordem de precedência entre as que empataram nessa severidade.
        def ordem(a: Achado) -> int:
            try:
                return PRECEDENCIA.index(a.regra)
            except ValueError:
                return len(PRECEDENCIA)

        elegiveis = [a for a in achados if not a.contextual]
        if not elegiveis:
            return Avaliacao("Baixo", "—", achados, lacuna)

        pior = max(SEVERIDADE[a.nivel] for a in elegiveis)
        nivel = next(n for n, s in SEVERIDADE.items() if s == pior)
        principal = min((a for a in elegiveis if SEVERIDADE[a.nivel] == pior), key=ordem)

        achados.sort(key=lambda a: (a.contextual, -SEVERIDADE.get(a.nivel, 0), ordem(a)))
        return Avaliacao(nivel, principal.regra, achados, lacuna)

    # -----------------------------------------------------------------

    def avaliar_evento(self, evento) -> Avaliacao:
        return self.avaliar(
            ferramenta_id=evento.ferramenta_id,
            informacao_id=evento.informacao_id,
            sensibilidade=evento.sensibilidade,
            qtd_itens=evento.qtd_itens,
            fora_horario=evento.fora_horario,
            rastreavel=evento.rastreavel,
        )


# ---------------------------------------------------------------------
# Propostas de política — NÃO são regras da planilha
# ---------------------------------------------------------------------

PROPOSTAS = [
    {
        "id": "R15",
        "tema": "Lacuna — ferramenta não aprovada",
        "regra": "Informação Interna em ferramenta de IA não aprovada",
        "nivel": "Médio",
        "acao": "Registrar e orientar o colaborador; contabilizar no indicador de uso não aprovado",
        "porque": (
            "A política diz que informação Interna deve 'preferir ferramentas corporativas "
            "aprovadas', mas não existe regra para quando isso não acontece. Hoje esses eventos "
            "recebem R09, cujo texto pressupõe ferramenta aprovada."
        ),
    },
    {
        "id": "R16",
        "tema": "Lacuna — citação de regra",
        "regra": "Toda regra citada deve ser compatível com o fato registrado",
        "nivel": "—",
        "acao": "Bloquear o fechamento do evento quando a regra citada contradiz os campos",
        "porque": (
            "Um evento em ferramenta não aprovada não pode citar uma regra cujo texto exige "
            "ferramenta aprovada. O nível pode estar certo e a trilha de auditoria, errada."
        ),
    },
    {
        "id": "R17",
        "tema": "Tratamento de alerta",
        "regra": "Todo alerta deve registrar data de tratamento e desfecho",
        "nivel": "—",
        "acao": "Campo obrigatório no workflow de alertas",
        "porque": (
            "O indicador 'Alertas críticos tratados em até 24h' é declarado como 72%, mas a "
            "base não tem carimbo de tratamento — o número não é apurável a partir dela."
        ),
    },
]
