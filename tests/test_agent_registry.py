from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace

from zion.agents import (
    DEFAULT_AGENT_REGISTRY,
    AgentId,
    AgentProfile,
    AgentRegistry,
    AgentRole,
    ConversationIntent,
    DMPolicy,
    KnowledgeScope,
    ModerationAuthority,
)


class AgentRegistryTests(unittest.TestCase):
    def test_registry_contains_exact_official_identities(self) -> None:
        self.assertEqual(
            {profile.agent_id for profile in DEFAULT_AGENT_REGISTRY},
            set(AgentId),
        )
        self.assertEqual(len(DEFAULT_AGENT_REGISTRY), 4)

    def test_authority_and_dm_contract(self) -> None:
        zion = DEFAULT_AGENT_REGISTRY.get(AgentId.ZION)
        mimir = DEFAULT_AGENT_REGISTRY.get(AgentId.MIMIR)
        eir = DEFAULT_AGENT_REGISTRY.get(AgentId.EIR)
        freyr = DEFAULT_AGENT_REGISTRY.get(AgentId.FREYR)

        self.assertEqual(zion.dm_policy, DMPolicy.CREATOR_ONLY)
        self.assertTrue(zion.can_moderate)
        self.assertEqual(mimir.dm_policy, DMPolicy.CLOSED)
        self.assertEqual(eir.dm_policy, DMPolicy.PUBLIC)
        self.assertEqual(freyr.dm_policy, DMPolicy.PUBLIC)
        self.assertFalse(mimir.can_moderate)
        self.assertFalse(eir.can_moderate)
        self.assertFalse(freyr.can_moderate)

    def test_every_speaking_intent_has_exactly_one_owner(self) -> None:
        expected = {
            ConversationIntent.MODERATION: AgentId.ZION,
            ConversationIntent.COMMUNITY: AgentId.ZION,
            ConversationIntent.TECHNICAL: AgentId.MIMIR,
            ConversationIntent.SUPPORT: AgentId.EIR,
            ConversationIntent.PARTNERSHIP: AgentId.FREYR,
        }
        for intent, owner in expected.items():
            with self.subTest(intent=intent):
                speaker = DEFAULT_AGENT_REGISTRY.speaker_for(intent)
                self.assertIsNotNone(speaker)
                self.assertEqual(speaker.agent_id, owner)

        self.assertIsNone(
            DEFAULT_AGENT_REGISTRY.speaker_for(
                ConversationIntent.UNRELATED
            )
        )
        self.assertIsNone(
            DEFAULT_AGENT_REGISTRY.speaker_for(
                ConversationIntent.AMBIGUOUS
            )
        )

    def test_profiles_and_scope_sets_are_immutable(self) -> None:
        profile = DEFAULT_AGENT_REGISTRY.get(AgentId.MIMIR)
        with self.assertRaises(FrozenInstanceError):
            profile.title = "changed"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            profile.knowledge_scopes.add(  # type: ignore[attr-defined]
                KnowledgeScope.COMMUNITY_PUBLIC
            )

    def test_username_lookup_is_case_and_at_insensitive(self) -> None:
        profile = DEFAULT_AGENT_REGISTRY.by_username("@zswap_mimirbot")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.agent_id, AgentId.MIMIR)

    def test_non_zion_moderation_authority_is_rejected(self) -> None:
        profiles = list(DEFAULT_AGENT_REGISTRY)
        index = next(
            index
            for index, profile in enumerate(profiles)
            if profile.agent_id is AgentId.EIR
        )
        profiles[index] = replace(
            profiles[index],
            moderation_authority=(
                ModerationAuthority.FULL_DETERMINISTIC
            ),
        )

        with self.assertRaisesRegex(ValueError, "only ZION"):
            AgentRegistry(profiles)

    def test_duplicate_speaker_for_intent_is_rejected(self) -> None:
        profiles = list(DEFAULT_AGENT_REGISTRY)
        index = next(
            index
            for index, profile in enumerate(profiles)
            if profile.agent_id is AgentId.EIR
        )
        profiles[index] = replace(
            profiles[index],
            group_intents=frozenset({ConversationIntent.TECHNICAL}),
        )

        with self.assertRaisesRegex(ValueError, "multiple speakers"):
            AgentRegistry(profiles)

    def test_registry_requires_all_official_agents(self) -> None:
        profiles = [
            profile
            for profile in DEFAULT_AGENT_REGISTRY
            if profile.agent_id is not AgentId.FREYR
        ]
        with self.assertRaisesRegex(ValueError, "missing=.+freyr"):
            AgentRegistry(profiles)

    def test_incomplete_or_unscoped_profile_is_rejected(self) -> None:
        profile = AgentProfile(
            agent_id=AgentId.ZION,
            display_name="",
            title="CCO",
            role=AgentRole.COMMUNITY,
            dm_policy=DMPolicy.CREATOR_ONLY,
            moderation_authority=(
                ModerationAuthority.FULL_DETERMINISTIC
            ),
            knowledge_scopes=frozenset(),
            group_intents=frozenset({ConversationIntent.MODERATION}),
        )
        with self.assertRaisesRegex(ValueError, "incomplete"):
            AgentRegistry((profile,))

    def test_unknown_agent_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            DEFAULT_AGENT_REGISTRY.get("odin")


if __name__ == "__main__":
    unittest.main()
