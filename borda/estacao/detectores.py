"""Detectores da camada 1 sobre CONTEÚDO capturado pela extensão.

Regex com validação (dígitos verificadores de CPF/CNPJ, Luhn em cartão) —
IA clássica, sem modelo. Saída: detecções, tipo de informação inferido e um
trecho MASCARADO para evidência. O texto completo nunca é gravado.

Os nomes de tipo seguem a aba Tipos_Informacao da base; a sensibilidade vem da
coluna "Classificação padrão" dessa aba, carregada pelo agente.
"""
import re

# ── validadores ─────────────────────────────────────────────────────────
def cpf_valido(s):
    d = re.sub(r"\D", "", s)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * ((n + 1) - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def cnpj_valido(s):
    d = re.sub(r"\D", "", s)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for n, pesos in ((12, pesos1), (13, pesos2)):
        soma = sum(int(d[i]) * pesos[i] for i in range(n))
        dv = 11 - (soma % 11)
        dv = 0 if dv >= 10 else dv
        if dv != int(d[n]):
            return False
    return True


def luhn_valido(s):
    d = re.sub(r"\D", "", s)
    if not 13 <= len(d) <= 19:
        return False
    total, alt = 0, False
    for c in reversed(d):
        n = int(c)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


# ── padrões ─────────────────────────────────────────────────────────────
# (nome, regex, validador opcional, máscara)
PADROES = [
    ("credencial", re.compile(
        r"(?:sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|ghp_[A-Za-z0-9]{36}"
        r"|xox[abp]-[A-Za-z0-9\-]{10,}"
        r"|AIza[0-9A-Za-z_\-]{35}"
        r"|-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----"
        r"|\b(?:api[_ \-]?key|secret|token|senha|password|passwd)\b\s*[:=]\s*['\"]?[^\s'\"]{8,})",
        re.I), None, "[CREDENCIAL]"),
    ("cartao", re.compile(r"\b(?:\d[ \-]?){13,19}\b"), luhn_valido, "[CARTÃO]"),
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), cpf_valido, "[CPF]"),
    ("cnpj", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), cnpj_valido, "[CNPJ]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), None, "[E-MAIL]"),
    ("folha", re.compile(r"\b(?:sal[aá]rio|folha de pagamento|remunera[çc][ãa]o|holerite|contracheque)\b", re.I), None, None),
    ("financeiro", re.compile(r"\b(?:ebitda|receita l[ií]quida|faturamento|margem (?:bruta|l[ií]quida)|proje[çc][ãa]o|guidance|resultado do trimestre|dre)\b", re.I), None, None),
    ("contrato", re.compile(r"\b(?:contrato|cl[aá]usula|minuta|aditivo|acordo de confidencialidade|nda)\b", re.I), None, None),
    ("proposta", re.compile(r"\b(?:proposta comercial|pre[çc]o unit[aá]rio|desconto de|tabela de pre[çc]os|cota[çc][ãa]o)\b", re.I), None, None),
    ("cliente", re.compile(r"\b(?:cliente|correntista|titular|conta corrente|ag[eê]ncia \d|cadastro)\b", re.I), None, None),
    ("codigo", re.compile(r"(?:\bdef \w+\(|\bfunction\s+\w*\(|\bclass \w+[:{(]|\bimport \w+|#include\s*<|\bSELECT\b.+\bFROM\b|public static|=>\s*\{|\bconst \w+ =)", re.I), None, None),
    ("juridico", re.compile(r"\b(?:parecer|peti[çc][ãa]o|processo n|senten[çc]a|tribunal|jurisprud[eê]ncia)\b", re.I), None, None),
]

# Prioridade: a primeira que casar define o tipo. Um conteúdo pode acionar
# vários detectores; todos ficam registrados como evidência.
INFERENCIA = [
    (lambda h: "credencial" in h,                              "Chave/API secret"),
    (lambda h: "cartao" in h,                                  "Dados financeiros de cliente"),
    (lambda h: ("cpf" in h or "cnpj" in h) and "cliente" in h, "Dados cadastrais de cliente"),
    (lambda h: "cpf" in h and h["cpf"] >= 1,                   "Dados cadastrais de cliente"),
    (lambda h: "folha" in h,                                   "Folha/remuneração"),
    (lambda h: "financeiro" in h,                              "Resultado financeiro não divulgado"),
    (lambda h: "proposta" in h,                                "Proposta comercial"),
    (lambda h: "contrato" in h,                                "Contrato de cliente"),
    (lambda h: "juridico" in h,                                "Parecer jurídico"),
    (lambda h: "codigo" in h,                                  "Código-fonte"),
    (lambda h: "email" in h and h["email"] >= 3,               "Dados cadastrais de cliente"),
]
SEM_CLASSIFICACAO = "Informação sem classificação"


def analisar(texto, arquivos=None):
    """Retorna dict com: tipo, detectores {nome: contagem}, trecho (mascarado), tamanho."""
    texto = texto or ""
    hits = {}
    mascarado = texto
    for nome, rx, valida, mascara in PADROES:
        n = 0
        for m in rx.finditer(texto):
            if valida and not valida(m.group(0)):
                continue
            n += 1
        if n:
            hits[nome] = n
            if mascara:
                def _sub(m, valida=valida, mascara=mascara):
                    return mascara if (valida is None or valida(m.group(0))) else m.group(0)
                mascarado = rx.sub(_sub, mascarado)

    # nomes de arquivo também carregam sinal (sem abrir o conteúdo)
    nomes = " ".join(a.get("nome", "") for a in (arquivos or []))
    if nomes:
        for nome, rx, valida, _ in PADROES:
            if valida is None and rx.search(nomes):
                hits[nome] = hits.get(nome, 0) + 1

    tipo = SEM_CLASSIFICACAO
    for cond, t in INFERENCIA:
        if cond(hits):
            tipo = t
            break

    trecho = re.sub(r"\s+", " ", mascarado).strip()[:120]
    return {"tipo": tipo, "detectores": hits, "trecho": trecho, "tamanho": len(texto)}
