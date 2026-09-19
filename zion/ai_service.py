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
        self._circuit_failures = self._load_int_setting(
            "ai_circuit_failures",
            0,
        )
        self._circuit_open_until = self._load_float_setting(
            "ai_circuit_open_until",
            0.0,
        )

    @property
    def enabled(self) -> bool:
        return self.client.configured

    def _load_int_setting(
        self,
        key: str,
        default: int,
    ) -> int:
        raw = self.db.get_setting(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    def _load_float_setting(
        self,
        key: str,
        default: float,
    ) -> float:
        raw = self.db.get_setting(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    @property
    def circuit_failures(self) -> int:
        return self._circuit_failures

    def circuit_open(self) -> bool:
        if self._circuit_open_until <= 0:
            return False

        now = time.time()
        if now < self._circuit_open_until:
            return True

        self._reset_circuit()
        return False

    def circuit_remaining_seconds(self) -> int:
        if not self.circuit_open():
            return 0
        return max(
            0,
            int(self._circuit_open_until - time.time()),
        )

    def _reset_circuit(self) -> None:
        self._circuit_failures = 0
        self._circuit_open_until = 0.0
        self.db.set_setting("ai_circuit_failures", "0")
        self.db.set_setting("ai_circuit_open_until", "0")

    def _record_provider_success(self) -> None:
        if self._circuit_failures or self._circuit_open_until:
            self._reset_circuit()

    def _record_provider_failure(self) -> None:
        self._circuit_failures += 1
        self.db.set_setting(
            "ai_circuit_failures",
            str(self._circuit_failures),
        )

        if self._circuit_failures < self.settings.ai_circuit_failures:
            return

        self._circuit_open_until = (
            time.time() + self.settings.ai_circuit_seconds
        )
        self.db.set_setting(
            "ai_circuit_open_until",
            str(self._circuit_open_until),
        )
        logger.warning(
            "Circuit breaker Mistral aberto por %ss após %s falhas consecutivas.",
            self.settings.ai_circuit_seconds,
            self._circuit_failures,
        )

    def provider_available(self) -> bool:
        return (
            self.enabled
            and self.budget_available()
            and not self.circuit_open()
        )

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

        if self.circuit_open():
            return AIAnswer(
                text="A camada de IA está temporariamente em proteção automática. Tente novamente em alguns minutos.",
                model=self.settings.mistral_model,
            )

        try:
            async with self._semaphore:
                answer = await self.client.answer(
                    question=safe_question,
                    context=context,
                )

            self._record_provider_success()

            source_names = sorted(
                {
                    chunk.source
                    for chunk in self.knowledge.search(safe_question)
                }
            )
            if source_names:
                answer.text = (
                    answer.text.rstrip()
                    + "\n\nFontes ZION: "
                    + ", ".join(source_names)
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
            self._record_provider_failure()
            logger.warning("Falha na resposta Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=self.settings.mistral_model,
                success=False,
                input_hash=question_hash,
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

        if self.circuit_open():
            return AIAnswer(
                text="A camada de IA está temporariamente em proteção automática. Tente novamente em alguns minutos.",
                model=self.settings.mistral_model,
            )

        safe_text = sanitize_for_ai(text)
        try:
            async with self._semaphore:
                answer = await self.client.summarize(safe_text)

            self._record_provider_success()

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
            self._record_provider_failure()
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

        if self.circuit_open():
            return AIAnswer(
                text="A camada de IA está temporariamente em proteção automática. Tente novamente em alguns minutos.",
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

            self._record_provider_success()

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
            self._record_provider_failure()
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

        if self.circuit_open():
            return None

        safe_text = sanitize_for_ai(text)

        try:
            async with self._semaphore:
                result = await self.client.classify(safe_text)

            self._record_provider_success()

            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=result.model or self.settings.mistral_model,
                success=True,
                category=result.category,
                risk=result.risk,
                requires_human=result.requires_human,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                input_hash=self._hash_text(safe_text),
            )
            return result

        except Exception as exc:
            self._record_provider_failure()
            logger.warning("Falha no classificador Mistral: %s", exc)
            self.db.record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={"error_type": type(exc).__name__},
            )
            return None
