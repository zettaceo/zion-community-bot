#!/usr/bin/env python3
"""Offline by default. Explicit --live enables a capped synthetic smoke/full run."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zion.db import ZionDB
from zion.evaluation import evaluate_case, load_cases
from zion.evaluation_budget import EvaluationBudget
from zion.knowledge import KnowledgeBase
from zion.mistral import MistralClient
from zion.provider_secrets import ProviderSecretStore
from zion.providers import KimiCompletionProvider, MistralCompletionProvider
from zion.secret_store import SecretStore


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or path.resolve() != path.absolute()):
        raise ValueError('unsafe evaluation directory')


async def run(args) -> int:
    cases = load_cases(ROOT / 'evaluations/cognitive-v2.jsonl')
    if not args.live:
        print(f'DATASET_OK cases={len(cases)} provider_calls=0')
        return 0
    state = Path.home() / '.local/state/zion-community-bot'
    secrets = state / 'secrets'
    if args.model in {'ministral-8b-2512', 'mistral-large-2512'}:
        config = SimpleNamespace(ai_enabled=True, mistral_model=args.model,
            mistral_api_url='https://api.mistral.ai/v1/chat/completions',
            mistral_min_request_interval_ms=1000, mistral_max_tokens=700,
            mistral_timeout_seconds=45.0, mistral_rate_limit_retries=0,
            mistral_rate_limit_max_delay_seconds=1.0)
        provider = MistralCompletionProvider(MistralClient(config, SecretStore(secrets / 'mistral-api-key')))
    else:
        provider = KimiCompletionProvider(ProviderSecretStore(secrets / 'providers').for_provider('kimi'), model=args.model)
    if not provider.configured:
        print('EVALUATION_BLOCKED credential_not_configured_or_unsafe')
        return 1
    # This is a dedicated disposable evaluation ledger. Never production zion.db.
    directory = state / 'evaluations'
    private_directory(directory)
    directory = directory / 'cognitive-v2'
    private_directory(directory)
    db = ZionDB(directory / 'evaluation.db'); db.initialize()
    budget = EvaluationBudget(db)
    try:
        EvaluationBudget.price(args.model, datetime.now(timezone.utc).date())
        knowledge = KnowledgeBase(ROOT / 'knowledge')
        if knowledge.load_errors:
            raise ValueError('knowledge_load_errors')
        # Smoke covers one technical, noisy, support, boundary and finite case.
        selected = cases if args.full else [cases[i] for i in (0, 30, 40, 60, 90)]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = directory / (stamp + '-' + args.model + '.jsonl')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        failed = False
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            for case in selected:
                result = await evaluate_case(case, knowledge=knowledge,
                    provider=provider, model=args.model, budget=budget)
                output.write(json.dumps(result, ensure_ascii=False) + '\n')
                output.flush(); os.fsync(output.fileno())
                print(f"case={result['id']} status={result['status']}", flush=True)
                if result['status'] in {'PROVIDER_FAIL', 'AUTOMATED_FAIL'}:
                    failed = True
                    break
                await asyncio.sleep(1)
        print(f'EVIDENCE={path}')
        print(f'BUDGET_RESERVED_OR_SPENT_MICRO_USD={budget.total_micro_usd()}')
        print('ACCEPTANCE=PENDING_HUMAN_REVIEW_AND_CORE_TELEGRAM_TESTS')
        return 1 if failed else 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=('kimi-k2.6', 'kimi-k3', 'ministral-8b-2512', 'mistral-large-2512'), default='kimi-k2.6')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as error:
        print('EVALUATION_FAIL error_type=' + type(error).__name__)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
