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
from .guardian import Guardian, normalize_policy_domain
from .health import HealthService
from .knowledge import KnowledgeBase
from .logging_safe import (
    configure_logging,
    contains_high_confidence_credential,
)
from .migrate import migrate_legacy_guardian_state
from .models import FloodDecision, OperatingState, Severity
from .process_lock import ProcessLock


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
        self._closed = False
        self.process_lock = ProcessLock(settings.runtime_lock_path)
        try:
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
            self.observe_limiter = AskRateLimiter(
                settings.ai_user_requests_per_minute
            )
            self.admin_cache: dict[
                tuple[int, int],
                tuple[bool, float],
            ] = {}
            self.update_lags: deque[float] = deque(maxlen=100)
        except Exception:
            db = getattr(self, "db", None)
            if isinstance(db, ZionDB):
                db.close()
            self.process_lock.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.db.close()
        finally:
            self.process_lock.close()


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


def telegram_entity_domains(message: Any) -> list[str]:
    domains: list[str] = []

    entity_sets = (
        (
            getattr(message, "entities", None) or [],
            getattr(message, "parse_entity", None),
        ),
        (
            getattr(message, "caption_entities", None) or [],
            getattr(message, "parse_caption_entity", None),
        ),
    )

    for entities, parser in entity_sets:
        for entity in entities:
            entity_type = getattr(entity, "type", "")
            entity_type = getattr(entity_type, "value", entity_type)

            candidate = None
            if entity_type == "text_link":
                candidate = getattr(entity, "url", None)
            elif entity_type == "url" and callable(parser):
                try:
                    candidate = parser(entity)
                except Exception:
                    candidate = None

            if not candidate:
                continue

            domain = normalize_policy_domain(str(candidate))
            if domain and domain not in domains:
                domains.append(domain)

    return domains


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


def is_operator(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not update.effective_user:
        return False

    return (
        update.effective_user.id
        in runtime(context).settings.admin_user_ids
    )


async def require_operator(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if is_operator(update, context):
        return True

    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Comando restrito aos operadores explícitos do ZION."
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


def record_update_lag(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if not message:
        return
    date = getattr(message, "date", None)
    if date is None:
        return
    try:
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        lag = max(
            0.0,
            (datetime.now(timezone.utc) - date).total_seconds(),
        )
    except Exception:
        return
    runtime(context).update_lags.append(lag)


def update_lag_stats(rt: Runtime) -> tuple[float, float]:
    values = sorted(rt.update_lags)
    if not values:
        return 0.0, 0.0
    latest = float(rt.update_lags[-1])
    index = min(
        len(values) - 1,
        max(0, ((95 * len(values) + 99) // 100) - 1),
    )
    return latest, float(values[index])


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


async def protect_credential_exposure(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    source: str,
    notice_text: str,
    source_message_id: int | None = None,
    source_user_id: int | None = None,
) -> bool:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
        or not contains_high_confidence_credential(text)
    ):
        return False

    rt = runtime(context)
    message_id_to_delete = (
        source_message_id
        if source_message_id is not None
        else update.effective_message.message_id
    )
    user_id = (
        source_user_id
        if source_user_id is not None
        else update.effective_user.id
    )

    deleted = await delete_message_safe(
        context,
        update.effective_chat.id,
        message_id_to_delete,
    )
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        category="possible_credential_exposure",
        severity=Severity.CRITICAL,
        source=source,
        evidence={
            "message_id": message_id_to_delete,
            "content_not_stored": True,
        },
        note=(
            "Possível credencial de alta confiança detectada; "
            "o conteúdo sensível não foi persistido."
        ),
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=user_id,
        action_type="delete",
        actor_type="guardian",
        actor_id=None,
        reason="possible_credential_exposure",
        success=deleted,
    )

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=notice_text,
        )
    except Exception as exc:
        logger.warning(
            "Falha ao enviar aviso de possível credencial: %s",
            exc,
        )
    return True


async def protect_wallet_secret(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    source: str,
    notice_text: str,
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
    user_id = (
        source_user_id
        if source_user_id is not None
        else update.effective_user.id
    )

    deleted = await delete_message_safe(
        context,
        update.effective_chat.id,
        message_id_to_delete,
    )
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        category=sensitive.kind,
        severity=Severity.CRITICAL,
        source=source,
        evidence={
            "message_id": message_id_to_delete,
            "content_not_stored": True,
        },
        note=sensitive.reason,
    )
    rt.db.record_action(
        incident_id=incident_id,
        chat_id=update.effective_chat.id,
        user_id=user_id,
        action_type="delete",
        actor_type="guardian",
        actor_id=None,
        reason=sensitive.kind,
        success=deleted,
    )

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=notice_text,
        )
    except Exception as exc:
        logger.warning(
            "Falha ao enviar aviso de segredo de carteira: %s",
            exc,
        )

    return True


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
        "⚡ ZION — Z-SWAP Community OS\n\n"
        "PT-BR\n"
        "Sou o sistema oficial de comunidade da Z-SWAP: segurança, "
        "moderação determinística, suporte e operações.\n"
        "• /help — comandos e suporte\n"
        "• /rules — regras da comunidade\n"
        "• /privacy — privacidade e uso de IA\n"
        "• /ask <pergunta> — base oficial quando a IA estiver habilitada\n\n"
        "Nunca envie seed phrase, chave privada, senha, token ou API key.\n\n"
        "EN\n"
        "I am Z-SWAP's official community system for safety, deterministic "
        "moderation, support and operations.\n"
        "Use /help, /rules and /privacy. Never share a seed phrase, "
        "private key, password, token or API key."
    )


