from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zion.db import ZionDB


class RoutingTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = ZionDB(Path(self.temp.name) / "zion.db")
        self.db.initialize()
        self.addCleanup(self.db.close)

    def test_telemetry_counts_routes_handoffs_silence_and_failures(self) -> None:
        self.assertTrue(
            self.db.record_routing_event(
                route_key="route-1",
                source_identity="zion",
                channel="group",
                initial_agent="eir",
                selected_agent="mimir",
                intent="technical",
                outcome="routed",
                reason="technical_question",
                handoff_count=1,
                status="selected",
                now=10.0,
            )
        )
        self.assertTrue(
            self.db.complete_routing_event(
                "route-1",
                status="sent",
                now=11.0,
            )
        )
        self.db.record_routing_event(
            route_key="route-2",
            source_identity="zion",
            channel="group",
            initial_agent=None,
            selected_agent=None,
            intent="ambiguous",
            outcome="ambiguous",
            reason="addressed_but_ambiguous",
            status="suppressed",
            now=12.0,
        )
        self.db.record_routing_event(
            route_key="route-3",
            source_identity="mimir",
            channel="private",
            initial_agent="mimir",
            selected_agent=None,
            intent="technical",
            outcome="dm_denied",
            reason="dm_closed",
            status="denied",
            now=13.0,
        )
        telemetry = self.db.routing_telemetry()
        self.assertEqual(telemetry["agents"]["mimir"]["routed"], 1)
        self.assertEqual(telemetry["agents"]["mimir"]["sent"], 1)
        self.assertEqual(telemetry["agents"]["mimir"]["last_success"], 11.0)
        self.assertEqual(telemetry["ambiguous"], 1)
        self.assertEqual(telemetry["handoffs"], 1)
        self.assertEqual(telemetry["dm_denied"], 1)

    def test_duplicate_route_key_does_not_double_count(self) -> None:
        kwargs = {
            "route_key": "same-key",
            "source_identity": "zion",
            "channel": "group",
            "initial_agent": None,
            "selected_agent": "eir",
            "intent": "support",
            "outcome": "routed",
            "reason": "user_problem",
            "status": "selected",
        }
        self.assertTrue(self.db.record_routing_event(**kwargs))
        self.assertFalse(self.db.record_routing_event(**kwargs))
        self.assertEqual(
            self.db.routing_telemetry()["agents"]["eir"]["routed"],
            1,
        )

    def test_schema_cannot_store_message_or_user_content(self) -> None:
        columns = {
            row["name"]
            for row in self.db._conn.execute(
                "PRAGMA table_info(routing_events)"
            ).fetchall()
        }
        self.assertFalse(
            columns.intersection(
                {
                    "text",
                    "message_text",
                    "prompt",
                    "body",
                    "chat_id",
                    "user_id",
                    "username",
                    "contact",
                }
            )
        )

    def test_invalid_actor_or_unbounded_handoff_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.db.record_routing_event(
                route_key="invalid",
                source_identity="attacker",
                channel="group",
                initial_agent=None,
                selected_agent="mimir",
                intent="technical",
                outcome="routed",
                reason="technical_question",
                status="selected",
            )
        with self.assertRaises(ValueError):
            self.db.record_routing_event(
                route_key="loop",
                source_identity="zion",
                channel="group",
                initial_agent="eir",
                selected_agent="mimir",
                intent="technical",
                outcome="routed",
                reason="technical_question",
                handoff_count=2,
                status="selected",
            )


if __name__ == "__main__":
    unittest.main()
