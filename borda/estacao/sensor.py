#!/usr/bin/env python3
"""
GerencIA · sensor de rede da estação.

Complementa a extensão de navegador. A extensão vê o CONTEÚDO que o usuário
digita numa IA no navegador (antes de cifrar). O sensor vê que a MÁQUINA falou
com uma IA — de QUALQUER programa: app de desktop do ChatGPT, Cursor, um script
Python, o Copilot do Windows. Assim a governança não depende de a IA ter sido
usada dentro do navegador.

Como ele detecta, sem MITM e sem ler conteúdo — três sinais que se somam:

  1. Índice de IPs: resolve periodicamente a lista de domínios de IA para os
     IPs que elas usam agora, e casa as conexões de saída contra esse índice.
     (DNS reverso puro não serve: os IPs são de CDN e não voltam para o nome.)
  2. Cache de DNS do Windows (`ipconfig /displaydns`): prova que a máquina
     CONSULTOU um hostname de IA — o nome exato, sem interceptar nada.
  3. Processo dono da conexão (PID → nome do .exe): diz de qual aplicativo
     partiu, para o registro citar "cursor.exe" e não só "porta 443".

O que ele NÃO faz, dito na cara: não lê o conteúdo — o tráfego é TLS; ler o
texto exigiria instalar uma CA de interceptação na máquina, o que este projeto
não faz. O sensor reporta METADADO ("a estação X falou com a API da OpenAI às
14h pelo cursor.exe"), não o prompt. Quem lê conteúdo é a extensão. E há um
resíduo de falso-positivo: um IP de CDN compartilhado (Cloudflare) pode servir
outro site além da IA; por isso cada evento carrega o sinal que o gerou
(`via`) e o coletor trata metadado sem risco declarado.

Uso (roda no macOS/Linux para teste e no Windows em produção):
    python3 sensor.py testar      # uma varredura, imprime o que casou
    python3 sensor.py rodar       # laço contínuo em primeiro plano (Ctrl+C sai)
    python3 sensor.py servico ... # subcomandos do serviço do Windows

Variáveis de ambiente:
    GERENCIA_COLETOR   URL do coletor central (ex.: http://10.211.55.2:8765).
                       Sem ela, o sensor só imprime — não envia.
    GERENCIA_INTERVALO segundos entre varreduras (padrão 15)
    GERENCIA_JANELA    segundos p/ não repetir o mesmo processo+ferramenta (padrão 900)
"""
from __future__ import annotations

import getpass
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

COLETOR = os.environ.get("GERENCIA_COLETOR", "").strip().rstrip("/")
INTERVALO = int(os.environ.get("GERENCIA_INTERVALO", "15"))
JANELA = int(os.environ.get("GERENCIA_JANELA", "900"))
MAQUINA = socket.gethostname()
WIN = platform.system() == "Windows"

# Sufixo de domínio → nome amigável. O status (aprovada/não) é do inventário,
# no coletor — o sensor só observa, como a extensão.
DOMINIOS_IA = {
    "openai.com": "ChatGPT (OpenAI)",
    "chatgpt.com": "ChatGPT (OpenAI)",
    "anthropic.com": "Claude (Anthropic)",
    "claude.ai": "Claude (Anthropic)",
    "gemini.google.com": "Gemini (Google)",
    "generativelanguage.googleapis.com": "Gemini (Google)",
    "copilot.microsoft.com": "Copilot (Microsoft)",
    "deepseek.com": "DeepSeek",
    "perplexity.ai": "Perplexity",
    "poe.com": "Poe",
    "huggingface.co": "HuggingChat",
    "meta.ai": "Meta AI",
    "x.ai": "Grok (xAI)",
    "grok.com": "Grok (xAI)",
    "cursor.sh": "Cursor",
    "cursor.com": "Cursor",
}

_ip_index: dict[str, str] = {}       # ip → nome da ferramenta
_ip_index_em: float = 0.0
_visto: dict[tuple, float] = {}       # (usuario, processo, ferramenta) → último envio


def _agora() -> str:
    # Hora LOCAL (como o coletor e a extensão), para não aparecer no futuro no painel.
    return datetime.now().replace(microsecond=0).isoformat()


def _publico(ip: str) -> bool:
    if ":" in ip:
        return not (ip.startswith("fe80") or ip == "::1")
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        return False
    a, b, *_ = (int(x) for x in ip.split("."))
    if a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254):
        return False
    return True


def _reindexar(forcar: bool = False) -> None:
    """Resolve cada domínio de IA para seus IPs atuais e monta o índice."""
    global _ip_index, _ip_index_em
    if not forcar and time.time() - _ip_index_em < 600 and _ip_index:
        return
    novo: dict[str, str] = {}
    for dom, nome in DOMINIOS_IA.items():
        try:
            for fam in socket.getaddrinfo(dom, 443, proto=socket.IPPROTO_TCP):
                ip = fam[4][0]
                if _publico(ip):
                    novo.setdefault(ip, nome)
        except (OSError, socket.gaierror):
            continue
    if novo:
        _ip_index = novo
        _ip_index_em = time.time()


