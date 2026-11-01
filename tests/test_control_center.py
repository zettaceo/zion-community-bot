from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_settings
from zion.models import OperatingState
from zion.telegram_app import (
    ControlCenterSession,
    Runtime,
    control_center_callback,
    send_control_center,
)


class FakeMessage:
    def __init__(self) -> None:
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append((text, kwargs))


class FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class ControlCenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(make_settings(Path(self.temp.name)))
        self.addCleanup(self.runtime.close)
        self.context = SimpleNamespace(
            application=SimpleNamespace(
                bot_data={"zion_runtime": self.runtime}
            )
        )

    def update(self, *, user_id=1, data=None):
        message = FakeMessage()
        query = FakeQuery(data) if data is not None else None
        return SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id),
            effective_chat=SimpleNamespace(id=user_id, type="private"),
            callback_query=query,
        )

    def test_creator_opens_menu_without_secret_values(self) -> None:
        update = self.update()
        opened = asyncio.run(send_control_center(update, self.context))
        self.assertTrue(opened)
        text, kwargs = update.effective_message.calls[0]
        self.assertEqual(text, "ZION CONTROL CENTER\nSelecione uma área.")
        rendered = repr(kwargs["reply_markup"])
        self.assertNotIn(self.runtime.settings.telegram_token, rendered)
        self.assertTrue(self.runtime.control_center_sessions)

    def test_provider_panel_distinguishes_credential_from_activation(self):
        main = self.update()
        asyncio.run(send_control_center(main, self.context))
        nonce = next(iter(self.runtime.control_center_sessions))
        update = self.update(data=f"zc1:{nonce}:ai")
        asyncio.run(control_center_callback(update, self.context))
        text = update.callback_query.edits[0][0]
        self.assertIn("Active provider: Mistral", text)
        self.assertIn("Kimi store: MISSING", text)
        self.assertIn("Kimi activation: BLOCKED", text)
        self.assertIn("Tokens today UTC:", text)
        self.assertNotIn(str(self.runtime.settings.mistral_secret_path), text)

    def test_provider_ledger_failure_shows_unavailable_not_zero(self):
        from zion.provider_budget import ProviderTokenBudget
        self.runtime.db.set_setting(ProviderTokenBudget.KEY, '{broken')
        asyncio.run(send_control_center(self.update(), self.context))
        nonce = next(iter(self.runtime.control_center_sessions))
        update = self.update(data=f"zc1:{nonce}:ai")
        asyncio.run(control_center_callback(update, self.context))
        text = update.callback_query.edits[0][0]
        self.assertIn('tokens (charged/reserved): UNAVAILABLE', text)
        self.assertIn('Accounting: FAIL-CLOSED', text)

    def test_non_operator_cannot_open_or_use_panel(self) -> None:
        update = self.update(user_id=9)
        self.assertFalse(
            asyncio.run(send_control_center(update, self.context))
        )
        forged = self.update(user_id=9, data="zc1:forged:main")
        asyncio.run(control_center_callback(forged, self.context))
        self.assertEqual(forged.callback_query.edits, [])
        self.assertEqual(
            forged.callback_query.answers[0][0],
            "Não autorizado.",
        )

    def test_stale_callback_is_rejected(self) -> None:
        self.runtime.control_center_sessions["stale"] = ControlCenterSession(
            operator_id=1,
            expires_at=time.monotonic() - 1,
        )
        update = self.update(data="zc1:stale:main")
        asyncio.run(control_center_callback(update, self.context))
        self.assertEqual(update.callback_query.edits, [])
        self.assertIn("expirado", update.callback_query.answers[0][0])

    def test_agents_submenu_exposes_safe_policy_scope_and_telemetry(self) -> None:
        main = self.update()
        asyncio.run(send_control_center(main, self.context))
        nonce = next(iter(self.runtime.control_center_sessions))

        agents = self.update(data=f"zc1:{nonce}:agents")
        asyncio.run(control_center_callback(agents, self.context))
        text, kwargs = agents.callback_query.edits[0]
        self.assertIn("EIR: runtime=", text)
        rendered = repr(kwargs["reply_markup"])
        self.assertIn("agent_eir", rendered)
        self.assertIn("routing", rendered)

        detail = self.update(data=f"zc1:{nonce}:agent_eir")
        asyncio.run(control_center_callback(detail, self.context))
        detail_text = detail.callback_query.edits[0][0]
        self.assertIn("DM policy: public", detail_text)
        self.assertIn("support_public", detail_text)
        self.assertIn("Responses sent: 0", detail_text)
        self.assertNotIn(self.runtime.settings.telegram_token, detail_text)

    def test_lockdown_requires_confirmation_and_is_one_time(self) -> None:
        main = self.update()
        asyncio.run(send_control_center(main, self.context))
        nonce = next(iter(self.runtime.control_center_sessions))
        request = self.update(data=f"zc1:{nonce}:lockdown_request")
        asyncio.run(control_center_callback(request, self.context))
        markup = request.callback_query.edits[0][1]["reply_markup"]
        confirm_data = markup.inline_keyboard[0][0].callback_data

        confirm = self.update(data=confirm_data)
        asyncio.run(control_center_callback(confirm, self.context))
        self.assertEqual(
            self.runtime.db.get_operating_state(),
            OperatingState.LOCKDOWN,
        )
        actions = self.runtime.db._conn.execute(
            "SELECT COUNT(*) FROM actions WHERE action_type='lockdown'"
        ).fetchone()[0]
        self.assertEqual(actions, 1)

        replay = self.update(data=confirm_data)
        asyncio.run(control_center_callback(replay, self.context))
        actions = self.runtime.db._conn.execute(
            "SELECT COUNT(*) FROM actions WHERE action_type='lockdown'"
        ).fetchone()[0]
        self.assertEqual(actions, 1)


if __name__ == "__main__":
    unittest.main()