async def rules_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "⚡ Z-SWAP COMMUNITY RULES\n\n"
        "PT-BR\n"
        "1. Respeite os membros da comunidade.\n"
        "2. Sem spam ou flood.\n"
        "3. Sem golpes, phishing ou impersonação.\n"
        "4. Links dependem da política vigente.\n"
        "5. Nunca envie seed phrase, chave privada ou credenciais.\n"
        "6. Administradores nunca pedirão sua seed phrase.\n"
        "7. Críticas, dúvidas e discordâncias são permitidas.\n"
        "8. Casos ambíguos não são punidos automaticamente pela IA.\n\n"
        "EN\n"
        "Be respectful. No spam, flooding, scams, phishing or impersonation. "
        "Links follow the active policy. Never share wallet secrets or "
        "credentials. Criticism and disagreement are allowed. Ambiguous "
        "moderation decisions are not delegated to AI.\n\n"
        "AI may interpret or flag; irreversible automatic moderation "
        "requires deterministic policy."
    )


async def privacy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    rt = runtime(context)
    observe = (
        "ATIVO / ON"
        if rt.settings.ai_observe and rt.ai.enabled
        else "DESATIVADO / OFF"
    )

    await update.effective_message.reply_text(
        "ZION PRIVACY / PRIVACIDADE\n"
        "• Mensagens comuns não são armazenadas integralmente no banco.\n"
        "• Ordinary message bodies are not stored in full.\n"
        "• Metadados operacionais de moderação podem ser registrados.\n"
        "• /ask, /summary e /translate podem enviar conteúdo sanitizado "
        "à Mistral quando a IA estiver habilitada.\n"
        f"• Observe-only de mensagens comuns: {observe}.\n"
        "• Possíveis segredos de carteira são bloqueados antes de chamadas "
        "de IA quando detectados pelo Guardian.\n"
        f"• Lacunas de /ask: retenção de "
        f"{rt.settings.knowledge_gap_retention_days} dias.\n"
        f"• Perguntas de AMA encerrado: retenção de até "
        f"{rt.settings.ama_retention_days} dias.\n"
        "• /ama armazena explicitamente a pergunta para organizar a sessão.\n"
        "Nunca envie / Never send seed phrase, private key, password, "
        "token or API key."
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
    if not await require_operator(update, context):
        return
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
        f"Sensitive Files: "
        f"{'PRIVATE' if snapshot.details.get('sensitive_files_private') else 'WARNING'}\n"
        f"Disk Free: {snapshot.disk_free_mb} MB\n"
        f"Process Uptime: {uptime}"
    )


async def diagnostics_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    diag = rt.health.diagnostics()
    latest_lag, p95_lag = update_lag_stats(rt)
    latency = diag["ai_latency_24h"]
    pragmas = diag["sqlite_pragmas"]

    disk_state = "LOW" if diag["disk_low"] else "OK"
    lag_state = (
        "WARNING"
        if p95_lag > rt.settings.update_lag_warn_seconds
        else "OK"
    )

    await update.effective_message.reply_text(
        "ZION DIAGNOSTICS\n"
        f"State: {diag['state']}\n"
        f"SQLite quick_check: "
        f"{'OK' if diag['sqlite_integrity_ok'] else 'FAIL'}\n"
        f"Runtime lock: "
        f"{'HELD' if rt.process_lock.acquired else 'MISSING'}\n"
        f"SQLite schema: v{diag['schema_version']}\n"
        f"SQLite journal/FK: "
        f"{pragmas['journal_mode']}/{pragmas['foreign_keys']}\n"
        f"SQLite busy timeout: {pragmas['busy_timeout_ms']} ms\n"
        f"SQLite size: {diag['db_size_mb']} MB\n"
        f"Disk: {disk_state} ({diag['disk_free_mb']} MB free)\n"
        f"Sensitive files: "
        f"{'PRIVATE' if diag['sensitive_files_private'] else 'WARNING'}\n"
        f"Wi-Fi interface: "
        f"{'PRESENT' if diag['wifi_interface_present'] else 'MISSING'}\n"
        f"Telegram update lag latest/p95(100): "
        f"{latest_lag:.2f}s/{p95_lag:.2f}s [{lag_state}]\n"
        f"AI latency 24h avg/p95: "
        f"{latency['avg_ms']}ms/{latency['p95_ms']}ms "
        f"(n={latency['count']})"
    )


