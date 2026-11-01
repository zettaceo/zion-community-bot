#!/usr/bin/env python3
"""Score community triage on evaluations/community-triage.jsonl.

`--split dev` is for prompt iteration; `--split test` is held out and should
be run once per candidate. Live runs use the production AIService/MistralClient
path with per-attempt currency admission in the isolated evaluation DB.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import make_settings
from zion.ai_service import AIService
from zion.db import ZionDB
from zion.evaluation_budget import EvaluationBudget
from zion.knowledge import KnowledgeBase
from zion.runtime_cost import RuntimeCostBudget
from zion.secret_store import SecretStore
from zion.triage import TRIAGE_RISKS, decide_action

MODEL = 'ministral-8b-2512'
REQUEST_CAP, DAILY_CAP = 50000, 500000


def score(rows: list[dict], readings: list) -> dict:
    total = len(rows)
    ok = Counter()
    risk = {r: Counter() for r in sorted(TRIAGE_RISKS)}
    failures = []
    for row, got in zip(rows, readings):
        exp = row['expected']
        if got is None:
            ok['unparsed'] += 1
            failures.append({'id': row['id'], 'error': 'no_reading'})
            continue
        want_action = decide_action(intent=exp['intent'], risks=exp['risks'], text=row['text'])
        got_action = decide_action(intent=got.intent, risks=got.risks, text=row['text'])
        checks = {
            'action': want_action == got_action,
            # The bot engages on actionable intents (host decision), so that
            # is what must match whether the member was talking to the bot.
            'engage': got.actionable == exp['addressed'],
            'intent': got.intent == exp['intent'],
            'language': exp['language'] == 'und' or got.language == exp['language'],
            'risks': set(got.risks) == set(exp['risks']),
        }
        for name, passed in checks.items():
            ok[name] += passed
        for name in risk:
            want, have = name in exp['risks'], name in got.risks
            risk[name]['tp' if want and have else 'fn' if want else 'fp' if have else 'tn'] += 1
        if not all(checks.values()):
            failures.append({'id': row['id'], 'text': row['text'][:90],
                             'expected': exp, 'want_action': want_action,
                             'got_action': got_action, 'got': {
                                 'engage': got.actionable, 'intent': got.intent,
                                 'risks': sorted(got.risks), 'language': got.language}})
    summary = {k: f"{ok[k]}/{total}" for k in ('action', 'engage', 'intent', 'language', 'risks')}
    summary['unparsed'] = ok['unparsed']
    summary['risk_recall'] = {
        n: f"{c['tp']}/{c['tp'] + c['fn']}" for n, c in risk.items() if c['tp'] + c['fn']}
    summary['risk_false_positives'] = {n: c['fp'] for n, c in risk.items() if c['fp']}
    return {'summary': summary, 'failures': failures}


async def run(split: str) -> int:
    rows = [json.loads(line) for line in open(ROOT / 'evaluations/community-triage.jsonl')
            if json.loads(line)['split'] == split]
    state = Path.home() / '.local/state/zion-community-bot'
    directory = state / 'evaluations' / 'cognitive-v2'
    secret = state / 'secrets' / 'mistral-api-key'
    if SecretStore(secret).status() != SecretStore.PRIVATE:
        raise ValueError('credential_not_configured_or_unsafe')
    price = EvaluationBudget.price(MODEL, datetime.now(timezone.utc).date())
    with tempfile.TemporaryDirectory(prefix='triage-eval-', dir=directory) as temp:
        settings = replace(make_settings(Path(temp)), knowledge_dir=ROOT / 'knowledge',
                           ai_enabled=True, ai_daily_token_budget=1000000,
                           mistral_model=MODEL, mistral_secret_path=secret)
        db = ZionDB(directory / 'evaluation-baseline.db')
        db.initialize()
        try:
            costs = RuntimeCostBudget(db, daily_limit=DAILY_CAP,
                provider_limits={'mistral': DAILY_CAP}, model_limits={MODEL: DAILY_CAP},
                request_limit=REQUEST_CAP, prices={MODEL: price})
            before = costs.totals()['total']
            ai = AIService(settings, db, KnowledgeBase(ROOT / 'knowledge'),
                           runtime_cost_budget=costs)
            readings = []
            for row in rows:
                readings.append(await ai.classify_triage(
                    text=row['text'], context=tuple(row.get('context') or ())))
                if ai.circuit_open():
                    break
            readings += [None] * (len(rows) - len(readings))
            result = score(rows, readings)
            result['split'] = split
            result['model'] = MODEL
            result['spent_or_reserved_micro_usd'] = costs.totals()['total'] - before
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            out = directory / f'{stamp}-triage-{split}.json'
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(result, handle, ensure_ascii=False, indent=1)
            print(json.dumps(result['summary'], ensure_ascii=False))
            print('MICRO_USD=' + str(result['spent_or_reserved_micro_usd']))
            print('EVIDENCE=' + str(out))
            return 0
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=('dev', 'test'), required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.split))


if __name__ == '__main__':
    raise SystemExit(main())
