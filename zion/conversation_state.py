"""Bounded conversational topic metadata; never an authorization decision.

This layer identifies explicit subject changes before pronoun/follow-up heuristics.
It does not infer facts, moderate content, or grant access to another agent's data.
Unknown subjects remain unknown rather than receiving invented semantic certainty.
"""
from __future__ import annotations

import re
from .language_recovery import recover_language


# Order resolves mixed questions conservatively: an operational failure takes
# precedence over the product whose operation failed. No generated answer text
# participates in selecting the active topic.
_TOPIC_RULES = tuple((name, re.compile(pattern)) for name, pattern in (
    ('support', r'\b(?:nao (?:consigo|conecta|conectar)|erro|falhou|travou|sumiu|probleminha|resolver)\b'),
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
    folded = recover_language(text).canonical
    for topic, pattern in _TOPIC_RULES:
        if pattern.search(folded):
            return topic
    return None


def changes_explicit_topic(text: str, previous_topic: str | None) -> bool:
    current = explicit_topic(text)
    return bool(current and previous_topic and current != previous_topic)


class FragmentWindow:
    """Ephemeral support slots scoped by chat, thread AND user.

    Only fixed public product labels are retained (not raw messages, addresses,
    keys or generated answers). An unrelated turn resets the slots. No timers
    send messages; each reply still requires its own durable speaker claim.
    """
    TTL = 90.0
    MAX_ENTRIES = 2048

    def __init__(self):
        self._entries: dict[tuple[int, int | None, int], tuple[float, dict[str, str]]] = {}

    def observe(self, key: tuple[int, int | None, int], text: str, *, now: float) -> str | None:
        canonical = recover_language(text).canonical.strip(' .!?')
        # Work is bounded even in a busy group; state expires without waiting
        # for the same user to return.
        self._entries = {k: v for k, v in self._entries.items() if v[0] > now}
        if canonical in {'swap', 'bridge', 'ordem'}:
            if len(self._entries) >= self.MAX_ENTRIES:
                self._entries.pop(next(iter(self._entries)))
            self._entries[key] = (now + self.TTL, {'product': canonical})
            return None
        previous = self._entries.get(key)
        if previous is None:
            return None
        slots = dict(previous[1])
        if canonical in {'deu erro', 'falhou', 'travou'}:
            slots['problem'] = 'deu erro'
        elif re.fullmatch(r'(?:na|no|em) (?:base|solana|ethereum|polygon|arbitrum|optimism|avalanche|bnb)', canonical):
            slots['network'] = canonical.split()[-1]
        elif re.fullmatch(r'com (?:usdc|usdt|eth|sol|bnb)', canonical):
            slots['asset'] = canonical.split()[-1]
        else:
            self._entries.pop(key, None)
            return None
        self._entries[key] = (previous[0], slots)  # No unbounded sliding window.
        if 'problem' not in slots:
            return None
        return ' '.join((slots['product'], slots['problem'],
                         'na rede ' + slots['network'] if 'network' in slots else '',
                         'com ' + slots['asset'] if 'asset' in slots else '')).strip()
