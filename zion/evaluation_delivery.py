"""Synthetic PUBLIC-only AIService delivery probe; never a runtime activation.

This intentionally keeps the existing raw-generation benchmark unchanged. The
evaluation service overrides only the candidate generation boundary so the
ordinary AIService retrieval, deterministic replies, admission and output guard
can be observed without granting a production ModelApproval.
"""
from __future__ import annotations

import hashlib
import json

from .agents import AgentId
from .ai_service import AIService
from .evaluation_budget import EvaluationBudget, PriceSnapshot
from .generation_policy import GenerationFailure
from .knowledge import KnowledgeBase, KnowledgeClassification, KnowledgeSourceStatus
from .knowledge_tools import KnowledgeTools
from .mistral import build_answer_messages
from .models import AIAnswer
from .providers import CompletionProvider
from .response_guard import validate_public_response
from .runtime_cost import RuntimeCostBudget


SMOKE_IDS = (
    'v2-001', 'v2-021', 'v2-041', 'v2-051', 'v2-061',
    'v2-065', 'v2-091', 'v2-094', 'v2-101', 'v2-103',
)
EXPECTED_LOCAL = {'v2-021': 'canonical_finite_list',
                  'v2-041': 'wallet_connection_triage',
                  'v2-091': 'canonical_finite_list'}


# The model production actually serves. Kimi remains a separate candidate.
BASELINE_MODEL = 'ministral-8b-2512'
# GA Mistral models that may replace it through MISTRAL_MODEL; same provider,
# credential and data terms. Evaluated on the identical production path.
BASELINE_MODELS = (BASELINE_MODEL, 'mistral-small-2603')


class PublicEvaluationKnowledge(KnowledgeBase):
    """Reapply the PUBLIC/CURRENT projection even if the corpus reloads."""

    def reload(self) -> int:
        super().reload()
        if self.load_errors:
            raise ValueError('knowledge_load_errors')
        self.chunks = [
            chunk for chunk in self.chunks
            if (chunk.authority.classification is KnowledgeClassification.PUBLIC
                and chunk.authority.status is KnowledgeSourceStatus.CURRENT
                and not chunk.authority.superseded_by
                and any(chunk.authority.allows(agent)
                        for agent in chunk.authority.allowed_agents))
        ]
        self.sources = {
            name: source for name, source in self.sources.items()
            if (source.classification is KnowledgeClassification.PUBLIC
                and source.status is KnowledgeSourceStatus.CURRENT
                and not source.superseded_by
                and any(source.allows(agent) for agent in source.allowed_agents))
        }
        return len(self.chunks)


class NeverNetworkBaseline:
    configured = True

    async def answer(self, **_kwargs):
        raise AssertionError('baseline_provider_called_in_delivery_evaluation')


class DeliveryEvaluationService(AIService):
    """Evaluation-only K3 adapter with durable pre-request cost admission."""

    def __init__(self, *args, provider: CompletionProvider,
                 evaluation_budget: EvaluationBudget, model: str = 'kimi-k3', **kwargs):
        if model != 'kimi-k3':
            raise ValueError('delivery_probe_model_not_reviewed')
        super().__init__(*args, **kwargs)
        self.client = NeverNetworkBaseline()
        self.evaluation_provider = provider
        self.evaluation_budget = evaluation_budget
        self.evaluation_model = model
        self.provider_attempts = 0
        self.last_input_hash: str | None = None
        self.last_cost_micro_usd = 0
        self.last_error_type: str | None = None

    async def _generate_answer(self, kwargs: dict, *, agent: AgentId,
                               context_query: str) -> AIAnswer:
        evidence = KnowledgeTools(self.knowledge).call(
            'search_approved_knowledge', {'query': context_query},
            agent_id=agent,
        ).render()
        if not evidence:
            self.last_error_type = 'PublicEvidenceUnavailable'
            raise ValueError('public_evidence_unavailable')
        messages = build_answer_messages(
            question=kwargs['question'], context=evidence,
            conversation_context='', agent_id=agent.value,
        )
        self.last_input_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        try:
            reservation = self.evaluation_budget.reserve(
                self.evaluation_model, messages, 700)
            self.last_cost_micro_usd = self.evaluation_budget.charge_for(reservation)
        except Exception as error:
            self.last_error_type = type(error).__name__
            raise GenerationFailure('kimi', self.evaluation_model) from None
        self.provider_attempts += 1
        try:
            result = await self.evaluation_provider.complete(messages, max_tokens=700)
            if result.model != self.evaluation_model:
                raise ValueError('unexpected_response_model')
            self.last_cost_micro_usd = self.evaluation_budget.settle(reservation, result)
        except Exception as error:
            # The reserved estimate stays in the separate, durable evaluation
            # ledger after an uncertain provider/usage outcome.
            self.last_error_type = type(error).__name__
            raise GenerationFailure('kimi', self.evaluation_model) from None
        return AIAnswer(result.text, result.model, result.input_tokens,
                        result.output_tokens, result.latency_ms, evidence)


