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


_EVM_TIERS = ('free', 'pro', 'trader', 'pilot')
_TIER_PATTERN = r'free|pro|trader|pilot'
_PERCENT_PATTERN = r'(\d{1,2}(?:[.,]\d{1,2})?)\s*%'


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c)).casefold()


def _evm_plan_fees(context: str) -> dict[str, Decimal]:
    """Read fee pairs from titled, approved evidence, never from a local tariff."""
    parts = re.split(r'\[contexto oficial: ([^\]]+)\]\s*', _fold(context))
    fees: dict[str, Decimal] = {}
    for heading, body in zip(parts[1::2], parts[2::2]):
        tier = next((name for name in _EVM_TIERS
                     if re.match(r'plano ' + name + r'\b', heading)), None)
        if tier is None:
            continue
        body = ' '.join(body.split())
        match = re.search(r'\bplatform fee\b.{0,180}?\bevm\b.{0,180}?'
                          + _PERCENT_PATTERN, body)
        if match:
            fees[tier] = Decimal(match[1].replace(',', '.'))
    return fees


def _evm_fee_enumeration_is_complete(answer: str, context: str) -> bool:
    """A broad EVM tier schedule must be the whole source-derived matrix."""
    folded = _fold(answer)
    if '%' not in folded:
        return True
    if (not re.search(r'\bevm\b', folded)
            and (re.search(r'\bsolana\b', folded)
                 or not re.search(r'\b(?:taxas?|fees?|cobrancas?)\b', folded))):
        return True
    named = set(re.findall(r'\b(?:' + _TIER_PATTERN + r')\b', folded))
    if len(named) < 3:
        return True  # Two-tier comparisons are not claims to list every tier.
    source = _evm_plan_fees(context)
    if set(source) != set(_EVM_TIERS):
        return False
    pairs: dict[str, set[Decimal]] = {}
    # An inverse phrase such as "0,5% no Pro" must own that percentage; a
    # forward scan from the previous tier must not steal it across a comma.
    for match in re.finditer(
        _PERCENT_PATTERN + r'\s*(?:no|na|para(?: o)?|do|da)?\s*\b('
        + _TIER_PATTERN + r')\b', folded,
    ):
        pairs.setdefault(match[2], set()).add(Decimal(match[1].replace(',', '.')))
    for match in re.finditer(
        r'\b(' + _TIER_PATTERN + r')\b'
        r'(?:(?!\b(?:' + _TIER_PATTERN + r')\b)[^,.!?;\n%]){0,50}?'
        + _PERCENT_PATTERN, folded,
    ):
        if match[1] not in pairs:
            pairs.setdefault(match[1], set()).add(Decimal(match[2].replace(',', '.')))
    return all(pairs.get(tier) == {value} for tier, value in source.items())


def _solana_fee_scope_is_preserved(answer: str) -> bool:
    """Jupiter's pair condition cannot be stated as an all-Solana policy."""
    folded = _fold(answer).replace('li.fi', 'lifi')
    previous_solana = False
    for clause in re.split(r'[.!?;\n]+', folded):
        solana_scope = 'solana' in clause or (previous_solana and bool(re.search(
            r'\b(?:os )?(?:outros|demais) pares?\b', clause)))
        previous_solana = 'solana' in clause
        if not solana_scope:
            continue
        jupiter_scope = (bool(re.search(r'\b(?:na|pela|via|com|da|de|a) jupiter\b', clause))
                         and not bool(re.search(r'\bjupiter\b.{0,15}\bou lifi\b', clause)))
        pair_condition = bool(re.search(r'\busdc\b.{0,12}\bsol\b|\bsol\b.{0,12}\busdc\b', clause))
        if pair_condition and re.search(
            r'\b(?:todas? as?|qualquer|cada) rotas? (?:de |da )?solana\b', clause
        ):
            return False
        if (pair_condition and not jupiter_scope
                and re.search(r'\b(?:so|somente|apenas|sem)\b', clause)
                and re.search(r'\b(?:taxa|fee|cobranca|cobra|pagam)\b', clause)):
            return False
        if (pair_condition and not jupiter_scope
                and re.search(r'\bnao (?:incluem|contem|tem)\b.{0,35}'
                              r'\bnao (?:pagam|tem|incide|cobram)\b', clause)):
            return False
        if (pair_condition and not jupiter_scope
                and re.search(r'\b(?:em|na) solana\b.{0,90}\bmesma escada vale quando\b', clause)):
            return False
        if (not jupiter_scope and re.search(
            r'\b(?:outros|demais) pares? (?:solana )?nao (?:tem|pagam|possuem)\b'
            r'.{0,45}\b(?:platform fee|taxa)\b', clause
        )):
            return False
    return True


