#!/usr/bin/env python3
"""
EspIA — interface de linha de comando.

Base oficial do Desafio 2 · Stark Bank.

    python3 run.py gerar                    # processa a base e monta o painel
    python3 run.py painel                   # abre o painel no navegador

    python3 run.py panorama                 # números do período
    python3 run.py validar                  # os 15 casos oficiais
    python3 run.py auditar                  # indicadores e achados de rotulagem
    python3 run.py regras                   # as 14 regras e quantas vezes cada uma dispara

    python3 run.py rastrear "<termo>"       # BUSCA REVERSA — por informação ou por pessoa
    python3 run.py evidencia EVT-00123      # por que este evento é risco
    python3 run.py alertas [nível] [n]      # fila por nível de risco
    python3 run.py exposicao                # ranking de informação exposta

    python3 run.py classificar "<texto>"    # demonstra fingerprint + detectores
    python3 run.py sintetico                # gerador sintético (demo da camada de captura)
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit(
        f"EspIA precisa de Python 3.9 ou superior (encontrado {sys.version.split()[0]}).\n"
        "No macOS: brew install python@3.12 — ou rode com o python3 mais novo que você tiver."
    )

sys.path.insert(0, str(Path(__file__).resolve().parent))

from espia import consultas, pipeline_oficial  # noqa: E402


def _abrir():
    if not consultas.CAMINHO_DB.exists():
        print("Banco não encontrado. Rode primeiro:  python3 run.py gerar")
        sys.exit(1)
    return consultas.conectar()


def _n(v) -> str:
    return f"{v:,}".replace(",", ".")


def main() -> None:
    args = sys.argv[1:]
    comando = args[0] if args else "ajuda"

    # ---------------------------------------------------------------
    if comando == "gerar":
        pipeline_oficial.executar()

    elif comando == "painel":
        import json
        import webbrowser
        painel = pipeline_oficial.DIR_PAINEL / "painel.html"
        origem = pipeline_oficial.DIR_DADOS / "dashboard.json"
        if not painel.exists():
            if not origem.exists():
                print("Nada para mostrar ainda. Rode primeiro:  python3 run.py gerar")
                sys.exit(1)
            pipeline_oficial.exportar_painel(json.loads(origem.read_text(encoding="utf-8")))
        print(f"Abrindo {painel}")
        if not webbrowser.open(painel.as_uri()):
            print("Não consegui abrir o navegador daqui. Abra este arquivo manualmente:")
            print(f"  {painel}")

    # ---------------------------------------------------------------
    elif comando == "panorama":
        con = _abrir()
        p = consultas.panorama(con)
        consultas.cab("Panorama — base oficial do desafio")
        print(f"Eventos de IA ................................ {_n(p['eventos'])}")
        print(f"Alertas registrados .......................... {_n(p['alertas'])}")
        print(f"Usuários com uso de IA ....................... {p['usuarios']}")
        print(f"Ferramentas de IA em uso ..................... {p['ferramentas']}")
        print(f"Com informação confidencial ou crítica ....... {_n(p['sensiveis'])}"
              f"  ({100*p['sensiveis']/p['eventos']:.1f}%)")
        print(f"Em ferramenta não aprovada ................... {_n(p['nao_aprovadas'])}"
              f"  ({100*p['nao_aprovadas']/p['eventos']:.1f}%)")
        print()
        print("Risco apurado pela EspIA        Risco declarado na base")
        for nivel in ("Crítico", "Alto", "Médio", "Baixo", "REVISAR"):
            a = p["por_risco"].get(nivel, 0)
            b = p["por_risco_base"].get(nivel, 0)
            print(f"  {nivel:<10} {a:>6}                    {b:>6}")
        print()
        print(f"Divergências entre os dois ................... {p['divergentes']}")
        print(f"Casos de validação oficiais reproduzidos ..... {p['validacao_ok']}/{p['validacao_total']}")
        print(f"Indicadores declarados que divergem .......... {p['indicadores_divergentes']}/{p['indicadores_total']}")
        print(f"Nossa apuração confere com a da planilha ..... {p['indicadores_conferem']}/{p['indicadores_total']}")

    # ---------------------------------------------------------------
    elif comando == "validar":
        con = _abrir()
        linhas = consultas.validacao(con)
        ok = sum(1 for x in linhas if x["passou"])
        consultas.cab(f"Casos de validação oficiais — {ok}/{len(linhas)} reproduzidos")
        for x in linhas:
            marca = "\033[92m✓\033[0m" if x["passou"] else "\033[91m✗\033[0m"
            print(f"{marca} {x['caso']}  esperado {x['esperado']:<9} obtido {x['obtido']:<9} "
                  f"regra {x['regra']:<5} | {x['ferramenta']} + {x['informacao']}")
        if ok < len(linhas):
            sys.exit(1)

    # ---------------------------------------------------------------
    elif comando == "auditar":
        con = _abrir()
        consultas.cab("Indicadores — declarado × apurado")
        print(f"{'indicador':<44}{'declarado':<14}{'apurado':<15}{'planilha':<14}confere")
        for i in consultas.indicadores(con):
            marca = "sim" if i["confere"] else "NÃO"
            alerta = "  \033[91m← diverge\033[0m" if i["divergente"] else ""
            print(f"{i['nome'][:43]:<44}{i['declarado']:<14}{i['apurado']:<15}"
                  f"{i['planilha']:<14}{marca}{alerta}")

        consultas.cab("Achados de auditoria")
        for a in consultas.auditoria(con):
            print(f"\n[{a['id']}] ({a['gravidade']}) {a['titulo']}")
            print(f"   {a['resumo']}")
            print(f"   → {a['consequencia']}")
            print(f"   verificável em: {a['evidencia']}")
            if a["n_eventos"]:
                amostra = ", ".join(a["eventos"][:6])
                print(f"   {a['n_eventos']} item(ns) afetado(s): {amostra}"
                      + (" …" if a["n_eventos"] > 6 else ""))

    # ---------------------------------------------------------------
    elif comando == "regras":
        con = _abrir()
        consultas.cab("As 14 regras da política")
        print(f"{'id':<5}{'nível':<9}{'usos na base':>13}{'usos no motor':>15}   tema")
        for r in consultas.regras(con):
            morta = "  \033[91m← nunca acionada na base\033[0m" if r["usos_base"] == 0 else ""
            print(f"{r['id']:<5}{r['nivel']:<9}{r['usos_base']:>13}{r['usos_espia']:>15}   "
                  f"{r['tema']}{morta}")

    # ---------------------------------------------------------------
    elif comando == "rastrear":
        if len(args) < 2:
            print('Uso: python3 run.py rastrear "Chave/API secret"')
            sys.exit(1)
        consultas.imprimir_linhagem(_abrir(), args[1])

    elif comando == "evidencia":
        if len(args) < 2:
            print("Uso: python3 run.py evidencia EVT-00123")
            sys.exit(1)
        consultas.imprimir_evidencia(_abrir(), args[1])

    elif comando == "alertas":
        con = _abrir()
        nivel = args[1] if len(args) > 1 else "Crítico"
        limite = int(args[2]) if len(args) > 2 else 20
        linhas = consultas.alertas(con, nivel, limite)
        consultas.cab(f"Eventos de risco {nivel} ({len(linhas)} exibidos)")
        for a in linhas:
            div = f"  base: {a['risco_base']}" if a["divergente"] else ""
            st = f"  [{a['status']}]" if a["status"] else ""
            print(f"{a['id']}  {a['ts'][:16].replace('T',' ')}  {a['regra']:<5} {a['pessoa']:<22} "
                  f"{a['ferramenta']:<26} {a['informacao'][:28]:<30}{st}{div}")
        print("\nUse:  python3 run.py evidencia <ID>   para ver a cadeia completa.")

    elif comando == "exposicao":
        con = _abrir()
        consultas.cab("Informação mais exposta a ferramentas de IA")
        print(f"{'TIPO DE INFORMAÇÃO':<40}{'CLASSIF.':<15}{'USOS':>6}{'PESSOAS':>9}"
              f"{'FORA':>6}{'RISCO':>7}")
        for x in consultas.exposicao(con):
            print(f"{x['nome'][:38]:<40}{x['sensibilidade']:<15}{x['eventos']:>6}"
                  f"{x['pessoas']:>9}{x['fora_politica']:>6}{x['em_risco']:>7}")

    # ---------------------------------------------------------------
    elif comando == "classificar":
        if len(args) < 2:
            print('Uso: python3 run.py classificar "texto que iria para a IA"')
            sys.exit(1)
        _classificar(args[1])

    elif comando == "sintetico":
        from espia import pipeline
        print("Gerador sintético — demonstra a camada de captura (fingerprint + detectores).")
        print("A base oficial continua sendo a fonte do painel.\n")
        pipeline.executar()

    else:
        print(__doc__)


# ---------------------------------------------------------------------


def _classificar(texto: str) -> None:
    """Mostra como as colunas 'Tipo informação' e 'Sensibilidade' seriam preenchidas.

    Na base oficial elas chegam prontas — o dicionário de dados diz que a origem é
    'Classificador/DLP'. Este comando demonstra a camada que produz esse resultado.
    """
    from espia import detectores
    from espia.acervo import ACERVO_POR_ID
    from espia.fingerprint import Assinatura, casar
    from espia.pipeline import carregar_politica, construir_catalogo_assinaturas

    politica = carregar_politica()
    cfg = politica["fingerprint"]
    catalogo = construir_catalogo_assinaturas(politica)
    assinatura = Assinatura.de_texto(texto, n=cfg["tamanho_shingle"],
                                     num_perm=cfg["permutacoes_minhash"])
    achados = casar(assinatura, catalogo, cfg["limiar_correspondencia"],
                    cfg["limiar_alta_confianca"])
    deteccoes = detectores.detectar(texto)

    consultas.cab("Classificação automática do conteúdo")
    print(f"{len(texto)} caracteres · {assinatura.n_shingles} fragmentos · "
          f"assinatura {hex(assinatura.simhash)}\n")

    if achados:
        print("Ativos do acervo reconhecidos:")
        for c in achados[:5]:
            a = ACERVO_POR_ID[c.ativo_id]
            print(f"  ▸ {a.nome}")
            print(f"    {c.score:.0%} de correspondência ({c.confianca} confiança) · "
                  f"classificação {a.classificacao}")
    else:
        print("Nenhum ativo do acervo reconhecido neste texto.")

    print()
    if deteccoes:
        print("Dado sensível detectado (tipo e contagem — nunca o valor):")
        for d in deteccoes:
            selo = " validado" if d.validado else ""
            print(f"  ▸ {d.contagem}× {d.tipo.replace('_',' ')}{selo}")
        mascarado, n = detectores.mascarar(texto)
        print(f"\nO mascaramento removeria {n} identificador(es). Versão que sairia:")
        print("  " + mascarado.replace("\n", "\n  ")[:600])
    else:
        print("Nenhum dado pessoal, cartão ou credencial detectado.")

    print("\nO texto analisado não é gravado: só a assinatura e as contagens acima.")


if __name__ == "__main__":
    main()
