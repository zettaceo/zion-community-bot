from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from urllib.parse import urlparse

import idna

from .config import Settings
from .db import ZionDB
from .models import (
    AbuseDecision,
    ChatBurstDecision,
    FloodDecision,
    LinkDecision,
    OperatingState,
    SensitiveContentDecision,
    Severity,
)


URL_REGEX = re.compile(
    r"(?i)\b(?:https?://|www\.|t\.me/)[^\s<>]+"
)

UNSUPPORTED_VISIBLE_SCHEME_REGEX = re.compile(
    r"(?i)\b("
    r"tg|ton|solana|ethereum|javascript|data|file|intent|mailto|ftp"
    r"):(?://)?[^\s<>]+"
)

BASE58_PRIVATE_KEY_REGEX = re.compile(
    r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{48,128}"
    r"(?![1-9A-HJ-NP-Za-km-z])"
)

POLICY_DOMAIN_REGEX = re.compile(
    r"(?i)^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

SENSITIVE_LABEL_REGEX = re.compile(
    r"(?i)\b("
    r"private\s+key|chave\s+privada|"
    r"seed\s+phrase|frase\s+semente|"
    r"recovery\s+phrase|frase\s+de\s+recupera[cç][aã]o|"
    r"mnemonic"
    r")\b"
)

LONG_SECRET_AFTER_LABEL_REGEX = re.compile(
    r"(?is)\b("
    r"private\s+key|chave\s+privada|"
    r"seed\s+phrase|frase\s+semente|"
    r"recovery\s+phrase|frase\s+de\s+recupera[cç][aã]o|"
    r"mnemonic"
    r")\b\s*[:=\-]?\s*(.{24,})"
)

INVISIBLE_SECURITY_CODEPOINTS = {
    0x200B,
    0x200C,
    0x200D,
    0x2060,
    0xFEFF,
}

ALLOWED_LINK_SCHEMES = frozenset({"http", "https"})


def _nfkc_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "")


def _contains_invisible_security_char(value: str) -> bool:
    return any(
        ord(char) in INVISIBLE_SECURITY_CODEPOINTS
        for char in value
    )


def _normalize_security_text(value: str) -> str:
    normalized = _nfkc_text(value)
    return "".join(
        char
        for char in normalized
        if ord(char) not in INVISIBLE_SECURITY_CODEPOINTS
    )


def normalize_link_target(value: str) -> tuple[str | None, str | None]:
    raw = _nfkc_text(value).strip()
    if _contains_invisible_security_char(raw):
        return None, "invisible-link-character"
    if not raw:
        return None, None

    lowered = raw.lower()
    if lowered.startswith("www.") or lowered.startswith("t.me/"):
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)
    except ValueError:
        return None, "unparseable-url"

    scheme = (parsed.scheme or "").lower()
    if scheme and scheme not in ALLOWED_LINK_SCHEMES:
        return None, scheme

    if not scheme:
        raw = "https://" + raw
        scheme = "https"

    domain = _normalize_domain(raw)
    if scheme in ALLOWED_LINK_SCHEMES and not domain:
        return None, f"invalid-{scheme}"

    return domain, None


def _normalize_domain(raw_url: str) -> str | None:
    candidate = _nfkc_text(raw_url).strip().rstrip(".,);]}>")
    if _contains_invisible_security_char(candidate):
        return None
    candidate = candidate.translate({
        0x3002: ".",
        0xFF0E: ".",
        0xFF61: ".",
    })
    if candidate.lower().startswith("www."):
        candidate = "https://" + candidate
    elif candidate.lower().startswith("t.me/"):
        candidate = "https://" + candidate

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    try:
        return idna.encode(
            host,
            uts46=True,
            transitional=False,
            std3_rules=True,
        ).decode("ascii").lower() or None
    except (idna.IDNAError, UnicodeError, ValueError):
        return None


def normalize_policy_domain(value: str) -> str | None:
    raw = _nfkc_text(value).strip()
    if not raw:
        return None
    domain, unsupported_scheme = normalize_link_target(raw)
    if unsupported_scheme is not None:
        return None
    if not domain or not POLICY_DOMAIN_REGEX.fullmatch(domain):
        return None
    return domain


def extract_domains(text: str) -> list[str]:
    domains: list[str] = []
    normalized_text = _nfkc_text(text)
    for raw in URL_REGEX.findall(normalized_text):
        domain = _normalize_domain(raw)
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def extract_unsupported_schemes(text: str) -> list[str]:
    normalized_text = _nfkc_text(text)
    schemes: list[str] = []
    for raw in URL_REGEX.findall(normalized_text):
        domain, error = normalize_link_target(raw)
        if domain:
            continue
        marker = error or "invalid-http-target"
        if marker not in schemes:
            schemes.append(marker)
    for match in UNSUPPORTED_VISIBLE_SCHEME_REGEX.finditer(normalized_text):
        scheme = match.group(1).lower()
        if scheme not in schemes:
            schemes.append(scheme)
    return schemes


def domain_matches(domain: str, allowed: str) -> bool:
    domain = domain.lower().strip(".")
    allowed = allowed.lower().strip(".")
    return domain == allowed or domain.endswith("." + allowed)