async def ai_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    key_state = "configured" if rt.settings.mistral_api_key else "missing"
    used = rt.ai.tokens_used_today()
    budget = rt.settings.ai_daily_token_budget
    budget_text = "unlimited" if budget <= 0 else str(budget)
    circuit_remaining = rt.ai.circuit_remaining_seconds()
    circuit_text = (
        f"OPEN ({circuit_remaining}s)"
        if circuit_remaining > 0
        else "CLOSED"
    )

    await update.effective_message.reply_text(
        "ZION AI\n"
        "Provider: Mistral AI\n"
        f"Model: {rt.settings.mistral_model}\n"
        f"Enabled: {rt.settings.ai_enabled}\n"
        f"API key: {key_state}\n"
        f"Observe-only moderation: {rt.settings.ai_observe}\n"
        f"Circuit breaker: {circuit_text}\n"
        f"Provider failures: {rt.ai.circuit_failures}/"
        f"{rt.settings.ai_circuit_failures}\n"
        f"Tokens today UTC: {used}/{budget_text}\n"
        f"Knowledge chunks: {len(rt.knowledge.chunks)}"
    )


async def protect_sensitive_command_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source_message_id: int | None = None,
    source_user_id: int | None = None,
) -> bool:
    if await protect_credential_exposure(
        update,
        context,
        text,
        source="guardian_ai_input",
        notice_text=(
            "🚨 ZION bloqueou a solicitação porque ela parece conter "
            "uma credencial. Esse conteúdo não foi enviado à Mistral."
        ),
        source_message_id=source_message_id,
        source_user_id=source_user_id,
    ):
        return True

    return await protect_wallet_secret(
        update,
        context,
        text,
        source="guardian_ai_input",
        notice_text=(
            "🚨 ZION bloqueou a solicitação porque ela parece conter "
            "uma seed phrase/chave privada. Esse conteúdo não foi enviado "
            "à Mistral."
        ),
        source_message_id=source_message_id,
        source_user_id=source_user_id,
    )


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
        "ZION COMMANDS / COMANDOS\n\n"
        "COMUNIDADE / COMMUNITY\n"
        "/status — estado público / public status\n"
        "/rules — regras / rules\n"
        "/privacy — privacidade, IA e retenção / privacy, AI and retention\n"
        "/ask <pergunta> — suporte fundamentado na base oficial\n"
        "/summary <texto> — resumo explícito via IA quando habilitada\n"
        "/translate <idioma> <texto> — tradução explícita via IA\n"
        "/report — responda a uma mensagem para denunciar\n"
        "/ama <pergunta> — envia pergunta ao AMA ativo\n\n"
        "A IA nunca recebe autoridade punitiva automática. "
        "Ações irreversíveis dependem de regra determinística ou humano autorizado."
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
    if not await require_operator(update, context):
        return
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
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    stats = rt.db.stats()
    community = rt.db.community_stats()
    await update.effective_message.reply_text(
        "ZION STATS\n"
        f"Users: {stats.get('users', 0)}\n"
        f"Strikes: {stats.get('strikes', 0)}\n"
        f"Incidents: {stats.get('incidents', 0)}\n"
        f"Actions: {stats.get('actions', 0)}\n"
        f"AI Events: {stats.get('ai_events', 0)}\n"
        f"Knowledge Gaps: {stats.get('knowledge_gaps', 0)}\n"
        f"Pending scheduled: {community['pending_scheduled']}\n"
        f"Failed scheduled: {community['failed_scheduled']}\n"
        f"Active recurring: {community['active_recurring']}\n"
        f"Paused recurring: {community['paused_recurring']}\n"
        f"Open AMAs: {community['open_amas']}\n"
        f"Pending AMA questions: {community['pending_ama_questions']}"
    )


async def gaps_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
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
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /allowdomain example.com"
        )
        return

    domain = normalize_policy_domain(context.args[0])
    if not domain:
        await update.effective_message.reply_text(
            "Domínio inválido. Exemplo: example.com"
        )
        return

    runtime(context).db.set_domain(domain, "allow", "operator")
    await update.effective_message.reply_text(
        f"Domínio permitido: {domain}"
    )


async def block_domain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Use: /blockdomain example.com"
        )
        return

    domain = normalize_policy_domain(context.args[0])
    if not domain:
        await update.effective_message.reply_text(
            "Domínio inválido. Exemplo: example.com"
        )
        return

    runtime(context).db.set_domain(domain, "block", "operator")
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


async def brief_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    since = time.time() - 86400
    metrics = rt.db.operational_stats_since(since)
    community = rt.db.community_stats()
    tokens = rt.ai.tokens_used_today()
    diag = rt.health.diagnostics()

    await update.effective_message.reply_text(
        "ZION 24H BRIEF\n"
        f"State: {rt.db.get_operating_state().value}\n"
        f"New users: {metrics['new_users']}\n"
        f"Strikes: {metrics['strikes']}\n"
        f"Incidents: {metrics['incidents']}\n"
        f"Open incidents: {metrics['open_incidents']}\n"
        f"Actions: {metrics['actions']}\n"
        f"AI events: {metrics['ai_events']}\n"
        f"Mistral tokens today UTC: {tokens}\n"
        f"Scheduled failed: {community['failed_scheduled']}\n"
        f"Active / paused recurring: "
        f"{community['active_recurring']}/{community['paused_recurring']}\n"
        f"Open AMAs / pending questions: "
        f"{community['open_amas']}/{community['pending_ama_questions']}\n"
        f"SQLite integrity: "
        f"{'OK' if diag['sqlite_integrity_ok'] else 'FAIL'}\n"
        f"Disk free: {diag['disk_free_mb']} MB"
    )


