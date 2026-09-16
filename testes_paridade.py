#!/usr/bin/env python3
"""
EspIA — teste de paridade entre o motor Python e o motor JavaScript.

O console de políticas simula o impacto de uma mudança reavaliando os 650
eventos no navegador. Se o motor JavaScript divergir do Python nem que seja em
um evento, a simulação mente — e uma simulação que mente é pior que nenhuma,
porque dá confiança onde não deveria.

Este teste roda os dois sobre a mesma base, com a mesma política, e compara
evento a evento e caso a caso.

    python3 testes_paridade.py

Precisa do Node.js apenas para executar o motor JavaScript. Se o Node não
estiver instalado, o teste avisa e sai sem falhar — o resto do projeto continua
rodando com Python puro.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PAYLOAD = RAIZ / "dados" / "dashboard.json"
MOTOR_JS = RAIZ / "dashboard" / "motor.js"

PONTE = r"""
// Ponte mínima: carrega o motor do navegador dentro do Node e devolve o que ele
// calculou, para o Python comparar com o próprio resultado.
const fs = require('fs');
global.window = global;
require(process.argv[2]);                       // define window.ESPIA_MOTOR
const D = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const { Motor, politicaDoPayload } = global.ESPIA_MOTOR;
const motor = new Motor(
  { ferramentas: D.ferramentas, tipos: D.tipos, regras: D.politica.regras },
  politicaDoPayload(D)
);

const eventos = D.eventos.map(e => {
  const r = motor.avaliarEvento(e);
  return { id: e.id, nivel: r.nivel, regra: r.regra,
           regras: r.achados.map(a => a.regra).sort() };
});
const casos = D.validacao.map(c => {
  const r = motor.avaliarCaso(c);
  return { caso: c.caso, nivel: r.nivel, regra: r.regra };
});
process.stdout.write(JSON.stringify({ eventos, casos }));
"""

VERDE, VERMELHO, CINZA, FIM = "\033[92m", "\033[91m", "\033[90m", "\033[0m"


def main() -> int:
    if not PAYLOAD.exists():
        print("Base não gerada ainda. Rode primeiro:  python3 run.py gerar")
        return 1

    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        print(f"{CINZA}Node.js não encontrado — teste de paridade pulado.{FIM}")
        print("O motor JavaScript só é usado pelo console de políticas, no navegador.")
        print("Para rodar este teste:  instale o Node.js e execute de novo.")
        return 0

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(PONTE)
        ponte = fh.name

    try:
        saida = subprocess.run(
            [node, ponte, str(MOTOR_JS), str(PAYLOAD)],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        Path(ponte).unlink(missing_ok=True)

    if saida.returncode != 0:
        print(f"{VERMELHO}O motor JavaScript não rodou:{FIM}\n{saida.stderr[:2000]}")
        return 1

    js = json.loads(saida.stdout)
    py = json.loads(PAYLOAD.read_text(encoding="utf-8"))

    falhas = 0

    # --- eventos ------------------------------------------------------
    esperado = {e["id"]: e for e in py["eventos"]}
    dif_nivel, dif_regra, dif_cadeia = [], [], []

    for r in js["eventos"]:
        alvo = esperado.get(r["id"])
        if alvo is None:
            dif_nivel.append((r["id"], "—", r["nivel"]))
            continue
        if r["nivel"] != alvo["risco"]:
            dif_nivel.append((r["id"], alvo["risco"], r["nivel"]))
        if r["regra"] != alvo["regra"]:
            dif_regra.append((r["id"], alvo["regra"], r["regra"]))
        cadeia_py = sorted(a["regra"] for a in alvo["achados"])
        if r["regras"] != cadeia_py:
            dif_cadeia.append((r["id"], cadeia_py, r["regras"]))

    n = len(js["eventos"])
    print(f"\n\033[1mParidade entre o motor Python e o motor do navegador\033[0m")
    print("─" * 60)
    print(f"  base: {n} eventos · {len(js['casos'])} casos de validação\n")

    def checar(ok: bool, desc: str, amostra=None) -> None:
        nonlocal falhas
        if ok:
            print(f"  {VERDE}✓{FIM} {desc}")
        else:
            falhas += 1
            print(f"  {VERMELHO}✗{FIM} {desc}")
            for x in (amostra or [])[:5]:
                print(f"      {x}")

    checar(len(js["eventos"]) == len(py["eventos"]),
           f"os dois motores avaliam os mesmos {n} eventos")
    checar(not dif_nivel, "mesmo nível de risco em todos os eventos", dif_nivel)
    checar(not dif_regra, "mesma regra principal em todos os eventos", dif_regra)
    checar(not dif_cadeia, "mesma cadeia de regras aplicáveis em todos os eventos", dif_cadeia)

    # --- casos de validação -------------------------------------------
    esperado_caso = {c["caso"]: c for c in py["validacao"]}
    dif_caso = [
        (c["caso"], esperado_caso[c["caso"]]["obtido"], c["nivel"])
        for c in js["casos"]
        if c["caso"] in esperado_caso and c["nivel"] != esperado_caso[c["caso"]]["obtido"]
    ]
    checar(not dif_caso, "mesmo resultado nos 15 casos oficiais", dif_caso)

    todos_passam = all(
        c["nivel"].strip().upper() == esperado_caso[c["caso"]]["esperado"].strip().upper()
        for c in js["casos"] if c["caso"] in esperado_caso
    )
    checar(todos_passam, "o motor do navegador também reproduz o gabarito oficial")

    print()
    if falhas:
        print(f"{VERMELHO}{falhas} verificação(ões) falharam — a simulação do console "
              f"não é confiável enquanto isso não for corrigido.{FIM}")
        return 1
    print(f"{VERDE}Os dois motores concordam em tudo.{FIM}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