def detect_sensitive_content(text: str) -> SensitiveContentDecision:
    text = _normalize_security_text(text)
    if not SENSITIVE_LABEL_REGEX.search(text):
        return SensitiveContentDecision()
    match = LONG_SECRET_AFTER_LABEL_REGEX.search(text)
    if not match:
        return SensitiveContentDecision()

    tail = match.group(2).strip()
    words = re.findall(
        r"[^\W\d_]+(?:['-][^\W\d_]+)*",
        tail,
        flags=re.UNICODE,
    )
    if (
        len(words) >= 12
        and all(
            word.replace("'", "").replace("-", "").isalpha()
            and 1 <= len(word) <= 32
            for word in words[:12]
        )
    ):
        return SensitiveContentDecision(
            detected=True,
            kind="possible_wallet_secret",
            reason=(
                "possível seed phrase/chave privada identificada "
                "junto a um rótulo sensível"
            ),
        )

    if re.search(r"\b(?:0x)?[A-Fa-f0-9]{64}\b", tail):
        return SensitiveContentDecision(
            detected=True,
            kind="possible_private_key",
            reason=(
                "possível chave privada identificada "
                "junto a um rótulo sensível"
            ),
        )

    if BASE58_PRIVATE_KEY_REGEX.search(tail):
        return SensitiveContentDecision(
            detected=True,
            kind="possible_private_key",
            reason=(
                "possível chave privada Base58 identificada "
                "junto a um rótulo sensível"
            ),
        )

    array_match = re.search(
        r"\[((?:\s*\d{1,3}\s*,){31,63}\s*\d{1,3}\s*)\]",
        tail,
    )
    if array_match:
        values = [
            int(value)
            for value in re.findall(r"\d{1,3}", array_match.group(1))
        ]
        if (
            len(values) in {32, 64}
            and all(0 <= value <= 255 for value in values)
        ):
            return SensitiveContentDecision(
                detected=True,
                kind="possible_private_key",
                reason=(
                    "possível chave privada em array de bytes identificada "
                    "junto a um rótulo sensível"
                ),
            )

    return SensitiveContentDecision()


# Deterministic community-language policy. These rules are intentionally
# local/auditable: Mistral may observe context, but it never decides punishment.
_LEET_SUBSTITUTIONS = str.maketrans({
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "$": "s",
})

_CONFUSABLE_SUBSTITUTIONS = str.maketrans({
    # Small, explicit set of common Cyrillic/Greek homoglyphs. This is not a
    # general transliterator; it only closes trivial visual bypasses.
    "а": "a", "ɑ": "a", "α": "a",
    "е": "e", "ε": "e",
    "і": "i", "ι": "i",
    "ј": "j",
    "κ": "k",
    "о": "o", "ο": "o",
    "р": "p", "ρ": "p",
    "с": "c",
    "ѕ": "s",
    "τ": "t",
    "υ": "u",
    "ν": "v",
    "х": "x", "χ": "x",
    "у": "y",
})

_PROFANITY_RULES = (
    ("profanity_pt_01", "puta que te pariu"),
    ("profanity_pt_02", "puta que pariu"),
    ("profanity_pt_03", "puta merda"),
    ("profanity_pt_04", "porra"),
    ("profanity_pt_05", "caralho"),
    ("profanity_pt_06", "caraio"),
    ("profanity_pt_07", "karalho"),
    ("profanity_pt_08", "merda"),
    ("profanity_pt_09", "bosta"),
    ("profanity_pt_10", "cacete"),
    ("profanity_pt_11", "fodase"),
    ("profanity_pt_12", "foder"),
    ("profanity_pt_13", "fodeu"),
    ("profanity_pt_14", "fode"),
    ("profanity_pt_15", "fodido"),
    ("profanity_pt_16", "fodida"),
    ("profanity_pt_17", "fudeu"),
    ("profanity_pt_18", "fudeo"),
    ("profanity_pt_19", "fuder"),
    ("profanity_pt_20", "foda"),
    ("profanity_pt_21", "puta"),
    ("profanity_pt_22", "puto"),
    ("profanity_pt_23", "putaria"),
    ("profanity_pt_24", "puteiro"),
    ("profanity_pt_25", "putinha"),
    ("profanity_en_01", "motherfucking"),
    ("profanity_en_02", "fucking"),
    ("profanity_en_03", "bullshit"),
    ("profanity_en_04", "fuck"),
    ("profanity_en_05", "shit"),
    ("profanity_en_06", "cunt"),
)

_EXPLICIT_SEXUAL_RULES = (
    ("explicit_pt_01", "buceta"),
    ("explicit_pt_02", "boceta"),
    ("explicit_pt_03", "xota"),
    ("explicit_pt_04", "xoxota"),
    ("explicit_pt_05", "chochota"),
    ("explicit_pt_06", "chota"),
    ("explicit_pt_07", "xereca"),
    ("explicit_pt_08", "xibiu"),
    ("explicit_pt_09", "piroca"),
    ("explicit_pt_10", "piroka"),
    ("explicit_pt_11", "piru"),
    ("explicit_pt_12", "punheta"),
    ("explicit_pt_13", "punheteiro"),
    ("explicit_pt_14", "punheteira"),
    ("explicit_pt_15", "siririca"),
    ("explicit_pt_16", "boquete"),
    ("explicit_pt_17", "bronha"),
    ("explicit_content_01", "pornografia"),
    ("explicit_content_02", "pornographic"),
    ("explicit_content_03", "pornography"),
    ("explicit_content_04", "porno"),
    ("explicit_content_05", "porn"),
    ("explicit_content_06", "hentai"),
    ("explicit_content_07", "rule34"),
)

