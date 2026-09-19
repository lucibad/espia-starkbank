"""
GerencIA — importador da base oficial do desafio.

Lê `base/Base_de_Dados_Starkbank_apurada_15-09.xlsx` — a planilha fornecida
pela Stark Bank — para o modelo interno da ferramenta.

A planilha tem doze abas. Quatro são *cadastros* (ferramentas, tipos de
informação, usuários, regras), duas são *fatos* (650 eventos, 160 alertas), e
as demais são referência: dicionário de dados, fontes de log, casos de
validação, indicadores declarados e a apuração que a própria planilha fez.

Uma observação que vale para a leitura de todo o resto do projeto: as colunas
`Tipo informação` e `Sensibilidade` já vêm preenchidas, e o dicionário de dados
diz que a origem delas é "Classificador/DLP". Ou seja, a planilha é a **saída**
de uma camada de captura e classificação que já existe. A GerencIA consome essa
saída, aplica as regras, audita o resultado e o torna consultável — e os módulos
`fingerprint.py` e `detectores.py` mostram como essas duas colunas seriam
preenchidas automaticamente, que hoje depende de DLP e de registro manual.

Todos os dados da planilha são fictícios, declarado na própria fonte.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ / "base" / "Base_de_Dados_Starkbank_apurada_15-09.xlsx"


def _abrir(caminho):
    """openpyxl quando existe; senão o leitor embutido. O resultado é o mesmo."""
    try:
        import openpyxl  # noqa: F401
    except ModuleNotFoundError:
        from . import xlsx_min
        return xlsx_min.abrir(caminho), "xlsx_min (leitor embutido)"

    from . import xlsx_min
    return xlsx_min.abrir(caminho), "xlsx_min (leitor embutido)"


# ---------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Ferramenta:
    id: str
    nome: str
    tipo: str                 # Corporativa | Pública
    status: str               # Aprovada | Aprovada condicional | Não aprovada | ...
    uso_principal: str
    logs: str                 # Sim | Não | Parcial
    controles: str
    finalidade_aprovada: str

    @property
    def aprovada(self) -> bool:
        """Tratada como aprovada pela política.

        O 'Gerador de Imagens' é 'Aprovada apenas para conteúdo público': conta
        como aprovada para efeito das regras que falam em ferramenta aprovada, e
        a restrição de conteúdo entra na checagem de finalidade.
        """
        return not self.status.lower().startswith("não aprovada")

    @property
    def publica(self) -> bool:
        return self.tipo.strip().lower() == "pública"

    @property
    def somente_conteudo_publico(self) -> bool:
        return "apenas para conteúdo público" in self.status.lower()

    @property
    def tem_logs(self) -> bool:
        return self.logs.strip().lower() == "sim"


@dataclass(frozen=True)
class TipoInformacao:
    id: str
    nome: str
    categoria: str
    classificacao_padrao: str  # Pública | Interna | Confidencial | Crítica
    area_tipica: str

    @property
    def e_credencial(self) -> bool:
        return self.categoria.strip().lower() == "credencial"

    @property
    def e_dado_pessoal(self) -> bool:
        return self.categoria.strip().lower().startswith("dados pessoais")

    @property
    def e_codigo(self) -> bool:
        return self.id == "INF-01"

    @property
    def e_financeiro_nao_divulgado(self) -> bool:
        return self.id == "INF-09"


@dataclass(frozen=True)
class Usuario:
    id: str
    nome: str
    area: str
    cargo: str
    modelo_trabalho: str
    perfil_acesso: str
    status: str


@dataclass(frozen=True)
class Regra:
    id: str
    tema: str
    texto: str
    nivel_esperado: str
    acao_esperada: str


@dataclass
class Evento:
    id: str
    ts: dt.datetime | None
    ts_bruto: str
    usuario_id: str
    area: str
    ferramenta_id: str
    ferramenta_nome: str
    informacao_id: str
    informacao_nome: str
    sensibilidade: str
    forma_uso: str
    qtd_itens: int
    finalidade: str
    risco_declarado: str
    regra_declarada: str
    evidencias_declaradas: str
    acao_sugerida: str
    origem_registro: str
    # preenchidos pelo motor
    risco_espia: str | None = None
    regra_espia: str | None = None
    fatores: list = field(default_factory=list)

    @property
    def data(self) -> str:
        return self.ts.date().isoformat() if self.ts else ""

    @property
    def hora(self) -> int:
        return self.ts.hour if self.ts else -1

    @property
    def fim_de_semana(self) -> bool:
        return bool(self.ts) and self.ts.weekday() >= 5

    @property
    def fora_horario(self) -> bool:
        """R12: uso fora do padrão. 22h–06h ou fim de semana."""
        if not self.ts:
            return False
        return self.ts.hour >= 22 or self.ts.hour < 6 or self.fim_de_semana

    @property
    def rastreavel(self) -> bool:
        """R14: o evento tem usuário, ferramenta e data confiáveis?"""
        return bool(self.usuario_id and self.ferramenta_id and self.ts)

    @property
    def divergente(self) -> bool:
        return bool(self.risco_espia) and self.risco_espia != self.risco_declarado


@dataclass(frozen=True)
class Alerta:
    id: str
    evento_id: str
    ts_bruto: str
    usuario_id: str
    area: str
    ferramenta: str
    informacao: str
    sensibilidade: str
    risco: str
    regra: str
    evidencia: str
    status: str            # Aberto | Em análise | Tratado
    responsavel: str


@dataclass(frozen=True)
class CasoValidacao:
    id: str
    area: str
    ferramenta: str
    informacao: str
    sensibilidade: str
    esperado: str
    justificativa: str


@dataclass(frozen=True)
class IndicadorDeclarado:
    nome: str
    valor_declarado: str
    meta: str
    frequencia: str
    responsavel: str
    valor_planilha: str     # o que a própria planilha apurou
    divergencia_planilha: str


@dataclass(frozen=True)
class FonteLog:
    id: str
    nome: str
    dados: str
    formato: str
    confiabilidade: str
    atualizacao: str


@dataclass
class Base:
    ferramentas: dict[str, Ferramenta]
    tipos: dict[str, TipoInformacao]
    usuarios: dict[str, Usuario]
    regras: dict[str, Regra]
    eventos: list[Evento]
    alertas: list[Alerta]
    casos: list[CasoValidacao]
    indicadores: list[IndicadorDeclarado]
    fontes: list[FonteLog]
    classificacoes: list[dict]
    leitor: str

    @property
    def areas(self) -> list[str]:
        return sorted({e.area for e in self.eventos})

    @property
    def periodo(self) -> tuple[str, str]:
        datas = sorted(e.data for e in self.eventos if e.data)
        return (datas[0], datas[-1]) if datas else ("", "")


# ---------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------

_RE_DATA = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})[ T]*(\d{1,2})?:?(\d{2})?")


def _data(valor) -> tuple[dt.datetime | None, str]:
    if valor is None:
        return None, ""
    if isinstance(valor, dt.datetime):
        return valor, valor.strftime("%d/%m/%Y %H:%M")
    texto = str(valor).strip()
    m = _RE_DATA.match(texto)
    if not m:
        return None, texto
    d, mes, a, h, mi = m.groups()
    try:
        return dt.datetime(int(a), int(mes), int(d), int(h or 0), int(mi or 0)), texto
    except ValueError:
        return None, texto


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def carregar(caminho: Path = CAMINHO_PADRAO) -> Base:
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(
            f"Base oficial não encontrada em {caminho}.\n"
            "Coloque o arquivo .xlsx do desafio na pasta base/ com esse nome."
        )
    planilha, leitor = _abrir(caminho)

    ferramentas = {
        _txt(r["ID"]): Ferramenta(
            id=_txt(r["ID"]), nome=_txt(r["Ferramenta fictícia"]), tipo=_txt(r["Tipo"]),
            status=_txt(r["Status"]), uso_principal=_txt(r["Uso principal"]),
            logs=_txt(r["Logs disponíveis"]), controles=_txt(r["Controles fictícios"]),
            finalidade_aprovada=_txt(r["Finalidade aprovada"]),
        )
        for r in planilha.tabela("Ferramentas_IA")
    }

    tipos = {
        _txt(r["ID"]): TipoInformacao(
            id=_txt(r["ID"]), nome=_txt(r["Tipo de informação"]),
            categoria=_txt(r["Categoria"]),
            classificacao_padrao=_txt(r["Classificação padrão"]),
            area_tipica=_txt(r["Área típica"]),
        )
        for r in planilha.tabela("Tipos_Informacao")
    }

    usuarios = {
        _txt(r["ID Usuário"]): Usuario(
            id=_txt(r["ID Usuário"]), nome=_txt(r["Nome fictício"]), area=_txt(r["Área"]),
            cargo=_txt(r["Cargo"]), modelo_trabalho=_txt(r["Modelo trabalho"]),
            perfil_acesso=_txt(r["Perfil de acesso"]), status=_txt(r["Status"]),
        )
        for r in planilha.tabela("Usuarios_Areas")
    }

    regras = {
        _txt(r["ID"]): Regra(
            id=_txt(r["ID"]), tema=_txt(r["Tema"]), texto=_txt(r["Regra fictícia"]),
            nivel_esperado=_txt(r["Nível esperado"]), acao_esperada=_txt(r["Ação esperada"]),
        )
        for r in planilha.tabela("Regras_Risco")
    }

    eventos = []
    for r in planilha.tabela("Eventos_Uso_IA"):
        ts, bruto = _data(r["Data/hora"])
        eventos.append(Evento(
            id=_txt(r["ID Evento"]), ts=ts, ts_bruto=bruto,
            usuario_id=_txt(r["ID Usuário"]), area=_txt(r["Área"]),
            ferramenta_id=_txt(r["ID Ferramenta"]), ferramenta_nome=_txt(r["Ferramenta"]),
            informacao_id=_txt(r["ID Informação"]), informacao_nome=_txt(r["Tipo informação"]),
            sensibilidade=_txt(r["Sensibilidade"]), forma_uso=_txt(r["Forma de uso"]),
            qtd_itens=_int(r["Qtd. itens"]), finalidade=_txt(r["Finalidade"]),
            risco_declarado=_txt(r["Risco"]), regra_declarada=_txt(r["Regra acionada"]),
            evidencias_declaradas=_txt(r["Evidências"]), acao_sugerida=_txt(r["Ação sugerida"]),
            origem_registro=_txt(r["Origem do registro"]),
        ))

    alertas = [
        Alerta(
            id=_txt(r["ID Alerta"]), evento_id=_txt(r["ID Evento"]),
            ts_bruto=_data(r["Data/hora"])[1], usuario_id=_txt(r["ID Usuário"]),
            area=_txt(r["Área"]), ferramenta=_txt(r["Ferramenta"]),
            informacao=_txt(r["Informação"]), sensibilidade=_txt(r["Sensibilidade"]),
            risco=_txt(r["Risco"]), regra=_txt(r["Regra"]), evidencia=_txt(r["Evidência"]),
            status=_txt(r["Status"]), responsavel=_txt(r["Responsável"]),
        )
        for r in planilha.tabela("Alertas")
    ]

    casos = [
        CasoValidacao(
            id=_txt(r["Caso"]), area=_txt(r["Área"]), ferramenta=_txt(r["Ferramenta"]),
            informacao=_txt(r["Informação"]), sensibilidade=_txt(r["Sensibilidade"]),
            esperado=_txt(r["Resultado esperado"]), justificativa=_txt(r["Justificativa"]),
        )
        for r in planilha.tabela("Casos_Validacao")
    ]

    indicadores = [
        IndicadorDeclarado(
            nome=_txt(r["Indicador"]), valor_declarado=_txt(r["Valor fictício atual"]),
            meta=_txt(r["Meta fictícia"]), frequencia=_txt(r["Frequência"]),
            responsavel=_txt(r["Responsável"]), valor_planilha=_txt(r["Valor apurado na base"]),
            divergencia_planilha=_txt(r["Divergência"]),
        )
        for r in planilha.tabela("Indicadores_Atuais")
    ]

    fontes = [
        FonteLog(
            id=_txt(r["ID"]), nome=_txt(r["Fonte fictícia"]), dados=_txt(r["Dados disponíveis"]),
            formato=_txt(r["Formato"]), confiabilidade=_txt(r["Confiabilidade"]),
            atualizacao=_txt(r["Atualização"]),
        )
        for r in planilha.tabela("Fontes_Logs")
    ]

    classificacoes = [
        {
            "classificacao": _txt(r["Classificação"]), "definicao": _txt(r["Definição fictícia"]),
            "risco_base": _txt(r["Risco base"]), "regra_geral": _txt(r["Regra geral"]),
        }
        for r in planilha.tabela("Classificacao_Informacao")
    ]

    planilha.close()

    return Base(
        ferramentas=ferramentas, tipos=tipos, usuarios=usuarios, regras=regras,
        eventos=eventos, alertas=alertas, casos=casos, indicadores=indicadores,
        fontes=fontes, classificacoes=classificacoes, leitor=leitor,
    )
