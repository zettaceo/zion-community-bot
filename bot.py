import os
import re
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

ALLOW_LINKS = os.getenv("ALLOW_LINKS", "false").lower() == "true"

ALLOWED_DOMAINS = {
    d.strip().lower()
    for d in os.getenv("ALLOWED_DOMAINS", "").split(",")
    if d.strip()
}

FLOOD_MAX_MESSAGES = int(os.getenv("FLOOD_MAX_MESSAGES", "6"))
FLOOD_WINDOW_SECONDS = int(os.getenv("FLOOD_WINDOW_SECONDS", "10"))

FLOOD_MUTE_LEVELS = [
    int(value.strip())
    for value in os.getenv(
        "FLOOD_MUTE_LEVELS",
        "60,300,900,3600",
    ).split(",")
    if value.strip()
]

FLOOD_STRIKE_RESET_SECONDS = int(
    os.getenv("FLOOD_STRIKE_RESET_SECONDS", "3600")
)

ADMIN_CACHE_SECONDS = int(
    os.getenv("ADMIN_CACHE_SECONDS", "60")
)

URL_REGEX = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+)",
    re.IGNORECASE,
)

DOMAIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?([^/\s]+)",
    re.IGNORECASE,
)

# (chat_id, user_id) -> deque[(timestamp_monotonic, message_id)]
message_history = defaultdict(lambda: deque())

# (chat_id, user_id) -> timestamp_monotonic
# Enquanto estiver bloqueado localmente, toda nova mensagem é apagada.
flood_blocked_until = {}

# (chat_id, user_id) -> (quantidade_de_floods, timestamp_do_ultimo_flood)
flood_strikes = {}

# (chat_id, user_id) -> (eh_admin, timestamp_de_expiracao)
admin_cache = {}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("zion.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("zion")


def user_display_name(user) -> str:
    if user.username:
        return f"@{user.username}"

    if user.first_name:
        return user.first_name

    return f"usuário {user.id}"


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} segundos"

    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "1 hora" if hours == 1 else f"{hours} horas"

    if seconds % 60 == 0:
        minutes = seconds // 60
        return "1 minuto" if minutes == 1 else f"{minutes} minutos"

    return f"{seconds} segundos"


def next_flood_mute_seconds(key: tuple, now: float) -> tuple[int, int]:
    previous_count, last_strike = flood_strikes.get(
        key,
        (0, 0.0),
    )

    if (
        last_strike
        and now - last_strike > FLOOD_STRIKE_RESET_SECONDS
    ):
        previous_count = 0

    strike_count = previous_count + 1

    if FLOOD_MUTE_LEVELS:
        level_index = min(
            strike_count - 1,
            len(FLOOD_MUTE_LEVELS) - 1,
        )
        mute_seconds = FLOOD_MUTE_LEVELS[level_index]
    else:
        mute_seconds = 60

    flood_strikes[key] = (
        strike_count,
        now,
    )

    return mute_seconds, strike_count


async def is_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False

    if update.effective_chat.type == "private":
        return True

    key = (
        update.effective_chat.id,
        update.effective_user.id,
    )

    now = time.monotonic()
    cached = admin_cache.get(key)

    if cached:
        cached_is_admin, expires_at = cached

        if now < expires_at:
            return cached_is_admin

        admin_cache.pop(key, None)

    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id,
        )

        result = member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }

        admin_cache[key] = (
            result,
            now + ADMIN_CACHE_SECONDS,
        )

        return result

    except Exception as exc:
        logger.warning(
            "Falha ao verificar admin: %s",
            exc,
        )
        return False


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "ZION online.\n\n"
        "Sistema oficial da comunidade Z-SWAP ativo.\n"
        "Use /rules para consultar as regras."
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "ZION STATUS: ONLINE\n"
        "Community Core: ACTIVE\n"
        "AI Layer: NOT ENABLED"
    )


async def rules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "⚡ Z-SWAP COMMUNITY RULES\n\n"
        "1. Respeite os membros da comunidade.\n"
        "2. Sem spam ou flood.\n"
        "3. Sem golpes, phishing ou impersonação.\n"
        "4. Não compartilhe links sem autorização.\n"
        "5. Nunca envie seed phrase ou chave privada.\n"
        "6. Administradores nunca pedirão sua seed phrase.\n"
        "7. Críticas e dúvidas são permitidas. "
        "Ataques e manipulação não.\n\n"
        "ZION monitora a comunidade para reduzir spam e golpes."
    )

    await update.message.reply_text(text)


async def chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        f"Chat ID: {update.effective_chat.id}"
    )


async def welcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        name = member.first_name or "novo membro"

        await update.message.reply_text(
            f"⚡ Bem-vindo(a), {name}.\n\n"
            "Você entrou na comunidade Z-SWAP.\n"
            "Leia /rules antes de participar.\n\n"
            "Nunca compartilhe sua seed phrase ou chave privada."
        )

        logger.info(
            "Novo membro | user_id=%s | nome=%s | chat=%s",
            member.id,
            name,
            update.effective_chat.id,
        )


def extract_domains(text: str):
    urls = URL_REGEX.findall(text or "")

    domains = []

    for url in urls:
        match = DOMAIN_REGEX.search(url)

        if match:
            domains.append(
                match.group(1).lower()
            )

    return domains


def domain_allowed(domain: str) -> bool:
    if not ALLOWED_DOMAINS:
        return False

    for allowed in ALLOWED_DOMAINS:
        if (
            domain == allowed
            or domain.endswith("." + allowed)
        ):
            return True

    return False


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
            "Mensagem %s não pôde ser apagada: %s",
            message_id,
            exc,
        )
        return False


