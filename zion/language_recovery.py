"""Bounded language interpretation, never factual or authorization evidence.

Only reviewed aliases are recovered. No edit-distance matching, administrative
identity inference or moderation bypass. Callers must check policy on RAW input.
The original is immutable; interpretation is ephemeral and not persisted here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class InterpretationConfidence(str, Enum):
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


_ALIASES = MappingProxyType({
    'zswap': 'z-swap', 'zsawp': 'z-swap', 'zswp': 'z-swap',
    'segra': 'segura', 'qnt': 'quanto', 'qnto': 'quanto',
    'qnts': 'quantas', 'qntas': 'quantas', 'q': 'que',
    'vc': 'voce', 'vcs': 'voces', 'cm': 'com', 'msm': 'mesmo',
    'pq': 'por que', 'tbm': 'tambem', 'n': 'nao',
    'vantagen': 'vantagem', 'integra': 'integrar', 'funfa': 'funciona', 'conecta': 'conectar',
    'unisswap': 'uniswap', 'metamaskk': 'metamask',
})
# Protected spans are opaque even if they happen to contain a reviewed alias.
_TOKEN = re.compile(r'https?://\S+|@[\w]+|\b[\w]+\b', re.UNICODE)
_LOW = re.compile(r'^(?:e )?(?:esse|essa|isso|esse ai|essa ai)\??$|^como faz\??$')


@dataclass(frozen=True, slots=True)
class LanguageInterpretation:
    original: str
    canonical: str
    confidence: InterpretationConfidence
    recovered: bool
    clarification: str | None = None


def recover_language(text: str) -> LanguageInterpretation:
    original = text or ''
    bounded = original[:6000]
    folded = ''.join(c for c in unicodedata.normalize('NFKD', bounded)
                     if not unicodedata.combining(c)).casefold()
    # URL/mention spans are left opaque; they never select an admin identity.
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        token = match.group()
        replacement = _ALIASES.get(token, token)
        if token == 'cm' and re.match(r'\s+funciona(?:m)?\b', folded[match.end():]):
            replacement = 'como'
        changed |= replacement != token
        return replacement

    canonical = _TOKEN.sub(replace, folded)
    canonical = re.sub(r'\bdeu ruim\b', 'deu erro', canonical)
    canonical = re.sub(r'\bz swap\b', 'z-swap', canonical)
    canonical = re.sub(r'\be segurar usar\b', 'e seguro usar', canonical)
    canonical = re.sub(r'\s+', ' ', canonical).strip()
    if _LOW.fullmatch(canonical):
        confidence = InterpretationConfidence.LOW
        clarification = 'Você está falando de qual recurso da Z-SWAP?'
    elif changed or canonical != folded.strip():
        confidence = InterpretationConfidence.MEDIUM
        clarification = None
    else:
        confidence = InterpretationConfidence.HIGH
        clarification = None
    return LanguageInterpretation(original, canonical, confidence, changed,
                                  clarification)
