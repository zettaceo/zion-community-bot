from __future__ import annotations

import re
import time

import idna
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
    r"(?i)\b("
    r"private\s+key|chave\s+privada|"
    r"seed\s+phrase|frase\s+semente|"
    r"recovery\s+phrase|frase\s+de\s+recupera[cç][aã]o|"
    r"mnemonic"
    r")\b\s*[:=\-]?\s*(.{24,})"
)


def _normalize_domain(raw_url: str) -> str | None:
    candidate = (raw_url or "").strip().rstrip(".,);]}>")
    candidate = candidate.translate({
        0x3002: ".",
        0xFF0E: ".",
        0xFF61: ".",
    })
    candidate = candidate.replace("\u200b", "").replace("\u2060", "")
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
        host = idna.encode(
            host,
            uts46=True,
            transitional=False,
        ).decode("ascii").lower()
    except (idna.IDNAError, UnicodeError, ValueError):
        return None
    return host or None


def normalize_policy_domain(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    candidate = raw
    if not re.match(r"(?i)^(?:https?://|www\.|t\.me/)", candidate):
        candidate = "https://" + candidate

    domain = _normalize_domain(candidate)
    if not domain or not POLICY_DOMAIN_REGEX.fullmatch(domain):
        return None
    return domain


def _extract_domains_and_invalid(text: str) -> tuple[list[str], bool]:
    domains: list[str] = []
    invalid = False
    for raw in URL_REGEX.findall(text or ""):
        domain = _normalize_domain(raw)
        if not domain:
            invalid = True
            continue
        if domain not in domains:
            domains.append(domain)
    return domains, invalid


def extract_domains(text: str) -> list[str]:
    domains, _ = _extract_domains_and_invalid(text)
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
            base_threshold = self.settings.flood_max_messages
            threshold = base_threshold
            if state == OperatingState.ELEVATED:
                threshold = min(
                    base_threshold,
                    max(3, base_threshold - 2),
                )
            elif state == OperatingState.ATTACK:
                threshold = min(
                    base_threshold,
                    max(2, base_threshold // 2),
                )

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

            # Keep a persistent local containment even when the next external
            # action is a ban. If the process dies after this transaction but
            # before Telegram confirms the ban, later messages remain blocked.
            self.db.set_containment(
                chat_id,
                user_id,
                ts + mute_seconds,
                "flood_pending_ban" if should_ban else "flood",
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
        extra_urls: list[str] | tuple[str, ...] | None = None,
    ) -> LinkDecision:
        domains, invalid_link = _extract_domains_and_invalid(text)

        for raw_url in extra_urls or ():
            normalized = normalize_policy_domain(raw_url)
            if normalized:
                if normalized not in domains:
                    domains.append(normalized)
            else:
                # A clickable URL that cannot be mapped into the domain policy
                # is not silently ignored. Unknown/unsupported schemes fail
                # closed without persisting the raw target.
                invalid_link = True

        for raw_domain in extra_domains or ():
            normalized = normalize_policy_domain(raw_domain)
            if normalized and normalized not in domains:
                domains.append(normalized)

        if not domains and not invalid_link:
            return LinkDecision()

        unauthorized: list[str] = []
        if invalid_link:
            unauthorized.append("<invalid-or-unsupported-url>")

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
