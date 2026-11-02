from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import logging
import re
import threading
import time

from .agents import AgentId
from .config import Settings
from .db import ZionDB
from .knowledge import KnowledgeBase
from .knowledge import KnowledgeClassification
from .knowledge_tools import KnowledgeTools
from .generation_policy import GenerationPolicy, GenerationFailure
from .response_planner import plan_response
from .mistral import build_answer_messages
from .providers import CompletionProvider, MistralCompletionProvider
from .runtime_cost import RuntimeCostBudget, RequestAdmission
from .language_recovery import recover_language
from .mistral import MistralClient
from .provider_budget import ProviderTokenBudget, ProviderBudgetError
from .models import (
    AIAnswer,
    AIClassification,
    AIRouteClassification,
    OperatingState,
)
from .secret_store import SecretStore
from .router import _fold
from .response_guard import (TRANSFORMED_SCAM_NOTICE, is_broad_product_comparison,
                             public_fallback_for, repair_public_response,
                             scam_surface_reason,
                             validate_public_response, wallet_connection_triage)


logger = logging.getLogger("zion.ai")


AI_REQUEST_OVERHEAD_TOKEN_RESERVE = 4096


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


def _wallet_connection_failure(canonical: str) -> bool:
    """Only explicit wallet-connection trouble gets the fixed support intake."""
    if len(canonical) > 180 or "\n" in canonical:
        return False
    if re.search(r"\b(?:api|endpoint|sdk|webhook|bot)\b", canonical):
        return False
    # A later swap failure must not turn an already connected wallet into a
    # connection incident. Match trouble and wallet in the same clause.
    clauses = re.split(r"[,;.!?]|\b(?:mas|porem)\b", canonical)
    connection_action = r"(?:re)?conect(?:ar|a|am|ou|ando|ei|o)\b"
    trouble = (
        rf"\b(?:nao consigo|nao consegui|nao consegue|nao esta conseguindo|"
        rf"nao da (?:para|pra))\b.{{0,55}}\b{connection_action}",
        # Wallet is the grammatical subject. This excludes advice such as
        # "por que não conectar minha carteira?" and first-person choices.
        r"\b(?:carteira|wallet)\b.{0,45}\bnao "
        r"(?:esta |ta |se )?(?:re)?conect(?:ar|a|am|ou|ando|ada|ado)\b",
        rf"\b(?:erro|falha|problema|dificuldade)\b"
        rf".{{0,45}}\b(?:{connection_action}|conex\w*\b)",
        r"\bconex\w*\b.{0,45}\b(?:falh\w*|erro)\b",
    )
    for clause in clauses:
        if not re.search(r"\b(?:carteira|wallet)\b", clause):
            continue
        if re.search(r"\bsem (?:erro|falha|problema|dificuldade)\b",
                     clause):
            continue
        if re.search(r"\bnao (?:tenho|tem|ha|esta com|estou com|apresenta) "
                     r"(?:nenhum )?(?:erro|falha|problema|dificuldade)\b", clause):
            continue
        if any(re.search(pattern, clause) for pattern in trouble):
            return True
    return False


def _public_wallet_triage_context(knowledge: KnowledgeBase) -> str:
    """Check the reviewed EIR source directly, independent of caller query."""
    if knowledge.load_errors:
        return ""
    for chunk in knowledge.chunks:
        authority = chunk.authority
        if (
            authority.classification is not KnowledgeClassification.PUBLIC
            or authority.source_identity != "zswap-public-disclosure-policy"
            or authority.source_id != "zswap-public-disclosure-policy"
            or authority.filename != "zswap-safety-boundary.md"
            or not authority.allows(AgentId.EIR)
            or _fold(chunk.heading) != "seguranca de carteira"
        ):
            continue
        body = _fold(chunk.text)
        if all(term in body for term in (
            "nunca deve pedir", "seed phrase", "chave privada", "senha da carteira"
        )):
            return f"[Contexto oficial: {chunk.heading}]\n{chunk.text}"
    return ""


_WALLET_TRIAGE_SOURCE_UNAVAILABLE = (
    "Ainda não tenho informação oficial suficiente para orientar essa "
    "conexão com segurança. Fale com a equipe da Z-SWAP sem compartilhar "
    "seed phrase, chave privada ou senha da carteira."
)


