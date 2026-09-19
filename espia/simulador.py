"""
GerencIA — Simulador da rede corporativa.

Gera 90 dias de atividade de IA numa instituição financeira fictícia, com
os três canais de captura da arquitetura híbrida:

  gateway    — tráfego corporativo que passa pelo proxy de IA da empresa
  extensao   — colagem detectada no navegador do colaborador (shadow AI)
  declarativo— registro manual feito pelo próprio colaborador
  api        — chamada direta de aplicação interna ao provedor de LLM

E os dois sinais de descoberta:

  proxy_dns  — log do proxy de saída / resolvedor DNS corporativo
  oauth      — concessões de aplicativo de terceiro no provedor de identidade

TODOS OS DADOS SÃO SINTÉTICOS. Nenhuma pessoa, cliente ou transação real.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .acervo import ACERVO, Ativo

SEMENTE = 20260913
DIAS = 90
DATA_FIM = datetime(2026, 9, 12, 23, 59)
DATA_INICIO = DATA_FIM - timedelta(days=DIAS)


# ---------------------------------------------------------------------
# Pessoas — nomes fictícios
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Colaborador:
    id: str
    nome: str
    area: str
    cargo: str
    senioridade: str
    perfil: str  # "disciplinado" | "pragmatico" | "sob_pressao"


COLABORADORES: list[Colaborador] = [
    Colaborador("COL-01", "Helena Duarte", "Engenharia", "Engenheira de Software Sênior", "senior", "pragmatico"),
    Colaborador("COL-02", "Rafael Antunes", "Engenharia", "Engenheiro de Plataforma", "pleno", "pragmatico"),
    Colaborador("COL-03", "Marina Sales", "Engenharia", "Tech Lead", "senior", "disciplinado"),
    Colaborador("COL-04", "Tomás Ferraz", "Engenharia", "Engenheiro de Dados", "pleno", "sob_pressao"),
    Colaborador("COL-05", "Beatriz Nogueira", "Produto", "Product Manager", "senior", "pragmatico"),
    Colaborador("COL-06", "Caio Villela", "Produto", "Product Designer", "pleno", "pragmatico"),
    Colaborador("COL-07", "Luana Peixoto", "Risco e Crédito", "Analista de Risco Sênior", "senior", "sob_pressao"),
    Colaborador("COL-08", "Eduardo Bastos", "Risco e Crédito", "Cientista de Dados", "pleno", "pragmatico"),
    Colaborador("COL-09", "Priscila Amaral", "Compliance", "Analista de PLD/FT", "senior", "disciplinado"),
    Colaborador("COL-10", "Gustavo Rezende", "Compliance", "Coordenador de Compliance", "senior", "disciplinado"),
    Colaborador("COL-11", "Isabela Moraes", "Jurídico", "Advogada Societária", "senior", "pragmatico"),
    Colaborador("COL-12", "Otávio Lins", "Jurídico", "Advogado Contratual", "pleno", "sob_pressao"),
    Colaborador("COL-13", "Camila Furtado", "Comercial", "Executiva de Contas Enterprise", "senior", "sob_pressao"),
    Colaborador("COL-14", "Daniel Corrêa", "Comercial", "Analista de Pré-vendas", "junior", "sob_pressao"),
    Colaborador("COL-15", "Renata Quintela", "Comercial", "Gerente Comercial", "senior", "pragmatico"),
    Colaborador("COL-16", "Sérgio Pacheco", "Financeiro", "Analista de FP&A", "pleno", "pragmatico"),
    Colaborador("COL-17", "Aline Castro", "Financeiro", "Controller", "senior", "disciplinado"),
    Colaborador("COL-18", "Vitor Sampaio", "People", "Business Partner de People", "pleno", "pragmatico"),
    Colaborador("COL-19", "Fernanda Rios", "People", "Analista de Remuneração", "pleno", "disciplinado"),
    Colaborador("COL-20", "Paulo Menezes", "Segurança da Informação", "Analista de SegInfo", "senior", "disciplinado"),
    Colaborador("COL-21", "Larissa Bittencourt", "Atendimento", "Especialista de Suporte", "pleno", "pragmatico"),
    Colaborador("COL-22", "Henrique Vasques", "Atendimento", "Coordenador de Suporte", "senior", "pragmatico"),
]

COLABORADORES_POR_ID = {c.id: c for c in COLABORADORES}

# Qual área naturalmente toca qual classe de ativo.
AFINIDADE_AREA: dict[str, list[str]] = {
    "Engenharia": ["ATV-001", "ATV-002", "ATV-010", "ATV-023", "ATV-026", "ATV-035"],
    "Produto": ["ATV-001", "ATV-002", "ATV-011", "ATV-022", "ATV-010"],
    "Risco e Crédito": ["ATV-024", "ATV-031", "ATV-025", "ATV-030"],
    "Compliance": ["ATV-011", "ATV-032", "ATV-034", "ATV-024"],
    "Jurídico": ["ATV-020", "ATV-024", "ATV-036", "ATV-011"],
    "Comercial": ["ATV-021", "ATV-030", "ATV-022", "ATV-001"],
    "Financeiro": ["ATV-025", "ATV-036", "ATV-021", "ATV-033"],
    "People": ["ATV-012", "ATV-033", "ATV-011"],
    "Segurança da Informação": ["ATV-011", "ATV-026", "ATV-035", "ATV-010"],
    "Atendimento": ["ATV-001", "ATV-010", "ATV-012"],
}

# Ferramentas plausíveis por perfil de colaborador.
FERRAMENTAS_POR_PERFIL: dict[str, list[tuple[str, float]]] = {
    "disciplinado": [
        ("chatgpt_enterprise", 0.42), ("claude_api_interna", 0.28),
        ("copilot_business", 0.14), ("gemini_workspace", 0.10), ("notion_ai", 0.06),
    ],
    "pragmatico": [
        ("chatgpt_enterprise", 0.30), ("claude_api_interna", 0.16), ("copilot_business", 0.14),
        ("gemini_workspace", 0.12), ("notion_ai", 0.08), ("chatgpt_free", 0.10),
        ("perplexity", 0.06), ("cursor_pessoal", 0.04),
    ],
    "sob_pressao": [
        ("chatgpt_enterprise", 0.28), ("chatgpt_free", 0.18), ("gemini_workspace", 0.13),
        ("perplexity", 0.10), ("deepseek", 0.045), ("tradutor_ia", 0.05),
        ("resumidor_pdf", 0.035), ("cursor_pessoal", 0.06), ("claude_api_interna", 0.12),
    ],
}

FINALIDADES = [
    ("resumir_documento", "Resumir documento longo"),
    ("revisar_texto", "Revisar redação e clareza"),
    ("gerar_codigo", "Gerar ou revisar código"),
    ("analisar_dados", "Analisar dados e encontrar padrões"),
    ("traduzir", "Traduzir conteúdo"),
    ("gerar_apresentacao", "Estruturar apresentação"),
    ("responder_cliente", "Redigir resposta a cliente"),
    ("pesquisar", "Pesquisar assunto técnico ou regulatório"),
    (None, None),  # sem finalidade declarada
]

# Conteúdo genérico, sem correspondência com o acervo — a maior parte do
# uso real de IA numa empresa é assim, e a ferramenta precisa não gritar.
PROMPTS_NEUTROS = [
    "Explique a diferença entre idempotência e atomicidade em sistemas distribuídos com exemplos práticos.",
    "Me ajude a escrever uma mensagem educada recusando um convite para participar de um painel.",
    "Quais são boas práticas de indexação em bancos relacionais para consultas com filtro por data e status.",
    "Resuma em três parágrafos o conceito de open finance para uma audiência não técnica.",
    "Sugira uma estrutura de apresentação de quinze minutos sobre cultura de engenharia.",
    "Como funciona o algoritmo de consenso Raft e quando ele é preferível a Paxos.",
    "Reescreva este parágrafo deixando o tom mais direto e menos formal, sem perder precisão.",
    "Quais métricas fazem sentido para acompanhar a saúde de uma equipe de atendimento.",
    "Me explique o que muda na contabilização de receita quando o contrato tem componente variável.",
    "Faça um roteiro de entrevista estruturada para uma vaga de pessoa analista de dados.",
    "Gere casos de teste para uma função que valida datas de vencimento considerando feriados.",
    "Compare abordagens de versionamento de API e os trade-offs de cada uma.",
]

# Identificadores sintéticos que passam nos validadores — usados apenas para
# provar que o detector funciona. Não correspondem a pessoas reais.
CPFS_SINTETICOS = [
    "529.982.247-25", "111.444.777-35", "398.826.150-08", "046.622.517-10",
    "863.132.100-05", "232.410.520-71", "700.535.750-00", "088.550.510-95",
]
CNPJS_SINTETICOS = ["11.222.333/0001-81", "34.028.316/0001-03", "45.997.418/0001-53"]
CARTOES_SINTETICOS = ["4539 1488 0343 6467", "5555 5555 5555 4444", "4111 1111 1111 1111"]


@dataclass
class EventoBruto:
    """Um uso de IA como o coletor o entrega, antes do enriquecimento."""

    id: str
    ts: datetime
    colaborador_id: str
    ferramenta_id: str
    canal: str
    finalidade: str | None
    texto: str                      # descartado após fingerprint + detectores
    ativos_origem: list[str] = field(default_factory=list)  # verdade de base
    mascaramento_aceito: bool = False
    finalidade_aprovada: bool = False


@dataclass
class RegistroProxy:
    ts: datetime
    colaborador_id: str
    dominio: str
    requisicoes: int
    bytes_enviados: int
    fonte: str  # "proxy" | "dns"


@dataclass
class ConcessaoOAuth:
    ts: datetime
    colaborador_id: str
    aplicativo: str
    dominio: str
    escopos: list[str]


# ---------------------------------------------------------------------
# Construção de prompts a partir de ativos
# ---------------------------------------------------------------------


def _trecho(rng: random.Random, ativo: Ativo, fracao: tuple[float, float] = (0.35, 0.9)) -> str:
    """Recorta um pedaço contíguo do ativo, como um colar real faria."""
    palavras = ativo.texto.split()
    frac = rng.uniform(*fracao)
    tamanho = max(18, int(len(palavras) * frac))
    inicio = rng.randint(0, max(0, len(palavras) - tamanho))
    return " ".join(palavras[inicio : inicio + tamanho])


def _envelopar(rng: random.Random, corpo: str, finalidade: str | None) -> str:
    """Adiciona a instrução que o colaborador escreve em volta do trecho."""
    aberturas = {
        "resumir_documento": "Resuma os pontos principais do texto abaixo em tópicos:",
        "revisar_texto": "Revise o texto abaixo deixando mais claro e objetivo:",
        "gerar_codigo": "Com base no trecho abaixo, gere o código correspondente:",
        "analisar_dados": "Analise os dados abaixo e aponte padrões relevantes:",
        "traduzir": "Traduza o texto abaixo para inglês mantendo o tom formal:",
        "gerar_apresentacao": "Transforme o conteúdo abaixo em roteiro de slides:",
        "responder_cliente": "Escreva uma resposta ao cliente com base nas informações abaixo:",
        "pesquisar": "Com base no material abaixo, explique o contexto regulatório:",
    }
    abertura = aberturas.get(finalidade or "", rng.choice(list(aberturas.values())))
    return f"{abertura}\n\n{corpo}"


def _injetar_pii(rng: random.Random, texto: str, quantidade: int) -> str:
    linhas = []
    for _ in range(quantidade):
        cpf = rng.choice(CPFS_SINTETICOS)
        nome = rng.choice(
            ["Cliente A. Ribeiro", "Cliente M. Tavares", "Cliente J. Moreira", "Cliente P. Salgado"]
        )
        linhas.append(f"{nome} - CPF {cpf} - contato {nome.split()[-1].lower()}@exemplo.com.br")
    return texto + "\n\n" + "\n".join(linhas)


def _escolher_ponderado(rng: random.Random, opcoes: list[tuple[str, float]]) -> str:
    total = sum(p for _, p in opcoes)
    alvo = rng.uniform(0, total)
    acumulado = 0.0
    for valor, peso in opcoes:
        acumulado += peso
        if alvo <= acumulado:
            return valor
    return opcoes[-1][0]


def _timestamp(rng: random.Random, dia: datetime, sob_pressao: bool) -> datetime:
    """Distribui a hora do dia. Quem está sob pressão trabalha fora de hora."""
    if sob_pressao and rng.random() < 0.22:
        hora = rng.choice([22, 23, 0, 1, 2, 6])
    else:
        hora = rng.choices(
            [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            weights=[3, 8, 11, 12, 6, 5, 10, 12, 11, 9, 6, 4, 3],
        )[0]
    return dia.replace(hour=hora, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)


CANAL_POR_TIER = {
    "corporativa": ["gateway", "gateway", "gateway", "api"],
    "homologada": ["gateway", "gateway", "extensao"],
    "tolerada": ["extensao", "extensao", "declarativo"],
    "nao_homologada": ["extensao", "extensao", "extensao", "declarativo"],
}


# ---------------------------------------------------------------------
# Geração principal
# ---------------------------------------------------------------------


def gerar(tiers_ferramenta: dict[str, str], semente: int = SEMENTE) -> tuple[
    list[EventoBruto], list[RegistroProxy], list[ConcessaoOAuth]
]:
    rng = random.Random(semente)
    eventos: list[EventoBruto] = []
    proxy: list[RegistroProxy] = []
    oauth: list[ConcessaoOAuth] = []
    contador = 0

    acervo_por_id = {a.id: a for a in ACERVO}

    for dia_offset in range(DIAS):
        dia = DATA_INICIO + timedelta(days=dia_offset)
        fim_de_semana = dia.weekday() >= 5

        for col in COLABORADORES:
            # Volume diário de uso por perfil.
            base = {"disciplinado": 2.1, "pragmatico": 3.4, "sob_pressao": 4.2}[col.perfil]
            if fim_de_semana:
                base *= 0.18 if col.perfil != "sob_pressao" else 0.45
            n_eventos = max(0, int(rng.gauss(base, 1.4)))

            for _ in range(n_eventos):
                contador += 1
                ferramenta = _escolher_ponderado(rng, FERRAMENTAS_POR_PERFIL[col.perfil])
                tier = tiers_ferramenta.get(ferramenta, "nao_homologada")
                canal = rng.choice(CANAL_POR_TIER[tier])
                finalidade, _ = rng.choice(FINALIDADES)

                # 46% dos usos não envolvem documento da empresa.
                usa_ativo = rng.random() > 0.46
                ativos_origem: list[str] = []

                if usa_ativo:
                    candidatos = AFINIDADE_AREA.get(col.area, ["ATV-011"])
                    ativo_id = rng.choice(candidatos)
                    ativo = acervo_por_id[ativo_id]
                    corpo = _trecho(rng, ativo)
                    ativos_origem = [ativo_id]
                    # Às vezes o colaborador cola dois documentos juntos.
                    if rng.random() < 0.08:
                        outro_id = rng.choice([c for c in candidatos if c != ativo_id] or [ativo_id])
                        corpo += "\n\n" + _trecho(rng, acervo_por_id[outro_id], (0.3, 0.6))
                        ativos_origem.append(outro_id)
                    texto = _envelopar(rng, corpo, finalidade)
                    # PII avulsa junto do documento.
                    if ativo.categoria in ("clientes", "dados_pessoais") and rng.random() < 0.55:
                        texto = _injetar_pii(rng, texto, rng.randint(3, 14))
                else:
                    texto = rng.choice(PROMPTS_NEUTROS)
                    if rng.random() < 0.06:
                        texto = _injetar_pii(rng, texto, rng.randint(1, 3))

                mascarou = False
                if tier in ("tolerada", "nao_homologada") and rng.random() < 0.22:
                    # A extensão ofereceu mascaramento e a pessoa aceitou.
                    mascarou = True

                eventos.append(
                    EventoBruto(
                        id=f"EVT-{contador:05d}",
                        ts=_timestamp(rng, dia, col.perfil == "sob_pressao"),
                        colaborador_id=col.id,
                        ferramenta_id=ferramenta,
                        canal=canal,
                        finalidade=finalidade,
                        texto=texto,
                        ativos_origem=ativos_origem,
                        mascaramento_aceito=mascarou,
                        finalidade_aprovada=(finalidade in ("gerar_codigo", "revisar_texto") and tier == "corporativa"),
                    )
                )

    eventos.extend(_incidente_plantado(rng, len(eventos)))
    proxy = _gerar_proxy(rng, eventos)
    oauth = _gerar_oauth(rng)

    eventos.sort(key=lambda e: e.ts)
    return eventos, proxy, oauth


# ---------------------------------------------------------------------
# O incidente plantado — o caso que carrega o pitch
# ---------------------------------------------------------------------


def _incidente_plantado(rng: random.Random, offset: int) -> list[EventoBruto]:
    """Sequência narrativa: uma analista de Risco sob prazo apertado recorre a
    uma IA não homologada em jurisdição sem adequação, de madrugada, com o
    modelo de score e a base de clientes.

    É o tipo de evento que, sem rastreabilidade, a empresa só descobre quando
    o dado reaparece em outro lugar.
    """
    from .acervo import ACERVO_POR_ID

    col = "COL-07"  # Luana Peixoto — Risco e Crédito, perfil sob pressão
    modelo = ACERVO_POR_ID["ATV-031"]
    base = ACERVO_POR_ID["ATV-030"]
    ata = ACERVO_POR_ID["ATV-024"]

    sabado = DATA_FIM - timedelta(days=5)
    eventos = []

    roteiro = [
        # (dias antes do fim, hora, ferramenta, canal, ativos, finalidade, pii, cartoes, credencial)
        (9, 15, "chatgpt_enterprise", "gateway", [modelo], "analisar_dados", 0, 0, False,
         "Ensaio legítimo: começa dentro da política, na ferramenta corporativa."),
        (7, 20, "perplexity", "extensao", [modelo], "pesquisar", 0, 0, False,
         "Escorrega para ferramenta tolerada ao buscar referência externa."),
        (5, 23, "deepseek", "extensao", [modelo, base], "analisar_dados", 34, 0, False,
         "Vira crítico: modelo proprietário + base de clientes em IA não homologada, de madrugada."),
        (5, 23, "deepseek", "extensao", [base], "analisar_dados", 51, 2, False,
         "Reincidência na mesma noite, agora com dados de cartão no recorte."),
        (4, 1, "deepseek", "extensao", [modelo, ata], "gerar_codigo", 12, 0, True,
         "Terceira ocorrência, com credencial de ambiente embutida no trecho de código."),
    ]

    for i, (dias, hora, ferramenta, canal, ativos, finalidade, n_pii, n_cartao, credencial, _nota) in enumerate(roteiro):
        ts = (DATA_FIM - timedelta(days=dias)).replace(hour=hora, minute=rng.randint(5, 55), second=0, microsecond=0)
        corpo = "\n\n".join(a.texto for a in ativos)
        texto = _envelopar(rng, corpo, finalidade)
        if n_pii:
            texto = _injetar_pii(rng, texto, n_pii)
        if n_cartao:
            texto += "\n\n" + "\n".join(
                f"cartao portador {rng.choice(CARTOES_SINTETICOS)} venc 08/29" for _ in range(n_cartao)
            )
        if credencial:
            texto += (
                "\n\nconfig de ambiente:\n"
                "DATABASE_URL=postgres://svc_risco:Xk93!ptrQ2@db-primario.interno:5432/risco\n"
                "api_key=sk-live-9f2b7c4e1a8d6035bb21ce4470af9d12\n"
            )
        eventos.append(
            EventoBruto(
                id=f"EVT-{offset + i + 1:05d}",
                ts=ts,
                colaborador_id=col,
                ferramenta_id=ferramenta,
                canal=canal,
                finalidade=finalidade,
                texto=texto,
                ativos_origem=[a.id for a in ativos],
                mascaramento_aceito=False,
                finalidade_aprovada=False,
            )
        )

    # Ruído de contraste: outro colaborador aceita o mascaramento no mesmo período.
    eventos.append(
        EventoBruto(
            id=f"EVT-{offset + len(roteiro) + 1:05d}",
            ts=(DATA_FIM - timedelta(days=3)).replace(hour=14, minute=12, second=0, microsecond=0),
            colaborador_id="COL-13",
            ferramenta_id="chatgpt_free",
            canal="extensao",
            finalidade="responder_cliente",
            texto=_injetar_pii(rng, _envelopar(rng, ACERVO_POR_ID["ATV-021"].texto, "responder_cliente"), 9),
            ativos_origem=["ATV-021"],
            mascaramento_aceito=True,
            finalidade_aprovada=False,
        )
    )
    return eventos


# ---------------------------------------------------------------------
# Sinais de descoberta de Shadow AI
# ---------------------------------------------------------------------

# Domínios de IA que aparecem no proxy mas que NINGUÉM declarou — o achado
# que a empresa não sabe que tem.
DOMINIOS_NAO_CATALOGADOS = [
    ("scribe-ai.io", "Transcrição de reuniões", ["oauth"]),
    ("meetnotes.ai", "Notas automáticas de reunião", ["oauth", "proxy"]),
    ("resumeia.com.br", "Resumo de currículos", ["proxy"]),
    ("chatpdf.app", "Perguntas sobre PDF", ["proxy"]),
    ("codegen-helper.dev", "Assistente de código", ["proxy"]),
    ("veo-render.ai", "Geração de vídeo", ["proxy"]),
    ("planilha-gpt.com", "Fórmulas de planilha", ["proxy"]),
    ("legaldraft.ai", "Minutas jurídicas", ["oauth", "proxy"]),
]


def _gerar_proxy(rng: random.Random, eventos: list[EventoBruto]) -> list[RegistroProxy]:
    registros: list[RegistroProxy] = []

    # 1) Tráfego correspondente aos eventos capturados — o proxy vê o domínio
    #    mesmo quando o gateway não vê o conteúdo.
    dominio_por_ferramenta = {
        "chatgpt_enterprise": "chatgpt.com",
        "claude_api_interna": "api.anthropic.com",
        "copilot_business": "copilot-proxy.githubusercontent.com",
        "gemini_workspace": "gemini.google.com",
        "notion_ai": "notion.so",
        "chatgpt_free": "chat.openai.com",
        "perplexity": "perplexity.ai",
        "deepseek": "chat.deepseek.com",
        "cursor_pessoal": "cursor.sh",
        "tradutor_ia": "traduzir-ia.app",
        "resumidor_pdf": "pdfsummarizer.ai",
    }
    for e in eventos:
        dom = dominio_por_ferramenta.get(e.ferramenta_id)
        if not dom:
            continue
        registros.append(
            RegistroProxy(
                ts=e.ts,
                colaborador_id=e.colaborador_id,
                dominio=dom,
                requisicoes=rng.randint(3, 40),
                bytes_enviados=len(e.texto) * rng.randint(2, 6),
                fonte="proxy",
            )
        )

    # 2) Tráfego para ferramentas que NENHUM evento declarou.
    for dominio, _rotulo, fontes in DOMINIOS_NAO_CATALOGADOS:
        n_usuarios = rng.randint(2, 9)
        usuarios = rng.sample([c.id for c in COLABORADORES], n_usuarios)
        for col_id in usuarios:
            for _ in range(rng.randint(2, 18)):
                dia = DATA_INICIO + timedelta(days=rng.randint(10, DIAS - 1))
                registros.append(
                    RegistroProxy(
                        ts=dia.replace(hour=rng.randint(8, 21), minute=rng.randint(0, 59)),
                        colaborador_id=col_id,
                        dominio=dominio,
                        requisicoes=rng.randint(1, 25),
                        bytes_enviados=rng.randint(2_000, 900_000),
                        fonte=rng.choice([f for f in fontes if f == "proxy"] or ["proxy"]),
                    )
                )
    return registros


def _gerar_oauth(rng: random.Random) -> list[ConcessaoOAuth]:
    concessoes: list[ConcessaoOAuth] = []
    apps = [
        ("Scribe AI", "scribe-ai.io", ["calendar.readonly", "drive.file", "meetings.record"]),
        ("MeetNotes", "meetnotes.ai", ["calendar.events", "drive.readonly", "profile.email"]),
        ("LegalDraft AI", "legaldraft.ai", ["drive.readonly", "docs.write"]),
        ("Notion AI", "notion.so", ["workspace.read"]),
    ]
    for nome, dominio, escopos in apps:
        for col_id in rng.sample([c.id for c in COLABORADORES], rng.randint(2, 7)):
            dia = DATA_INICIO + timedelta(days=rng.randint(5, DIAS - 5))
            concessoes.append(
                ConcessaoOAuth(
                    ts=dia.replace(hour=rng.randint(9, 18), minute=rng.randint(0, 59)),
                    colaborador_id=col_id,
                    aplicativo=nome,
                    dominio=dominio,
                    escopos=escopos,
                )
            )
    return concessoes