def _snapshot_proof_is_preserved(answer: str) -> bool:
    """This answer path has reviewed snapshots, not a live product probe."""
    folded = _fold(answer)
    for match in re.finditer(r'\b(?:verificavel|comprovad[ao]) '
                             r'(?:hoje|agora|neste momento)\b', folded):
        prefix = folded[max(0, match.start() - 90):match.start()]
        if not (re.search(r'\bnao (?:e|foi|esta|ha nada|comprovado) $', prefix)
                or re.search(r'\bnao e possivel afirmar que seja $', prefix)
                or re.search(r'\bsem prova $', prefix)
                or re.search(r'\bnao $', prefix)):
            return False
    for match in re.finditer(r'\b(?:hoje|agora) (?:eu )?(?:testei|confirmei|verifiquei)\b'
                             r'|\bacabei de (?:testar|verificar|confirmar)\b', folded):
        if not re.search(r'\bnao $', folded[max(0, match.start() - 15):match.start()]):
            return False
    for match in re.finditer(r'\b(?:eu )?(?:testei|confirmei|verifiquei)\b'
                             r'[^.!?;\n]{0,80}\b(?:hoje|agora|em tempo real)\b', folded):
        prefix = folded[max(0, match.start() - 20):match.start()]
        if not re.search(r'\b(?:eu )?(?:nao|nunca) $', prefix):
            return False
    for match in re.finditer(r'\b(?:foi|esta) (?:verificado|confirmado|testado) '
                             r'(?:hoje|agora|em tempo real)\b', folded):
        if not re.search(r'\bnao $', folded[max(0, match.start() - 12):match.start()]):
            return False
    for match in re.finditer(r'\b(?:esta|estao) disponive(?:l|is) agora na plataforma\b', folded):
        if not re.search(r'\bnao $', folded[max(0, match.start() - 12):match.start()]):
            return False
    for match in re.finditer(r'\binterface (?:foi|esta) testada em tempo real\b', folded):
        if not re.search(r'\bnao $', folded[max(0, match.start() - 12):match.start()]):
            return False
    for match in re.finditer(
        r'\bno momento,? .{0,80}\bdisponive(?:l|is) na plataforma\b', folded
    ):
        if not re.search(r'\bnao (?:esta|estao) disponive(?:l|is) na plataforma\b',
                         match.group()):
            return False
    for match in re.finditer(r'\bisso e prova\b', folded):
        previous = folded[max(0, match.start() - 240):match.start()]
        if re.search(r'\b(?:abra|acesse|rode|execute|teste|verifique)\b', previous):
            return False
    return True


def _source_feature_statuses(context: str) -> set[str]:
    """Find direct affirmative feature-state predicates in one evidence section."""
    statuses: set[str] = set()
    sections = re.split(r'(?m)^\[contexto oficial: [^\]\n]+\][ \t]*$', _fold(context))
    partial = r'\b(?:partial|parcial(?:mente)?)\b'
    patterns = {
        'terminal pro': (
            r'\bterminal pro\s+(?:esta|permanece|segue|aparece)\b[^.!?,;]{0,25}\bbeta\b',
            r'\bterminal pro\b[^.!?,;]{0,80}\be aparece como beta\b',
        ),
        'portfolio': (
            r'\bportfolio\s+(?:esta|permanece|segue)\b[^.!?,;]{0,25}' + partial,
            r'\bportfolio e orders\s+estao\b[^.!?,;]{0,25}' + partial,
            r'\bportfolio\s*:\s*acompanhamento\b[^.!?,;]{0,25}' + partial,
        ),
        'orders': (
            r'\borders\s+(?:esta|estao|permanece|segue)\b[^.!?,;]{0,25}' + partial,
            r'\borders\s*:\s*planejamento e gatilhos,\s*em estado\s+' + partial,
        ),
    }
    for section in sections:
        for feature, rules in patterns.items():
            for pattern in rules:
                for match in re.finditer(pattern, section):
                    fragment = match.group()
                    if not re.search(r'\b(?:nao|nunca|sem|fora|deixou|saiu)\b', fragment):
                        statuses.add(feature)
    return statuses


