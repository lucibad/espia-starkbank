"""
EspIA — validação contra os casos oficiais do desafio.

A aba `Casos_Validacao` da planilha traz quinze situações com o resultado que a
Stark Bank espera de qualquer solução: CRÍTICO, ALTO, MÉDIO, BAIXO ou REVISAR.

É um gabarito. Rodar o motor contra ele transforma "nosso motor está correto" de
opinião em afirmação verificável — e é o que a apresentação deve mostrar antes
de qualquer número bonito.

O caso CV15 merece nota: a informação é descrita como "10 arquivos de propostas",
ou seja, o volume está no texto, não numa coluna. O tradutor abaixo extrai a
quantidade do enunciado, porque é o que um operador faria ao registrar o evento.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .regras import MotorRegras


def _chave(texto: str) -> str:
    """Normaliza para casar nomes escritos com variação de acento e caixa."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


@dataclass
class ResultadoCaso:
    caso: str
    area: str
    ferramenta: str
    informacao: str
    sensibilidade: str
    esperado: str
    obtido: str
    regra: str
    passou: bool
    justificativa: str
    evidencia: str
    achados: list
    # os identificadores já resolvidos, para que o console de políticas possa
    # reavaliar os casos no navegador sem repetir o casamento por nome
    ferramenta_id: str = ""
    informacao_id: str = ""
    qtd_itens: int = 1


class Validador:
    def __init__(self, base):
        self.base = base
        self.motor = MotorRegras(base)
        self._ferr = {_chave(f.nome): f.id for f in base.ferramentas.values()}
        self._info = {_chave(t.nome): t.id for t in base.tipos.values()}

    # -----------------------------------------------------------------

    def _resolver_ferramenta(self, nome: str) -> str | None:
        return self._ferr.get(_chave(nome))

    def _resolver_informacao(self, nome: str) -> tuple[str | None, int]:
        """Devolve (id do tipo, quantidade de itens declarada no texto).

        CV15 diz "10 arquivos de propostas": a quantidade está embutida no nome
        da informação, e o tipo é 'Proposta comercial'.
        """
        bruto = nome or ""
        qtd = 1
        m = re.match(r"\s*(\d+)\s+(?:arquivos?|itens?|documentos?)\s+de\s+(.*)", bruto, re.I)
        if m:
            qtd = int(m.group(1))
            bruto = m.group(2)

        chave = _chave(bruto)
        if chave in self._info:
            return self._info[chave], qtd

        # "propostas" → "Proposta comercial": casa pelo radical
        singular = chave.rstrip("s")
        for k, v in self._info.items():
            if k.startswith(singular) or singular and singular in k:
                return v, qtd
        return None, qtd

    # -----------------------------------------------------------------

    def rodar(self) -> list[ResultadoCaso]:
        saida = []
        for c in self.base.casos:
            fid = self._resolver_ferramenta(c.ferramenta)
            iid, qtd = self._resolver_informacao(c.informacao)
            sens = c.sensibilidade if c.sensibilidade not in ("—", "-", "") else ""

            av = self.motor.avaliar(
                ferramenta_id=fid or "",
                informacao_id=iid or "",
                sensibilidade=sens,
                qtd_itens=qtd,
                fora_horario=False,
                rastreavel=bool(fid),
            )

            esperado = c.esperado.strip().upper()
            obtido = av.nivel.strip().upper()
            saida.append(ResultadoCaso(
                caso=c.id, area=c.area, ferramenta=c.ferramenta, informacao=c.informacao,
                sensibilidade=c.sensibilidade, esperado=c.esperado, obtido=av.nivel,
                regra=av.regra_principal, passou=(obtido == esperado),
                justificativa=c.justificativa, evidencia=av.evidencia,
                achados=[{
                    "regra": a.regra, "nivel": a.nivel, "titulo": a.titulo,
                    "motivo": a.motivo, "acao": a.acao, "contextual": a.contextual,
                } for a in av.achados],
                ferramenta_id=fid or "", informacao_id=iid or "", qtd_itens=qtd,
            ))
        return saida

    def resumo(self) -> dict:
        r = self.rodar()
        passaram = [x for x in r if x.passou]
        return {
            "total": len(r),
            "passaram": len(passaram),
            "falharam": [x.caso for x in r if not x.passou],
            "resultados": r,
        }