def _casar_suf(host: str) -> str | None:
    for suf, nome in DOMINIOS_IA.items():
        if host == suf or host.endswith("." + suf):
            return nome
    return None


def _cache_dns() -> dict[str, str]:
    """Hostnames de IA presentes no cache de DNS do Windows → ferramenta.
    É a prova de que a máquina CONSULTOU o nome (sinal mais forte, sem CDN)."""
    achados: dict[str, str] = {}
    if not WIN:
        return achados
    try:
        txt = subprocess.run(["ipconfig", "/displaydns"], capture_output=True,
                             text=True, timeout=10, errors="ignore").stdout
    except (OSError, subprocess.SubprocessError):
        return achados
    for host in re.findall(r"([A-Za-z0-9._-]+\.[A-Za-z]{2,})", txt):
        nome = _casar_suf(host.lower().rstrip("."))
        if nome:
            achados[host.lower().rstrip(".")] = nome
    return achados


def _conexoes() -> list[tuple[str, int, int]]:
    """(ip_remoto, porta, pid) das conexões TCP estabelecidas de saída."""
    saida: list[tuple[str, int, int]] = []
    try:
        import psutil
        for c in psutil.net_connections(kind="tcp"):
            if c.status == "ESTABLISHED" and c.raddr and c.raddr.ip and _publico(c.raddr.ip):
                saida.append((c.raddr.ip, c.raddr.port, c.pid or 0))
        return saida
    except Exception:
        pass
    cmd = ["netstat", "-ano"] if WIN else ["netstat", "-n"]
    try:
        txt = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return saida
    for ln in txt.splitlines():
        if "ESTAB" not in ln.upper():          # Windows: ESTABLISHED · BSD: ESTABLISHED
            continue
        campos = ln.split()
        if not campos or not campos[0].upper().startswith("TCP"):
            continue
        # Windows:  TCP  local  foreign  ESTABLISHED  pid   -> foreign = campos[2]
        # macOS/BSD: tcp6 0 0 local foreign ESTABLISHED     -> foreign vem antes do estado
        if WIN:
            remoto, pid = campos[2], (int(campos[-1]) if campos[-1].isdigit() else 0)
        else:
            est = next((i for i, c in enumerate(campos) if "ESTAB" in c.upper()), len(campos))
            remoto, pid = campos[est - 1], 0
        ip, porta = _sep_host_porta(remoto)
        if ip and _publico(ip):
            saida.append((ip, porta, pid))
    return saida


def _sep_host_porta(remoto: str) -> tuple[str, int]:
    """Separa 'ip:porta', '[v6]:porta' (Windows) e 'ip.porta'/'v6.porta' (BSD)."""
    remoto = remoto.strip()
    m = re.match(r"^\[(.+)\]:(\d+)$", remoto)            # [v6]:porta
    if m:
        return m.group(1), int(m.group(2))
    # BSD (macOS/Linux) usa '.' como separador da porta; Windows usa ':'
    if not WIN and re.search(r"\.\d+$", remoto):
        host, _, porta = remoto.rpartition(".")
        return host.strip("[]"), int(porta) if porta.isdigit() else 0
    host, _, porta = remoto.rpartition(":")
    return host.strip("[]"), int(porta) if porta.isdigit() else 0


def _processo(pid: int) -> str:
    if not pid:
        return ""
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        pass
    if WIN:
        try:
            txt = subprocess.run(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                                 capture_output=True, text=True, timeout=8).stdout
            return txt.split(",")[0].strip().strip('"') if txt.strip() else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""


def _dom_base(nome: str) -> str:
    for suf, n in DOMINIOS_IA.items():
        if n == nome:
            return suf
    return nome


