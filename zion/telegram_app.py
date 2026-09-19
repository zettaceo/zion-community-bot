from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .ai_service import AIService
from .config import Settings
from .db import ZionDB
from .guardian import Guardian
from .health import HealthService
from .knowledge import KnowledgeBase
from .logging_safe import configure_logging
from .migrate import migrate_legacy_guardian_state
from .models import FloodDecision, OperatingState, Severity


logger = logging.getLogger("zion.telegram")

ADMIN_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.OWNER,
}


class AskRateLimiter:
    def __init__(self, requests_per_minute: int):
        self.limit = max(1, requests_per_minute)
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        queue = self._events[user_id]
        while queue and now - queue[0] > 60:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        return True


class Runtime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = ZionDB(settings.db_path)
        self.db.initialize()
        migrate_legacy_guardian_state(
            self.db,
            settings.legacy_state_path,
        )
        self.knowledge = KnowledgeBase(settings.knowledge_dir)
        self.guardian = Guardian(settings, self.db)
        self.ai = AIService(settings, self.db, self.knowledge)
        self.health = HealthService(settings, self.db)
        self.ask_limiter = AskRateLimiter(
            settings.ai_user_requests_per_minute
        )
        self.admin_cache: dict[
            tuple[int, int],
            tuple[bool, float],
        ] = {}


def runtime(context: ContextTypes.DEFAULT_TYPE) -> Runtime:
    value = context.application.bot_data.get("zion_runtime")
    if not isinstance(value, Runtime):
        raise RuntimeError("Runtime ZION não inicializado.")
    return value


def user_display_name(user: Any) -> str:
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)
    user_id = getattr(user, "id", "?")

    if username:
        return f"@{username}"
    if first_name:
        return str(first_name)
    return f"usuário {user_id}"


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} segundos"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "1 hora" if hours == 1 else f"{hours} horas"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return "1 minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{seconds} segundos"


def parse_duration(value: str) -> int | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None

    suffix = raw[-1]
    multiplier = 1
    number = raw

    if suffix in {"s", "m", "h", "d"}:
        number = raw[:-1]
        multiplier = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
        }[suffix]

    try:
        seconds = int(number) * multiplier
    except ValueError:
        return None

    if seconds < 10 or seconds > 30 * 86400:
        return None
    return seconds


async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not update.effective_user or not update.effective_chat:
        return False

    rt = runtime(context)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id in rt.settings.admin_user_ids:
        return True

    # Em chat privado, nunca inferimos privilégio de admin.
    # É necessário estar em ZION_ADMIN_USER_IDS.
    if update.effective_chat.type == "private":
        return False

    key = (chat_id, user_id)
    now = time.monotonic()
    cached = rt.admin_cache.get(key)
    if cached and now < cached[1]:
        return cached[0]

    try:
        member = await context.bot.get_chat_member(
            chat_id=chat_id,
            user_id=user_id,
        )
        result = member.status in ADMIN_STATUSES
        rt.admin_cache[key] = (
            result,
            now + rt.settings.admin_cache_seconds,
        )
        return result
    except Exception as exc:
        logger.warning(
            "Falha ao verificar admin chat=%s user=%s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False


async def require_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if await is_admin(update, context):
        return True

    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Comando restrito aos administradores autorizados."
        )
    return False


def record_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    increment_messages: bool = False,
) -> None:
    if not update.effective_user or not update.effective_chat:
        return

    user = update.effective_user
    runtime(context).db.upsert_user(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        language_code=user.language_code,
        increment_messages=increment_messages,
    )


async def delete_message_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> bool:
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
        return True
    except Exception as exc:
        logger.debug(
            "Falha ao apagar chat=%s message=%s: %s",
            chat_id,
            message_id,
            exc,
        )
        return False


async def mute_user_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    seconds: int,
) -> bool:
    try:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Falha ao silenciar chat=%s user=%s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False


async def ban_user_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            revoke_messages=True,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Falha ao banir chat=%s user=%s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False


async def unban_user_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
) -> bool:
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Falha ao desbanir chat=%s user=%s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    record_user(update, context)
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "ZION online.\n\n"
        "Sistema oficial da comunidade Z-SWAP.\n"
        "Guardian determinístico ativo.\n"
        "Use /rules para consultar as regras e /ask para suporte."
    )


async def rules_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "⚡ Z-SWAP COMMUNITY RULES\n\n"
        "1. Respeite os membros da comunidade.\n"
        "2. Sem spam ou flood.\n"
        "3. Sem golpes, phishing ou impersonação.\n"
        "4. Links dependem da política vigente.\n"
        "5. Nunca envie seed phrase ou chave privada.\n"
        "6. Administradores nunca pedirão sua seed phrase.\n"
        "7. Críticas, dúvidas e discordâncias são permitidas.\n"
        "8. Decisões ambíguas de moderação não são delegadas à IA.\n\n"
        "A camada de IA pode observar e orientar; punições automáticas "
        "dependem de regras determinísticas."
    )


