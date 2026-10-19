from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from .agents import AgentProfile, ConversationIntent
from .db import ZionDB


class SpeakerClaimStatus(str, Enum):
    CLAIMED = "claimed"
    SENT = "sent"
    FAILED_SAFE = "failed_safe"
    UNCERTAIN = "uncertain"


class UpdateKind(str, Enum):
    MESSAGE = "message"
    EDITED_MESSAGE = "edited_message"
    CALLBACK_QUERY = "callback_query"


@dataclass(frozen=True, slots=True)
class InboundMessageIdentity:
    source_identity: str
    chat_id: int
    message_id: int | None
    update_id: int | None
    update_kind: UpdateKind

    def claim_key(self) -> str:
        source = self.source_identity.strip().lower()
        if self.update_kind in {
            UpdateKind.MESSAGE,
            UpdateKind.EDITED_MESSAGE,
        }:
            if self.message_id is None:
                raise ValueError("message update requires message_id")
            # An edit shares the original claim and cannot create a second
            # speaker after the original message was processed.
            material = f"message:{source}:{self.chat_id}:{self.message_id}"
        else:
            if self.update_id is None:
                raise ValueError("callback update requires update_id")
            material = f"callback:{source}:{self.chat_id}:{self.update_id}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SpeakerClaim:
    claim_key: str
    speaker: AgentProfile
    intent: ConversationIntent
    attempt_count: int


class SpeakerArbiter:
    """Durable zero-or-one speaker authorization."""

    def __init__(self, db: ZionDB) -> None:
        self.db = db

    def claim(
        self,
        inbound: InboundMessageIdentity,
        *,
        speaker: AgentProfile,
        intent: ConversationIntent,
        allow_failed_safe_retry: bool = False,
        now: float | None = None,
    ) -> SpeakerClaim | None:
        if not speaker.can_speak_group:
            return None
        if intent not in speaker.group_intents:
            return None

        claim_key = inbound.claim_key()
        acquired = self.db.claim_speaker_message(
            claim_key=claim_key,
            source_identity=inbound.source_identity,
            chat_id=inbound.chat_id,
            message_id=inbound.message_id,
            update_id=inbound.update_id,
            update_kind=inbound.update_kind.value,
            selected_agent=speaker.agent_id.value,
            intent=intent.delivery_family,
            allow_failed_safe_retry=allow_failed_safe_retry,
            now=now,
        )
        if not acquired:
            return None
        row = self.db.get_speaker_claim(claim_key)
        if row is None:
            raise RuntimeError("speaker claim disappeared after acquisition")
        return SpeakerClaim(
            claim_key=claim_key,
            speaker=speaker,
            intent=intent,
            attempt_count=int(row["attempt_count"]),
        )

    def sent(
        self,
        claim: SpeakerClaim,
        *,
        telegram_message_id: int,
        now: float | None = None,
    ) -> bool:
        return self.db.complete_speaker_claim(
            claim.claim_key,
            status=SpeakerClaimStatus.SENT.value,
            telegram_message_id=telegram_message_id,
            now=now,
        )

    def failed_safe(
        self,
        claim: SpeakerClaim,
        *,
        error_type: str,
        now: float | None = None,
    ) -> bool:
        return self.db.complete_speaker_claim(
            claim.claim_key,
            status=SpeakerClaimStatus.FAILED_SAFE.value,
            error_type=error_type,
            now=now,
        )

    def uncertain(
        self,
        claim: SpeakerClaim,
        *,
        error_type: str,
        now: float | None = None,
    ) -> bool:
        return self.db.complete_speaker_claim(
            claim.claim_key,
            status=SpeakerClaimStatus.UNCERTAIN.value,
            error_type=error_type,
            now=now,
        )