UNGROUNDED_FALLBACK = (
    "Não tenho informação oficial suficiente para confirmar isso com segurança. "
    "Posso explicar o que está documentado publicamente sobre a Z-SWAP, se quiser."
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
        secret_store: SecretStore | None = None,
        *, generation_policy: GenerationPolicy | None = None,
        completion_providers: dict[tuple[str, str], CompletionProvider] | None = None,
        runtime_cost_budget: RuntimeCostBudget | None = None,
    ):
        self.settings = settings
        self.db = db
        self.knowledge = knowledge
        self.secret_store = secret_store or SecretStore(
            settings.mistral_secret_path
        )
        cap = max(0, settings.ai_daily_token_budget)
        self.generation_policy = generation_policy or GenerationPolicy(
            settings.mistral_model, min(settings.mistral_max_tokens, 4096))
        if self.generation_policy.baseline.model != settings.mistral_model:
            raise ValueError('baseline_policy_mismatch')
        self.completion_providers = dict(completion_providers or {})
        approvals = self.generation_policy.approvals
        self.provider_token_budget = ProviderTokenBudget(db, daily_limit=cap,
            provider_limits={name: cap for name in {'mistral', *(a.provider for a in approvals)}},
            model_limits={name: cap for name in {settings.mistral_model, *(a.model for a in approvals)}})
        self.runtime_cost_budget = runtime_cost_budget
        if runtime_cost_budget is not None:
            self.provider_token_budget = RequestAdmission(self.provider_token_budget, runtime_cost_budget)
        for (provider, model), adapter in self.completion_providers.items():
            if isinstance(adapter, MistralCompletionProvider):
                if provider != 'mistral' or adapter.client.settings.mistral_model != model:
                    raise ValueError('candidate_adapter_mismatch')
                # Mistral retries require admission at the HTTP-attempt level,
                # not one reservation around an entire retriable completion.
                adapter.client.token_budget = self.provider_token_budget
        self.client = MistralClient(settings, self.secret_store,
                                   token_budget=self.provider_token_budget,
                                   knowledge_tools=KnowledgeTools(knowledge))
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
        if self._accounting_healthy:
            try:
                self.provider_token_budget.totals()
            except Exception:
                self._accounting_healthy = False
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

    def _persist_circuit_state(self) -> bool:
        try:
            with self.db.transaction():
                self.db.set_setting(
                    "ai_circuit_failures",
                    str(self._circuit_failures),
                )
                self.db.set_setting(
                    "ai_circuit_open_until",
                    str(self._circuit_open_until),
                )
            return True
        except Exception as exc:
            logger.warning(
                "Falha ao persistir circuit breaker da IA atomicamente | "
                "error=%s",
                type(exc).__name__,
            )
            return False

    def _reset_circuit(self) -> None:
        self._circuit_failures = 0
        self._circuit_open_until = 0.0
        self._persist_circuit_state()

    def _record_provider_success(self) -> None:
        if self._circuit_failures or self._circuit_open_until:
            self._reset_circuit()

    def _record_provider_failure(self) -> None:
        self._circuit_failures += 1

        if self._circuit_failures >= self.settings.ai_circuit_failures:
            self._circuit_open_until = (
                time.time() + self.settings.ai_circuit_seconds
            )

        self._persist_circuit_state()

        if self._circuit_failures < self.settings.ai_circuit_failures:
            return

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
        # Conservative admission reserve. Do not estimate from average
        # chars/token: Unicode and serialization overhead can invalidate
        # that assumption. Reserve at least twice the UTF-8 payload bytes
        # plus a fixed allowance for system prompts/wrappers, then the
        # provider-side output ceiling.
        payload_bytes = len(
            (text or "").encode("utf-8", errors="replace")
        )
        input_reserve = max(
            1,
            (payload_bytes * 2)
            + AI_REQUEST_OVERHEAD_TOKEN_RESERVE,
        )
        return input_reserve + max(1, int(max_output_tokens))

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

    @staticmethod
    def _utc_day_number(now: float | None = None) -> int:
        ts = time.time() if now is None else now
        return int(ts // 86400)

    def _uncertain_budget_tokens_today(self) -> int:
        raw = self.db.get_setting("ai_uncertain_budget")
        if raw is None:
            return 0

        day_text, separator, tokens_text = raw.partition(":")
        if not separator:
            raise ValueError("invalid uncertain AI budget state")

        day = int(day_text)
        tokens = max(0, int(tokens_text))
        if day != self._utc_day_number():
            return 0
        return tokens

    def _charge_uncertain_budget(self, estimated_tokens: int) -> bool:
        estimate = max(0, int(estimated_tokens))
        if estimate <= 0:
            return True

        with self._budget_lock:
            try:
                current = self._uncertain_budget_tokens_today()
                day = self._utc_day_number()
                self.db.set_setting(
                    "ai_uncertain_budget",
                    f"{day}:{current + estimate}",
                )
                return True
            except Exception as exc:
                self._accounting_healthy = False
                logger.error(
                    "AI accounting FAIL-CLOSED | "
                    "uso incerto não persistido | error=%s",
                    type(exc).__name__,
                )
                return False

    def _record_provider_success_event(
        self,
        *,
        reservation: int,
        input_tokens: int,
        output_tokens: int,
        **event_kwargs,
    ) -> bool:
        recorded = self._record_ai_event(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **event_kwargs,
        )
        if recorded:
            return True

        # The provider returned successfully, so external usage already
        # happened. If the exact event ledger write fails, persist that
        # usage in the conservative UTC-day accounting channel so a
        # restart cannot make the cost disappear.
        exact_usage = (
            max(0, int(input_tokens))
            + max(0, int(output_tokens))
        )
        fallback_usage = (
            exact_usage if exact_usage > 0 else max(0, reservation)
        )
        charged = self._charge_uncertain_budget(fallback_usage)
        logger.error(
            "AI success ledger fallback | exact_event_persisted=false | "
            "fallback_tokens=%s | fallback_persisted=%s",
            fallback_usage,
            charged,
        )
        return False

    def tokens_used_today(self) -> int:
        now = time.time()
        utc_day_start = now - (now % 86400)
        try:
            recorded = self.db.ai_tokens_since(utc_day_start)
            uncertain = self._uncertain_budget_tokens_today()
            return recorded + uncertain
        except Exception as exc:
            self._accounting_healthy = False
            logger.error(
                "AI accounting FAIL-CLOSED | leitura de tokens falhou | error=%s",
                type(exc).__name__,
            )
            return 0

    def budget_remaining(self) -> int | None:
        if not self.accounting_healthy:
            return 0

        budget = self.settings.ai_daily_token_budget
        if budget <= 0:
            return None

        used = self.tokens_used_today()
        if not self._accounting_healthy:
            return 0
        try:
            # The two ledgers overlap: use the larger conservative total,
            # never sum them and double-charge successful calls.
            used = max(used, self.provider_token_budget.totals()['total'])
        except Exception:
            self._accounting_healthy = False
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

    async def _generate_answer(self, kwargs: dict, *, agent: AgentId,
                               context_query: str) -> AIAnswer:
        chunks = self.knowledge.search(context_query, agent_id=agent)
        public_only = bool(chunks) and all(
            c.authority.classification is KnowledgeClassification.PUBLIC for c in chunks)
        available = frozenset(key for key, client in self.completion_providers.items()
                              if self.runtime_cost_budget is not None and client.configured)
        selection = self.generation_policy.select(
            plan_response(agent_id=agent, question=kwargs['question'], has_evidence=bool(chunks)),
            has_evidence=bool(chunks), public_only=public_only, available=available)
        if selection.reason == 'baseline':
            try:
                return await self.client.answer(**kwargs)
            except ProviderBudgetError:
                raise
            except Exception:
                raise GenerationFailure('mistral', self.settings.mistral_model) from None
        # Candidate generation gets PUBLIC-only evidence and no tool authority.
        # No implicit retry/fallback after an uncertain request or rejection.
        evidence = KnowledgeTools(self.knowledge).call('search_approved_knowledge',
            {'query': context_query}, agent_id=agent).render()
        if not evidence:
            raise ProviderBudgetError('candidate_evidence_unavailable')
        messages = build_answer_messages(question=kwargs['question'], context=evidence,
            # Historical assistant output may have been grounded in CONTROLLED
            # material. It has no public classification and cannot be exported
            # to a new provider merely because this turn retrieves PUBLIC data.
            conversation_context='', agent_id=agent.value)
        import json
        # Every token is at least one byte, so the serialized size is already a
        # true upper bound on input tokens; the old 2x factor reserved ~10x the
        # real K3 cost and tripped the per-request cap.
        upper = len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 256
        adapter = self.completion_providers[(selection.provider, selection.model)]
        try:
            reservation = (None if isinstance(adapter, MistralCompletionProvider) else
                self.provider_token_budget.reserve(selection.provider, selection.model,
                    upper + selection.max_output_tokens))
        except ProviderBudgetError:
            # Nothing was sent: a spent or unavailable candidate budget keeps
            # the member answered by the baseline instead of an error.
            logger.info("Escalada sem orçamento; usando baseline | provider=%s",
                        selection.provider)
            try:
                return await self.client.answer(**kwargs)
            except ProviderBudgetError:
                raise
            except Exception:
                raise GenerationFailure('mistral', self.settings.mistral_model) from None
        try:
            result = await adapter.complete(messages, max_tokens=selection.max_output_tokens)
            if result.model != selection.model:
                raise ProviderBudgetError('unexpected_response_model')
            if reservation is not None:
                self.provider_token_budget.settle(reservation, result.input_tokens, result.output_tokens)
            return AIAnswer(result.text, result.model, result.input_tokens,
                result.output_tokens, result.latency_ms, evidence)
        except ProviderBudgetError:
            raise
        except Exception:
            raise GenerationFailure(selection.provider, selection.model) from None
        finally:
            if reservation is not None:
                self.provider_token_budget.retain_uncertain(reservation)

    async def answer(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        question: str,
        context_query: str | None = None,
        conversation_context: str | None = None,
        agent_id: AgentId | str = AgentId.ZION,
    ) -> AIAnswer:
        try:
            selected_agent = (
                agent_id
                if isinstance(agent_id, AgentId)
                else AgentId(str(agent_id).strip().lower())
            )
        except ValueError:
            return AIAnswer(
                text=(
                    "Não foi possível confirmar a identidade autorizada para "
                    "esta resposta."
                ),
                model="zion-local",
            )
        if not self.state_allows_ai():
            return AIAnswer(
                text=(
                    "No momento não consigo usar a IA porque o ZION está no "
                    f"modo {self.operating_state().value}. A proteção da "
                    "comunidade continua funcionando normalmente."
                ),
                model=self.settings.mistral_model,
            )

        interpretation = recover_language(question)
        if not conversation_context and interpretation.clarification:
            return AIAnswer(text=interpretation.clarification, model="zion-local")
        if re.fullmatch(r"(?:a )?minha ordem sumiu[.!?]*", interpretation.canonical):
            return AIAnswer(
                text="Ela sumiu apenas da lista de ordens abertas ou também não aparece no histórico?",
                model="zion-local",
            )

        # No developer interface is explicitly approved in the current public
        # corpus. Refuse interface discovery before retrieval or history can
        # introduce private routes. Public interface publication needs review.
        interface_request = re.search(
            r"\b(?:endpoints?|sdks?|webhooks?|developer|development|"
            r"desenvolvedor|desenvolvimento|integracao|integrar)\b|"
            r"\b(?:apis?|conectar)\b.*\bbot\b|"
            r"\b(?:quais|listar?|conectar|usar)\b.*\bapis?\b",
            recover_language(question).canonical,
        )
        if selected_agent is AgentId.MIMIR and interface_request:
            return AIAnswer(
                text=(
                    "Ainda não tenho uma interface pública oficialmente aprovada "
                    "para indicar nessa integração. Não posso fornecer endpoints "
                    "internos. Qual caso de uso você quer implementar no seu bot?"
                ),
                model="zion-local",
            )

        safe_question = sanitize_for_ai(question)
        safe_context_query = sanitize_for_ai(recover_language(context_query or question).canonical)
        safe_conversation_context = sanitize_for_ai(
            conversation_context or ""
        )[:6000]
        context = self.knowledge.render_context(
            safe_context_query,
            agent_id=selected_agent,
        )
        if not context.strip():
            # The corpus is Portuguese and the search is lexical: a question
            # in Chinese, Spanish or slang found nothing (2026-11-02). Ask the
            # model for a short Portuguese search query and retry; the reply
            # itself still follows the member's language.
            rewritten = await self._portuguese_search_query(safe_question)
            if rewritten:
                safe_context_query = sanitize_for_ai(recover_language(rewritten).canonical)
                context = self.knowledge.render_context(safe_context_query, agent_id=selected_agent)
        if (selected_agent is AgentId.ZION and len(safe_context_query) <= 6000
                and is_broad_product_comparison(safe_question)):
            # The public tool projection keeps reviewed feature-state sections
            # together for this broad question. It is also used by the isolated
            # generation evaluator; never substitute CONTROLLED/raw sources.
            comparison_context = KnowledgeTools(self.knowledge).call(
                'search_approved_knowledge', {'query': safe_context_query},
                agent_id=selected_agent).render()
            if comparison_context:
                context = comparison_context
        question_hash = self._hash_text(safe_question)

        if (selected_agent is AgentId.EIR
                and _wallet_connection_failure(interpretation.canonical)):
            wallet_context = _public_wallet_triage_context(self.knowledge)
            local_reply = _WALLET_TRIAGE_SOURCE_UNAVAILABLE
            template = "wallet_connection_source_unavailable"
            if wallet_context:
                candidate_reply = wallet_connection_triage()
                if validate_public_response(
                    candidate_reply, official_context=wallet_context
                ).allowed:
                    local_reply = candidate_reply
                    template = "wallet_connection_triage"
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model="zion-local",
                success=True,
                input_hash=question_hash,
                metadata={
                    "knowledge_hits": 1 if wallet_context else 0,
                    "provider_called": False,
                    "agent_id": selected_agent.value,
                    "local_template": template,
                },
            )
            return AIAnswer(text=local_reply, model="zion-local")

        canonical_answer = self.knowledge.canonical_finite_answer(
            safe_question,
            agent_id=selected_agent,
        )
        if canonical_answer is not None:
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model="zion-local",
                success=True,
                input_hash=question_hash,
                metadata={
                    "knowledge_hits": len(
                        self.knowledge.search(
                            safe_context_query,
                            agent_id=selected_agent,
                        )
                    ),
                    "provider_called": False,
                    "canonical_finite_list": True,
                },
            )
            return AIAnswer(
                text=canonical_answer,
                model="zion-local",
            )

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
            if selected_agent in (AgentId.EIR, AgentId.ZION, AgentId.MIMIR, AgentId.FREYR):
                # "Boa noite, estou com um probleminha" needs a question back,
                # not "no official information"; nothing factual is claimed.
                natural = await self.converse(
                    situation='open_support' if selected_agent is AgentId.EIR else 'conversation',
                    agent_id=selected_agent, text=safe_question, language='und',
                    member_turns=tuple(t for t in safe_conversation_context.split('\n') if t.strip()))
                if natural:
                    return AIAnswer(text=natural, model=self.settings.mistral_model)
            return AIAnswer(
                text=(
                    "Ainda não tenho informação oficial suficiente para "
                    "responder isso com segurança. Se quiser, reformule a "
                    "pergunta ou fale com a equipe da Z-SWAP."
                ),
                model=self.settings.mistral_model,
            )

        if not self.enabled:
            return AIAnswer(
                text=(
                    "Ainda não consigo responder por IA, mas a proteção da "
                    "comunidade continua ativa."
                ),
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
                text=(
                    "Ativei uma proteção automática por causa de uma "
                    "indisponibilidade temporária. Tente novamente em alguns "
                    "minutos."
                ),
                model=self.settings.mistral_model,
            )

        reservation = self._reserve_budget(
            self._estimate_tokens(
                safe_question
                + "\n"
                + context
                + "\n"
                + safe_conversation_context,
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
                    client_kwargs: dict[str, str] = {
                        "question": safe_question,
                        "context": context,
                    }
                    if selected_agent is not AgentId.ZION:
                        client_kwargs["agent_id"] = selected_agent.value
                    if safe_conversation_context:
                        client_kwargs["conversation_context"] = (
                            safe_conversation_context
                        )
                    answer = await self._generate_answer(client_kwargs, agent=selected_agent,
                                                         context_query=safe_context_query)
            finally:
                self._release_budget(reservation)

            self._record_provider_success()

            self._record_provider_success_event(
                reservation=reservation,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_hash=question_hash,
                metadata={
                    "knowledge_hits": len(
                        self.knowledge.search(
                            safe_context_query,
                            agent_id=selected_agent,
                        )
                    ),
                    "knowledge_sources": self.knowledge.source_labels(
                        safe_context_query,
                        agent_id=selected_agent,
                    ),
                    "agent_id": selected_agent.value,
                },
            )
            approved_response_context = context + "\n" + answer.evidence_context
            # Telegram gets plain text: "**negrito**" showed up literally.
            answer = replace(answer, text=re.sub(r'\*\*(.+?)\*\*|__(.+?)__',
                                                 lambda m: m.group(1) or m.group(2), answer.text))
            check = validate_public_response(answer.text,
                official_context=approved_response_context)
            if not check.allowed:
                repaired = repair_public_response(
                    answer.text, official_context=approved_response_context,
                    reason=check.reason)
                if repaired is not None:
                    # Audited separately: a repair is not a clean model pass.
                    self._record_ai_event(
                        chat_id=chat_id, user_id=user_id, purpose="response_repair",
                        model=answer.model, success=True, input_hash=question_hash,
                        metadata={"reason": check.reason, "agent_id": selected_agent.value},
                    )
                    return await self._grounded(replace(answer, text=repaired),
                                                approved_response_context, question_hash,
                                                chat_id, user_id, selected_agent)
                self._record_ai_event(
                    chat_id=chat_id, user_id=user_id, purpose="response_guard",
                    model=answer.model, success=False, input_hash=question_hash,
                    metadata={"reason": check.reason, "agent_id": selected_agent.value},
                )
                rewritten = await self._rewrite_after_guard(
                    question=safe_question, previous=answer.text, reason=check.reason,
                    official_context=approved_response_context, agent=selected_agent)
                if rewritten is not None:
                    self._record_ai_event(
                        chat_id=chat_id, user_id=user_id, purpose="response_rewrite",
                        model=answer.model, success=True, input_hash=question_hash,
                        metadata={"reason": check.reason, "agent_id": selected_agent.value})
                    return await self._grounded(replace(answer, text=rewritten),
                                                approved_response_context, question_hash,
                                                chat_id, user_id, selected_agent)
                return replace(answer, text=public_fallback_for(
                    check.reason, official_context=approved_response_context,
                    question=safe_question))
            return await self._grounded(answer, approved_response_context, question_hash,
                                        chat_id, user_id, selected_agent)

        except ProviderBudgetError:
            return AIAnswer(text="O limite de uso da IA está indisponível ou foi atingido. Tente novamente mais tarde.",
                            model=self.settings.mistral_model)

        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            failed_model = exc.model if isinstance(exc, GenerationFailure) else self.settings.mistral_model
            failed_provider = exc.provider if isinstance(exc, GenerationFailure) else 'mistral'
            logger.warning("Falha na geração | provider=%s | error=%s", failed_provider, type(exc).__name__)
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="support_answer",
                model=failed_model,
                success=False,
                input_hash=question_hash,
                metadata={
                    "provider": failed_provider,
                    "error_type": type(exc).__name__,
                    "budget_estimate_tokens": reservation,
                    "usage_outcome": "uncertain",
                },
            )
            return AIAnswer(
                text=(
                    "A IA está indisponível agora. Tente novamente em "
                    "alguns instantes; a proteção da comunidade continua "
                    "funcionando normalmente."
                ),
                model=failed_model,
            )

    def _public_reference_context(self) -> str:
        """Official hosts/contacts that may appear in a restated text."""
        return '\n'.join(chunk.text for chunk in self.knowledge.chunks
                         if chunk.authority.classification is KnowledgeClassification.PUBLIC)

    def _contain_transformed_output(self, answer: AIAnswer, *, purpose: str,
                                    chat_id, user_id, input_hash: str) -> AIAnswer:
        try:
            reason = scam_surface_reason(answer.text,
                                         official_context=self._public_reference_context())
        except Exception:
            reason = 'guard_unavailable'
        if reason is None:
            return answer
        self._record_ai_event(chat_id=chat_id, user_id=user_id, purpose="response_guard",
            model=answer.model, success=False, input_hash=input_hash,
            metadata={"reason": reason, "source_purpose": purpose})
        return replace(answer, text=TRANSFORMED_SCAM_NOTICE)

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

            self._record_provider_success_event(
                reservation=reservation,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                chat_id=chat_id,
                user_id=user_id,
                purpose="summarize",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_hash=self._hash_text(safe_text),
            )
            return self._contain_transformed_output(answer, purpose="summarize",
                chat_id=chat_id, user_id=user_id, input_hash=self._hash_text(safe_text))
        except ProviderBudgetError:
            return AIAnswer(text="O limite de uso da IA está indisponível ou foi atingido. Tente novamente mais tarde.",
                            model=self.settings.mistral_model)

        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            logger.warning("Falha no resumo Mistral: %s", exc)
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="summarize",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={
                    "error_type": type(exc).__name__,
                    "budget_estimate_tokens": reservation,
                    "usage_outcome": "uncertain",
                },
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

            self._record_provider_success_event(
                reservation=reservation,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                chat_id=chat_id,
                user_id=user_id,
                purpose="translate",
                model=answer.model,
                success=True,
                latency_ms=answer.latency_ms,
                input_hash=self._hash_text(safe_text),
                metadata={"target_language": safe_target},
            )
            return self._contain_transformed_output(answer, purpose="translate",
                chat_id=chat_id, user_id=user_id, input_hash=self._hash_text(safe_text))
        except ProviderBudgetError:
            return AIAnswer(text="O limite de uso da IA está indisponível ou foi atingido. Tente novamente mais tarde.",
                            model=self.settings.mistral_model)

        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
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
                    "budget_estimate_tokens": reservation,
                    "usage_outcome": "uncertain",
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

            self._record_provider_success_event(
                reservation=reservation,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=result.model or self.settings.mistral_model,
                success=True,
                category=result.category,
                risk=result.risk,
                requires_human=result.requires_human,
                latency_ms=result.latency_ms,
                input_hash=self._hash_text(safe_text),
            )
            return result

        except ProviderBudgetError:
            return None

        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            logger.warning("Falha no classificador Mistral: %s", exc)
            self._record_ai_event(
                chat_id=chat_id,
                user_id=user_id,
                purpose="moderation_observe",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={
                    "error_type": type(exc).__name__,
                    "budget_estimate_tokens": reservation,
                    "usage_outcome": "uncertain",
                },
            )
            return None

    def _public_topic_context(self, text: str) -> str:
        """PUBLIC sections about the member's own topic for a tactful reply."""
        try:
            query = sanitize_for_ai(recover_language(text).canonical)
            chunks = self.knowledge.search(query, limit=2, agent_id=AgentId.ZION)
        except Exception:
            return ''
        return "\n\n".join(
            f"[Contexto oficial: {c.heading}]\n{c.text}" for c in chunks
            if c.authority.classification is KnowledgeClassification.PUBLIC)

    def _non_custodial_context(self) -> str:
        """The PUBLIC facts a distrust reply may rely on, nothing else: the
        non-custodial definition and the signing/confirmation guidance."""
        found = []
        for chunk in self.knowledge.chunks:
            if chunk.authority.classification is not KnowledgeClassification.PUBLIC:
                continue
            body = _fold(chunk.text)
            if (('nao custodial' in body and 'seed phrase' in body)
                    or 'assinaturas devem ocorrer na carteira' in body
                    or 'antes de confirmar, o usuario deve conferir' in body):
                found.append(f"[Contexto oficial: {chunk.heading}]\n{chunk.text}")
        return "\n\n".join(found[:3])

    async def _grounded(self, answer: AIAnswer, official_context: str, question_hash: str,
                        chat_id, user_id, agent: AgentId) -> AIAnswer:
        """Apply the AI grounding review after the guard has accepted a reply.

        Only with the approved stronger model (the baseline reviewer rejected
        too many correct replies in evaluation). It can only cut sentences or
        withhold; on any review failure the guard's accepted reply stands.
        """
        candidate = self._approved_candidate()
        if candidate is None or candidate[0].model != 'kimi-k3':
            # Only the reviewer that was measured (K3: 12/12 caught, 1/10
            # false positive) may cut or withhold replies.
            return answer
        verdict = await self.review_grounding(answer=answer.text, official_context=official_context)
        if verdict is None or verdict.supported:
            return answer
        from .grounding import remove_sentences
        trimmed = remove_sentences(answer.text, verdict.unsupported_sentences)
        keeps_enough = len(trimmed) >= 60 and len(trimmed) >= 0.4 * len(answer.text)
        if keeps_enough and validate_public_response(trimmed, official_context=official_context).allowed:
            self._record_ai_event(chat_id=chat_id, user_id=user_id, purpose="response_repair",
                                  model=answer.model, success=True, input_hash=question_hash,
                                  metadata={"reason": "ungrounded", "agent_id": agent.value,
                                            "removed": len(verdict.unsupported_sentences)})
            return replace(answer, text=trimmed)
        self._record_ai_event(chat_id=chat_id, user_id=user_id, purpose="response_guard",
                              model=answer.model, success=False, input_hash=question_hash,
                              metadata={"reason": "ungrounded", "agent_id": agent.value})
        return replace(answer, text=UNGROUNDED_FALLBACK)

    async def _rewrite_after_guard(self, *, question: str, previous: str, reason: str,
                                   official_context: str, agent: AgentId) -> str | None:
        """One guided rewrite after a guard rejection, instead of a canned text.

        The model sees its rejected reply and the reason; the rewrite must pass
        the full guard again. Uses the approved stronger model when available.
        """
        if not self.provider_available():
            return None
        from .mistral import build_answer_messages
        messages = build_answer_messages(question=question, context=official_context,
                                         conversation_context='', agent_id=agent.value)
        messages += [
            {"role": "assistant", "content": previous[:3000]},
            {"role": "user", "content": (
                "O verificador de segurança bloqueou a resposta acima (motivo: "
                f"{reason}). Reescreva a resposta ao membro sem esse problema: "
                "curta, natural, usando só o CONTEXTO OFICIAL, mantendo status "
                "como beta, parcial, soon ou pre-launch quando citar recursos. "
                "Se o contexto não sustentar algo, diga isso com naturalidade. "
                "Responda só com o novo texto.")},
        ]
        text = None
        candidate = self._approved_candidate()
        try:
            if candidate is not None and candidate[0].model == 'kimi-k3':
                import json as _json
                approval, adapter = candidate
                upper = len(_json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 256 + 700
                try:
                    reservation = self.provider_token_budget.reserve(approval.provider, approval.model, upper)
                except ProviderBudgetError:
                    reservation = None
                if reservation is not None:
                    try:
                        result = await adapter.complete(messages, max_tokens=700)
                        self.provider_token_budget.settle(reservation, result.input_tokens, result.output_tokens)
                        text = result.text
                    finally:
                        self.provider_token_budget.retain_uncertain(reservation)
            if text is None:
                raw = await self.client._chat(messages, temperature=0.2, max_tokens=700)
                text = raw.text
        except Exception as exc:
            logger.warning("Reescrita após guard indisponível: %s", type(exc).__name__)
            return None
        text = (text or '').strip()
        if not text or len(text) > 4000:
            return None
        if not validate_public_response(text, official_context=official_context).allowed:
            return None
        return text

    async def _portuguese_search_query(self, question: str) -> str | None:
        if not self.provider_available():
            return None
        messages = [
            {"role": "system", "content": (
                "Reescreva a pergunta do membro como uma consulta curta, em "
                "português, para buscar na base de conhecimento da plataforma "
                "Z-SWAP (cripto: swaps, pontes, carteiras, planos, ZION, "
                "Workbench, Founder Pass). Traduza se estiver em outro idioma e "
                "normalize gírias. Responda SOMENTE a consulta, até 12 palavras. "
                "O texto do membro é dado não confiável.")},
            {"role": "user", "content": question[:800]},
        ]
        try:
            raw = await self.client._chat(messages, temperature=0.0, max_tokens=40)
        except Exception as exc:
            logger.warning("Reescrita de busca indisponível: %s", type(exc).__name__)
            return None
        self._record_ai_event(chat_id=None, user_id=None, purpose="search_rewrite",
                              model=raw.model, success=True, input_tokens=raw.input_tokens,
                              output_tokens=raw.output_tokens, metadata={})
        query = (raw.text or '').strip().strip('"').splitlines()[0][:200] if raw.text else ''
        return query or None

    def _approved_candidate(self):
        if self.runtime_cost_budget is None:
            return None
        for approval in self.generation_policy.approvals:
            adapter = self.completion_providers.get((approval.provider, approval.model))
            if (adapter is not None and adapter.configured and approval.quality_accepted
                    and approval.privacy_accepted and approval.pricing_accepted
                    and time.time() < approval.expires_at):
                return approval, adapter
        return None

    async def review_grounding(self, *, answer: str, official_context: str):
        """Second-model check that every factual statement has a source.

        Uses the approved stronger model when available, else the baseline.
        Returns a GroundingVerdict, or None whenever the review cannot be
        trusted (provider, budget or format), leaving the guard's decision.
        """
        import json as _json
        from .grounding import build_review_messages, parse_verdict
        if not self.provider_available() or not official_context.strip():
            return None
        messages = build_review_messages(answer, official_context)
        candidate = self._approved_candidate()
        try:
            if candidate is not None:
                approval, adapter = candidate
                upper = len(_json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 256 + 500
                try:
                    reservation = self.provider_token_budget.reserve(approval.provider, approval.model, upper)
                except ProviderBudgetError:
                    candidate = None
                else:
                    try:
                        result = await adapter.complete(messages, max_tokens=500)
                        self.provider_token_budget.settle(reservation, result.input_tokens, result.output_tokens)
                        text, model = result.text, result.model
                        tokens = (result.input_tokens, result.output_tokens)
                    finally:
                        self.provider_token_budget.retain_uncertain(reservation)
            if candidate is None:
                raw = await self.client._chat(messages, temperature=0.0, max_tokens=500)
                text, model, tokens = raw.text, raw.model, (raw.input_tokens, raw.output_tokens)
        except ProviderBudgetError:
            return None
        except Exception as exc:
            logger.warning("Revisão de fundamentação indisponível: %s", type(exc).__name__)
            return None
        verdict = parse_verdict(text, answer)
        self._record_ai_event(
            chat_id=None, user_id=None, purpose="grounding_review", model=model,
            success=verdict is not None, input_tokens=tokens[0], output_tokens=tokens[1],
            metadata={"supported": None if verdict is None else verdict.supported,
                      "flagged": 0 if verdict is None else len(verdict.unsupported_sentences)})
        if verdict is None:
            return None
        from dataclasses import replace as _replace
        return _replace(verdict, model=model, input_tokens=tokens[0], output_tokens=tokens[1])

    async def _converse_with_candidate(self, candidate, messages):
        """K3 for the most delicate conversational turns; None falls back."""
        import json as _json
        from .mistral import MistralRawResponse
        approval, adapter = candidate
        upper = len(_json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 256 + 180
        try:
            reservation = self.provider_token_budget.reserve(approval.provider, approval.model, upper)
        except ProviderBudgetError:
            return None
        try:
            result = await adapter.complete(messages, max_tokens=180)
            if result.model != approval.model:
                return None
            self.provider_token_budget.settle(reservation, result.input_tokens, result.output_tokens)
            return MistralRawResponse(text=result.text, model=result.model,
                                      input_tokens=result.input_tokens,
                                      output_tokens=result.output_tokens,
                                      latency_ms=result.latency_ms)
        except Exception as exc:
            logger.warning("Candidato conversacional indisponível: %s", type(exc).__name__)
            return None
        finally:
            self.provider_token_budget.retain_uncertain(reservation)

    async def converse(self, *, situation: str, agent_id: AgentId | str, text: str,
                       member_turns: tuple[str, ...] = (), bot_replies: tuple[str, ...] = (),
                       language: str = 'pt') -> str | None:
        """A natural reply for a tactful turn, or None to keep the fixed fallback."""
        from .conversation import acceptable_reply, build_conversation_messages, repeats_previous
        from .mistral import AGENT_IDENTITY_PROMPTS
        if not self.provider_available():
            return None
        agent = AgentId(agent_id)
        official = self._non_custodial_context() if situation == 'trust_concern' else ''
        if situation == 'trust_concern' and not official:
            return None
        if situation in ('complaint', 'trust_concern', 'conversation'):
            # "E pq eu deveria comprar o Founder Pass" read as a complaint got
            # "no official information" although the KB covers it (2026-11-02).
            official = "\n\n".join(p for p in (official, self._public_topic_context(text)) if p)
        messages = build_conversation_messages(
            situation=situation, agent_identity=AGENT_IDENTITY_PROMPTS[agent.value],
            text=sanitize_for_ai(text), member_turns=tuple(sanitize_for_ai(t) for t in member_turns),
            bot_replies=bot_replies, language=language, official_context=official)
        safe_text = sanitize_for_ai(text)[:1000]
        reservation = self._reserve_budget(self._estimate_tokens(
            "\n".join(m['content'] for m in messages), 180))
        if reservation is None:
            return None
        candidate = None
        if situation in ('trust_concern', 'complaint') and self.runtime_cost_budget is not None:
            for approval in self.generation_policy.approvals:
                adapter = self.completion_providers.get((approval.provider, approval.model))
                if (adapter is not None and adapter.configured and approval.quality_accepted
                        and approval.privacy_accepted and approval.pricing_accepted
                        and time.time() < approval.expires_at):
                    candidate = (approval, adapter)
                    break
        try:
            try:
                async with self._semaphore:
                    raw = None
                    if candidate is not None:
                        raw = await self._converse_with_candidate(candidate, messages)
                    if raw is None:
                        raw = await self.client.converse(messages)
            finally:
                self._release_budget(reservation)
            self._record_provider_success()
            reply = (raw.text or '').strip()
            check = validate_public_response(reply, official_context=official) if acceptable_reply(reply) else None
            accepted = bool(check and check.allowed and not repeats_previous(reply, bot_replies))
            self._record_provider_success_event(
                reservation=reservation, input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens, chat_id=None, user_id=None,
                purpose="conversation_reply", model=raw.model or self.settings.mistral_model,
                success=True, latency_ms=raw.latency_ms, input_hash=self._hash_text(safe_text),
                metadata={"situation": situation, "agent_id": agent.value, "accepted": accepted,
                          "guard": check.reason if check else "shape"},
            )
            return reply if accepted else None
        except ProviderBudgetError:
            return None
        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            logger.warning("Falha na resposta conversacional: %s", type(exc).__name__)
            return None

    async def classify_triage(self, *, text: str, context: tuple[str, ...] = ()):
        """Read one member turn; None whenever the provider or budget is unavailable.

        Callers keep their deterministic behaviour on None (fail closed to the
        existing gates). The reading grants no authority by itself.
        """
        if not self.provider_available():
            return None
        safe_text = sanitize_for_ai(text)[:1500]
        safe_context = tuple(sanitize_for_ai(c)[:400] for c in context[-3:])
        reservation = self._reserve_budget(
            self._estimate_tokens(safe_text + "\n".join(safe_context), 900))
        if reservation is None:
            return None
        try:
            try:
                async with self._semaphore:
                    result = await self.client.classify_triage(safe_text, safe_context)
            finally:
                self._release_budget(reservation)
            self._record_provider_success()
            self._record_provider_success_event(
                reservation=reservation, input_tokens=result.input_tokens,
                output_tokens=result.output_tokens, chat_id=None, user_id=None,
                purpose="community_triage",
                model=result.model or self.settings.mistral_model, success=True,
                category=result.intent, risk=result.confidence, requires_human=False,
                latency_ms=result.latency_ms, input_hash=self._hash_text(safe_text),
                metadata={"authority": "interpretation_only",
                          "risks": sorted(result.risks), "language": result.language,
                          "addressed": result.addressed, "valid": result.valid},
            )
            return result if result.valid else None
        except ProviderBudgetError:
            return None
        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            logger.warning("Falha na triagem comunitária: %s", type(exc).__name__)
            self._record_ai_event(
                chat_id=None, user_id=None, purpose="community_triage",
                model=self.settings.mistral_model, success=False,
                input_hash=self._hash_text(safe_text),
                metadata={"error_type": type(exc).__name__,
                          "budget_estimate_tokens": reservation,
                          "usage_outcome": "uncertain",
                          "authority": "interpretation_only"},
            )
            return None

    async def classify_route(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        text: str,
    ) -> AIRouteClassification | None:
        """Interpret ambiguous conversation without gaining authority."""

        if not self.provider_available():
            return None
        safe_text = sanitize_for_ai(text)[:3000]
        reservation = self._reserve_budget(
            self._estimate_tokens(safe_text, 120)
        )
        if reservation is None:
            return None
        try:
            try:
                async with self._semaphore:
                    result = await self.client.classify_route(safe_text)
            finally:
                self._release_budget(reservation)
            self._record_provider_success()
            self._record_provider_success_event(
                reservation=reservation,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                chat_id=None,
                user_id=None,
                purpose="intent_route",
                model=result.model or self.settings.mistral_model,
                success=True,
                category=result.intent,
                risk=result.confidence,
                requires_human=False,
                latency_ms=result.latency_ms,
                input_hash=self._hash_text(safe_text),
                metadata={"authority": "interpretation_only"},
            )
            return result
        except ProviderBudgetError:
            return None

        except Exception as exc:
            self._record_provider_failure()
            self._charge_uncertain_budget(reservation)
            logger.warning(
                "Falha no classificador limitado de routing: %s",
                type(exc).__name__,
            )
            self._record_ai_event(
                chat_id=None,
                user_id=None,
                purpose="intent_route",
                model=self.settings.mistral_model,
                success=False,
                input_hash=self._hash_text(safe_text),
                metadata={
                    "error_type": type(exc).__name__,
                    "budget_estimate_tokens": reservation,
                    "usage_outcome": "uncertain",
                    "authority": "interpretation_only",
                },
            )
            return None
