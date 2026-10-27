"""Small deterministic public-output gate, not a general factuality oracle.

Reject known confidentiality, unsupported authority and absolute-guarantee
failures. Grounding still requires retrieval, source freshness and evaluation.
Never persist the rejected answer or its matching sensitive substring.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
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
_SPELLED_PERCENT_VALUES = {
    'zero': Decimal('0'), 'um': Decimal('1'), 'uma': Decimal('1'),
    'dois': Decimal('2'), 'duas': Decimal('2'), 'tres': Decimal('3'),
    'quatro': Decimal('4'), 'cinco': Decimal('5'), 'seis': Decimal('6'),
    'sete': Decimal('7'), 'oito': Decimal('8'), 'nove': Decimal('9'),
    'dez': Decimal('10'), 'meio': Decimal('0.5'),
    'zero virgula cinco': Decimal('0.5'),
    'zero virgula vinte e cinco': Decimal('0.25'),
    'zero virgula um': Decimal('0.1'),
    'zero virgula dez': Decimal('0.1'),
    'um decimo': Decimal('0.1'),
    'um quarto': Decimal('0.25'),
}


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c)).casefold()


_ROUTE_SUPERLATIVE = (
    r'\b(?:(?:a|o) )?(?:melhor|mais eficiente|mais vantajos[ao]|otim[ao]|'
    r'mais barat[ao]|mais economic[ao]) (?:rota|cotacao|preco|taxa)\b|'
    r'\b(?:rota|cotacao) (?:mais eficiente|mais vantajos[ao]|'
    r'otim[ao]|mais barat[ao]|mais economic[ao]|'
    r'(?:de|com) menor (?:custo|preco|taxa))\b|'
    r'\b(?:best quote|best route|most efficient route|'
    r'lowest-cost route|lowest cost route|cheapest route)\b|'
    r'\b(?:menor (?:preco|taxa)|(?:preco|taxa) mais baix[ao])\b'
)
_ROUTE_CHOOSER = (
    r'\b(?:escolhe|seleciona|encontra|identifica|define|determina|'
    r'recomenda|indica|calcula|otimiza|busca|apresenta|mostra|entrega|fornece|'
    r'oferece|escolher|selecionar|encontrar|identificar|otimizar|'
    r'chooses|selects|finds|picks|optimizes)\b'
)


_QUOTED_CONCERN = re.compile(
    r'"[^"\n]{0,240}"|“[^”\n]{0,240}”|‘[^’\n]{0,240}’|'
    r"(?<!\w)'[^'\n]{0,240}'(?!\w)")


def _mask_reported_quotes(folded: str) -> str:
    """Mask a user's quoted concern, but not an unattributed quoted assertion."""
    def replace(match: re.Match[str]) -> str:
        before = folded[max(0, match.start() - 90):match.start()]
        after = folded[match.end():match.end() + 90]
        reported = (match.group()[-2] == '?'
                    or re.search(r'\b(?:voce|usuario|cliente|ele|ela)\s+'
                                 r'(?:perguntou|disse|alegou|citou)\b[^.!?;\n]{0,35}$',
                                 before)
                    or re.match(r'\s*(?:e|foi)\s+(?:a |uma )?(?:sua )?'
                                r'(?:pergunta|duvida|alegacao)\b', after))
        return ' ' * len(match.group()) if reported else match.group()
    return _QUOTED_CONCERN.sub(replace, folded)


def _denied_claim_prefix(prefix: str) -> bool:
    return bool(re.search(r'\b(?:nao e verdade que|nao ha evidencias? de que|'
                          r'nao ha provas? de que|e falso que|'
                          r'e incorreto afirmar que)\b[^.!?;\n]{0,55}$', prefix))


def _reported_or_denied_prefix(prefix: str) -> bool:
    return (_denied_claim_prefix(prefix)
            or bool(re.search(r'\b(?:nao (?:posso|podemos) (?:confirmar|afirmar) que|'
                              r'nao ha (?:prova|evidencia|confirmacao) de que|'
                              r'(?:voce )?perguntou se|quer saber se)\b'
                              r'[^.!?;\n]{0,55}$', prefix)))


def _unsupported_route_optimization(answer: str) -> bool:
    """Catch an asserted best-route choice, not questions or scoped denials.

    This is a bounded known-claim check, not proof of grounding for arbitrary
    route descriptions. User-quoted concerns remain non-authoritative.
    """
    folded = _mask_reported_quotes(_fold(answer))
    actor = r'\b(?:z[\s-]?swap|a plataforma|o sistema|o motor|o agregador|ela|it|the platform)\b'
    claim = re.compile(
        rf'(?:{actor}[^.!?;\n]{{0,55}}?|^)'
        rf'(?P<verb>{_ROUTE_CHOOSER})[^.!?;\n]{{0,95}}?'
        rf'(?P<superlative>{_ROUTE_SUPERLATIVE})'
    )
    passive = re.compile(
        r'\b(?:a|o)\s+(?:melhor|mais eficiente|mais barata|mais barato)\s+'
        r'(?:cotacao|rota|preco|taxa)\s+(?:e|foi|sera)\s+'
        r'(?:escolhid[ao]|selecionad[ao]|encontrad[ao])\b'
        r'[^.!?;\n]{0,45}\b(?:pela|pelo)\s+z[\s-]?swap\b'
    )
    for sentence in re.finditer(r'[^.!?;\n]+[.!?;\n]?', folded):
        segment = sentence.group().strip()
        if segment.endswith('?'):
            continue  # A question about a capability is not an assertion.
        for clause in re.split(r'\b(?:mas|porem|contudo|however|but)\b',
                               segment.rstrip('.!;\n')):
            clause = clause.strip(' ,:')
            if not clause:
                continue
            for match in passive.finditer(clause):
                if not _reported_or_denied_prefix(clause[:match.start()]):
                    return True
            for match in claim.finditer(clause):
                prefix = clause[:match.start()]
                between = clause[match.start():match.start('verb')]
                if re.search(r'\b(?:nao|nunca|jamais|not|never)\b', between):
                    continue
                if _denied_claim_prefix(prefix) or re.search(
                    r'\b(?:se|caso|quando|if|perguntou se|pergunta se|quer saber se|'
                    r'nao (?:posso|podemos|da para|e possivel) afirmar que|'
                    r'nao afirmo que|sem prova de que|nao ha evidencia de que)'
                    r'\s+(?:a |o )?$', prefix
                ):
                    continue
                return True
    return False


