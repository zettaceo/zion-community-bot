from __future__ import annotations

import unittest

from zion.agents import DEFAULT_AGENT_REGISTRY, AgentId
from zion.dm_policy import evaluate_dm_access


class DMPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admins = frozenset({101})

    def test_zion_allows_only_explicit_operator_id(self) -> None:
        zion = DEFAULT_AGENT_REGISTRY.get(AgentId.ZION)

        allowed = evaluate_dm_access(
            zion,
            user_id=101,
            admin_user_ids=self.admins,
        )
        denied = evaluate_dm_access(
            zion,
            user_id=202,
            admin_user_ids=self.admins,
        )

        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.reason, "authorized_creator")
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "creator_authorization_required")

    def test_mimir_dm_is_closed_even_for_operator(self) -> None:
        decision = evaluate_dm_access(
            DEFAULT_AGENT_REGISTRY.get(AgentId.MIMIR),
            user_id=101,
            admin_user_ids=self.admins,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "dm_closed")

    def test_eir_and_freyr_accept_public_dm(self) -> None:
        for agent_id in (AgentId.EIR, AgentId.FREYR):
            with self.subTest(agent_id=agent_id):
                decision = evaluate_dm_access(
                    DEFAULT_AGENT_REGISTRY.get(agent_id),
                    user_id=202,
                    admin_user_ids=self.admins,
                )
                self.assertTrue(decision.allowed)
                self.assertEqual(decision.reason, "public_dm")


if __name__ == "__main__":
    unittest.main()
