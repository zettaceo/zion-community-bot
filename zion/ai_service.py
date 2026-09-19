from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time

from .config import Settings
from .db import ZionDB
from .knowledge import KnowledgeBase
from .mistral import MistralClient
from .models import AIAnswer, AIClassification, OperatingState


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

WALLET_SECRET_INPUT_REGEX = re.compile(
    r"(?i)\b("
    r"seed\s+phrase|recovery\s+phrase|mnemonic|"
    r"frase\s+semente|frase\s+de\s+recupera[cç][aã]o|"
    r"private\s+key|chave\s+privada"
    r")\b\s*[:=\-]\s*([^\n]{20,})"
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
    sanitized = WALLET_SECRET_INPUT_REGEX.sub(
        lambda match: (
            f"{match.group(1)}: [REDACTED_WALLET_SECRET]"
        ),
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
        self._budget_lock = threading.Lock()
        self._reserved_tokens = 0
        self._accounting_healthy = True
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

    def operating_state(self) -> OperatingState:
        try:
            return self.db.get_operating_state()
        except Exception:
            return OperatingState.SAFE_MODE

    def state_allows_ai(self) -> bool:
        return self.operating_state() in {
            OperatingState.NORMAL,
            OperatingState.ELEVATED,
        }

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
    def accounting_healthy(self) -> bool:
        return self._accounting_healthy

    def _safe_set_setting(self, key: str, value: str) -> bool:
        try:
            self.db.set_setting(key, value)
            return True
        except Exception as exc:
            logger.warning(
                "Falha ao persistir estado interno da IA | key=%s | error=%s",
                key,
                type(exc).__name__,
            )
            return False

    def _record_ai_event(self, **kwargs) -> bool:
        try:
            self.db.record_ai_event(**kwargs)
            return True
        except Exception as exc:
            self._accounting_healthy = False
            logger.error(
                "AI accounting FAIL-CLOSED | event não persistido | error=%s",
                type(exc).__name__,
            )
            return False

    def _record_knowledge_gap(
        self,
        *,
        question_hash: str,
        sample_text: str,
    ) -> bool:
        try:
            self.db.record_knowledge_gap(
                question_hash=question_hash,
                sample_text=sample_text,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Falha ao registrar knowledge gap | error=%s",
                type(exc).__name__,
            )
            return False

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
        self._safe_set_setting("ai_circuit_failures", "0")
        self._safe_set_setting("ai_circuit_open_until", "0")

    def _record_provider_success(self) -> None:
        if self._circuit_failures or self._circuit_open_until:
            self._reset_circuit()

    def _record_provider_failure(self) -> None:
        self._circuit_failures += 1
        self._safe_set_setting(
            "ai_circuit_failures",
            str(self._circuit_failures),
        )

        if self._circuit_failures < self.settings.ai_circuit_failures:
            return

        self._circuit_open_until = (
            time.time() + self.settings.ai_circuit_seconds
        )
        self._safe_set_setting(
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
            and self.state_allows_ai()
            and self.budget_available()
            and not self.circuit_open()
        )

    @staticmethod
    def _estimate_tokens(
        text: str,
        max_output_tokens: int,
    ) -> int:
        # Conservative approximation for a hard local budget gate.
        # UTF-8 natural language is usually <= ~4 chars/token; using 3
        # intentionally over-reserves rather than risking a cost overrun.
        input_estimate = max(1, (len(text) + 2) // 3)
        return input_estimate + max(1, max_output_tokens)

    def _reserve_budget(self, estimated_tokens: int) -> int | None:
        budget = self.settings.ai_daily_token_budget
        if budget <= 0:
            return 0

        estimate = max(1, int(estimated_tokens))
        with self._budget_lock:
            used = self.tokens_used_today()
            if (
                used
                + self._reserved_tokens
                + estimate
                > budget
            ):
                return None
            self._reserved_tokens += estimate
            return estimate

    def _release_budget(self, reservation: int) -> None:
        if reservation <= 0:
            return

        with self._budget_lock:
            self._reserved_tokens = max(
                0,
                self._reserved_tokens - reservation,
            )

    def tokens_used_today(self) -> int:
        now = time.time()
        utc_day_start = now - (now % 86400)
        try:
            return self.db.ai_tokens_since(utc_day_start)
        except Exception as exc:
            self._accounting_healthy = False
            logger.error(
                "AI accounting FAIL-CLOSED | leitura de tokens falhou | error=%s",
                type(exc).__name__,
            )
            return 0

    def budget_remaining(self) -> int | None:
        if not self._accounting_healthy:
            return 0

        budget = self.settings.ai_daily_token_budget
        if budget <= 0:
            return None

        used = self.tokens_used_today()
        if not self._accounting_healthy:
            return 0
        return max(0, budget - used)

    def budget_available(self) -> bool:
        if not self._accounting_healthy:
            return False
        remaining = self.budget_remaining()
        return (
            self._accounting_healthy
            and (remaining is None or remaining > 0)
        )

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
        if not self.state_allows_ai():
            return AIAnswer(
                text=(
                    "A camada de IA está pausada pelo estado operacional "
                    f"{self.operating_state().value}. "
                    "O Guardian determinístico continua ativo."
                ),
                model=self.settings.mistral_model,
            )

        safe_question = sanitize_for_ai(question)
        context = self.knowledge.render_context(safe_question)
        question_hash = self._hash_text(safe_question)

        if not context.strip():
            self._record_knowledge_gap(
                question_hash=question_hash,
                sample_text=safe_question,
            )
            self._record_ai_event(
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

        reservation = self._reserve_budget(
            self._estimate_tokens(
                safe_question + "\n" + context,
                self.settings.mistral_max_tokens,
            )
        )
        if reservation is None:
            return AIAnswer(
                text=(
                    "O orçamento diário de IA do ZION não possui saldo "
                    "suficiente para esta solicitação."
                ),
                model=self.settings.mistral_model,
            )

        try:
            try:
                async with self._semaphore:
                    answer = await self.client.answer(
                        question=safe_question,
                        context=context,
                    )
            finally:
                self._release_budget(reservation)

            self._record_provider_success()

            source_labels = self.knowledge.source_labels(safe_question)
            if source_labels:
                answer.text = (
                    answer.text.rstrip()
                    + "\n\nFontes ZION:\n- "
                    + "\n- ".join(source_labels)
                )

            self._record_ai_event(
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
                    "knowledge_sources": self.knowledge.source_labels(
                        safe_question
                    ),
                },
            )
            return answer

        except Exception as exc:
            self._record_provider_failure()
            logger.warning("Falha na resposta Mistral: %s", exc)
            self._record_ai_event(
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
        if not self.state_allows_ai():
            return AIAnswer(
                text=(
                    "A camada de IA está pausada pelo estado operacional "
                    f"{self.operating_state().value}."
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
                text="Orçamento diário de IA atingido. Tente novamente após a virada UTC.",
                model=self.settings.mistral_model,
            )

        if self.circuit_open():
            return AIAnswer(
                text="A camada de IA está temporariamente em proteção automática. Tente novamente em alguns minutos.",
                model=self.settings.mistral_model,
            )

        safe_text = sanitize_for_ai(text)
        reservation = self._reserve_budget(
            self._estimate_tokens(safe_text, 500)
        )
        if reservation is None:
            return AIAnswer(
                text="Orçamento diário de IA insuficiente para este resumo.",
                model=self.settings.mistral_model,
            )

        try:
            try:
                async with self._semaphore:
                    answer = await self.client.summarize(safe_text)
            finally:
                self._release_budget(reservation)

            self._record_provider_success()

            self._record_ai_event(
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
            self._record_ai_event(
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
        if not self.state_allows_ai():
            return AIAnswer(
                text=(
                    "A camada de IA está pausada pelo estado operacional "
                    f"{self.operating_state().value}."
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

        reservation = self._reserve_budget(
            self._estimate_tokens(safe_text, 700)
        )
        if reservation is None:
            return AIAnswer(
                text="Orçamento diário de IA insuficiente para esta tradução.",
                model=self.settings.mistral_model,
            )

        try:
            try:
                async with self._semaphore:
                    answer = await self.client.translate(
                        text=safe_text,
                        target_language=safe_target,
                    )
            finally:
                self._release_budget(reservation)

            self._record_provider_success()

            self._record_ai_event(
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
            self._record_ai_event(
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
        if (
            not self.enabled
            or not self.settings.ai_observe
            or not self.state_allows_ai()
        ):
            return None

        if not self.budget_available():
            return None

        if self.circuit_open():
            return None

        safe_text = sanitize_for_ai(text)
        reservation = self._reserve_budget(
            self._estimate_tokens(safe_text, 260)
        )
        if reservation is None:
            return None

        try:
            try:
                async with self._semaphore:
                    result = await self.client.classify(safe_text)
            finally:
                self._release_budget(reservation)

            self._record_provider_success()

            self._record_ai_event(
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
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={"error_type": type(exc).__name__},
            )
            return None