async def id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    await update.effective_message.reply_text(
        f"Chat ID: {update.effective_chat.id}"
    )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    rt = runtime(context)
    snapshot = rt.health.snapshot()

    ai_state = "MISTRAL ACTIVE" if rt.ai.enabled else "MISTRAL DISABLED"
    observe_state = (
        "OBSERVE-ONLY ON"
        if rt.settings.ai_observe and rt.ai.enabled
        else "OBSERVE-ONLY OFF"
    )

    await update.effective_message.reply_text(
        "ZION STATUS: ONLINE\n"
        f"Operating State: {snapshot.state.value}\n"
        "Community Core: ACTIVE\n"
        "Guardian State: SQLITE PERSISTENT\n"
        f"AI Layer: {ai_state}\n"
        f"AI Moderation: {observe_state}"
    )


async def health_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    rt = runtime(context)
    snapshot = rt.health.snapshot()
    uptime = rt.health.format_uptime(snapshot.uptime_seconds)

    await update.effective_message.reply_text(
        "ZION HEALTH\n"
        f"State: {snapshot.state.value}\n"
        f"Database: {'OK' if snapshot.db_ok else 'FAIL'}\n"
        f"Telegram Config: {'OK' if snapshot.telegram_configured else 'FAIL'}\n"
        f"Mistral: {'READY' if rt.ai.enabled else 'OFF'}\n"
        f"Wi-Fi Interface: {'PRESENT' if snapshot.wifi_interface_present else 'MISSING'}\n"
        f"Disk Free: {snapshot.disk_free_mb} MB\n"
        f"Process Uptime: {uptime}"
    )


async def ai_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    rt = runtime(context)
    key_state = "configured" if rt.settings.mistral_api_key else "missing"
    await update.effective_message.reply_text(
        "ZION AI\n"
        "Provider: Mistral AI\n"
        f"Model: {rt.settings.mistral_model}\n"
        f"Enabled: {rt.settings.ai_enabled}\n"
        f"API key: {key_state}\n"
        f"Observe-only moderation: {rt.settings.ai_observe}\n"
        f"Knowledge chunks: {len(rt.knowledge.chunks)}"
    )


async def protect_sensitive_command_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source_message_id: int | None = None,
    source_user_id: int | None = None,
) -> bool:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return False

    rt = runtime(context)
    sensitive = rt.guardian.sensitive_content(text)
    if not sensitive.detected:
        return False

    message_id_to_delete = (
        source_message_id
        if source_message_id is not None
        else update.effective_message.message_id
    )
    deleted = await delete_message_safe(
        context,
        update.effective_chat.id,
        message_id_to_delete,
    )
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=(
            source_user_id
            if source_user_id is not None
            else update.effective_user.id
        ),
        category=sensitive.kind,
        severity=Severity.CRITICAL,
        source="guardian_command_input",
        evidence={
            "message_id": message_id_to_delete,
            "content_not_stored": True,
        },
        note=sensitive.reason,
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=(
            source_user_id
            if source_user_id is not None
            else update.effective_user.id
        ),
        action_type="delete",
        actor_type="guardian",
        actor_id=None,
        reason=sensitive.kind,
        success=deleted,
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "🚨 ZION bloqueou a solicitação porque ela parece conter "
            "uma seed phrase/chave privada. Esse conteúdo não foi enviado "
            "à Mistral."
        ),
    )
    return True


async def ask_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    record_user(update, context)

    question = " ".join(context.args).strip()
    if not question:
        await update.effective_message.reply_text(
            "Use: /ask sua pergunta sobre a Z-SWAP"
        )
        return

    rt = runtime(context)

    if await protect_sensitive_command_input(
        update,
        context,
        question,
    ):
        return

    if not rt.ask_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Limite temporário de perguntas atingido. Tente novamente em instantes."
        )
        return

    answer = await rt.ai.answer(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        question=question[:6000],
    )
    await update.effective_message.reply_text(answer.text[:3900])


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "ZION COMMANDS\n"
        "/status — estado do sistema\n"
        "/health — saúde operacional\n"
        "/rules — regras da comunidade\n"
        "/ask <pergunta> — suporte Z-SWAP com Mistral + base oficial\n"
        "/summary <texto> — resumo explícito via Mistral\n"
        "/translate <idioma> <texto> — tradução explícita via Mistral\n"
        "/report — responda a uma mensagem para denunciar\n"
        "/aistatus — estado da camada de IA"
    )


