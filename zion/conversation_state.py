"""Bounded conversational topic metadata; never an authorization decision.

This layer identifies explicit subject changes before pronoun/follow-up heuristics.
It does not infer facts, moderate content, or grant access to another agent's data.
Unknown subjects remain unknown rather than receiving invented semantic certainty.
"""
from __future__ import annotations

import re
import unicodedata


# Order resolves mixed questions conservatively: an operational failure takes
# precedence over the product whose operation failed. No generated answer text
# participates in selecting the active topic.
_TOPIC_RULES = tuple((name, re.compile(pattern)) for name, pattern in (
    ('support', r'\b(?:nao (?:consigo|conecta)|erro|falhou|travou|sumiu|probleminha|resolver)\b'),
    ('integration', r'\b(?:endpoints?|apis?|sdks?|webhooks?|integrar|integracao|developer)\b'),
    ('partnership', r'\b(?:parcerias?|partner(?:ship)?|comercial|patrocinio)\b'),
    ('roadmap', r'\b(?:roadmap|cronograma|lancamento|lancar)\b'),
    ('plans', r'\b(?:planos?|pro|pilot|trader|thrall|drengr|berserkr|einherjar|precos?|taxas?|fees?)\b'),
    ('security', r'\b(?:segur[oa]|seguranca|riscos?|custodia|seed|private key)\b'),
    ('swap', r'\b(?<!z-)(?<!z )(?:swaps?|bridges?|roteamento|routing|liquidez|slippage)\b'),
    ('networks', r'\b(?:redes?|chains?|blockchains?)\b'),
    ('orders', r'\b(?:ordens|ordem|oco|stop|limit|market)\b'),
))


def explicit_topic(text: str) -> str | None:
    """Return a bounded topic label, not a factual or security classification."""
    folded = ''.join(c for c in unicodedata.normalize('NFKD', text[:6000])
                     if not unicodedata.combining(c)).casefold()
    for topic, pattern in _TOPIC_RULES:
        if pattern.search(folded):
            return topic
    return None


def changes_explicit_topic(text: str, previous_topic: str | None) -> bool:
    current = explicit_topic(text)
    return bool(current and previous_topic and current != previous_topic)
