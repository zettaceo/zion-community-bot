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
from zion.evaluation_delivery import (DeliveryEvaluationService,
                                      PublicEvaluationKnowledge, SMOKE_IDS,
                                      evaluate_delivery_case)
from zion.provider_secrets import ProviderSecretStore
from zion.providers import KimiCompletionProvider


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


async def run(case_id: str, live: bool) -> int:
    if case_id not in SMOKE_IDS or (case_id != 'v2-041' and not live):
        raise ValueError('case_requires_explicit_live_opt_in')
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
    stem = stamp + '-delivery-' + case_id + '-' + head[:8]
    manifest_path = directory / (stem + '-manifest.json')
    result_path = directory / (stem + '-result.json')

    price = None
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
                'price_source': 'https://platform.kimi.ai/' if price else None,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--case-id', choices=SMOKE_IDS, default='v2-041')
    parser.add_argument('--live', action='store_true',
                        help='allow at most one capped K3 synthetic PUBLIC request')
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.case_id, args.live))
    except Exception as error:
        print('DELIVERY_EVALUATION_FAIL error_type=' + type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
