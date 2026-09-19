#!/usr/bin/env python3
"""
GerencIA — testes de sanidade.

Não é uma suíte completa; é o conjunto mínimo que prova, na frente da banca,
que as três afirmações centrais do projeto são verdadeiras:

  1. O fingerprint reconhece um trecho colado de um documento do acervo
     mesmo quando ele foi reformatado — e NÃO confunde documentos distintos.
  2. Os detectores validam de verdade (dígito verificador, Luhn), em vez de
     alarmar em qualquer sequência de números.
  3. O motor de risco é monotônico: piorar a ferramenta ou a classificação
     nunca reduz o score, e a cadeia de evidências soma o score final.

    python testes.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from espia.acervo import ACERVO_POR_ID  # noqa: E402
from espia.detectores import cnpj_valido, cpf_valido, detectar, luhn_valido, mascarar  # noqa: E402
from espia.fingerprint import Assinatura, casar  # noqa: E402
from espia.motor_risco import MotorRisco  # noqa: E402
from espia.pipeline import carregar_politica, construir_catalogo_assinaturas  # noqa: E402

falhas = 0


def checar(condicao: bool, descricao: str, detalhe: str = "") -> None:
    global falhas
    if condicao:
        print(f"  \033[92m✓\033[0m {descricao}")
    else:
        falhas += 1
        print(f"  \033[91m✗\033[0m {descricao}" + (f"  ({detalhe})" if detalhe else ""))


politica = carregar_politica()
catalogo = construir_catalogo_assinaturas(politica)
cfg = politica["fingerprint"]


def assinar(texto: str) -> Assinatura:
    return Assinatura.de_texto(texto, n=cfg["tamanho_shingle"], num_perm=cfg["permutacoes_minhash"])


# =====================================================================
print("\n\033[1m1. Fingerprint\033[0m")

contrato = ACERVO_POR_ID["ATV-020"]
palavras = contrato.texto.split()
trecho = " ".join(palavras[12:58])

m = casar(assinar(trecho), catalogo, cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
checar(bool(m) and m[0].ativo_id == "ATV-020",
       "trecho literal de um contrato casa com o contrato certo",
       f"obtido: {m[0].ativo_id if m else 'nenhum'}")

# Mesmo trecho maltratado: sem acento, tudo minúsculo, pontuação trocada,
# quebras de linha — como sai de um copiar-colar real.
maltratado = trecho.upper().replace(",", " ;").replace(".", " |").replace(" ", "\n  ")
m2 = casar(assinar(maltratado), catalogo, cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
checar(bool(m2) and m2[0].ativo_id == "ATV-020",
       "o mesmo trecho reformatado continua casando",
       f"obtido: {m2[0].ativo_id if m2 else 'nenhum'}")

# Texto sem relação nenhuma não pode gerar correspondência.
ruido = ("A fotossíntese converte energia luminosa em energia química nos cloroplastos "
         "das células vegetais, produzindo glicose a partir de gás carbônico e água. "
         "O processo ocorre em duas etapas complementares e interdependentes.")
m3 = casar(assinar(ruido), catalogo, cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
checar(not m3, "texto sem relação com o acervo não gera falso positivo",
       f"casou com {[c.ativo_id for c in m3]}")

# Dois ativos distintos não podem colidir entre si.
colisoes = []
for aid, assinatura in catalogo.items():
    outros = casar(assinatura, {k: v for k, v in catalogo.items() if k != aid},
                   cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
    if outros:
        colisoes.append((aid, outros[0].ativo_id, round(outros[0].score, 2)))
checar(not colisoes, "nenhum par de ativos distintos colide acima do limiar", str(colisoes[:3]))

# Containment: um parágrafo curto dentro de um documento longo ainda casa.
curto = " ".join(ACERVO_POR_ID["ATV-031"].texto.split()[:32])
m4 = casar(assinar(curto), catalogo, cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
checar(bool(m4) and m4[0].ativo_id == "ATV-031",
       "trecho curto de documento longo é reconhecido (containment)",
       f"obtido: {m4[0].ativo_id if m4 else 'nenhum'}")

# A assinatura persistida não pode carregar o conteúdo.
persistido = assinar(contrato.texto).para_persistencia()
checar("_shingles" not in persistido and set(persistido) == {"minhash", "simhash", "n_shingles"},
       "a assinatura gravada no banco não contém texto do documento")


# =====================================================================
print("\n\033[1m2. Detectores\033[0m")

checar(cpf_valido("529.982.247-25") and not cpf_valido("529.982.247-26"),
       "CPF é validado por dígito verificador, não por formato")
checar(cnpj_valido("11.222.333/0001-81") and not cnpj_valido("11.222.333/0001-82"),
       "CNPJ é validado por dígito verificador")
checar(luhn_valido("4539148803436467") and not luhn_valido("4539148803436468"),
       "número de cartão é validado por Luhn")
checar(not detectar("Protocolo 1234567890123456 aberto em 12/03"),
       "sequência longa de dígitos sem validade não vira alarme")

texto_pii = ("Cliente A. Ribeiro - CPF 529.982.247-25 - contato ribeiro@exemplo.com.br\n"
             "api_key=sk-live-9f2b7c4e1a8d6035bb21ce4470af9d12")
d = detectar(texto_pii)
tipos = {x.tipo for x in d}
checar("cpf" in tipos and "email" in tipos and "credencial" in tipos,
       "CPF, e-mail e credencial são detectados no mesmo trecho", str(tipos))

mascarado, n = mascarar(texto_pii)
checar(n >= 3 and "529.982.247-25" not in mascarado and "sk-live-9f2b" not in mascarado,
       "o mascaramento remove o identificador e a credencial do texto")
checar("Cliente A. Ribeiro" in mascarado,
       "o mascaramento preserva o conteúdo útil — a IA ainda consegue responder")


# =====================================================================
print("\n\033[1m3. Motor de risco\033[0m")

motor = MotorRisco(politica)
quando = datetime(2026, 9, 9, 14, 30)  # quarta-feira, horário comercial


def avaliar(ativo_id: str, ferramenta: str, **kw):
    m = casar(assinar(ACERVO_POR_ID[ativo_id].texto), catalogo,
              cfg["limiar_correspondencia"], cfg["limiar_alta_confianca"])
    base = dict(
        ts=quando, ferramenta_id=ferramenta, canal="gateway", finalidade="analisar_dados",
        finalidade_aprovada=False, mascaramento_aceito=False, tamanho_texto=1200,
        correspondencias=m, ativos=ACERVO_POR_ID, deteccoes=[], eventos_similares_7d=0,
    )
    base.update(kw)
    return motor.avaliar(**base)


publico_corp = avaliar("ATV-001", "chatgpt_enterprise")
conf_corp = avaliar("ATV-020", "chatgpt_enterprise")
crit_corp = avaliar("ATV-031", "chatgpt_enterprise")
crit_deep = avaliar("ATV-031", "deepseek", canal="extensao")

checar(publico_corp.score < conf_corp.score < crit_corp.score,
       "piorar a classificação aumenta o score, mantida a ferramenta",
       f"{publico_corp.score} / {conf_corp.score} / {crit_corp.score}")
checar(crit_deep.score > crit_corp.score,
       "a mesma informação em ferramenta não homologada pontua mais",
       f"{crit_corp.score} vs {crit_deep.score}")
checar(publico_corp.nivel == "baixo" and crit_deep.nivel == "critico",
       "documento público em ferramenta corporativa é baixo; crítico em IA não homologada é crítico",
       f"{publico_corp.nivel} / {crit_deep.nivel}")

com_mascara = avaliar("ATV-031", "deepseek", canal="extensao", mascaramento_aceito=True)
checar(com_mascara.score < crit_deep.score,
       "aceitar o mascaramento reduz o score — o incentivo aponta na direção certa")

soma = sum(f.contribuicao for f in crit_deep.fatores)
checar(abs(soma - crit_deep.score) < 0.05,
       "a cadeia de evidências soma exatamente o score final",
       f"soma={soma:.2f} score={crit_deep.score}")
checar(all(f.explicacao for f in crit_deep.fatores),
       "todo fator da cadeia traz explicação em linguagem natural")

sem_nada = motor.avaliar(
    ts=quando, ferramenta_id="chatgpt_enterprise", canal="gateway", finalidade="pesquisar",
    finalidade_aprovada=False, mascaramento_aceito=False, tamanho_texto=200,
    correspondencias=[], ativos=ACERVO_POR_ID, deteccoes=[], eventos_similares_7d=0,
)
checar(sem_nada.nivel == "baixo",
       "uso cotidiano sem informação da empresa não gera alarme")


# =====================================================================
print("\n\033[1m4. Leitura da política sem dependências\033[0m")

from espia import yaml_min  # noqa: E402

bruto = Path("config/politica.yaml").read_text(encoding="utf-8")
proprio = yaml_min.safe_load(bruto)

try:
    import yaml as _pyyaml
    checar(proprio == _pyyaml.safe_load(bruto),
           "o leitor embutido produz exatamente o mesmo resultado que o PyYAML")
except ModuleNotFoundError:
    print("  \033[90m·\033[0m PyYAML não instalado — comparação pulada (o leitor embutido está em uso)")

checar(proprio["motor_risco"]["multiplicadores"]["treina_com_dados"] == 1.6
       and proprio["ferramentas_ia"][0]["treina_com_dados"] is False
       and proprio["ferramentas_ia"][5]["retencao_dias"] is None
       and proprio["categorias_informacao"]["clientes"]["marcos"] == ["LGPD", "SIGILO_BANCARIO"],
       "decimais, booleanos, nulos e listas em fluxo são lidos com o tipo certo")

checar(any("," in n["acao"] for n in proprio["motor_risco"]["niveis"]),
       "vírgula dentro de string entre aspas não quebra o mapa em fluxo")


# =====================================================================
print("\n\033[1m5. Base oficial do desafio\033[0m")

from espia import base_oficial as bo  # noqa: E402

BASE = bo.carregar()
checar(
    (len(BASE.eventos), len(BASE.alertas), len(BASE.ferramentas), len(BASE.tipos),
     len(BASE.usuarios), len(BASE.regras), len(BASE.casos)) == (650, 160, 8, 20, 72, 14, 15),
    "as doze abas são lidas com as contagens da planilha "
    "(650 eventos, 160 alertas, 8 ferramentas, 20 tipos, 72 usuários, 14 regras, 15 casos)",
    f"obtido: {len(BASE.eventos)}/{len(BASE.alertas)}/{len(BASE.ferramentas)}/"
    f"{len(BASE.tipos)}/{len(BASE.usuarios)}/{len(BASE.regras)}/{len(BASE.casos)}",
)

from collections import Counter  # noqa: E402

dist = Counter(e.sensibilidade for e in BASE.eventos)
checar(dict(dist) == {"Interna": 273, "Confidencial": 226, "Crítica": 108, "Pública": 43},
       "a distribuição de sensibilidade bate com a aba Divergencias_Apuradas da planilha",
       str(dict(dist)))

try:
    import openpyxl as _oxl

    from espia import xlsx_min as _xm
    _p = _xm.abrir(bo.CAMINHO_PADRAO)
    _wb = _oxl.load_workbook(bo.CAMINHO_PADRAO, data_only=True)
    checar(_p.abas == _wb.sheetnames and len(_p.tabela("Eventos_Uso_IA")) == 650,
           "o leitor de xlsx embutido concorda com o openpyxl")
    _p.close()
except ModuleNotFoundError:
    print("  \033[90m·\033[0m openpyxl não instalado — comparação pulada (o leitor embutido está em uso)")


# =====================================================================
print("\n\033[1m6. Motor das regras oficiais\033[0m")

from espia import regras as rgo  # noqa: E402
from espia import validacao as vlo  # noqa: E402

motor_of = rgo.MotorRegras(BASE)

res = vlo.Validador(BASE).resumo()
checar(res["passaram"] == res["total"],
       f"os {res['total']} casos de validação oficiais são reproduzidos sem exceção por caso",
       f"falharam: {res['falharam']}")

concord = sum(1 for e in BASE.eventos
              if motor_of.avaliar_evento(e).nivel == e.risco_declarado)
checar(concord / len(BASE.eventos) >= 0.98,
       f"o motor concorda com o risco declarado na base em {100*concord/len(BASE.eventos):.1f}% "
       "dos 650 eventos")

# precedência: credencial vence "ferramenta aprovada"
av = motor_of.avaliar(ferramenta_id="IA-03", informacao_id="INF-02",
                      sensibilidade="Crítica")
checar(av.nivel == "Crítico" and av.regra_principal == "R03",
       "credencial em ferramenta aprovada continua Crítico (R03 vem antes da ferramenta)",
       f"{av.nivel}/{av.regra_principal}")

# precedência: rastreabilidade vence tudo
av = motor_of.avaliar(ferramenta_id="", informacao_id="INF-02",
                      sensibilidade="Crítica", rastreavel=False)
checar(av.nivel == "REVISAR" and av.regra_principal == "R14",
       "sem usuário, ferramenta ou data confiáveis o motor recusa classificar (REVISAR)",
       f"{av.nivel}/{av.regra_principal}")

# contexto não eleva sozinho
sem_hora = motor_of.avaliar(ferramenta_id="IA-01", informacao_id="INF-15", sensibilidade="Interna")
com_hora = motor_of.avaliar(ferramenta_id="IA-01", informacao_id="INF-15",
                            sensibilidade="Interna", fora_horario=True)
checar(sem_hora.nivel == com_hora.nivel == "Baixo"
       and any(a.regra == "R12" for a in com_hora.achados),
       "horário fora do padrão entra como evidência (R12) sem elevar o nível")

# monotonicidade: piorar a ferramenta nunca reduz o risco
sev = rgo.SEVERIDADE
aprov = motor_of.avaliar(ferramenta_id="IA-01", informacao_id="INF-04", sensibilidade="Confidencial")
publ = motor_of.avaliar(ferramenta_id="IA-04", informacao_id="INF-04", sensibilidade="Confidencial")
checar(sev[publ.nivel] > sev[aprov.nivel],
       "a mesma informação numa ferramenta não aprovada pontua mais",
       f"{aprov.nivel} → {publ.nivel}")

checar(all(a.motivo and a.acao for av2 in
           (motor_of.avaliar_evento(e) for e in BASE.eventos[:120]) for a in av2.achados),
       "todo achado traz motivo e ação em linguagem natural")


# =====================================================================
print("\n\033[1m7. Auditoria\033[0m")

from espia import auditoria as auo  # noqa: E402

aud = auo.Auditoria(BASE)
inds = aud.indicadores()
checar(all(i.confere for i in inds),
       f"os {len(inds)} indicadores que recalculamos batem com a apuração da própria planilha",
       str([i.nome for i in inds if not i.confere]))
checar(sum(1 for i in inds if i.divergente) >= 5,
       "a maioria dos indicadores declarados diverge do que a base mostra")

ach = aud.achados()
checar(len(ach) >= 5 and all(a.consequencia and a.evidencia for a in ach),
       "cada achado de auditoria declara a consequência e onde ele é verificável")
ids = {a.id for a in ach}
checar({"A-01", "A-02", "A-03"} <= ids,
       "os três achados de gravidade alta são encontrados (regra incompatível, "
       "regra genérica, sub-classificação)")


# =====================================================================
print()
if falhas:
    print(f"\033[91m{falhas} verificação(ões) falharam.\033[0m")
    sys.exit(1)
print("\033[92mTodas as verificações passaram.\033[0m")