def _feature_status_is_preserved(answer: str, context: str) -> bool:
    """Carry explicit beta/partial status when approved evidence supplies it."""
    source_statuses = _source_feature_statuses(context)
    folded = _fold(answer)
    statuses = (
        ('terminal pro', r'\bbeta\b'),
        ('portfolio', r'\b(?:parcial\w*|partial\w*)\b'),
        ('orders', r'\b(?:parcial\w*|partial\w*)\b'),
    )
    for feature, required in statuses:
        if feature not in source_statuses:
            continue
        if not re.search(r'\b' + feature + r'\b', folded):
            continue
        if feature == 'terminal pro' and re.search(
            r'\bterminal pro\b.{0,55}\b(?:nao (?:esta |segue |permanece )?(?:mais )?(?:em )?'
            r'|deixou (?:o |a |de (?:estar )?(?:em )?)|saiu (?:do |da ))beta\b', folded):
            return False
        if feature in {'portfolio', 'orders'} and re.search(
            r'\b' + feature + r'\b.{0,55}\bnao (?:esta |segue )?(?:so |apenas )?'
            r'(?:parcial\w*|partial\w*)\b', folded):
            return False
        mentions = list(re.finditer(r'\b' + feature + r'\b', folded))
        if not any(re.search(required, folded[max(0, match.start() - 35):match.end() + 100])
                   for match in mentions):
            return False
    return True


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
        ('best_price_guarantee', r"\b(?:garant\w*|assegur\w*)\b(?:(?!\s*,\s*mas\b)[^.!?;\n]){0,60}\bmelhor(?:es)? (?:precos?|taxas?)\b"),
        ('best_price_guarantee', r'\bmelhor(?:es)? (?:precos?|taxas?) (?:e|sao|esta)? ?garantid[ao]s?\b'),
        ('best_price_guarantee', r'\b(?:oferece|oferecemos|entrega|entregamos|obtem|obtemos) sempre (?:o|a) melhor(?:es)? (?:precos?|taxas?)\b|\b(?:menor|mais baixa) taxa (?:do mercado )?(?:e|esta)? ?garantid[ao]\b'),
        ('universal_swap_execution', r"\btodos os swaps (?:sao (?:sempre )?(?:executados|realizados|processados) (?:por|via|em)|usam) (?:smart contracts?|contratos? inteligentes?)\b"),
        ('safety_guarantee', r'\b(?:garant\w*|assegur\w*)\b(?:(?!\s*,\s*mas\b)[^.!?;\n]){0,80}\b(?:seguranca|segur[oa]s?|protecao total)\b'),
        ('safety_guarantee', r'\bseguranca(?: da (?:operacao|transacao))?\s+(?:esta|e)\s+(?:(?:plenamente|totalmente|completamente|100%)\s+)?garantid[ao]s?\b'),
        ('execution_guarantee', r'\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,70}\b(?:transacao|ordem|swap|operacao)\b[^.!?\n]{0,50}\b(?:executad[oa]|concluid[oa]|bem.sucedid[oa])\b|\b(?:garant\w*|assegur\w*)\b[^.!?\n]{0,30}\bexecucao (?:da|do|de) (?:sua |seu |uma |um )?(?:transacao|ordem|swap|operacao)\b'),
        ('absolute_safety', r"\b(?:e segur[oa](?: para usar)?|(?:100%|totalmente|completamente) segur[oa]|livre de riscos?|seguranca total|risco zero|nao (?:tem|corre|existe) riscos?)\b"),
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
            if (reason in {'best_price_guarantee', 'safety_guarantee'}
                    and match.group().startswith('garantia')
                    and (re.search(r'\bnao (?:ha|existe|tem|temos|oferece|oferecemos|fornece|damos) '
                                   r'(?:(?:uma?|qualquer) )?$', prefix)
                         or re.search(r'\bnenhuma plataforma oferece $', prefix)
                         or re.match(r'\s+nao existe\b',
                                     checked[match.end():match.end() + 25]))):
                continue
            if (reason == 'best_price_guarantee' and match.group().startswith('melhor')
                    and re.search(r'\bnao (?:ha|existe) $', prefix)):
                continue
            if re.search(
                r"\b(?:(?:nao|nunca|nem) (?:(?:podemos|posso|pode|e|e possivel|da para) )?"
                r"|nao ha como |nao se pode |sem |ninguem pode |"
                r"nenhuma plataforma pode |e impossivel )$", prefix):
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
        r'(?:^|[.!?:]\s*)(?:varias|muitas|algumas|outras) plataformas? oferecem\b',
        r'\bvarias (?:das? )?(?:pecas|etapas|funcionalidades|ferramentas)'
        r'[^.!?\n]{0,100}\bja existem\b[^.!?\n]{0,60}\bem outras plataformas\b',
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
    if not _evm_fee_enumeration_is_complete(text, official_context):
        return ResponseCheck(False, 'incomplete_plan_fee_matrix')
    if not _solana_fee_scope_is_preserved(text):
        return ResponseCheck(False, 'overbroad_solana_fee_scope')
    if not _snapshot_proof_is_preserved(text):
        return ResponseCheck(False, 'unverified_live_proof')
    if not _feature_status_is_preserved(text, official_context):
        return ResponseCheck(False, 'missing_feature_status')
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


