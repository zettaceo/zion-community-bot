#!/usr/bin/env python3
"""Score the AI grounding reviewer on evaluations/grounding-review.jsonl.

Runs AIService.review_grounding on the production path with the isolated
evaluation DB; --model kimi-k3 composes the approved escalation, otherwise
the Mistral baseline reviews.
"""
from __future__ import annotations

import argparse, asyncio, json, sys, tempfile
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import make_settings
from zion.agents import AgentId
from zion.ai_service import AIService
from zion.db import ZionDB
from zion.escalation import build_ai_composition
from zion.knowledge import KnowledgeBase
from zion.knowledge_tools import KnowledgeTools
from zion.provider_secrets import ProviderSecretStore


async def run(model: str) -> int:
    state = Path.home() / '.local/state/zion-community-bot'
    directory = state / 'evaluations' / 'cognitive-v2'
    rows = [json.loads(l) for l in open(ROOT / 'evaluations/grounding-review.jsonl')]
    with tempfile.TemporaryDirectory(prefix='grounding-eval-', dir=directory) as temp:
        settings = replace(make_settings(Path(temp)), knowledge_dir=ROOT / 'knowledge',
                           ai_enabled=True, ai_daily_token_budget=2000000,
                           mistral_secret_path=state / 'secrets' / 'mistral-api-key')
        if model == 'kimi-k3':
            settings = replace(settings, kimi_escalation_enabled=True, ai_daily_usd_cap=2.0,
                               kimi_approval_until=(date.today() + timedelta(days=2)).isoformat())
        db = ZionDB(directory / 'evaluation-baseline.db')
        db.initialize()
        try:
            store = ProviderSecretStore(state / 'secrets' / 'providers').for_provider('kimi')
            knowledge = KnowledgeBase(ROOT / 'knowledge')
            ai = AIService(settings, db, knowledge, **build_ai_composition(settings, db, store))
            tools = KnowledgeTools(knowledge)
            caught = missed = false_pos = clean = unread = 0
            details = []
            for row in rows:
                context = tools.call('search_approved_knowledge', {'query': row['query']},
                                     agent_id=AgentId.ZION).render()
                context += '\n' + knowledge.render_context(row['query'], agent_id=AgentId.ZION)
                context += '\n' + ai._non_custodial_context()
                verdict = await ai.review_grounding(answer=row['answer'], official_context=context)
                if verdict is None:
                    unread += 1
                    details.append((row['id'], 'UNREAD', row['note']))
                    continue
                flagged = not verdict.supported
                if row['verdict'] == 'unsupported':
                    caught += flagged; missed += not flagged
                else:
                    false_pos += flagged; clean += not flagged
                if flagged != (row['verdict'] == 'unsupported'):
                    details.append((row['id'], 'MISS' if row['verdict'] == 'unsupported' else 'FALSE_POSITIVE',
                                    row['note'], verdict.reason, verdict.unsupported_sentences[:1]))
            print(json.dumps({'model': model, 'caught': f'{caught}/{caught + missed}',
                              'false_positives': f'{false_pos}/{false_pos + clean}', 'unreadable': unread}))
            for d in details:
                print(d)
            return 0
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=('ministral-8b-2512', 'kimi-k3'), required=True)
    return asyncio.run(run(parser.parse_args().model))


if __name__ == '__main__':
    raise SystemExit(main())
