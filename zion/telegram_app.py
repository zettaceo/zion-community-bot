from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from urllib.parse import unquote

from telegram import (
    Bot,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agents import DEFAULT_AGENT_REGISTRY, AgentId, ConversationIntent
from .agent_workflows import (
    partnership_intake_prompt,
    qualify_partnership,
    triage_support,
)
from .ai_service import AIService, sanitize_for_ai
from .provider_secrets import ProviderSecretStore
from .providers import KimiCompletionProvider
from .kimi_provisioning import (set_kimi_key_command, kimi_secret_capture_handler,
                                cancel_kimi_key_command, kimi_status_command)
from .config import Settings
from .language_recovery import recover_language
from .conversation_state import (FragmentWindow, DialogueSummary, bounded_exchanges,
                                 summarize_dialogue, changes_explicit_topic, explicit_topic)
from .db import ZION_APPLICATION_ID, ZionDB
from .dm_policy import evaluate_dm_access
from .guardian import (
    Guardian,
    normalize_link_target,
    normalize_policy_domain,
)
from .health import HealthService
from .knowledge import KnowledgeBase
from .logging_safe import (
    configure_logging,
    contains_high_confidence_credential,
    register_sensitive_value,
)
from .migrate import migrate_legacy_guardian_state
from .mistral import (
    MistralCredentialInvalid,
    MistralCredentialValidationUnavailable,
)
from .multi_agent_transport import (
    DeliveryFailedSafe,
    DeliveryOutcomeUncertain,
    MultiAgentTransport,
)
from .models import AbuseDecision, FloodDecision, OperatingState, Severity
from .process_lock import ProcessLock
from .router import IntentRouter, RouteDecision
from .secret_store import (
    SecretStore,
    SecretStoreError,
    SecretValidationError,
)
from .speaker import InboundMessageIdentity, SpeakerArbiter, UpdateKind


logger = logging.getLogger("zion.telegram")

ADMIN_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.OWNER,
}

GROUP_CONVERSATION_TTL_SECONDS = 10 * 60
GROUP_CONVERSATION_MAX_SESSIONS = 2048
GROUP_CONVERSATION_CONTEXT_MAX_CHARS = 3000
GROUP_CONVERSATION_QUERY_MAX_CHARS = 3000
GROUP_CONVERSATION_PASSIVE_COOLDOWN_SECONDS = 2.0


class ConversationRoute(str, Enum):
    MODERATE_ONLY = "MODERATE_ONLY"
    LOCAL_HELP = "LOCAL_HELP"
    AI_SUPPORT = "AI_SUPPORT"
    FOLLOW_UP = "FOLLOW_UP"
    IGNORE = "IGNORE"


@dataclass(frozen=True)
class GroupConversationSession:
    expires_at: float
    retrieval_query: str
    transcript: str
    last_reply_at: float
    active_topic: str | None = None
    summary: DialogueSummary | None = None
    recent_exchanges: tuple[tuple[str, str], ...] = ()
    last_user_id: int | None = None


@dataclass(frozen=True)
class ControlCenterSession:
    operator_id: int
    expires_at: float
    confirmation_action: str | None = None


class AskRateLimiter:
    def __init__(self, requests_per_minute: int):
        self.limit = max(1, requests_per_minute)
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._next_prune_at = 0.0

    def _prune(self, now: float) -> None:
        if now < self._next_prune_at:
            return
        for user_id, queue in list(self._events.items()):
            while queue and now - queue[0] > 60:
                queue.popleft()
            if not queue:
                self._events.pop(user_id, None)
        self._next_prune_at = now + 60

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        self._prune(now)
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

            startup_integrity = self.db.verify_integrity(full=False)
            if not startup_integrity["ok"]:
                raise RuntimeError(
                    "ZION refused to start on an inconsistent SQLite "
                    f"database: {startup_integrity}"
                )

            self.startup_delivery_recovery = (
                self.db.quarantine_stale_delivery_claims(
                    stale_after_seconds=None,
                )
            )
            self.startup_speaker_recovery = (
                self.db.quarantine_stale_speaker_claims(
                    stale_after_seconds=(
                        settings.delivery_claim_timeout_seconds
                    )
                )
            )
            if any(self.startup_delivery_recovery.values()):
                try:
                    self.db.create_incident(
                        chat_id=None,
                        user_id=None,
                        category="orphaned_delivery_claims_quarantined",
                        severity=Severity.HIGH,
                        source="runtime_startup",
                        evidence=self.startup_delivery_recovery,
                        note=(
                            "Jobs left in sending by a previous process were "
                            "quarantined. One-shot deliveries are UNCERTAIN and "
                            "recurring deliveries are PAUSED; nothing is replayed "
                            "automatically."
                        ),
                    )
                except Exception as exc:
                    logger.error(
                        "Claims órfãos foram isolados, mas o incidente "
                        "não pôde ser persistido: %s",
                        type(exc).__name__,
                    )
            self.knowledge = KnowledgeBase(settings.knowledge_dir)
            self.intent_router = IntentRouter(DEFAULT_AGENT_REGISTRY)
            self.speaker_arbiter = SpeakerArbiter(self.db)
            self.multi_agent_transport = MultiAgentTransport(settings)
            # Bound only after the primary Application is initialized.  This
            # gives secondary private flows a single, explicit path back to
            # the creator's ZION control channel without reusing a secondary
            # identity or persisting contact content.
            self.primary_bot: Bot | None = None
            self.guardian = Guardian(settings, self.db)
            self.secret_store = SecretStore(settings.mistral_secret_path)
            self.mistral_secret_startup_status = self.secret_store.status()
            if self.mistral_secret_startup_status == SecretStore.UNSAFE:
                logger.warning(
                    "Cofre Mistral inseguro no startup; provider bloqueado."
                )
            self.ai = AIService(
                settings,
                self.db,
                self.knowledge,
                self.secret_store,
            )
            self.health = HealthService(
                settings,
                self.db,
                self.secret_store,
                self.multi_agent_transport.identity_store,
            )
            self.ask_limiter = AskRateLimiter(
                settings.ai_user_requests_per_minute
            )
            self.observe_limiter = AskRateLimiter(
                settings.ai_user_requests_per_minute
            )
            self.report_limiter = AskRateLimiter(
                settings.report_requests_per_minute
            )
            self.ama_limiter = AskRateLimiter(
                settings.ama_requests_per_minute
            )
            self.admin_cache: dict[
                tuple[int, int],
                tuple[bool, float],
            ] = {}
            self.admin_cache_next_prune_at = 0.0
            self.update_lags: deque[float] = deque(maxlen=100)
            self.update_lag_last_sample_monotonic = 0.0
            self.health_alert_signature: str | None = None
            self.health_alert_last_sent_at = 0.0
            self.health_alert_persistence_dirty = False
            self.health_incident_signature: str | None = None
            self.health_incident_id: str | None = None
            self.health_incident_hydrated = False
            self.housekeeping_last_error: str | None = None
            self.wal_checkpoint_last_error: str | None = None
            self.state_maintenance_last_error: str | None = None
            self.delivery_guard_last_error: str | None = None
            self.delivery_health_blocked = False
            self.delivery_health_block_reasons: tuple[str, ...] = ()
            self.kimi_secret_captures: dict[tuple[int, int], float] = {}
            self.kimi_secret_store = ProviderSecretStore(settings.mistral_secret_path.parent / "providers").for_provider("kimi")
            self.kimi_provisioning_client = KimiCompletionProvider(self.kimi_secret_store, model="kimi-k2.6")
            self.mistral_secret_captures: dict[
                tuple[int, int],
                float,
            ] = {}
            self.group_conversation_sessions: dict[
                tuple[int, int],
                GroupConversationSession,
            ] = {}
            self.group_conversation_sessions_next_prune_at = 0.0
            self.fragment_window = FragmentWindow()
            self.control_center_sessions: dict[
                str,
                ControlCenterSession,
            ] = {}
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


def safe_display_text(value: object, max_chars: int = 80) -> str:
    raw = str(value or "")
    without_controls = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in raw
    )
    return " ".join(without_controls.split())[:max_chars]


def user_display_name(user: Any) -> str:
    username = safe_display_text(getattr(user, "username", None), 32)
    first_name = safe_display_text(getattr(user, "first_name", None), 80)
    user_id = getattr(user, "id", "?")

    if username:
        return f"@{username}"
    if first_name:
        return first_name
    return f"usuário {user_id}"