async def summary_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    replied = update.effective_message.reply_to_message
    if replied and (replied.text or replied.caption):
        source = replied.text or replied.caption or ""
    else:
        source = " ".join(context.args).strip()

    if not source:
        await update.effective_message.reply_text(
            "Responda a uma mensagem com /summary ou use /summary <texto>."
        )
        return

    if await protect_sensitive_command_input(
        update,
        context,
        source,
        source_message_id=(replied.message_id if replied else None),
        source_user_id=(
            replied.from_user.id
            if replied and replied.from_user
            else None
        ),
    ):
        return

    rt = runtime(context)
    if not rt.ask_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Limite temporário de IA atingido. Tente novamente em instantes."
        )
        return

    answer = await rt.ai.summarize(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        text=source[:12000],
    )
    await update.effective_message.reply_text(answer.text[:3900])


async def translate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use /translate en <texto> ou responda a uma mensagem "
            "com /translate en."
        )
        return

    target = context.args[0]
    replied = update.effective_message.reply_to_message

    if replied and (replied.text or replied.caption):
        source = replied.text or replied.caption or ""
    else:
        source = " ".join(context.args[1:]).strip()

    if not source:
        await update.effective_message.reply_text(
            "Nenhum texto encontrado para traduzir."
        )
        return

    if await protect_sensitive_command_input(
        update,
        context,
        source,
        source_message_id=(replied.message_id if replied else None),
        source_user_id=(
            replied.from_user.id
            if replied and replied.from_user
            else None
        ),
    ):
        return

    rt = runtime(context)
    if not rt.ask_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Limite temporário de IA atingido. Tente novamente em instantes."
        )
        return

    answer = await rt.ai.translate(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        text=source[:12000],
        target_language=target,
    )
    await update.effective_message.reply_text(answer.text[:3900])


async def guardian_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    rt = runtime(context)
    await update.effective_message.reply_text(
        "ZION GUARDIAN\n"
        f"State: {rt.db.get_operating_state().value}\n"
        f"Flood: {rt.settings.flood_max_messages} msgs/"
        f"{rt.settings.flood_window_seconds}s\n"
        f"Purge window: {rt.settings.flood_purge_window_seconds}s\n"
        f"Ban after active strikes: {rt.settings.flood_ban_after_strikes}\n"
        f"Links globally enabled: {rt.settings.allow_links}\n"
        f"Raid threshold: {rt.settings.raid_max_joins} joins/"
        f"{rt.settings.raid_window_seconds}s\n"
        "AI punitive authority: NONE"
    )


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    stats = runtime(context).db.stats()
    await update.effective_message.reply_text(
        "ZION STATS\n"
        f"Users: {stats.get('users', 0)}\n"
        f"Strikes: {stats.get('strikes', 0)}\n"
        f"Incidents: {stats.get('incidents', 0)}\n"
        f"Actions: {stats.get('actions', 0)}\n"
        f"AI Events: {stats.get('ai_events', 0)}\n"
        f"Knowledge Gaps: {stats.get('knowledge_gaps', 0)}"
    )


async def gaps_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    gaps = runtime(context).db.list_knowledge_gaps(limit=10)
    if not gaps:
        await update.effective_message.reply_text(
            "Nenhuma lacuna de conhecimento aberta."
        )
        return

    lines = ["ZION KNOWLEDGE GAPS"]
    for item in gaps:
        lines.append(
            f"{item['question_hash']} | x{item['seen_count']} | "
            f"{item['sample_text'][:220]}"
        )
    await update.effective_message.reply_text("\n".join(lines)[:3900])


async def resolve_gap_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /resolvegap <question_hash>"
        )
        return

    success = runtime(context).db.set_knowledge_gap_status(
        context.args[0].strip(),
        "resolved",
    )
    await update.effective_message.reply_text(
        "Lacuna marcada como resolvida."
        if success
        else "Hash de lacuna não encontrado."
    )


async def incidents_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    limit = 8
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 20))
        except ValueError:
            pass

    incidents = runtime(context).db.list_incidents(limit)
    if not incidents:
        await update.effective_message.reply_text("Nenhum incidente registrado.")
        return

    lines = ["ZION INCIDENTS"]
    for item in incidents:
        when = datetime.fromtimestamp(
            float(item["created_at"]),
            tz=timezone.utc,
        ).strftime("%Y-%m-%d %H:%MZ")
        lines.append(
            f"{item['id'][:8]} | {item['severity']} | "
            f"{item['category']} | user={item['user_id']} | {when}"
        )

    await update.effective_message.reply_text("\n".join(lines)[:3900])


async def incident_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /incident <id-ou-prefixo>"
        )
        return

    incident = runtime(context).db.get_incident(context.args[0])
    if not incident:
        await update.effective_message.reply_text(
            "Incidente não encontrado ou prefixo ambíguo."
        )
        return

    try:
        evidence = incident.get("evidence_json") or "{}"
        evidence_text = str(evidence)[:900]
    except Exception:
        evidence_text = "{}"

    when = datetime.fromtimestamp(
        float(incident["created_at"]),
        tz=timezone.utc,
    ).isoformat()

    await update.effective_message.reply_text(
        "ZION INCIDENT\n"
        f"ID: {incident['id']}\n"
        f"Status: {incident['status']}\n"
        f"Severity: {incident['severity']}\n"
        f"Category: {incident['category']}\n"
        f"Source: {incident['source']}\n"
        f"Chat: {incident['chat_id']}\n"
        f"User: {incident['user_id']}\n"
        f"Created: {when}\n"
        f"Note: {incident.get('note') or '-'}\n"
        f"Evidence: {evidence_text}"
    )


