"""
EspIA — leitor mínimo de YAML, sem dependências.

Por que isto existe: `config/politica.yaml` é o coração do projeto — é onde a
empresa declara sua taxonomia e suas regras de risco. Amarrar a leitura desse
arquivo a um `pip install` significa que o protótipo não roda numa máquina
recém-formatada, que é exatamente a situação de uma apresentação.

Se PyYAML estiver instalado, o pipeline usa PyYAML. Se não estiver, cai aqui.

Este módulo cobre o subconjunto de YAML que o politica.yaml usa e nada além:

  chave: valor                      mapeamento de bloco
  chave:                            mapeamento aninhado por indentação
    sub: valor
  lista:                            sequência de bloco
    - escalar
    - { a: 1, b: "texto, com vírgula" }
    - chave: valor                  (mapa de bloco dentro de item de lista)
      outra: valor
  inline: [a, b, "c"]               sequência em fluxo
  inline: { a: 1 }                  mapeamento em fluxo
  # comentário                      linha inteira ou no fim da linha

Escalares reconhecidos: string entre aspas (simples ou duplas), inteiro,
decimal, true/false, null/~, e string nua. Não há suporte a âncoras, tags,
multilinha (| e >), chaves complexas ou documentos múltiplos — e não deveria
haver: se o politica.yaml precisar disso um dia, instale PyYAML.
"""

from __future__ import annotations

import re


class ErroYAML(ValueError):
    """Erro de sintaxe com número de linha, para não deixar o usuário caçando."""


# ---------------------------------------------------------------------
# Escalares
# ---------------------------------------------------------------------

_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


def _escalar(texto: str):
    t = texto.strip()
    if not t:
        return None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        corpo = t[1:-1]
        if t[0] == '"':
            corpo = corpo.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        else:
            corpo = corpo.replace("''", "'")
        return corpo
    baixo = t.lower()
    if baixo in ("null", "~"):
        return None
    if baixo == "true":
        return True
    if baixo == "false":
        return False
    if _INT.match(t):
        return int(t)
    if _FLOAT.match(t):
        return float(t)
    return t


# ---------------------------------------------------------------------
# Estruturas em fluxo:  [a, b]   {a: 1, b: 2}
# Separadas por um varredor que respeita aspas e aninhamento.
# ---------------------------------------------------------------------


def _partes(corpo: str, linha: int) -> list[str]:
    partes, atual = [], []
    aspas = None
    prof = 0
    for ch in corpo:
        if aspas:
            atual.append(ch)
            if ch == aspas:
                aspas = None
            continue
        if ch in "\"'":
            aspas = ch
            atual.append(ch)
            continue
        if ch in "[{":
            prof += 1
        elif ch in "]}":
            prof -= 1
            if prof < 0:
                raise ErroYAML(f"linha {linha}: fechamento sem abertura em estrutura em fluxo")
        if ch == "," and prof == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(ch)
    if aspas:
        raise ErroYAML(f"linha {linha}: aspas não fechadas")
    if prof != 0:
        raise ErroYAML(f"linha {linha}: estrutura em fluxo não fechada")
    resto = "".join(atual).strip()
    if resto:
        partes.append(resto)
    return [p.strip() for p in partes if p.strip()]


def _divide_chave(parte: str, linha: int) -> tuple[str, str]:
    """Separa 'chave: valor' no primeiro ':' fora de aspas e de colchetes."""
    aspas = None
    prof = 0
    for i, ch in enumerate(parte):
        if aspas:
            if ch == aspas:
                aspas = None
            continue
        if ch in "\"'":
            aspas = ch
        elif ch in "[{":
            prof += 1
        elif ch in "]}":
            prof -= 1
        elif ch == ":" and prof == 0:
            return parte[:i].strip(), parte[i + 1:].strip()
    raise ErroYAML(f"linha {linha}: esperava 'chave: valor' em '{parte}'")


def _valor(texto: str, linha: int):
    t = texto.strip()
    if t.startswith("["):
        if not t.endswith("]"):
            raise ErroYAML(f"linha {linha}: lista em fluxo não fechada")
        return [_valor(p, linha) for p in _partes(t[1:-1], linha)]
    if t.startswith("{"):
        if not t.endswith("}"):
            raise ErroYAML(f"linha {linha}: mapa em fluxo não fechado")
        saida = {}
        for parte in _partes(t[1:-1], linha):
            k, v = _divide_chave(parte, linha)
            saida[str(_escalar(k))] = _valor(v, linha)
        return saida
    return _escalar(t)