class _CaseAdmission:
    """Per-case view over the durable token+currency admission.

    Counts every HTTP attempt the real MistralClient admits (retries and the
    bounded tool round included) and this case's own charge: the settled
    estimate, or the full reservation when the outcome is uncertain. It never
    derives cost from a global ledger delta another evaluation could move.
    """

    def __init__(self, inner, costs: RuntimeCostBudget):
        self.inner, self.costs = inner, costs
        self.db = inner.db
        self.attempts = 0
        self.charged = 0
        self._open: dict[str, tuple[int, list[int]]] = {}

    def reserve(self, provider, model, tokens, *, today=None):
        reservation = self.inner.reserve(provider, model, tokens, today=today)
        self.attempts += 1
        cost_ref = reservation.split(':')[1]
        with self.db.transaction():
            entry = self.costs._read()['pending'][cost_ref]
        self._open[reservation] = (entry['tokens'], list(entry['price']))
        return reservation

    def settle(self, reservation, input_tokens, output_tokens):
        reserved, rates = self._open.pop(reservation)
        try:
            self.inner.settle(reservation, input_tokens, output_tokens)
        except Exception:
            self.charged += reserved
            raise
        self.charged += PriceSnapshot('reserved-rate', *rates, self.costs.today()).cost(
            input_tokens, output_tokens)

    def retain_uncertain(self, reservation):
        pending = self._open.pop(reservation, None)
        if pending is not None:
            self.charged += pending[0]
        self.inner.retain_uncertain(reservation)

    def totals(self, *, today=None):
        return self.inner.totals(today=today)


class BaselineDeliveryEvaluationService(AIService):
    """The production baseline path: real MistralClient, real tool round.

    Only the corpus (PUBLIC/CURRENT), the database (isolated evaluation file)
    and the per-attempt currency admission differ from the runtime. No
    ModelApproval exists, so GenerationPolicy can only select the baseline.
    """

    def __init__(self, settings, db, knowledge, *, runtime_cost_budget: RuntimeCostBudget):
        if settings.mistral_model not in BASELINE_MODELS or not settings.ai_enabled:
            raise ValueError('delivery_probe_model_not_reviewed')
        super().__init__(settings, db, knowledge, runtime_cost_budget=runtime_cost_budget)
        if self.generation_policy.approvals or self.completion_providers:
            raise ValueError('baseline_probe_requires_no_candidate')
        self.case_admission = _CaseAdmission(self.provider_token_budget, runtime_cost_budget)
        self.provider_token_budget = self.case_admission
        self.client.token_budget = self.case_admission
        self.evaluation_model = settings.mistral_model
        # Each rate-limit retry is a separately admitted attempt, for the
        # first request and for the single bounded tool round.
        self.max_provider_attempts = 2 * (max(0, settings.mistral_rate_limit_retries) + 1)
        self.last_input_hash: str | None = None
        self.last_error_type: str | None = None

    @property
    def provider_attempts(self) -> int:
        return self.case_admission.attempts

    @property
    def last_cost_micro_usd(self) -> int:
        return self.case_admission.charged

    @last_cost_micro_usd.setter
    def last_cost_micro_usd(self, value: int) -> None:
        self.case_admission.charged = value

    async def _generate_answer(self, kwargs: dict, *, agent: AgentId,
                               context_query: str) -> AIAnswer:
        messages = build_answer_messages(
            question=kwargs['question'], context=kwargs['context'],
            conversation_context=kwargs.get('conversation_context', ''),
            agent_id=agent.value,
        )
        self.last_input_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        try:
            return await super()._generate_answer(kwargs, agent=agent, context_query=context_query)
        except Exception as error:
            self.last_error_type = type(error).__name__
            raise