_SOLANA_FEE_HEADING = '[Contexto oficial: Taxas Solana, Jupiter e LI.FI]'
_SOLANA_FEE_TIERS = ('free/thrall', 'pro/drengr',
                    'trader/berserkr', 'pilot/einherjar')


def _public_solana_fee_reply(official_context: str) -> str | None:
    """Compose a short answer from one complete, already authorized section."""
    if not official_context:
        return None
    # The caller must supply locally retrieved PUBLIC/CURRENT context. A
    # heading in arbitrary user or model text is not an authority grant.
    for heading in re.finditer(r'^' + re.escape(_SOLANA_FEE_HEADING) + r'\s*$',
                               official_context, re.MULTILINE):
        start = heading.end()
        next_heading = re.search(r'^\[Contexto oficial: [^\]\n]+\]\s*$',
                                 official_context[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(official_context)
        section = official_context[start:end].strip()
        folded = ' '.join(_fold(section).split())
        rates = re.findall(
            r'\b(free/thrall|pro/drengr|trader/berserkr|pilot/einherjar)\s+'
            r'(\d+(?:[.,]\d+)?\s*%)', folded)
        if len(rates) != 4 or {tier for tier, _ in rates} != set(_SOLANA_FEE_TIERS):
            continue
        required_scope = (
            r'\brotas solana elegiveis usam a mesma escada de platform fee\b',
            r'\bna jupiter, essa cobranca se aplica quando usdc ou sol e um dos lados do swap\b',
            r'\bna jupiter, outros pares solana nao tem platform fee da z-swap\b',
            r'\brotas li\.fi saindo da solana sao tratadas separadamente'
            r' e nao seguem essa condicao de par\b',
            r'\bisso nao significa operacao sem custo\b',
            r'\bconfira os custos apresentados para a rota antes de confirmar\b',
        )
        if not all(re.search(pattern, folded) for pattern in required_scope):
            continue
        values = {tier: ''.join(value.split()) for tier, value in rates}
        amounts = (f'Free/Thrall {values["free/thrall"]}, '
                   f'Pro/Drengr {values["pro/drengr"]}, '
                   f'Trader/Berserkr {values["trader/berserkr"]} e '
                   f'Pilot/Einherjar {values["pilot/einherjar"]}')
        reply = (
            'A base pública revisada informa platform fee nas rotas Solana '
            f'elegíveis: {amounts}. Na Jupiter, a cobrança se aplica quando '
            'USDC ou SOL é um dos lados do swap; outros pares na Jupiter não '
            'têm essa taxa. As rotas LI.FI saindo da Solana são tratadas '
            'separadamente e não seguem essa condição de par. Custos de rede '
            'e de terceiros podem ocorrer à parte; confira os custos da rota '
            'antes de confirmar. Essa fonte não compara taxas com outras '
            'plataformas, então não posso dizer se a Z-SWAP cobra mais ou menos.'
        )
        if validate_public_response(reply, official_context=official_context).allowed:
            return reply
    return None


def _public_feature_status_reply(official_context: str) -> str | None:
    """Carry only feature states present in already approved retrieved context."""
    source_statuses = _source_feature_statuses(official_context)
    states = []
    if 'terminal pro' in source_statuses:
        states.append('o Terminal Pro está em beta')
    if 'portfolio' in source_statuses:
        states.append('Portfolio está parcialmente disponível')
    if 'orders' in source_statuses:
        states.append('Orders está parcialmente disponível')
    if not states:
        return None
    reply = ('Na base pública revisada, ' + '; '.join(states) + '. '
             'Posso detalhar o que cada recurso oferece e suas limitações atuais.')
    if validate_public_response(reply, official_context=official_context).allowed:
        return reply
    return None


def public_fallback_for(reason: str, *, official_context: str = '') -> str:
    """Host-owned public reply for a few known quality failures."""
    if reason == 'best_price_guarantee':
        return ('A Z-SWAP compara rotas disponíveis conforme as condições daquele '
                'momento, mas não garante o melhor preço ou taxa. Confira a cotação '
                'e os custos antes de confirmar.')
    if reason in {'safety_guarantee', 'absolute_safety'}:
        return ('A Z-SWAP implementa controles para reduzir riscos, mas nenhuma '
                'plataforma ou transação é livre de risco. Confira os detalhes da '
                'operação antes de confirmar.')
    if reason in {'unapproved_market_service_claim', 'unsupported_competitor_comparison'}:
        return ('Não tenho dados oficiais para comparar a Z-SWAP com essa plataforma '
                'ou confirmar que as propostas são equivalentes. Posso explicar os '
                'recursos confirmados da Z-SWAP e sugerir critérios para você comparar.')
    if reason == 'unsupported_partnership_fee_policy':
        return ('Não tenho informação oficial sobre uma taxa padrão de parceria. '
                'Posso explicar o processo público de triagem, sem prometer condições comerciais.')
    if reason == 'incomplete_plan_fee_matrix':
        return ('As taxas da plataforma variam por plano e rota. Não vou tratar '
                'uma lista parcial como completa; posso detalhar Free, Pro, '
                'Trader e Pilot com os valores publicados.')
    if reason == 'overbroad_solana_fee_scope':
        reply = _public_solana_fee_reply(official_context)
        if reply is not None:
            return reply
        return ('As condições de taxa na Solana dependem da rota e do provedor. '
                'Não vou aplicar a condição de uma rota a todos os swaps; confira '
                'os custos mostrados antes de confirmar.')
    if reason == 'unverified_live_proof':
        return ('Posso explicar o estado documentado na base pública revisada, '
                'mas não fiz uma verificação ao vivo da plataforma. Confira a '
                'disponibilidade na interface para o seu caso.')
    if reason == 'missing_feature_status':
        reply = _public_feature_status_reply(official_context)
        if reply is not None:
            return reply
        return ('A base pública distingue recursos em beta ou parcialmente '
                'disponíveis. Posso detalhar o estado documentado de cada um; '
                'confira a disponibilidade na interface para o seu caso.')
    return PUBLIC_FALLBACK
