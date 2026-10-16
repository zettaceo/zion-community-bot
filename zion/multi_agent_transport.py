from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from telegram import Bot, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from .agents import DEFAULT_AGENT_REGISTRY, AgentId, AgentRegistry
from .config import Settings
from .telegram_identity_store import TelegramIdentityStore


logger = logging.getLogger("zion.multi_agent_transport")

SecondaryHandler = Callable[
    [Update, ContextTypes.DEFAULT_TYPE],
    Awaitable[None],
]


@dataclass(frozen=True, slots=True)
class IdentityRuntimeStatus:
    store_status: str
    runtime_status: str
    error_type: str | None = None


class DeliveryOutcomeUncertain(RuntimeError):
    """Telegram may have accepted the send even though no reply was received."""


class DeliveryFailedSafe(RuntimeError):
    """Telegram rejected the send before an accepted outcome was possible."""


class MultiAgentTransport:
    """One core with secondary Telegram identities and isolated DM intake.

    ZION's Application remains the only group intake and Guardian. Secondary
    Applications exist solely to receive their own private messages and to
    provide outbound Bot clients. Any group update delivered to a secondary
    token is consumed without routing, persistence, AI, or reply.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        registry: AgentRegistry = DEFAULT_AGENT_REGISTRY,
        identity_store: TelegramIdentityStore | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.identity_store = identity_store or TelegramIdentityStore(
            settings.telegram_identity_secret_dir
        )
        self._applications: dict[AgentId, Application] = {}
        self._runtime_status: dict[AgentId, IdentityRuntimeStatus] = {}

    def status_all(self) -> dict[AgentId, IdentityRuntimeStatus]:
        statuses: dict[AgentId, IdentityRuntimeStatus] = {
            AgentId.ZION: IdentityRuntimeStatus(
                store_status=TelegramIdentityStore.CONFIGURED,
                runtime_status="PRIMARY",
            )
        }
        for agent_id in (AgentId.MIMIR, AgentId.EIR, AgentId.FREYR):
            statuses[agent_id] = self._runtime_status.get(
                agent_id,
                IdentityRuntimeStatus(
                    store_status=self.identity_store.status(agent_id),
                    runtime_status="STOPPED",
                ),
            )
        return statuses

    @staticmethod
    async def reject_secondary_group_update(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        chat = update.effective_chat
        if chat is None or chat.type == "private":
            return
        # This handler is the only handler registered for non-private updates.
        # It intentionally produces no side effect and no response.
        return

    def prepare(
        self,
        *,
        shared_runtime: Any,
        private_handler: SecondaryHandler,
        error_handler: SecondaryHandler,
    ) -> None:
        if self._applications:
            raise RuntimeError("secondary applications already prepared")

        seen_tokens = {self.settings.telegram_token}
        for agent_id in (AgentId.MIMIR, AgentId.EIR, AgentId.FREYR):
            store_status = self.identity_store.status(agent_id)
            if store_status != TelegramIdentityStore.CONFIGURED:
                self._runtime_status[agent_id] = IdentityRuntimeStatus(
                    store_status=store_status,
                    runtime_status="DISABLED",
                )
                continue
            try:
                token = self.identity_store.read(agent_id)
                if not token or token in seen_tokens:
                    raise ValueError("duplicate_or_missing_identity_token")
                seen_tokens.add(token)
                app = Application.builder().token(token).build()
                app.bot_data["zion_runtime"] = shared_runtime
                app.bot_data["zion_agent_id"] = agent_id
                app.add_handler(
                    MessageHandler(
                        ~filters.ChatType.PRIVATE,
                        self.reject_secondary_group_update,
                    ),
                    group=-100,
                )
                app.add_handler(
                    MessageHandler(
                        filters.ChatType.PRIVATE & filters.ALL,
                        private_handler,
                    )
                )
                app.add_error_handler(error_handler)
                self._applications[agent_id] = app
                self._runtime_status[agent_id] = IdentityRuntimeStatus(
                    store_status=store_status,
                    runtime_status="PREPARED",
                )
            except Exception as exc:
                self._runtime_status[agent_id] = IdentityRuntimeStatus(
                    store_status=store_status,
                    runtime_status="DISABLED",
                    error_type=type(exc).__name__,
                )

    async def start(self) -> None:
        for agent_id, app in self._applications.items():
            try:
                await app.initialize()
                if app.updater is None:
                    raise RuntimeError("secondary updater unavailable")
                await app.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                    bootstrap_retries=0,
                )
                await app.start()
                current = self._runtime_status[agent_id]
                self._runtime_status[agent_id] = IdentityRuntimeStatus(
                    store_status=current.store_status,
                    runtime_status="RUNNING",
                )
            except Exception as exc:
                current = self._runtime_status[agent_id]
                self._runtime_status[agent_id] = IdentityRuntimeStatus(
                    store_status=current.store_status,
                    runtime_status="DEGRADED",
                    error_type=type(exc).__name__,
                )
                logger.warning(
                    "Secondary Telegram identity failed to start | "
                    "agent=%s | error=%s",
                    agent_id.value,
                    type(exc).__name__,
                )
                await self._stop_one(app)

    @staticmethod
    async def _stop_one(app: Application) -> None:
        try:
            if app.updater is not None and app.updater.running:
                await app.updater.stop()
        except Exception:
            pass
        try:
            if app.running:
                await app.stop()
        except Exception:
            pass
        try:
            if getattr(app, "_initialized", False):
                await app.shutdown()
        except Exception:
            pass

    async def stop(self) -> None:
        for agent_id, app in reversed(tuple(self._applications.items())):
            await self._stop_one(app)
            current = self._runtime_status[agent_id]
            self._runtime_status[agent_id] = IdentityRuntimeStatus(
                store_status=current.store_status,
                runtime_status="STOPPED",
                error_type=current.error_type,
            )

    def bot_for(self, agent_id: AgentId, primary_bot: Bot) -> Bot | None:
        if agent_id is AgentId.ZION:
            return primary_bot
        status = self._runtime_status.get(agent_id)
        app = self._applications.get(agent_id)
        if status is None or status.runtime_status != "RUNNING" or app is None:
            return None
        return app.bot

    async def send_message(
        self,
        *,
        agent_id: AgentId,
        primary_bot: Bot,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> Any:
        profile = self.registry.get(agent_id)
        if not profile.can_speak_group:
            raise DeliveryFailedSafe("identity_not_authorized_to_speak")
        bot = self.bot_for(agent_id, primary_bot)
        if bot is None:
            raise DeliveryFailedSafe("identity_transport_unavailable")
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_to_message_id is not None:
            kwargs["reply_to_message_id"] = reply_to_message_id
        try:
            return await bot.send_message(**kwargs)
        except (TimedOut, NetworkError) as exc:
            raise DeliveryOutcomeUncertain(type(exc).__name__) from exc
        except Exception as exc:
            raise DeliveryFailedSafe(type(exc).__name__) from exc
