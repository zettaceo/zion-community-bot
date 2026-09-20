from __future__ import annotations

import re
import time
import unicodedata
from urllib.parse import urlparse

from .config import Settings
from .db import ZionDB
from .models import (
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
    r"\b[1-9A-HJ-NP-Za-km-z]{64,100}\b"
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
    0x200B,  # zero width space
    0x200C,  # zero width non-joiner
    0x200D,  # zero width joiner
    0x2060,  # word joiner
    0xFEFF,  # zero width no-break space / BOM
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
        return None, None

    scheme = (parsed.scheme or "").lower()
    if scheme and scheme not in ALLOWED_LINK_SCHEMES:
        return None, scheme

    if not scheme:
        raw = "https://" + raw

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
        host = host.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return None
    return host or None


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
        if (
            _contains_invisible_security_char(raw)
            and "invisible-link-character" not in schemes
        ):
            schemes.append("invisible-link-character")

    for match in UNSUPPORTED_VISIBLE_SCHEME_REGEX.finditer(
        normalized_text
    ):
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

    plausible_seed_prefix = (
        len(words) >= 12
        and all(
            word.replace("'", "").replace("-", "").isalpha()
            and 1 <= len(word) <= 32
            for word in words[:12]
        )
    )

    if plausible_seed_prefix:
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
                "possível chave privada base58 identificada "
                "junto a um rótulo sensível"
            ),
        )

    byte_values = [
        int(value)
        for value in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", tail)
    ]
    if (
        len(byte_values) in {32, 64}
        and all(0 <= value <= 255 for value in byte_values)
        and "[" in tail
        and "]" in tail
    ):
        return SensitiveContentDecision(
            detected=True,
            kind="possible_private_key",
            reason=(
                "possível chave privada em vetor de bytes identificada "
                "junto a um rótulo sensível"
            ),
        )

    return SensitiveContentDecision()


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
            self.db.prune_recent_messages(
                ts - self.settings.flood_purge_window_seconds
            )
            self.db.record_recent_message(
                chat_id,
                user_id,
                message_id,
                ts,
            )

            count = self.db.count_recent_messages(
                chat_id,
                user_id,
                ts - self.settings.flood_window_seconds,
            )

            state = self.db.get_operating_state()
            threshold = self.settings.flood_max_messages
            if state == OperatingState.ELEVATED:
                threshold = max(2, threshold - 2)
            elif state == OperatingState.ATTACK:
                threshold = max(2, threshold // 2)

            if count < threshold:
                return FloodDecision()

            message_ids = self.db.recent_message_ids(
                chat_id,
                user_id,
                ts - self.settings.flood_window_seconds,
            )
            self.db.clear_recent_messages(chat_id, user_id)

            self.db.add_strike(
                chat_id=chat_id,
                user_id=user_id,
                reason="flood",
                severity=Severity.MEDIUM,
                source="guardian",
                ttl_seconds=self.settings.flood_strike_reset_seconds,
                metadata={
                    "messages_in_window": count,
                    "threshold": threshold,
                    "operating_state": state.value,
                },
                now=ts,
            )

            strike_count = self.db.count_active_strikes(
                chat_id,
                user_id,
                ts,
                reasons=("flood", "legacy_flood"),
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

            if not should_ban:
                self.db.set_containment(
                    chat_id,
                    user_id,
                    ts + mute_seconds,
                    "flood",
                    ts,
                )

            return FloodDecision(
                triggered=True,
                strike_count=strike_count,
                mute_seconds=mute_seconds,
                should_ban=should_ban,
                message_ids=message_ids,
            )

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
        unsupported_schemes: list[str] | tuple[str, ...] | None = None,
    ) -> LinkDecision:
        domains = extract_domains(text)
        unsupported = sorted(
            {
                str(scheme).strip().lower()
                for scheme in (
                    list(extract_unsupported_schemes(text))
                    + list(unsupported_schemes or ())
                )
                if str(scheme).strip()
            }
        )

        for raw_domain in extra_domains or ():
            normalized = normalize_policy_domain(raw_domain)
            if normalized and normalized not in domains:
                domains.append(normalized)

        if not domains and not unsupported:
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

        if unauthorized or unsupported:
            return LinkDecision(
                has_links=True,
                domains=domains,
                unauthorized_domains=unauthorized,
                unsupported_schemes=unsupported,
                should_delete=True,
                reason=(
                    "link/esquema não autorizado"
                    if unsupported
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