_WALLET_CONNECTION = re.compile(
    r'\b(?:conexao|conectar|conecta(?:m|ndo|do|da)?|conecte|conectou)\b')
_WALLET_SIGNATURE = re.compile(r'\b(?:assinatura\w*|assinar|assine)\b')
_WALLET_EXCLUSIVE = re.compile(r'\b(?:so|somente|apenas|exclusivamente|basta)\b')
_NAMED_WALLETS = ('metamask', 'phantom', 'rabby')


def _approved_wallet_brand(name: str, official_context: str) -> bool:
    """A mention, especially a negative one, is not approval of support."""
    parts = re.split(r'(?m)^\[contexto oficial: ([^\]\n]+)\][ \t]*$',
                     _fold(official_context))
    positive = False
    brand = r'\b' + re.escape(name) + r'\b'
    positive_rules = (
        brand + r'[^.!?;\n]{0,55}\b(?:e|esta|sao|aparece(?:m)? como)\s+'
        r'(?:carteiras?\s+)?(?:suportad[ao]s?|compativ(?:el|eis)|'
        r'integrad[ao]s?|aceit[ao]s?)\b',
        r'\b(?:suporta|aceita|integra|funciona com|e compativel com|'
        r'carteiras? suportadas?)\b[^.!?;\n]{0,65}' + brand,
        brand + r'\s+funciona\s+com\s+z[\s-]?swap\b',
    )
    for heading, body in zip(parts[1::2], parts[2::2]):
        for sentence in re.finditer(r'[^.!?;\n]+[.!?;\n]?', body):
            clause = sentence.group().strip()
            if not re.search(brand, clause) or clause.endswith('?'):
                continue
            if not any(re.search(rule, clause) for rule in positive_rules):
                continue
            if re.search(r'\b(?:nao|nunca|nem|sem)\b', clause):
                return False
            positive = True
    return positive


