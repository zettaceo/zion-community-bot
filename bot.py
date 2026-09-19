import os
import re
import time
import logging
from collections import defaultdict, deque

from dotenv import load_dotenv
from telegram import Update
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

URL_REGEX = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+)",
    re.IGNORECASE,
)

DOMAIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?([^/\s]+)",
    re.IGNORECASE,
)

message_history = defaultdict(lambda: deque())

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("zion.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("zion")


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False

    if update.effective_chat.type == "private":
        return True

    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id,
        )

        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }

    except Exception as exc:
        logger.warning("Falha ao verificar admin: %s", exc)
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ZION online.\n\n"
        "Sistema oficial da comunidade Z-SWAP ativo.\n"
        "Use /rules para consultar as regras."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ZION STATUS: ONLINE\n"
        "Community Core: ACTIVE\n"
        "AI Layer: NOT ENABLED"
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚡ Z-SWAP COMMUNITY RULES\n\n"
        "1. Respeite os membros da comunidade.\n"
        "2. Sem spam ou flood.\n"
        "3. Sem golpes, phishing ou impersonação.\n"
        "4. Não compartilhe links sem autorização.\n"
        "5. Nunca envie seed phrase ou chave privada.\n"
        "6. Administradores nunca pedirão sua seed phrase.\n"
        "7. Críticas e dúvidas são permitidas. Ataques e manipulação não.\n\n"
        "ZION monitora a comunidade para reduzir spam e golpes."
    )

    await update.message.reply_text(text)


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Chat ID: {update.effective_chat.id}"
    )


async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            domains.append(match.group(1).lower())

    return domains


def domain_allowed(domain: str) -> bool:
    if not ALLOWED_DOMAINS:
        return False

    for allowed in ALLOWED_DOMAINS:
        if domain == allowed or domain.endswith("." + allowed):
            return True

    return False


async def delete_and_warn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reason: str,
):
    if not update.message:
        return

    user = update.effective_user

    try:
        await update.message.delete()

        logger.warning(
            "Mensagem removida | user=%s | id=%s | motivo=%s",
            user.username or user.first_name,
            user.id,
            reason,
        )

        warning = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ @{user.username or user.first_name}: {reason}",
        )

        # Depois podemos apagar automaticamente esses avisos.

    except Exception as exc:
        logger.error("Falha ao remover mensagem: %s", exc)


async def moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    key = (chat_id_value, user_id)

    history = message_history[key]

    while history and now - history[0] > FLOOD_WINDOW_SECONDS:
        history.popleft()

    history.append(now)

    if len(history) > FLOOD_MAX_MESSAGES:
        await delete_and_warn(
            update,
            context,
            "flood detectado. Aguarde alguns segundos antes de continuar."
        )
        return

    # -----------------------------
    # CONTROLE DE LINKS
    # -----------------------------

    text = update.message.text or update.message.caption or ""

    domains = extract_domains(text)

    if domains:

        if not ALLOW_LINKS:
            await delete_and_warn(
                update,
                context,
                "links ainda não são permitidos para membros."
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
                "esse domínio não está autorizado."
            )
            return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(
        "Erro no ZION:",
        exc_info=context.error,
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não configurado."
        )

    app = Application.builder().token(TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("id", chat_id))

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

    app.add_error_handler(error_handler)

    logger.info("ZION iniciado.")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
