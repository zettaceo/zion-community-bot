from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram.error import TimedOut

from tests.helpers import make_settings
from zion.agents import AgentId
from zion.multi_agent_transport import (
    DeliveryFailedSafe,
    DeliveryOutcomeUncertain,
    IdentityRuntimeStatus,
    MultiAgentTransport,
)
from zion.telegram_identity_store import TelegramIdentityStore


class FakeStore:
    def __init__(self, statuses=None, tokens=None) -> None:
        self.statuses = statuses or {}
        self.tokens = tokens or {}

    def status(self, agent_id):
        return self.statuses.get(
            agent_id,
            TelegramIdentityStore.MISSING,
        )

    def read(self, agent_id):
        return self.tokens.get(agent_id)


class FakeBot:
    def __init__(self, outcome=None) -> None:
        self.outcome = outcome
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome or SimpleNamespace(message_id=77)


class FakeUpdater:
    def __init__(self, events) -> None:
        self.events = events
        self.running = False

    async def start_polling(self, **kwargs) -> None:
        self.events.append(("start_polling", kwargs))
        self.running = True

    async def stop(self) -> None:
        self.events.append(("updater_stop", {}))
        self.running = False


class FakeApplicationLifecycle:
    def __init__(self) -> None:
        self.events = []
        self.updater = FakeUpdater(self.events)
        self.running = False
        self._initialized = False
        self.bot = FakeBot()

    async def initialize(self) -> None:
        self.events.append(("initialize", {}))
        self._initialized = True

    async def start(self) -> None:
        self.events.append(("application_start", {}))
        self.running = True

    async def stop(self) -> None:
        self.events.append(("application_stop", {}))
        self.running = False

    async def shutdown(self) -> None:
        self.events.append(("shutdown", {}))
        self._initialized = False


class MultiAgentTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = make_settings(Path(self.temp.name))

    def test_missing_secondary_tokens_are_disabled_without_value_output(self):
        transport = MultiAgentTransport(
            self.settings,
            identity_store=FakeStore(),
        )
        transport.prepare(
            shared_runtime=object(),
            private_handler=self._handler,
            error_handler=self._handler,
        )
        statuses = transport.status_all()
        self.assertEqual(statuses[AgentId.ZION].runtime_status, "PRIMARY")
        for agent_id in (AgentId.MIMIR, AgentId.EIR, AgentId.FREYR):
            self.assertEqual(statuses[agent_id].store_status, "MISSING")
            self.assertEqual(statuses[agent_id].runtime_status, "DISABLED")

    def test_primary_token_reuse_by_secondary_fails_closed(self) -> None:
        store = FakeStore(
            statuses={AgentId.MIMIR: TelegramIdentityStore.CONFIGURED},
            tokens={AgentId.MIMIR: self.settings.telegram_token},
        )
        transport = MultiAgentTransport(
            self.settings,
            identity_store=store,
        )
        transport.prepare(
            shared_runtime=object(),
            private_handler=self._handler,
            error_handler=self._handler,
        )
        status = transport.status_all()[AgentId.MIMIR]
        self.assertEqual(status.runtime_status, "DISABLED")
        self.assertEqual(status.error_type, "ValueError")

    def test_unavailable_identity_fails_before_send(self) -> None:
        transport = MultiAgentTransport(
            self.settings,
            identity_store=FakeStore(),
        )
        with self.assertRaises(DeliveryFailedSafe):
            asyncio.run(
                transport.send_message(
                    agent_id=AgentId.MIMIR,
                    primary_bot=FakeBot(),
                    chat_id=-100,
                    text="hello",
                )
            )

    def test_network_timeout_is_uncertain_and_not_safe_to_replay(self) -> None:
        transport = MultiAgentTransport(
            self.settings,
            identity_store=FakeStore(),
        )
        fake_bot = FakeBot(TimedOut("synthetic"))
        transport._applications[AgentId.EIR] = SimpleNamespace(bot=fake_bot)
        transport._runtime_status[AgentId.EIR] = IdentityRuntimeStatus(
            store_status="CONFIGURED",
            runtime_status="RUNNING",
        )
        with self.assertRaises(DeliveryOutcomeUncertain):
            asyncio.run(
                transport.send_message(
                    agent_id=AgentId.EIR,
                    primary_bot=FakeBot(),
                    chat_id=-100,
                    text="hello",
                )
            )

    def test_secondary_group_update_has_no_side_effect(self) -> None:
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type="supergroup")
        )
        self.assertIsNone(
            asyncio.run(
                MultiAgentTransport.reject_secondary_group_update(
                    update,
                    SimpleNamespace(),
                )
            )
        )

    def test_secondary_lifecycle_starts_and_stops_in_safe_order(self) -> None:
        transport = MultiAgentTransport(
            self.settings,
            identity_store=FakeStore(),
        )
        app = FakeApplicationLifecycle()
        transport._applications[AgentId.EIR] = app
        transport._runtime_status[AgentId.EIR] = IdentityRuntimeStatus(
            store_status="CONFIGURED",
            runtime_status="PREPARED",
        )

        asyncio.run(transport.start())
        self.assertEqual(
            [event[0] for event in app.events],
            ["initialize", "start_polling", "application_start"],
        )
        polling_options = app.events[1][1]
        self.assertTrue(polling_options["drop_pending_updates"])
        self.assertEqual(polling_options["bootstrap_retries"], 0)
        self.assertEqual(
            transport.status_all()[AgentId.EIR].runtime_status,
            "RUNNING",
        )

        asyncio.run(transport.stop())
        self.assertEqual(
            [event[0] for event in app.events][-3:],
            ["updater_stop", "application_stop", "shutdown"],
        )
        self.assertEqual(
            transport.status_all()[AgentId.EIR].runtime_status,
            "STOPPED",
        )

    @staticmethod
    async def _handler(update, context) -> None:
        del update, context


if __name__ == "__main__":
    unittest.main()