def _asserted_exclusive_wallet_connection(answer: str) -> bool:
    """Do not turn documented *authentication* into a universal connection rule."""
    folded = _mask_reported_quotes(_fold(answer))
    folded = re.sub(r'\b(?:mas|porem|contudo|however|but)\b', ';', folded)
    for sentence in re.finditer(r'[^.!?;\n]+[.!?;\n]?', folded):
        clause = sentence.group().strip()
        if clause.endswith('?'):
            continue
        universal = re.search(
            r'\b(?:toda(?:s)?(?:\s+(?:a|as))?\s+carteiras?|qualquer carteira)\b'
            r'[^.!?;\n]{0,35}\b(?:precisa|exige|requer|depende)\b'
            r'[^.!?;\n]{0,35}\bassinatura\b[^.!?;\n]{0,30}'
            r'\b(?:para\s+se\s+)?conectar\b', clause)
        if universal and not _reported_or_denied_prefix(clause[:universal.start()]):
            return True
        exclusive_use = re.search(
            r'\b(?:voce|usuario)\b[^.!?;\n]{0,10}'
            r'\b(?:so|somente|apenas)\b[^.!?;\n]{0,10}'
            r'\b(?:consegue|pode)\b[^.!?;\n]{0,25}'
            r'\b(?:usar|conectar)\b[^.!?;\n]{0,20}'
            r'\bcarteira\b[^.!?;\n]{0,25}'
            r'\b(?:depois de|apos)\b[^.!?;\n]{0,8}'
            r'\bassin(?:ar|atura)\w*\b', clause)
        if exclusive_use and not _reported_or_denied_prefix(
                clause[:exclusive_use.start()]):
            return True
        required_without = re.search(
            r'\bnao\s+(?:consegue|pode|e possivel)\b[^.!?;\n]{0,25}'
            r'\b(?:conectar|conectad[ao])\b[^.!?;\n]{0,35}\bsem\s+'
            r'(?:uma?\s+)?(?:assinatura\w*|assinar|assine)\b', clause)
        if required_without and not _reported_or_denied_prefix(
                clause[:required_without.start()]):
            return True
        obligation = re.search(
            r'(?P<connection>\b(?:conexao|conectar|conecta(?:m|ndo|do|da)?|'
            r'conecte|conectou)\b)[^.!?;\n]{0,50}?'
            r'(?P<requirement>\b(?:obrigatori[oa]|necessari[oa]|exige|'
            r'exigem|depende|precisa|tem que)\b)[^.!?;\n]{0,40}?'
            r'\b(?:assinatura\w*|assinar|assine)\b', clause)
        if (obligation and not _reported_or_denied_prefix(clause[:obligation.start()])
                and not re.search(r'\b(?:nao|nunca|nem)\b',
                                  clause[obligation.start('connection'):
                                         obligation.start('requirement')])
                and not re.search(r'\b(?:perguntou se|pergunta se|quer saber se)\b',
                                  clause[:obligation.start()])):
            return True
        connections = list(_WALLET_CONNECTION.finditer(clause))
        signatures = list(_WALLET_SIGNATURE.finditer(clause))
        connection_starts = [match.start() for match in connections]
        signature_starts = [match.start() for match in signatures]
        for exclusive in _WALLET_EXCLUSIVE.finditer(clause):
            # An eligible triple spans at most 110 characters. Bisect bounds
            # each candidate set, rather than crossing every token in a long
            # generated answer with every other token (cubic work).
            near_connections = connections[
                bisect_left(connection_starts, exclusive.start() - 110):
                bisect_right(connection_starts, exclusive.end() + 110)]
            near_signatures = signatures[
                bisect_left(signature_starts, exclusive.start() - 110):
                bisect_right(signature_starts, exclusive.end() + 110)]
            for connection in near_connections:
                for signature in near_signatures:
                    ordered = (connection.start() < exclusive.start() < signature.start()
                               or exclusive.start() < signature.start() < connection.start()
                               or exclusive.start() < connection.start() < signature.start())
                    start = min(connection.start(), exclusive.start())
                    end = max(connection.end(), signature.end())
                    if not ordered or end - start > 110:
                        continue
                    before = clause[max(0, start - 95):start]
                    claim = clause[start:end]
                    if _reported_or_denied_prefix(before):
                        continue
                    if re.search(r'\b(?:perguntou|pergunta|quer saber)\s+se\s+(?:a |toda )?$',
                                 before):
                        continue
                    if re.search(r'\b(?:nao (?:posso|podemos) (?:confirmar|afirmar)|'
                                 r'nao tenho (?:prova|evidencia|confirmacao)|'
                                 r'nao ha (?:prova|evidencia|confirmacao))\s+'
                                 r'(?:de )?que\s+(?:a |toda )?$', before):
                        continue
                    if (re.search(r'\b(?:nao|nunca|nem)\b',
                                  claim[:exclusive.start() - start])
                            or re.search(r'\b(?:nao|nunca|nem)\b'
                                         r'(?:\W+\w+){0,2}\W*$', before)):
                        continue
                    if (exclusive.start() < connection.start()
                            and (re.search(r'\bautentic\w*\b[^.!?;]{0,35}$', before)
                                 or re.search(r'\bpara autentic\w*\b',
                                              clause[exclusive.end():connection.start()]))):
                        continue
                    if (connection.start() < exclusive.start()
                            and re.search(r'\bpara autentic\w*\b',
                                          clause[connection.end():exclusive.start()])):
                        continue
                    return True
    return False


def _unapproved_wallet_example(answer: str, official_context: str) -> bool:
    """Reject only observed unsourced wallet examples, not neutral questions."""
    folded = _mask_reported_quotes(_fold(answer))
    folded = re.sub(r'\b(?:mas|porem|contudo|however|but)\b', ';', folded)
    for name in _NAMED_WALLETS:
        brand = r'\b' + re.escape(name) + r'\b'
        if _approved_wallet_brand(name, official_context):
            continue
        for match in re.finditer(brand, folded):
            before = folded[max(0, match.start() - 100):match.start()]
            sentence_start = max(before.rfind(mark) for mark in '.!?;\n') + 1
            before = before[sentence_start:]
            after = folded[match.end():match.end() + 75]
            sentence_end = re.search(r'[.!?;\n]', after)
            terminal = after[sentence_end.start()] if sentence_end else ''
            if re.search(r'\b(?:por exemplo|exemplo|ex\.?|e\.g\.?|tipo|tais como)\s*'
                         r'(?:de )?(?:carteiras?|wallets?)?\s*[:(,]?\s*$', before):
                return True
            if re.search(r'\b(?:qual|quais)\s+(?:a |as |sua |suas )?'
                         r'(?:carteiras?|wallets?)\b', before):
                return True
            if re.search(r'\b(?:tente|experimente|use|utilize|recomendo|recomenda|'
                         r'sugiro|sugere|sugerimos|prefira|escolha|que tal)\b'
                         r'[^.!?;\n]{0,50}$', before):
                if not re.search(r'\b(?:nao|nunca|nem)\b[^.!?;\n]{0,20}'
                                 r'\b(?:tente|experimente|use|utilize|recomendo|'
                                 r'recomenda|sugiro|sugere|sugerimos|prefira|'
                                 r'escolha)\b', before):
                    return True
            if (re.search(r'\b(?:pode|podem) conectar\s*$', before)
                    and not re.search(r'\b(?:perguntou se|quer saber se|'
                                      r'nao posso confirmar que)\b', before)
                    and not re.search(r'\b(?:nao|nunca) (?:pode|podem) '
                                      r'conectar\s*$', before)):
                return True
            qualified_question = re.search(
                r'\b(?:perguntou se|quer saber se|nao posso confirmar que|'
                r'nao ha confirmacao de que)\b', before)
            if qualified_question or _denied_claim_prefix(before):
                continue
            if re.search(r'\b(?:nao|nunca|nem)\b[^.!?;\n]{0,25}'
                         r'\b(?:suporta|aceita|integra|funciona com|'
                         r'e compativel com|tem integracao com)\s*$', before):
                continue
            if terminal == '?':
                continue  # A capability question is not a support assertion.
            if re.search(
                r'\b(?:z[\s-]?swap|a plataforma|o produto|o app|o aplicativo)\b'
                r'[^.!?;\n]{0,55}'
                r'\b(?:suporta|aceita|integra|funciona com|e compativel com|'
                r'tem integracao com|oferece suporte a|permite conectar|'
                r'oferece compatibilidade com)\s*$',
                before):
                return True
            if (re.search(r'\b(?:z[\s-]?swap|the platform|the app)\b'
                          r'[^.!?;\n]{0,55}\b(?:supports?|accepts?|integrates?|'
                          r'works with|is compatible with)\s*$', before)
                    and not re.search(r'\b(?:does not|doesn.t|is not|cannot|can not)\b'
                                      r'[^.!?;\n]{0,30}$', before)):
                return True
            if re.search(r'\b(?:conectar|conecte|conexao)\b[^.!?;\n]{0,30}'
                         r'\b(?:usando|com|via)\s*$', before):
                return True
            if re.match(r'\s+(?:e|esta|funciona|pode ser)\s+'
                        r'(?:suportad[ao]|compativel|integrad[ao]|'
                        r'conectad[ao]|usada? na z[\s-]?swap)\b', after):
                return True
            if re.match(r'\s+funciona\s+(?:na|com)\s+'
                        r'(?:z[\s-]?swap|a plataforma)\b', after):
                return True
    return False


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


