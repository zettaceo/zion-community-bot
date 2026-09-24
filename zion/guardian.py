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

_PROFANITY_RULES = {
    "profanity_pt_01": "porra",
    "profanity_pt_02": "caralho",
    "profanity_pt_03": "merda",
    "profanity_pt_04": "foder",
    "profanity_en_01": "fuck",
    "profanity_en_02": "shit",
}

_INSULT_RULES = {
    "insult_pt_01": "idiota",
    "insult_pt_02": "imbecil",
    "insult_pt_03": "otario",
    "insult_pt_04": "burro",
    "insult_pt_05": "babaca",
    "insult_pt_06": "fdp",
    "insult_pt_07": "filho da puta",
    "insult_pt_08": "vai se foder",
    "insult_pt_09": "vai tomar no cu",
    "insult_en_01": "fuck you",
    "insult_en_02": "moron",
    "insult_en_03": "stupid",
}

_SLUR_RULES = {
    "slur_01": "nigger",
    "slur_02": "faggot",
    "slur_03": "traveco",
}

_THREAT_RULES = {
    "threat_pt_01": "vou te matar",
    "threat_pt_02": "eu vou te matar",
    "threat_pt_03": "te mato",
    "threat_pt_04": "matar voce",
    "threat_en_01": "kill you",
    "threat_en_02": "i will kill you",
}

_INHERENTLY_DIRECT_RULES = frozenset({
    "insult_pt_07",
    "insult_pt_08",
    "insult_pt_09",
    "insult_en_01",
})

_REPORTING_CONTEXT_REGEX = re.compile(
    r"\b(?:ele|ela|alguem|membro|usuario|user)\s+"
    r"(?:disse|falou|escreveu|mandou|me chamou)\b|"
    r"\b(?:citando|reportando|denunciando|quote|quoted)\b"
)

_DIRECTED_MARKER_REGEX = re.compile(
    r"\b(?:voce|vc|tu|te|teu|tua|seu|sua|ele|ela)\b"
)


def _normalize_abuse_text(value: str) -> tuple[str, str]:
    text = _normalize_security_text(value).casefold().translate(
        _LEET_SUBSTITUTIONS
    )
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(
        char for char in folded if not unicodedata.combining(char)
    )
    # "caaaaraaalho" and similar bypass attempts collapse to a stable form.
    folded = re.sub(r"([a-z])\1{2,}", r"\1", folded)
    spaced = re.sub(r"[^a-z0-9@]+", " ", folded)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    compact = re.sub(r"[^a-z0-9]+", "", folded)
    return spaced, compact


def _abuse_term_present(
    spaced: str,
    compact: str,
    term: str,
) -> bool:
    term_spaced, term_compact = _normalize_abuse_text(term)
    if not term_compact:
        return False
    if " " in term_spaced:
        return (
            term_spaced in spaced
            or term_compact in compact
        )
    tokens = set(spaced.split())
    if term_spaced in tokens:
        return True
    # Compact matching catches bounded separator/leet obfuscation such as
    # "i.d.i.o.t.a". Short terms are excluded to avoid incidental substrings.
    return len(term_compact) >= 5 and term_compact in compact


def detect_abusive_content(text: str) -> AbuseDecision:
    original = text or ""
    spaced, compact = _normalize_abuse_text(original)
    if not spaced and not compact:
        return AbuseDecision()

    reporting_context = bool(
        _REPORTING_CONTEXT_REGEX.search(spaced)
        or any(mark in original for mark in ('"', "“", "”"))
    )
    directed_marker = bool(
        _DIRECTED_MARKER_REGEX.search(spaced)
        or re.search(r"(?<!\w)@[A-Za-z0-9_]{2,}", original)
    )

    for rule_id, term in _THREAT_RULES.items():
        if _abuse_term_present(spaced, compact, term):
            return AbuseDecision(
                detected=True,
                category="threat_or_slur",
                severity=Severity.HIGH,
                rule_id=rule_id,
                normalized_hash=hashlib.sha256(
                    spaced.encode("utf-8", errors="ignore")
                ).hexdigest()[:24],
                directed=True,
                reporting_context=reporting_context,
                should_delete=True,
                should_strike=not reporting_context,
                immediate_mute=not reporting_context,
            )

    for rule_id, term in _SLUR_RULES.items():
        if _abuse_term_present(spaced, compact, term):
            return AbuseDecision(
                detected=True,
                category="threat_or_slur",
                severity=Severity.HIGH,
                rule_id=rule_id,
                normalized_hash=hashlib.sha256(
                    spaced.encode("utf-8", errors="ignore")
                ).hexdigest()[:24],
                directed=directed_marker,
                reporting_context=reporting_context,
                should_delete=True,
                should_strike=not reporting_context,
                immediate_mute=not reporting_context,
            )

    for rule_id, term in _INSULT_RULES.items():
        if _abuse_term_present(spaced, compact, term):
            directed = (
                directed_marker
                or rule_id in _INHERENTLY_DIRECT_RULES
            )
            return AbuseDecision(
                detected=True,
                category=(
                    "directed_abuse"
                    if directed
                    else "prohibited_language"
                ),
                severity=(
                    Severity.MEDIUM if directed else Severity.LOW
                ),
                rule_id=rule_id,
                normalized_hash=hashlib.sha256(
                    spaced.encode("utf-8", errors="ignore")
                ).hexdigest()[:24],
                directed=directed,
                reporting_context=reporting_context,
                should_delete=True,
                should_strike=not reporting_context,
                immediate_mute=False,
            )

    for rule_id, term in _PROFANITY_RULES.items():
        if _abuse_term_present(spaced, compact, term):
            directed = directed_marker
            return AbuseDecision(
                detected=True,
                category=(
                    "directed_abuse"
                    if directed
                    else "prohibited_language"
                ),
                severity=(
                    Severity.MEDIUM if directed else Severity.LOW
                ),
                rule_id=rule_id,
                normalized_hash=hashlib.sha256(
                    spaced.encode("utf-8", errors="ignore")
                ).hexdigest()[:24],
                directed=directed,
                reporting_context=reporting_context,
                should_delete=True,
                should_strike=not reporting_context,
                immediate_mute=False,
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

    def evaluate_abuse(self, text: str) -> AbuseDecision:
        return detect_abusive_content(text)

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