async def evaluate_delivery_case(case: dict, *, service: DeliveryEvaluationService) -> dict:
    """One frozen synthetic case. A safe fallback never becomes a model PASS."""
    if case['id'] not in SMOKE_IDS or case['human_review_required'] is not True:
        raise ValueError('unapproved_delivery_case')
    before_calls = service.provider_attempts
    before_event = service.db._conn.execute(
        'SELECT COALESCE(MAX(rowid), 0) AS n FROM ai_events'
    ).fetchone()['n']
    service.last_input_hash = None
    service.last_cost_micro_usd = 0
    service.last_error_type = None
    answer = await service.answer(
        chat_id=None, user_id=None, question=case['turns'][-1],
        context_query='\n'.join(case['turns'][-3:]),
        conversation_context='\n'.join('User: ' + turn for turn in case['turns'][:-1]),
        agent_id=case['expected_speaker'],
    )
    calls = service.provider_attempts - before_calls
    rows = service.db._conn.execute(
        'SELECT purpose, model, success, metadata_json FROM ai_events '
        'WHERE rowid > ? ORDER BY rowid', (before_event,),
    ).fetchall()
    events = [(row['purpose'], row['model'], bool(row['success']),
               json.loads(row['metadata_json'])) for row in rows]
    failed_event = any(not success for _, _, success, _ in events)
    delivered_event = any(
        purpose == 'support_answer' and success
        and model == answer.model
        for purpose, model, success, _ in events
    )
    local = answer.model == 'zion-local' or (
        calls == 0 and any(
            purpose == 'support_answer' and success
            and meta.get('provider_called') is False
            for purpose, _, success, meta in events
        )
    )
    missing = [term for term in case['required_terms']
               if term.casefold() not in answer.text.casefold()]
    official_context = service.knowledge.render_context(
        '\n'.join(case['turns'][-3:]), agent_id=case['expected_speaker'])
    official_context += '\n' + answer.evidence_context
    guard = validate_public_response(answer.text, official_context=official_context)
    if service.last_error_type:
        status = ('BUDGET_BLOCKED' if calls == 0
                  and service.last_error_type in {'EvaluationBudgetError', 'ProviderBudgetError'}
                  else 'PROVIDER_FAIL' if calls else 'HARNESS_FAIL')
    elif failed_event:
        status = 'AUTOMATED_FAIL'
    elif not guard.allowed or missing:
        status = 'AUTOMATED_FAIL'
    elif calls and (not delivered_event or not service.accounting_healthy):
        status = 'HARNESS_FAIL'
    elif local and calls == 0:
        status = 'LOCAL_REVIEW_REQUIRED'
    elif (1 <= calls <= getattr(service, 'max_provider_attempts', 1)
          and answer.model == service.evaluation_model):
        status = 'REVIEW_REQUIRED'
    else:
        status = 'HARNESS_FAIL'
    if local and status == 'LOCAL_REVIEW_REQUIRED':
        expected_template = EXPECTED_LOCAL.get(case['id'])
        verified_local = any(
            purpose == 'support_answer' and model == 'zion-local' and success
            and (meta.get('local_template') == expected_template
                 if expected_template == 'wallet_connection_triage'
                 else meta.get(expected_template) is True)
            and meta.get('provider_called') is False
            for purpose, model, success, meta in events
        )
        if not (expected_template and verified_local and calls == 0
                and service.last_cost_micro_usd == 0 and answer.model == 'zion-local'
                and guard.allowed):
            status = 'HARNESS_FAIL'
    return {
        'id': case['id'], 'model': answer.model, 'status': status,
        'response': answer.text if guard.allowed and not failed_event
                    and not service.last_error_type else '[WITHHELD_BY_OUTPUT_GUARD]',
        'guard': guard.reason, 'missing_terms': missing,
        'provider_calls': calls, 'input_hash': service.last_input_hash,
        'input_tokens': answer.input_tokens, 'output_tokens': answer.output_tokens,
        'estimated_micro_usd': service.last_cost_micro_usd,
        'usage_outcome': ('uncertain_reserved' if calls and service.last_error_type
                          else 'settled' if calls else 'no_provider'),
        'human_review': 'PENDING', 'scope': 'delivery_simulation_synthetic_public',
        'error_type': service.last_error_type,
        # A sentence-level repair is delivered, but it is not a clean pass.
        'repaired': any(purpose == 'response_repair' for purpose, _, _, _ in events),
        'event_statuses': [{'purpose': purpose, 'model': model, 'success': success}
                           for purpose, model, success, _ in events],
    }
