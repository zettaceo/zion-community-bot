"""Small deterministic public-output gate, not a general factuality oracle.

Reject known confidentiality, unsupported authority and absolute-guarantee
failures. Grounding still requires retrieval, source freshness and evaluation.
Never persist the rejected answer or its matching sensitive substring.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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


def _monetary_claims(text: str) -> set[tuple[str, str]]:
    # Numeric presence is necessary, not sufficient: this does NOT prove that
    # a price was attributed to the correct plan/network/time period.
    units = {'us$': 'USD', '$': 'USD', 'usd': 'USD', 'dolares': 'USD',
             'r$': 'BRL', 'brl': 'BRL', 'reais': 'BRL', 'eur': 'EUR', '€': 'EUR'}
    folded = ''.join(c for c in unicodedata.normalize('NFKD', text)
                     if not unicodedata.combining(c)).casefold()
    number = r'\d+(?:[.,]\d+)*'
    claims = []
    for match in re.finditer(r'(us\$|r\$|\$|usd\b|brl\b|eur\b|€)\s*(' + number + ')', folded):
        claims.append((match[1], match[2]))
    for match in re.finditer(r'(' + number + r')\s*(usd|brl|eur|reais|dolares)\b', folded):
        claims.append((match[2], match[1]))
    result = set()
    for unit, value in claims:
        if len(value) > 32:
            result.add((units[unit], 'invalid_amount'))
            continue
        if ',' in value and '.' in value:
            decimal_separator = ',' if value.rfind(',') > value.rfind('.') else '.'
            value = value.replace('.' if decimal_separator == ',' else ',', '').replace(',', '.')
        elif re.fullmatch(r'[1-9]\d*[.,]\d{3}', value):
            # Ambiguous grouping: require identical notation rather than
            # silently interpreting a thousands separator as a decimal.
            result.add((units[unit], 'ambiguous:' + value))
            continue
        else:
            value = value.replace(',', '.')
        try:
            amount = str(Decimal(value).normalize())
        except InvalidOperation:
            amount = 'invalid_amount'
        result.add((units[unit], amount))
    return result


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
        ('execution_guarantee', r'\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,70}\b(?:transacao|ordem|swap|operacao)\b[^.!?\n]{0,50}\b(?:executad[oa]|concluid[oa]|bem.sucedid[oa])\b|\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,30}\bexecucao (?:da|do|de) (?:sua |seu |uma |um )?(?:transacao|ordem|swap|operacao)\b'),
        ('absolute_safety', r"\b(?:e seguro usar|100% segur[oa]|totalmente segur[oa]|livre de riscos?)\b"),
    )
    checked = folded
    for reason, pattern in quality_rules:
        for match in re.finditer(pattern, checked):
            prefix = checked[max(0, match.start() - 100):match.start()]
            # Explicit universal risk caveats, scoped to this exact claim.
            # An earlier negation or a preceding 'mas' cannot excuse a guarantee.
            if reason == 'absolute_safety' and re.search(
                r"\b(?:nenhuma?|nenhum) (?:plataforma|transacao|sistema|servico|rota|swap|protocolo|ponte)"
                r"(?: ou (?:plataforma|transacao|sistema|servico|rota|swap|protocolo|ponte))? e $", prefix):
                continue
            if re.search(r"\b(?:nao|nunca|nem) (?:(?:podemos|posso|pode|e|e possivel) )?$", prefix):
                continue
            return ResponseCheck(False, reason)
    if re.search(r"\bz-?swap nao cobra (?:por )?(?:transacoes de )?swaps?\b|\bswaps? (?:sao|e) gratuit[oa]s?\b", folded):
        return ResponseCheck(False, 'unsupported_free_swap')
    # Reviewed regressions for invented competitor comparisons. Entity presence
    # is necessary, not sufficient, to establish any claim about its features.
    approved = ''.join(c for c in unicodedata.normalize('NFKD', official_context)
                       if not unicodedata.combining(c)).casefold()
    # Observed live claims turned absent comparative and partnership data into
    # categorical facts. The guard is deliberately narrow, not a general
    # factuality classifier; explicit official evidence can authorize them.
    competitor_claims = (
        r'\b(?:ha|existem|existencia de) (?:sim )?plataformas?[^.!?\n]{0,120}'
        r'\b(?:taxas? competitivas?|funcionalidades? similares?|abordagens? similares?|mais baratas?)\b',
        r'\bnao e exclusiv[ao] da z-?swap\b',
    )
    if any(re.search(pattern, folded) and not re.search(pattern, approved)
           for pattern in competitor_claims):
        return ResponseCheck(False, 'unsupported_competitor_comparison')
    no_standard_partnership_fee = (
        r'\b(?:nao ha|nao existe) (?:uma? )?taxa (?:padrao|fixa) '
        r'(?:de|para) parcerias?\b|\bparcerias? (?:nao (?:tem|possuem) '
        r'taxa (?:padrao|fixa)|(?:sao|e) gratuit[oa]s?)\b'
    )
    if (re.search(no_standard_partnership_fee, folded)
            and not re.search(no_standard_partnership_fee, approved)):
        return ResponseCheck(False, 'unsupported_partnership_fee_policy')
    for brand in ('uniswap', 'pancakeswap', '1inch', 'raydium', 'bisq'):
        pattern = r'\b' + re.escape(brand) + r'\b'
        if re.search(pattern, folded) and not re.search(pattern, approved):
            return ResponseCheck(False, 'unapproved_market_service_claim')
    monetary_claims = _monetary_claims(text)
    if (any(value == 'invalid_amount' for _, value in monetary_claims)
            or monetary_claims - _monetary_claims(official_context)):
        return ResponseCheck(False, 'unsupported_monetary_claim')
    approved_urls = set(re.findall(r'https?://[^\s<>]+', official_context))
    for url in re.findall(r'https?://[^\s<>]+', text):
        if url.rstrip('.,);') not in {u.rstrip('.,);') for u in approved_urls}:
            return ResponseCheck(False, 'unapproved_url')
    return ResponseCheck(True, 'accepted')


PUBLIC_FALLBACK = (
    'Não tenho informação oficial suficiente para confirmar essa resposta. '
    'Posso explicar o funcionamento público e suas limitações com base no que está confirmado.'
)


def public_fallback_for(reason: str) -> str:
    """Host-owned public reply for a few known quality failures."""
    if reason in {'unapproved_market_service_claim', 'unsupported_competitor_comparison'}:
        return ('Não tenho dados oficiais para comparar a Z-SWAP com essa plataforma '
                'ou confirmar que as propostas são equivalentes. Posso explicar os '
                'recursos confirmados da Z-SWAP e sugerir critérios para você comparar.')
    if reason == 'unsupported_partnership_fee_policy':
        return ('Não tenho informação oficial sobre uma taxa padrão de parceria. '
                'Posso explicar o processo público de triagem, sem prometer condições comerciais.')
    return PUBLIC_FALLBACK
