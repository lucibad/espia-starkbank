"""
EspIA — Motor de fingerprint de informação.

A ideia central do projeto: para saber QUAL informação da empresa foi
para dentro de uma IA, não é preciso guardar o que o colaborador digitou.
Basta guardar a *assinatura* do acervo e comparar assinaturas.

Como funciona:
  1. O texto é normalizado (minúsculas, sem acento, sem pontuação).
  2. Ele vira um conjunto de "shingles" — n-gramas de palavras sobrepostos.
     "contrato de correspondente bancario firmado entre" com n=5 gera
     {"contrato de correspondente bancario firmado", "de correspondente
     bancario firmado entre", ...}
  3. Desse conjunto extraímos duas assinaturas:
       - MinHash  -> estima similaridade de Jaccard (trecho colado dentro
                     de um documento maior continua casando)
       - SimHash  -> detecta quase-duplicata e reordenação
  4. O documento original é descartado. Fica só a assinatura.

Consequência prática: o banco de dados da EspIA não contém informação
confidencial da empresa. Ele contém números que só fazem sentido quando
comparados com outros números.

Implementação sem dependências externas — hashlib e struct bastam.
"""

from __future__ import annotations

import hashlib
import re
import struct
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Sequence

MASCARA_64 = (1 << 64) - 1
PRIMO_MERSENNE = (1 << 61) - 1


# ---------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------

_RE_NAO_PALAVRA = re.compile(r"[^a-z0-9\s]+")
_RE_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Reduz o texto à sua forma comparável.

    Tolerante ao que acontece no mundo real: o colaborador copia um trecho,
    reformata, tira acentuação, cola num chat que remove quebras de linha.
    Depois dessa normalização, todas essas variações colidem no mesmo shingle.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = _RE_NAO_PALAVRA.sub(" ", texto)
    return _RE_ESPACOS.sub(" ", texto).strip()


def shingles(texto: str, n: int = 5) -> set[str]:
    """Conjunto de n-gramas de palavras sobrepostos."""
    palavras = normalizar(texto).split()
    if len(palavras) < n:
        # Documento curto: o próprio texto é o único shingle.
        return {" ".join(palavras)} if palavras else set()
    return {" ".join(palavras[i : i + n]) for i in range(len(palavras) - n + 1)}


def _hash64(s: str) -> int:
    return struct.unpack("<Q", hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest())[0]


# ---------------------------------------------------------------------
# MinHash — estimador de Jaccard
# ---------------------------------------------------------------------


def _coeficientes(num_perm: int, semente: int = 0x5EED) -> list[tuple[int, int]]:
    """Coeficientes (a, b) determinísticos para as funções de permutação."""
    coefs = []
    estado = semente
    for _ in range(num_perm):
        estado = _hash64(f"a{estado}")
        a = (estado % (PRIMO_MERSENNE - 1)) + 1
        estado = _hash64(f"b{estado}")
        b = estado % PRIMO_MERSENNE
        coefs.append((a, b))
    return coefs


_CACHE_COEF: dict[int, list[tuple[int, int]]] = {}


def coeficientes(num_perm: int) -> list[tuple[int, int]]:
    if num_perm not in _CACHE_COEF:
        _CACHE_COEF[num_perm] = _coeficientes(num_perm)
    return _CACHE_COEF[num_perm]


def minhash(conjunto: Iterable[str], num_perm: int = 128) -> list[int]:
    """Assinatura MinHash de um conjunto de shingles."""
    coefs = coeficientes(num_perm)
    assinatura = [PRIMO_MERSENNE] * num_perm
    for item in conjunto:
        h = _hash64(item) % PRIMO_MERSENNE
        for i, (a, b) in enumerate(coefs):
            valor = (a * h + b) % PRIMO_MERSENNE
            if valor < assinatura[i]:
                assinatura[i] = valor
    return assinatura


