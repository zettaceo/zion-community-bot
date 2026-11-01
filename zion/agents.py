from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping


class AgentId(str, Enum):
    ZION = "zion"
    MIMIR = "mimir"
    EIR = "eir"
    FREYR = "freyr"


class AgentRole(str, Enum):
    COMMUNITY = "community"
    TECHNICAL = "technical"
    SUPPORT = "support"
    BUSINESS = "business"


class DMPolicy(str, Enum):
    CREATOR_ONLY = "creator_only"
    CLOSED = "closed"
    PUBLIC = "public"


class ModerationAuthority(str, Enum):
    FULL_DETERMINISTIC = "full_deterministic"
    NONE = "none"


class KnowledgeScope(str, Enum):
    COMMUNITY_PUBLIC = "community_public"
    TECHNICAL_PUBLIC = "technical_public"
    TECHNICAL_CONTROLLED = "technical_controlled"
    SUPPORT_PUBLIC = "support_public"
    BUSINESS_PUBLIC = "business_public"
    BUSINESS_CONTROLLED = "business_controlled"


class ConversationIntent(str, Enum):
    MODERATION = "moderation"
    COMMUNITY = "community"
    TECHNICAL = "technical"
    SUPPORT = "support"
    PARTNERSHIP = "partnership"
    PRODUCT = "product"
    PLAN = "plan"
    ROADMAP = "roadmap"
    SECURITY = "security"
    COMPETITIVE_OBJECTION = "competitive_objection"
    API_INTEGRATION = "api_integration"
    UNRELATED = "unrelated"
    AMBIGUOUS = "ambiguous"


    @property
    def delivery_family(self) -> str:
        """Stable schema-4 delivery category; fine intent stays in route reason.

        This projection grants no authority: registry validation occurs first.
        It avoids migrating delivery/quarantine records for cognitive labels.
        """
        if self is ConversationIntent.API_INTEGRATION:
            return 'technical'
        if self in {ConversationIntent.PRODUCT, ConversationIntent.PLAN,
                    ConversationIntent.ROADMAP, ConversationIntent.SECURITY,
                    ConversationIntent.COMPETITIVE_OBJECTION}:
            return 'community'
        return self.value


@dataclass(frozen=True, slots=True)
class AgentProfile:
    agent_id: AgentId
    display_name: str
    title: str
    role: AgentRole
    dm_policy: DMPolicy
    moderation_authority: ModerationAuthority
    knowledge_scopes: frozenset[KnowledgeScope]
    group_intents: frozenset[ConversationIntent]
    telegram_username: str | None = None
    can_speak_group: bool = True

    @property
    def can_moderate(self) -> bool:
        return (
            self.moderation_authority
            is ModerationAuthority.FULL_DETERMINISTIC
        )


_AGENT_KEY_REGEX = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_TELEGRAM_USERNAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


class AgentRegistry:
    """Immutable authority registry for official Z-SWAP agents."""

    def __init__(self, profiles: Iterable[AgentProfile]) -> None:
        by_id: dict[AgentId, AgentProfile] = {}
        by_username: dict[str, AgentProfile] = {}
        by_intent: dict[ConversationIntent, AgentProfile] = {}

        for profile in profiles:
            key = profile.agent_id.value
            if not _AGENT_KEY_REGEX.fullmatch(key):
                raise ValueError(f"invalid agent id: {key!r}")
            if profile.agent_id in by_id:
                raise ValueError(f"duplicate agent id: {key}")
            if not profile.display_name.strip() or not profile.title.strip():
                raise ValueError(f"agent identity is incomplete: {key}")
            if not profile.knowledge_scopes:
                raise ValueError(f"agent has no knowledge scope: {key}")

            username = profile.telegram_username
            if username is not None:
                normalized_username = username.removeprefix("@").lower()
                if not _TELEGRAM_USERNAME_REGEX.fullmatch(
                    username.removeprefix("@")
                ):
                    raise ValueError(
                        f"invalid Telegram username for {key}"
                    )
                if normalized_username in by_username:
                    raise ValueError(
                        f"duplicate Telegram username: {username}"
                    )
                by_username[normalized_username] = profile

            if profile.can_moderate and profile.agent_id is not AgentId.ZION:
                raise ValueError(
                    "only ZION may have deterministic moderation authority"
                )
            if (
                ConversationIntent.MODERATION in profile.group_intents
                and not profile.can_moderate
            ):
                raise ValueError(
                    "moderation intent requires deterministic authority"
                )

            for intent in profile.group_intents:
                if intent in {
                    ConversationIntent.UNRELATED,
                    ConversationIntent.AMBIGUOUS,
                }:
                    raise ValueError(
                        f"silence intent cannot have a speaker: {intent.value}"
                    )
                if intent in by_intent:
                    owner = by_intent[intent].agent_id.value
                    raise ValueError(
                        f"intent {intent.value} has multiple speakers: "
                        f"{owner}, {key}"
                    )
                by_intent[intent] = profile

            by_id[profile.agent_id] = profile

        expected = frozenset(AgentId)
        actual = frozenset(by_id)
        if actual != expected:
            missing = sorted(agent.value for agent in expected - actual)
            extra = sorted(agent.value for agent in actual - expected)
            raise ValueError(
                f"registry must define every official agent; "
                f"missing={missing}, extra={extra}"
            )
        if not by_id[AgentId.ZION].can_moderate:
            raise ValueError("ZION must retain deterministic Guardian authority")

        self._by_id: Mapping[AgentId, AgentProfile] = MappingProxyType(by_id)
        self._by_username: Mapping[str, AgentProfile] = MappingProxyType(
            by_username
        )
        self._by_intent: Mapping[ConversationIntent, AgentProfile] = (
            MappingProxyType(by_intent)
        )

    def __iter__(self) -> Iterator[AgentProfile]:
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, agent_id: AgentId | str) -> AgentProfile:
        try:
            normalized = (
                agent_id
                if isinstance(agent_id, AgentId)
                else AgentId(str(agent_id).strip().lower())
            )
            return self._by_id[normalized]
        except (KeyError, ValueError) as exc:
            raise KeyError(f"unknown agent identity: {agent_id!r}") from exc

    def by_username(self, username: str) -> AgentProfile | None:
        normalized = (username or "").strip().removeprefix("@").lower()
        return self._by_username.get(normalized)

    def speaker_for(
        self,
        intent: ConversationIntent,
    ) -> AgentProfile | None:
        return self._by_intent.get(intent)


