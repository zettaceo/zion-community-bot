from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.helpers import make_settings
import zion.telegram_app as telegram_app
from zion.db import ZionDB
from zion.guardian import Guardian, normalize_policy_domain
from zion.logging_safe import contains_high_confidence_credential
from zion.models import OperatingState
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

from zion.telegram_app import (
    AskRateLimiter,
    Runtime,
    allow_domain_command,
    ban_command,
    block_domain_command,
    command_guard_handler,
    gaps_command,
    incident_command,
    is_admin,
    moderation_handler,
    mute_command,
    reload_knowledge_command,
    require_admin,
    resolve_gap_command,
    safe_display_text,
    unban_command,
    telegram_entity_domains,
    telegram_external_urls,
    telegram_sensitive_surface,
)


class TelegramLinkSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(
            make_settings(self.root),
            allow_links=True,
            allowed_domains=frozenset({"fass.de", "z-swap.example"}),
        )
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.guardian = Guardian(self.settings, self.db)

    def test_idna2008_sharp_s_does_not_inherit_ascii_allowlist(self) -> None:
        normalized = normalize_policy_domain("https://faß.de/login")
        self.assertEqual(normalized, "xn--fa-hia.de")
        self.assertNotEqual(normalized, "fass.de")

        decision = self.guardian.evaluate_links("https://faß.de/login")
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unauthorized_domains, ["xn--fa-hia.de"])

    def test_inline_keyboard_urls_participate_in_domain_policy(self) -> None:
        button = SimpleNamespace(
            url="https://evil.example/path",
            login_url=None,
            web_app=None,
        )
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(inline_keyboard=[[button]]),
        )

        urls = telegram_external_urls(message)
        domains = telegram_entity_domains(message)

        self.assertEqual(urls, ["https://evil.example/path"])
        self.assertEqual(domains, ["evil.example"])
        decision = self.guardian.evaluate_links("", extra_domains=domains)
        self.assertTrue(decision.should_delete)

    def test_login_and_webapp_urls_are_inspected(self) -> None:
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(
                inline_keyboard=[[
                    SimpleNamespace(
                        url=None,
                        login_url=SimpleNamespace(
                            url="https://login.evil.example/auth"
                        ),
                        web_app=SimpleNamespace(
                            url="https://web.evil.example/app"
                        ),
                    )
                ]]
            ),
        )

        self.assertEqual(
            telegram_entity_domains(message),
            ["login.evil.example", "web.evil.example"],
        )


    def test_unsupported_clickable_scheme_fails_closed(self) -> None:
        decision = self.guardian.evaluate_links(
            "",
            extra_urls=["tg://resolve?domain=untrusted"],
        )
        self.assertTrue(decision.should_delete)
        self.assertIn(
            "<invalid-or-unsupported-url>",
            decision.unauthorized_domains,
        )

    def test_display_text_strips_control_and_bidi_formatting(self) -> None:
        value = "Alice\n\u202eADMIN\tSupport"
        rendered = safe_display_text(value)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\t", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertEqual(rendered, "Alice ADMIN Support")


    def test_percent_encoded_url_credential_is_decoded_for_detection(self) -> None:
        hidden = SimpleNamespace(
            type="text_link",
            url=(
                "https://z-swap.example/support?"
                "api%5Fkey%3Dexample-secret-value-123456"
            ),
        )
        message = SimpleNamespace(
            entities=[hidden],
            caption_entities=[],
            reply_markup=None,
        )

        surface = telegram_sensitive_surface(message, "safe visible text")
        self.assertTrue(contains_high_confidence_credential(surface))

    def test_hidden_url_credentials_are_visible_to_secret_detector(self) -> None:
        hidden = SimpleNamespace(
            type="text_link",
            url=(
                "https://z-swap.example/support?"
                "api_key=example-secret-value-123456"
            ),
        )
        message = SimpleNamespace(
            entities=[hidden],
            caption_entities=[],
            reply_markup=None,
        )

        surface = "\n".join(("safe label", *telegram_external_urls(message)))
        self.assertTrue(contains_high_confidence_credential(surface))


