"""Idioma de uma mensagem (pt/en/es), determinístico e barato, para o privado.

O caminho do grupo recebe o idioma da triagem por IA; o privado não tinha nada e o
modelo pequeno respondia em português a quem escrevia em espanhol (2026-11-18).
"""
from __future__ import annotations

import re
import unicodedata

_PALAVRAS = {
    "pt": set("""nao voce voces quero tenho estou esta isso essa esse meu minha nossa nosso como quando tambem
                 obrigado obrigada ola oi pra pro entao mas seu sua do da dos das no na nos nas sim agora
                 tem vai vao pode posso preciso queria gostaria fazer falar alguem equipe porque qual quais""".split()),
    "es": set("""usted ustedes quiero tengo estoy eso esa ese mi mis nuestro nuestra como cuando tambien gracias
                 hola pero su del los las si ahora tiene puede puedo necesito quisiera hacer hablar alguien
                 equipo porque cual cuales les ofrecemos interesa cuanto cuantos pagan hay muy""".split()),
    "en": set("""the you your i my our we is are am can could would what how when where who please thanks
                 thank hello hi with for team want need have has do does will this that it if and pay""".split()),
}


def _fold(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def detectar(texto: str) -> str | None:
    """'pt' | 'en' | 'es' quando há evidência suficiente; None quando é curto/ambíguo."""
    bruto = (texto or "").lower()
    pontos = {"pt": 0.0, "es": 0.0, "en": 0.0}
    if "¿" in bruto or "¡" in bruto or "ñ" in bruto:
        pontos["es"] += 3
    if re.search(r"[çãõ]", bruto):
        pontos["pt"] += 3
    for palavra in re.findall(r"[a-z]+", _fold(texto)):
        for lang, conjunto in _PALAVRAS.items():
            if palavra in conjunto:
                pontos[lang] += 1
    melhor = max(pontos, key=pontos.get)
    ordenados = sorted(pontos.values(), reverse=True)
    if ordenados[0] >= 2 and ordenados[0] - ordenados[1] >= 1:
        return melhor
    return None