DEFAULT_AGENT_REGISTRY = AgentRegistry(
    (
        AgentProfile(
            agent_id=AgentId.ZION,
            display_name="ZION - Chief Community Officer",
            title="CCO - Chief Community Officer",
            role=AgentRole.COMMUNITY,
            dm_policy=DMPolicy.CREATOR_ONLY,
            moderation_authority=ModerationAuthority.FULL_DETERMINISTIC,
            knowledge_scopes=frozenset(
                {KnowledgeScope.COMMUNITY_PUBLIC}
            ),
            group_intents=frozenset(
                {
                    ConversationIntent.MODERATION,
                    ConversationIntent.COMMUNITY,
                    ConversationIntent.PRODUCT,
                    ConversationIntent.PLAN,
                    ConversationIntent.ROADMAP,
                    ConversationIntent.SECURITY,
                    ConversationIntent.COMPETITIVE_OBJECTION,
                }
            ),
        ),
        AgentProfile(
            agent_id=AgentId.MIMIR,
            display_name="MIMIR - Chief Technology Officer",
            title="CTO - Chief Technology Officer",
            role=AgentRole.TECHNICAL,
            dm_policy=DMPolicy.CLOSED,
            moderation_authority=ModerationAuthority.NONE,
            knowledge_scopes=frozenset(
                {
                    KnowledgeScope.TECHNICAL_PUBLIC,
                    KnowledgeScope.TECHNICAL_CONTROLLED,
                }
            ),
            group_intents=frozenset({ConversationIntent.TECHNICAL, ConversationIntent.API_INTEGRATION}),
            telegram_username="ZSwap_MimirBot",
        ),
        AgentProfile(
            agent_id=AgentId.EIR,
            display_name="EIR - Chief Experience Officer",
            title="CXO - Chief Experience Officer",
            role=AgentRole.SUPPORT,
            dm_policy=DMPolicy.PUBLIC,
            moderation_authority=ModerationAuthority.NONE,
            knowledge_scopes=frozenset(
                {KnowledgeScope.SUPPORT_PUBLIC}
            ),
            group_intents=frozenset({ConversationIntent.SUPPORT}),
            telegram_username="ZSwap_EirBot",
        ),
        AgentProfile(
            agent_id=AgentId.FREYR,
            display_name="FREYR - Chief Business Officer",
            title="CBO - Chief Business Officer",
            role=AgentRole.BUSINESS,
            dm_policy=DMPolicy.PUBLIC,
            moderation_authority=ModerationAuthority.NONE,
            knowledge_scopes=frozenset(
                {
                    KnowledgeScope.BUSINESS_PUBLIC,
                    KnowledgeScope.BUSINESS_CONTROLLED,
                }
            ),
            group_intents=frozenset({ConversationIntent.PARTNERSHIP}),
            telegram_username="ZSwap_FreyrBot",
        ),
    )
)