async def restrict_user_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    mute_seconds: int,
) -> bool:
    try:
        until_date = (
            datetime.now(timezone.utc)
            + timedelta(seconds=mute_seconds)
        )

        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
            ),
            until_date=until_date,
        )

        return True

    except Exception as exc:
        logger.warning(
            "Não foi possível silenciar user_id=%s "
            "no chat=%s: %s",
            user_id,
            chat_id,
            exc,
        )
        return False


async def delete_and_warn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reason: str,
):
    if (
        not update.message
        or not update.effective_user
    ):
        return

    user = update.effective_user
    display_name = user_display_name(user)

    deleted = await delete_message_safe(
        context=context,
        chat_id=update.effective_chat.id,
        message_id=update.message.message_id,
    )

    logger.warning(
        "Mensagem removida=%s | user=%s | "
        "id=%s | motivo=%s",
        deleted,
        display_name,
        user.id,
        reason,
    )

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"⚠️ {display_name}: {reason}"
            ),
        )

    except Exception as exc:
        logger.error(
            "Falha ao enviar aviso: %s",
            exc,
        )


async def handle_flood(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    history: deque,
    key: tuple,
    now: float,
):
    user = update.effective_user
    chat_id_value = update.effective_chat.id
    display_name = user_display_name(user)

    mute_seconds, strike_count = (
        next_flood_mute_seconds(
            key=key,
            now=now,
        )
    )

    # Ativa a contenção local imediatamente.
    # Mesmo se o Telegram não permitir o mute,
    # as próximas mensagens continuam sendo apagadas.
    flood_blocked_until[key] = (
        now + mute_seconds
    )

    # Primeiro tentamos silenciar no próprio Telegram.
    # Isso interrompe novas mensagens na origem e evita
    # que o bot precise "correr atrás" do spam.
    restricted = await restrict_user_safe(
        context=context,
        chat_id=chat_id_value,
        user_id=user.id,
        mute_seconds=mute_seconds,
    )

    message_ids = [
        message_id
        for _, message_id in history
    ]

    history.clear()

    deleted_count = 0

    for message_id in message_ids:
        if await delete_message_safe(
            context=context,
            chat_id=chat_id_value,
            message_id=message_id,
        ):
            deleted_count += 1

    logger.warning(
        "FLOOD | user=%s | user_id=%s | "
        "chat=%s | strike=%s | mensagens=%s | "
        "removidas=%s | mute=%ss | "
        "telegram_restrict=%s",
        display_name,
        user.id,
        chat_id_value,
        strike_count,
        len(message_ids),
        deleted_count,
        mute_seconds,
        restricted,
    )

    duration_text = format_duration(
        mute_seconds
    )

    try:
        if restricted:
            action_text = (
                f"silenciado por {duration_text}."
            )
        else:
            action_text = (
                "contenção automática ativa por "
                f"{duration_text}."
            )

        await context.bot.send_message(
            chat_id=chat_id_value,
            text=(
                f"⚠️ {display_name}: flood detectado.\n"
                f"{deleted_count} mensagens removidas.\n"
                f"{action_text}"
            ),
        )

    except Exception as exc:
        logger.error(
            "Falha ao enviar aviso de flood: %s",
            exc,
        )


async def moderation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    if not update.effective_user:
        return

    if await is_admin(update, context):
        return

    user_id = update.effective_user.id
    chat_id_value = update.effective_chat.id

    # -----------------------------
    # ANTI-FLOOD
    # -----------------------------

    now = time.monotonic()
    key = (
        chat_id_value,
        user_id,
    )

    blocked_until = flood_blocked_until.get(
        key,
        0,
    )

    if now < blocked_until:
        await delete_message_safe(
            context=context,
            chat_id=chat_id_value,
            message_id=(
                update.message.message_id
            ),
        )

        logger.info(
            "Mensagem removida durante contenção | "
            "user_id=%s | chat=%s",
            user_id,
            chat_id_value,
        )
        return

    if blocked_until:
        flood_blocked_until.pop(
            key,
            None,
        )

    history = message_history[key]

    while (
        history
        and (
            now - history[0][0]
            > FLOOD_WINDOW_SECONDS
        )
    ):
        history.popleft()

    history.append(
        (
            now,
            update.message.message_id,
        )
    )

    if len(history) > FLOOD_MAX_MESSAGES:
        await handle_flood(
            update=update,
            context=context,
            history=history,
            key=key,
            now=now,
        )
        return

    # -----------------------------
    # CONTROLE DE LINKS
    # -----------------------------

    text = (
        update.message.text
        or update.message.caption
        or ""
    )

    domains = extract_domains(text)

    if domains:
        if not ALLOW_LINKS:
            await delete_and_warn(
                update,
                context,
                "links ainda não são permitidos "
                "para membros.",
            )
            return

        unauthorized = [
            domain
            for domain in domains
            if not domain_allowed(domain)
        ]

        if unauthorized:
            await delete_and_warn(
                update,
                context,
                "esse domínio não está autorizado.",
            )
            return


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Erro no ZION:",
        exc_info=context.error,
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não configurado."
        )

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # Comandos
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )
    app.add_handler(
        CommandHandler(
            "status",
            status,
        )
    )
    app.add_handler(
        CommandHandler(
            "rules",
            rules,
        )
    )
    app.add_handler(
        CommandHandler(
            "id",
            chat_id,
        )
    )

    # Entrada de novos membros
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome,
        )
    )

    # Moderação de mensagens
    app.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.PHOTO
                | filters.VIDEO
                | filters.Document.ALL
            )
            & ~filters.COMMAND,
            moderation,
        )
    )

    app.add_error_handler(
        error_handler
    )

    logger.info("ZION iniciado.")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