async def resolve_incident_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_user:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /resolveincident <id-ou-prefixo>"
        )
        return

    rt = runtime(context)
    incident = rt.db.get_incident(context.args[0])
    if not incident:
        await update.effective_message.reply_text(
            "Incidente não encontrado ou prefixo ambíguo."
        )
        return

    success = rt.db.set_incident_status(
        str(incident["id"]),
        "resolved",
    )
    rt.db.record_action(
        incident_id=str(incident["id"]),
        chat_id=incident.get("chat_id"),
        user_id=incident.get("user_id"),
        action_type="resolve_incident",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_review",
        success=success,
    )
    await update.effective_message.reply_text(
        "Incidente marcado como resolvido."
        if success
        else "Não foi possível resolver o incidente."
    )


async def strikes_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_chat:
        return

    replied = update.effective_message.reply_to_message
    if replied and replied.from_user:
        target_id = replied.from_user.id
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            target_id = 0
    else:
        target_id = 0

    if not target_id:
        await update.effective_message.reply_text(
            "Responda a uma mensagem com /strikes ou use /strikes <user_id>."
        )
        return

    rows = runtime(context).db.list_active_strikes(
        update.effective_chat.id,
        target_id,
        limit=20,
    )
    if not rows:
        await update.effective_message.reply_text(
            f"Usuário {target_id}: nenhum strike ativo."
        )
        return

    lines = [f"ZION STRIKES | user={target_id}"]
    for item in rows:
        expires = item.get("expires_at")
        expires_text = (
            datetime.fromtimestamp(
                float(expires),
                tz=timezone.utc,
            ).isoformat()
            if expires
            else "never"
        )
        lines.append(
            f"{item['id'][:8]} | {item['severity']} | "
            f"{item['reason']} | exp={expires_text}"
        )
    await update.effective_message.reply_text("\n".join(lines)[:3900])


async def user_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_chat:
        return

    target = None
    if update.effective_message.reply_to_message:
        target = update.effective_message.reply_to_message.from_user

    if target is None and context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            target_id = 0
    elif target is not None:
        target_id = target.id
    else:
        await update.effective_message.reply_text(
            "Responda a uma mensagem com /user ou use /user <user_id>."
        )
        return

    summary = runtime(context).db.user_summary(
        update.effective_chat.id,
        target_id,
    )
    user = summary["user"]
    if not user:
        await update.effective_message.reply_text(
            f"Usuário {target_id} ainda não possui histórico local."
        )
        return

    contained_until = float(summary["contained_until"])
    contained = (
        datetime.fromtimestamp(contained_until, tz=timezone.utc).isoformat()
        if contained_until > time.time()
        else "no"
    )

    await update.effective_message.reply_text(
        "ZION USER\n"
        f"ID: {target_id}\n"
        f"Username: {user.get('username') or '-'}\n"
        f"Messages observed: {user.get('message_count', 0)}\n"
        f"Active strikes: {summary['active_strikes']}\n"
        f"Incidents: {summary['incidents']}\n"
        f"Contained until: {contained}"
    )


async def state_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_user:
        return

    rt = runtime(context)

    if not context.args:
        await update.effective_message.reply_text(
            f"ZION operating state: {rt.db.get_operating_state().value}"
        )
        return

    raw = context.args[0].strip().upper()
    try:
        state = OperatingState(raw)
    except ValueError:
        allowed = ", ".join(item.value for item in OperatingState)
        await update.effective_message.reply_text(
            f"Estado inválido. Permitidos: {allowed}"
        )
        return

    previous = rt.db.get_operating_state()
    rt.db.set_operating_state(state)
    rt.db.set_setting("operating_state_expires_at", "0")
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=None,
        action_type="state_change",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason=f"{previous.value}->{state.value}",
        success=True,
    )
    await update.effective_message.reply_text(
        f"ZION state: {previous.value} → {state.value}"
    )


async def lockdown_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_user:
        return

    rt = runtime(context)
    rt.db.set_operating_state(OperatingState.LOCKDOWN)
    rt.db.set_setting("operating_state_expires_at", "0")
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=None,
        action_type="lockdown",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=True,
    )
    await update.effective_message.reply_text(
        "🔒 ZION LOCKDOWN ativado. Mensagens de não administradores serão bloqueadas."
    )


