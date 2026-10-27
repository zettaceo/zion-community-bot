"""Durable conservative cost admission for isolated, synthetic evaluation only.

Uses existing SQLite settings transactions, never the production database.
Reserve BEFORE network I/O. Unknown outcomes keep the entire reservation across
restart. No retry or provider switch is implicit. Integers are micro-US dollars.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .db import ZionDB
from .providers import Completion


class EvaluationBudgetError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    model: str
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    verified_on: date

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        if any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens)):
            raise EvaluationBudgetError('invalid_usage')
        # 20% budget headroom, no cache-hit discount assumed. This is a budget
        # estimate, not an invoice, tax calculation or authoritative balance.
        raw = (input_tokens * self.input_micro_usd_per_million
               + output_tokens * self.output_micro_usd_per_million)
        return (raw * 12 + 9999999) // 10000000


# Official platform.kimi.ai/docs/pricing/chat model table; K3
# reverified 2026-10-27. K3 input includes default 5min cache write
# conservatively (3 + 3 USD/M).
PRICES = {
    # Official docs.mistral.ai/models/ministral-3-8b-25-12, reverified 2026-10-27.
    'ministral-8b-2512': PriceSnapshot('ministral-8b-2512', 150000, 150000, date(2026, 10, 27)),
    # Official docs.mistral.ai/models/mistral-large-3-25-12, verified 2026-10-19.
    'mistral-large-2512': PriceSnapshot('mistral-large-2512', 500000, 1500000, date(2026, 10, 19)),
    'kimi-k2.6': PriceSnapshot('kimi-k2.6', 950000, 4000000, date(2026, 10, 25)),
    'kimi-k3': PriceSnapshot('kimi-k3', 6000000, 15000000, date(2026, 10, 27)),
}


class EvaluationBudget:
    STATE_KEY = 'cognitive_eval_budget_v1'
    TOTAL_CAP = 8000000  # USD 8 of the approximately USD 10 evaluation credit.
    DAILY_CAP = 2000000
    REQUEST_CAP = 250000

    def __init__(self, db: ZionDB):
        self.db = db

    @staticmethod
    def price(model: str, today: date) -> PriceSnapshot:
        price = PRICES.get(model)
        if price is None or not 0 <= (today - price.verified_on).days <= 1:
            raise EvaluationBudgetError('price_missing_or_stale')
        return price

    def _state(self) -> dict:
        raw = self.db.get_setting(self.STATE_KEY)
        if raw is None:
            return {'version': 1, 'poisoned': False, 'entries': {}}
        try:
            data = json.loads(raw)
            if data['version'] != 1 or data['poisoned'] or not isinstance(data['entries'], dict):
                raise ValueError()
            for entry in data['entries'].values():
                if (type(entry['charge']) is not int or entry['charge'] < 0
                        or entry['status'] not in {'reserved', 'settled'}
                        or entry['model'] not in PRICES):
                    raise ValueError()
                date.fromisoformat(entry['day'])
            return data
        except (ValueError, KeyError, TypeError):
            raise EvaluationBudgetError('accounting_unavailable') from None

    def reserve(self, model: str, messages: list[dict[str, str]], max_tokens: int,
                *, today: date | None = None) -> str:
        today = today or datetime.now(timezone.utc).date()
        price = self.price(model, today)
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise EvaluationBudgetError('invalid_completion_limit')
        # UTF-8 bytes, not chars/4: deliberately conservative tokenizer bound.
        input_upper = len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 4096
        estimated = price.cost(input_upper, max_tokens)
        if estimated > self.REQUEST_CAP:
            raise EvaluationBudgetError('request_cap')
        with self.db.transaction():
            data = self._state()
            entries = data['entries']
            if len(entries) >= 3000:
                raise EvaluationBudgetError('ledger_bound')
            if sum(e['charge'] for e in entries.values()) + estimated > self.TOTAL_CAP:
                raise EvaluationBudgetError('total_cap')
            daily = sum(e['charge'] for e in entries.values() if e['day'] == today.isoformat())
            if daily + estimated > self.DAILY_CAP:
                raise EvaluationBudgetError('daily_cap')
            reservation = uuid.uuid4().hex
            entries[reservation] = {'model': model, 'day': today.isoformat(),
                                    'charge': estimated, 'status': 'reserved'}
            self.db.set_setting(self.STATE_KEY, json.dumps(data, separators=(',', ':')))
        return reservation

    def settle(self, reservation: str, completion: Completion) -> int:
        overrun = False
        with self.db.transaction():
            data = self._state()
            entry = data['entries'].get(reservation)
            if not entry or entry['status'] != 'reserved' or entry['model'] != completion.model:
                raise EvaluationBudgetError('invalid_reservation')
            price = PRICES[entry['model']]
            charged = price.cost(completion.input_tokens, completion.output_tokens)
            if charged > entry['charge']:
                data['poisoned'] = True
                overrun = True
            entry.update(charge=charged, status='settled')
            self.db.set_setting(self.STATE_KEY, json.dumps(data, separators=(',', ':')))
        if overrun:
            raise EvaluationBudgetError('usage_exceeded_reservation')
        return charged

    def total_micro_usd(self) -> int:
        with self.db.transaction():
            return sum(e['charge'] for e in self._state()['entries'].values())