class FakeMessage:
    def __init__(self, text: str, *, message_id: int = 1) -> None:
        self.message_id = message_id
        self.text = text
        self.caption = None
        self.entities = []
        self.caption_entities = []
        self.reply_markup = None
        self.reply_to_message = None
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self, status=ChatMemberStatus.MEMBER) -> None:
        self.status = status
        self.member_calls = 0
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []
        self.restricted: list[tuple[int, int]] = []
        self.banned: list[tuple[int, int]] = []
        self.unbanned: list[tuple[int, int]] = []

    async def get_chat_member(self, *, chat_id: int, user_id: int):
        self.member_calls += 1
        return SimpleNamespace(status=self.status)

    async def delete_message(self, *, chat_id: int, message_id: int):
        self.deleted.append((chat_id, message_id))

    async def send_message(self, *, chat_id: int, text: str):
        self.sent.append((chat_id, text))

    async def restrict_chat_member(
        self, *, chat_id: int, user_id: int, permissions, until_date
    ):
        self.restricted.append((chat_id, user_id))

    async def ban_chat_member(
        self, *, chat_id: int, user_id: int, revoke_messages: bool
    ):
        self.banned.append((chat_id, user_id))

    async def unban_chat_member(
        self, *, chat_id: int, user_id: int, only_if_banned: bool
    ):
        self.unbanned.append((chat_id, user_id))


class FakeApplication:
    def __init__(self, runtime: Runtime) -> None:
        self.bot_data = {"zion_runtime": runtime}
        self.tasks = []

    def create_task(self, coro, *, update=None):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class FakeContext:
    def __init__(self, runtime: Runtime, bot: FakeBot) -> None:
        self.application = FakeApplication(runtime)
        self.bot = bot
        self.args: list[str] = []


def make_update(
    *,
    user_id: int,
    chat_type: str,
    text: str,
    message_id: int = 1,
    reply_target_id: int | None = None,
):
    message = FakeMessage(text, message_id=message_id)
    if reply_target_id is not None:
        message.reply_to_message = SimpleNamespace(
            message_id=message_id - 1,
            from_user=SimpleNamespace(
                id=reply_target_id,
                username=f"user{reply_target_id}",
                first_name=f"User {reply_target_id}",
            ),
        )
    return SimpleNamespace(
        update_id=message_id,
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            first_name=f"User {user_id}",
            language_code="pt",
        ),
        effective_chat=SimpleNamespace(
            id=123 if chat_type == "private" else -100123,
            type=chat_type,
        ),
        effective_message=message,
    )


class AuthorizationAndPrivateBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def test_private_chat_never_infers_admin_from_telegram_role(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        ordinary = make_update(
            user_id=2,
            chat_type="private",
            text="/status",
        )
        explicit = make_update(
            user_id=1,
            chat_type="private",
            text="/status",
            message_id=2,
        )

        self.assertFalse(asyncio.run(is_admin(ordinary, context)))
        self.assertTrue(asyncio.run(is_admin(explicit, context)))
        self.assertEqual(bot.member_calls, 0)

    def test_privileged_command_revalidates_cached_group_admin(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/ban",
        )

        self.assertTrue(asyncio.run(is_admin(update, context)))
        self.assertEqual(bot.member_calls, 1)

        bot.status = ChatMemberStatus.MEMBER
        self.assertFalse(asyncio.run(require_admin(update, context)))
        self.assertEqual(bot.member_calls, 2)
        self.assertTrue(update.effective_message.replies)


    def test_negative_admin_cache_prevents_command_api_amplification(self) -> None:
        bot = FakeBot(ChatMemberStatus.MEMBER)
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/ban",
            message_id=4,
        )

        self.assertFalse(asyncio.run(require_admin(update, context)))
        self.assertFalse(asyncio.run(require_admin(update, context)))
        self.assertEqual(bot.member_calls, 1)

    def test_cached_demoted_admin_loses_command_guard_exemption(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/ask https://evil.example/path",
            message_id=5,
        )

        self.assertTrue(asyncio.run(is_admin(update, context)))
        self.assertEqual(bot.member_calls, 1)
        bot.status = ChatMemberStatus.MEMBER

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, context))

        self.assertEqual(bot.member_calls, 2)
        self.assertEqual(
            bot.deleted,
            [(update.effective_chat.id, update.effective_message.message_id)],
        )

    def test_private_command_skips_group_link_policy(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="/ask veja https://evil.example/path",
        )

        asyncio.run(command_guard_handler(update, context))

        self.assertEqual(bot.deleted, [])
        self.assertEqual(bot.member_calls, 0)

    def test_private_ordinary_message_skips_group_link_policy(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="veja https://evil.example/path",
        )

        asyncio.run(moderation_handler(update, context))

        self.assertEqual(bot.deleted, [])
        self.assertEqual(bot.member_calls, 0)



    def test_encoded_hidden_url_credential_is_blocked_by_handler(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="safe visible label",
            message_id=8,
        )
        update.effective_message.entities = [
            SimpleNamespace(
                type="text_link",
                url=(
                    "https://z-swap.example/support?"
                    "api%5Fkey%3Dexample-secret-value-123456"
                ),
            )
        ]

        asyncio.run(moderation_handler(update, context))

        self.assertEqual(
            bot.deleted,
            [(update.effective_chat.id, update.effective_message.message_id)],
        )
        self.assertEqual(bot.member_calls, 0)
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
        )

    def test_hidden_url_credential_is_blocked_before_admin_exemption(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="safe visible label",
            message_id=9,
        )
        update.effective_message.entities = [
            SimpleNamespace(
                type="text_link",
                url=(
                    "https://z-swap.example/support?"
                    "api_key=example-secret-value-123456"
                ),
            )
        ]

        asyncio.run(moderation_handler(update, context))

        self.assertEqual(
            bot.deleted,
            [(update.effective_chat.id, update.effective_message.message_id)],
        )
        self.assertEqual(bot.member_calls, 0)
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
        )

    def test_private_command_still_blocks_exposed_credential(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="/ask API key: example-secret-value-123456",
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, context))

        self.assertEqual(
            bot.deleted,
            [(update.effective_chat.id, update.effective_message.message_id)],
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
        )


class ModerationDurabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def test_manual_punitive_actions_fail_closed_without_audit_intent(self) -> None:
        scenarios = (
            (ban_command, "/ban", [], "banned"),
            (mute_command, "/mute 10m", ["10m"], "restricted"),
            (unban_command, "/unban 2", ["2"], "unbanned"),
        )
        for index, (handler, text, args, effect_attr) in enumerate(
            scenarios, start=10
        ):
            with self.subTest(handler=handler.__name__):
                bot = FakeBot()
                context = FakeContext(self.runtime, bot)
                context.args = args
                update = make_update(
                    user_id=1,
                    chat_type="supergroup",
                    text=text,
                    message_id=index,
                    reply_target_id=(
                        None if handler is unban_command else 2
                    ),
                )
                with patch.object(
                    self.runtime.db,
                    "create_incident",
                    side_effect=RuntimeError("audit unavailable"),
                ):
                    with self.assertRaises(RuntimeError):
                        asyncio.run(handler(update, context))
                self.assertEqual(getattr(bot, effect_attr), [])

    def test_manual_ban_keeps_intent_if_outcome_write_fails(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="/ban",
            message_id=30,
            reply_target_id=2,
        )

        with patch.object(
            self.runtime.db,
            "record_action",
            side_effect=RuntimeError("outcome write failed"),
        ):
            with self.assertRaises(RuntimeError):
                asyncio.run(ban_command(update, context))

        self.assertEqual(bot.banned, [(update.effective_chat.id, 2)])
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["category"], "manual_ban")
        detail = self.runtime.db.get_incident(incidents[0]["id"])
        self.assertIsNotNone(detail)
        self.assertIn(
            '"requested_by_user_id":1',
            str(detail["evidence_json"]),
        )


    def test_flood_incident_is_durable_before_external_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                flood_max_messages=2,
                flood_ban_after_strikes=1,
            )
            db = ZionDB(settings.db_path)
            db.initialize()
            try:
                guardian = Guardian(settings, db)
                guardian.record_message(
                    chat_id=10,
                    user_id=20,
                    message_id=1,
                    now=3000.0,
                )
                decision = guardian.record_message(
                    chat_id=10,
                    user_id=20,
                    message_id=2,
                    now=3001.0,
                )

                self.assertTrue(decision.triggered)
                self.assertTrue(decision.should_ban)
                self.assertIsNotNone(decision.incident_id)
                incident = db.get_incident(str(decision.incident_id))
                self.assertIsNotNone(incident)
                self.assertEqual(incident["category"], "flood")
                self.assertIn(
                    '"enforcement_pending":true',
                    str(incident["evidence_json"]),
                )
            finally:
                db.close()

    def test_pending_flood_ban_has_persistent_local_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                flood_max_messages=2,
                flood_ban_after_strikes=1,
            )
            db = ZionDB(settings.db_path)
            db.initialize()
            try:
                guardian = Guardian(settings, db)
                first = guardian.record_message(
                    chat_id=10,
                    user_id=20,
                    message_id=1,
                    now=1000.0,
                )
                second = guardian.record_message(
                    chat_id=10,
                    user_id=20,
                    message_id=2,
                    now=1001.0,
                )
                self.assertFalse(first.triggered)
                self.assertTrue(second.triggered)
                self.assertTrue(second.should_ban)
                self.assertGreater(
                    guardian.containment_remaining(10, 20, 1001.0),
                    0,
                )
            finally:
                db.close()

    def test_elevated_state_never_relaxes_low_normal_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                flood_max_messages=2,
            )
            db = ZionDB(settings.db_path)
            db.initialize()
            try:
                db.set_operating_state(OperatingState.ELEVATED)
                guardian = Guardian(settings, db)
                self.assertFalse(
                    guardian.record_message(
                        chat_id=10,
                        user_id=30,
                        message_id=1,
                        now=2000.0,
                    ).triggered
                )
                self.assertTrue(
                    guardian.record_message(
                        chat_id=10,
                        user_id=30,
                        message_id=2,
                        now=2001.0,
                    ).triggered
                )
            finally:
                db.close()

    def test_successful_flood_ban_clears_pending_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            settings = replace(
                make_settings(root),
                flood_max_messages=2,
                flood_ban_after_strikes=1,
            )
            runtime = Runtime(settings)
            try:
                bot = FakeBot()
                context = FakeContext(runtime, bot)

                first = make_update(
                    user_id=2,
                    chat_type="supergroup",
                    text="one",
                    message_id=40,
                )
                second = make_update(
                    user_id=2,
                    chat_type="supergroup",
                    text="two",
                    message_id=41,
                )
                asyncio.run(moderation_handler(first, context))
                asyncio.run(moderation_handler(second, context))

                self.assertEqual(
                    bot.banned,
                    [(second.effective_chat.id, 2)],
                )
                self.assertEqual(
                    runtime.guardian.containment_remaining(
                        second.effective_chat.id,
                        2,
                    ),
                    0,
                )
            finally:
                runtime.close()


class BoundedRuntimeCacheTests(unittest.TestCase):
    def test_rate_limiter_prunes_inactive_user_keys(self) -> None:
        limiter = AskRateLimiter(2)
        with patch("zion.telegram_app.time.monotonic", return_value=100.0):
            self.assertTrue(limiter.allow(10))
            self.assertTrue(limiter.allow(20))
        self.assertEqual(set(limiter._events), {10, 20})

        with patch("zion.telegram_app.time.monotonic", return_value=161.0):
            self.assertTrue(limiter.allow(30))

        self.assertEqual(set(limiter._events), {30})

    def test_admin_cache_prunes_expired_member_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            runtime = Runtime(make_settings(root))
            try:
                bot = FakeBot(ChatMemberStatus.MEMBER)
                context = FakeContext(runtime, bot)
                first = make_update(
                    user_id=20,
                    chat_type="supergroup",
                    text="hello",
                )
                second = make_update(
                    user_id=30,
                    chat_type="supergroup",
                    text="hello",
                    message_id=2,
                )

                with patch(
                    "zion.telegram_app.time.monotonic",
                    return_value=100.0,
                ):
                    self.assertFalse(asyncio.run(is_admin(first, context)))
                self.assertIn(
                    (first.effective_chat.id, 20),
                    runtime.admin_cache,
                )

                with patch(
                    "zion.telegram_app.time.monotonic",
                    return_value=161.0,
                ):
                    self.assertFalse(asyncio.run(is_admin(second, context)))

                self.assertNotIn(
                    (first.effective_chat.id, 20),
                    runtime.admin_cache,
                )
                self.assertIn(
                    (second.effective_chat.id, 30),
                    runtime.admin_cache,
                )
            finally:
                runtime.close()


class OperatorAuditLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def _context(self, args: list[str]) -> tuple[FakeBot, FakeContext]:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        context.args = args
        return bot, context

    def test_domain_policy_change_and_ledger_are_atomic(self) -> None:
        _, context = self._context(["trusted.example"])
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="/allowdomain trusted.example",
            message_id=80,
        )

        self.runtime.db._conn.execute(
            """
            CREATE TEMP TRIGGER fail_domain_audit
            BEFORE INSERT ON actions
            BEGIN SELECT RAISE(ABORT, 'injected'); END
            """
        )
        with self.assertRaises(Exception):
            asyncio.run(allow_domain_command(update, context))

        self.assertIsNone(
            self.runtime.db.domain_disposition("trusted.example")
        )

    def test_domain_policy_change_records_operator_actor(self) -> None:
        _, context = self._context(["blocked.example"])
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="/blockdomain blocked.example",
            message_id=81,
        )

        asyncio.run(block_domain_command(update, context))

        self.assertEqual(
            self.runtime.db.domain_disposition("blocked.example"),
            "block",
        )
        row = self.runtime.db._conn.execute(
            """
            SELECT actor_type, actor_id, metadata_json
            FROM actions
            WHERE action_type='domain_policy_change'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        self.assertEqual(row["actor_type"], "operator")
        self.assertEqual(row["actor_id"], "1")
        self.assertIn('"disposition":"block"', row["metadata_json"])

    def test_resolve_gap_is_audited_atomically(self) -> None:
        self.runtime.db.record_knowledge_gap(
            question_hash="gap-hash",
            sample_text="sample",
        )
        _, context = self._context(["gap-hash"])
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="/resolvegap gap-hash",
            message_id=82,
        )

        asyncio.run(resolve_gap_command(update, context))

        self.assertEqual(
            self.runtime.db.list_knowledge_gaps(limit=10),
            [],
        )
        count = self.runtime.db._conn.execute(
            """
            SELECT COUNT(*) FROM actions
            WHERE action_type='knowledge_gap_resolve'
              AND actor_id='1'
              AND success=1
            """
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_knowledge_reload_records_outcome_without_message_body(self) -> None:
        root = self.runtime.settings.knowledge_dir
        (root / "official.md").write_text(
            "# Test\nApproved fact.",
            encoding="utf-8",
        )
        _, context = self._context([])
        update = make_update(
            user_id=1,
            chat_type="supergroup",
            text="/reloadkb",
            message_id=83,
        )

        asyncio.run(reload_knowledge_command(update, context))

        row = self.runtime.db._conn.execute(
            """
            SELECT actor_id, success, metadata_json
            FROM actions
            WHERE action_type='knowledge_reload'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        self.assertEqual(row["actor_id"], "1")
        self.assertEqual(row["success"], 1)
        self.assertIn('"chunks":1', row["metadata_json"])
        self.assertNotIn("Approved fact", row["metadata_json"])


class OperatorDisplayIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def test_knowledge_gap_display_strips_control_formatting_only_on_output(self) -> None:
        raw = "normal\n\u202eFAKE ADMIN FIELD\tvalue"
        self.runtime.db.record_knowledge_gap(
            question_hash="display-gap",
            sample_text=raw,
        )
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=1,
            chat_type="private",
            text="/gaps",
            message_id=90,
        )

        asyncio.run(gaps_command(update, context))

        rendered = update.effective_message.replies[0]
        self.assertNotIn("\u202e", rendered)
        self.assertNotIn("\nFAKE ADMIN", rendered)
        stored = self.runtime.db.list_knowledge_gaps(limit=10)[0]
        self.assertEqual(stored["sample_text"], raw)

    def test_incident_display_cannot_inject_fake_fields(self) -> None:
        incident_id = self.runtime.db.create_incident(
            chat_id=1,
            user_id=2,
            category="display_test",
            severity="low",
            source="test",
            evidence={"value": "safe\n\u202eSeverity: CRITICAL"},
            note="note\nStatus: resolved",
        )
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        context.args = [incident_id]
        update = make_update(
            user_id=1,
            chat_type="private",
            text=f"/incident {incident_id}",
            message_id=91,
        )

        asyncio.run(incident_command(update, context))

        rendered = update.effective_message.replies[0]
        self.assertNotIn("\u202e", rendered)
        self.assertNotIn("\nStatus: resolved", rendered)
        self.assertNotIn("\nSeverity: CRITICAL", rendered)
        stored = self.runtime.db.get_incident(incident_id)
        self.assertIn("\nStatus: resolved", stored["note"])