async def announce_command(
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

    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text(
            "Use: /announce <mensagem>"
        )
        return

    success = False
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text[:3900],
        )
        success = True
    finally:
        runtime(context).db.record_action(
            incident_id=None,
            chat_id=update.effective_chat.id,
            user_id=None,
            action_type="announce",
            actor_type="admin",
            actor_id=str(update.effective_user.id),
            reason="manual_admin_command",
            success=success,
            metadata={"length": len(text)},
        )


async def poll_command(
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

    raw = " ".join(context.args).strip()
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) < 3:
        await update.effective_message.reply_text(
            "Use: /poll Pergunta | Opção 1 | Opção 2 [| Opção 3 ...]"
        )
        return

    question = parts[0][:280]
    options = [value[:100] for value in parts[1:11]]

    success = False
    try:
        await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question,
            options=options,
            is_anonymous=False,
        )
        success = True
    finally:
        runtime(context).db.record_action(
            incident_id=None,
            chat_id=update.effective_chat.id,
            user_id=None,
            action_type="poll",
            actor_type="admin",
            actor_id=str(update.effective_user.id),
            reason="manual_admin_command",
            success=success,
            metadata={"options_count": len(options)},
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


async def recurring_command(
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

    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "Use: /recurring 24h 2026-09-20T15:00:00-03:00 mensagem"
        )
        return

    interval = parse_duration(context.args[0])
    if interval is None or interval < 300:
        await update.effective_message.reply_text(
            "Intervalo inválido. Use 5m até 30d."
        )
        return

    try:
        first = datetime.fromisoformat(context.args[1])
    except ValueError:
        await update.effective_message.reply_text(
            "Data inválida. Use ISO 8601 com fuso."
        )
        return

    if first.tzinfo is None or first.timestamp() <= time.time():
        await update.effective_message.reply_text(
            "Informe horário futuro com fuso explícito."
        )
        return

    text = " ".join(context.args[2:]).strip()
    if not text:
        return

    schedule_id = runtime(context).db.schedule_recurring_message(
        chat_id=update.effective_chat.id,
        first_send_at=first.timestamp(),
        interval_seconds=interval,
        text=text,
        created_by=update.effective_user.id,
    )
    runtime(context).db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id,
        user_id=None,
        action_type="recurring_schedule",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=True,
        metadata={
            "schedule_id": schedule_id,
            "interval_seconds": interval,
        },
    )
    await update.effective_message.reply_text(
        f"🔁 Recorrência criada: {schedule_id[:8]} | "
        f"primeiro envio {first.isoformat()} | "
        f"intervalo {format_duration(interval)}."
    )


async def cancel_recurring_command(
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
            "Use: /cancelrecurring <id-ou-prefixo>"
        )
        return

    schedule_ref = context.args[0].strip()
    rt = runtime(context)
    success = rt.db.cancel_recurring_message(
        schedule_ref,
        chat_id=update.effective_chat.id,
    )
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id,
        user_id=None,
        action_type="recurring_cancel",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=success,
        metadata={"schedule_ref": schedule_ref[:32]},
    )
    await update.effective_message.reply_text(
        "Recorrência cancelada."
        if success
        else "Recorrência ativa não encontrada ou prefixo ambíguo."
    )


async def jobs_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    scheduled = rt.db.list_scheduled_messages(limit=8)
    recurring = rt.db.list_recurring_messages(limit=8)

    lines = ["ZION DELIVERY JOBS", "", "ONE-SHOT"]
    if not scheduled:
        lines.append("none")
    for item in scheduled:
        lines.append(
            f"{str(item['id'])[:8]} | {item['status']} | "
            f"chat={item['chat_id']} | attempts={item['attempts']}"
        )

    lines.extend(["", "RECURRING"])
    if not recurring:
        lines.append("none")
    for item in recurring:
        lines.append(
            f"{str(item['id'])[:8]} | {item['status']} | "
            f"chat={item['chat_id']} | "
            f"failures={item['consecutive_failures']}"
        )

    await update.effective_message.reply_text(
        "\n".join(lines)[:3900]
    )


async def retry_scheduled_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message or not context.args:
        await update.effective_message.reply_text(
            "Use: /retryscheduled <id-ou-prefixo>"
        )
        return

    reference = context.args[0].strip()
    rt = runtime(context)
    success = rt.db.retry_scheduled_message(reference)
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=None,
        action_type="scheduled_retry",
        actor_type="operator",
        actor_id=(
            str(update.effective_user.id)
            if update.effective_user
            else None
        ),
        reason="manual_operator_command",
        success=success,
        metadata={"schedule_ref": reference[:32]},
    )
    await update.effective_message.reply_text(
        "Agendamento reenfileirado."
        if success
        else "Agendamento falho não encontrado ou prefixo ambíguo."
    )


