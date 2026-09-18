#!/usr/bin/env python3
"""Host de mensagens nativas do Rastro — informa o usuário logado no Windows.

A extensão de navegador não consegue ler o usuário do sistema operacional
(barreira de segurança). Este pequeno host roda no Windows do usuário e
devolve %USERNAME% pelo protocolo de native messaging (moldura de 4 bytes de
tamanho + JSON, via stdin/stdout).

Instale-o com instalar.ps1. Precisa de Python no Windows.
"""
import getpass
import json
import os
import struct
import sys


def ler():
    cab = sys.stdin.buffer.read(4)
    if len(cab) < 4:
        return None
    tam = struct.unpack("=I", cab)[0]
    dados = sys.stdin.buffer.read(tam)
    try:
        return json.loads(dados.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def escrever(obj):
    dados = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(dados)))
    sys.stdout.buffer.write(dados)
    sys.stdout.buffer.flush()


def main():
    # O navegador abre o host, manda uma mensagem e lê a resposta.
    ler()  # consome o pedido (não precisamos do conteúdo)
    escrever({
        "usuario": getpass.getuser(),
        "dominio": os.environ.get("USERDOMAIN", ""),
        "maquina": os.environ.get("COMPUTERNAME", ""),
    })


if __name__ == "__main__":
    main()
