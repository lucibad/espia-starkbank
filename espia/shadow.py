"""
GerencIA — Descoberta de Shadow AI.

O primeiro requisito do desafio é "registrar quais ferramentas ou aplicações
de IA estão sendo utilizadas". Um formulário responde a pergunta errada:
ele registra as ferramentas que alguém lembrou de declarar.

Este módulo responde a pergunta certa, correlacionando dois sinais que a
empresa já tem e não usa:

  1. Log do proxy de saída / resolvedor DNS corporativo — revela QUE
     domínios de IA a rede alcança.
  2. Concessões OAuth no provedor de identidade — revela QUE aplicativos de
     IA receberam acesso ao Drive, ao calendário e ao e-mail corporativo.

O que aparece nesses sinais e não aparece no cadastro de ferramentas é
Shadow AI: em uso, sem contrato, sem DPA, sem ninguém sabendo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


# Escopos OAuth que dão a um aplicativo acesso a conteúdo corporativo.
ESCOPOS_SENSIVEIS = {
    "drive.readonly": "leitura de todos os arquivos do Drive",
    "drive.file": "criação e leitura de arquivos no Drive",
    "docs.write": "escrita em documentos",
    "calendar.events": "leitura e escrita da agenda",
    "calendar.readonly": "leitura da agenda",
    "meetings.record": "gravação de reuniões",
    "mail.read": "leitura de e-mail",
}


@dataclass
class FerramentaDescoberta:
    dominio: str
    catalogada: bool
    nome_catalogo: str | None
    tier: str | None
    primeiro_visto: datetime
    ultimo_visto: datetime
    usuarios: set[str] = field(default_factory=set)
    areas: set[str] = field(default_factory=set)
    requisicoes: int = 0
    bytes_enviados: int = 0
    fontes: set[str] = field(default_factory=set)
    escopos_oauth: set[str] = field(default_factory=set)
    aplicativo_oauth: str | None = None

    @property
    def n_usuarios(self) -> int:
        return len(self.usuarios)

    def severidade(self) -> tuple[str, list[str]]:
        """Prioriza o que a Segurança da Informação deve olhar primeiro."""
        motivos: list[str] = []
        pontos = 0

        if not self.catalogada:
            pontos += 3
            motivos.append("Não consta no cadastro de ferramentas — TI não sabe que está em uso")
        elif self.tier == "nao_homologada":
            pontos += 3
            motivos.append("Catalogada como NÃO HOMOLOGADA e ainda assim alcançável pela rede — falta bloqueio")
        elif self.tier == "tolerada":
            pontos += 1
            motivos.append("Ferramenta tolerada: aceitável só para informação pública ou interna")

        escopos_perigosos = self.escopos_oauth & set(ESCOPOS_SENSIVEIS)
        if escopos_perigosos:
            pontos += 3
            legiveis = ", ".join(sorted(ESCOPOS_SENSIVEIS[e] for e in escopos_perigosos))
            motivos.append(f"Recebeu acesso persistente a: {legiveis}")

        if self.n_usuarios >= 5:
            pontos += 2
            motivos.append(f"{self.n_usuarios} pessoas em {len(self.areas)} área(s) — uso já disseminado")
        elif self.n_usuarios >= 3:
            pontos += 1
            motivos.append(f"{self.n_usuarios} pessoas usando")

        if self.bytes_enviados > 2_000_000:
            pontos += 2
            mb = self.bytes_enviados / 1_048_576
            motivos.append(f"{mb:.1f} MB enviados no período — volume de upload de documentos")

        if pontos >= 7:
            return "critico", motivos
        if pontos >= 5:
            return "alto", motivos
        if pontos >= 3:
            return "medio", motivos
        return "baixo", motivos


def descobrir(
    registros_proxy: list,
    concessoes_oauth: list,
    dominios_catalogados: dict[str, tuple[str, str]],
    colaboradores: dict,
) -> list[FerramentaDescoberta]:
    """Correlaciona proxy + OAuth e devolve o inventário real de ferramentas.

    `dominios_catalogados` mapeia domínio -> (nome, tier) segundo o politica.yaml.
    """
    achados: dict[str, FerramentaDescoberta] = {}

    def obter(dominio: str, ts: datetime) -> FerramentaDescoberta:
        if dominio not in achados:
            entrada = dominios_catalogados.get(dominio)
            achados[dominio] = FerramentaDescoberta(
                dominio=dominio,
                catalogada=entrada is not None,
                nome_catalogo=entrada[0] if entrada else None,
                tier=entrada[1] if entrada else None,
                primeiro_visto=ts,
                ultimo_visto=ts,
            )
        f = achados[dominio]
        f.primeiro_visto = min(f.primeiro_visto, ts)
        f.ultimo_visto = max(f.ultimo_visto, ts)
        return f

    for r in registros_proxy:
        f = obter(r.dominio, r.ts)
        f.usuarios.add(r.colaborador_id)
        col = colaboradores.get(r.colaborador_id)
        if col:
            f.areas.add(col.area)
        f.requisicoes += r.requisicoes
        f.bytes_enviados += r.bytes_enviados
        f.fontes.add(r.fonte)

    for c in concessoes_oauth:
        f = obter(c.dominio, c.ts)
        f.usuarios.add(c.colaborador_id)
        col = colaboradores.get(c.colaborador_id)
        if col:
            f.areas.add(col.area)
        f.fontes.add("oauth")
        f.escopos_oauth.update(c.escopos)
        f.aplicativo_oauth = c.aplicativo

    ordem = {"critico": 0, "alto": 1, "medio": 2, "baixo": 3}
    return sorted(achados.values(), key=lambda f: (ordem[f.severidade()[0]], -f.n_usuarios))


def resumo_por_area(descobertas: list[FerramentaDescoberta], colaboradores: dict) -> dict[str, dict]:
    """Quantas ferramentas não catalogadas cada área está usando."""
    por_area: dict[str, dict] = defaultdict(lambda: {"nao_catalogadas": set(), "usuarios": set()})
    for f in descobertas:
        if f.catalogada:
            continue
        for col_id in f.usuarios:
            col = colaboradores.get(col_id)
            if not col:
                continue
            por_area[col.area]["nao_catalogadas"].add(f.dominio)
            por_area[col.area]["usuarios"].add(col_id)
    return {
        area: {"nao_catalogadas": len(d["nao_catalogadas"]), "usuarios": len(d["usuarios"])}
        for area, d in por_area.items()
    }