async def resume_recurring_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message or not context.args:
        await update.effective_message.reply_text(
            "Use: /resumerecurring <id-ou-prefixo>"
        )
        return

    reference = context.args[0].strip()
    rt = runtime(context)
    success = rt.db.resume_recurring_message(reference)
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        user_id=None,
        action_type="recurring_resume",
        actor_type="operator",
        actor_id=(
            str(update.effective_user.id)
            if update.effective_user
            else None
        ),
        reason="manual_operator_command",
        success=success,
        metadata={"schedule_ref": reference[:32]},
    )
    await update.effective_message.reply_text(
        "Recorrência retomada."
        if success
        else "Recorrência pausada não encontrada ou prefixo ambíguo."
    )


async def ama_open_command(
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

    title = " ".join(context.args).strip()
    if not title:
        await update.effective_message.reply_text(
            "Use: /amaopen <tema do AMA>"
        )
        return

    rt = runtime(context)
    active = rt.db.active_ama(update.effective_chat.id)
    if active:
        await update.effective_message.reply_text(
            "Já existe um AMA aberto neste chat. "
            "Use /amaclose antes de abrir outro."
        )
        return

    ama_id = rt.db.create_ama(
        chat_id=update.effective_chat.id,
        title=title,
        created_by=update.effective_user.id,
    )
    rt.db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id,
        user_id=None,
        action_type="ama_open",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=True,
        metadata={"ama_id": ama_id},
    )
    await update.effective_message.reply_text(
        f"🎙️ AMA aberto: {title[:200]}\n"
        "Envie perguntas com /ama <pergunta>. "
        "As perguntas ficam armazenadas temporariamente para organização do AMA."
    )


async def ama_question_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not update.effective_message
        or not update.effective_chat
        or not update.effective_user
    ):
        return

    question = " ".join(context.args).strip()
    if not question:
        await update.effective_message.reply_text(
            "Use: /ama <pergunta>"
        )
        return

    if await protect_sensitive_command_input(
        update,
        context,
        question,
    ):
        return

    rt = runtime(context)
    active = rt.db.active_ama(update.effective_chat.id)
    if not active:
        await update.effective_message.reply_text(
            "Não há AMA aberto neste chat."
        )
        return

    question_id = rt.db.add_ama_question(
        ama_id=str(active["id"]),
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        question=question,
    )
    await update.effective_message.reply_text(
        f"🎙️ Pergunta registrada no AMA ({question_id[:8]})."
    )


async def ama_list_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_admin(update, context):
        return
    if not update.effective_message or not update.effective_chat:
        return

    rt = runtime(context)
    active = rt.db.active_ama(update.effective_chat.id)
    if not active:
        await update.effective_message.reply_text(
            "Não há AMA aberto neste chat."
        )
        return

    questions = rt.db.list_ama_questions(str(active["id"]), limit=30)
    lines = [
        f"🎙️ AMA: {active['title']}",
        f"ID: {str(active['id'])[:8]}",
        f"Perguntas: {len(questions)}",
    ]
    for item in questions:
        lines.append(
            f"{str(item['id'])[:8]} | user={item['user_id']} | "
            f"{str(item['question'])[:220]}"
        )
    await update.effective_message.reply_text(
        "\n".join(lines)[:3900]
    )