_INSULT_RULES = (
    ("directed_pt_01", "filho de uma puta"),
    ("directed_pt_02", "filha de uma puta"),
    ("directed_pt_03", "filho de um corno"),
    ("directed_pt_04", "filho da puta"),
    ("directed_pt_05", "filha da puta"),
    ("directed_pt_06", "seu merda"),
    ("directed_pt_07", "sua merda"),
    ("directed_pt_08", "seu bosta"),
    ("directed_pt_09", "sua bosta"),
    ("directed_pt_10", "seu lixo"),
    ("directed_pt_11", "sua lixo"),
    ("directed_pt_12", "seu verme"),
    ("directed_pt_13", "sua vadia"),
    ("directed_pt_14", "sua puta"),
    ("directed_pt_15", "sua piranha"),
    ("directed_pt_16", "seu arrombado"),
    ("directed_pt_17", "sua arrombada"),
    ("directed_pt_18", "seu idiota"),
    ("directed_pt_19", "sua idiota"),
    ("directed_pt_20", "seu imbecil"),
    ("directed_pt_21", "sua imbecil"),
    ("directed_pt_22", "seu babaca"),
    ("directed_pt_23", "sua babaca"),
    ("directed_pt_24", "seu otario"),
    ("directed_pt_25", "sua otaria"),
    ("directed_pt_26", "vai se foder"),
    ("directed_pt_27", "vai se fuder"),
    ("directed_pt_28", "vai a merda"),
    ("directed_pt_29", "vai tomar no cu"),
    ("directed_pt_30", "vai toma no cu"),
    ("directed_pt_31", "toma no cu"),
    ("directed_pt_32", "tomar no cu"),
    ("directed_pt_33", "pau no cu"),
    ("directed_pt_34", "pau no seu cu"),
    ("directed_pt_35", "pau no teu cu"),
    ("directed_pt_36", "enfia no cu"),
    ("directed_pt_37", "enfia no seu cu"),
    ("directed_pt_38", "enfia no teu cu"),
    ("directed_pt_39", "chupa meu pau"),
    ("directed_pt_40", "chupa o meu pau"),
    ("directed_pt_41", "vai pra puta que pariu"),
    ("directed_en_01", "go fuck yourself"),
    ("directed_en_02", "fuck you"),
    ("directed_en_03", "piece of shit"),
    ("directed_en_04", "son of a bitch"),
    ("insult_pt_01", "idiota"),
    ("insult_pt_02", "imbecil"),
    ("insult_pt_03", "babaca"),
    ("insult_pt_04", "otario"),
    ("insult_pt_05", "otaria"),
    ("insult_pt_06", "burro"),
    ("insult_pt_07", "burra"),
    ("insult_pt_08", "besta"),
    ("insult_pt_09", "cretino"),
    ("insult_pt_10", "cretina"),
    ("insult_pt_11", "canalha"),
    ("insult_pt_12", "trouxa"),
    ("insult_pt_13", "panaca"),
    ("insult_pt_14", "paspalho"),
    ("insult_pt_15", "paspalha"),
    ("insult_pt_16", "pilantra"),
    ("insult_pt_17", "arrombado"),
    ("insult_pt_18", "arrombada"),
    ("insult_pt_19", "cuzao"),
    ("insult_pt_20", "cusao"),
    ("insult_pt_21", "escroto"),
    ("insult_pt_22", "escrota"),
    ("insult_pt_23", "desgracado"),
    ("insult_pt_24", "desgracada"),
    ("insult_pt_25", "lazarento"),
    ("insult_pt_26", "lazarenta"),
    ("insult_pt_27", "corno"),
    ("insult_pt_28", "corna"),
    ("insult_pt_29", "vagabundo"),
    ("insult_pt_30", "vagabunda"),
    ("insult_pt_31", "vadia"),
    ("insult_pt_32", "piranha"),
    ("insult_pt_33", "biscate"),
    ("insult_pt_34", "piriguete"),
    ("insult_pt_35", "safado"),
    ("insult_pt_36", "safada"),
    ("insult_pt_37", "nojento"),
    ("insult_pt_38", "nojenta"),
    ("insult_pt_39", "inutil"),
    ("insult_pt_40", "ze ruela"),
    ("insult_pt_41", "fdp"),
    ("insult_en_01", "motherfucker"),
    ("insult_en_02", "asshole"),
    ("insult_en_03", "dumbass"),
    ("insult_en_04", "bitch"),
    ("insult_en_05", "dickhead"),
    ("insult_en_06", "prick"),
    ("insult_en_07", "moron"),
    ("insult_en_08", "idiot"),
    ("insult_en_09", "stupid"),
    ("insult_en_10", "whore"),
    ("insult_en_11", "slut"),
)

