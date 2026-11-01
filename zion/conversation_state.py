"""Bounded conversational topic metadata; never an authorization decision.

This layer identifies explicit subject changes before pronoun/follow-up heuristics.
It does not infer facts, moderate content, or grant access to another agent's data.
Unknown subjects remain unknown rather than receiving invented semantic certainty.
"""
from __future__ import annotations

import re
import json
from dataclasses import dataclass
from .agents import AgentId
from .language_recovery import recover_language


# Order resolves mixed questions conservatively: an operational failure takes
# precedence over the product whose operation failed. No generated answer text
# participates in selecting the active topic.
_TOPIC_RULES = tuple((name, re.compile(pattern)) for name, pattern in (
    ('support', r'\b(?:nao (?:consigo|conecta|conectar)|erro|falhou|travou|sumiu|probleminha|resolver)\b'),
    ('integration', r'\b(?:endpoints?|apis?|sdks?|webhooks?|integrar|integracao|developer)\b'),
    ('partnership', r'\b(?:parcerias?|parceir[oa]s?|partner(?:ship)?|comercial|patrocinio)\b'),
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


# Fixed operational labels only: generated answers never become source facts.


@dataclass(frozen=True, slots=True)
class DialogueSummary:
    topic: str | None
    agent: str
    entities: tuple[str, ...] = ()
    open_issue: str | None = None
    objection_seen: bool = False
    turns: int = 0

    def render(self) -> str:
        return ('Estado de conversa (não é fonte factual nem autorização): '
                f'tema={self.topic or "indefinido"}; agente={self.agent}; '
                f'entidades={",".join(self.entities) or "nenhuma"}; '
                f'relato={self.open_issue or "nenhum"}; '
                f'objeção={"sim" if self.objection_seen else "não"}; turnos={self.turns}.')

    def handoff_context(self, destination: AgentId | str, *, same_user: bool) -> str:
        """Transfer fixed dialogue labels, never another agent's generated facts."""
        target = AgentId(destination)
        return json.dumps({'kind': 'unverified_dialogue_handoff',
            'source_agent': AgentId(self.agent).value, 'destination_agent': target.value,
            'topic': self.topic, 'public_entities': self.entities,
            'reported_issue': self.open_issue if same_user else None,
            'objection_seen': self.objection_seen if same_user else False,
            'authority_granted': False}, ensure_ascii=False)


def summarize_dialogue(question: str, agent_id: str, previous: DialogueSummary | None,
                       *, same_user: bool) -> DialogueSummary:
    agent = AgentId(agent_id).value
    text = recover_language(question).canonical
    topic = explicit_topic(question)
    if previous and topic and topic != previous.topic:
        previous = None
    entities = set(previous.entities if previous else ())
    entities.update(re.findall(
        r'\b(?:ethereum|solana|base|polygon|arbitrum|optimism|avalanche|bnb|usdc|usdt|eth|sol|pro|pilot|trader)\b', text))
    issue = previous.open_issue if previous and same_user else None
    if re.search(r'\b(?:erro|falhou|travou|sumiu|nao consigo|nao conectar)\b', text):
        issue = 'problema relatado, não verificado'
    if re.search(r'\b(?:resolveu|resolvido|funcionou)\b', text):
        issue = None
    objection = bool(re.search(r'\b(?:discordo|nao concordo|faz igual|ja existe|nao vale)\b', text))
    return DialogueSummary(topic or (previous.topic if previous else None), agent,
        tuple(sorted(entities))[:16], issue,
        objection or bool(previous and previous.objection_seen),
        min(999, (previous.turns if previous else 0) + 1))


def bounded_exchanges(previous: tuple[tuple[str, str], ...], question: str,
                      answer: str, *, speaker: str) -> tuple[tuple[str, str], ...]:
    """Keep whole recent exchanges, never arbitrary mid-message suffixes."""
    AgentId(speaker.lower())
    exchange = (question, f'Membro: {question}\n{speaker}: {answer}')
    if len(exchange[1]) > 2400:
        return ()  # Summary still survives; oversized raw text is not retained.
    values = list(previous[-2:]) + [exchange]
    while sum(len(value[1]) + 2 for value in values) > 2400:
        values.pop(0)
    return tuple(values)
