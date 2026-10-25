"""Generation-only A/B harness; not Telegram, routing or production acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agents import AgentId
from .conversation_state import explicit_topic
from .evaluation_budget import EvaluationBudget
from .evaluation_native import NativeEvaluationClient
from .knowledge import KnowledgeBase
from .knowledge_tools import KnowledgeTools
from .mistral import build_answer_messages
from .providers import CompletionProvider
from .response_guard import validate_public_response


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not 100 <= len(cases) <= 200 or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('invalid evaluation dataset size or ids')
    for case in cases:
        if (not 1 <= len(case['turns']) <= 8
                or any(not isinstance(t, str) or not 1 <= len(t) <= 2000 for t in case['turns'])
                or case['expected_speaker'] not in {a.value for a in AgentId}
                or case['human_review_required'] is not True):
            raise ValueError('invalid evaluation case')
    return cases


def public_context(knowledge: KnowledgeBase, question: str, agent_id: str) -> str:
    return KnowledgeTools(knowledge).call(
        'search_approved_knowledge', {'query': question}, agent_id=agent_id,
    ).render()


def evaluation_context_query(turns: list[str]) -> str:
    """Bounded user-only continuity; explicit new topics clear older questions.

    This improves generation fixtures, but is not a substitute for runtime
    routing/thread/participant acceptance.
    """
    active = None
    retained = []
    for turn in turns:
        topic = explicit_topic(turn)
        if active and topic and topic != active:
            retained = []
        active = topic or active
        retained.append(turn)
        retained = retained[-3:]
        while sum(len(item) + 1 for item in retained) > 6000:
            retained.pop(0)
    return '\n'.join(retained)


async def evaluate_case(case: dict, *, knowledge: KnowledgeBase,
                        provider: CompletionProvider, model: str,
                        budget: EvaluationBudget,
                        conversation_context: str | None = None) -> dict:
    question = case['turns'][-1]
    context = public_context(knowledge, evaluation_context_query(case['turns']), case['expected_speaker'])
    messages = build_answer_messages(question=question, context=context,
        conversation_context=(conversation_context if conversation_context is not None else
                              '\n'.join('User: ' + t for t in case['turns'][:-1])),
        agent_id=case['expected_speaker'])
    input_hash = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    # Native mode accounts each real HTTP request, including a tool completion.
    # Text-only mode reserves once. Never reserve both paths for the same request.
    native = isinstance(provider, NativeEvaluationClient)
    reservation = None if native else budget.reserve(model, messages, 700)
    native_cost_before = provider.estimated_micro_usd if native else 0
    native_requests_before = provider.request_count if native else 0
    native_uncertain_before = provider.uncertain_request_count if native else 0
    evidence = context
    try:
        if native:
            result = await provider.answer(question=question, context=context,
                conversation_context=(conversation_context if conversation_context is not None else
                    '\n'.join('User: ' + t for t in case['turns'][:-1])),
                agent_id=case['expected_speaker'])
            cost = provider.estimated_micro_usd - native_cost_before
            evidence += '\n' + result.evidence_context
        else:
            result = await provider.complete(messages, max_tokens=700)
            cost = budget.settle(reservation, result)
    except Exception as error:
        return {'id': case['id'], 'model': model, 'input_hash': input_hash,
                'status': 'PROVIDER_FAIL', 'error_type': type(error).__name__,
                'usage_outcome': ('uncertain_reserved' if not native or
                    provider.uncertain_request_count > native_uncertain_before else
                    'no_uncertain_charge'), 'human_review': 'PENDING',
                'native_requests': provider.request_count - native_requests_before if native else 0,
                'scope': 'native_mistral_generation_only' if native else 'generation_only_synthetic_public'}
    check = validate_public_response(result.text, official_context=evidence)
    missing = [t for t in case['required_terms'] if t.casefold() not in result.text.casefold()]
    return {'id': case['id'], 'model': model, 'input_hash': input_hash,
            'status': 'REVIEW_REQUIRED' if check.allowed and not missing else 'AUTOMATED_FAIL',
            'response': result.text if check.allowed else '[WITHHELD_BY_OUTPUT_GUARD]',
            'guard': check.reason, 'missing_terms': missing,
            'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens,
            'latency_ms': result.latency_ms, 'estimated_micro_usd': cost,
            'human_review': 'PENDING',
            'native_requests': provider.request_count - native_requests_before if native else 0,
            'scope': 'native_mistral_generation_only' if native else 'generation_only_synthetic_public'}