def _evm_spelled_fee_claims_match_source(answer: str, context: str) -> bool:
    """Fail closed on a bounded written-out EVM plan rate, not general prose."""
    folded = _fold(answer)
    if 'por cento' not in folded:
        return True
    source = _evm_plan_fees(context)
    for clause in re.split(r'[.!?;\n]+', folded):
        if (not re.search(r'\bevm\b', clause)
                or not re.search(r'\b(?:taxas?|fees?|cobrancas?|cobra|paga)\b', clause)):
            continue
        # A comma followed by a new conjunction can introduce an unrelated
        # statement. Keep the EVM fee topic, but require a tier in that part.
        for part in re.split(r',\s+e\s+', clause):
            for rate in re.finditer(r'\bpor cento\b', part):
                before, after = part[:rate.start()], part[rate.end():]
                earlier_tiers = list(re.finditer(r'\b(' + _TIER_PATTERN + r')\b', before))
                later_tier = re.match(
                    r'\s+(?:para quem\s+(?:esta|fica)\s+(?:no|na)|'
                    r'(?:no|na|para o)\s+(?:plano\s+)?)\s*\b('
                    + _TIER_PATTERN + r')\b', after)
                if earlier_tiers:
                    tier = earlier_tiers[-1][1]
                    claim = before[earlier_tiers[-1].end():]
                    if '%' in claim:  # A preceding numeric fee owns this tier.
                        continue
                elif later_tier:
                    tier = later_tier[1]
                    claim = before
                else:
                    continue  # No bounded plan attribution in this part.
                fee_markers = list(re.finditer(
                    r'\b(?:taxas?|fees?|cobrancas?|cobra|paga)\b', claim))
                tail = (claim[fee_markers[-1].end():] if fee_markers else claim)
                tail = tail.strip(' ,:')
                if re.search(r'\bnao\s+(?:e|cobra|paga|fica)\b[^.!?;\n]{0,35}$', tail):
                    continue  # Explicitly denied rate, not a rate assertion.
                cue = re.search(r'\b(?:e|fica(?: em)?|vale|de)\s+', tail)
                words = (tail[cue.end():] if cue else tail).strip()
                words = re.sub(r'^de\s+', '', words)
                value = _SPELLED_PERCENT_VALUES.get(words)
                if value is None or source.get(tier) != value:
                    return False
    return True


