"""
EspIA — Detectores de conteúdo sensível sem correspondência de acervo.

O fingerprint responde "de qual documento da empresa isso veio?".
Estes detectores respondem a outra pergunta: "isso é sensível mesmo que
não esteja em nenhum documento catalogado?" — um colaborador pode digitar
um CPF de memória, colar um extrato do ERP ou embutir uma chave de API.

Todos rodam na borda (no cliente / no gateway) e devolvem apenas CONTAGENS
e tipos, nunca os valores encontrados. É a diferença entre um controle de
governança e um keylogger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------
# Validadores brasileiros
# ---------------------------------------------------------------------


def _digitos(s: str) -> list[int]:
    return [int(c) for c in s if c.isdigit()]


def cpf_valido(cpf: str) -> bool:
    d = _digitos(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for tam in (9, 10):
        soma = sum(d[i] * (tam + 1 - i) for i in range(tam))
        dv = (soma * 10) % 11
        dv = 0 if dv == 10 else dv
        if dv != d[tam]:
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    d = _digitos(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(d[i] * pesos[i] for i in range(pos))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != d[pos]:
            return False
    return True


def luhn_valido(numero: str) -> bool:
    """Algoritmo de Luhn — usado para PAN de cartão (escopo PCI DSS)."""
    d = _digitos(numero)
    if not 13 <= len(d) <= 19:
        return False
    soma = 0
    dobrar = False
    for digito in reversed(d):
        if dobrar:
            digito *= 2
            if digito > 9:
                digito -= 9
        soma += digito
        dobrar = not dobrar
    return soma % 10 == 0


# ---------------------------------------------------------------------
# Padrões
# ---------------------------------------------------------------------

PADROES = {
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "cnpj": re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "cartao": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "telefone": re.compile(r"\b(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}[- ]?\d{4}\b"),
    "chave_pix_aleatoria": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
    ),
    "credencial": re.compile(
        r"(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"
        r"|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"
        r"|(?:senha|password|secret|api[_-]?key|token)\s*[:=]\s*\S{8,})",
        re.I,
    ),
    "conta_bancaria": re.compile(r"\bag(?:[êe]ncia)?\.?\s*\d{4,5}[-\s/]?\d?\s*(?:c/?c|conta)\.?\s*\d{4,12}-?\d\b", re.I),
    "iban_swift": re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
}

# Tipos que caracterizam dado pessoal para efeito de LGPD.
TIPOS_PII = {"cpf", "email", "telefone", "chave_pix_aleatoria"}


@dataclass
class Deteccao:
    tipo: str
    contagem: int
    validado: bool  # passou por checagem de dígito verificador / Luhn


def detectar(texto: str) -> list[Deteccao]:
    """Varre o texto e devolve tipos + contagens. Nunca os valores."""
    resultado: list[Deteccao] = []

    for tipo, padrao in PADROES.items():
        achados = padrao.findall(texto)
        if not achados:
            continue

        if tipo == "cpf":
            validos = [a for a in achados if cpf_valido(a)]
            if validos:
                resultado.append(Deteccao("cpf", len(validos), True))
        elif tipo == "cnpj":
            validos = [a for a in achados if cnpj_valido(a)]
            if validos:
                resultado.append(Deteccao("cnpj", len(validos), True))
        elif tipo == "cartao":
            # Luhn evita que qualquer sequência longa de dígitos vire alarme.
            validos = [a for a in achados if luhn_valido(a) and not cpf_valido(a) and not cnpj_valido(a)]
            if validos:
                resultado.append(Deteccao("cartao", len(validos), True))
        elif tipo == "iban_swift":
            # Padrão ruidoso demais isolado; só conta se o texto falar de SWIFT.
            if re.search(r"\bswift\b|\bbic\b|\biban\b", texto, re.I):
                resultado.append(Deteccao("iban_swift", len(achados), False))
        else:
            resultado.append(Deteccao(tipo, len(achados), False))

    return resultado


def total_pii(deteccoes: list[Deteccao]) -> int:
    return sum(d.contagem for d in deteccoes if d.tipo in TIPOS_PII)


def tem(deteccoes: list[Deteccao], tipo: str) -> bool:
    return any(d.tipo == tipo for d in deteccoes)


# ---------------------------------------------------------------------
# Mascaramento — o "negocie, não bloqueie"
# ---------------------------------------------------------------------

_SUBSTITUTOS = {
    "cpf": "[CPF-MASCARADO]",
    "cnpj": "[CNPJ-MASCARADO]",
    "cartao": "[CARTAO-MASCARADO]",
    "email": "[EMAIL-MASCARADO]",
    "telefone": "[TELEFONE-MASCARADO]",
    "chave_pix_aleatoria": "[CHAVE-PIX-MASCARADA]",
    "credencial": "[CREDENCIAL-REMOVIDA]",
    "conta_bancaria": "[CONTA-MASCARADA]",
}


def mascarar(texto: str) -> tuple[str, int]:
    """Devolve a versão anonimizada e quantas substituições foram feitas.

    É o que a extensão oferece ao colaborador no momento do colar:
    não bloqueia o uso da IA, remove o que não pode sair.
    """
    substituicoes = 0
    saida = texto
    for tipo, padrao in PADROES.items():
        if tipo not in _SUBSTITUTOS:
            continue
        if tipo == "cpf":
            def _sub_cpf(m):
                nonlocal substituicoes
                if cpf_valido(m.group()):
                    substituicoes += 1
                    return _SUBSTITUTOS["cpf"]
                return m.group()
            saida = padrao.sub(_sub_cpf, saida)
        elif tipo == "cartao":
            def _sub_cartao(m):
                nonlocal substituicoes
                if luhn_valido(m.group()):
                    substituicoes += 1
                    return _SUBSTITUTOS["cartao"]
                return m.group()
            saida = padrao.sub(_sub_cartao, saida)
        else:
            saida, n = padrao.subn(_SUBSTITUTOS[tipo], saida)
            substituicoes += n
    return saida, substituicoes
