from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from .config import Settings
from .db import ZionDB
from .knowledge import KnowledgeBase
from .mistral import MistralClient
from .models import AIAnswer, AIClassification


logger = logging.getLogger("zion.ai")


AI_CREDENTIAL_REGEX = re.compile(
    r"(?i)\\b("
    r"api[_ -]?key|access[_ -]?key|client[_ -]?secret|"
    r"token|password|senha|secret|segredo"
    r")\\b\\s*[:=\\-]\\s*([^\\s,;]{6,})"
)

TELEGRAM_TOKEN_REGEX = re.compile(
    r"(?<![A-Za-z0-9_])\\d{6,}:[A-Za-z0-9_-]{20,}"
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

    async def classify(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        text: str,
    ) -> AIClassification | None:
        if not self.enabled or not self.settings.ai_observe:
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