# ---------------------------------------------------------------------
# Remoção de comentários preservando aspas
# ---------------------------------------------------------------------


def _sem_comentario(linha: str) -> str:
    aspas = None
    for i, ch in enumerate(linha):
        if aspas:
            if ch == aspas:
                aspas = None
            continue
        if ch in "\"'":
            aspas = ch
        elif ch == "#" and (i == 0 or linha[i - 1] in " \t"):
            return linha[:i]
    return linha


# ---------------------------------------------------------------------
# Analisador de bloco
# ---------------------------------------------------------------------


class _Leitor:
    def __init__(self, texto: str):
        self.linhas: list[tuple[int, int, str]] = []   # (nº da linha, indentação, conteúdo)
        for n, bruta in enumerate(texto.splitlines(), start=1):
            sem = _sem_comentario(bruta.replace("\t", "    ")).rstrip()
            if not sem.strip():
                continue
            if sem.strip() in ("---", "..."):
                continue
            self.linhas.append((n, len(sem) - len(sem.lstrip()), sem.strip()))
        self.i = 0

    def fim(self) -> bool:
        return self.i >= len(self.linhas)

    def espia(self):
        return self.linhas[self.i] if not self.fim() else None

    # -- nó a partir da indentação corrente --------------------------------
    def no(self, indent: int):
        atual = self.espia()
        if atual is None or atual[1] < indent:
            return None
        return self.sequencia(atual[1]) if atual[2].startswith("- ") or atual[2] == "-" \
            else self.mapa(atual[1])

    def mapa(self, indent: int) -> dict:
        saida: dict = {}
        while not self.fim():
            n, ind, conteudo = self.espia()
            if ind < indent:
                break
            if ind > indent:
                raise ErroYAML(f"linha {n}: indentação inesperada")
            if conteudo.startswith("- "):
                break
            chave_txt, resto = _divide_chave(conteudo, n)
            chave = str(_escalar(chave_txt))
            self.i += 1
            if resto:
                saida[chave] = _valor(resto, n)
            else:
                filho = self.espia()
                if filho and filho[1] > indent:
                    saida[chave] = self.no(filho[1])
                elif filho and filho[1] == indent and filho[2].startswith(("- ", "-")):
                    # sequência recuada no mesmo nível da chave — forma válida em YAML
                    saida[chave] = self.sequencia(indent)
                else:
                    saida[chave] = None
        return saida

    def sequencia(self, indent: int) -> list:
        saida: list = []
        while not self.fim():
            n, ind, conteudo = self.espia()
            if ind < indent or not (conteudo.startswith("- ") or conteudo == "-"):
                break
            if ind > indent:
                raise ErroYAML(f"linha {n}: indentação inesperada em sequência")
            item = conteudo[2:].strip() if conteudo.startswith("- ") else ""
            self.i += 1

            if not item:
                filho = self.espia()
                saida.append(self.no(filho[1]) if filho and filho[1] > indent else None)
                continue

            if item.startswith(("[", "{")):
                saida.append(_valor(item, n))
                continue

            # "- chave: valor" abre um mapa cujos irmãos vêm recuados abaixo
            try:
                chave_txt, resto = _divide_chave(item, n)
            except ErroYAML:
                saida.append(_escalar(item))
                continue

            interno_indent = ind + 2
            bloco: dict = {}
            chave = str(_escalar(chave_txt))
            if resto:
                bloco[chave] = _valor(resto, n)
            else:
                filho = self.espia()
                bloco[chave] = self.no(filho[1]) if filho and filho[1] > interno_indent - 1 else None

            filho = self.espia()
            if filho and filho[1] > ind and not filho[2].startswith("- "):
                bloco.update(self.mapa(filho[1]))
            saida.append(bloco)
        return saida


def safe_load(origem):
    """Equivalente a yaml.safe_load para o subconjunto suportado.

    Aceita texto ou um arquivo aberto, como o PyYAML faz — é o que permite
    trocar um pelo outro sem mexer em quem chama.
    """
    texto = origem.read() if hasattr(origem, "read") else origem
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8")
    leitor = _Leitor(texto)
    if leitor.fim():
        return None
    return leitor.no(leitor.espia()[1])
