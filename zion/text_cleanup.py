"""Limpeza depois que frases são removidas de uma resposta (reparo do guarda, revisão de grounding).

Uma lista que perdeu os itens deixava marcadores soltos ("• • •") e uma introdução
órfã ("As informações públicas são:") — visto ao vivo em 2026-11-18.
"""
from __future__ import annotations

import re

_ITEM = re.compile(r"^\s*(?:[•▪◦‣\-*–]|\d{1,2}[.)])\s+\S")
_MARKER_RUN = re.compile(r"(?:[•▪◦‣][ \t]*){2,}")
_EMPTY_ITEM = re.compile(r"(?m)^[ \t]*(?:[•▪◦‣\-*–]|\d{1,2}[.)])[ \t]*$\n?")


_ANAFORICA = re.compile(
    r"(?:quer|deseja|gostaria)(?: que eu)? (?:faca|fazer) isso\??|posso fazer isso\??|"
    r"(?:isso|isto) (?:ajudaria|ajuda|serve|resolve)\??|voce gostaria\??|quer\?")


def _dobra(texto: str) -> str:
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _sem_pergunta_orfa(original: str, resultado: str) -> str:
    """'Quer que eu faça isso?' só fica se a frase a que se refere ficou também."""
    frases = re.findall(r"[^.!?\n]+[.!?]?", resultado)
    saida = resultado
    for frase in frases:
        limpa = frase.strip()
        if not limpa or not _ANAFORICA.fullmatch(_dobra(limpa)):
            continue
        pos = original.find(limpa)
        if pos <= 0:
            continue
        anterior = re.findall(r"[^.!?\n]+[.!?]?", original[:pos])
        anterior = next((a.strip() for a in reversed(anterior) if a.strip()), "")
        if anterior and anterior not in resultado:
            saida = saida.replace(limpa, "", 1)
    return saida


def limpar_listas_orfas(original: str, resultado: str) -> str:
    texto = _MARKER_RUN.sub("", resultado)
    texto = _EMPTY_ITEM.sub("", texto)
    # introdução ":" que no ORIGINAL abria uma lista e agora não abre mais nada
    abria_lista = set()
    linhas_orig = [l for l in original.split("\n")]
    for i, linha in enumerate(linhas_orig):
        if linha.rstrip().endswith(":"):
            seguinte = next((l for l in linhas_orig[i + 1:] if l.strip()), "")
            if _ITEM.match(seguinte):
                abria_lista.add(linha.strip())
    linhas = texto.split("\n")
    saida = []
    for i, linha in enumerate(linhas):
        if linha.strip() in abria_lista:
            seguinte = next((l for l in linhas[i + 1:] if l.strip()), "")
            if not _ITEM.match(seguinte):
                continue
        saida.append(linha)
    texto = "\n".join(saida)
    texto = _sem_pergunta_orfa(original, texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()
