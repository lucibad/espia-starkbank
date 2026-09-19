"""
GerencIA — leitor mínimo de XLSX, sem dependências.

Mesma razão do `yaml_min.py`: a base oficial do desafio chega como planilha, e
amarrar a leitura dela a um `pip install openpyxl` significa que o protótipo não
roda numa máquina recém-formatada — que é a situação de uma apresentação.

Se openpyxl estiver instalado, o importador usa openpyxl. Se não estiver, cai aqui.

Um .xlsx é um zip de XML. Este módulo lê o que uma planilha de dados usa:
strings em `sharedStrings.xml`, strings inline (`t="inlineStr"`), números,
booleanos, e datas em número de série do Excel quando o formato da célula diz
que é data. Não lê fórmulas (apenas o valor em cache), gráficos, macros ou
formatação — e não deveria: se a base precisar disso um dia, instale openpyxl.
"""

from __future__ import annotations

import datetime as _dt
import re
import zipfile
from xml.etree import ElementTree as ET

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_R_COL = re.compile(r"([A-Z]+)")

# Formatos numéricos embutidos do Excel que representam data ou hora.
_FMT_DATA_EMBUTIDOS = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}
_EPOCH = _dt.datetime(1899, 12, 30)  # o "bug do ano 1900" já embutido


def _indice_coluna(ref: str) -> int:
    """'A' → 0, 'B' → 1, 'AA' → 26."""
    letras = _R_COL.match(ref or "A")
    letras = letras.group(1) if letras else "A"
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _texto_de(elem) -> str:
    """Concatena todos os <t> de um nó — cobre strings com formatação em partes."""
    return "".join(t.text or "" for t in elem.iter(f"{{{_NS['main']}}}t"))


class Planilha:
    """Um arquivo .xlsx aberto para leitura."""

    def __init__(self, caminho):
        self._zip = zipfile.ZipFile(caminho)
        self._compartilhadas = self._ler_compartilhadas()
        self._formatos_data = self._ler_formatos()
        self._abas = self._ler_indice_abas()

    # -- leitura dos componentes ---------------------------------------

    def _ler_compartilhadas(self) -> list[str]:
        try:
            raiz = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        return [_texto_de(si) for si in raiz.findall("main:si", _NS)]

    def _ler_formatos(self) -> set[int]:
        """Índices de estilo cujo formato numérico representa data."""
        try:
            raiz = ET.fromstring(self._zip.read("xl/styles.xml"))
        except KeyError:
            return set()

        personalizados = set()
        for fmt in raiz.iter(f"{{{_NS['main']}}}numFmt"):
            codigo = (fmt.get("formatCode") or "").lower()
            # remove trechos entre colchetes e aspas antes de procurar marcas de data
            limpo = re.sub(r"\[[^\]]*\]|\"[^\"]*\"", "", codigo)
            if any(m in limpo for m in ("yy", "mmm", "dd/", "d/m", "m/d", "hh:", "h:m")):
                personalizados.add(int(fmt.get("numFmtId")))

        de_data = set()
        xf = raiz.find("main:cellXfs", _NS)
        if xf is not None:
            for i, no in enumerate(xf.findall("main:xf", _NS)):
                fid = int(no.get("numFmtId") or 0)
                if fid in _FMT_DATA_EMBUTIDOS or fid in personalizados:
                    de_data.add(i)
        return de_data

    def _ler_indice_abas(self) -> dict[str, str]:
        wb = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        alvo = {
            r.get("Id"): r.get("Target").lstrip("/").replace("worksheets/", "worksheets/")
            for r in rels
        }
        abas = {}
        for i, sheet in enumerate(wb.iter(f"{{{_NS['main']}}}sheet"), start=1):
            rid = sheet.get(f"{{{_NS['rel']}}}id")
            caminho = alvo.get(rid, f"worksheets/sheet{i}.xml")
            if not caminho.startswith("xl/"):
                caminho = "xl/" + caminho
            abas[sheet.get("name")] = caminho
        return abas

    # -- API ------------------------------------------------------------

    @property
    def abas(self) -> list[str]:
        return list(self._abas)

    def _valor(self, celula) -> object:
        tipo = celula.get("t")
        estilo = celula.get("s")

        if tipo == "inlineStr":
            return _texto_de(celula) or None
        if tipo == "s":
            v = celula.find("main:v", _NS)
            if v is None or v.text is None:
                return None
            return self._compartilhadas[int(v.text)]
        if tipo == "str":  # resultado de fórmula em cache
            v = celula.find("main:v", _NS)
            return v.text if v is not None else None

        v = celula.find("main:v", _NS)
        if v is None or v.text is None:
            return None
        bruto = v.text

        if tipo == "b":
            return bruto == "1"
        if tipo == "e":  # célula com erro (#N/D, #VALOR!)
            return None

        try:
            numero = float(bruto)
        except ValueError:
            return bruto

        if estilo is not None and int(estilo) in self._formatos_data:
            try:
                return _EPOCH + _dt.timedelta(days=numero)
            except OverflowError:
                return numero

        return int(numero) if numero.is_integer() else numero

    def linhas(self, nome_aba: str) -> list[list]:
        """Todas as linhas da aba como listas, com as lacunas preenchidas por None.

        Linhas inteiramente vazias não aparecem no XML. Por isso a posição vem do
        atributo `r` de cada <row>, e não da ordem de leitura — senão uma linha em
        branco no meio da planilha desloca tudo o que vem depois.
        """
        if nome_aba not in self._abas:
            raise KeyError(f"aba '{nome_aba}' não existe. Abas: {self.abas}")
        raiz = ET.fromstring(self._zip.read(self._abas[nome_aba]))

        por_indice: dict[int, list] = {}
        for linha in raiz.iter(f"{{{_NS['main']}}}row"):
            celulas: dict[int, object] = {}
            for c in linha.findall("main:c", _NS):
                celulas[_indice_coluna(c.get("r", ""))] = self._valor(c)
            largura = (max(celulas) + 1) if celulas else 0
            indice = int(linha.get("r", len(por_indice) + 1)) - 1  # `r` é base 1
            por_indice[indice] = [celulas.get(i) for i in range(largura)]

        if not por_indice:
            return []
        return [por_indice.get(i, []) for i in range(max(por_indice) + 1)]

    def tabela(self, nome_aba: str, linha_cabecalho: int = 2) -> list[dict]:
        """Lê a aba como lista de dicionários.

        `linha_cabecalho` é o índice (base zero) da linha de títulos. As abas
        desta base trazem um título na linha 0 e uma linha em branco na 1, então
        o cabeçalho real está na linha 2.
        """
        linhas = self.linhas(nome_aba)
        if len(linhas) <= linha_cabecalho:
            return []
        cabecalho = [
            (str(h).strip() if h is not None else f"coluna_{i}")
            for i, h in enumerate(linhas[linha_cabecalho])
        ]
        registros = []
        for linha in linhas[linha_cabecalho + 1:]:
            if not any(v is not None and str(v).strip() for v in linha):
                continue
            linha = list(linha) + [None] * (len(cabecalho) - len(linha))
            registros.append(dict(zip(cabecalho, linha)))
        return registros

    def close(self) -> None:
        self._zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def abrir(caminho) -> Planilha:
    return Planilha(caminho)
