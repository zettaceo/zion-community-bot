"""Small deterministic public-output gate, not a general factuality oracle.

Reject known confidentiality, unsupported authority and absolute-guarantee
failures. Grounding still requires retrieval, source freshness and evaluation.
Never persist the rejected answer or its matching sensitive substring.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .logging_safe import contains_high_confidence_credential


@dataclass(frozen=True, slots=True)
class ResponseCheck:
    allowed: bool
    reason: str


_RULES = (
    ('internal_path', r'(?:/home/|/etc/|/var/|/tmp/|\.env\b|\b[a-z_]+\.sql\b)'),
    ('internal_route', r'/api/(?:admin|internal|private)(?:[/\s?#]|$)|\b[a-z0-9.-]+\.(?:internal|local)\b'),
    ('internal_address', r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    ('internal_provenance', r'\b(?:[a-f0-9]{40}|zettaceo/zion-community-bot|zetta-world/swap-z-app)\b'),
    ('unauthorized_action', r'\b(?:executei (?:a |sua |uma )?(?:ordem|transacao)|aprovei (?:a |sua )?parceria|garanto (?:seu |o )?lucro)\b'),
)


def validate_public_response(text: str, *, official_context: str) -> ResponseCheck:
    if not isinstance(text, str) or not text.strip():
        return ResponseCheck(False, 'empty_response')
    if len(text) > 16000:
        return ResponseCheck(False, 'response_bound')
    if contains_high_confidence_credential(text):
        return ResponseCheck(False, 'credential')
    folded = ''.join(c for c in unicodedata.normalize('NFKD', text)
                     if not unicodedata.combining(c)).casefold()
    for reason, pattern in _RULES:
        if re.search(pattern, folded):
            return ResponseCheck(False, reason)
    quality_rules = (
        ('best_price_guarantee', r"\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,60}\bmelhor(?:es)? (?:precos?|taxas?)\b"),
        ('universal_swap_execution', r"\btodos os swaps (?:sao (?:sempre )?(?:executados|realizados|processados) (?:por|via|em)|usam) (?:smart contracts?|contratos? inteligentes?)\b"),
        ('safety_guarantee', r'\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,80}\b(?:seguranca|segur[oa]s?)\b'),
        ('absolute_safety', r"\b(?:e seguro usar|100% segur[oa]|totalmente segur[oa]|livre de riscos?)\b"),
    )
    checked = folded
    for reason, pattern in quality_rules:
        for match in re.finditer(pattern, checked):
            prefix = checked[max(0, match.start() - 100):match.start()]
            # Explicit universal risk caveats, scoped to this exact claim.
            # An earlier negation or a preceding 'mas' cannot excuse a guarantee.
            if reason == 'absolute_safety' and re.search(
                r"\b(?:nenhuma?|nenhum) (?:plataforma|transacao|sistema|servico)"
                r"(?: ou (?:plataforma|transacao|sistema|servico))? e $", prefix):
                continue
            if re.search(r"\b(?:nao|nunca|nem) (?:(?:podemos|posso|pode|e|e possivel) )?$", prefix):
                continue
            return ResponseCheck(False, reason)
    approved_urls = set(re.findall(r'https?://[^\s<>]+', official_context))
    for url in re.findall(r'https?://[^\s<>]+', text):
        if url.rstrip('.,);') not in {u.rstrip('.,);') for u in approved_urls}:
            return ResponseCheck(False, 'unapproved_url')
    return ResponseCheck(True, 'accepted')


PUBLIC_FALLBACK = (
    'Não tenho informação oficial suficiente para confirmar essa resposta. '
    'Posso explicar o funcionamento público e suas limitações com base no que está confirmado.'
)
