"""Generation-only A/B harness; not Telegram, routing or production acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agents import AgentId
from .evaluation_budget import EvaluationBudget
from .knowledge import KnowledgeBase, KnowledgeClassification
from .language_recovery import recover_language
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
    # No real user data or CONTROLLED projections go to a candidate provider.
    chunks = knowledge.search(recover_language(question).canonical,
                              limit=12, agent_id=agent_id)
    return '\n\n'.join('[Contexto oficial: ' + chunk.heading + ']\n' + chunk.text
                       for chunk in chunks
                       if chunk.authority.classification is KnowledgeClassification.PUBLIC)[:8000]


async def evaluate_case(case: dict, *, knowledge: KnowledgeBase,
                        provider: CompletionProvider, model: str,
                        budget: EvaluationBudget) -> dict:
    question = case['turns'][-1]
    context = public_context(knowledge, question, case['expected_speaker'])
    messages = build_answer_messages(question=question, context=context,
        conversation_context='\n'.join('User: ' + t for t in case['turns'][:-1]),
        agent_id=case['expected_speaker'])
    input_hash = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    # Persist reservation before awaiting. Never automatically retry uncertain
    # requests or refund on exceptions, cancellation, process death or 429.
    reservation = budget.reserve(model, messages, 700)
    try:
        result = await provider.complete(messages, max_tokens=700)
        cost = budget.settle(reservation, result)
    except Exception as error:
        return {'id': case['id'], 'model': model, 'input_hash': input_hash,
                'status': 'PROVIDER_FAIL', 'error_type': type(error).__name__,
                'usage_outcome': 'uncertain_reserved', 'human_review': 'PENDING'}
    check = validate_public_response(result.text, official_context=context)
    missing = [t for t in case['required_terms'] if t.casefold() not in result.text.casefold()]
    return {'id': case['id'], 'model': model, 'input_hash': input_hash,
            'status': 'REVIEW_REQUIRED' if check.allowed and not missing else 'AUTOMATED_FAIL',
            'response': result.text if check.allowed else '[WITHHELD_BY_OUTPUT_GUARD]',
            'guard': check.reason, 'missing_terms': missing,
            'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens,
            'latency_ms': result.latency_ms, 'estimated_micro_usd': cost,
            'human_review': 'PENDING', 'scope': 'generation_only_synthetic_public'}