def _evm_fee_enumeration_is_complete(answer: str, context: str) -> bool:
    """Check numeric EVM tier/fee claims; broad schedules need every tier."""
    folded = _fold(answer)
    if '%' not in folded:
        return True
    if (not re.search(r'\bevm\b', folded)
            and (re.search(r'\bsolana\b', folded)
                 or not re.search(r'\b(?:taxas?|fees?|cobrancas?)\b', folded))):
        return True
    source = _evm_plan_fees(context)
    pairs: dict[str, set[Decimal]] = {}

    def belongs_to_evm(match: re.Match[str]) -> bool:
        # In an answer that discusses both networks, do not assign a Solana
        # rate to the EVM tier matrix. The latest explicit network in this
        # sentence owns the claim; an unscoped claim keeps the old behavior.
        sentence_start = max(folded.rfind(mark, 0, match.start())
                             for mark in '.!?;\n') + 1
        window = folded[sentence_start:match.end()]
        networks = list(re.finditer(r'\b(?:evm|solana)\b', window))
        if networks:
            return networks[-1].group() == 'evm'
        trailing_network = re.match(r'\s*(?:(?:na|no|em)\s+)?(evm|solana)\b',
                                    folded[match.end():match.end() + 14])
        return trailing_network is None or trailing_network[1] == 'evm'

    # An inverse phrase such as "0,5% no Pro" must own that percentage; a
    # forward scan from the previous tier must not steal it across a comma.
    for match in re.finditer(
        _PERCENT_PATTERN + r'\s*(?:(?:e|corresponde)\s+(?:ao|do|da|para(?: o| a)?)\s+)?'
        r'(?:(?:no|na|para(?: o| a)?|do|da|ao)\s+)?'
        r'(?:plano\s+)?\b('
        + _TIER_PATTERN + r')\b', folded,
    ):
        if belongs_to_evm(match):
            pairs.setdefault(match[2], set()).add(Decimal(match[1].replace(',', '.')))
    for match in re.finditer(
        _PERCENT_PATTERN + r'\s+para quem\s+(?:esta|fica)\s+(?:no|na)\s+'
        r'(?:plano\s+)?\b(' + _TIER_PATTERN + r')\b', folded,
    ):
        if belongs_to_evm(match):
            pairs.setdefault(match[2], set()).add(Decimal(match[1].replace(',', '.')))
    # In a direct correction, the denied value is not a fee claim. The next
    # affirmative EVM rate may refer back to that same, single named tier.
    for match in re.finditer(
        r'\b(' + _TIER_PATTERN + r')\b[^;.!?\n]{0,65}\bnao\s+'
        r'(?:cobra|paga|tem|e)\s+' + _PERCENT_PATTERN
        + r'\s*[;.!?]\s*(?:a\s+)?(?:taxa|platform fee)\s+evm\s+'
        r'(?:e|fica(?:\s+em)?)\s+(?:de\s+)?' + _PERCENT_PATTERN,
        folded,
    ):
        pairs.setdefault(match[1], set()).add(Decimal(match[3].replace(',', '.')))
    for match in re.finditer(
        r'\b(' + _TIER_PATTERN + r')\b'
        r'(?:(?!\b(?:' + _TIER_PATTERN + r')\b)[^.!?;\n%]){0,75}?'
        + _PERCENT_PATTERN, folded,
    ):
        denied_rate = re.search(
            r'\b(?:nao|nunca|nem)\s+(?:cobra|paga|tem|possui|aplica|e)\s*'
            r'(?:(?:a|uma|taxa|platform|fee|evm|de)\s*)*$',
            folded[match.start():match.start(2)],
        )
        if belongs_to_evm(match) and not denied_rate and match[1] not in pairs:
            pairs.setdefault(match[1], set()).add(Decimal(match[2].replace(',', '.')))
    # A one- or two-tier comparison need not enumerate every plan, but each
    # concrete rate it *does* attach to a tier still needs matching evidence.
    if any(source.get(tier) is None or values != {source[tier]}
           for tier, values in pairs.items()):
        return False
    named = set(re.findall(r'\b(?:' + _TIER_PATTERN + r')\b', folded))
    if len(pairs) < 3 and ('solana' in folded or len(named) < 3):
        return True
    if set(source) != set(_EVM_TIERS):
        return False
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


_PLATFORM_FEE = (r'(?:platform fee|taxa (?:da |de )?(?:plataforma|z[\s-]?swap)'
                 r'|cobranca da z[\s-]?swap)')


