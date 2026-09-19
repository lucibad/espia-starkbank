"""
GerencIA — Coletor de ingestão do espia-borda.

Recebe os eventos que a extensão (ou o agente de estação) envia, resolve a
identidade, grava em `capturas` e regenera o painel — que passa a mostrar a
base legada (Excel) e o presente (capturas) juntos, avaliados pelo mesmo motor.

    python3 run.py coletor                        # 127.0.0.1:8765
    ESPIA_BIND=0.0.0.0 python3 run.py coletor     # aberto à rede (Parallels)

Contrato (implantacao/coletores/extensao-gpo.json): POST /eventos.
Aceita também POST /api/ingest — é o que o agente de estação encaminha.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import captura as cp
from . import pipeline_oficial as po

BIND = os.environ.get("ESPIA_BIND", "127.0.0.1")
PORTA = int(os.environ.get("ESPIA_PORTA", "8765"))
CAMINHO_DB = po.DIR_DADOS / "espia.db"
USUARIO_LOCAL = getpass.getuser()   # quem roda o coletor nesta máquina

_regen_timer: threading.Timer | None = None
_regen_lock = threading.Lock()


def _conectar() -> sqlite3.Connection:
    po.DIR_DADOS.mkdir(exist_ok=True)
    con = sqlite3.connect(CAMINHO_DB, timeout=10)
    cp.garantir_esquema(con)
    return con


def _regenerar() -> None:
    """Roda o pipeline oficial: legado + capturas → SQLite → painel."""
    with _regen_lock:
        try:
            po.executar(verboso=False)
            print(f"  ↻ painel regenerado com {cp.contar(_conectar())} captura(s)", flush=True)
        except Exception as e:  # o coletor não pode cair por causa do painel
            print(f"  ! falha ao regenerar o painel: {e}", file=sys.stderr, flush=True)


def _agendar_regeneracao(atraso: float = 2.0) -> None:
    """Debounce: várias capturas seguidas geram um painel só."""
    global _regen_timer
    if _regen_timer:
        _regen_timer.cancel()
    _regen_timer = threading.Timer(atraso, _regenerar)
    _regen_timer.daemon = True
    _regen_timer.start()


def identidade(corpo: dict, remoto: bool) -> tuple[str, str]:
    """Quem gerou o evento — nunca decidido pela página.

    Local (mesma máquina): o usuário do SO que roda o coletor.
    Remoto (estação): confia no que um processo do SO informou —
    'agente-local' (agente de estação) ou 'nativo' (host de mensagens nativas).
    'declarado' é falsificável e fica marcado como tal.
    """
    if not remoto:
        return USUARIO_LOCAL, "so-local"
    u = str(corpo.get("usuario", "")).strip()[:64]
    fonte = corpo.get("usuario_fonte")
    if u and fonte in ("nativo", "agente-local"):
        return u, fonte
    if u:
        return u, "declarado"
    return "não identificado", "ausente"


def _eventos_recentes(limite: int = 200) -> list[dict]:
    """Capturas já avaliadas pelo motor (após o painel regenerar)."""
    con = _conectar()
    try:
        rows = con.execute(
            """SELECT e.id, e.ts, e.hora, e.usuario_id, e.area, e.ferramenta, e.informacao,
                      e.sensibilidade, e.risco_espia, e.regra_espia, e.origem,
                      c.usuario, c.identidade_fonte, c.dominio, c.maquina
               FROM eventos e JOIN capturas c ON c.cap_id = e.id
               ORDER BY e.ts DESC LIMIT ?""", (limite,)).fetchall()
        cols = ["id", "ts", "hora", "usuario_id", "area", "ferramenta", "informacao",
                "sensibilidade", "risco", "regra", "origem", "usuario", "fonte", "dominio", "maquina"]
        return [dict(zip(cols, r)) for r in rows]
    except sqlite3.OperationalError:
        # ainda sem `gerar`: devolve as capturas cruas
        rows = con.execute(
            "SELECT cap_id,ts,usuario,identidade_fonte,dominio,ferramenta,tipo,sens FROM capturas ORDER BY seq DESC LIMIT ?",
            (limite,)).fetchall()
        return [dict(zip(["id", "ts", "usuario", "fonte", "dominio", "ferramenta", "informacao", "sensibilidade"], r))
                | {"risco": "(aguardando gerar)", "regra": "", "origem": cp.ORIGEM_CAPTURA} for r in rows]
    finally:
        con.close()


class Coletor(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, corpo, status=200):
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 200_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _remoto(self) -> bool:
        return self.client_address[0] not in ("127.0.0.1", "::1", "localhost")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota == "/api/saude":
            con = _conectar()
            n = cp.contar(con)
            con.close()
            return self._json({"ok": True, "papel": "coletor-espia", "analista_local": USUARIO_LOCAL,
                               "capturas": n, "painel": str(po.DIR_PAINEL / "painel.html")})
        if rota == "/api/eventos":
            return self._json({"itens": _eventos_recentes()})
        if rota == "/api/inventario":
            con = _conectar()
            inv = cp.inventario(con)
            con.close()
            return self._json({"itens": [{"dominio": d, **m} for d, m in sorted(inv.items())],
                               "status_validos": list(cp.STATUS_VALIDOS),
                               "editavel": not self._remoto()})
        if rota in ("/", "/painel", "/painel.html"):
            painel = po.DIR_PAINEL / "painel.html"
            if not painel.exists():
                return self._json({"message": "painel ainda não gerado: rode python3 run.py gerar"}, 404)
            dados = painel.read_bytes()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(dados)
        return self._json({"code": "not_found"}, 404)

    def do_POST(self):
        rota = self.path.split("?")[0]
        if rota == "/api/inventario":
            # Só o admin, na máquina do coletor, muda o que é aprovado.
            if self._remoto():
                return self._json({"code": "somente_local",
                                   "message": "inventário só é editável na máquina do coletor"}, 403)
            corpo = self._corpo()
            try:
                con = _conectar()
                inv = cp.gravar_inventario(con, corpo.get("inventario", {}))
                con.close()
            except Exception as e:
                return self._json({"code": "erro_inventario", "message": str(e)[:160]}, 400)
            _agendar_regeneracao(0.5)   # o status novo reclassifica as capturas
            return self._json({"ok": True, "itens": len(inv), "painel_em": "~1s"})
        if rota not in ("/eventos", "/api/ingest"):
            return self._json({"code": "not_found"}, 404)
        corpo = self._corpo()
        usuario, fonte = identidade(corpo, self._remoto())
        try:
            con = _conectar()
            cap_id = cp.ingerir(con, corpo, usuario, fonte)
            con.close()
        except Exception as e:
            return self._json({"code": "erro_ingest", "message": str(e)[:160]}, 400)
        _agendar_regeneracao()
        return self._json({"ok": True, "id": cap_id, "usuario": usuario, "fonte": fonte,
                           "origem": cp.ORIGEM_CAPTURA, "painel_em": "~2s"})

    def log_message(self, fmt, *args):
        pass  # a trilha é o banco, não o stdout


def _enderecos() -> list[tuple[str, str]]:
    """IPs desta máquina alcançáveis por uma VM (Parallels primeiro)."""
    achados: list[tuple[str, str]] = []
    try:
        import re
        import subprocess
        saida = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout
        for ip in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", saida):
            if ip.startswith("10.211.55."):
                achados.append((ip, "Parallels · Compartilhada"))
            elif ip.startswith("10.37.129."):
                achados.append((ip, "Parallels · Host-Only"))
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and all(ip != a for a, _ in achados):
            achados.append((ip, "LAN · só em modo Bridge"))
    except OSError:
        pass
    return achados


def main() -> None:
    con = _conectar()
    n = cp.contar(con)
    con.close()
    srv = ThreadingHTTPServer((BIND, PORTA), Coletor)
    print(f"GerencIA · coletor ouvindo em {BIND}:{PORTA}")
    print(f"  painel:  http://127.0.0.1:{PORTA}/   (o mesmo de `run.py painel`, regenerado a cada captura)")
    if BIND == "0.0.0.0":
        for ip, rot in _enderecos():
            print(f"  das estações, aponte para: http://{ip}:{PORTA}  [{rot}]")
    else:
        print("  (só 127.0.0.1 — para receber das estações do Parallels: ESPIA_BIND=0.0.0.0)")
    print(f"  usuário local deste coletor: {USUARIO_LOCAL}")
    print(f"  banco: {CAMINHO_DB} · capturas já persistidas: {n}")
    print("  Excel = carga legada · capturas = presente · um motor, um painel")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
