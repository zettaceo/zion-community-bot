from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from .config import Settings
from .db import ZionDB
from .models import (
    FloodDecision,
    LinkDecision,
    OperatingState,
    SensitiveContentDecision,
    Severity,
)


URL_REGEX = re.compile(
    r"(?i)\b(?:https?://|www\.|t\.me/)[^\s<>]+"
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
    r"(?i)\b("
    r"private\s+key|chave\s+privada|"
    r"seed\s+phrase|frase\s+semente|"
    r"recovery\s+phrase|frase\s+de\s+recupera[cç][aã]o|"
    r"mnemonic"
    r")\b\s*[:=\-]?\s*(.{24,})"
)


def _normalize_domain(raw_url: str) -> str | None:
    candidate = raw_url.strip().rstrip(".,);]}>")
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
    return host or None


def extract_domains(text: str) -> list[str]:
    domains: list[str] = []
    for raw in URL_REGEX.findall(text or ""):
        domain = _normalize_domain(raw)
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def domain_matches(domain: str, allowed: str) -> bool:
    domain = domain.lower().strip(".")
    allowed = allowed.lower().strip(".")
    return domain == allowed or domain.endswith("." + allowed)


def detect_sensitive_content(text: str) -> SensitiveContentDecision:
    text = text or ""
    if not SENSITIVE_LABEL_REGEX.search(text):
        return SensitiveContentDecision()

    match = LONG_SECRET_AFTER_LABEL_REGEX.search(text)
    if not match:
        return SensitiveContentDecision()

    tail = match.group(2).strip()
    words = re.findall(r"[A-Za-zÀ-ÿ0-9_'-]+", tail)

    if len(words) in {12, 15, 18, 21, 24}:
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
        ts = now or time.time()
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
        ts = now or time.time()
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
            threshold = max(3, threshold - 2)
        elif state == OperatingState.ATTACK:
            threshold = max(2, threshold // 2)

        if count < threshold:
            return FloodDecision()

        message_ids = self.db.recent_message_ids(
            chat_id,
            user_id,
            ts - self.settings.flood_purge_window_seconds,
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

    def evaluate_links(self, text: str) -> LinkDecision:
        domains = extract_domains(text)
        if not domains:
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

        if unauthorized:
            return LinkDecision(
                has_links=True,
                domains=domains,
                unauthorized_domains=unauthorized,
                should_delete=True,
                reason="link/domínio não autorizado",
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