def _overbroad_platform_fee_claim(answer: str) -> bool:
    """Catch a known unconditional fee assumption, not arbitrary fee policy."""
    folded = _mask_reported_quotes(_fold(answer))

    def mask_disclaimed_quote(match: re.Match[str]) -> str:
        after = folded[match.end():match.end() + 45]
        if re.match(r'\s+(?:esta|e|foi)\s+'
                    r'(?:incorret[ao]|fals[ao]|imprecis[ao]|errad[ao])\b', after):
            return ' ' * len(match.group())
        return match.group()

    folded = _QUOTED_CONCERN.sub(mask_disclaimed_quote, folded)
    fee = _PLATFORM_FEE
    target = (r'(?:cross[- ]chain\s+)?(?:swaps?|bridges?|pontes?|rotas?|'
              r'routes?|operacoes?|transacoes?)')
    quantified = (r'\b(?:todos?|todas?|qualquer|cada|every|all|any)\s+'
                  r'(?:(?:os?|as?|the)\s+)?(?:demais\s+)?' + target + r'\b')
    additive = re.compile(
        r'\b(?:alem d[aeo]s?|fora (?:a|da)|por cima d[aeo]s?|'
        r'se somam? (?:a|ao)|somam-se (?:a|ao)|'
        r'sao adicionais? (?:a|ao)|in addition to|on top of)\s+'
        r'(?:the\s+)?' + fee + r'\b')
    universal = re.compile('|'.join((
        quantified + r'[^.!?;\n]{0,75}\b(?:pagam?|cobram?|tem|possuem|'
        r'inclu(?:em|i)|envolvem|ha|existe|incide|includes?|pays?|has|have)\b'
        r'[^.!?;\n]{0,35}\b' + fee + r'\b',
        quantified + r'[^.!?;\n]{0,75}\b' + fee + r'\b'
        r'\s+(?:se\s+)?(?:aplica(?:-se)?|incide|applies?)\b',
        quantified + r'[^.!?;\n]{0,100}' + additive.pattern,
        r'\b' + fee + r'\b[^.!?;\n]{0,50}\b(?:aplica(?:-se|da)?|'
        r'applies?|cobrada|cobra|vale|entra|incide|soma|somada|is charged)\b'
        r'[^.!?;\n]{0,45}' + quantified,
        r'\b(?:ha|existe|incide)\s+(?:a\s+|uma\s+)?' + fee + r'\b'
        r'[^.!?;\n]{0,25}\b(?:em|nas?|para|for|in|on)\s+' + quantified,
        r'\b' + fee + r'\b\s+(?:em|nas?|para|for|in|on)\s+' + quantified,
        r'\bz[\s-]?swap\b[^.!?;\n]{0,25}\b(?:sempre\s+)?cobra\s+'
        r'(?:a\s+)?(?:sua\s+)?taxa\b[^.!?;\n]{0,35}'
        r'\b(?:em|nas?|para)\s+' + quantified,
        r'\bz[\s-]?swap\b[^.!?;\n]{0,25}\bsempre\s+cobra\s+'
        r'(?:a\s+)?sua\s+taxa\s+(?:em|nas?)\s+' + target + r'\b',
        r'\b' + fee + r'\b[^.!?;\n]{0,35}'
        r'\b(?:sempre que houver|whenever there is)\s+(?:uma?\s+)?'
        + target + r'\b',
        r'\b' + target + r'\b[^.!?;\n]{0,30}\bsempre\s+'
        r'(?:inclu(?:em|i)|cobram?|tem)\s+(?:a\s+|uma\s+)?' + fee + r'\b',
        r'\bthere is always\s+(?:a\s+)?' + fee + r'\b'
        r'[^.!?;\n]{0,25}\b(?:on|in|for)\s+' + target + r'\b',
        r'\b(?:cobra|aplica|inclui)\s+(?:a\s+)?' + fee + r'\b'
        r'[^.!?;\n]{0,40}' + quantified,
        r'\bsempre\s+(?:ha|existe|incide)\s+(?:a\s+|uma\s+)?' + fee + r'\b'
        r'[^.!?;\n]{0,35}\b(?:nas?|em|para|on|in|for)\s+' + target + r'\b',
        r'\b(?:nas?|em)\s+(?:pontes?|bridges?)\b[^.!?;\n]{0,35}'
        r'\bsempre ha duas taxas\b[^.!?;\n]{0,35}'
        r'\bda rede e da z[\s-]?swap\b',
    )))
    conditional = re.compile('|'.join((
        r'\b(?:se|quando) aplicavel\b',
        r'\b(?:se|quando|caso)\s+(?:houver|existir|incidir|for cobrada|'
        r'estiver ativa)\s+(?:uma?\s+)?' + fee + r'\b',
        r'\bse\s+(?:a\s+)?rota\s+(?:cobrar|aplicar)\s+(?:a\s+)?'
        + fee + r'\b',
        r'\b' + fee + r'\b[^.!?;\n]{0,20}\bse houver\b',
        r'\b' + fee + r'\b[^.!?;\n]{0,35}\bquando houver\b',
        r'\b' + fee + r'\b[^.!?;\n]{0,30}'
        r'\b(?:quando|se)\s+(?:ela\s+)?(?:for\s+)?'
        r'(?:aplicavel|cobrada|incidir)\b',
        r'\b(?:se|quando|caso)\s+(?:a\s+)?(?:cobranca|taxa da plataforma)\s+'
        r'(?:for|estiver|seja)\s+(?:ativa|aplicavel)\b',
        r'\b(?:onde|em que)\s+(?:a\s+)?(?:cobranca|taxa da plataforma)\s+'
        r'(?:esta|esteja|for)\s+(?:ativa|aplicavel)\b',
        r'\brotas?\s+em que\s+(?:a\s+)?cobranca\s+incide\b',
        r'\brotas?\s+evm\s+suportadas?\b[^.!?;\n]{0,45}'
        r'\b(?:mecanismo|cobranca)\s+(?:esta|esteja|for)\s+ativ[ao]\b',
        r'\brotas?\s+evm\s+suportadas?\s+com\s+mecanismo\s+ativo\b',
        r'\brotas?\s+elegiveis\b',
        r'\b(?:na|em)\s+rota\s+evm\b[^.!?;\n]{0,45}'
        r'\bmecanismo\s+(?:esta|estiver|for)?\s*ativo\b',
        r'\b(?:na|em|pela)\s+rota\s+aplicavel\b',
        r'\b(?:na|pela|via)\s+jupiter\b[^.!?;\n]{0,65}'
        r'\b(?:usdc|sol)\b[^.!?;\n]{0,35}\b(?:swap|par|rota)\b',
    )))

    def denied(prefix: str) -> bool:
        return (_reported_or_denied_prefix(prefix)
                or bool(re.search(
                    r'\b(?:nao e correto (?:dizer|afirmar) que|'
                    r'nao (?:devemos|se deve|assuma) (?:assumir |presumir )?que|'
                    r'it is incorrect to say that|it is false that)\b'
                    r'[^.!?;\n]{0,90}$', prefix)))

    previous_condition = False
    for sentence in re.finditer(r'[^.!?;\n]+[.!?;\n]?', folded):
        clause = sentence.group().strip()
        if clause.endswith('?'):
            previous_condition = False
            continue
        for match in universal.finditer(clause):
            prefix = clause[max(0, match.start() - 120):match.start()]
            suffix = clause[match.end():match.end() + 40]
            if (denied(prefix)
                    or re.search(r'\b(?:nao|nem|nunca)\s*$', prefix)
                    or re.search(r'\b(?:nao|nem|nunca)\b', match.group())
                    or conditional.search(match.group())
                    or (re.search(r'\ba ideia de que\b', prefix)
                        and re.match(r'\s+e\s+(?:fals[ao]|incorret[ao])\b', suffix))):
                continue
            return True
        for match in additive.finditer(clause):
            prefix = clause[max(0, match.start() - 120):match.start()]
            if denied(prefix):
                continue
            local = clause[max(0, match.start() - 135):min(len(clause),
                                                             match.end() + 100)]
            if conditional.search(local) or previous_condition:
                continue
            return True
        previous_condition = bool(re.fullmatch(
            r'se houver\s+(?:a\s+|uma\s+)?' + fee + r'\s*;', clause))
    return False


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
        if feature == 'terminal pro' and _terminal_beta_is_promoted(folded):
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


