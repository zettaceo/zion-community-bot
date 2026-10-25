"""Bounded adversarial generation sequences, not routing/Telegram acceptance.

Only versioned synthetic questions and PUBLIC knowledge enter this harness.
Each yielded result must be durably recorded by the caller before requesting the
next turn. No cross-agent history, automatic retry or automatic PASS exists.
"""
from __future__ import annotations

import json
from pathlib import Path

from .agents import AgentId
from .evaluation import evaluate_case


def load_conversations(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not 1 <= len(cases) <= 20:
        raise ValueError('invalid conversation count')
    ids = set()
    for case in cases:
        if (set(case) != {'id', 'expected_speaker', 'turns', 'human_review_required'}
                or not isinstance(case['id'], str) or not 1 <= len(case['id']) <= 80
                or case['id'] in ids
                or case['expected_speaker'] not in {a.value for a in AgentId}
                or case['human_review_required'] is not True
                or not isinstance(case['turns'], list) or not 10 <= len(case['turns']) <= 20
                or any(not isinstance(t, str) or not 1 <= len(t) <= 2000 for t in case['turns'])):
            raise ValueError('invalid conversation fixture')
        ids.add(case['id'])
    return cases


def bounded_history(pairs: list[tuple[str, str]]) -> str:
    # Keep whole exchanges, never cut an assistant claim into a misleading fragment.
    kept = []
    size = 0
    for question, answer in reversed(pairs[-6:]):
        block = 'User: ' + question + '\nAssistant: ' + answer
        if size + len(block) + 1 > 6000:
            break
        kept.append(block)
        size += len(block) + 1
    return '\n'.join(reversed(kept))


async def evaluate_conversation(case: dict, **kwargs):
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, question in enumerate(case['turns']):
        result = await evaluate_case(
            {'id': f"{case['id']}/{index + 1}",
             'turns': case['turns'][max(0, index - 2):index + 1],
             'expected_speaker': case['expected_speaker'], 'required_terms': []},
            conversation_context=bounded_history(pairs), **kwargs,
        )
        result['scope'] = 'generation_only_synthetic_public_multiturn'
        result['conversation_id'] = case['id']
        result['turn'] = index + 1
        result['planned_turns'] = len(case['turns'])
        if result['status'] == 'REVIEW_REQUIRED':
            answer = result['response']
            normalized = ' '.join(answer.casefold().split())
            result['repeated_answer'] = normalized in seen
            if not normalized or result['repeated_answer']:
                result['status'] = 'AUTOMATED_FAIL'
                result['sequence_failure'] = 'empty_or_repeated_answer'
            else:
                seen.add(normalized)
                pairs.append((question, answer))
        yield result
        if result['status'] != 'REVIEW_REQUIRED':
            return