_CONTEXTUAL_INSULT_RULES = (
    ("contextual_insult_pt_01", "animal"),
    ("contextual_insult_pt_02", "anta"),
    ("contextual_insult_pt_03", "jegue"),
    ("contextual_insult_pt_04", "jumento"),
    ("contextual_insult_pt_05", "asno"),
    ("contextual_insult_pt_06", "palhaco"),
    ("contextual_insult_pt_07", "cadela"),
    ("contextual_insult_pt_08", "lixo"),
    ("contextual_insult_pt_09", "verme"),
    ("contextual_insult_pt_10", "doente"),
    ("contextual_insult_pt_11", "louco"),
    ("contextual_insult_pt_12", "louca"),
    ("contextual_insult_pt_13", "mane"),
)

_SLUR_RULES = (
    ("slur_pt_01", "traveco"),
    ("slur_pt_02", "baitola"),
    ("slur_pt_03", "boiola"),
    ("slur_pt_04", "bicha"),
    ("slur_pt_05", "bixa"),
    ("slur_pt_06", "viado"),
    ("slur_pt_07", "viadinho"),
    ("slur_pt_08", "bichinha"),
    ("slur_pt_09", "bixinha"),
    ("slur_pt_10", "bichona"),
    ("slur_pt_11", "bixona"),
    ("slur_pt_12", "marica"),
    ("slur_pt_13", "mongoloide"),
    ("slur_en_01", "nigger"),
    ("slur_en_02", "nigga"),
    ("slur_en_03", "faggot"),
    ("slur_en_04", "fag"),
    ("slur_en_05", "tranny"),
    ("slur_en_06", "chink"),
    ("slur_en_07", "kike"),
    ("slur_en_08", "spic"),
    ("slur_en_09", "wetback"),
)

_CONTEXTUAL_HATE_RULES = (
    ("contextual_hate_pt_01", "macaco"),
    ("contextual_hate_pt_02", "macaca"),
    ("contextual_hate_pt_03", "veado"),
    ("contextual_hate_pt_04", "sapatao"),
    ("contextual_hate_pt_05", "retardado"),
    ("contextual_hate_pt_06", "retardada"),
    ("contextual_hate_pt_07", "aleijado"),
    ("contextual_hate_pt_08", "aleijada"),
)

_THREAT_RULES = (
    ("threat_pt_01", "eu vou te matar"),
    ("threat_pt_02", "vou te matar"),
    ("threat_pt_03", "te mato"),
    ("threat_pt_04", "matar voce"),
    ("threat_pt_05", "vou matar voce"),
    ("threat_pt_06", "vou acabar com voce"),
    ("threat_pt_07", "vou te arrebentar"),
    ("threat_pt_08", "vou quebrar sua cara"),
    ("threat_pt_09", "vou quebrar tua cara"),
    ("threat_pt_10", "vou te quebrar"),
    ("threat_pt_11", "vou te pegar"),
    ("threat_pt_12", "vou atras de voce"),
    ("threat_pt_13", "vou te cacar"),
    ("threat_pt_14", "sei onde voce mora"),
    ("threat_pt_15", "voce vai morrer"),
    ("threat_pt_16", "vai morrer"),
    ("threat_pt_17", "merece morrer"),
    ("threat_pt_18", "tomara que voce morra"),
    ("threat_pt_19", "tomara que morra"),
    ("self_harm_pt_01", "vai se matar"),
    ("self_harm_pt_02", "se mata"),
    ("self_harm_pt_03", "se mate"),
    ("threat_en_01", "i am going to kill you"),
    ("threat_en_02", "i m going to kill you"),
    ("threat_en_03", "i will kill you"),
    ("threat_en_04", "kill you"),
    ("threat_en_05", "you will die"),
    ("self_harm_en_01", "go kill yourself"),
    ("self_harm_en_02", "kill yourself"),
    ("threat_en_06", "i know where you live"),
)

_ADULT_DOMAIN_RULES = (
    ("adult_domain_01", "xvideos.com"),
    ("adult_domain_02", "xvideos.red"),
    ("adult_domain_03", "onlyfans.com"),
    ("adult_domain_04", "pornhub.com"),
    ("adult_domain_05", "xhamster.com"),
    ("adult_domain_06", "xnxx.com"),
    ("adult_domain_07", "fatalmodel.com"),
    ("adult_domain_08", "socialmediagirls.com"),
    ("adult_domain_09", "sambaporno.com"),
    ("adult_domain_10", "animeshentai.biz"),
    ("adult_domain_11", "hentaistube.com"),
    ("adult_domain_12", "privacy.com.br"),
    ("adult_domain_13", "thehentai.net"),
    ("adult_domain_14", "photoacompanhantes.com"),
    ("adult_domain_15", "cameraprive.com"),
    ("adult_domain_16", "hiper.cool"),
    ("adult_domain_17", "shokka.com"),
    ("adult_domain_18", "thisvid.com"),
    ("adult_domain_19", "ixxx.com"),
)