async def unlock_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_user:
        return

    rt = runtime(context)
    rt.db.set_operating_state(OperatingState.NORMAL)
    rt.db.set_setting("operating_state_expires_at", "0")
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=None,
        action_type="unlock",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=True,
    )
    await update.effective_message.reply_text(
        "🔓 ZION voltou ao estado NORMAL."
    )


async def allow_domain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /allowdomain example.com"
        )
        return

    domain = context.args[0].lower().strip().strip(".")
    runtime(context).db.set_domain(domain, "allow", "admin")
    await update.effective_message.reply_text(
        f"Domínio permitido: {domain}"
    )


async def block_domain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /blockdomain example.com"
        )
        return

    domain = context.args[0].lower().strip().strip(".")
    runtime(context).db.set_domain(domain, "block", "admin")
    await update.effective_message.reply_text(
        f"Domínio bloqueado: {domain}"
    )


async def warn_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    replied = update.effective_message.reply_to_message
    target = replied.from_user if replied else None
    if not target:
        await update.effective_message.reply_text(
            "Responda à mensagem do usuário com /warn [motivo]."
        )
        return

    reason = " ".join(context.args).strip() or "advertência administrativa"
    rt = runtime(context)
    rt.db.add_strike(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        reason=reason[:200],
        severity=Severity.MEDIUM,
        source="admin",
        ttl_seconds=rt.settings.flood_strike_reset_seconds,
    )
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="manual_warning",
        severity=Severity.MEDIUM,
        source="admin",
        evidence={"message_id": replied.message_id if replied else None},
        note=reason[:500],
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=target.id,
        action_type="warn",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason=reason[:200],
        success=True,
    )
    await update.effective_message.reply_text(
        f"⚠️ {user_display_name(target)} recebeu uma advertência."
    )


async def mute_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    replied = update.effective_message.reply_to_message
    target = replied.from_user if replied else None
    seconds = parse_duration(context.args[0]) if context.args else None

    if not target or seconds is None:
        await update.effective_message.reply_text(
            "Responda à mensagem com /mute 10m (s/m/h/d)."
        )
        return

    success = await mute_user_safe(
        context,
        update.effective_chat.id,
        target.id,
        seconds,
    )
    rt = runtime(context)
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="manual_mute",
        severity=Severity.MEDIUM,
        source="admin",
        evidence={"duration_seconds": seconds},
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=target.id,
        action_type="mute",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=success,
        metadata={"duration_seconds": seconds},
    )
    await update.effective_message.reply_text(
        (
            f"🔇 {user_display_name(target)} silenciado por "
            f"{format_duration(seconds)}."
        )
        if success
        else "Falha ao aplicar mute. Verifique as permissões do bot."
    )


async def ban_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    replied = update.effective_message.reply_to_message
    target = replied.from_user if replied else None
    if not target:
        await update.effective_message.reply_text(
            "Responda à mensagem do usuário com /ban."
        )
        return

    success = await ban_user_safe(
        context,
        update.effective_chat.id,
        target.id,
    )
    rt = runtime(context)
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="manual_ban",
        severity=Severity.HIGH,
        source="admin",
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=target.id,
        action_type="ban",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=success,
    )
    await update.effective_message.reply_text(
        (
            f"⛔ {user_display_name(target)} foi banido."
            if success
            else "Falha ao banir. Verifique as permissões do bot."
        )
    )


async def unban_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /unban <user_id>"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "user_id inválido."
        )
        return

    success = await unban_user_safe(
        context,
        update.effective_chat.id,
        target_id,
    )
    rt = runtime(context)
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target_id,
        category="manual_unban",
        severity=Severity.INFO,
        source="admin",
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=target_id,
        action_type="unban",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=success,
    )
    await update.effective_message.reply_text(
        (
            f"✅ Usuário {target_id} desbanido."
            if success
            else "Falha ao desbanir. Verifique o ID e permissões."
        )
    )


async def report_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    replied = update.effective_message.reply_to_message
    target = replied.from_user if replied else None
    if not target:
        await update.effective_message.reply_text(
            "Responda à mensagem que deseja denunciar com /report [motivo]."
        )
        return

    reason = " ".join(context.args).strip() or "user_report"
    incident_id = runtime(context).db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="user_report",
        severity=Severity.LOW,
        source="community",
        evidence={
            "reported_message_id": replied.message_id,
            "reporter_user_id": update.effective_user.id,
        },
        note=reason[:500],
    )
    await update.effective_message.reply_text(
        f"🛡️ Denúncia registrada: {incident_id[:8]}. Um administrador pode revisar."
    )