async def ama_close_command(
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

    closed = runtime(context).db.close_ama(update.effective_chat.id)
    if not closed:
        await update.effective_message.reply_text(
            "Não há AMA aberto neste chat."
        )
        return

    runtime(context).db.record_action(
        incident_id=None,
        chat_id=update.effective_chat.id,
        user_id=None,
        action_type="ama_close",
        actor_type="admin",
        actor_id=str(update.effective_user.id),
        reason="manual_admin_command",
        success=True,
        metadata={"ama_id": str(closed["id"])},
    )
    await update.effective_message.reply_text(
        f"🎙️ AMA encerrado: {closed['title']}"
    )


async def reload_knowledge_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
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
    record_update_lag(update, context)
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
            f"⚡ Bem-vindo(a) / Welcome, "
            f"{member.first_name or 'novo membro'}!\n\n"
            "PT-BR: Você entrou na comunidade Z-SWAP. "
            "Leia /rules, consulte /help e use /report para sinalizar problemas.\n"
            "EN: Welcome to the Z-SWAP community. "
            "Read /rules, check /help and use /report to flag issues.\n\n"
            "🔐 Nunca compartilhe / Never share seed phrase, private key, "
            "password, token or API key."
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


async def _evaluate_chat_burst(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    user_id: int,
) -> float:
    rt = runtime(context)
    now = time.time()
    burst = rt.guardian.evaluate_chat_burst(
        chat_id,
        user_id=user_id,
        now=now,
    )
    if burst.triggered:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🛡️ ZION: pico distribuído de mensagens detectado.\n"
                    f"{burst.message_count} mensagens de "
                    f"{burst.unique_users} usuários em "
                    f"{burst.window_seconds}s.\n"
                    "Estado ELEVATED ativado temporariamente. "
                    "Nenhum usuário foi punido apenas por este gatilho."
                ),
            )
        except Exception as exc:
            logger.warning(
                "Falha ao publicar alerta de chat burst: %s",
                exc,
            )
    return now


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
        # Se o ban falhar, aplicamos contenção/mute como fallback
        # e registramos a segunda ação separadamente no ledger.
        rt.db.set_containment(
            chat.id,
            user.id,
            time.time() + flood.mute_seconds,
            "flood_ban_fallback",
        )
        fallback_success = await mute_user_safe(
            context,
            chat.id,
            user.id,
            flood.mute_seconds,
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat.id,
            user_id=user.id,
            action_type="mute",
            actor_type="guardian",
            actor_id=None,
            reason="flood_ban_fallback",
            success=fallback_success,
            metadata={
                "duration_seconds": flood.mute_seconds,
            },
        )
        action_text = (
            "ban automático falhou; "
            + (
                "mute/contenção de fallback aplicado."
                if fallback_success
                else "contenção local mantida; mute de fallback falhou."
            )
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
    """Apply universal secret protection and deterministic command policy."""
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
    record_update_lag(update, context)

    record_user(update, context, increment_messages=True)

    text = message.text or message.caption or ""
    if await protect_credential_exposure(
        update,
        context,
        text,
        source="guardian_command_preflight",
        notice_text=(
            "🚨 ZION bloqueou um comando que aparentava conter "
            "uma credencial. O conteúdo não foi processado."
        ),
    ):
        raise ApplicationHandlerStop

    if await protect_wallet_secret(
        update,
        context,
        text,
        source="guardian_command_preflight",
        notice_text=(
            "🚨 ZION bloqueou um comando que aparentava conter "
            "segredo de carteira. O conteúdo não foi processado."
        ),
    ):
        raise ApplicationHandlerStop

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

    activity_now = await _evaluate_chat_burst(
        context,
        chat_id=chat.id,
        user_id=user.id,
    )
    flood = rt.guardian.record_message(
        chat_id=chat.id,
        user_id=user.id,
        message_id=message.message_id,
        now=activity_now,
    )
    if flood.triggered:
        await _enforce_flood(update, context, flood)
        raise ApplicationHandlerStop

    links = rt.guardian.evaluate_links(
        text,
        extra_domains=telegram_entity_domains(message),
    )
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
            source="guardian_command_preflight",
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
    record_update_lag(update, context)

    record_user(update, context, increment_messages=True)

    # Segredos são protegidos para TODOS, inclusive administradores.
    # Admin não deve perder esta camada por causa da isenção de moderação.
    text = message.text or message.caption or ""
    if await protect_credential_exposure(
        update,
        context,
        text,
        source="guardian",
        notice_text=(
            f"🚨 {user_display_name(user)}: mensagem removida por "
            "possível exposição de credencial. Revogue/rotacione a "
            "credencial caso ela seja real."
        ),
    ):
        return

    if await protect_wallet_secret(
        update,
        context,
        text,
        source="guardian",
        notice_text=(
            f"🚨 {user_display_name(user)}: mensagem removida por "
            "possível exposição de segredo de carteira. "
            "Nunca publique seed phrase ou chave privada."
        ),
    ):
        return

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

    # Administradores continuam isentos de flood e política de links,
    # mas somente depois da proteção universal de segredos.
    if admin:
        return

    remaining = rt.guardian.containment_remaining(chat.id, user.id)
    if remaining > 0:
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
            reason="active_containment",
            success=deleted,
            metadata={"remaining_seconds": remaining},
        )
        return

    activity_now = await _evaluate_chat_burst(
        context,
        chat_id=chat.id,
        user_id=user.id,
    )
    flood = rt.guardian.record_message(
        chat_id=chat.id,
        user_id=user.id,
        message_id=message.message_id,
        now=activity_now,
    )
    if flood.triggered:
        await _enforce_flood(update, context, flood)
        return

    links = rt.guardian.evaluate_links(
        text,
        extra_domains=telegram_entity_domains(message),
    )
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
        except Exception as exc:
            logger.warning(
                "Falha ao enviar aviso de link não autorizado: %s",
                exc,
            )
        return

    if (
        rt.settings.ai_observe
        and rt.ai.enabled
        and len(text.strip()) >= rt.settings.ai_min_observe_chars
        and rt.observe_limiter.allow(user.id)
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


async def operational_alert_cycle(
    application: Application,
    rt: Runtime,
) -> None:
    snapshot = rt.health.snapshot()
    diagnostics = rt.health.diagnostics()
    pragmas = diagnostics["sqlite_pragmas"]
    community = rt.db.community_stats()
    _, p95_lag = update_lag_stats(rt)
    issues: list[str] = []

    if not snapshot.db_ok:
        issues.append("database_or_integrity")
    if pragmas["journal_mode"] != "wal":
        issues.append("sqlite_not_wal")
    if int(pragmas["foreign_keys"]) != 1:
        issues.append("sqlite_foreign_keys_off")
    if community["failed_scheduled"] > 0:
        issues.append("scheduled_delivery_failed")
    if community["paused_recurring"] > 0:
        issues.append("recurring_delivery_paused")
    if snapshot.details.get("disk_low"):
        issues.append("disk_low")
    if not snapshot.details.get("sensitive_files_private"):
        issues.append("sensitive_file_permissions")
    if not snapshot.wifi_interface_present:
        issues.append("wifi_interface_missing")
    if (
        rt.update_lags
        and p95_lag > rt.settings.update_lag_warn_seconds
    ):
        issues.append("telegram_update_lag")

    signature = "|".join(sorted(issues)) if issues else "OK"
    previous = rt.db.get_setting("health_alert_signature")

    now = time.time()
    raw_last_sent = rt.db.get_setting("health_alert_last_sent_at") or "0"
    try:
        last_sent_at = float(raw_last_sent)
    except ValueError:
        last_sent_at = 0.0

    if signature == previous:
        if signature == "OK":
            return
        if (
            now - last_sent_at
            < rt.settings.health_alert_repeat_seconds
        ):
            return

    rt.db.set_setting("health_alert_signature", signature)

    if not issues:
        rt.db.set_setting("health_alert_last_sent_at", "0")
        if previous and previous != "OK":
            for operator_id in sorted(rt.settings.admin_user_ids):
                success = False
                try:
                    await application.bot.send_message(
                        chat_id=operator_id,
                        text=(
                            "✅ ZION OPERATIONAL RECOVERY\n"
                            "Os alertas operacionais anteriormente ativos "
                            "não estão mais presentes. "
                            "Use /diagnostics para confirmar."
                        ),
                    )
                    success = True
                except Exception as exc:
                    logger.warning(
                        "Falha ao enviar recuperação para operator=%s: %s",
                        operator_id,
                        exc,
                    )
                rt.db.record_action(
                    incident_id=None,
                    chat_id=operator_id,
                    user_id=None,
                    action_type="operator_recovery",
                    actor_type="health",
                    actor_id=None,
                    reason="operational_health_recovered",
                    success=success,
                    metadata={"previous_signature": previous},
                )
        return

    incident_id = rt.db.create_incident(
        chat_id=None,
        user_id=None,
        category="operational_health_warning",
        severity=(
            Severity.HIGH
            if not snapshot.db_ok
            else Severity.MEDIUM
        ),
        source="health",
        evidence={
            "issues": issues,
            "disk_free_mb": snapshot.disk_free_mb,
            "telegram_update_lag_p95": round(p95_lag, 3),
            "repeat_interval_seconds": (
                rt.settings.health_alert_repeat_seconds
            ),
        },
        note=(
            "Operational alert; no automated destructive action executed."
        ),
    )

    alert_text = (
        "⚠️ ZION OPERATIONAL ALERT\n"
        + "\n".join(f"• {issue}" for issue in issues)
        + "\nUse /diagnostics para detalhes."
    )

    for operator_id in sorted(rt.settings.admin_user_ids):
        success = False
        try:
            await application.bot.send_message(
                chat_id=operator_id,
                text=alert_text,
            )
            success = True
        except Exception as exc:
            logger.warning(
                "Falha ao enviar alerta operacional para operator=%s: %s",
                operator_id,
                exc,
            )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=operator_id,
            user_id=None,
            action_type="operator_alert",
            actor_type="health",
            actor_id=None,
            reason="operational_health_warning",
            success=success,
            metadata={"issues": issues},
        )

    rt.db.set_setting("health_alert_last_sent_at", str(now))


