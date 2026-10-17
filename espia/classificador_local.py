"""
GerencIA · classificador local (Nível 1) — LLM on-premise via llamafile + Qwen3.

É o PRIMEIRO nível de classificação por IA do conteúdo capturado pela extensão:
o texto do prompt/resposta é classificado por um LLM que roda NA PRÓPRIA MÁQUINA
(llamafile servindo um modelo Qwen3 do Hugging Face), então o conteúdo NÃO sai do
perímetro. Só o resíduo ambíguo (baixa confiança) sobe para o LLM na nuvem (Nível 2).

Cascata de classificação do conteúdo:
    Nível 0  detectores determinísticos (CPF/CNPJ/Luhn/credencial)  — em captura.py
    Nível 1  este módulo: Qwen3 local, on-premise                   — tipo + sensibilidade
    Nível 2  claude-opus-5 (nuvem), só quando a confiança local é baixa

Configuração (ambiente):
    GERENCIA_LLM_LOCAL    URL do llamafile (padrão http://127.0.0.1:8090)
    GERENCIA_LLM_TIMEOUT  segundos por chamada (padrão 12)
    GERENCIA_LLM_MIN_CONF confiança mínima p/ aceitar o Nível 1 (padrão 0.55)

Degrada com elegância: se o llamafile não estiver no ar, classificar() devolve
None na hora (conexão recusada) e o coletor segue com o Nível 0.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

URL = os.environ.get("GERENCIA_LLM_LOCAL", "http://127.0.0.1:8090").rstrip("/")
TIMEOUT = float(os.environ.get("GERENCIA_LLM_TIMEOUT", "12"))
MIN_CONF = float(os.environ.get("GERENCIA_LLM_MIN_CONF", "0.55"))

SENSIBILIDADES = ("Pública", "Interna", "Confidencial", "Crítica")

# Vocabulário de tipos da base oficial — o Nível 1 deve escolher DESTA lista
# (mantém o presente no mesmo vocabulário do legado).
TIPOS = [
    "Dado pessoal (CPF)", "Dados cadastrais de cliente", "Dados financeiros de cliente",
    "Contrato de cliente", "Proposta comercial", "Pipeline de vendas",
    "Resultado financeiro não divulgado", "Projeção de receita/EBITDA",
    "Chave/API secret", "Código-fonte", "Arquitetura técnica",
    "Estratégia de lançamento", "Parecer jurídico", "Avaliação de desempenho",
    "Folha/remuneração", "Currículo de candidato", "Ata de reunião interna",
    "Ticket de atendimento anonimizado", "Dados agregados anonimizados",
    "Campanha já publicada", "Documento público/regulatório",
    "Conteúdo não classificado",
]

_SISTEMA = (
    "Você é um classificador de governança de informação do Stark Bank. "
    "Dado o CONTEÚDO que um funcionário enviou a uma ferramenta de IA, classifique:\n"
    "1) tipo: escolha EXATAMENTE um item da lista de tipos fornecida;\n"
    "2) sensibilidade: um de Pública, Interna, Confidencial, Crítica;\n"
    "3) confianca: a SUA confiança real na classificação, número entre 0 e 1 "
    "(ex.: 0.95 quando é evidente, 0.4 quando é ambíguo). "
    "NUNCA devolva 0 por padrão — avalie de verdade.\n"
    "Responda SOMENTE um objeto JSON, sem comentários, no formato "
    '{"tipo":<um item exato da lista>,"sensibilidade":<Pública|Interna|Confidencial|Crítica>,'
    '"confianca":<número entre 0 e 1>}. Não explique.'
)


def _snap_tipo(t: str) -> str:
    t = (t or "").strip()
    for v in TIPOS:
        if t.lower() == v.lower():
            return v
    for v in TIPOS:                      # correspondência parcial
        if t and (t.lower() in v.lower() or v.lower() in t.lower()):
            return v
    return "Conteúdo não classificado"


def _extrair_json(txt: str) -> dict | None:
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def classificar(texto: str, tipos: list[str] | None = None) -> dict | None:
    """Classifica o conteúdo com o Qwen3 local. Devolve
    {tipo, sensibilidade, confianca, classificado_por:'llm-local'} ou None."""
    texto = (texto or "").strip()
    if len(texto) < 2:
        return None
    lista = tipos or TIPOS
    usuario = (
        "Tipos permitidos: " + " | ".join(lista) + "\n\n"
        "CONTEÚDO:\n" + texto[:4000] + "\n\n/no_think"   # Qwen3: desliga o raciocínio
    )
    corpo = {
        "model": "local",
        "messages": [{"role": "system", "content": _SISTEMA},
                     {"role": "user", "content": usuario}],
        "temperature": 0,
        "max_tokens": 120,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            URL + "/v1/chat/completions",
            data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            resp = json.load(r)
        conteudo = resp["choices"][0]["message"]["content"]
    except Exception:
        return None  # llamafile fora do ar / erro → cai para o Nível 0
    # Qwen3 pode emitir um bloco <think>…</think> mesmo com /no_think em alguns builds
    conteudo = re.sub(r"<think>.*?</think>", "", conteudo, flags=re.DOTALL)
    j = _extrair_json(conteudo)
    if not j:
        return None
    sens = str(j.get("sensibilidade", "")).strip().capitalize()
    sens = next((s for s in SENSIBILIDADES if s.lower() == sens.lower()), None)
    if not sens:
        return None
    try:
        conf = float(j.get("confianca", 0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "tipo": _snap_tipo(str(j.get("tipo", ""))),
        "sensibilidade": sens,
        "confianca": round(conf, 2),
        "classificado_por": "llm-local",
    }


def resumir(texto: str, limite: int = 400) -> str | None:
    """Resumo curto (on-premise, Qwen3) do conteúdo de um anexo — para avaliar o
    que o arquivo contém sem guardar o arquivo inteiro. Devolve o resumo ou None."""
    texto = (texto or "").strip()
    if len(texto) < 2:
        return None
    corpo = {
        "model": "local",
        "messages": [
            {"role": "system", "content": "Você resume, em português, o conteúdo de um "
             "documento para governança de informação. Produza um resumo objetivo de 2 a 4 "
             "frases, dizendo do que trata e se há indícios de dado sensível (pessoal, "
             "financeiro, segredo). Não invente. Responda só o resumo, sem título."},
            {"role": "user", "content": "DOCUMENTO:\n" + texto[:6000] + "\n\n/no_think"},
        ],
        "temperature": 0,
        "max_tokens": 220,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            URL + "/v1/chat/completions",
            data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            resp = json.load(r)
        out = resp["choices"][0]["message"]["content"]
    except Exception:
        return None
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
    return out[:limite] or None


def disponivel() -> bool:
    """Checa rápido se o llamafile responde (para logs/health)."""
    try:
        with urllib.request.urlopen(URL + "/v1/models", timeout=3) as r:
            return r.status < 500
    except Exception:
        return False