async def schedule_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Use: /schedule 2026-09-20T15:00:00-03:00 mensagem"
        )
        return

    try:
        when = datetime.fromisoformat(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "Data inválida. Use ISO 8601 com fuso, ex.: 2026-09-20T15:00:00-03:00"
        )
        return

    if when.tzinfo is None:
        await update.effective_message.reply_text(
            "Informe o fuso horário explicitamente, ex.: -03:00."
        )
        return

    send_at = when.timestamp()
    if send_at <= time.time():
        await update.effective_message.reply_text(
            "O horário precisa estar no futuro."
        )
        return

    text = " ".join(context.args[1:]).strip()
    if not text:
        return

    schedule_id = runtime(context).db.schedule_message(
        chat_id=update.effective_chat.id,
        send_at=send_at,
        text=text[:3500],
        created_by=update.effective_user.id,
    )
    await update.effective_message.reply_text(
        f"📅 Mensagem agendada: {schedule_id[:8]} para {when.isoformat()}."
    )


async def reload_knowledge_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message:
        return

    count = runtime(context).knowledge.reload()
    await update.effective_message.reply_text(
        f"Knowledge base recarregada: {count} blocos."
    )


async def welcome_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message or not update.effective_chat:
        return

    rt = runtime(context)
    chat_id = update.effective_chat.id

    for member in update.effective_message.new_chat_members:
        if member.is_bot:
            continue

        rt.db.upsert_user(
            chat_id=chat_id,
            user_id=member.id,
            username=member.username,
            first_name=member.first_name,
            language_code=member.language_code,
        )
        rt.db.record_user_event(
            chat_id,
            member.id,
            "joined",
        )

        await update.effective_message.reply_text(
            f"⚡ Bem-vindo(a), {member.first_name or 'novo membro'}.\n\n"
            "Você entrou na comunidade Z-SWAP. Leia /rules.\n"
            "Nunca compartilhe seed phrase, chave privada, senha ou token."
        )

    now = time.time()
    joins = rt.db.count_user_events(
        chat_id=chat_id,
        event_type="joined",
        since=now - rt.settings.raid_window_seconds,
    )

    if (
        joins >= rt.settings.raid_max_joins
        and rt.db.get_operating_state() == OperatingState.NORMAL
    ):
        expires_at = now + rt.settings.raid_elevated_seconds
        rt.db.set_operating_state(OperatingState.ELEVATED)
        rt.db.set_setting(
            "operating_state_expires_at",
            str(expires_at),
        )

        incident_id = rt.db.create_incident(
            chat_id=chat_id,
            user_id=None,
            category="mass_join_detected",
            severity=Severity.HIGH,
            source="guardian",
            evidence={
                "joins": joins,
                "window_seconds": rt.settings.raid_window_seconds,
                "temporary_state": OperatingState.ELEVATED.value,
                "expires_at": expires_at,
            },
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat_id,
            user_id=None,
            action_type="state_change",
            actor_type="guardian",
            actor_id=None,
            reason="mass_join_detected",
            success=True,
            metadata={
                "state": OperatingState.ELEVATED.value,
                "expires_at": expires_at,
            },
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🛡️ ZION: volume anormal de entradas detectado.\n"
                "Estado ELEVATED ativado temporariamente.\n"
                "O limite de flood foi endurecido; nenhuma punição "
                "por IA foi habilitada."
            ),
        )


async def _observe_with_ai(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    user_id: int,
    text: str,
) -> None:
    rt = runtime(context)
    result = await rt.ai.classify(
        chat_id=chat_id,
        user_id=user_id,
        text=text,
    )
    if not result:
        return

    # A IA nunca pune. Apenas abre incidente para revisão humana
    # quando a própria classificação pede revisão ou aponta alto risco.
    if result.requires_human or result.risk >= 0.80:
        rt.db.create_incident(
            chat_id=chat_id,
            user_id=user_id,
            category=f"ai_observe:{result.category}",
            severity=(
                Severity.HIGH
                if result.risk >= 0.90
                else Severity.MEDIUM
            ),
            source="mistral_observe",
            evidence={
                "category": result.category,
                "risk": result.risk,
                "requires_human": result.requires_human,
                "language": result.language,
            },
            note=(
                "Observe-only: nenhuma ação punitiva automática "
                "foi executada pela IA."
            ),
        )


