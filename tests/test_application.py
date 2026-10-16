from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.telegram_app import (
    Runtime,
    build_application,
    mistral_secret_capture_handler,
    post_init,
)


class ApplicationBuildTests(unittest.TestCase):
    def test_post_init_refuses_second_scheduler_task(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                settings = make_settings(Path(tmp))
                application = build_application(settings)
                runtime = application.bot_data["zion_runtime"]

                existing = asyncio.create_task(
                    asyncio.sleep(60),
                    name="existing-zion-scheduler",
                )
                application.bot_data["zion_scheduler_task"] = existing

                try:
                    await post_init(application)
                    self.assertIs(
                        application.bot_data["zion_scheduler_task"],
                        existing,
                    )
                    self.assertIsNone(runtime.primary_bot)
                finally:
                    existing.cancel()
                    try:
                        await existing
                    except asyncio.CancelledError:
                        pass
                    runtime.close()

        asyncio.run(scenario())

    def test_application_builds_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            application = build_application(settings)

            runtime = application.bot_data.get("zion_runtime")
            self.assertIsInstance(runtime, Runtime)
            self.assertTrue(application.handlers)

            commands: set[str] = set()
            for handlers in application.handlers.values():
                for handler in handlers:
                    values = getattr(handler, "commands", None)
                    if values:
                        commands.update(values)

            self.assertTrue(
                {
                    "status",
                    "health",
                    "diagnostics",
                    "help",
                    "ama",
                    "amaopen",
                    "amalist",
                    "amaclose",
                    "recurring",
                    "cancelscheduled",
                    "cancelrecurring",
                    "jobs",
                    "retryscheduled",
                    "resumerecurring",
                    "setmistralkey",
                    "clearmistralkey",
                }.issubset(commands)
            )

            runtime.close()

    def test_post_init_binds_primary_zion_bot_before_secondary_start(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                settings = make_settings(Path(tmp))
                application = build_application(settings)
                runtime = application.bot_data["zion_runtime"]
                runtime.multi_agent_transport.start = unittest.mock.AsyncMock()
                try:
                    await post_init(application)
                    self.assertIs(runtime.primary_bot, application.bot)
                    runtime.multi_agent_transport.start.assert_awaited_once()
                finally:
                    task = application.bot_data.get("zion_scheduler_task")
                    if task is not None:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    runtime.close()

        asyncio.run(scenario())

    def test_private_mistral_capture_handler_runs_before_generic_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            application = build_application(settings)
            runtime = application.bot_data["zion_runtime"]
            try:
                self.assertIn(-3, application.handlers)
                self.assertIn(-2, application.handlers)
                self.assertIn(-1, application.handlers)
                secret_handlers = application.handlers[-3]
                self.assertEqual(len(secret_handlers), 1)
                self.assertIs(
                    secret_handlers[0].callback,
                    mistral_secret_capture_handler,
                )
            finally:
                runtime.close()

    def test_application_rejects_deprecated_mistral_env_secret_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(
                make_settings(Path(tmp)),
                legacy_mistral_api_key_present=True,
            )
            with self.assertRaises(RuntimeError):
                build_application(settings)


if __name__ == "__main__":
    unittest.main()