def similaridade_minhash(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    """Estimativa de Jaccard: fração de posições coincidentes."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    iguais = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
    return iguais / len(sig_a)


# ---------------------------------------------------------------------
# SimHash — detector de quase-duplicata
# ---------------------------------------------------------------------


def simhash(conjunto: Iterable[str]) -> int:
    """SimHash de 64 bits sobre os shingles."""
    vetor = [0] * 64
    vazio = True
    for item in conjunto:
        vazio = False
        h = _hash64(item)
        for bit in range(64):
            vetor[bit] += 1 if (h >> bit) & 1 else -1
    if vazio:
        return 0
    valor = 0
    for bit in range(64):
        if vetor[bit] > 0:
            valor |= 1 << bit
    return valor


def distancia_hamming(a: int, b: int) -> int:
    return bin((a ^ b) & MASCARA_64).count("1")


# ---------------------------------------------------------------------
# Contenção — o caso que realmente importa
# ---------------------------------------------------------------------


def containment(shingles_prompt: set[str], shingles_ativo: set[str]) -> float:
    """Fração do PROMPT que veio do ativo.

    Jaccard pune documentos de tamanhos muito diferentes: colar 3 parágrafos
    de um contrato de 40 páginas dá Jaccard baixíssimo, mas o vazamento é real.
    Containment mede o que de fato interessa — quanto do que foi enviado
    pertence a um ativo conhecido da empresa.
    """
    if not shingles_prompt:
        return 0.0
    return len(shingles_prompt & shingles_ativo) / len(shingles_prompt)


# ---------------------------------------------------------------------
# Estrutura de assinatura
# ---------------------------------------------------------------------


@dataclass
class Assinatura:
    """O que sobra de um documento depois que ele é descartado."""

    minhash: list[int] = field(default_factory=list)
    simhash: int = 0
    n_shingles: int = 0
    # Conjunto de shingles mantido em memória apenas durante o processamento
    # do lote. Em produção viveria num índice LSH, não no banco.
    _shingles: set[str] = field(default_factory=set, repr=False)

    @classmethod
    def de_texto(cls, texto: str, n: int = 5, num_perm: int = 128) -> "Assinatura":
        sh = shingles(texto, n=n)
        return cls(
            minhash=minhash(sh, num_perm=num_perm),
            simhash=simhash(sh),
            n_shingles=len(sh),
            _shingles=sh,
        )

    def para_persistencia(self) -> dict:
        """Somente o que vai para o banco. Note que `_shingles` fica de fora."""
        return {
            "minhash": self.minhash,
            "simhash": self.simhash,
            "n_shingles": self.n_shingles,
        }


@dataclass
class Correspondencia:
    ativo_id: str
    jaccard: float
    containment: float
    hamming: int
    confianca: str  # "alta" | "media"

    @property
    def score(self) -> float:
        """Métrica única usada para ordenar candidatos."""
        return max(self.jaccard, self.containment)


def casar(
    assinatura_prompt: Assinatura,
    catalogo: dict[str, Assinatura],
    limiar: float = 0.18,
    limiar_alta: float = 0.45,
) -> list[Correspondencia]:
    """Compara a assinatura de um prompt contra todo o acervo classificado.

    Retorna as correspondências acima do limiar, da mais forte para a mais fraca.
    Em produção esta varredura linear vira um índice LSH por bandas; para a
    escala de um acervo de demonstração, a varredura é exata e mais honesta.
    """
    achados: list[Correspondencia] = []
    for ativo_id, assinatura_ativo in catalogo.items():
        jac = similaridade_minhash(assinatura_prompt.minhash, assinatura_ativo.minhash)
        cont = containment(assinatura_prompt._shingles, assinatura_ativo._shingles)
        score = max(jac, cont)
        if score < limiar:
            continue
        achados.append(
            Correspondencia(
                ativo_id=ativo_id,
                jaccard=round(jac, 4),
                containment=round(cont, 4),
                hamming=distancia_hamming(assinatura_prompt.simhash, assinatura_ativo.simhash),
                confianca="alta" if score >= limiar_alta else "media",
            )
        )
    achados.sort(key=lambda c: c.score, reverse=True)
    return achados
