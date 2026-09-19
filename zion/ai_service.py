from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time

from .config import Settings
from .db import ZionDB
from .knowledge import KnowledgeBase
from .mistral import MistralClient
from .models import AIAnswer, AIClassification


logger = logging.getLogger("zion.ai")


AI_CREDENTIAL_REGEX = re.compile(
    r"(?i)\b("
    r"api[_ -]?key|access[_ -]?key|client[_ -]?secret|"
    r"token|password|senha|secret|segredo"
    r")\b\s*[:=\-]\s*([^\s,;]{6,})"
)

TELEGRAM_TOKEN_REGEX = re.compile(
    r"\d{6,}:[A-Za-z0-9_-]{20,}"
)


def sanitize_for_ai(text: str) -> str:
    sanitized = TELEGRAM_TOKEN_REGEX.sub(
        "[REDACTED_TELEGRAM_TOKEN]",
        text or "",
    )
    sanitized = AI_CREDENTIAL_REGEX.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )
    return sanitized


class AIService:
    def __init__(
        self,
        settings: Settings,
        db: ZionDB,
        knowledge: KnowledgeBase,
    ):
        self.settings = settings
        self.db = db
        self.knowledge = knowledge
        self.client = MistralClient(settings)
        self._semaphore = asyncio.Semaphore(settings.ai_max_concurrency)

    @property
    def enabled(self) -> bool:
        return self.client.configured

    def tokens_used_today(self) -> int:
        now = time.time()
        utc_day_start = now - (now % 86400)
        return self.db.ai_tokens_since(utc_day_start)

    def budget_remaining(self) -> int | None:
        budget = self.settings.ai_daily_token_budget
        if budget <= 0:
            return None
        return max(0, budget - self.tokens_used_today())

    def budget_available(self) -> bool:
        remaining = self.budget_remaining()
        return remaining is None or remaining > 0

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(
            text.encode("utf-8", errors="ignore")
        ).hexdigest()[:24]

    async def answer(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        question: str,
    ) -> AIAnswer:
        safe_question = sanitize_for_ai(question)
        context = self.knowledge.render_context(safe_question)
        question_hash = self._hash_text(safe_question)

        if not context.strip():
            self.db.record_knowledge_gap(
                question_hash=question_hash,
                sample_text=safe_question,
            )
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=self.settings.mistral_model,
                success=True,
                input_hash=question_hash,
                metadata={
                    "knowledge_hits": 0,
                    "provider_called": False,
                },
            )
            return AIAnswer(
                text=(
                    "Não encontrei informação oficial suficiente na base "
                    "de conhecimento do ZION para confirmar isso. "
                    "A pergunta foi registrada como lacuna de conhecimento "
                    "para revisão da equipe."
                ),
                model=self.settings.mistral_model,
            )

        if not self.enabled:
            return AIAnswer(
                text="A camada de IA Mistral do ZION ainda não está habilitada.",
                model=self.settings.mistral_model,
            )

        if not self.budget_available():
            return AIAnswer(
                text=(
                    "O orçamento diário de IA do ZION foi atingido. "
                    "O Guardian continua ativo; novas chamadas Mistral "
                    "ficam pausadas até o próximo dia UTC."
                ),
                model=self.settings.mistral_model,
            )

        try:
            async with self._semaphore:
                answer = await self.client.answer(
                    question=safe_question,
                    context=context,
                )

            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                input_hash=question_hash,
                metadata={
                    "knowledge_hits": len(self.knowledge.search(safe_question)),
                },
            )
            return answer

        except Exception as exc:
            logger.warning("Falha na resposta Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(question),
                metadata={"error_type": type(exc).__name__},
            )
            return AIAnswer(
                text=(
                    "A camada de IA está temporariamente indisponível. "
                    "O Guardian determinístico continua ativo."
                ),
                model=self.settings.mistral_model,
            )

    async def summarize(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        text: str,
    ) -> AIAnswer:
        if not self.enabled:
            return AIAnswer(
                text="A camada de IA Mistral do ZION ainda não está habilitada.",
                model=self.settings.mistral_model,
            )

        if not self.budget_available():
            return AIAnswer(
                text="Orçamento diário de IA atingido. Tente novamente após a virada UTC.",
                model=self.settings.mistral_model,
            )

        safe_text = sanitize_for_ai(text)
        try:
            async with self._semaphore:
                answer = await self.client.summarize(safe_text)

            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="summarize",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                input_hash=self._hash_text(safe_text),
            )
            return answer
        except Exception as exc:
            logger.warning("Falha no resumo Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="summarize",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={"error_type": type(exc).__name__},
            )
            return AIAnswer(
                text="Não foi possível gerar o resumo agora.",
                model=self.settings.mistral_model,
            )

    async def translate(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        text: str,
        target_language: str,
    ) -> AIAnswer:
        if not self.enabled:
            return AIAnswer(
                text="A camada de IA Mistral do ZION ainda não está habilitada.",
                model=self.settings.mistral_model,
            )

        if not self.budget_available():
            return AIAnswer(
                text="Orçamento diário de IA atingido. Tente novamente após a virada UTC.",
                model=self.settings.mistral_model,
            )

        safe_text = sanitize_for_ai(text)
        safe_target = re.sub(
            r"[^A-Za-zÀ-ÿ -]",
            "",
            target_language,
        )[:40] or "English"

        try:
            async with self._semaphore:
                answer = await self.client.translate(
                    text=safe_text,
                    target_language=safe_target,
                )

            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="translate",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                input_hash=self._hash_text(safe_text),
                metadata={"target_language": safe_target},
            )
            return answer
        except Exception as exc:
            logger.warning("Falha na tradução Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="translate",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={
                    "target_language": safe_target,
                    "error_type": type(exc).__name__,
                },
            )
            return AIAnswer(
                text="Não foi possível traduzir agora.",
                model=self.settings.mistral_model,
            )

    async def classify(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        text: str,
    ) -> AIClassification | None:
        if not self.enabled or not self.settings.ai_observe:
            return None

        if not self.budget_available():
            return None

        try:
            async with self._semaphore:
                result = await self.client.classify(sanitize_for_ai(text))

            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=self.settings.mistral_model,
                success=True,
                category=result.category,
                risk=result.risk,
                requires_human=result.requires_human,
                input_hash=self._hash_text(text),
            )
            return result

        except Exception as exc:
            logger.warning("Falha no classificador Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(text),
                metadata={"error_type": type(exc).__name__},
            )
            return None