def _enviar(evt: dict) -> bool:
    if not COLETOR:
        return False
    corpo = json.dumps(evt).encode("utf-8")
    for rota in ("/api/ingest", "/eventos"):
        try:
            req = urllib.request.Request(COLETOR + rota, data=corpo,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                if r.status < 300:
                    return True
        except Exception:
            continue
    return False


def _usuario_logado() -> str:
    """Quem está de fato usando a máquina — não a conta do serviço.

    Como serviço (LocalSystem), getpass.getuser() devolve 'SYSTEM'/conta da
    máquina, não a pessoa logada. Descobrimos o usuário interativo real:
      1) dono do explorer.exe (o shell da sessão logada);
      2) `quser` (sessão ativa do console);
      3) por último, getpass (quando rodando interativo, já é o certo).
    """
    # 1) dono do explorer.exe
    try:
        import psutil
        for p in psutil.process_iter(["name", "username"]):
            if (p.info.get("name") or "").lower() == "explorer.exe":
                u = p.info.get("username") or ""
                if u:
                    return u.split("\\")[-1]  # tira DOMINIO\
    except Exception:
        pass
    # 2) quser (sessão ativa)
    if WIN:
        try:
            out = subprocess.run(["quser"], capture_output=True, text=True,
                                 timeout=8, errors="ignore").stdout.splitlines()
            ativa = next((l for l in out[1:] if "Ativo" in l or "Active" in l), None)
            linha = ativa or (out[1] if len(out) > 1 else "")
            if linha:
                return linha.split()[0].lstrip(">").strip()
        except Exception:
            pass
    # 3) fallback
    return getpass.getuser()


def varrer(imprimir: bool = False) -> int:
    """Detecta uso de IA e emite eventos.

    No Windows o CACHE DE DNS é a autoridade: só reporta as ferramentas cujo
    hostname a máquina realmente consultou (chatgpt.com, gemini.google.com…).
    Isso elimina o falso-positivo de IP de CDN compartilhado (Cloudflare serve
    várias IAs no mesmo IP). As conexões ativas só enriquecem com o processo.
    Fora do Windows (sem esse cache) cai no índice de IPs, best-effort.
    """
    _reindexar()
    usuario = _usuario_logado()
    agora = time.time()
    cache = _cache_dns()                     # {host: nome} no Windows; {} fora
    novos = 0
    achou: dict[tuple, dict] = {}

    # Conexões ativas casadas por IP → uma entrada por ferramenta (para o processo).
    conn_por_ferr: dict[str, tuple] = {}
    for ip, porta, pid in _conexoes():
        nome = _ip_index.get(ip)
        if nome and nome not in conn_por_ferr:
            conn_por_ferr[nome] = (ip, porta, pid)

    if WIN and cache:
        # Autoridade: o que a máquina consultou. Sem ruído de CDN.
        for host, nome in cache.items():
            ip, porta, pid = conn_por_ferr.get(nome, ("", 0, 0))
            proc = _processo(pid) if pid else ""
            via = "ip+dns" if nome in conn_por_ferr else "dns"
            achou[(usuario, proc, nome)] = {"ferramenta": nome, "processo": proc,
                                            "ip": ip, "porta": porta, "via": via, "host": host}
    else:
        # macOS/Linux (sem cache de DNS): índice de IPs.
        for nome, (ip, porta, pid) in conn_por_ferr.items():
            proc = _processo(pid)
            achou[(usuario, proc, nome)] = {"ferramenta": nome, "processo": proc,
                                            "ip": ip, "porta": porta, "via": "ip"}

    for chave, d in achou.items():
        if agora - _visto.get(chave, 0) < JANELA:
            continue
        _visto[chave] = agora
        evt = {
            "ts": _agora(), "usuario": usuario, "usuario_fonte": "agente-local",
            "maquina": MAQUINA, "dominio": _dom_base(d["ferramenta"]),
            "ferramenta": d["ferramenta"], "processo": d.get("processo", ""),
            "ip": d.get("ip", ""), "porta": d.get("porta", 0), "via": d["via"],
            "forma": "Conexão de rede", "modo": "sensor",
            "host": d.get("host", ""), "tipo": "Uso de IA detectado na rede",
            "sens": "", "conteudo": "", "origem_sensor": "Sensor de rede (GerencIA)",
        }
        enviado = _enviar(evt)
        novos += 1
        if imprimir or not COLETOR:
            selo = "→ enviado" if enviado else ("(sem coletor)" if not COLETOR else "! falha")
            alvo = d.get("host") or d.get("ip") or "?"
            print(f"  {evt['ts']}  {usuario:<14} {d['ferramenta']:<20} "
                  f"{(d.get('processo') or '·'):<16} {alvo:<22} [{d['via']}] {selo}")
    return novos


def rodar() -> None:
    print(f"GerencIA · sensor de rede — máquina {MAQUINA}, usuário {_usuario_logado()}")
    print(f"  coletor: {COLETOR or '(nenhum — modo impressão)'} · intervalo {INTERVALO}s · janela {JANELA}s")
    print(f"  sinais: índice de IPs + {'cache de DNS do Windows' if WIN else 'cache de DNS (só Windows)'} + processo dono")
    print("  registra METADADO de uso de IA — nunca o conteúdo\n")
    _reindexar(forcar=True)
    print(f"  índice inicial: {len(_ip_index)} IP(s) de IA mapeado(s)\n")
    try:
        while True:
            n = varrer(imprimir=False)
            if n:
                print(f"  {_agora()}  {n} uso(s) de IA registrado(s)", flush=True)
            time.sleep(INTERVALO)
    except KeyboardInterrupt:
        print("\nencerrado")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "testar"
    if cmd == "testar":
        print("Varredura única — quem está falando com IA agora:\n")
        _reindexar(forcar=True)
        print(f"  (índice: {len(_ip_index)} IPs de IA mapeados a partir de {len(DOMINIOS_IA)} domínios)\n")
        n = varrer(imprimir=True)
        print(f"\n{n} uso(s) casado(s)." if n else
              "\nNada casou agora. Abra uma IA (navegador ou app) e rode de novo.")
    elif cmd == "rodar":
        rodar()
    elif cmd == "servico":
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "servico"))
        from servico_win import ponte_servico
        ponte_servico(sys.argv[2:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