async def _enforce_flood(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flood: FloodDecision,
) -> None:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    user = update.effective_user
    chat = update.effective_chat
    rt = runtime(context)

    deleted_count = 0
    for message_id in flood.message_ids:
        if await delete_message_safe(context, chat.id, message_id):
            deleted_count += 1

    incident_id = rt.db.create_incident(
        chat_id=chat.id,
        user_id=user.id,
        category="flood",
        severity=(
            Severity.HIGH
            if flood.should_ban
            else Severity.MEDIUM
        ),
        source="guardian",
        evidence={
            "strike_count": flood.strike_count,
            "tracked_messages": len(flood.message_ids),
            "deleted_messages": deleted_count,
        },
    )

    if flood.should_ban:
        success = await ban_user_safe(context, chat.id, user.id)
        if success:
            rt.db.clear_containment(chat.id, user.id)
        action_type = "ban"
    else:
        success = await mute_user_safe(
            context,
            chat.id,
            user.id,
            flood.mute_seconds,
        )
        action_type = "mute"

    rt.db.record_action(
        incident_id=incident_id,
        chat_id=chat.id,
        user_id=user.id,
        action_type=action_type,
        actor_type="guardian",
        actor_id=None,
        reason="flood",
        success=success,
        metadata={
            "strike_count": flood.strike_count,
            "duration_seconds": flood.mute_seconds,
        },
    )

    if flood.should_ban and success:
        action_text = "banido por reincidência objetiva de flood."
    elif flood.should_ban:
        # Se o ban falhar, aplicamos contenção/mute como fallback.
        rt.db.set_containment(
            chat.id,
            user.id,
            time.time() + flood.mute_seconds,
            "flood_ban_fallback",
        )
        await mute_user_safe(
            context,
            chat.id,
            user.id,
            flood.mute_seconds,
        )
        action_text = (
            "ban automático falhou; contenção preventiva aplicada."
        )
    else:
        action_text = (
            f"silenciado por {format_duration(flood.mute_seconds)}."
        )

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"⚠️ {user_display_name(user)}: flood detectado.\n"
                f"{deleted_count} mensagens removidas.\n"
                f"Ocorrência {flood.strike_count}/"
                f"{rt.settings.flood_ban_after_strikes}.\n"
                f"{action_text}"
            ),
        )
    except Exception as exc:
        logger.warning("Falha ao publicar aviso de flood: %s", exc)