def _terminal_beta_is_promoted(folded_answer: str) -> bool:
    """A beta can be used in beta; it cannot be described as fully launched."""
    full_release = (
        r'\b(?:ja\s+)?(?:esta|foi|ficou)\s+(?:em\s+)?producao\s+para\s+todos\b'
        r'|\b(?:ja\s+)?(?:esta|foi|ficou)\s+(?:totalmente|plenamente|completamente)\s+'
        r'(?:lancad[oa]|disponivel|operacional)\b'
        r'|\b(?:ja\s+)?(?:foi|esta)\s+lancad[oa]\s+(?:para\s+todos|sem\s+restricoes)\b'
        r'|\b(?:ja\s+)?(?:saiu|deixou)\s+(?:de|do|da)\s+beta\b'
        r'|\bfase\s+de\s+testes?\s+(?:ja\s+)?(?:acabou|terminou|foi\s+encerrad[ao])\b'
    )
    clauses = re.split(r'[.!?;\n]+', folded_answer)
    prior_terminal = False
    for clause in clauses:
        mentions_terminal = bool(re.search(r'\bterminal pro\b', clause))
        # An immediate "Já está ..." can refer back to Terminal Pro. A named
        # different feature ends that carry-over rather than borrowing status.
        carries_terminal = bool(prior_terminal and re.match(
            r'\s*(?:(?:mas|porem|e)\s+)?(?:ele|esse recurso|o recurso)?\s*'
            r'(?:ja\s+)?(?:esta|foi|ficou)\b', clause))
        carries_terminal = carries_terminal or bool(prior_terminal and re.match(
            r'\s*(?:a\s+)?fase\s+de\s+testes?\b', clause))
        if mentions_terminal or carries_terminal:
            for claim in re.finditer(full_release, clause):
                # "Para todos os participantes do beta" is a bounded beta
                # audience, not a claim of unrestricted general release.
                scope = clause[claim.start():claim.end() + 55]
                if re.search(r'\bpara todos os (?:participantes|testadores|usuarios)\b'
                             r'[^.!?;\n]{0,25}\bbeta\b', scope):
                    continue
                if not re.search(r'\b(?:nao|nunca|nem)\s*$',
                                 clause[max(0, claim.start() - 12):claim.start()]):
                    return True
        prior_terminal = mentions_terminal
    return False


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
    if _unsupported_route_optimization(text):
        return ResponseCheck(False, 'unsupported_route_optimization')
    if (_asserted_exclusive_wallet_connection(text)
            and not _asserted_exclusive_wallet_connection(official_context)):
        return ResponseCheck(False, 'unsupported_wallet_connection_signature')
    if _unapproved_wallet_example(text, official_context):
        return ResponseCheck(False, 'unapproved_wallet_example')
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
    if not _evm_spelled_fee_claims_match_source(text, official_context):
        return ResponseCheck(False, 'unsupported_spelled_plan_fee')
    if not _evm_fee_enumeration_is_complete(text, official_context):
        return ResponseCheck(False, 'incomplete_plan_fee_matrix')
    if not _solana_fee_scope_is_preserved(text):
        return ResponseCheck(False, 'overbroad_solana_fee_scope')
    if _overbroad_platform_fee_claim(text):
        return ResponseCheck(False, 'overbroad_platform_fee')
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


def _public_evm_fee_reply(question: str, official_context: str) -> str | None:
    """Restate only the requested EVM plan fees from complete public sections."""
    requested = set(re.findall(r'\b(?:' + _TIER_PATTERN + r')\b', _fold(question)))
    if 1 <= len(requested) <= 2:
        tiers = tuple(tier for tier in _EVM_TIERS if tier in requested)
    elif (len(requested) >= 3 or re.search(
            r'\b(?:todos os planos|taxas? (?:evm )?(?:por plano|dos planos))\b',
                                      _fold(question))):
        tiers = _EVM_TIERS
    else:
        return None
    parts = re.split(r'\[contexto oficial: ([^\]]+)\]\s*', _fold(official_context))
    approved: set[str] = set()
    for heading, body in zip(parts[1::2], parts[2::2]):
        for tier in tiers:
            if not re.match(r'plano ' + tier + r'\b', heading):
                continue
            flat = ' '.join(body.split())
            if (re.search(r'\bplatform fee\b.{0,180}?\bevm\b.{0,180}?'
                          + _PERCENT_PATTERN, flat)
                    and re.search(r'\brotas?\s+(?:evm\s+)?suportadas?\s+onde o '
                                  r'mecanismo esta ativo\b', flat)):
                approved.add(tier)
    source = _evm_plan_fees(official_context)
    if any(tier not in approved or tier not in source for tier in tiers):
        return None
    rates = [f'{tier.title()} {source[tier]:.2f}%'.replace('.', ',')
             for tier in tiers]
    if len(tiers) == 1:
        amount = f'{source[tiers[0]]:.2f}'.replace('.', ',')
        reply = ('Nas rotas EVM suportadas onde a cobrança está ativa, a taxa '
                 f'da plataforma para o plano {tiers[0].title()} é '
                 f'{amount}%.')
    else:
        schedule = ', '.join(rates[:-1]) + ' e ' + rates[-1]
        reply = ('Nas rotas EVM suportadas onde a cobrança está ativa, as taxas '
                 f'da plataforma por plano são: {schedule}.')
    reply += (' Custos de rede e de terceiros podem existir à parte; confira '
              'os custos da rota antes de confirmar.')
    if validate_public_response(reply, official_context=official_context).allowed:
        return reply
    return None


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