_ADULT_BRAND_RULES = (
    ("adult_brand_01", "socialmediagirls"),
    ("adult_brand_02", "photoacompanhantes"),
    ("adult_brand_03", "animeshentai"),
    ("adult_brand_04", "hentaistube"),
    ("adult_brand_05", "sambaporno"),
    ("adult_brand_06", "fatalmodel"),
    ("adult_brand_07", "cameraprive"),
    ("adult_brand_08", "thehentai"),
    ("adult_brand_09", "xvideos"),
    ("adult_brand_10", "xvideo"),
    ("adult_brand_11", "pornhub"),
    ("adult_brand_12", "xhamster"),
    ("adult_brand_13", "onlyfans"),
    ("adult_brand_14", "spankbang"),
    ("adult_brand_15", "motherless"),
    ("adult_brand_16", "naughtyamerica"),
    ("adult_brand_17", "realitykings"),
    ("adult_brand_18", "teamskeet"),
    ("adult_brand_19", "bangbros"),
    ("adult_brand_20", "brazzers"),
    ("adult_brand_21", "redtube"),
    ("adult_brand_22", "youporn"),
    ("adult_brand_23", "youjizz"),
    ("adult_brand_24", "eporner"),
    ("adult_brand_25", "thisvid"),
    ("adult_brand_26", "shokka"),
    ("adult_brand_27", "xnxx"),
    ("adult_brand_28", "ixxx"),
    ("adult_brand_29", "tube8"),
    ("adult_brand_30", "mofos"),
    ("adult_brand_31", "beeg"),
)

_INHERENTLY_DIRECT_RULES = frozenset(
    rule_id
    for rule_id, _term in _INSULT_RULES
    if rule_id.startswith("directed_")
)

_SHORT_TERM_ALIASES = {
    # v/@ are common glyph substitutions in this specific Portuguese term.
    # Keeping the alias bounded avoids changing every v into u globally.
    "puta": ("pvta",),
}

_REPORTING_CONTEXT_REGEX = re.compile(
    r"^(?:(?:o|a)\s+)?(?:ele|ela|alguem|membro|usuario|user)\s+"
    r"(?:disse|falou|escreveu|mandou|me chamou|denunciou|reportou|"
    r"said|wrote|reported)\b|"
    r"^(?:(?:estou|estamos)\s+)?"
    r"(?:citando|reportando|denunciando|quoting)\b|"
    r"^(?:(?:quero|vim para|gostaria de)\s+)"
    r"(?:citar|reportar|denunciar)\b|"
    r"^(?:citacao|denuncia|relato|quote|quoted)\b|"
    r"^(?:a mensagem|o comentario|a frase)\s+"
    r"(?:dizia|disse|continha)\b"
)

_DIRECTED_MARKER_REGEX = re.compile(
    r"\b(?:voce|vc|tu|te|teu|tua|seu|sua|ele|ela|you|your)\b"
)

_LEGITIMATE_FODA_REGEX = re.compile(
    r"\b(?:analise|matriz|metodologia|planejamento|estrategia)\s+foda\b"
)

_MENTION_REGEX = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9_]{2,}")

_ADULT_DOT_WORD_REGEX = re.compile(
    r"(?i)(?<=[a-z0-9])\s*"
    r"(?:\[\s*(?:\.|dot|ponto)\s*\]|dot|ponto)"
    r"\s*(?=[a-z0-9])"
)


def _normalize_abuse_text(value: str) -> tuple[str, str, str]:
    text = _normalize_security_text(value).casefold()
    # A Telegram @username is not leetspeak. Mask it before interpreting @ as
    # an in-word/end-of-word substitute for "a" (m3rd@, pvt@, c@r@lh0).
    text = _MENTION_REGEX.sub(" mention ", text)
    text = text.translate(_CONFUSABLE_SUBSTITUTIONS)
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(
        char for char in folded if not unicodedata.combining(char)
    )
    folded = re.sub(
        r"(?<=[a-z0-9])@(?=[a-z0-9]|$|[^a-z0-9_])",
        "a",
        folded,
    )
    # Interpret ! and | as "i" only when they occupy a word-character
    # position. Ordinary punctuation such as "atenção!" remains punctuation.
    folded = re.sub(
        r"(?<![a-z0-9_])[!|](?=[a-z0-9])|"
        r"(?<=[a-z0-9])[!|](?=[a-z0-9])",
        "i",
        folded,
    )
    folded = folded.translate(_LEET_SUBSTITUTIONS)
    # Repeated letters are not semantically significant to this lexical
    # policy. Rules pass through the same normalizer, so legitimate doubled
    # letters in English terms remain comparable while "caraaallho" closes.
    folded = re.sub(r"([a-z])\1+", r"\1", folded)
    spaced = re.sub(r"[^a-z0-9@]+", " ", folded)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    compact = re.sub(r"[^a-z0-9]+", "", folded)
    return spaced, compact, folded


def _compact_term_variants(term_compact: str) -> set[str]:
    variants = {term_compact}
    for canonical, aliases in _SHORT_TERM_ALIASES.items():
        if canonical not in term_compact:
            continue
        variants.update(
            term_compact.replace(canonical, alias)
            for alias in aliases
        )
    return variants


def _bounded_obfuscated_term_present(
    structured: str,
    candidate: str,
) -> bool:
    if len(candidate) < 2:
        return False
    obfuscated = r"[^a-z0-9@]*".join(
        re.escape(char) for char in candidate
    )
    return bool(
        re.search(
            rf"(?<![a-z0-9@]){obfuscated}(?![a-z0-9@])",
            structured,
        )
    )


