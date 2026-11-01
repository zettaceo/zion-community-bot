#!/usr/bin/env python3
"""One synthetic AIService delivery case per run; default is local/no network.

The ordinary generation benchmark remains a separate, frozen diagnostic. This
probe never uses the production SQLite database or enables a runtime provider.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.evaluation import load_cases
from zion.evaluation_budget import EvaluationBudget
from zion.evaluation_delivery import (BASELINE_MODEL,
                                      BaselineDeliveryEvaluationService,
                                      DeliveryEvaluationService,
                                      PublicEvaluationKnowledge, SMOKE_IDS,
                                      evaluate_delivery_case)
from zion.provider_secrets import ProviderSecretStore
from zion.providers import KimiCompletionProvider
from zion.runtime_cost import RuntimeCostBudget
from zion.secret_store import SecretStore

PRICE_SOURCES = {
    'kimi-k3': 'https://platform.kimi.ai/',
    BASELINE_MODEL: 'https://docs.mistral.ai/models/ministral-3-8b-25-12',
}
# Separate, smaller currency caps for the production-baseline probe. Each
# admitted HTTP attempt is priced at the worst rate before it is sent.
BASELINE_REQUEST_CAP = 50000
BASELINE_DAILY_CAP = 500000


class NeverCallProvider:
    configured = False

    async def complete(self, _messages, *, max_tokens: int):
        raise AssertionError('provider_called_without_live_opt_in')


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.resolve() != path.absolute()):
        raise ValueError('unsafe_evaluation_directory')


def write_private_json(path: Path, data: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(data, output, ensure_ascii=False, sort_keys=True)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ['/usr/bin/git', '-C', str(ROOT), *args], text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(case_id: str, live: bool, model: str = 'kimi-k3') -> int:
    if case_id not in SMOKE_IDS or (case_id != 'v2-041' and not live):
        raise ValueError('case_requires_explicit_live_opt_in')
    if model not in PRICE_SOURCES:
        raise ValueError('delivery_probe_model_not_reviewed')
    baseline = live and model == BASELINE_MODEL
    if git_output('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('delivery_probe_requires_clean_worktree')
    head = git_output('rev-parse', 'HEAD')
    dataset_path = ROOT / 'evaluations/cognitive-v2.jsonl'
    cases = {case['id']: case for case in load_cases(dataset_path)}
    case = cases[case_id]
    knowledge = PublicEvaluationKnowledge(ROOT / 'knowledge')
    if not knowledge.chunks:
        raise ValueError('public_knowledge_unavailable')

    state = Path.home() / '.local/state/zion-community-bot'
    directory = state / 'evaluations' / 'cognitive-v2'
    private_directory(state / 'evaluations')
    private_directory(directory)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    stem = (stamp + '-delivery-' + ('baseline-' if baseline else '')
            + case_id + '-' + head[:8])
    manifest_path = directory / (stem + '-manifest.json')
    result_path = directory / (stem + '-result.json')

    price = None
    if baseline:
        price = EvaluationBudget.price(BASELINE_MODEL, datetime.now(timezone.utc).date())
        # The production Mistral credential is read by the real client only;
        # nothing here prints, copies or stores it.
        mistral_secret = state / 'secrets' / 'mistral-api-key'
        if SecretStore(mistral_secret).status() != SecretStore.PRIVATE:
            raise ValueError('baseline_credential_not_configured_or_unsafe')
        return await run_baseline(case, case_id, head, dataset_path, knowledge,
                                  directory, manifest_path, result_path, price,
                                  mistral_secret)
    if live:
        price = EvaluationBudget.price('kimi-k3', datetime.now(timezone.utc).date())
        provider = KimiCompletionProvider(
            ProviderSecretStore(state / 'secrets' / 'providers').for_provider('kimi'),
            model='kimi-k3',
        )
        if not provider.configured:
            raise ValueError('candidate_credential_not_configured_or_unsafe')
    else:
        provider = NeverCallProvider()

    with tempfile.TemporaryDirectory(prefix='delivery-eval-', dir=directory) as temp:
        root = Path(temp)
        settings = replace(make_settings(root),
            knowledge_dir=ROOT / 'knowledge', ai_enabled=True,
            ai_daily_token_budget=1000000)
        service_db = ZionDB(root / 'service.db')
        service_db.initialize()
        budget_db = (ZionDB(directory / 'evaluation.db') if live else service_db)
        if live:
            budget_db.initialize()
        budget = EvaluationBudget(budget_db)
        try:
            manifest = {
                'scope': 'delivery_simulation_synthetic_public',
                'case_id': case_id, 'candidate_sha': head,
                'knowledge_tree_sha': git_output('rev-parse', 'HEAD:knowledge'),
                'dataset_sha256': sha256_file(dataset_path),
                'delivery_harness_sha256': sha256_file(ROOT / 'zion/evaluation_delivery.py'),
                'ai_service_sha256': sha256_file(ROOT / 'zion/ai_service.py'),
                'response_guard_sha256': sha256_file(ROOT / 'zion/response_guard.py'),
                'model': 'kimi-k3' if live else 'zion-local',
                'price_source': PRICE_SOURCES['kimi-k3'] if price else None,
                'price_verified_on': price.verified_on.isoformat() if price else None,
                'live_opt_in': live, 'utc': datetime.now(timezone.utc).isoformat(),
                'public_chunks': len(knowledge.chunks),
                'budget_before_micro_usd': budget.total_micro_usd(),
                'caps_micro_usd': {
                    'request': budget.REQUEST_CAP,
                    'day': budget.DAILY_CAP,
                    'total': budget.TOTAL_CAP,
                },
                'human_review': 'PENDING',
            }
            write_private_json(manifest_path, manifest)
            service = DeliveryEvaluationService(
                settings, service_db, knowledge, provider=provider,
                evaluation_budget=budget,
            )
            result = await evaluate_delivery_case(case, service=service)
            result['candidate_sha'] = head
            result['manifest'] = manifest_path.name
            write_private_json(result_path, result)
            print(f"CASE={case_id} STATUS={result['status']} PROVIDER_CALLS={result['provider_calls']}")
            print(f"BUDGET_RESERVED_OR_SPENT_MICRO_USD={budget.total_micro_usd()}")
            print(f'MANIFEST={manifest_path}')
            print(f'EVIDENCE={result_path}')
            print('ACCEPTANCE=PENDING_HUMAN_REVIEW_AND_CONTROLLED_TELEGRAM_TESTS')
            return 0 if result['status'] in {'REVIEW_REQUIRED', 'LOCAL_REVIEW_REQUIRED'} else 1
        finally:
            if budget_db is not service_db:
                budget_db.close()
            service_db.close()


def _base_manifest(case_id, head, dataset_path, knowledge, model, price) -> dict:
    return {
        'scope': 'delivery_simulation_synthetic_public',
        'case_id': case_id, 'candidate_sha': head,
        'knowledge_tree_sha': git_output('rev-parse', 'HEAD:knowledge'),
        'dataset_sha256': sha256_file(dataset_path),
        'delivery_harness_sha256': sha256_file(ROOT / 'zion/evaluation_delivery.py'),
        'ai_service_sha256': sha256_file(ROOT / 'zion/ai_service.py'),
        'response_guard_sha256': sha256_file(ROOT / 'zion/response_guard.py'),
        'mistral_client_sha256': sha256_file(ROOT / 'zion/mistral.py'),
        'model': model, 'price_source': PRICE_SOURCES[model],
        'price_verified_on': price.verified_on.isoformat(),
        'live_opt_in': True, 'utc': datetime.now(timezone.utc).isoformat(),
        'public_chunks': len(knowledge.chunks),
        'human_review': 'PENDING',
    }


async def run_baseline(case, case_id, head, dataset_path, knowledge, directory,
                       manifest_path, result_path, price, mistral_secret) -> int:
    """Production model through the production AIService/MistralClient path."""
    with tempfile.TemporaryDirectory(prefix='delivery-baseline-', dir=directory) as temp:
        settings = replace(make_settings(Path(temp)),
            knowledge_dir=ROOT / 'knowledge', ai_enabled=True,
            ai_daily_token_budget=1000000, mistral_model=BASELINE_MODEL,
            mistral_secret_path=mistral_secret)
        # Durable and isolated: never the production SQLite database. The
        # token and currency ledgers must share it for atomic admission.
        db = ZionDB(directory / 'evaluation-baseline.db')
        db.initialize()
        try:
            costs = RuntimeCostBudget(db, daily_limit=BASELINE_DAILY_CAP,
                provider_limits={'mistral': BASELINE_DAILY_CAP},
                model_limits={BASELINE_MODEL: BASELINE_DAILY_CAP},
                request_limit=BASELINE_REQUEST_CAP, prices={BASELINE_MODEL: price})
            before = costs.totals()['total']
            manifest = _base_manifest(case_id, head, dataset_path, knowledge,
                                      BASELINE_MODEL, price)
            manifest.update(budget_before_micro_usd=before, caps_micro_usd={
                'request': BASELINE_REQUEST_CAP, 'day': BASELINE_DAILY_CAP})
            write_private_json(manifest_path, manifest)
            service = BaselineDeliveryEvaluationService(
                settings, db, knowledge, runtime_cost_budget=costs)
            result = await evaluate_delivery_case(case, service=service)
            result['candidate_sha'] = head
            result['manifest'] = manifest_path.name
            write_private_json(result_path, result)
            print(f"CASE={case_id} MODEL={BASELINE_MODEL} STATUS={result['status']} "
                  f"PROVIDER_CALLS={result['provider_calls']}")
            print(f"CASE_ESTIMATED_MICRO_USD={result['estimated_micro_usd']}")
            print(f"DAY_RESERVED_OR_SPENT_MICRO_USD={costs.totals()['total']}")
            print(f'MANIFEST={manifest_path}')
            print(f'EVIDENCE={result_path}')
            print('ACCEPTANCE=PENDING_HUMAN_REVIEW_AND_CONTROLLED_TELEGRAM_TESTS')
            return 0 if result['status'] in {'REVIEW_REQUIRED', 'LOCAL_REVIEW_REQUIRED'} else 1
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--case-id', choices=SMOKE_IDS, default='v2-041')
    parser.add_argument('--live', action='store_true',
                        help='allow capped synthetic PUBLIC provider requests')
    parser.add_argument('--model', choices=tuple(PRICE_SOURCES), default='kimi-k3',
                        help=f'{BASELINE_MODEL} exercises the production baseline path')
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.case_id, args.live, args.model))
    except Exception as error:
        print('DELIVERY_EVALUATION_FAIL error_type=' + type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