async def command_guard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Apply flood/containment/lockdown to commands too.

    Without this preflight, a user could bypass anti-flood by sending
    repeated Telegram commands, because normal moderation excludes commands.
    """
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    rt = runtime(context)

    record_user(update, context, increment_messages=True)

    if await is_admin(update, context):
        return

    if rt.db.get_operating_state() == OperatingState.LOCKDOWN:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        rt.db.record_action(
            incident_id=None,
            chat_id=chat.id,
            user_id=user.id,
            action_type="delete",
            actor_type="guardian",
            actor_id=None,
            reason="lockdown_command",
            success=deleted,
        )
        raise ApplicationHandlerStop

    if rt.guardian.containment_remaining(chat.id, user.id) > 0:
        await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        raise ApplicationHandlerStop

    flood = rt.guardian.record_message(
        chat_id=chat.id,
        user_id=user.id,
        message_id=message.message_id,
    )
    if flood.triggered:
        await _enforce_flood(update, context, flood)
        raise ApplicationHandlerStop


async def moderation_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    rt = runtime(context)

    record_user(update, context, increment_messages=True)

    admin = await is_admin(update, context)

    if rt.db.get_operating_state() == OperatingState.LOCKDOWN and not admin:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        rt.db.record_action(
            incident_id=None,
            chat_id=chat.id,
            user_id=user.id,
            action_type="delete",
            actor_type="guardian",
            actor_id=None,
            reason="lockdown",
            success=deleted,
        )
        return

    if admin:
        return

    remaining = rt.guardian.containment_remaining(chat.id, user.id)
    if remaining > 0:
        await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        return

    flood = rt.guardian.record_message(
        chat_id=chat.id,
        user_id=user.id,
        message_id=message.message_id,
    )

    if flood.triggered:
        await _enforce_flood(update, context, flood)
        return

    text = message.text or message.caption or ""

    sensitive = rt.guardian.sensitive_content(text)
    if sensitive.detected:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        incident_id = rt.db.create_incident(
            chat_id=chat.id,
            user_id=user.id,
            category=sensitive.kind,
            severity=Severity.CRITICAL,
            source="guardian",
            evidence={
                "message_id": message.message_id,
                "content_not_stored": True,
            },
            note=sensitive.reason,
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat.id,
            user_id=user.id,
            action_type="delete",
            actor_type="guardian",
            actor_id=None,
            reason=sensitive.kind,
            success=deleted,
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"🚨 {user_display_name(user)}: mensagem removida por "
                "possível exposição de segredo de carteira. "
                "Nunca publique seed phrase ou chave privada."
            ),
        )
        return

    links = rt.guardian.evaluate_links(text)
    if links.should_delete:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        incident_id = rt.db.create_incident(
            chat_id=chat.id,
            user_id=user.id,
            category="unauthorized_link",
            severity=Severity.LOW,
            source="guardian",
            evidence={
                "domains": links.unauthorized_domains,
                "message_id": message.message_id,
            },
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat.id,
            user_id=user.id,
            action_type="delete",
            actor_type="guardian",
            actor_id=None,
            reason="unauthorized_link",
            success=deleted,
            metadata={"domains": links.unauthorized_domains},
        )
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"⚠️ {user_display_name(user)}: "
                    "link/domínio não autorizado."
                ),
            )
        except Exception:
            pass
        return

    if (
        rt.settings.ai_observe
        and rt.ai.enabled
        and len(text.strip()) >= rt.settings.ai_min_observe_chars
    ):
        context.application.create_task(
            _observe_with_ai(
                context,
                chat_id=chat.id,
                user_id=user.id,
                text=text[:6000],
            ),
            update=update,
        )


def expire_temporary_state(rt: Runtime) -> None:
    raw = rt.db.get_setting("operating_state_expires_at")
    if not raw:
        return

    try:
        expires_at = float(raw)
    except ValueError:
        rt.db.set_setting("operating_state_expires_at", "0")
        return

    if expires_at <= 0 or time.time() < expires_at:
        return

    if rt.db.get_operating_state() == OperatingState.ELEVATED:
        rt.db.set_operating_state(OperatingState.NORMAL)
        rt.db.record_action(
            incident_id=None,
            chat_id=None,
            user_id=None,
            action_type="state_change",
            actor_type="guardian",
            actor_id=None,
            reason="temporary_elevated_expired",
            success=True,
        )

    rt.db.set_setting("operating_state_expires_at", "0")


async def scheduler_loop(application: Application) -> None:
    while True:
        try:
            rt = application.bot_data.get("zion_runtime")
            if not isinstance(rt, Runtime):
                await asyncio.sleep(10)
                continue

            expire_temporary_state(rt)

            state = rt.db.get_operating_state()
            due = (
                rt.db.due_scheduled_messages(limit=20)
                if state in {
                    OperatingState.NORMAL,
                    OperatingState.ELEVATED,
                }
                else []
            )
            for item in due:
                success = False
                try:
                    await application.bot.send_message(
                        chat_id=int(item["chat_id"]),
                        text=str(item["text"]),
                    )
                    success = True
                except Exception as exc:
                    logger.warning(
                        "Falha ao enviar agendamento %s: %s",
                        item["id"],
                        exc,
                    )
                rt.db.mark_scheduled_message(
                    str(item["id"]),
                    success=success,
                )

            await asyncio.sleep(20)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no scheduler do ZION.")
            await asyncio.sleep(20)


async def post_init(application: Application) -> None:
    task = asyncio.create_task(
        scheduler_loop(application),
        name="zion-scheduler",
    )
    application.bot_data["zion_scheduler_task"] = task
    logger.info("ZION scheduler iniciado.")


async def post_shutdown(application: Application) -> None:
    task = application.bot_data.get("zion_scheduler_task")
    if isinstance(task, asyncio.Task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    rt = application.bot_data.get("zion_runtime")
    if isinstance(rt, Runtime):
        rt.db.close()


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    error = context.error
    if error is None:
        logger.error("Erro não tratado no ZION sem exceção associada.")
        return

    logger.error(
        "Erro não tratado no ZION: %s",
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )


def build_application(settings: Settings | None = None) -> Application:
    settings = settings or Settings.from_env()

    configure_logging(settings.log_path)

    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado.")

    rt = Runtime(settings)

    app = (
        Application.builder()
        .token(settings.telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["zion_runtime"] = rt

    commands = {
        "start": start_command,
        "status": status_command,
        "health": health_command,
        "guardian": guardian_command,
        "rules": rules_command,
        "id": id_command,
        "ask": ask_command,
        "summary": summary_command,
        "translate": translate_command,
        "help": help_command,
        "aistatus": ai_status_command,
        "stats": stats_command,
        "gaps": gaps_command,
        "resolvegap": resolve_gap_command,
        "incidents": incidents_command,
        "incident": incident_command,
        "resolveincident": resolve_incident_command,
        "strikes": strikes_command,
        "user": user_command,
        "state": state_command,
        "lockdown": lockdown_command,
        "unlock": unlock_command,
        "allowdomain": allow_domain_command,
        "blockdomain": block_domain_command,
        "warn": warn_command,
        "mute": mute_command,
        "ban": ban_command,
        "unban": unban_command,
        "report": report_command,
        "schedule": schedule_command,
        "reloadkb": reload_knowledge_command,
    }

    # Group -1 runs before command handlers. This closes the
    # command-flood bypass while still allowing valid commands in group 0.
    app.add_handler(
        MessageHandler(filters.COMMAND, command_guard_handler),
        group=-1,
    )

    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_handler,
        )
    )
    app.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.PHOTO
                | filters.VIDEO
                | filters.Document.ALL
            )
            & ~filters.COMMAND,
            moderation_handler,
        )
    )
    app.add_error_handler(error_handler)
    return app


def main() -> None:
    settings = Settings.from_env()
    app = build_application(settings)
    logger.info(
        "ZION iniciado | db=sqlite | ai_provider=mistral | ai_enabled=%s | observe=%s",
        settings.ai_enabled,
        settings.ai_observe,
    )
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