async def scheduler_loop(application: Application) -> None:
    last_housekeeping = 0.0

    while True:
        try:
            rt = application.bot_data.get("zion_runtime")
            if not isinstance(rt, Runtime):
                await asyncio.sleep(10)
                continue

            expire_temporary_state(rt)

            now = time.time()
            if now - last_housekeeping >= 3600:
                gaps_removed = rt.db.prune_knowledge_gaps(
                    now
                    - (
                        rt.settings.knowledge_gap_retention_days
                        * 86400
                    )
                )
                reports_redacted = rt.db.redact_resolved_user_reports(
                    now
                    - (
                        rt.settings.report_retention_days
                        * 86400
                    )
                )
                ama_questions_deleted = rt.db.prune_ama_questions(
                    now - (rt.settings.ama_retention_days * 86400)
                )
                if gaps_removed or reports_redacted or ama_questions_deleted:
                    logger.info(
                        "Housekeeping | knowledge_gaps_deleted=%s | "
                        "resolved_reports_redacted=%s | "
                        "ama_questions_deleted=%s",
                        gaps_removed,
                        reports_redacted,
                        ama_questions_deleted,
                    )
                try:
                    checkpoint = rt.db.checkpoint_wal()
                    if checkpoint["busy"] not in {0, -1}:
                        logger.warning(
                            "SQLite WAL checkpoint busy | frames=%s | "
                            "checkpointed=%s",
                            checkpoint["log_frames"],
                            checkpoint["checkpointed_frames"],
                        )
                except Exception as exc:
                    logger.warning(
                        "Falha no checkpoint passivo SQLite: %s",
                        type(exc).__name__,
                    )

                await operational_alert_cycle(application, rt)
                last_housekeeping = now

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
                error_type: str | None = None
                try:
                    await application.bot.send_message(
                        chat_id=int(item["chat_id"]),
                        text=str(item["text"]),
                    )
                    success = True
                except Exception as exc:
                    error_type = type(exc).__name__
                    logger.warning(
                        "Falha ao enviar agendamento %s: %s",
                        item["id"],
                        error_type,
                    )

                delivery_state = rt.db.mark_scheduled_message(
                    str(item["id"]),
                    success=success,
                    max_attempts=rt.settings.schedule_max_attempts,
                    retry_seconds=rt.settings.schedule_retry_seconds,
                    error_type=error_type,
                )
                rt.db.record_action(
                    incident_id=None,
                    chat_id=int(item["chat_id"]),
                    user_id=None,
                    action_type="scheduled_send",
                    actor_type="scheduler",
                    actor_id=None,
                    reason="scheduled_message_due",
                    success=success,
                    metadata={
                        "schedule_id": str(item["id"]),
                        "delivery_state": delivery_state,
                        "attempt": int(item.get("attempts", 0)) + 1,
                        "error_type": error_type,
                    },
                )

                if delivery_state == "failed":
                    rt.db.create_incident(
                        chat_id=int(item["chat_id"]),
                        user_id=None,
                        category="scheduled_delivery_failed",
                        severity=Severity.MEDIUM,
                        source="scheduler",
                        evidence={
                            "schedule_id": str(item["id"]),
                            "attempts": (
                                int(item.get("attempts", 0)) + 1
                            ),
                            "error_type": error_type,
                        },
                        note=(
                            "One-shot delivery exhausted bounded retries; "
                            "operator can use /retryscheduled."
                        ),
                    )

            recurring_due = (
                rt.db.due_recurring_messages(limit=20)
                if state in {
                    OperatingState.NORMAL,
                    OperatingState.ELEVATED,
                }
                else []
            )
            for item in recurring_due:
                success = False
                error_type: str | None = None
                try:
                    await application.bot.send_message(
                        chat_id=int(item["chat_id"]),
                        text=str(item["text"]),
                    )
                    success = True
                except Exception as exc:
                    error_type = type(exc).__name__
                    logger.warning(
                        "Falha ao enviar recorrência %s: %s",
                        item["id"],
                        error_type,
                    )

                delivery_state = rt.db.advance_recurring_message(
                    str(item["id"]),
                    success=success,
                    max_failures=rt.settings.recurring_max_failures,
                    retry_seconds=rt.settings.schedule_retry_seconds,
                    error_type=error_type,
                )
                rt.db.record_action(
                    incident_id=None,
                    chat_id=int(item["chat_id"]),
                    user_id=None,
                    action_type="recurring_send",
                    actor_type="scheduler",
                    actor_id=None,
                    reason="recurring_message_due",
                    success=success,
                    metadata={
                        "schedule_id": str(item["id"]),
                        "delivery_state": delivery_state,
                        "failure_count": (
                            0
                            if success
                            else int(item.get("consecutive_failures", 0)) + 1
                        ),
                        "error_type": error_type,
                    },
                )

                if delivery_state == "paused":
                    rt.db.create_incident(
                        chat_id=int(item["chat_id"]),
                        user_id=None,
                        category="recurring_delivery_paused",
                        severity=Severity.MEDIUM,
                        source="scheduler",
                        evidence={
                            "schedule_id": str(item["id"]),
                            "consecutive_failures": (
                                int(item.get("consecutive_failures", 0)) + 1
                            ),
                            "error_type": error_type,
                        },
                        note=(
                            "Recurring delivery paused after bounded "
                            "consecutive failures; operator can use "
                            "/resumerecurring."
                        ),
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
        rt.close()


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

    configure_logging(
        settings.log_path,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )

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
        "diagnostics": diagnostics_command,
        "guardian": guardian_command,
        "rules": rules_command,
        "privacy": privacy_command,
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
        "brief": brief_command,
        "announce": announce_command,
        "poll": poll_command,
        "schedule": schedule_command,
        "recurring": recurring_command,
        "cancelrecurring": cancel_recurring_command,
        "jobs": jobs_command,
        "retryscheduled": retry_scheduled_command,
        "resumerecurring": resume_recurring_command,
        "amaopen": ama_open_command,
        "ama": ama_question_command,
        "amalist": ama_list_command,
        "amaclose": ama_close_command,
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
    # Toda mensagem comum entra no Guardian, inclusive sticker,
    # voice, audio, animation e mídia sem legenda. Isso evita bypass
    # do anti-flood por tipos de mensagem não textuais.
    app.add_handler(
        MessageHandler(
            filters.ALL
            & ~filters.COMMAND
            & ~filters.StatusUpdate.ALL,
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