def is_broad_product_comparison(question: str) -> bool:
    """Identify a broad product comparison without plan or feature narrowing."""
    query = _fold(question)
    return not (not re.search(r'\bz[\s-]*swap\b', query)
            or not re.search(r'\b(?:outras? plataformas?|concorrent\w*)\b', query)
            or not re.search(r'\b(?:diferenc\w*|compar\w*|vantag\w*|oferec\w*)\b', query)
            or re.search(r'\b(?:terminal pro|portfolio|orders|planos?|free|pro|trader|pilot)\b', query))


def _public_broad_comparison_reply(question: str, official_context: str) -> str | None:
    """Answer a broad product comparison only from the retrieved public snapshot."""
    if not is_broad_product_comparison(question):
        return None
    sections = re.split(r'(?m)^\[contexto oficial: ([^\]\n]+)\][ \t]*$',
                        _fold(official_context))
    approved = {heading: ' '.join(body.split())
                for heading, body in zip(sections[1::2], sections[2::2])}
    positioning = approved.get('z-swap — posicionamento institucional publico', '')
    platform_map = approved.get('mapa publico da plataforma', '')
    if (not all(fragment in positioning for fragment in (
            'a z-swap conecta etapas que normalmente vivem separadas: entender, analisar, '
            'testar, simular, planejar, executar e acompanhar.',
            ))
            or not all(fragment in platform_map for fragment in (
            'orders: planejamento e gatilhos, em estado partial.',
            'swap: preparacao e execucao de rotas suportadas.',
            'portfolio: acompanhamento partial de ativos curados suportados.',
            ))
            or not {'terminal pro', 'portfolio', 'orders'} <= _source_feature_statuses(official_context)):
        return None
    reply = ('Na base pública revisada, a Z-SWAP reúne análise, simulação, '
             'planejamento de ordens, swap e acompanhamento numa mesma experiência. '
             'O Terminal Pro está em beta, e Portfolio e Orders estão parcialmente '
             'disponíveis. Não tenho uma comparação oficial equivalente com outras '
             'plataformas para afirmar que essa combinação seja exclusiva ou superior.')
    if validate_public_response(reply, official_context=official_context).allowed:
        return reply
    return None


def _public_swap_route_reply(official_context: str) -> str | None:
    """Use only the retrieved canonical public swap section for route mechanics."""
    parts = re.split(r'\[contexto oficial: ([^\]]+)\]\s*', _fold(official_context))
    for heading, body in zip(parts[1::2], parts[2::2]):
        if heading != 'swaps e pontes':
            continue
        flat = ' '.join(body.split())
        if not all(fragment in flat for fragment in (
            'a z-swap seleciona a fonte de cotacao conforme as redes envolvidas '
            'e mostra a rota retornada para o par escolhido',
            'nao compara todas as fontes em cada pedido',
        )):
            continue
        reply = ('A Z-SWAP seleciona a fonte de cotação conforme as redes envolvidas '
                 'e mostra a rota retornada para o par escolhido. Isso não significa '
                 'consultar todas as fontes a cada pedido ou prometer o melhor preço. '
                 'Confira a cotação e os custos antes de confirmar.')
        if validate_public_response(reply, official_context=official_context).allowed:
            return reply
    return None


def public_fallback_for(reason: str, *, official_context: str = '', question: str = '') -> str:
    """Host-owned public reply for a few known quality failures."""
    if reason in {'unsupported_wallet_connection_signature',
                  'unapproved_wallet_example'}:
        if re.search(r'\b(?:conecta\w*|conexao|carteira\w*|wallet\w*)\b',
                     _fold(question)):
            return ('Para entender a dificuldade de conexão, diga qual carteira '
                    'e rede você usa e qual mensagem de erro aparece. Não compartilhe '
                    'seed phrase, chave privada ou senha da carteira.')
        return PUBLIC_FALLBACK
    if reason in {'best_price_guarantee', 'unsupported_route_optimization'}:
        reply = _public_swap_route_reply(official_context)
        if reply is not None:
            return reply
        return ('Não posso confirmar uma escolha automática da melhor rota nem '
                'prometer o melhor preço ou taxa. Confira a cotação e os custos '
                'antes de confirmar.')
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
    if reason in {'incomplete_plan_fee_matrix', 'unsupported_spelled_plan_fee'}:
        reply = _public_evm_fee_reply(question, official_context)
        if reply is not None:
            return reply
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
    if reason == 'overbroad_platform_fee':
        return ('Custos de rede, bridge ou terceiros podem variar conforme a rota, '
                'inclusive quando a taxa da plataforma não incide. Confira os '
                'custos apresentados antes de confirmar.')
    if reason == 'unverified_live_proof':
        return ('Posso explicar o estado documentado na base pública revisada, '
                'mas não fiz uma verificação ao vivo da plataforma. Confira a '
                'disponibilidade na interface para o seu caso.')
    if reason == 'missing_feature_status':
        reply = _public_broad_comparison_reply(question, official_context)
        if reply is not None:
            return reply
        reply = _public_feature_status_reply(official_context)
        if reply is not None:
            return reply
        return ('A base pública distingue recursos em beta ou parcialmente '
                'disponíveis. Posso detalhar o estado documentado de cada um; '
                'confira a disponibilidade na interface para o seu caso.')
    return PUBLIC_FALLBACK