def _abuse_term_present(
    spaced: str,
    compact: str,
    structured: str,
    term: str,
) -> bool:
    term_spaced, term_compact, _term_structured = (
        _normalize_abuse_text(term)
    )
    if not term_compact:
        return False
    variants = _compact_term_variants(term_compact)
    if " " in term_spaced and re.search(
        rf"(?:^| ){re.escape(term_spaced)}(?: |$)",
        spaced,
    ):
        return True
    for variant in variants:
        # Every compact/obfuscated path is bounded in the structured source.
        # This accepts "p.u.t.a" and "filhodaputa", but it cannot find
        # "puta" inside computador, deputado or reputacao.
        if _bounded_obfuscated_term_present(structured, variant):
            return True
    return False


def _abuse_decision(
    *,
    category: str,
    severity: Severity,
    rule_id: str,
    spaced: str,
    directed: bool,
    reporting_context: bool,
    immediate_mute: bool = False,
) -> AbuseDecision:
    return AbuseDecision(
        detected=True,
        category=category,
        severity=severity,
        rule_id=rule_id,
        normalized_hash=hashlib.sha256(
            spaced.encode("utf-8", errors="ignore")
        ).hexdigest()[:24],
        directed=directed,
        reporting_context=reporting_context,
        should_delete=True,
        should_strike=not reporting_context,
        immediate_mute=immediate_mute and not reporting_context,
    )


def _normalize_adult_domain_text(value: str) -> tuple[str, str, str]:
    prepared = _normalize_security_text(value).casefold()
    prepared = _ADULT_DOT_WORD_REGEX.sub(".", prepared)
    return _normalize_abuse_text(prepared)


def detect_abusive_content(
    text: str,
    *,
    directed_hint: bool = False,
) -> AbuseDecision:
    original = text or ""
    spaced, compact, structured = _normalize_abuse_text(original)
    if not spaced and not compact:
        return AbuseDecision()

    # Quotes alone are not evidence of reporting. Otherwise an attacker could
    # wrap a threat or slur in quotes to suppress strikes and immediate mute.
    reporting_context = bool(_REPORTING_CONTEXT_REGEX.search(spaced))
    directed_marker = bool(
        directed_hint
        or _DIRECTED_MARKER_REGEX.search(spaced)
        or re.search(r"(?<!\w)@[A-Za-z0-9_]{2,}", original)
    )

    for rule_id, term in _THREAT_RULES:
        if _abuse_term_present(spaced, compact, structured, term):
            return _abuse_decision(
                category="threat",
                severity=Severity.HIGH,
                rule_id=rule_id,
                spaced=spaced,
                directed=True,
                reporting_context=reporting_context,
                immediate_mute=True,
            )

    for rule_id, term in _SLUR_RULES:
        if _abuse_term_present(spaced, compact, structured, term):
            return _abuse_decision(
                category="slur_or_hate",
                severity=Severity.HIGH,
                rule_id=rule_id,
                spaced=spaced,
                directed=directed_marker,
                reporting_context=reporting_context,
                immediate_mute=True,
            )

    if directed_marker:
        for rule_id, term in _CONTEXTUAL_HATE_RULES:
            if not _abuse_term_present(
                spaced, compact, structured, term
            ):
                continue
            return _abuse_decision(
                category="slur_or_hate",
                severity=Severity.HIGH,
                rule_id=rule_id,
                spaced=spaced,
                directed=True,
                reporting_context=reporting_context,
                immediate_mute=True,
            )

    adult_spaced, adult_compact, adult_structured = (
        _normalize_adult_domain_text(original)
    )
    for rule_id, term in _ADULT_DOMAIN_RULES:
        if _abuse_term_present(
            adult_spaced,
            adult_compact,
            adult_structured,
            term,
        ):
            return _abuse_decision(
                category="adult_site_reference",
                severity=Severity.MEDIUM,
                rule_id=rule_id,
                spaced=spaced,
                directed=False,
                reporting_context=reporting_context,
            )

    for rule_id, term in _ADULT_BRAND_RULES:
        if _abuse_term_present(spaced, compact, structured, term):
            return _abuse_decision(
                category="adult_site_reference",
                severity=Severity.MEDIUM,
                rule_id=rule_id,
                spaced=spaced,
                directed=False,
                reporting_context=reporting_context,
            )

    for rule_id, term in _INSULT_RULES:
        if _abuse_term_present(spaced, compact, structured, term):
            directed = (
                directed_marker
                or rule_id in _INHERENTLY_DIRECT_RULES
            )
            return _abuse_decision(
                category=(
                    "directed_abuse"
                    if directed
                    else "prohibited_language"
                ),
                severity=(
                    Severity.MEDIUM if directed else Severity.LOW
                ),
                rule_id=rule_id,
                spaced=spaced,
                directed=directed,
                reporting_context=reporting_context,
            )

    if directed_marker:
        for rule_id, term in _CONTEXTUAL_INSULT_RULES:
            if not _abuse_term_present(
                spaced, compact, structured, term
            ):
                continue
            return _abuse_decision(
                category="directed_abuse",
                severity=Severity.MEDIUM,
                rule_id=rule_id,
                spaced=spaced,
                directed=True,
                reporting_context=reporting_context,
            )

    for rule_id, term in _EXPLICIT_SEXUAL_RULES:
        if _abuse_term_present(spaced, compact, structured, term):
            return _abuse_decision(
                category="explicit_sexual_language",
                severity=Severity.MEDIUM,
                rule_id=rule_id,
                spaced=spaced,
                directed=directed_marker,
                reporting_context=reporting_context,
            )

    for rule_id, term in _PROFANITY_RULES:
        if (
            term == "foda"
            and _LEGITIMATE_FODA_REGEX.search(spaced)
        ):
            continue
        if _abuse_term_present(spaced, compact, structured, term):
            directed = directed_marker
            return _abuse_decision(
                category=(
                    "directed_abuse"
                    if directed
                    else "prohibited_language"
                ),
                severity=(
                    Severity.MEDIUM if directed else Severity.LOW
                ),
                rule_id=rule_id,
                spaced=spaced,
                directed=directed,
                reporting_context=reporting_context,
            )

    return AbuseDecision()


