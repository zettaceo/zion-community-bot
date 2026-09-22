from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.telegram_app import Runtime, build_application, post_init


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

    def test_private_mistral_capture_handler_runs_before_generic_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            application = build_application(settings)
            runtime = application.bot_data["zion_runtime"]
            try:
                self.assertIn(-3, application.handlers)
                self.assertTrue(application.handlers[-3])
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
