"""Operator-only ZION DM capture; never activates a provider or sends to an LLM."""
from __future__ import annotations
import time
from telegram.ext import ApplicationHandlerStop
from .logging_safe import register_sensitive_value
from .secret_store import SecretStore


async def set_kimi_key_command(update, context):
    from .telegram_app import runtime, _explicit_operator, delete_message_safe, _send_secret_status
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user:
        return
    if not _explicit_operator(update, context) or chat.type != 'private':
        await message.reply_text('Use este comando no privado do ZION com uma conta de operador autorizado.')
        return
    rt = runtime(context)
    if context.args:
        register_sensitive_value(' '.join(context.args))
        deleted = await delete_message_safe(context, chat.id, message.message_id)
        await _send_secret_status(context, chat.id,
            'Não envie a chave junto do comando. Use /setkimikey sem argumentos.' if deleted
            else 'Não consegui excluir a mensagem. Exclua-a manualmente. Nada foi armazenado.')
        return
    if rt.kimi_secret_store.status() == SecretStore.UNSAFE:
        await message.reply_text('O cofre Kimi está inseguro. O recebimento está bloqueado.')
        return
    key = (chat.id, user.id)
    rt.mistral_secret_captures.pop(key, None)
    rt.kimi_secret_captures[key] = time.monotonic() + 120
    await message.reply_text(
        'Envie a chave Kimi na próxima mensagem deste privado, em até 120 segundos. '
        'A mensagem será excluída antes da validação e do armazenamento no cofre local. '
        'Ela passa pelo Telegram; a exclusão não garante remoção de todas as cópias do serviço. '
        'Use /cancelkimikey para cancelar. Isso não ativa Kimi nas conversas.')


def _audit(rt, chat_id, user_id, operation):
    rt.db.record_action(incident_id=None, chat_id=chat_id, user_id=user_id,
        action_type='kimi_key_set', actor_type='operator', actor_id=str(user_id),
        reason='private_secret_provisioning', success=True,
        metadata={'secret': 'kimi', 'operation': operation})


async def kimi_secret_capture_handler(update, context):
    from .telegram_app import runtime, delete_message_safe, _send_secret_status
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user or chat.type != 'private':
        return
    rt = runtime(context)
    key = (chat.id, user.id)
    expiry = rt.kimi_secret_captures.get(key)
    if expiry is None or not message.text or message.text.startswith('/'):
        return
    rt.kimi_secret_captures.pop(key, None)
    register_sensitive_value(message.text)
    # Consume even expired/revoked captures: never let a late credential reach
    # generic conversation, telemetry, model input or ordinary message storage.
    deleted = await delete_message_safe(context, chat.id, message.message_id)
    if not deleted:
        await _send_secret_status(context, chat.id,
            'Não consegui excluir a mensagem. Nada foi armazenado. Exclua-a manualmente.')
        raise ApplicationHandlerStop
    if user.id not in rt.settings.admin_user_ids or time.monotonic() > expiry:
        await _send_secret_status(context, chat.id,
            'Solicitação expirada ou sem autorização. Nada foi armazenado.')
        raise ApplicationHandlerStop
    store = rt.kimi_secret_store
    try:
        candidate = SecretStore.normalize_candidate(message.text)
        status = store.status()
        if status == SecretStore.UNSAFE:
            raise ValueError('unsafe_store')
        await rt.kimi_provisioning_client.validate_candidate(candidate)
        previous = store.read() if status == SecretStore.PRIVATE else None
        store.write_atomic(candidate)
    except Exception:
        # Never interpolate exception text, provider body or candidate.
        await _send_secret_status(context, chat.id,
            'Não foi possível validar ou armazenar a chave Kimi com segurança. '
            'Não houve ativação de Kimi. Verifique o cofre antes de tentar novamente.')
        raise ApplicationHandlerStop
    try:
        _audit(rt, chat.id, user.id, 'rotate' if previous is not None else 'set')
    except Exception:
        try:
            store.clear() if previous is None else store.write_atomic(previous)
        except Exception:
            await _send_secret_status(context, chat.id,
                'A auditoria falhou e a reversão não pôde ser confirmada. Solicite revisão do cofre.')
            raise ApplicationHandlerStop
        await _send_secret_status(context, chat.id,
            'A auditoria falhou. A alteração foi revertida; Kimi não foi ativado.')
        raise ApplicationHandlerStop
    await _send_secret_status(context, chat.id,
        'Kimi: credencial validada e armazenada no cofre protegido. '
        'Mensagem excluída. Ativação nas conversas: NÃO. Use /kimistatus para consultar.')
    raise ApplicationHandlerStop


async def cancel_kimi_key_command(update, context):
    from .telegram_app import runtime, _explicit_operator
    if update.effective_chat.type == 'private' and _explicit_operator(update, context):
        runtime(context).kimi_secret_captures.pop((update.effective_chat.id, update.effective_user.id), None)
        await update.effective_message.reply_text('Recebimento da chave Kimi cancelado.')


async def kimi_status_command(update, context):
    from .telegram_app import runtime, _explicit_operator
    if update.effective_chat.type == 'private' and _explicit_operator(update, context):
        status = runtime(context).kimi_secret_store.status()
        await update.effective_message.reply_text('KIMI\nCofre: ' + status + '\nAtivação nas conversas: NÃO')