class CommandAuthorizationContractTests(unittest.TestCase):
    OPERATOR_ONLY = (
        "health_command",
        "diagnostics_command",
        "ai_status_command",
        "guardian_command",
        "stats_command",
        "gaps_command",
        "resolve_gap_command",
        "incidents_command",
        "incident_command",
        "resolve_incident_command",
        "state_command",
        "lockdown_command",
        "unlock_command",
        "allow_domain_command",
        "block_domain_command",
        "brief_command",
        "jobs_command",
        "retry_scheduled_command",
        "resume_recurring_command",
        "reload_knowledge_command",
    )
    CHAT_ADMIN = (
        "strikes_command",
        "user_command",
        "warn_command",
        "mute_command",
        "ban_command",
        "unban_command",
        "announce_command",
        "poll_command",
        "schedule_command",
        "cancel_scheduled_command",
        "recurring_command",
        "cancel_recurring_command",
        "ama_open_command",
        "ama_list_command",
        "ama_close_command",
    )

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def test_sensitive_commands_reject_ordinary_member_before_side_effects(self) -> None:
        for index, name in enumerate(
            self.OPERATOR_ONLY + self.CHAT_ADMIN,
            start=200,
        ):
            with self.subTest(command=name):
                bot = FakeBot(ChatMemberStatus.MEMBER)
                context = FakeContext(self.runtime, bot)
                update = make_update(
                    user_id=2,
                    chat_type="supergroup",
                    text="/" + name.removesuffix("_command"),
                    message_id=index,
                )

                asyncio.run(getattr(telegram_app, name)(update, context))

                self.assertTrue(update.effective_message.replies)
                self.assertIn(
                    "restrito",
                    update.effective_message.replies[0].lower(),
                )
                self.assertEqual(bot.deleted, [])
                self.assertEqual(bot.restricted, [])
                self.assertEqual(bot.banned, [])
                self.assertEqual(bot.unbanned, [])
                self.assertEqual(bot.sent, [])

    def test_group_admin_cannot_change_global_operating_state(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        context.args = ["LOCKDOWN"]
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/state LOCKDOWN",
            message_id=250,
        )

        asyncio.run(telegram_app.state_command(update, context))

        self.assertEqual(
            self.runtime.db.get_operating_state(),
            OperatingState.NORMAL,
        )
        self.assertTrue(update.effective_message.replies)
        self.assertIn(
            "operadores explícitos",
            update.effective_message.replies[0],
        )
        self.assertEqual(bot.member_calls, 0)

    def test_group_admin_retains_chat_local_authority(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/strikes 99",
            message_id=251,
        )
        context.args = ["99"]

        asyncio.run(telegram_app.strikes_command(update, context))

        self.assertEqual(bot.member_calls, 1)
        self.assertTrue(update.effective_message.replies)
        self.assertIn(
            "nenhum strike ativo",
            update.effective_message.replies[0],
        )


if __name__ == "__main__":
    unittest.main()
