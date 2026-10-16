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