def telegram_ai_reply_text(value: object, max_chars: int = 3900) -> str:
    """Render provider output as safe, readable Telegram plain text."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")

    # Source lists were part of the old response contract. Drop them even if
    # a provider reproduces the old shape from learned behaviour.
    text = re.sub(
        r"(?ims)\n*fontes?\s+zion\s*:.*$",
        "",
        text,
    )

    # Internal paths and source file names never belong in a community answer.
    text = re.sub(
        r"(?i)(?:[a-z]:\\|/(?:home|srv|opt|var|tmp|etc)/)[^\s<>()]+",
        "documentação oficial",
        text,
    )
    text = re.sub(
        r"(?i)\b[\w.-]+\.(?:md|py|toml|ya?ml|json)\b",
        "documentação oficial",
        text,
    )

    # Telegram receives plain text here. Normalize common Markdown so users do
    # not see raw emphasis markers, headings or code fences.
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "• ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = text.replace("```", "").replace("**", "").replace("__", "")
    text = text.replace("`", "").replace("~~", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if not text:
        text = "Não consegui formular uma resposta agora. Tente novamente."
    return text[: max(1, int(max_chars))]


def _fold_conversation_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        char for char in folded if not unicodedata.combining(char)
    )


def _bot_identity(context: ContextTypes.DEFAULT_TYPE) -> tuple[int | None, str]:
    try:
        bot_id = getattr(context.bot, "id", None)
    except RuntimeError:
        bot_id = None
    try:
        username = str(getattr(context.bot, "username", "") or "").strip()
    except RuntimeError:
        username = ""
    return bot_id, username.lstrip("@")


def _group_conversation_key(
    update: Update,
) -> tuple[int, int] | None:
    if (
        not update.effective_chat
        or update.effective_chat.type == "private"
    ):
        return None
    message = update.effective_message
    raw_thread_id = getattr(message, "message_thread_id", None)
    try:
        thread_id = int(raw_thread_id) if raw_thread_id is not None else 0
    except (TypeError, ValueError):
        thread_id = 0
    return int(update.effective_chat.id), thread_id


def _active_group_conversation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> GroupConversationSession | None:
    key = _group_conversation_key(update)
    if key is None:
        return None

    rt = runtime(context)
    value = rt.group_conversation_sessions.get(key)
    if value is None:
        return None

    if value.expires_at <= time.monotonic():
        rt.group_conversation_sessions.pop(key, None)
        return None
    return value


def _looks_like_conversation_turn(value: str) -> bool:
    folded = _fold_conversation_text(value)
    if "?" in value:
        return True
    if re.fullmatch(
        r"\s*(?:obrigado|obrigada|valeu|agradecido)[\s!,.]*",
        folded,
    ):
        return True
    return bool(
        re.match(
            r"^\s*(?:o que|qual|quais|como|onde|quando|quem|por que|"
            r"porque|quanto|quantas|quantos|manda|posso|pode|tem|existe|me explica|explique|me fala|"
            r"diga|conte|resuma|resume|quero saber|gostaria|e se|e qual|"
            r"e quais|e como|mas|mais eu|eu perguntei|nao foi isso|"
            r"entao|isso inclui|que\b|redes\b|planos\b|taxas\b|cex\b|"
            r"ordens\b|terminal\b|dca\b|laboratorio\b)\b",
            folded,
        )
    )


_CONVERSATION_STOPWORDS = {
    "agora",
    "ainda",
    "algo",
    "alguem",
    "aquela",
    "aquele",
    "aqui",
    "assim",
    "como",
    "coisa",
    "comigo",
    "depois",
    "dessa",
    "desse",
    "disso",
    "entao",
    "essa",
    "esse",
    "esta",
    "este",
    "falar",
    "gente",
    "isso",
    "mais",
    "mesmo",
    "muito",
    "nada",
    "onde",
    "outra",
    "outro",
    "para",
    "porque",
    "qual",
    "quando",
    "quero",
    "sobre",
    "tambem",
    "tenho",
    "voce",
}


def _conversation_topic_tokens(value: str) -> set[str]:
    folded = _fold_conversation_text(value)
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", folded)
        if token not in _CONVERSATION_STOPWORDS
    }


def _is_explicit_active_follow_up(value: str) -> bool:
    folded = _fold_conversation_text(value)
    if re.match(
        r"^\s*(?:e\b|mas\b|mais\s+eu\b|eu\s+perguntei\b|"
        r"nao\s+foi\s+isso\b|porem\b|entao\b|isso\b|esse\b|essa\b|"
        r"esses\b|essas\b|ele\b|ela\b|tambem\b|sobre isso\b|"
        r"quanto a isso\b|discordo\b|nao concordo\b)",
        folded,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:nao\s+(?:concordo|faz sentido|acredito|confio)|discordo|"
            r"duvido|mentira|enganoso|enganosa|golpe|absurdo|errado|errada|"
            r"ruim|critica|problema)\b",
            folded,
        )
    )


def _continues_active_group_topic(
    question: str,
    session: GroupConversationSession | None,
) -> bool:
    if session is None:
        return False

    # Explicit new subjects take precedence over "E..." and lexical overlap.
    # Only user-request metadata determines the topic; generated answers may
    # mention unrelated subjects and must not make those subjects sticky.
    if changes_explicit_topic(question, session.active_topic):
        return False

    if _is_explicit_active_follow_up(question):
        return True

    current_tokens = _conversation_topic_tokens(question)
    previous_tokens = _conversation_topic_tokens(
        session.retrieval_query
    )
    if len(current_tokens & previous_tokens) < 2:
        return False

    # Passive overlap is rate-shaped per chat/thread so ZION does not answer
    # every line of a fast-moving group discussion. Explicit questions,
    # corrections and criticism are still handled immediately.
    return (
        time.monotonic() - session.last_reply_at
        >= GROUP_CONVERSATION_PASSIVE_COOLDOWN_SECONDS
    )


def _is_explicit_conversation_correction(value: str) -> bool:
    folded = _fold_conversation_text(value)
    return bool(
        re.match(
            r"^\s*(?:mas\s+eu|mais\s+eu|eu\s+perguntei|"
            r"nao\s+foi\s+isso)\b",
            folded,
        )
    )


def _looks_like_project_question(
    question: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not _looks_like_conversation_turn(recover_language(question).canonical):
        return False

    folded = recover_language(question).canonical
    if re.search(
        r"\b(?:projeto|produto|pro|pilot|trader|plano|beneficio|beneficios|vantagem|vantagens|"
        r"acesso|swaps?|bridges?|ordem|ordens|ponte|token|parcerias?|"
        r"carteira|wallet|blockchain|rede|redes|terminal|backtest|"
        r"arquitetura|roteamento|routing|multi[- ]?chain|apis?|sdks?|"
        r"endpoints?|webhooks?|integracao|integrar|developer|development|"
        r"desenvolvedor|desenvolvimento|conectar bot|"
        r"smart contract|contrato inteligente|indicador|ema|vwap|rsi|"
        r"macd|autopilot|arbitragem|liquidez|staking|mint|founder|cex|dex|"
        r"assinatura|suporte|problem(?:a|inha)|roadmap|whitepaper|taxa|taxas|"
        r"cotacao|portfolio|"
        r"preco|valor|comprar|adquirir|lancamento|lancar)\b",
        folded,
    ):
        return True

    # A busca é local e usa apenas a base oficial carregada. Ela permite
    # reconhecer perguntas do domínio mesmo quando o membro não repete o nome
    # do projeto, sem enviar conversa aleatória ao provedor de IA.
    question_tokens = _conversation_topic_tokens(question)
    for chunk in runtime(context).knowledge.search(question, limit=2):
        chunk_tokens = _conversation_topic_tokens(
            chunk.heading + "\n" + chunk.text
        )
        if len(question_tokens & chunk_tokens) >= 2:
            return True
    return False


def _looks_like_high_confidence_actionable_intent(value: str) -> bool:
    """Recognize support/business requests that do not need question syntax."""

    folded = recover_language(value).canonical
    return bool(
        re.search(
            r"\b(?:conta (?:foi )?invadida|transacao (?:desconhecida|"
            r"nao reconhecida)|nao reconheco (?:esta |essa )?transacao|"
            r"fundos? sumiu|saldo sumiu|carteira nao conectar|wallet nao "
            r"conectar|nao consigo conectar carteira|(?:swap|bridge|ordem) (?:falhou|travou|esta pendente|deu erro)|"
            r"quero (?:(?:propor|fazer) (?:uma )?)?parceria|proposta de parceria|"
            r"nossa empresa quer (?:integrar|uma parceria))\b",
            folded,
        )
    )


def _remember_group_conversation(
    rt: Runtime,
    update: Update,
    question: str,
    answer: str,
    previous: GroupConversationSession | None,
    *,
    speaker_name: str = "ZION",
) -> None:
    key = _group_conversation_key(update)
    if key is None:
        return

    now = time.monotonic()
    sessions = rt.group_conversation_sessions
    if (
        now >= rt.group_conversation_sessions_next_prune_at
        or len(sessions) >= GROUP_CONVERSATION_MAX_SESSIONS
    ):
        for candidate, session in list(sessions.items()):
            if session.expires_at <= now:
                sessions.pop(candidate, None)
        rt.group_conversation_sessions_next_prune_at = now + 60

    if (
        key not in sessions
        and len(sessions) >= GROUP_CONVERSATION_MAX_SESSIONS
    ):
        oldest = min(
            sessions,
            key=lambda candidate: sessions[candidate].expires_at,
        )
        sessions.pop(oldest, None)

    safe_question, safe_answer = sanitize_for_ai(question), sanitize_for_ai(answer)
    user_id = update.effective_user.id if update.effective_user else None
    summary = summarize_dialogue(safe_question, speaker_name.lower(),
        previous.summary if previous else None,
        same_user=bool(previous and previous.last_user_id == user_id))
    exchanges = bounded_exchanges(previous.recent_exchanges if previous else (),
        safe_question, safe_answer, speaker=speaker_name)
    retrieval_query = "\n".join(item[0] for item in exchanges)
    if not retrieval_query:
        retrieval_query = safe_question[:GROUP_CONVERSATION_QUERY_MAX_CHARS]
    transcript = summary.render() + "\n\n" + "\n\n".join(item[1] for item in exchanges)
    sessions[key] = GroupConversationSession(
        expires_at=now + GROUP_CONVERSATION_TTL_SECONDS,
        retrieval_query=retrieval_query,
        transcript=transcript,
        last_reply_at=now,
        summary=summary, recent_exchanges=exchanges, last_user_id=user_id,
        active_topic=explicit_topic(question) or (
            previous.active_topic if previous else None
        ),
    )


def natural_conversation_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> str | None:
    """Return text only when an ordinary message is addressed to ZION."""
    question = (text or "").strip()
    if not question or question.startswith("/") or not update.effective_chat:
        return None

    if update.effective_chat.type == "private":
        return question[:6000]

    message = update.effective_message
    bot_id, bot_username = _bot_identity(context)
    replied = getattr(message, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None)
    is_reply = bool(
        bot_id is not None
        and getattr(replied_user, "id", None) == bot_id
    )

    folded = recover_language(question).canonical
    username_mention = bool(
        bot_username
        and re.search(
            rf"(?<!\w)@{re.escape(bot_username.casefold())}(?!\w)",
            question.casefold(),
        )
    )
    named_directly = bool(
        re.match(r"^\s*(?:zion|z[\s-]?ion)\b", folded)
    )
    short_greeting = bool(
        re.fullmatch(
            r"\s*(?:oi|ola|bom dia|boa tarde|boa noite|e ai|salve)"
            r"[\s!,.]*(?:zion)?[\s!,.]*",
            folded,
        )
    )
    product_topic = bool(
        re.search(
            r"\b(?:z[\s-]?swap|zion|guardian|pilot|trader|thrall|hird|"
            r"panteao|access\s+pass|plano\s+(?:free|gratis|gratuito|pro|"
            r"profissional|trader|pilot|piloto)|terminal\s+pro)\b",
            folded,
        )
    )
    question_like = _looks_like_conversation_turn(recover_language(question).canonical)
    active_session = _active_group_conversation(update, context)
    recent_follow_up = _continues_active_group_topic(
        question,
        active_session,
    )
    project_question = _looks_like_project_question(question, context)
    actionable_intent = _looks_like_high_confidence_actionable_intent(question)
    interpreted_request = bool(re.search(
        r"\b(?:z-swap e segur[oa]|uniswap nao faz igual|isso ai ja existe|"
        r"por que eu pagaria|e no pro)\b", folded))

    if not (
        is_reply
        or username_mention
        or named_directly
        or short_greeting
        or (product_topic and (question_like or active_session is not None))
        or project_question
        or actionable_intent
        or interpreted_request
        or recent_follow_up
    ):
        return None

    cleaned = question
    if bot_username:
        cleaned = re.sub(
            rf"(?i)(?<!\w)@{re.escape(bot_username)}(?!\w)[\s,:;-]*",
            "",
            cleaned,
        ).strip()
    cleaned = re.sub(
        r"(?i)^\s*(?:zion|z[\s-]?ion)\b[\s,:;-]*",
        "",
        cleaned,
    ).strip()
    return (cleaned or question)[:6000]


def _community_help_reply(question: str) -> str | None:
    folded = _fold_conversation_text(question)
    if re.search(
        r"\b(?:que grupo e esse|do que se trata (?:esse|este) grupo|"
        r"onde estou|onde vim parar|estou perdido|estou perdida|"
        r"nao estou entendendo(?: nada)?|nao entendo nada|"
        r"alguem pode (?:me )?(?:explicar|ajudar)|"
        r"o que faco aqui|como funciona a comunidade)\b",
        folded,
    ):
        return (
            "Este é o grupo oficial da comunidade Z-SWAP. Aqui você pode "
            "tirar dúvidas sobre a plataforma, recursos, planos e segurança. "
            "O que você quer entender primeiro?"
        )
    return None


def _security_refusal_reply(question: str) -> str | None:
    candidates = [question or ""]
    percent_value = question or ""
    for _ in range(2):
        decoded = unquote(percent_value)
        if decoded == percent_value:
            break
        candidates.append(decoded)
        percent_value = decoded

    # Decode only bounded, standalone Base64-like tokens.  This is an
    # exfiltration detector, not a general-purpose decoder and never changes
    # the text sent to normal conversation or knowledge retrieval.
    encoded_candidates = re.findall(
        r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{16,512}"
        r"(?![A-Za-z0-9+/=_-])",
        question or "",
    )
    for token in encoded_candidates:
        padded = token + ("=" * (-len(token) % 4))
        try:
            raw = base64.b64decode(
                padded.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            decoded = raw.decode("utf-8")
        except (UnicodeDecodeError, ValueError, binascii.Error):
            continue
        printable_ratio = (
            sum(char.isprintable() for char in decoded) / len(decoded)
            if decoded
            else 0.0
        )
        if printable_ratio >= 0.9:
            candidates.append(decoded)

    folded = " ".join(_fold_conversation_text(value) for value in candidates)
    internal_target = bool(
        re.search(
            r"\b(?:ip(?: do)? servidor|servidor|host|ssh|firewall|tailscale|"
            r"schema|sql|banco interno|database interno|rotas? admin(?:istrativas?)?|"
            r"endpoints? (?:admin|internos?)|api key|chave api|credenciais|credencial|leads|"
            r"segredo|secret|prompt do sistema|system prompt|fontes internas|"
            r"arquivos internos|repositorios?|repository|commits?|infraestrutura|"
            r"deploy|variavel de ambiente|env)\b",
            folded,
        )
    )
    imperative = bool(
        re.search(
            r"\b(?:me passe|passe|mostre|revele|forneca|liste|envie|"
            r"exiba|mostra|revela|mostre-me|me diga|give me|show me|reveal)\b",
            folded,
        )
    )
    prompt_exfiltration = bool(
        re.search(
            r"\b(?:ignore (?:todas )?(?:as )?(?:regras|instrucoes)|"
            r"ignore instrucoes anteriores|modo auditor|"
            r"revele (?:seu |o )?prompt|mostre (?:seu |o )?prompt|"
            r"fontes internas|system prompt)\b",
            folded,
        )
    )
    direct_private_discovery = bool(re.search(
        r"\b(?:quais (?:credenciais|leads)|quais sao (?:as )?(?:credenciais|rotas administrativas))\b",
        folded,
    ))
    if (imperative and internal_target) or prompt_exfiltration or direct_private_discovery:
        return (
            "Posso explicar o funcionamento público e as proteções em alto "
            "nível, mas não forneço credenciais, infraestrutura interna, "
            "rotas administrativas, prompts ou mecanismos que reduzam a "
            "segurança do sistema."
        )
    full_document_request = bool(
        re.search(
            r"\b(?:reproduza|reproduzir|copie|copiar|transcreva|transcrever|"
            r"mostre|envie)\b.*\b(?:technical paper|paper tecnico|apn|"
            r"documento)\b.*\b(?:completo|inteiro|integral|todas as paginas)\b",
            folded,
        )
    )
    if full_document_request:
        return (
            "Posso resumir e explicar os pontos públicos aprovados, mas não "
            "reproduzo documentos inteiros ou materiais extensos. Diga qual "
            "tópico você quer entender."
        )
    return None


def conversation_route(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> ConversationRoute:
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return ConversationRoute.IGNORE

    if (
        update.effective_chat
        and update.effective_chat.type != "private"
        and runtime(context).guardian.evaluate_abuse(
            telegram_abuse_surface(update.effective_message, raw),
            directed_hint=telegram_reply_targets_other_user(
                update.effective_message,
                getattr(update.effective_user, "id", None),
            ),
        ).detected
    ):
        return ConversationRoute.MODERATE_ONLY

    if (
        _security_refusal_reply(raw) is not None
        or _community_help_reply(raw) is not None
        or _casual_conversation_reply(raw) is not None
    ):
        return ConversationRoute.LOCAL_HELP

    question = natural_conversation_question(update, context, raw)
    if question is None:
        return ConversationRoute.IGNORE

    session = _active_group_conversation(update, context)
    if (
        session is not None
        and _continues_active_group_topic(question, session)
    ):
        return ConversationRoute.FOLLOW_UP
    return ConversationRoute.AI_SUPPORT


def _casual_conversation_reply(question: str) -> str | None:
    folded = _fold_conversation_text(question)
    simple = re.sub(r"[^a-z0-9\s]", "", folded).strip()
    if simple in {"oi", "ola", "e ai", "salve", "zion"}:
        return "Olá! Como posso ajudar com a Z-SWAP?"
    if simple in {"bom dia", "boa tarde", "boa noite"}:
        return f"{simple.capitalize()}! Como posso ajudar com a Z-SWAP?"
    if simple in {"obrigado", "obrigada", "valeu", "agradecido"}:
        return "Por nada! Se precisar, estou por aqui."
    return None


def _routing_inbound(
    update: Update,
    source_agent: AgentId,
) -> InboundMessageIdentity:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        raise ValueError("routing telemetry requires message and chat")
    update_id = getattr(update, "update_id", None)
    return InboundMessageIdentity(
        source_identity=source_agent.value,
        chat_id=int(chat.id),
        message_id=int(message.message_id),
        update_id=int(update_id) if update_id is not None else None,
        update_kind=(
            UpdateKind.EDITED_MESSAGE
            if getattr(update, "edited_message", None) is not None
            else UpdateKind.MESSAGE
        ),
    )


def _record_routing_decision(
    rt: Runtime,
    inbound: InboundMessageIdentity,
    decision: RouteDecision,
    *,
    outcome: str,
    status: str,
) -> bool:
    selected = decision.speaker.agent_id if decision.speaker else None
    try:
        return rt.db.record_routing_event(
            route_key=inbound.claim_key(),
            source_identity=inbound.source_identity,
            channel="private" if inbound.chat_id > 0 else "group",
            initial_agent=(
                decision.handoff_from.value
                if decision.handoff_from is not None
                else None
            ),
            selected_agent=selected.value if selected is not None else None,
            intent=decision.intent.delivery_family,
            outcome=outcome,
            reason=decision.reason,
            handoff_count=decision.handoff_count,
            ai_fallback=decision.used_ai_fallback,
            status=status,
        )
    except Exception as exc:
        logger.warning(
            "Routing telemetry unavailable | error=%s",
            type(exc).__name__,
        )
        return False


def _complete_routing_decision(
    rt: Runtime,
    inbound: InboundMessageIdentity | None,
    status: str,
) -> bool:
    if inbound is None:
        return False
    try:
        return rt.db.complete_routing_event(
            inbound.claim_key(),
            status=status,
        )
    except Exception as exc:
        logger.warning(
            "Routing completion telemetry unavailable | error=%s",
            type(exc).__name__,
        )
        return False


def _record_dm_denial(
    rt: Runtime,
    update: Update,
    agent_id: AgentId,
    intent: ConversationIntent,
    reason: str,
) -> None:
    inbound = _routing_inbound(update, agent_id)
    try:
        rt.db.record_routing_event(
            route_key=inbound.claim_key(),
            source_identity=agent_id.value,
            channel="private",
            initial_agent=agent_id.value,
            selected_agent=None,
            intent=intent.value,
            outcome="dm_denied",
            reason=reason,
            status="denied",
        )
    except Exception as exc:
        logger.warning(
            "DM denial telemetry unavailable | agent=%s | error=%s",
            agent_id.value,
            type(exc).__name__,
        )


async def answer_natural_conversation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    claim_private_update: bool = False,
) -> bool:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return False

    raw_question = (text or "").strip()
    rt = runtime(context)
    multi_agent_group = bool(
        update.effective_chat.type != "private"
        and context.application.bot_data.get("zion_multi_agent_started")
    )
    route = conversation_route(
        update,
        context,
        raw_question,
    )
    fragment_query = None
    if multi_agent_group and route not in {
        ConversationRoute.MODERATE_ONLY, ConversationRoute.LOCAL_HELP,
    }:
        fragment_query = rt.fragment_window.observe(
            (int(update.effective_chat.id),
             getattr(update.effective_message, 'message_thread_id', None),
             int(update.effective_user.id)), raw_question, now=time.monotonic())
        if fragment_query:
            route = ConversationRoute.AI_SUPPORT
    if route == ConversationRoute.IGNORE:
        if multi_agent_group:
            inbound = _routing_inbound(update, AgentId.ZION)
            decision = rt.intent_router.route_group(
                raw_question,
                explicitly_addressed=False,
                addressed_agent=rt.intent_router.addressed_agent(raw_question),
            )
            _record_routing_decision(
                rt,
                inbound,
                decision,
                outcome="suppressed",
                status="suppressed",
            )
        return False

    selected_profile = DEFAULT_AGENT_REGISTRY.get(AgentId.ZION)
    selected_intent = ConversationIntent.COMMUNITY
    speaker_claim = None
    update_id = getattr(update, "update_id", None)
    routing_inbound = None
    delivery_succeeded = False
    if multi_agent_group:
        routing_inbound = _routing_inbound(update, AgentId.ZION)
        if route == ConversationRoute.LOCAL_HELP:
            selected_profile = DEFAULT_AGENT_REGISTRY.get(AgentId.ZION)
            selected_intent = ConversationIntent.COMMUNITY
            decision = RouteDecision(
                intent=selected_intent,
                speaker=selected_profile,
                confidence=1.0,
                reason="local_community_help",
            )
        else:
            addressed_agent = rt.intent_router.addressed_agent(raw_question)
            routing_question = fragment_query or raw_question
            active = _active_group_conversation(update, context)
            if (route == ConversationRoute.FOLLOW_UP and active is not None
                    and explicit_topic(raw_question) is None):
                routing_question = active.retrieval_query + '\n' + raw_question
            decision = rt.intent_router.route_group(
                routing_question,
                explicitly_addressed=True,
                addressed_agent=addressed_agent,
            )
            if decision.speaker is None:
                fallback = await rt.ai.classify_route(
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    text=raw_question,
                )
                decision = rt.intent_router.accept_ai_fallback(
                    decision,
                    fallback,
                )
            if decision.speaker is None:
                _record_routing_decision(
                    rt,
                    routing_inbound,
                    decision,
                    outcome=(
                        "ambiguous"
                        if decision.intent is ConversationIntent.AMBIGUOUS
                        else "suppressed"
                    ),
                    status="suppressed",
                )
                return True
            selected_profile = decision.speaker
            selected_intent = decision.intent

        _record_routing_decision(
            rt,
            routing_inbound,
            decision,
            outcome="routed",
            status="selected",
        )
        speaker_claim = rt.speaker_arbiter.claim(
            routing_inbound,
            speaker=selected_profile,
            intent=selected_intent,
        )
        if speaker_claim is None:
            return True

    async def deliver(reply: str) -> bool:
        nonlocal delivery_succeeded
        if speaker_claim is None:
            await update.effective_message.reply_text(reply)
            delivery_succeeded = True
            return True
        try:
            sent = await rt.multi_agent_transport.send_message(
                agent_id=selected_profile.agent_id,
                primary_bot=context.bot,
                chat_id=int(update.effective_chat.id),
                text=reply,
                reply_to_message_id=int(
                    update.effective_message.message_id
                ),
            )
        except DeliveryOutcomeUncertain as exc:
            rt.speaker_arbiter.uncertain(
                speaker_claim,
                error_type=type(exc).__name__,
            )
            _complete_routing_decision(
                rt,
                routing_inbound,
                "uncertain",
            )
            return True
        except DeliveryFailedSafe as exc:
            rt.speaker_arbiter.failed_safe(
                speaker_claim,
                error_type=type(exc).__name__,
            )
            _complete_routing_decision(
                rt,
                routing_inbound,
                "failed_safe",
            )
            return True
        telegram_message_id = getattr(sent, "message_id", None)
        if telegram_message_id is None:
            rt.speaker_arbiter.uncertain(
                speaker_claim,
                error_type="missing_telegram_message_id",
            )
            _complete_routing_decision(
                rt,
                routing_inbound,
                "uncertain",
            )
            return True
        if not rt.speaker_arbiter.sent(
            speaker_claim,
            telegram_message_id=int(telegram_message_id),
        ):
            logger.error(
                "Speaker delivery persisted incompletely | agent=%s",
                selected_profile.agent_id.value,
            )
        delivery_succeeded = True
        _complete_routing_decision(rt, routing_inbound, "sent")
        return True

    active_session = _active_group_conversation(update, context)
    previous_session = (
        active_session
        if route == ConversationRoute.FOLLOW_UP
        else None
    )
    if claim_private_update and update_id is not None:
        try:
            claimed = rt.db.claim_idempotency_key(
                f"telegram_conversation:{int(update_id)}",
                ttl_seconds=rt.settings.idempotency_retention_days * 86400,
            )
        except Exception as exc:
            logger.error(
                "Falha no gate de idempotência da conversa: %s",
                type(exc).__name__,
            )
            return True
        if not claimed:
            return True

    if route == ConversationRoute.LOCAL_HELP:
        local_reply = (
            _security_refusal_reply(raw_question)
            or _community_help_reply(raw_question)
            or _casual_conversation_reply(raw_question)
        )
        if local_reply is None:
            return False
        return await deliver(local_reply)

    question = natural_conversation_question(
        update,
        context,
        raw_question,
    )
    if fragment_query:
        question = raw_question
    if question is None:
        return False

    if not rt.ask_limiter.allow(update.effective_user.id):
        return await deliver(
            "Recebi muitas perguntas em pouco tempo. Tente novamente em "
            "alguns instantes."
        )

    answer_kwargs: dict[str, Any] = {
        "chat_id": update.effective_chat.id,
        "user_id": update.effective_user.id,
        "question": question,
    }
    if selected_profile.agent_id is not AgentId.ZION:
        answer_kwargs["agent_id"] = selected_profile.agent_id
    if previous_session is not None:
        if _is_explicit_conversation_correction(question):
            # Keep the transcript so the model understands and acknowledges
            # the correction, but retrieve official facts from the corrected
            # subject instead of allowing the old, mistaken subject to win.
            answer_kwargs["context_query"] = question
        else:
            answer_kwargs["context_query"] = (
                previous_session.retrieval_query + "\n" + question
            )[-6000:]
        answer_kwargs["conversation_context"] = (
            previous_session.transcript
        )
        if (previous_session.summary is not None
                and previous_session.summary.agent != selected_profile.agent_id.value):
            answer_kwargs["conversation_context"] = previous_session.summary.handoff_context(
                selected_profile.agent_id,
                same_user=previous_session.last_user_id == update.effective_user.id)

    if fragment_query:
        answer_kwargs["context_query"] = fragment_query
    answer = await rt.ai.answer(**answer_kwargs)
    rendered = telegram_ai_reply_text(answer.text)
    if selected_profile.agent_id is AgentId.EIR:
        support_triage = triage_support(question)
        if support_triage.requires_human:
            rendered += (
                "\n\nEste caso precisa de revisão humana. Não envie seed "
                "phrase, chave privada, senha, token, API secret ou código 2FA."
            )
    elif selected_profile.agent_id is AgentId.FREYR:
        rendered += (
            "\n\nSe quiser qualificar a oportunidade, fale com a FREYR no "
            "privado e envie somente os dados profissionais necessários."
        )
    await deliver(rendered)
    if delivery_succeeded:
        _remember_group_conversation(
            rt,
            update,
            question,
            rendered,
            previous_session,
            speaker_name=selected_profile.agent_id.value.upper(),
        )
    return True


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


def _telegram_link_candidates(
    message: Any,
    *,
    policy_limits: bool = True,
) -> tuple[list[str], bool, bool]:
    targets: list[str] = []
    parse_failed = False
    too_many = False

    def add(candidate: object | None) -> None:
        nonlocal too_many
        if candidate is None:
            return
        value = str(candidate).strip()
        if policy_limits:
            value = value[:2048]
        if not value or value in targets:
            return
        if policy_limits and len(targets) >= 20:
            too_many = True
            return
        targets.append(value)

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
            if entity_type == "text_link":
                candidate = getattr(entity, "url", None)
                if not candidate:
                    parse_failed = True
                add(candidate)
            elif entity_type == "url":
                if not callable(parser):
                    parse_failed = True
                    continue
                try:
                    candidate = parser(entity)
                except Exception:
                    parse_failed = True
                    continue
                if not candidate:
                    parse_failed = True
                add(candidate)

    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "inline_keyboard", None) or ():
        for button in row or ():
            add(getattr(button, "url", None))
            login_url = getattr(button, "login_url", None)
            add(getattr(login_url, "url", None))
            web_app = getattr(button, "web_app", None)
            add(getattr(web_app, "url", None))

    return targets, parse_failed, too_many


def telegram_external_urls(message: Any) -> list[str]:
    targets, _, _ = _telegram_link_candidates(message)
    return targets


def telegram_abuse_surface(message: Any, visible_text: str) -> str:
    # Hidden Telegram links and button URLs are user-supplied content too.
    # The returned surface is evaluated in memory and is never persisted.
    return "\n".join((visible_text or "", *telegram_external_urls(message)))


def telegram_reply_targets_other_user(
    message: Any,
    user_id: int | None,
) -> bool:
    replied = getattr(message, "reply_to_message", None)
    target = getattr(replied, "from_user", None)
    target_id = getattr(target, "id", None)
    if target_id is None or user_id is None:
        return False
    try:
        return int(target_id) != int(user_id)
    except (TypeError, ValueError):
        return False


def telegram_entity_link_evidence(
    message: Any,
) -> tuple[list[str], list[str]]:
    domains: list[str] = []
    targets, parse_failed, too_many = _telegram_link_candidates(message)
    unsupported_schemes: list[str] = []

    if parse_failed:
        unsupported_schemes.append("unparseable-url-entity")
    if too_many:
        unsupported_schemes.append("too-many-link-entities")

    for candidate in targets:
        domain, unsupported_scheme = normalize_link_target(candidate)
        if domain and domain not in domains:
            domains.append(domain)
        if (
            unsupported_scheme
            and unsupported_scheme not in unsupported_schemes
        ):
            unsupported_schemes.append(unsupported_scheme)

    return domains, unsupported_schemes


def telegram_entity_domains(message: Any) -> list[str]:
    domains, _ = telegram_entity_link_evidence(message)
    return domains


def telegram_sensitive_surface(message: Any, visible_text: str) -> str:
    # Domain-policy limits must not hide credentials in private/admin messages.
    # Inspect the entire supplied surface; never persist these raw values.
    targets, _, _ = _telegram_link_candidates(message, policy_limits=False)
    values = []
    for value in [visible_text or "", *targets]:
        values.append(value)
        # Support singly/doubly encoded labels without an unbounded decode loop.
        for _ in range(2):
            decoded = unquote(value)
            if decoded == value:
                break
            values.append(decoded)
            value = decoded
    return "\n".join(values)


def link_incident_severity(
    unauthorized_domains: list[str],
    unsupported_schemes: list[str],
) -> Severity:
    if unsupported_schemes:
        return Severity.MEDIUM
    if any(
        label.startswith("xn--")
        for domain in unauthorized_domains
        for label in domain.split(".")
    ):
        return Severity.MEDIUM
    return Severity.LOW


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
    *,
    use_cache: bool = True,
    revalidate_cached_admin: bool = False,
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
    if now >= rt.admin_cache_next_prune_at:
        for cache_key, (_, expires_at) in list(rt.admin_cache.items()):
            if expires_at <= now:
                rt.admin_cache.pop(cache_key, None)
        rt.admin_cache_next_prune_at = (
            now + max(5, rt.settings.admin_cache_seconds)
        )

    cached = rt.admin_cache.get(key)
    if use_cache and cached and now < cached[1]:
        if not (revalidate_cached_admin and cached[0]):
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
    # Positive cached privilege is revalidated before granting a privileged
    # chat-local command. Negative cache entries remain useful against API
    # amplification from members repeatedly invoking admin commands.
    if await is_admin(
        update,
        context,
        revalidate_cached_admin=True,
    ):
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
    date = (
        getattr(message, "edit_date", None)
        or getattr(message, "date", None)
    )
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
    rt = runtime(context)
    rt.update_lags.append(lag)
    rt.update_lag_last_sample_monotonic = time.monotonic()


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
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            result = await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
            # The Telegram Bot API contract returns the boolean True on
            # success. Anything else is unconfirmed and must be retried rather
            # than written to the enforcement ledger as a successful delete.
            if result is True:
                return True
        except Exception as exc:
            logger.debug(
                "Falha ao apagar chat=%s message=%s attempt=%s/%s: %s",
                chat_id,
                message_id,
                attempt,
                attempts,
                type(exc).__name__,
            )
        if attempt < attempts:
            await asyncio.sleep(0.20 * attempt)

    logger.warning(
        "Telegram não confirmou exclusão chat=%s message=%s attempts=%s",
        chat_id,
        message_id,
        attempts,
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
    with rt.db.transaction():
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

    if not deleted:
        await _alert_operators_enforcement_failure(
            context,
            chat_id=update.effective_chat.id,
            target_user_id=user_id,
            action="delete",
            reason="possible_credential_exposure",
        )
        notice_text = (
            f"🚨 {user_display_name(update.effective_user)}: possível "
            "credencial detectada, mas o Telegram não confirmou a remoção. "
            "Apague a mensagem manualmente e revogue/rotacione a credencial."
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
    with rt.db.transaction():
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

    if not deleted:
        await _alert_operators_enforcement_failure(
            context,
            chat_id=update.effective_chat.id,
            target_user_id=user_id,
            action="delete",
            reason=sensitive.kind,
        )
        notice_text = (
            f"🚨 {user_display_name(update.effective_user)}: possível segredo "
            "de carteira detectado, mas o Telegram não confirmou a remoção. "
            "Apague a mensagem manualmente e proteja a carteira."
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


async def _alert_operators_enforcement_failure(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    target_user_id: int,
    action: str,
    reason: str,
) -> None:
    rt = runtime(context)
    for operator_id in sorted(rt.settings.admin_user_ids):
        if operator_id == target_user_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=operator_id,
                text=(
                    "⚠️ ZION enforcement review required. "
                    f"Chat={chat_id}; target_user={target_user_id}; "
                    f"action={action}; reason={reason}. "
                    "Telegram rejected the external action; inspect the "
                    "sanitized incident/action ledger."
                ),
            )
        except Exception as exc:
            logger.warning(
                "Falha ao alertar operador sobre enforcement: %s",
                type(exc).__name__,
            )


async def mute_user_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    seconds: int,
) -> bool:
    try:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        result = await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        return result is True
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
        result = await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            revoke_messages=True,
        )
        return result is True
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
        result = await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )
        return result is True
    except Exception as exc:
        logger.warning(
            "Falha ao desbanir chat=%s user=%s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False


CONTROL_CENTER_TTL_SECONDS = 10 * 60
CONTROL_CENTER_ACTIONS = frozenset(
    {
        "main",
        "guardian",
        "ai",
        "community",
        "agents",
        "agent_zion",
        "agent_mimir",
        "agent_eir",
        "agent_freyr",
        "routing",
        "incidents",
        "domains",
        "announcements",
        "health",
        "configuration",
        "audit",
        "lockdown_request",
        "lockdown_confirm",
        "cancel",
    }
)


def _control_center_callback(nonce: str, action: str) -> str:
    return f"zc1:{nonce}:{action}"


def _new_control_center_session(
    rt: Runtime,
    operator_id: int,
    *,
    confirmation_action: str | None = None,
) -> str:
    now = time.monotonic()
    for nonce, session in list(rt.control_center_sessions.items()):
        if session.expires_at <= now:
            rt.control_center_sessions.pop(nonce, None)
    nonce = secrets.token_urlsafe(8)
    rt.control_center_sessions[nonce] = ControlCenterSession(
        operator_id=int(operator_id),
        expires_at=now + CONTROL_CENTER_TTL_SECONDS,
        confirmation_action=confirmation_action,
    )
    return nonce


def _control_center_main_markup(nonce: str) -> InlineKeyboardMarkup:
    button = lambda label, action: InlineKeyboardButton(
        label,
        callback_data=_control_center_callback(nonce, action),
    )
    return InlineKeyboardMarkup(
        [
            [button("Guardian", "guardian"), button("AI & Knowledge", "ai")],
            [button("Community", "community"), button("Agents", "agents")],
            [button("Incidents", "incidents"), button("Domains & Security", "domains")],
            [button("Announcements", "announcements"), button("System Health", "health")],
            [button("Configuration", "configuration"), button("Audit", "audit")],
        ]
    )


def _control_center_back_markup(nonce: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "Voltar",
            callback_data=_control_center_callback(nonce, "main"),
        )]]
    )


def _control_center_agents_markup(nonce: str) -> InlineKeyboardMarkup:
    button = lambda label, action: InlineKeyboardButton(
        label,
        callback_data=_control_center_callback(nonce, action),
    )
    return InlineKeyboardMarkup(
        [
            [button("ZION", "agent_zion"), button("MÍMIR", "agent_mimir")],
            [button("EIR", "agent_eir"), button("FREYR", "agent_freyr")],
            [button("Routing telemetry", "routing")],
            [button("Voltar", "main")],
        ]
    )


def _control_center_agent_back_markup(nonce: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "Voltar para Agents",
            callback_data=_control_center_callback(nonce, "agents"),
        )]]
    )


def _control_center_view(
    rt: Runtime,
    nonce: str,
    action: str,
) -> tuple[str, InlineKeyboardMarkup]:
    if action == "main":
        return "ZION CONTROL CENTER\nSelecione uma área.", _control_center_main_markup(nonce)
    if action == "agents":
        lines = ["AGENTS"]
        statuses = rt.multi_agent_transport.status_all()
        for profile in DEFAULT_AGENT_REGISTRY:
            status = statuses[profile.agent_id]
            lines.append(
                f"{profile.agent_id.value.upper()}: "
                f"runtime={status.runtime_status} | "
                f"token={status.store_status} | "
                f"DM={profile.dm_policy.value} | "
                f"moderation={profile.moderation_authority.value}"
            )
        return "\n".join(lines), _control_center_agents_markup(nonce)
    if action.startswith("agent_"):
        try:
            agent_id = AgentId(action.removeprefix("agent_"))
        except ValueError:
            return "AGENT INVÁLIDO", _control_center_agent_back_markup(nonce)
        profile = DEFAULT_AGENT_REGISTRY.get(agent_id)
        status = rt.multi_agent_transport.status_all()[agent_id]
        telemetry = rt.db.routing_telemetry()["agents"].get(
            agent_id.value,
            {},
        )
        last_success = telemetry.get("last_success")
        last_activity = (
            datetime.fromtimestamp(
                float(last_success),
                tz=timezone.utc,
            ).isoformat()
            if last_success is not None
            else "NONE"
        )
        scopes = ", ".join(
            sorted(scope.value for scope in profile.knowledge_scopes)
        )
        return (
            f"{profile.display_name}\n"
            f"Title: {profile.title}\n"
            f"Runtime: {status.runtime_status}\n"
            f"Token: {status.store_status}\n"
            f"DM policy: {profile.dm_policy.value}\n"
            f"Knowledge scopes: {scopes}\n"
            f"Moderation: {profile.moderation_authority.value}\n"
            f"Routed: {telemetry.get('routed', 0)}\n"
            f"Responses sent: {telemetry.get('sent', 0)}\n"
            f"Send failures: {telemetry.get('send_failures', 0)}\n"
            f"Last successful activity UTC: {last_activity}",
            _control_center_agent_back_markup(nonce),
        )
    if action == "routing":
        telemetry = rt.db.routing_telemetry()
        lines = [
            "ROUTING TELEMETRY",
            f"Suppressed: {telemetry['suppressed']}",
            f"Ambiguous: {telemetry['ambiguous']}",
            f"Handoffs: {telemetry['handoffs']}",
            f"DM denied: {telemetry['dm_denied']}",
            f"Routing failures: {telemetry['routing_failures']}",
        ]
        for agent_id in AgentId:
            agent = telemetry["agents"].get(agent_id.value, {})
            lines.append(
                f"{agent_id.value.upper()}: "
                f"routed={agent.get('routed', 0)} | "
                f"sent={agent.get('sent', 0)} | "
                f"send_failures={agent.get('send_failures', 0)}"
            )
        return "\n".join(lines), _control_center_agent_back_markup(nonce)
    if action == "guardian":
        state = rt.db.get_operating_state().value
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(
                    "Ativar LOCKDOWN",
                    callback_data=_control_center_callback(
                        nonce,
                        "lockdown_request",
                    ),
                )],
                [InlineKeyboardButton(
                    "Voltar",
                    callback_data=_control_center_callback(nonce, "main"),
                )],
            ]
        )
        return (
            "GUARDIAN\n"
            f"Operating State: {state}\n"
            "Authority: deterministic ZION only",
            markup,
        )
    if action == "ai":
        try:
            totals = rt.ai.provider_token_budget.totals()
            provider_tokens = str(totals['providers'].get('mistral', 0))
            model_tokens = str(totals['models'].get(rt.settings.mistral_model, 0))
        except Exception:
            provider_tokens = model_tokens = 'UNAVAILABLE'
        cost_status = 'NOT CONFIGURED'
        if rt.ai.runtime_cost_budget is not None:
            try:
                cost_status = str(rt.ai.runtime_cost_budget.totals()['total']) + ' micro-USD estimated/reserved'
            except Exception:
                cost_status = 'UNAVAILABLE'
        return (
            "AI & KNOWLEDGE\n"
            "Active provider: Mistral\n"
            f"Active model: {rt.settings.mistral_model}\n"
            f"Tokens today UTC: {rt.ai.tokens_used_today()}/{rt.settings.ai_daily_token_budget}\n"
            f"Runtime ledger Mistral tokens (charged/reserved): {provider_tokens}\n"
            f"Runtime ledger active model tokens (charged/reserved): {model_tokens}\n"
            "Runtime ledger: UTC, starts at release adoption; not currency billing\n"
            f"Runtime currency policy: {cost_status}\n"
            f"Accounting: {'OK' if rt.ai.accounting_healthy else 'FAIL-CLOSED'}\n"
            f"Kimi store: {rt.kimi_secret_store.status()}\n"
            "Kimi activation: BLOCKED — benchmark/policy acceptance pending\n"
            "Kimi registration: /setkimikey (private operator chat only)\n"
            f"Provider ready: {rt.ai.enabled}\n"
            f"Circuit: {'OPEN' if rt.ai.circuit_open() else 'CLOSED'}\n"
            f"Knowledge chunks: {len(rt.knowledge.chunks)}\n"
            f"Knowledge load errors: {len(rt.knowledge.load_errors)}",
            _control_center_back_markup(nonce),
        )
    if action == "community":
        stats = rt.db.community_stats()
        return (
            "COMMUNITY\n"
            + "\n".join(
                f"{key}: {value}" for key, value in sorted(stats.items())
            ),
            _control_center_back_markup(nonce),
        )
    if action == "incidents":
        incidents = rt.db.list_incidents(limit=10)
        return (
            f"INCIDENTS\nRecent count shown: {len(incidents)}",
            _control_center_back_markup(nonce),
        )
    if action == "health":
        snapshot = rt.health.snapshot()
        return (
            "SYSTEM HEALTH\n"
            f"State: {snapshot.state.value}\n"
            f"Database: {'OK' if snapshot.db_ok else 'FAIL'}\n"
            f"Sensitive files: "
            f"{'PRIVATE' if snapshot.details.get('sensitive_files_private') else 'WARNING'}",
            _control_center_back_markup(nonce),
        )
    labels = {
        "domains": "DOMAINS & SECURITY\nUse os controles operacionais aprovados; nenhum segredo é exibido.",
        "announcements": "ANNOUNCEMENTS\nA superfície de anúncios permanece auditada e autorizada.",
        "configuration": "CONFIGURATION\nValores secretos nunca são exibidos neste painel.",
        "audit": "AUDIT\nAções administrativas permanecem no ledger sanitizado.",
    }
    return labels.get(action, "ZION CONTROL CENTER"), _control_center_back_markup(nonce)


async def send_control_center(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
        or update.effective_chat.type != "private"
        or update.effective_user.id
        not in runtime(context).settings.admin_user_ids
    ):
        return False
    rt = runtime(context)
    nonce = _new_control_center_session(rt, update.effective_user.id)
    text, markup = _control_center_view(rt, nonce, "main")
    await update.effective_message.reply_text(text, reply_markup=markup)
    return True


async def control_center_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if query is None or user is None or chat is None:
        return
    rt = runtime(context)
    if chat.type != "private" or user.id not in rt.settings.admin_user_ids:
        await query.answer("Não autorizado.", show_alert=True)
        return
    parts = str(query.data or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "zc1":
        await query.answer("Controle inválido.", show_alert=True)
        return
    nonce, action = parts[1], parts[2]
    session = rt.control_center_sessions.get(nonce)
    if (
        action not in CONTROL_CENTER_ACTIONS
        or session is None
        or session.operator_id != user.id
        or session.expires_at <= time.monotonic()
    ):
        rt.control_center_sessions.pop(nonce, None)
        await query.answer("Controle expirado ou inválido.", show_alert=True)
        return

    if action == "lockdown_request":
        confirm_nonce = _new_control_center_session(
            rt,
            user.id,
            confirmation_action="lockdown",
        )
        markup = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "Confirmar LOCKDOWN",
                    callback_data=_control_center_callback(
                        confirm_nonce,
                        "lockdown_confirm",
                    ),
                ),
                InlineKeyboardButton(
                    "Cancelar",
                    callback_data=_control_center_callback(
                        confirm_nonce,
                        "cancel",
                    ),
                ),
            ]]
        )
        await query.answer()
        await query.edit_message_text(
            "CONFIRMAÇÃO NECESSÁRIA\nAtivar LOCKDOWN agora?",
            reply_markup=markup,
        )
        return

    if action in {"lockdown_confirm", "cancel"}:
        rt.control_center_sessions.pop(nonce, None)
        if session.confirmation_action != "lockdown":
            await query.answer("Confirmação inválida.", show_alert=True)
            return
        if action == "cancel":
            new_nonce = _new_control_center_session(rt, user.id)
            text, markup = _control_center_view(rt, new_nonce, "main")
            await query.answer("Cancelado.")
            await query.edit_message_text(text, reply_markup=markup)
            return
        try:
            claimed = rt.db.claim_idempotency_key(
                f"control_center:lockdown:{nonce}",
                ttl_seconds=rt.settings.idempotency_retention_days * 86400,
            )
            if not claimed:
                await query.answer("Ação já processada.", show_alert=True)
                return
            with rt.db.transaction():
                rt.db.set_operating_state(OperatingState.LOCKDOWN)
                rt.db.set_setting("operating_state_expires_at", "0")
                rt.db.record_action(
                    incident_id=None,
                    chat_id=chat.id,
                    user_id=None,
                    action_type="lockdown",
                    actor_type="admin",
                    actor_id=str(user.id),
                    reason="control_center_confirmed",
                    success=True,
                )
        except Exception as exc:
            logger.error(
                "Control Center action failed | action=lockdown | error=%s",
                type(exc).__name__,
            )
            await query.answer("Ação não concluída.", show_alert=True)
            return
        await query.answer("LOCKDOWN ativado.", show_alert=True)
        await query.edit_message_text("ZION LOCKDOWN ATIVADO")
        return

    await query.answer()
    text, markup = _control_center_view(rt, nonce, action)
    await query.edit_message_text(text, reply_markup=markup)


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    record_user(update, context)
    if not update.effective_message:
        return

    if await send_control_center(update, context):
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
        "2. Sem spam ou flood, inclusive flood sustentado.\n"
        "3. Linguagem proibida, insultos dirigidos, ameaças e slurs podem "
        "ser removidos por regra determinística.\n"
        "4. Sem golpes, phishing ou impersonação.\n"
        "5. Links dependem da política vigente.\n"
        "6. Nunca envie seed phrase, chave privada ou credenciais.\n"
        "7. Administradores nunca pedirão sua seed phrase.\n"
        "8. Críticas, dúvidas e discordâncias são permitidas.\n"
        "9. As regras objetivas de conduta valem também para operadores e "
        "administradores; privilégio de comando não é isenção de conduta.\n"
        "10. Casos ambíguos não são punidos automaticamente pela IA.\n\n"
        "EN\n"
        "Be respectful. No spam or sustained flooding. Deterministic rules "
        "may remove prohibited language, directed abuse, threats and slurs. "
        "Links follow the active policy. Never share wallet secrets or "
        "credentials. Objective conduct rules also apply to operators/admins. "
        "Criticism and disagreement are allowed. Ambiguous moderation "
        "decisions are not delegated to AI.\n\n"
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
        "• Routing multiagente registra somente identidade, intenção, estado "
        "e timestamps; não grava o texto, chat, usuário ou contato.\n"
        f"• Routing e arbitration: retenção de até "
        f"{rt.settings.idempotency_retention_days} dias.\n"
        "• A qualificação de parceria é encaminhada ao operador sem criar "
        "um cadastro persistente de lead no SQLite.\n"
        "• Perguntas dirigidas ao ZION, além de /ask, /summary e /translate, "
        "podem enviar conteúdo sanitizado à Mistral quando a IA estiver "
        "habilitada.\n"
        f"• Observe-only de mensagens comuns: {observe}.\n"
        "• Possíveis segredos de carteira são bloqueados antes de chamadas "
        "de IA quando detectados pelo Guardian.\n"
        f"• Lacunas de perguntas ao ZION: retenção de "
        f"{rt.settings.knowledge_gap_retention_days} dias.\n"
        f"• Perguntas de AMA encerrado: retenção de até "
        f"{rt.settings.ama_retention_days} dias.\n"
        "• /ama armazena explicitamente a pergunta para organizar a sessão.\n"
        "• A única exceção para API key é o fluxo operador-only "
        "/setmistralkey no chat privado; a mensagem é apagada antes da "
        "persistência local.\n"
        "Nunca envie / Never send seed phrase, private key, password ou "
        "tokens por fluxos comuns."
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
    agent_core_state = (
        "ACTIVE"
        if context.application.bot_data.get("zion_multi_agent_started")
        else "STANDBY"
    )

    await update.effective_message.reply_text(
        "ZION STATUS: ONLINE\n"
        f"Operating State: {snapshot.state.value}\n"
        "Community Core: ACTIVE\n"
        f"Multi-Agent Core: {agent_core_state}\n"
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
    identity_status = snapshot.details.get(
        "telegram_identity_status",
        {},
    )
    configured_identities = sum(
        1 for value in identity_status.values() if value == "CONFIGURED"
    )

    await update.effective_message.reply_text(
        "ZION HEALTH\n"
        f"State: {snapshot.state.value}\n"
        f"Database: {'OK' if snapshot.db_ok else 'FAIL'}\n"
        f"Telegram Config: {'OK' if snapshot.telegram_configured else 'FAIL'}\n"
        f"Secondary Identities: {configured_identities}/3 configured\n"
        f"Mistral: {'READY' if rt.ai.enabled else 'OFF'}\n"
        f"Wi-Fi Interface: {'PRESENT' if snapshot.wifi_interface_present else 'MISSING'}\n"
        f"Sensitive Files: "
        f"{'PRIVATE' if snapshot.details.get('sensitive_files_private') else 'WARNING'}\n"
        f"Config: "
        f"{'OK' if not snapshot.details.get('configuration_issues') else 'WARNING'}\n"
        f"Operators: {snapshot.details.get('operator_count', 0)}\n"
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

    if not diag["disk_usage_ok"]:
        disk_state = "UNAVAILABLE"
    else:
        disk_state = "LOW" if diag["disk_low"] else "OK"

    lag_count = len(rt.update_lags)
    lag_sample_max_age = max(
        120,
        rt.settings.health_check_interval_seconds * 2,
    )
    lag_sample_age = (
        max(
            0.0,
            time.monotonic()
            - rt.update_lag_last_sample_monotonic,
        )
        if rt.update_lag_last_sample_monotonic > 0
        else None
    )
    lag_sample_fresh = (
        lag_sample_age is not None
        and lag_sample_age <= lag_sample_max_age
    )
    if not lag_count:
        lag_state = "NO-SAMPLES"
    elif not lag_sample_fresh:
        lag_state = "STALE"
    else:
        lag_state = (
            "WARNING"
            if p95_lag > rt.settings.update_lag_warn_seconds
            else "OK"
        )
    lag_age_text = (
        "n/a"
        if lag_sample_age is None
        else f"{lag_sample_age:.0f}s"
    )
    pragma_state = "OK" if diag["sqlite_pragmas_ok"] else "WARNING"
    pragma_issues = (
        ",".join(diag["sqlite_pragma_issues"])
        if diag["sqlite_pragma_issues"]
        else "NONE"
    )

    ai_used = rt.ai.tokens_used_today()
    ai_accounting_ok = rt.ai.accounting_healthy
    ai_budget = rt.settings.ai_daily_token_budget
    ai_budget_text = "unlimited" if ai_budget <= 0 else str(ai_budget)
    if not ai_accounting_ok:
        ai_remaining_text = "unavailable"
    elif ai_budget <= 0:
        ai_remaining_text = "unlimited"
    else:
        ai_remaining_text = str(max(0, ai_budget - ai_used))
    circuit_remaining = rt.ai.circuit_remaining_seconds()
    circuit_text = (
        f"OPEN ({circuit_remaining}s)"
        if circuit_remaining > 0
        else "CLOSED"
    )
    identity_status = diag.get("telegram_identity_status", {})
    identity_status_text = ",".join(
        f"{name}={value}"
        for name, value in sorted(identity_status.items())
        if name != AgentId.ZION.value
    ) or "NONE"
    routing = rt.db.routing_telemetry()
    routing_agent_text = ",".join(
        f"{agent.value}={routing['agents'].get(agent.value, {}).get('sent', 0)}"
        for agent in AgentId
    )

    scheduler_task = context.application.bot_data.get(
        "zion_scheduler_task"
    )
    scheduler_state = (
        "RUNNING"
        if isinstance(scheduler_task, asyncio.Task)
        and not scheduler_task.done()
        else "STOPPED"
    )
    housekeeping_state = (
        f"WARNING ({rt.housekeeping_last_error})"
        if rt.housekeeping_last_error
        else "OK"
    )
    checkpoint_state = (
        f"WARNING ({rt.wal_checkpoint_last_error})"
        if rt.wal_checkpoint_last_error
        else "OK"
    )
    state_maintenance = (
        f"WARNING ({rt.state_maintenance_last_error})"
        if rt.state_maintenance_last_error
        else "OK"
    )
    delivery_guard = (
        f"BLOCKED ({rt.delivery_guard_last_error})"
        if rt.delivery_guard_last_error
        else "OK"
    )
    delivery_health_gate = (
        "BLOCKED ("
        + ",".join(rt.delivery_health_block_reasons)
        + ")"
        if rt.delivery_health_blocked
        else "OPEN"
    )

    await update.effective_message.reply_text(
        "ZION DIAGNOSTICS\n"
        f"State: {diag['state']}\n"
        f"SQLite quick_check: "
        f"{'OK' if diag['sqlite_integrity_ok'] else 'FAIL'}\n"
        f"Runtime lock: "
        f"{'HELD' if rt.process_lock.acquired else 'MISSING'}\n"
        f"Scheduler: {scheduler_state}\n"
        f"Hourly housekeeping: {housekeeping_state}\n"
        f"WAL checkpoint: {checkpoint_state}\n"
        f"Temporary-state maintenance: {state_maintenance}\n"
        f"Delivery safety preflight: {delivery_guard}\n"
        f"Scheduled delivery health gate: {delivery_health_gate}\n"
        f"Alert dedup persistence: "
        f"{'DIRTY' if rt.health_alert_persistence_dirty else 'OK'}\n"
        f"Health check/repeat cadence: "
        f"{rt.settings.health_check_interval_seconds}s/"
        f"{rt.settings.health_alert_repeat_seconds}s\n"
        f"SQLite schema: v{diag['schema_version']} "
        f"(supported={diag['schema_version_supported']}) "
        f"[{'OK' if diag['schema_version_ok'] else 'WARNING'}]\n"
        f"SQLite PRAGMAs: {pragma_state} ({pragma_issues})\n"
        f"SQLite application_id: "
        f"{pragmas['application_id']} "
        f"(ZION={ZION_APPLICATION_ID})\n"
        f"SQLite journal/FK enforcement: "
        f"{pragmas['journal_mode']}/{pragmas['foreign_keys']}\n"
        f"SQLite FK integrity: "
        f"{'OK' if diag['sqlite_foreign_keys_ok'] else 'FAIL'}\n"
        f"SQLite synchronous: {pragmas['synchronous']} (FULL=2)\n"
        f"SQLite trusted_schema: {pragmas['trusted_schema']} (OFF=0)\n"
        f"SQLite WAL autocheckpoint: "
        f"{pragmas['wal_autocheckpoint']} pages\n"
        f"SQLite journal size limit: "
        f"{pragmas['journal_size_limit']} bytes\n"
        f"SQLite busy timeout: {pragmas['busy_timeout_ms']} ms\n"
        f"SQLite total/db/WAL/SHM: "
        f"{diag['db_size_mb']}/{diag['db_file_mb']}/"
        f"{diag['wal_size_mb']}/{diag['shm_size_mb']} MB\n"
        f"SQLite DB threshold: {diag['db_warn_mb']} MB "
        f"[{'WARNING' if diag['db_large'] else 'OK'}]\n"
        f"SQLite WAL threshold: {diag['wal_warn_mb']} MB "
        f"[{'WARNING' if diag['wal_large'] else 'OK'}]\n"
        f"Disk: {disk_state} ({diag['disk_free_mb']} MB free)\n"
        f"Sensitive files: "
        f"{'PRIVATE' if diag['sensitive_files_private'] else 'WARNING'}\n"
        f"Wi-Fi interface: "
        f"{'PRESENT' if diag['wifi_interface_present'] else 'MISSING'}\n"
        f"Telegram update lag latest/p95/n: "
        f"{latest_lag:.2f}s/{p95_lag:.2f}s/{lag_count} "
        f"[{lag_state}; age={lag_age_text}]\n"
        f"AI latency 24h avg/p95: "
        f"{latency['avg_ms']}ms/{latency['p95_ms']}ms "
        f"(n={latency['count']}) "
        f"[{'OK' if diag['ai_latency_read_ok'] else 'UNAVAILABLE'}]\n"
        f"AI enabled/provider ready: "
        f"{rt.settings.ai_enabled}/{rt.ai.enabled}\n"
        f"Mistral secret: {diag['mistral_secret_status']}\n"
        f"Telegram identity stores: {identity_status_text}\n"
        f"Routing responses sent: {routing_agent_text}\n"
        f"Routing suppressed/ambiguous/handoffs: "
        f"{routing['suppressed']}/{routing['ambiguous']}/{routing['handoffs']}\n"
        f"Routing DM denied/failures: "
        f"{routing['dm_denied']}/{routing['routing_failures']}\n"
        f"AI accounting: "
        f"{'OK' if ai_accounting_ok else 'FAIL-CLOSED'}\n"
        f"AI tokens UTC used/budget/remaining: "
        f"{ai_used}/{ai_budget_text}/{ai_remaining_text}\n"
        f"AI circuit: {circuit_text}\n"
        f"AI provider failures: {rt.ai.circuit_failures}/"
        f"{rt.settings.ai_circuit_failures}\n"
        f"Operators: {diag['operator_count']}\n"
        f"Knowledge: {len(rt.knowledge.chunks)} chunks / "
        f"{len(rt.knowledge.load_errors)} errors\n"
        f"Config issues: "
        f"{', '.join(diag['configuration_issues']) if diag['configuration_issues'] else 'NONE'}"
    )


MISTRAL_SECRET_CAPTURE_TTL_SECONDS = 120


def _explicit_operator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(
        update.effective_user
        and update.effective_user.id
        in runtime(context).settings.admin_user_ids
    )


async def _send_secret_status(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.warning(
            "Falha ao enviar status de provisionamento Mistral: %s",
            type(exc).__name__,
        )


def _audit_mistral_secret_operation(
    rt: Runtime,
    *,
    chat_id: int,
    user_id: int,
    operation: str,
    success: bool,
) -> bool:
    try:
        rt.db.record_action(
            incident_id=None,
            chat_id=chat_id,
            user_id=user_id,
            action_type=(
                "mistral_key_set"
                if operation in {"set", "rotate"}
                else "mistral_key_clear"
            ),
            actor_type="operator",
            actor_id=str(user_id),
            reason="private_secret_provisioning",
            success=success,
            metadata={
                "secret": "mistral",
                "operation": operation,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "Falha ao registrar auditoria de segredo Mistral: %s",
            type(exc).__name__,
        )
        return False


async def set_mistral_key_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or not _explicit_operator(update, context):
        if message:
            await message.reply_text(
                "⛔ Comando restrito aos operadores explícitos do ZION."
            )
        return

    if chat.type != "private":
        await message.reply_text(
            "Use este comando no chat privado com o ZION."
        )
        return

    if context.args:
        register_sensitive_value(" ".join(context.args).strip())
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        await _send_secret_status(
            context,
            chat.id,
            (
                "A chave não pode ser enviada no comando. "
                "A mensagem foi removida; use /setmistralkey sem argumentos."
                if deleted
                else
                "Não consegui remover o comando que continha dados após "
                "/setmistralkey. Exclua a mensagem manualmente."
            ),
        )
        return

    rt = runtime(context)
    if rt.secret_store.status() == SecretStore.UNSAFE:
        await message.reply_text(
            "O cofre local da Mistral está em estado inseguro. "
            "A chave não será recebida até o host ser corrigido."
        )
        return

    from .kimi_provisioning import clear_pending_kimi_capture
    try:
        clear_pending_kimi_capture(rt, chat.id, update.effective_user.id)
    except Exception:
        await message.reply_text("Não foi possível preparar o recebimento seguro. Não envie a chave.")
        return
    rt.mistral_secret_captures[(chat.id, update.effective_user.id)] = (
        time.monotonic() + MISTRAL_SECRET_CAPTURE_TTL_SECONDS
    )
    await message.reply_text(
        "Envie a chave Mistral na próxima mensagem.\n"
        "Ela será processada como segredo e removida do chat antes de ser "
        "armazenada.\n"
        "A solicitação expira em 120 segundos."
    )


async def mistral_secret_capture_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type != "private":
        return

    rt = runtime(context)
    capture_key = (chat.id, user.id)
    if user.id not in rt.settings.admin_user_ids:
        rt.mistral_secret_captures.pop(capture_key, None)
        return

    expires_at = rt.mistral_secret_captures.get(capture_key)
    if expires_at is None:
        return
    if time.monotonic() > expires_at:
        rt.mistral_secret_captures.pop(capture_key, None)
        return

    text = message.text or ""
    if not text or text.startswith("/"):
        return

    # One attempt consumes the in-memory capture. The raw message must be
    # deleted before validation, provider I/O, persistence or audit writes.
    rt.mistral_secret_captures.pop(capture_key, None)

    deleted = await delete_message_safe(
        context,
        chat.id,
        message.message_id,
    )
    if not deleted:
        await _send_secret_status(
            context,
            chat.id,
            "Não consegui remover a mensagem com segurança. "
            "A chave não foi armazenada. Exclua a mensagem e tente novamente.",
        )
        raise ApplicationHandlerStop

    try:
        candidate = SecretStore.normalize_candidate(text)
    except SecretValidationError:
        await _send_secret_status(
            context,
            chat.id,
            "A chave recebida não possui um formato seguro válido. "
            "Nada foi armazenado.",
        )
        raise ApplicationHandlerStop

    existing_status = rt.secret_store.status()
    if existing_status == SecretStore.UNSAFE:
        await _send_secret_status(
            context,
            chat.id,
            "O cofre local da Mistral está inseguro. Nada foi armazenado.",
        )
        raise ApplicationHandlerStop

    operation = (
        "rotate"
        if existing_status == SecretStore.PRIVATE
        else "set"
    )

    try:
        await rt.ai.client.validate_api_key(candidate)
    except MistralCredentialInvalid:
        _audit_mistral_secret_operation(
            rt,
            chat_id=chat.id,
            user_id=user.id,
            operation=operation,
            success=False,
        )
        await _send_secret_status(
            context,
            chat.id,
            "A Mistral rejeitou a credencial. "
            "A chave anterior, se existente, foi preservada.",
        )
        raise ApplicationHandlerStop
    except MistralCredentialValidationUnavailable:
        _audit_mistral_secret_operation(
            rt,
            chat_id=chat.id,
            user_id=user.id,
            operation=operation,
            success=False,
        )
        await _send_secret_status(
            context,
            chat.id,
            "Não foi possível validar a credencial Mistral agora. "
            "Nada foi alterado; tente novamente mais tarde.",
        )
        raise ApplicationHandlerStop
    except Exception as exc:
        logger.error(
            "Falha inesperada na validação Mistral: %s",
            type(exc).__name__,
        )
        _audit_mistral_secret_operation(
            rt,
            chat_id=chat.id,
            user_id=user.id,
            operation=operation,
            success=False,
        )
        await _send_secret_status(
            context,
            chat.id,
            "A validação da credencial falhou de forma segura. "
            "Nada foi armazenado.",
        )
        raise ApplicationHandlerStop

    try:
        previous_secret = (
            rt.secret_store.read()
            if existing_status == SecretStore.PRIVATE
            else None
        )
    except Exception as exc:
        logger.warning(
            "Falha ao ler estado anterior do cofre Mistral: %s",
            type(exc).__name__,
        )
        await _send_secret_status(
            context,
            chat.id,
            "O estado anterior do cofre não pôde ser confirmado. "
            "Nada foi alterado.",
        )
        raise ApplicationHandlerStop

    try:
        rt.secret_store.write_atomic(candidate)
    except Exception as exc:
        logger.warning(
            "Falha no cofre local Mistral: %s",
            type(exc).__name__,
        )
        _audit_mistral_secret_operation(
            rt,
            chat_id=chat.id,
            user_id=user.id,
            operation=operation,
            success=False,
        )
        await _send_secret_status(
            context,
            chat.id,
            "A credencial foi validada, mas o cofre local recusou a "
            "persistência. A chave anterior, se existente, foi preservada.",
        )
        raise ApplicationHandlerStop

    if not _audit_mistral_secret_operation(
        rt,
        chat_id=chat.id,
        user_id=user.id,
        operation=operation,
        success=True,
    ):
        try:
            if previous_secret is None:
                rt.secret_store.clear()
            else:
                rt.secret_store.write_atomic(previous_secret)
        except Exception as exc:
            logger.error(
                "Falha ao reverter segredo Mistral após auditoria: %s",
                type(exc).__name__,
            )
            await _send_secret_status(
                context,
                chat.id,
                "A auditoria da alteração falhou e a reversão local não "
                "pôde ser confirmada. Não envie outra chave até revisão "
                "do host.",
            )
            raise ApplicationHandlerStop

        await _send_secret_status(
            context,
            chat.id,
            "A auditoria da alteração falhou. "
            "A mudança foi revertida e nenhuma nova chave ficou ativa.",
        )
        raise ApplicationHandlerStop

    await _send_secret_status(
        context,
        chat.id,
        "Mistral configurada com sucesso.\n"
        "A chave foi armazenada no cofre local protegido do ZION.\n"
        "Use /aistatus para verificar.",
    )
    raise ApplicationHandlerStop


async def clear_mistral_key_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or not _explicit_operator(update, context):
        if message:
            await message.reply_text(
                "⛔ Comando restrito aos operadores explícitos do ZION."
            )
        return

    if chat.type != "private":
        await message.reply_text(
            "Use este comando no chat privado com o ZION."
        )
        return

    if [arg.upper() for arg in context.args] != ["CONFIRM"]:
        await message.reply_text(
            "Isso desativa o provider Mistral até uma nova chave ser "
            "configurada.\n"
            "Confirme com /clearmistralkey CONFIRM."
        )
        return

    rt = runtime(context)
    status = rt.secret_store.status()
    if status == SecretStore.UNSAFE:
        await message.reply_text(
            "O cofre local está inseguro; a remoção automática foi recusada."
        )
        return
    if status == SecretStore.MISSING:
        await message.reply_text("A credencial Mistral já está ausente.")
        return

    try:
        previous_secret = rt.secret_store.read()
    except Exception as exc:
        logger.warning(
            "Falha ao ler segredo antes da remoção Mistral: %s",
            type(exc).__name__,
        )
        await message.reply_text(
            "O estado atual do cofre não pôde ser confirmado; "
            "nenhuma remoção foi tentada."
        )
        return

    try:
        removed = rt.secret_store.clear()
    except Exception as exc:
        logger.warning(
            "Falha ao remover segredo Mistral: %s",
            type(exc).__name__,
        )
        await message.reply_text(
            "Não foi possível remover a credencial com segurança."
        )
        return

    if removed and not _audit_mistral_secret_operation(
        rt,
        chat_id=chat.id,
        user_id=user.id,
        operation="clear",
        success=True,
    ):
        try:
            if previous_secret is not None:
                rt.secret_store.write_atomic(previous_secret)
        except Exception as exc:
            logger.error(
                "Falha ao restaurar segredo Mistral após auditoria: %s",
                type(exc).__name__,
            )
            await message.reply_text(
                "A auditoria da remoção falhou e a restauração não pôde "
                "ser confirmada. Revise o host antes de continuar."
            )
            return

        await message.reply_text(
            "A auditoria da remoção falhou. "
            "A credencial anterior foi restaurada."
        )
        return

    await message.reply_text(
        "Credencial Mistral removida. "
        "O Guardian determinístico continua ativo."
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
    secret_status = rt.secret_store.status()
    key_state = (
        "CONFIGURED"
        if secret_status == SecretStore.PRIVATE
        else secret_status
    )
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
        f"Enabled by config: {rt.settings.ai_enabled}\n"
        f"Provider ready: {rt.ai.enabled}\n"
        f"API credential: {key_state}\n"
        "Secret source: LOCAL PROTECTED STORE\n"
        f"Observe-only moderation: {rt.settings.ai_observe}\n"
        "Intent routing fallback: BOUNDED / NO MODERATION AUTHORITY\n"
        f"Circuit breaker: {circuit_text}\n"
        f"Provider failures: {rt.ai.circuit_failures}/"
        f"{rt.settings.ai_circuit_failures}\n"
        f"Accounting: {'OK' if rt.ai.accounting_healthy else 'FAIL-CLOSED'}\n"
        f"Tokens today UTC: {used}/{budget_text}\n"
        f"Knowledge chunks: {len(rt.knowledge.chunks)}\n"
        f"Knowledge load errors: {len(rt.knowledge.load_errors)}"
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
    await update.effective_message.reply_text(
        telegram_ai_reply_text(answer.text)
    )


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
        "/ask <pergunta> — suporte fundamentado na base oficial (opcional)\n"
        "Você também pode conversar normalmente com o ZION no privado ou "
        "chamá-lo pelo nome no grupo.\n"
        "/summary <texto> — resumo explícito via IA quando habilitada\n"
        "/translate <idioma> <texto> — tradução explícita via IA\n"
        "/report — responda a uma mensagem para denunciar\n"
        "/ama <pergunta> — envia pergunta ao AMA ativo\n\n"
        "OPERADOR / OPERATOR (chat privado)\n"
        "/aistatus — estado da IA sem expor credenciais\n"
        "/setmistralkey — inicia captura protegida da chave Mistral\n"
        "/clearmistralkey — remoção protegida com confirmação\n\n"
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
    await update.effective_message.reply_text(
        telegram_ai_reply_text(answer.text)
    )


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
    await update.effective_message.reply_text(
        telegram_ai_reply_text(answer.text)
    )


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
        f"Flood burst: {rt.settings.flood_max_messages} msgs/"
        f"{rt.settings.flood_window_seconds}s\n"
        f"Flood sustained: {rt.settings.flood_sustained_max_messages} msgs/"
        f"{rt.settings.flood_sustained_window_seconds}s\n"
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
        f"Uncertain scheduled: {community['uncertain_scheduled']}\n"
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
            f"{safe_display_text(item['sample_text'], 220)}"
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

    rt = runtime(context)
    question_hash = context.args[0].strip()
    with rt.db.transaction():
        success = rt.db.set_knowledge_gap_status(
            question_hash,
            "resolved",
        )
        rt.db.record_action(
            incident_id=None,
            chat_id=(
                update.effective_chat.id
                if update.effective_chat
                else None
            ),
            user_id=None,
            action_type="knowledge_gap_resolve",
            actor_type="operator",
            actor_id=(
                str(update.effective_user.id)
                if update.effective_user
                else None
            ),
            reason="manual_operator_command",
            success=success,
            metadata={"question_hash": question_hash[:128]},
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
        evidence_text = safe_display_text(evidence, 900)
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
        f"Note: {safe_display_text(incident.get('note') or '-', 500)}\n"
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

    with rt.db.transaction():
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
            f"{safe_display_text(item['reason'], 200)} | exp={expires_text}"
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
        f"Username: {safe_display_text(user.get('username') or '-', 80)}\n"
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

    with rt.db.transaction():
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
    with rt.db.transaction():
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
    with rt.db.transaction():
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

    rt = runtime(context)
    with rt.db.transaction():
        rt.db.set_domain(domain, "allow", "operator")
        rt.db.record_action(
            incident_id=None,
            chat_id=(
                update.effective_chat.id
                if update.effective_chat
                else None
            ),
            user_id=None,
            action_type="domain_policy_change",
            actor_type="operator",
            actor_id=(
                str(update.effective_user.id)
                if update.effective_user
                else None
            ),
            reason="manual_operator_command",
            success=True,
            metadata={
                "domain": domain,
                "disposition": "allow",
            },
        )
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

    rt = runtime(context)
    with rt.db.transaction():
        rt.db.set_domain(domain, "block", "operator")
        rt.db.record_action(
            incident_id=None,
            chat_id=(
                update.effective_chat.id
                if update.effective_chat
                else None
            ),
            user_id=None,
            action_type="domain_policy_change",
            actor_type="operator",
            actor_id=(
                str(update.effective_user.id)
                if update.effective_user
                else None
            ),
            reason="manual_operator_command",
            success=True,
            metadata={
                "domain": domain,
                "disposition": "block",
            },
        )
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
    with rt.db.transaction():
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

    rt = runtime(context)
    # Persist intent before the irreversible Telegram side effect. If this
    # write fails, fail closed and do not mute. The outcome is recorded after
    # Telegram returns; the incident remains evidence if that second write fails.
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="manual_mute",
        severity=Severity.MEDIUM,
        source="admin",
        evidence={
            "duration_seconds": seconds,
            "requested_by_user_id": update.effective_user.id,
        },
    )
    success = await mute_user_safe(
        context,
        update.effective_chat.id,
        target.id,
        seconds,
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

    rt = runtime(context)
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target.id,
        category="manual_ban",
        severity=Severity.HIGH,
        source="admin",
        evidence={
            "requested_by_user_id": update.effective_user.id,
        },
    )
    success = await ban_user_safe(
        context,
        update.effective_chat.id,
        target.id,
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

    rt = runtime(context)
    incident_id = rt.db.create_incident(
        chat_id=update.effective_chat.id,
        user_id=target_id,
        category="manual_unban",
        severity=Severity.INFO,
        source="admin",
        evidence={
            "requested_by_user_id": update.effective_user.id,
        },
    )
    success = await unban_user_safe(
        context,
        update.effective_chat.id,
        target_id,
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

    rt = runtime(context)
    if not rt.report_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Limite temporário de denúncias atingido. Tente novamente em instantes."
        )
        return

    reason = " ".join(context.args).strip() or "user_report"
    incident_id = rt.db.create_incident(
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
        f"Scheduled failed / uncertain: "
        f"{community['failed_scheduled']}/{community['uncertain_scheduled']}\n"
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

    rt = runtime(context)
    with rt.db.transaction():
        schedule_id = rt.db.schedule_message(
            chat_id=update.effective_chat.id,
            send_at=send_at,
            text=text[:3500],
            created_by=update.effective_user.id,
        )
        rt.db.record_action(
            incident_id=None,
            chat_id=update.effective_chat.id,
            user_id=None,
            action_type="scheduled_create",
            actor_type="admin",
            actor_id=str(update.effective_user.id),
            reason="manual_admin_command",
            success=True,
            metadata={
                "schedule_id": schedule_id,
                "send_at": send_at,
            },
        )
    await update.effective_message.reply_text(
        f"📅 Mensagem agendada: {schedule_id[:8]} para {when.isoformat()}."
    )


async def cancel_scheduled_command(
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
            "Use: /cancelscheduled <id-ou-prefixo>"
        )
        return

    reference = context.args[0].strip()
    rt = runtime(context)
    with rt.db.transaction():
        success = rt.db.cancel_scheduled_message(
            reference,
            chat_id=update.effective_chat.id,
        )
        rt.db.record_action(
            incident_id=None,
            chat_id=update.effective_chat.id,
            user_id=None,
            action_type="scheduled_cancel",
            actor_type="admin",
            actor_id=str(update.effective_user.id),
            reason="manual_admin_command",
            success=success,
            metadata={"schedule_ref": reference[:32]},
        )
    await update.effective_message.reply_text(
        "Agendamento cancelado."
        if success
        else "Agendamento não encontrado, já enviado ou prefixo ambíguo."
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

    rt = runtime(context)
    with rt.db.transaction():
        schedule_id = rt.db.schedule_recurring_message(
            chat_id=update.effective_chat.id,
            first_send_at=first.timestamp(),
            interval_seconds=interval,
            text=text,
            created_by=update.effective_user.id,
        )
        rt.db.record_action(
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
    with rt.db.transaction():
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

    now = time.time()
    lines = ["ZION DELIVERY JOBS", "", "ONE-SHOT"]
    if not scheduled:
        lines.append("none")
    for item in scheduled:
        claimed_at = item.get("claimed_at")
        claim_age = (
            f"{max(0, int(now - float(claimed_at)))}s"
            if claimed_at is not None
            else "-"
        )
        error = str(item.get("last_error_type") or "-")
        lines.append(
            f"{str(item['id'])[:8]} | {item['status']} | "
            f"chat={item['chat_id']} | attempts={item['attempts']} | "
            f"claim_age={claim_age} | error={error[:40]}"
        )

    lines.extend(["", "RECURRING"])
    if not recurring:
        lines.append("none")
    for item in recurring:
        claimed_at = item.get("claimed_at")
        claim_age = (
            f"{max(0, int(now - float(claimed_at)))}s"
            if claimed_at is not None
            else "-"
        )
        error = str(item.get("last_error_type") or "-")
        lines.append(
            f"{str(item['id'])[:8]} | {item['status']} | "
            f"chat={item['chat_id']} | "
            f"failures={item['consecutive_failures']} | "
            f"claim_age={claim_age} | error={error[:40]}"
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
    with rt.db.transaction():
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
        (
            "Agendamento reenfileirado. Se o estado anterior era UNCERTAIN, "
            "esta é uma reexecução explícita e pode duplicar uma entrega "
            "cujo resultado não pôde ser confirmado."
        )
        if success
        else (
            "Agendamento FAILED/UNCERTAIN não encontrado "
            "ou prefixo ambíguo."
        )
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
    with rt.db.transaction():
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
        (
            "Recorrência retomada. Se a pausa veio de um resultado "
            "desconhecido após crash, a ocorrência incerta é pulada e "
            "o próximo ciclo futuro é preservado."
        )
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

    with rt.db.transaction():
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
        f"🎙️ AMA aberto: {safe_display_text(title, 200)}\n"
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

    if not rt.ama_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Limite temporário de perguntas do AMA atingido. "
            "Tente novamente em instantes."
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
        f"🎙️ AMA: {safe_display_text(active['title'], 200)}",
        f"ID: {str(active['id'])[:8]}",
        f"Perguntas: {len(questions)}",
    ]
    for item in questions:
        lines.append(
            f"{str(item['id'])[:8]} | user={item['user_id']} | "
            f"{safe_display_text(item['question'], 220)}"
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

    rt = runtime(context)
    with rt.db.transaction():
        closed = rt.db.close_ama(update.effective_chat.id)
        if closed:
            rt.db.record_action(
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
    if not closed:
        await update.effective_message.reply_text(
            "Não há AMA aberto neste chat."
        )
        return

    await update.effective_message.reply_text(
        f"🎙️ AMA encerrado: {safe_display_text(closed['title'], 200)}"
    )


async def reload_knowledge_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not await require_operator(update, context):
        return
    if not update.effective_message:
        return

    rt = runtime(context)
    knowledge = rt.knowledge
    count = knowledge.reload()
    rt.db.record_action(
        incident_id=None,
        chat_id=(
            update.effective_chat.id
            if update.effective_chat
            else None
        ),
        user_id=None,
        action_type="knowledge_reload",
        actor_type="operator",
        actor_id=(
            str(update.effective_user.id)
            if update.effective_user
            else None
        ),
        reason="manual_operator_command",
        success=not knowledge.load_errors,
        metadata={
            "chunks": count,
            "load_error_count": len(knowledge.load_errors),
        },
    )
    await update.effective_message.reply_text(
        f"Knowledge base recarregada: {count} blocos | "
        f"errors={len(knowledge.load_errors)}."
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
    members = [
        member
        for member in (
            getattr(update.effective_message, "new_chat_members", None)
            or []
        )
        if not getattr(member, "is_bot", False)
    ]
    if not members:
        return

    now = time.time()
    update_id = getattr(update, "update_id", None)
    raid_triggered = False
    joins = 0

    try:
        with rt.db.transaction():
            if update_id is not None:
                claimed = rt.db.claim_idempotency_key(
                    f"telegram_welcome:{int(update_id)}",
                    ttl_seconds=(
                        rt.settings.idempotency_retention_days * 86400
                    ),
                    now=now,
                )
                if not claimed:
                    logger.warning(
                        "Welcome update duplicado suprimido | update_id=%s",
                        update_id,
                    )
                    return

            for member in members:
                rt.db.upsert_user(
                    chat_id=chat_id,
                    user_id=member.id,
                    username=getattr(member, "username", None),
                    first_name=getattr(member, "first_name", None),
                    language_code=getattr(member, "language_code", None),
                    now=now,
                )
                rt.db.record_user_event(
                    chat_id,
                    member.id,
                    "joined",
                    now=now,
                )

            # Count and state transition are part of the same local transaction
            # as the join event. A crash after commit cannot leave the raid
            # counter updated but the corresponding local state decision absent.
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
                raid_triggered = True
    except Exception as exc:
        logger.error(
            "Falha ao persistir onboarding/raid counters: %s",
            type(exc).__name__,
        )
        return

    if len(members) == 1:
        name = (
            safe_display_text(
                getattr(members[0], "first_name", None),
                80,
            )
            or "novo membro"
        )
        welcome_text = (
            f"⚡ Bem-vindo(a) / Welcome, {name}!\n\n"
            "PT-BR: Você entrou na comunidade Z-SWAP. "
            "Leia /rules, consulte /help e use /report para sinalizar problemas.\n"
            "EN: Welcome to the Z-SWAP community. "
            "Read /rules, check /help and use /report to flag issues.\n\n"
            "🔐 Nunca compartilhe / Never share seed phrase, private key, "
            "password, token or API key."
        )
    else:
        welcome_text = (
            f"⚡ {len(members)} novos membros / new members chegaram.\n\n"
            "PT-BR: Bem-vindos à comunidade Z-SWAP. "
            "Leiam /rules e /help.\n"
            "EN: Welcome to the Z-SWAP community. "
            "Read /rules and /help.\n\n"
            "🔐 Nunca compartilhe / Never share seed phrase, private key, "
            "password, token or API key."
        )

    try:
        await update.effective_message.reply_text(welcome_text)
    except Exception as exc:
        logger.warning(
            "Falha ao enviar onboarding: %s",
            type(exc).__name__,
        )

    if raid_triggered:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🛡️ ZION: volume anormal de entradas detectado.\n"
                    "Estado ELEVATED ativado temporariamente.\n"
                    "O limite de flood foi endurecido; nenhuma punição "
                    "por IA foi habilitada."
                ),
            )
        except Exception as exc:
            logger.warning(
                "Falha ao publicar alerta de mass join: %s",
                type(exc).__name__,
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


async def _enforce_abuse(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    decision: AbuseDecision,
    *,
    active_containment_seconds: int = 0,
) -> None:
    if (
        not decision.detected
        or not update.effective_message
        or not update.effective_user
        or not update.effective_chat
    ):
        return

    rt = runtime(context)
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    now = time.time()

    deleted = await delete_message_safe(
        context,
        chat.id,
        message.message_id,
    )

    already_contained = active_containment_seconds > 0
    strike_count = 0
    mute_seconds = 0
    mute_required = False
    with rt.db.transaction():
        incident_id = rt.db.create_incident(
            chat_id=chat.id,
            user_id=user.id,
            category=decision.category,
            severity=decision.severity,
            source="guardian",
            evidence={
                "message_id": message.message_id,
                "rule_id": decision.rule_id,
                "normalized_hash": decision.normalized_hash,
                "directed": decision.directed,
                "reporting_context": decision.reporting_context,
                "active_containment": already_contained,
                "content_not_stored": True,
            },
            note=(
                "Deterministic community-language rule matched; "
                "offending message body was not persisted."
            ),
            now=now,
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat.id,
            user_id=user.id,
            action_type="delete",
            actor_type="guardian",
            actor_id=None,
            reason=decision.category,
            success=deleted,
            metadata={
                "rule_id": decision.rule_id,
                "active_containment": already_contained,
                "content_not_stored": True,
            },
            now=now,
        )

        if decision.should_strike and not already_contained:
            rt.db.add_strike(
                chat_id=chat.id,
                user_id=user.id,
                reason=decision.category,
                severity=decision.severity,
                source="guardian",
                ttl_seconds=rt.settings.flood_strike_reset_seconds,
                metadata={
                    "rule_id": decision.rule_id,
                    "normalized_hash": decision.normalized_hash,
                    "directed": decision.directed,
                },
                now=now,
            )
            strike_count = rt.db.count_active_strikes(
                chat.id,
                user.id,
                now,
                reasons=(
                    "prohibited_language",
                    "directed_abuse",
                    "explicit_sexual_language",
                    "adult_site_reference",
                    "threat",
                    "slur_or_hate",
                    # Count strikes recorded before the categories were split.
                    "threat_or_slur",
                ),
            )
            mute_required = (
                decision.immediate_mute
                or strike_count >= 2
                or not deleted
            )
            if mute_required:
                level_index = min(
                    max(0, strike_count - 1),
                    len(rt.settings.flood_mute_levels) - 1,
                )
                mute_seconds = rt.settings.flood_mute_levels[level_index]
                rt.db.set_containment(
                    chat.id,
                    user.id,
                    now + mute_seconds,
                    decision.category,
                    now,
                )

    if not deleted:
        await _alert_operators_enforcement_failure(
            context,
            chat_id=chat.id,
            target_user_id=user.id,
            action="delete",
            reason=decision.category,
        )

    mute_success: bool | None = None
    if mute_required:
        mute_success = await mute_user_safe(
            context,
            chat.id,
            user.id,
            mute_seconds,
        )
        rt.db.record_action(
            incident_id=incident_id,
            chat_id=chat.id,
            user_id=user.id,
            action_type="mute",
            actor_type="guardian",
            actor_id=None,
            reason=decision.category,
            success=mute_success,
            metadata={
                "duration_seconds": mute_seconds,
                "strike_count": strike_count,
                "local_containment": True,
            },
        )
        if not mute_success:
            await _alert_operators_enforcement_failure(
                context,
                chat_id=chat.id,
                target_user_id=user.id,
                action="mute",
                reason=decision.category,
            )

    if already_contained and deleted:
        # Do not flood the group with repeated notices while the member is
        # already contained. The incident remains classified as abuse.
        return
    if already_contained:
        outcome = (
            "Ofensa detectada, mas o Telegram não confirmou a remoção. "
            "A contenção continua ativa e a equipe foi alertada."
        )
    elif not deleted and mute_required and mute_success:
        outcome = (
            "Ofensa detectada, mas o Telegram não confirmou a remoção; "
            f"usuário silenciado por {format_duration(mute_seconds)} e "
            "equipe alertada."
        )
    elif not deleted and mute_required:
        outcome = (
            "Ofensa detectada, mas o Telegram não confirmou a remoção nem "
            "o bloqueio externo. A contenção local foi mantida e a equipe "
            "foi alertada."
        )
    elif not deleted:
        outcome = (
            "Conteúdo impróprio detectado, mas o Telegram não confirmou a "
            "remoção. A equipe foi alertada para revisão."
        )
    elif decision.reporting_context:
        outcome = (
            "Mensagem removida pela regra de linguagem; contexto de "
            "citação/relato não recebeu punição automática."
        )
    elif mute_required and mute_success:
        outcome = (
            f"Mensagem removida e usuário silenciado por "
            f"{format_duration(mute_seconds)}."
        )
    elif mute_required:
        outcome = (
            "Mensagem removida. A restrição externa falhou; a contenção "
            "local foi mantida e um operador autorizado deve revisar."
        )
    elif decision.should_strike:
        outcome = (
            f"Mensagem removida e ocorrência registrada "
            f"({strike_count}). Reincidência pode gerar mute."
        )
    else:
        outcome = "Mensagem removida pela política de linguagem."

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"⚠️ {user_display_name(user)}: {outcome}",
        )
    except Exception as exc:
        logger.warning(
            "Falha ao publicar aviso de moderação de linguagem: %s",
            type(exc).__name__,
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

    if deleted_count < len(flood.message_ids):
        await _alert_operators_enforcement_failure(
            context,
            chat_id=chat.id,
            target_user_id=user.id,
            action="delete",
            reason=flood.reason,
        )

    incident_id = flood.incident_id
    if not incident_id:
        # Backward-compatible fallback for callers/tests that construct a
        # FloodDecision directly instead of using Guardian.record_message().
        incident_id = rt.db.create_incident(
            chat_id=chat.id,
            user_id=user.id,
            category=flood.reason,
            severity=(
                Severity.HIGH
                if flood.should_ban
                else Severity.MEDIUM
            ),
            source="guardian",
            evidence={
                "strike_count": flood.strike_count,
                "tracked_messages": len(flood.message_ids),
                "planned_action": "ban" if flood.should_ban else "mute",
            },
        )

    if flood.should_ban:
        success = await ban_user_safe(context, chat.id, user.id)
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
        reason=flood.reason,
        success=success,
        metadata={
            "strike_count": flood.strike_count,
            "duration_seconds": flood.mute_seconds,
            "deleted_messages": deleted_count,
        },
    )
    if not success:
        await _alert_operators_enforcement_failure(
            context,
            chat_id=chat.id,
            target_user_id=user.id,
            action=action_type,
            reason=flood.reason,
        )

    if flood.should_ban and success:
        # Outcome is durably recorded before local cleanup. A DB failure in
        # cleanup therefore cannot erase evidence of a successful external ban.
        rt.db.clear_containment(chat.id, user.id)
        action_text = "banido por reincidência objetiva de flood."
    elif flood.should_ban:
        # Se o ban falhar, aplicamos contenção/mute como fallback
        # e registramos a segunda ação separadamente no ledger.
        rt.db.set_containment(
            chat.id,
            user.id,
            time.time() + flood.mute_seconds,
            f"{flood.reason}_ban_fallback",
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
            reason=f"{flood.reason}_ban_fallback",
            success=fallback_success,
            metadata={
                "duration_seconds": flood.mute_seconds,
            },
        )
        if not fallback_success:
            await _alert_operators_enforcement_failure(
                context,
                chat_id=chat.id,
                target_user_id=user.id,
                action="mute",
                reason=f"{flood.reason}_ban_fallback",
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
            if success
            else (
                "mute falhou; contenção local mantida e um operador "
                "autorizado deve revisar."
            )
        )

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"⚠️ {user_display_name(user)}: "
                f"{'flood sustentado' if flood.reason == 'sustained_flood' else 'flood'} "
                "detectado.\n"
                f"{deleted_count} mensagens removidas.\n"
                f"Ocorrência {flood.strike_count}/"
                f"{rt.settings.flood_ban_after_strikes}.\n"
                f"{action_text}"
            ),
        )
    except Exception as exc:
        logger.warning("Falha ao publicar aviso de flood: %s", exc)


async def command_idempotency_guard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    # Secret deletion must precede the durable command claim. Otherwise a
    # crash after claiming but before the next handler group could suppress
    # Telegram redelivery while leaving a credential visible.
    message = update.effective_message
    if message is not None:
        visible = message.text or message.caption or ""
        stripped = visible.strip()
        command_parts = stripped.split(maxsplit=1)
        command_head = command_parts[0] if command_parts else ""
        command_name = command_head.split("@", 1)[0].lower()
        if command_name in {"/setmistralkey", "/setkimikey"} and len(command_parts) > 1:
            register_sensitive_value(command_parts[1].strip())
            chat = update.effective_chat
            deleted = bool(
                chat
                and await delete_message_safe(
                    context,
                    chat.id,
                    message.message_id,
                )
            )
            if chat:
                await _send_secret_status(
                    context,
                    chat.id,
                    (
                        "A chave não pode ser enviada no comando. "
                        f"A mensagem foi removida; use {command_name} sem "
                        "argumentos."
                        if deleted
                        else
                        "Não consegui remover o comando que continha dados "
                        f"após {command_name}. Exclua a mensagem manualmente."
                    ),
                )
            raise ApplicationHandlerStop

        sensitive_surface = telegram_sensitive_surface(
            message,
            visible,
        )
        if await protect_credential_exposure(
            update,
            context,
            sensitive_surface,
            source="guardian_command_idempotency_preflight",
            notice_text=(
                "🚨 ZION bloqueou um comando que aparentava conter "
                "uma credencial. O conteúdo não foi processado."
            ),
        ):
            raise ApplicationHandlerStop
        if await protect_wallet_secret(
            update,
            context,
            sensitive_surface,
            source="guardian_command_idempotency_preflight",
            notice_text=(
                "🚨 ZION bloqueou um comando que aparentava conter "
                "segredo de carteira. O conteúdo não foi processado."
            ),
        ):
            raise ApplicationHandlerStop

    update_id = getattr(update, "update_id", None)
    if update_id is None:
        return

    rt = runtime(context)
    key = f"telegram_command:{int(update_id)}"
    try:
        claimed = rt.db.claim_idempotency_key(
            key,
            ttl_seconds=(
                rt.settings.idempotency_retention_days * 86400
            ),
        )
    except Exception as exc:
        logger.error(
            "Falha no gate de idempotência do comando: %s",
            type(exc).__name__,
        )
        raise ApplicationHandlerStop from exc

    if not claimed:
        logger.warning(
            "Comando Telegram duplicado suprimido | update_id=%s",
            update_id,
        )
        raise ApplicationHandlerStop

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
    abuse_surface = telegram_abuse_surface(message, text)
    directed_hint = telegram_reply_targets_other_user(message, user.id)
    sensitive_surface = telegram_sensitive_surface(message, text)
    if await protect_credential_exposure(
        update,
        context,
        sensitive_surface,
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
        sensitive_surface,
        source="guardian_command_preflight",
        notice_text=(
            "🚨 ZION bloqueou um comando que aparentava conter "
            "segredo de carteira. O conteúdo não foi processado."
        ),
    ):
        raise ApplicationHandlerStop

    # Flood, containment, lockdown deletion and domain policy are community
    # chat controls. Private support commands keep universal secret protection
    # above, then proceed to their own command authorization/AI boundaries.
    if chat.type == "private":
        return

    admin = await is_admin(
        update,
        context,
        revalidate_cached_admin=True,
    )
    command_head = (text.strip().split(maxsplit=1) or [""])[0]
    command_name = command_head.split("@", 1)[0].lower()
    lockdown_recovery_command = (
        admin
        and command_name
        in {
            "/unlock",
            "/state",
            "/status",
            "/health",
            "/diagnostics",
            "/guardian",
            "/incidents",
            "/incident",
            "/strikes",
            "/user",
        }
    )

    if (
        rt.db.get_operating_state() == OperatingState.LOCKDOWN
        and not lockdown_recovery_command
    ):
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

    remaining = rt.guardian.containment_remaining(chat.id, user.id)
    if remaining > 0:
        abuse = rt.guardian.evaluate_abuse(
            abuse_surface,
            directed_hint=directed_hint,
        )
        if abuse.detected:
            await _enforce_abuse(
                update,
                context,
                abuse,
                active_containment_seconds=remaining,
            )
            raise ApplicationHandlerStop
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
            reason="active_containment_command",
            success=deleted,
            metadata={"remaining_seconds": remaining},
        )
        if not deleted:
            await _alert_operators_enforcement_failure(
                context,
                chat_id=chat.id,
                target_user_id=user.id,
                action="delete",
                reason="active_containment_command",
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

    abuse = rt.guardian.evaluate_abuse(
        abuse_surface,
        directed_hint=directed_hint,
    )
    if abuse.detected:
        await _enforce_abuse(update, context, abuse)
        raise ApplicationHandlerStop

    entity_domains, unsupported_schemes = (
        telegram_entity_link_evidence(message)
    )
    links = rt.guardian.evaluate_links(
        text,
        extra_domains=entity_domains,
        unsupported_schemes=unsupported_schemes,
    )
    if links.should_delete:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        with rt.db.transaction():
            incident_id = rt.db.create_incident(
                chat_id=chat.id,
                user_id=user.id,
                category="unauthorized_link",
                severity=link_incident_severity(
                    links.unauthorized_domains,
                    links.unsupported_schemes,
                ),
                source="guardian_command_preflight",
                evidence={
                    "domains": links.unauthorized_domains,
                    "unsupported_schemes": links.unsupported_schemes,
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
                metadata={
                    "domains": links.unauthorized_domains,
                    "unsupported_schemes": links.unsupported_schemes,
                },
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
    abuse_surface = telegram_abuse_surface(message, text)
    directed_hint = telegram_reply_targets_other_user(message, user.id)
    sensitive_surface = telegram_sensitive_surface(message, text)
    if await protect_credential_exposure(
        update,
        context,
        sensitive_surface,
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
        sensitive_surface,
        source="guardian",
        notice_text=(
            f"🚨 {user_display_name(user)}: mensagem removida por "
            "possível exposição de segredo de carteira. "
            "Nunca publique seed phrase ou chave privada."
        ),
    ):
        return

    # This Application receives ZION's token. Its private policy is applied
    # before conversation state, knowledge retrieval, or any provider call.
    if chat.type == "private":
        dm_access = evaluate_dm_access(
            DEFAULT_AGENT_REGISTRY.get(AgentId.ZION),
            user_id=user.id,
            admin_user_ids=rt.settings.admin_user_ids,
        )
        if not dm_access.allowed:
            _record_dm_denial(
                rt,
                update,
                AgentId.ZION,
                ConversationIntent.COMMUNITY,
                "dm_creator_only",
            )
            return
        await answer_natural_conversation(
            update,
            context,
            text,
            claim_private_update=True,
        )
        return

    update_id = getattr(update, "update_id", None)
    if update_id is not None:
        try:
            claimed = rt.db.claim_idempotency_key(
                f"telegram_moderation:{int(update_id)}",
                ttl_seconds=(
                    rt.settings.idempotency_retention_days * 86400
                ),
            )
        except Exception as exc:
            logger.error(
                "Falha no gate de idempotência da moderação: %s",
                type(exc).__name__,
            )
            return

        if not claimed:
            logger.warning(
                "Update de moderação duplicado suprimido | update_id=%s",
                update_id,
            )
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
            reason="lockdown",
            success=deleted,
        )
        return

    remaining = rt.guardian.containment_remaining(chat.id, user.id)
    if remaining > 0:
        abuse = rt.guardian.evaluate_abuse(
            abuse_surface,
            directed_hint=directed_hint,
        )
        if abuse.detected:
            await _enforce_abuse(
                update,
                context,
                abuse,
                active_containment_seconds=remaining,
            )
            return
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
        if not deleted:
            await _alert_operators_enforcement_failure(
                context,
                chat_id=chat.id,
                target_user_id=user.id,
                action="delete",
                reason="active_containment",
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

    abuse = rt.guardian.evaluate_abuse(
        abuse_surface,
        directed_hint=directed_hint,
    )
    if abuse.detected:
        await _enforce_abuse(update, context, abuse)
        return

    entity_domains, unsupported_schemes = (
        telegram_entity_link_evidence(message)
    )
    links = rt.guardian.evaluate_links(
        text,
        extra_domains=entity_domains,
        unsupported_schemes=unsupported_schemes,
    )
    if links.should_delete:
        deleted = await delete_message_safe(
            context,
            chat.id,
            message.message_id,
        )
        with rt.db.transaction():
            incident_id = rt.db.create_incident(
                chat_id=chat.id,
                user_id=user.id,
                category="unauthorized_link",
                severity=link_incident_severity(
                    links.unauthorized_domains,
                    links.unsupported_schemes,
                ),
                source="guardian",
                evidence={
                    "domains": links.unauthorized_domains,
                    "unsupported_schemes": links.unsupported_schemes,
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
                metadata={
                    "domains": links.unauthorized_domains,
                    "unsupported_schemes": links.unsupported_schemes,
                },
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

    # Guardian decisions always run first. Only a safe message explicitly
    # addressed to ZION reaches the conversational AI.
    if await answer_natural_conversation(update, context, text):
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


async def secondary_private_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle only the private inbox owned by one secondary identity."""
    if (
        not update.effective_message
        or not update.effective_user
        or not update.effective_chat
        or update.effective_chat.type != "private"
    ):
        return

    rt = runtime(context)
    raw_agent = context.application.bot_data.get("zion_agent_id")
    if not isinstance(raw_agent, AgentId) or raw_agent is AgentId.ZION:
        return
    profile = DEFAULT_AGENT_REGISTRY.get(raw_agent)
    access = evaluate_dm_access(
        profile,
        user_id=update.effective_user.id,
        admin_user_ids=rt.settings.admin_user_ids,
    )
    if not access.allowed:
        denied_intent = {
            AgentId.MIMIR: ConversationIntent.TECHNICAL,
            AgentId.EIR: ConversationIntent.SUPPORT,
            AgentId.FREYR: ConversationIntent.PARTNERSHIP,
        }[raw_agent]
        _record_dm_denial(
            rt,
            update,
            raw_agent,
            denied_intent,
            f"dm_{profile.dm_policy.value}",
        )
        return

    text = (
        update.effective_message.text
        or update.effective_message.caption
        or ""
    ).strip()
    if not text or text.startswith("/"):
        return

    sensitive_surface = telegram_sensitive_surface(
        update.effective_message,
        text,
    )
    if await protect_credential_exposure(
        update,
        context,
        sensitive_surface,
        source=f"{raw_agent.value}_private",
        notice_text=(
            "Esta mensagem parece conter uma credencial. Apague-a e "
            "revogue ou rotacione o valor se ele for real."
        ),
    ):
        return
    if await protect_wallet_secret(
        update,
        context,
        sensitive_surface,
        source=f"{raw_agent.value}_private",
        notice_text=(
            "Nunca envie seed phrase, recovery phrase ou chave privada. "
            "Proteja a carteira e revogue qualquer segredo exposto."
        ),
    ):
        return

    update_id = getattr(update, "update_id", None)
    if update_id is not None:
        try:
            claimed = rt.db.claim_idempotency_key(
                f"telegram_private:{raw_agent.value}:{int(update_id)}",
                ttl_seconds=rt.settings.idempotency_retention_days * 86400,
            )
        except Exception as exc:
            logger.error(
                "Secondary DM idempotency unavailable | agent=%s | error=%s",
                raw_agent.value,
                type(exc).__name__,
            )
            return
        if not claimed:
            return

    decision = rt.intent_router.route_private(profile, text)
    if decision.speaker is None:
        return
    routing_inbound = _routing_inbound(update, raw_agent)
    _record_routing_decision(
        rt,
        routing_inbound,
        decision,
        outcome="routed",
        status="selected",
    )
    local_reply = _security_refusal_reply(text)
    if local_reply is not None:
        await update.effective_message.reply_text(local_reply)
        _complete_routing_decision(rt, routing_inbound, "sent")
        return
    if raw_agent is AgentId.FREYR:
        qualification = qualify_partnership(text)
        if qualification.fields or qualification.requires_human_decision:
            if not qualification.ready_for_operator:
                await update.effective_message.reply_text(
                    partnership_intake_prompt()
                )
                _complete_routing_decision(rt, routing_inbound, "sent")
                return
            summary = sanitize_for_ai(qualification.operator_summary())
            delivered = 0
            for operator_id in sorted(rt.settings.admin_user_ids):
                try:
                    if rt.primary_bot is None:
                        raise RuntimeError("primary ZION bot unavailable")
                    await rt.primary_bot.send_message(
                        chat_id=operator_id,
                        text=summary,
                    )
                    delivered += 1
                except Exception as exc:
                    logger.warning(
                        "Partnership operator handoff failed | error=%s",
                        type(exc).__name__,
                    )
            try:
                rt.db.record_action(
                    incident_id=None,
                    chat_id=None,
                    user_id=None,
                    action_type="partnership_handoff",
                    actor_type="agent",
                    actor_id=AgentId.FREYR.value,
                    reason="qualified_summary_forwarded",
                    success=delivered > 0,
                    metadata={
                        "field_count": len(qualification.fields),
                        "operator_delivery_count": delivered,
                        "human_decision_required": (
                            qualification.requires_human_decision
                        ),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Partnership handoff audit unavailable | error=%s",
                    type(exc).__name__,
                )
            reply = (
                "Obrigado. A oportunidade foi resumida e encaminhada para "
                "decisão humana. Nenhum acordo, prazo ou condição está "
                "confirmado nesta etapa."
                if delivered
                else (
                    "Consegui qualificar a oportunidade, mas o encaminhamento "
                    "humano está temporariamente indisponível. Tente novamente "
                    "mais tarde; nenhum acordo ou prazo foi confirmado."
                )
            )
            await update.effective_message.reply_text(reply)
            _complete_routing_decision(rt, routing_inbound, "sent")
            return
    if not rt.ask_limiter.allow(update.effective_user.id):
        await update.effective_message.reply_text(
            "Recebi muitas perguntas em pouco tempo. Tente novamente em "
            "alguns instantes."
        )
        _complete_routing_decision(rt, routing_inbound, "sent")
        return
    support_triage = (
        triage_support(text) if raw_agent is AgentId.EIR else None
    )
    answer = await rt.ai.answer(
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        question=text[:6000],
        agent_id=raw_agent,
    )
    rendered = telegram_ai_reply_text(answer.text)
    if support_triage is not None and support_triage.requires_human:
        rendered += (
            "\n\nEste caso precisa de revisão humana. Não envie seed phrase, "
            "chave privada, senha, token, API secret ou código 2FA."
        )
    await update.effective_message.reply_text(rendered)
    _complete_routing_decision(rt, routing_inbound, "sent")


def expire_temporary_state(rt: Runtime) -> None:
    with rt.db.transaction():
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


def scheduler_safety_preflight(
    rt: Runtime,
    now: float,
) -> bool:
    try:
        expire_temporary_state(rt)
        rt.state_maintenance_last_error = None
    except Exception as exc:
        rt.state_maintenance_last_error = type(exc).__name__
        logger.warning(
            "Falha ao atualizar estado temporário: %s",
            type(exc).__name__,
        )

    try:
        quarantined = rt.db.quarantine_stale_delivery_claims(
            now=now,
            stale_after_seconds=(
                rt.settings.delivery_claim_timeout_seconds
            ),
        )
        rt.delivery_guard_last_error = None
    except Exception as exc:
        rt.delivery_guard_last_error = type(exc).__name__
        logger.error(
            "Falha no delivery safety preflight: %s",
            type(exc).__name__,
        )
        return False

    if any(quarantined.values()):
        try:
            rt.db.create_incident(
                chat_id=None,
                user_id=None,
                category="stale_delivery_claims_quarantined",
                severity=Severity.HIGH,
                source="scheduler",
                evidence=quarantined,
                note=(
                    "A delivery claim exceeded its timeout. "
                    "ZION quarantined it instead of auto-replaying, "
                    "preventing duplicate delivery after an unknown outcome."
                ),
            )
        except Exception as exc:
            logger.error(
                "Claims stale foram isolados, mas o incidente "
                "não pôde ser persistido: %s",
                type(exc).__name__,
            )
        logger.error(
            "Delivery claim quarantine | scheduled_uncertain=%s | "
            "recurring_paused=%s",
            quarantined["scheduled_uncertain"],
            quarantined["recurring_paused"],
        )

    return True


def housekeeping_cycle(
    rt: Runtime,
    now: float,
) -> tuple[dict[str, int], list[str]]:
    results: dict[str, int] = {}
    failures: list[str] = []

    def run_step(name: str, operation) -> None:
        try:
            results[name] = int(operation())
        except Exception as exc:
            error_type = type(exc).__name__
            results[name] = 0
            failures.append(f"{name}:{error_type}")
            logger.warning(
                "Housekeeping step failed | step=%s | error=%s",
                name,
                error_type,
            )

    run_step(
        "knowledge_gaps_deleted",
        lambda: rt.db.prune_knowledge_gaps(
            now - (rt.settings.knowledge_gap_retention_days * 86400)
        ),
    )
    run_step(
        "resolved_reports_redacted",
        lambda: rt.db.redact_resolved_user_reports(
            now - (rt.settings.report_retention_days * 86400)
        ),
    )
    run_step(
        "user_events_deleted",
        lambda: rt.db.prune_user_events(
            now - (rt.settings.user_event_retention_days * 86400)
        ),
    )
    run_step(
        "idempotency_deleted",
        lambda: rt.db.prune_idempotency_keys(now),
    )
    routing_cutoff = now - (
        rt.settings.idempotency_retention_days * 86400
    )
    run_step(
        "speaker_claims_deleted",
        lambda: rt.db.prune_speaker_claims(routing_cutoff),
    )
    run_step(
        "routing_events_deleted",
        lambda: rt.db.prune_routing_events(routing_cutoff),
    )

    ama_cutoff = now - (rt.settings.ama_retention_days * 86400)
    run_step(
        "ama_questions_deleted",
        lambda: rt.db.prune_ama_questions(ama_cutoff),
    )
    run_step(
        "ama_sessions_deleted",
        lambda: rt.db.prune_closed_ama_sessions(ama_cutoff),
    )
    run_step(
        "ai_events_deleted",
        lambda: rt.db.prune_ai_events(
            now - (rt.settings.ai_event_retention_days * 86400)
        ),
    )
    run_step(
        "scheduled_deleted",
        lambda: rt.db.prune_completed_scheduled_messages(
            now - (rt.settings.completed_job_retention_days * 86400)
        ),
    )
    run_step(
        "containments_deleted",
        lambda: rt.db.prune_expired_containments(now),
    )

    if any(results.values()):
        logger.info(
            "Housekeeping | knowledge_gaps_deleted=%s | "
            "resolved_reports_redacted=%s | "
            "user_events_deleted=%s | "
            "idempotency_deleted=%s | "
            "speaker_claims_deleted=%s | "
            "routing_events_deleted=%s | "
            "ama_questions_deleted=%s | "
            "ama_sessions_deleted=%s | "
            "ai_events_deleted=%s | "
            "scheduled_deleted=%s | "
            "containments_deleted=%s",
            results["knowledge_gaps_deleted"],
            results["resolved_reports_redacted"],
            results["user_events_deleted"],
            results["idempotency_deleted"],
            results["speaker_claims_deleted"],
            results["routing_events_deleted"],
            results["ama_questions_deleted"],
            results["ama_sessions_deleted"],
            results["ai_events_deleted"],
            results["scheduled_deleted"],
            results["containments_deleted"],
        )

    return results, failures

def hydrate_operational_health_incident(rt: Runtime) -> None:
    if rt.health_incident_hydrated:
        return

    try:
        signature = (
            rt.db.get_setting("health_incident_signature")
            or ""
        ).strip()
        incident_id = (
            rt.db.get_setting("health_incident_id")
            or ""
        ).strip()

        if signature and incident_id:
            incident = rt.db.get_incident(incident_id)
            if (
                incident
                and incident.get("status") == "open"
                and incident.get("category")
                == "operational_health_warning"
            ):
                rt.health_incident_signature = signature
                rt.health_incident_id = incident_id
            else:
                with rt.db.transaction():
                    rt.db.set_setting(
                        "health_incident_signature",
                        "",
                    )
                    rt.db.set_setting(
                        "health_incident_id",
                        "",
                    )

        rt.health_incident_hydrated = True
    except Exception as exc:
        logger.warning(
            "Falha ao hidratar incidente operacional: %s",
            type(exc).__name__,
        )


def transition_operational_health_incident(
    rt: Runtime,
    *,
    signature: str,
    issues: list[str],
    snapshot,
    p95_lag: float,
) -> tuple[str | None, str | None]:
    hydrate_operational_health_incident(rt)

    previous_incident_id = rt.health_incident_id

    if not issues:
        if previous_incident_id:
            try:
                with rt.db.transaction():
                    if not rt.db.set_incident_status(
                        previous_incident_id,
                        "resolved",
                    ):
                        raise RuntimeError(
                            "operational incident not found"
                        )
                    rt.db.set_setting(
                        "health_incident_signature",
                        "",
                    )
                    rt.db.set_setting(
                        "health_incident_id",
                        "",
                    )
                rt.health_incident_signature = None
                rt.health_incident_id = None
            except Exception as exc:
                logger.warning(
                    "Falha ao resolver incidente operacional: %s",
                    type(exc).__name__,
                )
        return None, previous_incident_id

    if (
        signature == rt.health_incident_signature
        and rt.health_incident_id
    ):
        return rt.health_incident_id, None

    try:
        new_incident_id: str
        with rt.db.transaction():
            if previous_incident_id:
                if not rt.db.set_incident_status(
                    previous_incident_id,
                    "resolved",
                ):
                    raise RuntimeError(
                        "previous operational incident not found"
                    )

            new_incident_id = rt.db.create_incident(
                chat_id=None,
                user_id=None,
                category="operational_health_warning",
                severity=(
                    Severity.HIGH
                    if rt.delivery_health_blocked
                    or "housekeeping_failed" in issues
                    or "delivery_safety_preflight_failed" in issues
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
                    "housekeeping_error_type": (
                        rt.housekeeping_last_error
                    ),
                    "wal_checkpoint_error_type": (
                        rt.wal_checkpoint_last_error
                    ),
                    "state_maintenance_error_type": (
                        rt.state_maintenance_last_error
                    ),
                    "delivery_guard_error_type": (
                        rt.delivery_guard_last_error
                    ),
                },
                note=(
                    "Operational alert; no automated destructive action executed."
                ),
            )
            rt.db.set_setting(
                "health_incident_signature",
                signature,
            )
            rt.db.set_setting(
                "health_incident_id",
                new_incident_id,
            )

        rt.health_incident_signature = signature
        rt.health_incident_id = new_incident_id
        return new_incident_id, previous_incident_id
    except Exception as exc:
        logger.warning(
            "Falha ao transicionar incidente operacional: %s",
            type(exc).__name__,
        )
        return None, None


async def operational_alert_cycle(
    application: Application,
    rt: Runtime,
) -> None:
    snapshot = rt.health.snapshot()
    diagnostics = rt.health.diagnostics()
    _, p95_lag = update_lag_stats(rt)

    community_stats_ok = True
    try:
        community = rt.db.community_stats()
    except Exception as exc:
        community_stats_ok = False
        logger.warning(
            "Falha ao ler community_stats para health alert: %s",
            type(exc).__name__,
        )
        community = {
            "failed_scheduled": 0,
            "uncertain_scheduled": 0,
            "paused_recurring": 0,
        }

    issues: list[str] = []

    if not snapshot.db_ok:
        issues.append("database_or_integrity")
    if not diagnostics.get("db_file_present", False):
        issues.append("sqlite_database_file_missing")
    if not diagnostics.get("sqlite_foreign_keys_ok", False):
        issues.append("sqlite_foreign_key_violation")

    if not diagnostics.get("schema_version_read_ok", False):
        issues.append("sqlite_schema_version_unavailable")
    elif not diagnostics.get("schema_version_ok", False):
        issues.append("sqlite_schema_version_mismatch")
    if not diagnostics.get("sqlite_pragma_read_ok", False):
        issues.append("sqlite_pragmas_unavailable")
    else:
        pragma_issue_names = {
            "journal_mode": "sqlite_not_wal",
            "foreign_keys": "sqlite_foreign_keys_off",
            "synchronous": "sqlite_synchronous_not_full",
            "trusted_schema": "sqlite_trusted_schema_on",
            "application_id": "sqlite_application_id_mismatch",
            "busy_timeout": "sqlite_busy_timeout_too_low",
            "wal_autocheckpoint": "sqlite_wal_autocheckpoint_drift",
            "journal_size_limit": "sqlite_journal_size_limit_drift",
        }
        for pragma_issue in diagnostics.get("sqlite_pragma_issues", []):
            issues.append(
                pragma_issue_names.get(
                    str(pragma_issue),
                    f"sqlite_pragma:{pragma_issue}",
                )
            )

    if rt.housekeeping_last_error:
        issues.append("housekeeping_failed")
    if rt.wal_checkpoint_last_error:
        issues.append("wal_checkpoint_failed")
    if rt.state_maintenance_last_error:
        issues.append("temporary_state_maintenance_failed")
    if rt.delivery_guard_last_error:
        issues.append("delivery_safety_preflight_failed")

    if rt.settings.ai_enabled:
        if not rt.ai.accounting_healthy:
            issues.append("ai_accounting_fail_closed")
        if not rt.ai.enabled:
            issues.append("ai_provider_not_ready")
        elif rt.ai.circuit_open():
            issues.append("ai_circuit_open")

        if rt.settings.ai_daily_token_budget > 0:
            remaining = rt.ai.budget_remaining()
            if not rt.ai.accounting_healthy:
                if "ai_accounting_fail_closed" not in issues:
                    issues.append("ai_accounting_fail_closed")
            elif remaining == 0:
                issues.append("ai_budget_exhausted")

    if not rt.knowledge.chunks:
        issues.append("knowledge_empty")
    if rt.knowledge.load_errors:
        issues.append("knowledge_load_error")
    for config_issue in diagnostics.get("configuration_issues", []):
        issues.append(f"config:{config_issue}")

    if not community_stats_ok:
        issues.append("community_stats_unavailable")
    if community.get("failed_scheduled", 0) > 0:
        issues.append("scheduled_delivery_failed")
    if community.get("uncertain_scheduled", 0) > 0:
        issues.append("scheduled_delivery_uncertain")
    if community.get("paused_recurring", 0) > 0:
        issues.append("recurring_delivery_paused")
    if diagnostics.get("db_large"):
        issues.append("sqlite_database_large")
    if diagnostics.get("wal_large"):
        issues.append("sqlite_wal_large")
    if not diagnostics.get("ai_latency_read_ok", False):
        issues.append("ai_latency_telemetry_unavailable")
    if not diagnostics.get("disk_usage_ok", False):
        issues.append("disk_usage_unavailable")
    elif snapshot.details.get("disk_low"):
        issues.append("disk_low")
    if not snapshot.details.get("sensitive_files_private"):
        issues.append("sensitive_file_permissions")
    if not snapshot.wifi_interface_present:
        issues.append("wifi_interface_missing")
    lag_sample_max_age = max(
        120,
        rt.settings.health_check_interval_seconds * 2,
    )
    lag_sample_fresh = (
        rt.update_lag_last_sample_monotonic > 0
        and (
            time.monotonic()
            - rt.update_lag_last_sample_monotonic
        )
        <= lag_sample_max_age
    )
    if (
        rt.update_lags
        and lag_sample_fresh
        and p95_lag > rt.settings.update_lag_warn_seconds
    ):
        issues.append("telegram_update_lag")

    issues = sorted(set(issues))

    delivery_blocking_issues = {
        "database_or_integrity",
        "sqlite_database_file_missing",
        "sqlite_foreign_key_violation",
        "sqlite_schema_version_unavailable",
        "sqlite_schema_version_mismatch",
        "sqlite_pragmas_unavailable",
        "sqlite_not_wal",
        "sqlite_foreign_keys_off",
        "sqlite_synchronous_not_full",
        "sqlite_trusted_schema_on",
        "sqlite_application_id_mismatch",
    }
    rt.delivery_health_block_reasons = tuple(
        issue for issue in issues
        if issue in delivery_blocking_issues
    )
    rt.delivery_health_blocked = bool(
        rt.delivery_health_block_reasons
    )

    now = time.time()

    previous = rt.health_alert_signature
    last_sent_at = rt.health_alert_last_sent_at
    persistence_read_ok = True

    # Normally persisted dedup state is authoritative so restarts and
    # the configured repeat interval keep their historical semantics.
    # If a dedup write failed after a confirmed Telegram delivery, the
    # live single-process state is newer than SQLite. Repair that state
    # before accepting persisted values again.
    if rt.health_alert_persistence_dirty and previous is not None:
        try:
            with rt.db.transaction():
                rt.db.set_setting("health_alert_signature", previous)
                rt.db.set_setting(
                    "health_alert_last_sent_at",
                    str(last_sent_at),
                )
            rt.health_alert_persistence_dirty = False
        except Exception as exc:
            persistence_read_ok = False
            logger.warning(
                "Health alert dedup ainda não pôde ser persistido: %s",
                type(exc).__name__,
            )

    if not rt.health_alert_persistence_dirty:
        try:
            persisted = rt.db.get_setting("health_alert_signature")
            if persisted is not None:
                previous = persisted

            raw_last_sent = (
                rt.db.get_setting("health_alert_last_sent_at")
                or "0"
            )
            last_sent_at = float(raw_last_sent)
        except Exception as exc:
            persistence_read_ok = False
            logger.warning(
                "Health alert persistence indisponível: %s",
                type(exc).__name__,
            )

    if (
        not persistence_read_ok
        or rt.health_alert_persistence_dirty
    ):
        issues.append("health_alert_persistence_unavailable")
        issues = sorted(set(issues))

    signature = "|".join(issues) if issues else "OK"
    rt.health_alert_signature = previous
    rt.health_alert_last_sent_at = last_sent_at

    incident_id, recovered_incident_id = (
        transition_operational_health_incident(
            rt,
            signature=signature,
            issues=issues,
            snapshot=snapshot,
            p95_lag=p95_lag,
        )
    )

    if signature == previous:
        if signature == "OK":
            return
        if (
            now - last_sent_at
            < rt.settings.health_alert_repeat_seconds
        ):
            return

    if not issues:
        if not previous or previous == "OK":
            return

        delivered = False
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
                delivered = True
            except Exception as exc:
                logger.warning(
                    "Falha ao enviar recuperação para operator=%s: %s",
                    operator_id,
                    type(exc).__name__,
                )

            try:
                rt.db.record_action(
                    incident_id=recovered_incident_id,
                    chat_id=operator_id,
                    user_id=None,
                    action_type="operator_recovery",
                    actor_type="health",
                    actor_id=None,
                    reason="operational_health_recovered",
                    success=success,
                    metadata={"previous_signature": previous},
                )
            except Exception:
                pass

        if not delivered:
            logger.warning(
                "Operational recovery sem entrega confirmada; "
                "estado permanecerá elegível para retry."
            )
            return

        try:
            with rt.db.transaction():
                rt.db.set_setting("health_alert_signature", "OK")
                rt.db.set_setting("health_alert_last_sent_at", "0")
            rt.health_alert_persistence_dirty = False
        except Exception as exc:
            rt.health_alert_persistence_dirty = True
            logger.warning(
                "Recuperação entregue, mas persistência do dedup falhou: %s",
                type(exc).__name__,
            )
        rt.health_alert_signature = "OK"
        rt.health_alert_last_sent_at = 0.0
        return

    alert_text = (
        "⚠️ ZION OPERATIONAL ALERT\n"
        + "\n".join(f"• {issue}" for issue in issues)
        + "\nUse /diagnostics para detalhes."
    )

    delivered = False
    for operator_id in sorted(rt.settings.admin_user_ids):
        success = False
        try:
            await application.bot.send_message(
                chat_id=operator_id,
                text=alert_text,
            )
            success = True
            delivered = True
        except Exception as exc:
            logger.warning(
                "Falha ao enviar alerta operacional para operator=%s: %s",
                operator_id,
                type(exc).__name__,
            )

        try:
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
        except Exception:
            pass

    if not delivered:
        logger.warning(
            "Operational alert sem entrega confirmada; "
            "não avançando estado de deduplicação."
        )
        return

    try:
        with rt.db.transaction():
            rt.db.set_setting("health_alert_signature", signature)
            rt.db.set_setting("health_alert_last_sent_at", str(now))
        rt.health_alert_persistence_dirty = False
    except Exception as exc:
        rt.health_alert_persistence_dirty = True
        logger.warning(
            "Alerta entregue, mas persistência do dedup falhou: %s",
            type(exc).__name__,
        )
    rt.health_alert_signature = signature
    rt.health_alert_last_sent_at = now


async def hourly_operations_cycle(
    application: Application,
    rt: Runtime,
    *,
    now: float | None = None,
) -> None:
    cycle_now = time.time() if now is None else now

    try:
        _, housekeeping_failures = housekeeping_cycle(rt, cycle_now)
        rt.housekeeping_last_error = (
            ",".join(housekeeping_failures)
            if housekeeping_failures
            else None
        )
    except Exception as exc:
        rt.housekeeping_last_error = f"cycle:{type(exc).__name__}"
        logger.exception(
            "Falha estrutural no housekeeping do ZION; "
            "health alert seguirá ativo."
        )

    try:
        checkpoint = rt.db.checkpoint_wal()
        rt.wal_checkpoint_last_error = None
        if checkpoint["busy"] not in {0, -1}:
            logger.warning(
                "SQLite WAL checkpoint busy | frames=%s | checkpointed=%s",
                checkpoint["log_frames"],
                checkpoint["checkpointed_frames"],
            )
    except Exception as exc:
        rt.wal_checkpoint_last_error = type(exc).__name__
        logger.warning(
            "Falha no checkpoint passivo SQLite: %s",
            type(exc).__name__,
        )

    try:
        await operational_alert_cycle(application, rt)
    except Exception as exc:
        rt.delivery_health_blocked = True
        rt.delivery_health_block_reasons = (
            f"operational_health_check_failed:{type(exc).__name__}",
        )
        logger.exception(
            "Falha no ciclo de alerta operacional do ZION; "
            "scheduled delivery bloqueada."
        )


async def scheduler_loop(application: Application) -> None:
    # Preserve the previous startup contract: maintenance and health run
    # on the first scheduler iteration regardless of host uptime.
    last_housekeeping_monotonic = float("-inf")
    last_health_check_monotonic = float("-inf")

    while True:
        try:
            rt = application.bot_data.get("zion_runtime")
            if not isinstance(rt, Runtime):
                await asyncio.sleep(10)
                continue

            now = time.time()
            monotonic_now = time.monotonic()
            previous_preflight_state = (
                rt.state_maintenance_last_error,
                rt.delivery_guard_last_error,
            )
            delivery_guard_ok = scheduler_safety_preflight(rt, now)
            preflight_state = (
                rt.state_maintenance_last_error,
                rt.delivery_guard_last_error,
            )
            preflight_changed = (
                any(preflight_state)
                and preflight_state != previous_preflight_state
            )

            ran_operational_check = False
            if monotonic_now - last_housekeeping_monotonic >= 3600:
                await hourly_operations_cycle(
                    application,
                    rt,
                    now=now,
                )
                last_housekeeping_monotonic = monotonic_now
                last_health_check_monotonic = monotonic_now
                ran_operational_check = True
            elif (
                monotonic_now - last_health_check_monotonic
                >= rt.settings.health_check_interval_seconds
            ):
                try:
                    await operational_alert_cycle(application, rt)
                except Exception as exc:
                    rt.delivery_health_blocked = True
                    rt.delivery_health_block_reasons = (
                        f"operational_health_check_failed:{type(exc).__name__}",
                    )
                    logger.exception(
                        "Falha no ciclo periódico de saúde operacional; "
                        "scheduled delivery bloqueada."
                    )
                finally:
                    last_health_check_monotonic = monotonic_now
                ran_operational_check = True

            if preflight_changed and not ran_operational_check:
                try:
                    await operational_alert_cycle(application, rt)
                except Exception as exc:
                    rt.delivery_health_blocked = True
                    rt.delivery_health_block_reasons = (
                        f"operational_health_check_failed:{type(exc).__name__}",
                    )
                    logger.exception(
                        "Falha no alerta imediato do scheduler safety preflight; "
                        "scheduled delivery bloqueada."
                    )
                finally:
                    last_health_check_monotonic = monotonic_now

            if not delivery_guard_ok or rt.delivery_health_blocked:
                await asyncio.sleep(20)
                continue

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
                attempt = rt.db.claim_scheduled_message(
                    str(item["id"]),
                    now=now,
                )
                if attempt is None:
                    continue

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

                with rt.db.transaction():
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
                            "attempt": attempt,
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
                            "attempts": attempt,
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
                if not rt.db.claim_recurring_message(
                    str(item["id"]),
                    now=now,
                ):
                    continue

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

                with rt.db.transaction():
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
    existing = application.bot_data.get("zion_scheduler_task")
    if isinstance(existing, asyncio.Task) and not existing.done():
        logger.error(
            "Tentativa de iniciar um segundo scheduler bloqueada."
        )
        return

    rt = application.bot_data.get("zion_runtime")
    if isinstance(rt, Runtime):
        rt.primary_bot = application.bot
        await rt.multi_agent_transport.start()
        statuses = rt.multi_agent_transport.status_all()
        application.bot_data["zion_multi_agent_started"] = all(
            statuses[agent_id].runtime_status == "RUNNING"
            for agent_id in (AgentId.MIMIR, AgentId.EIR, AgentId.FREYR)
        )

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
        await rt.multi_agent_transport.stop()
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
    settings = (settings or Settings.from_env()).with_primary_telegram_identity()

    configure_logging(
        settings.log_path,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )

    if not settings.telegram_token:
        raise RuntimeError("Identidade Telegram principal não configurada.")
    if settings.legacy_mistral_api_key_present:
        raise RuntimeError(
            "MISTRAL_API_KEY está depreciada e deve permanecer vazia; "
            "use o cofre local protegido."
        )

    rt = Runtime(settings)

    app = (
        Application.builder()
        .token(settings.telegram_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["zion_runtime"] = rt
    rt.multi_agent_transport.prepare(
        shared_runtime=rt,
        private_handler=secondary_private_handler,
        error_handler=error_handler,
    )

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
        "setkimikey": set_kimi_key_command,
        "cancelkimikey": cancel_kimi_key_command,
        "kimistatus": kimi_status_command,
        "setmistralkey": set_mistral_key_command,
        "clearmistralkey": clear_mistral_key_command,
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
        "cancelscheduled": cancel_scheduled_command,
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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   kimi_secret_capture_handler), group=-4)

    # Group -3 captures only an explicitly armed private Mistral secret.
    # It runs before generic credential protection, persistence and moderation.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            mistral_secret_capture_handler,
        ),
        group=-3,
    )

    # Group -2 protects secrets before persisting Telegram update IDs.
    # Functional command side effects remain at-most-once across restarts;
    # secret deletion is deliberately retriable across a pre-claim crash.
    app.add_handler(
        MessageHandler(
            filters.COMMAND,
            command_idempotency_guard_handler,
        ),
        group=-2,
    )

    # Group -1 runs before command handlers. This closes the
    # command-flood bypass while still allowing valid commands in group 0.
    app.add_handler(
        MessageHandler(filters.COMMAND, command_guard_handler),
        group=-1,
    )

    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(
        CallbackQueryHandler(
            control_center_callback,
            pattern=r"^zc1:",
        )
    )

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
    issues = settings.configuration_issues()
    if issues:
        logger.warning(
            "ZION configuration warnings: %s",
            ",".join(issues),
        )
    logger.info(
        "ZION iniciado | db=sqlite | ai_provider=mistral | ai_enabled=%s | observe=%s",
        settings.ai_enabled,
        settings.ai_observe,
    )
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