class Guardian:
    def __init__(self, settings: Settings, db: ZionDB):
        self.settings = settings
        self.db = db

    def containment_remaining(
        self,
        chat_id: int,
        user_id: int,
        now: float | None = None,
    ) -> int:
        ts = time.time() if now is None else now
        until = self.db.containment_until(chat_id, user_id, ts)
        return max(0, int(until - ts))

    def record_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        message_id: int,
        now: float | None = None,
    ) -> FloodDecision:
        with self.db.transaction():
            ts = time.time() if now is None else now
            purge_window = max(
                self.settings.flood_purge_window_seconds,
                self.settings.flood_sustained_window_seconds,
            )
            self.db.prune_recent_messages(ts - purge_window)
            self.db.record_recent_message(
                chat_id,
                user_id,
                message_id,
                ts,
            )

            short_since = ts - self.settings.flood_window_seconds
            sustained_since = (
                ts - self.settings.flood_sustained_window_seconds
            )
            short_count = self.db.count_recent_messages(
                chat_id,
                user_id,
                short_since,
            )
            sustained_count = self.db.count_recent_messages(
                chat_id,
                user_id,
                sustained_since,
            )

            state = self.db.get_operating_state()
            base_threshold = self.settings.flood_max_messages
            short_threshold = base_threshold
            if state == OperatingState.ELEVATED:
                short_threshold = min(
                    base_threshold,
                    max(2, base_threshold - 2),
                )
            elif state == OperatingState.ATTACK:
                short_threshold = min(
                    base_threshold,
                    max(2, base_threshold // 2),
                )

            reason = ""
            trigger_since = short_since
            trigger_count = short_count
            trigger_threshold = short_threshold
            window_seconds = self.settings.flood_window_seconds

            if short_count >= short_threshold:
                reason = "flood"
            elif (
                sustained_count
                >= self.settings.flood_sustained_max_messages
            ):
                reason = "sustained_flood"
                trigger_since = sustained_since
                trigger_count = sustained_count
                trigger_threshold = (
                    self.settings.flood_sustained_max_messages
                )
                window_seconds = (
                    self.settings.flood_sustained_window_seconds
                )

            if not reason:
                return FloodDecision()

            message_ids = self.db.recent_message_ids(
                chat_id,
                user_id,
                trigger_since,
            )
            # Keep older legitimate activity intact. Only the triggering
            # short/sustained window is cleared.
            self.db.clear_recent_messages_since(
                chat_id,
                user_id,
                trigger_since,
            )

            self.db.add_strike(
                chat_id=chat_id,
                user_id=user_id,
                reason=reason,
                severity=Severity.MEDIUM,
                source="guardian",
                ttl_seconds=self.settings.flood_strike_reset_seconds,
                metadata={
                    "messages_in_window": trigger_count,
                    "threshold": trigger_threshold,
                    "window_seconds": window_seconds,
                    "short_messages": short_count,
                    "sustained_messages": sustained_count,
                    "operating_state": state.value,
                },
                now=ts,
            )
            strike_count = self.db.count_active_strikes(
                chat_id,
                user_id,
                ts,
                reasons=(
                    "flood",
                    "sustained_flood",
                    "legacy_flood",
                ),
            )
            level_index = min(
                max(0, strike_count - 1),
                len(self.settings.flood_mute_levels) - 1,
            )
            mute_seconds = self.settings.flood_mute_levels[level_index]
            should_ban = (
                self.settings.flood_ban_after_strikes > 0
                and strike_count >= self.settings.flood_ban_after_strikes
            )

            self.db.set_containment(
                chat_id,
                user_id,
                ts + mute_seconds,
                (
                    f"{reason}_pending_ban"
                    if should_ban
                    else reason
                ),
                ts,
            )
            incident_id = self.db.create_incident(
                chat_id=chat_id,
                user_id=user_id,
                category=reason,
                severity=Severity.HIGH if should_ban else Severity.MEDIUM,
                source="guardian",
                evidence={
                    "strike_count": strike_count,
                    "tracked_messages": len(message_ids),
                    "messages_in_window": trigger_count,
                    "threshold": trigger_threshold,
                    "window_seconds": window_seconds,
                    "planned_action": "ban" if should_ban else "mute",
                    "enforcement_pending": True,
                },
                now=ts,
            )
            return FloodDecision(
                triggered=True,
                strike_count=strike_count,
                mute_seconds=mute_seconds,
                should_ban=should_ban,
                message_ids=message_ids,
                incident_id=incident_id,
                reason=reason,
                window_seconds=window_seconds,
            )

    def evaluate_abuse(
        self,
        text: str,
        *,
        directed_hint: bool = False,
    ) -> AbuseDecision:
        return detect_abusive_content(text, directed_hint=directed_hint)

    def evaluate_chat_burst(
        self,
        chat_id: int,
        user_id: int | None = None,
        now: float | None = None,
    ) -> ChatBurstDecision:
        with self.db.transaction():
            ts = time.time() if now is None else now
            since = ts - self.settings.chat_burst_window_seconds
            messages, users = self.db.chat_recent_activity(
                chat_id,
                since,
            )

            # Callers evaluate immediately before recording the current message.
            # Project it into the window without writing twice.
            if user_id is not None:
                messages += 1
                if self.db.count_recent_messages(
                    chat_id,
                    user_id,
                    since,
                ) == 0:
                    users += 1

            decision = ChatBurstDecision(
                message_count=messages,
                unique_users=users,
                window_seconds=self.settings.chat_burst_window_seconds,
                elevated_seconds=self.settings.chat_burst_elevated_seconds,
            )

            if self.db.get_operating_state() != OperatingState.NORMAL:
                return decision

            if (
                messages < self.settings.chat_burst_max_messages
                or users < self.settings.chat_burst_min_users
            ):
                return decision

            expires_at = ts + self.settings.chat_burst_elevated_seconds
            self.db.set_operating_state(OperatingState.ELEVATED)
            self.db.set_setting(
                "operating_state_expires_at",
                str(expires_at),
            )
            incident_id = self.db.create_incident(
                chat_id=chat_id,
                user_id=None,
                category="distributed_chat_burst",
                severity=Severity.MEDIUM,
                source="guardian",
                evidence={
                    "messages": messages,
                    "unique_users": users,
                    "window_seconds": self.settings.chat_burst_window_seconds,
                    "temporary_state": OperatingState.ELEVATED.value,
                    "expires_at": expires_at,
                },
                note=(
                    "Distributed burst only changes temporary operating state; "
                    "it does not punish individual users."
                ),
                now=ts,
            )
            self.db.record_action(
                incident_id=incident_id,
                chat_id=chat_id,
                user_id=None,
                action_type="state_change",
                actor_type="guardian",
                actor_id=None,
                reason="distributed_chat_burst",
                success=True,
                metadata={
                    "state": OperatingState.ELEVATED.value,
                    "expires_at": expires_at,
                },
                now=ts,
            )
            decision.triggered = True
            return decision

    def evaluate_links(
        self,
        text: str,
        extra_domains: list[str] | tuple[str, ...] | None = None,
        extra_urls: list[str] | tuple[str, ...] | None = None,
        unsupported_schemes: list[str] | tuple[str, ...] | None = None,
    ) -> LinkDecision:
        domains = extract_domains(text)
        unsupported = {
            str(scheme).strip().lower()
            for scheme in (
                list(extract_unsupported_schemes(text))
                + list(unsupported_schemes or ())
            )
            if str(scheme).strip()
        }

        for raw_url in extra_urls or ():
            domain, error = normalize_link_target(raw_url)
            if domain and domain not in domains:
                domains.append(domain)
            if error:
                unsupported.add(error)

        for raw_domain in extra_domains or ():
            normalized = normalize_policy_domain(raw_domain)
            if normalized and normalized not in domains:
                domains.append(normalized)

        unsupported_list = sorted(unsupported)
        if not domains and not unsupported_list:
            return LinkDecision()

        unauthorized: list[str] = []
        for domain in domains:
            labels = domain.split(".")
            candidates = [
                ".".join(labels[index:])
                for index in range(max(1, len(labels) - 1))
            ]
            disposition = None
            for candidate in candidates:
                disposition = self.db.domain_disposition(candidate)
                if disposition is not None:
                    break

            if disposition == "allow":
                continue
            if disposition == "block":
                unauthorized.append(domain)
                continue
            allowed_by_env = any(
                domain_matches(domain, allowed)
                for allowed in self.settings.allowed_domains
            )
            if not self.settings.allow_links or not allowed_by_env:
                unauthorized.append(domain)

        if unauthorized or unsupported_list:
            return LinkDecision(
                has_links=True,
                domains=domains,
                unauthorized_domains=unauthorized,
                unsupported_schemes=unsupported_list,
                should_delete=True,
                reason=(
                    "link/esquema não autorizado"
                    if unsupported_list
                    else "link/domínio não autorizado"
                ),
            )
        return LinkDecision(
            has_links=True,
            domains=domains,
        )

    def sensitive_content(
        self,
        text: str,
    ) -> SensitiveContentDecision:
        return detect_sensitive_content(text)
