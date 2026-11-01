"""Durable runtime token admission; no prompts, credentials or currency prices.

Reserve each HTTP attempt before I/O. Unknown outcomes keep their full charge.
Provider/model limits are subordinate to a shared daily cap, so switching models
cannot reset allowance. This is conservative token accounting, not an invoice.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from .db import ZionDB


class ProviderBudgetError(RuntimeError):
    pass


class ProviderTokenBudget:
    KEY = 'provider_token_budget_v1'
    MAX_PENDING = 2048
    MAX_MODELS = 64

    def __init__(self, db: ZionDB, *, daily_limit: int,
                 provider_limits: dict[str, int], model_limits: dict[str, int]):
        for limit in (daily_limit, *provider_limits.values(), *model_limits.values()):
            if type(limit) is not int or limit < 0:
                raise ValueError('invalid_token_limit')
        if not provider_limits or not model_limits:
            raise ValueError('missing_budget_policy')
        self.db = db
        self.daily_limit = daily_limit
        self.provider_limits = dict(provider_limits)
        self.model_limits = dict(model_limits)

    @staticmethod
    def today() -> date:
        return datetime.now(timezone.utc).date()

    @staticmethod
    def _count(value):
        if type(value) is not int or value < 0:
            raise ValueError('invalid_count')
        return value

    def _read(self):
        raw = self.db.get_setting(self.KEY)
        if raw is None:
            return {'version': 1, 'poisoned': False, 'days': {}, 'pending': {}}
        try:
            data = json.loads(raw)
            if type(data['version']) is not int or data['version'] != 1 or data['poisoned'] is not False:
                raise ValueError()
            if not isinstance(data['days'], dict) or not isinstance(data['pending'], dict):
                raise ValueError()
            if len(data['days']) > 3 or len(data['pending']) > self.MAX_PENDING:
                raise ValueError()
            for day, totals in data['days'].items():
                date.fromisoformat(day)
                self._count(totals['total'])
                for name in ('providers', 'models'):
                    if not isinstance(totals[name], dict) or len(totals[name]) > self.MAX_MODELS:
                        raise ValueError()
                    for count in totals[name].values():
                        self._count(count)
                if (sum(totals['providers'].values()) != totals['total']
                    or sum(totals['models'].values()) != totals['total']):
                    raise ValueError()
            reserved = {}
            for entry in data['pending'].values():
                self._count(entry['tokens'])
                totals = data['days'][entry['day']]
                if entry['provider'] not in totals['providers'] or entry['model'] not in totals['models']:
                    raise ValueError()
                for kind, label in (('total', ''), ('providers', entry['provider']), ('models', entry['model'])):
                    key = (entry['day'], kind, label)
                    reserved[key] = reserved.get(key, 0) + entry['tokens']
                    if reserved[key] > (totals['total'] if kind == 'total' else totals[kind][label]):
                        raise ValueError()
            return data
        except (ValueError, KeyError, TypeError):
            raise ProviderBudgetError('accounting_unavailable') from None

    def _write(self, data):
        self.db.set_setting(self.KEY, json.dumps(data, separators=(',', ':')))

    def reserve(self, provider: str, model: str, tokens: int, *, today: date | None = None) -> str:
        if (provider not in self.provider_limits or model not in self.model_limits
            or not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,128}', provider)
            or not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,128}', model)
            or type(tokens) is not int or tokens <= 0):
            raise ProviderBudgetError('unapproved_request')
        today = today or self.today()
        day = today.isoformat()
        with self.db.transaction():
            data = self._read()
            if data['days'] and day < max(data['days']):
                raise ProviderBudgetError('clock_regression')
            cutoff = (today - timedelta(days=2)).isoformat()
            data['days'] = {k: v for k, v in data['days'].items() if k >= cutoff}
            data['pending'] = {k: v for k, v in data['pending'].items() if v['day'] >= cutoff}
            if len(data['pending']) >= self.MAX_PENDING:
                raise ProviderBudgetError('pending_bound')
            totals = data['days'].setdefault(day, {'total': 0, 'providers': {}, 'models': {}})
            for kind, label, cap in (('total', '', self.daily_limit),
                ('providers', provider, self.provider_limits[provider]),
                ('models', model, self.model_limits[model])):
                used = totals['total'] if kind == 'total' else totals[kind].get(label, 0)
                if cap and used + tokens > cap:
                    raise ProviderBudgetError('daily_token_cap')
                if kind != 'total' and label not in totals[kind] and len(totals[kind]) >= self.MAX_MODELS:
                    raise ProviderBudgetError('model_bound')
            self._adjust(totals, provider, model, tokens)
            reservation = uuid.uuid4().hex
            data['pending'][reservation] = dict(day=day, provider=provider, model=model, tokens=tokens)
            self._write(data)
        return reservation

    @staticmethod
    def _adjust(totals, provider, model, delta):
        totals['total'] += delta
        totals['providers'][provider] = totals['providers'].get(provider, 0) + delta
        totals['models'][model] = totals['models'].get(model, 0) + delta

    def settle(self, reservation: str, input_tokens: int, output_tokens: int) -> None:
        try:
            actual = self._count(input_tokens) + self._count(output_tokens)
        except ValueError:
            raise ProviderBudgetError('invalid_usage') from None
        overrun = False
        with self.db.transaction():
            data = self._read()
            entry = data['pending'].pop(reservation, None)
            if entry is None:
                raise ProviderBudgetError('unknown_reservation')
            self._adjust(data['days'][entry['day']], entry['provider'], entry['model'], actual-entry['tokens'])
            if actual > entry['tokens']:
                data['poisoned'] = True
                overrun = True
            self._write(data)
        if overrun:
            raise ProviderBudgetError('usage_exceeded_reservation')

    def retain_uncertain(self, reservation: str) -> None:
        """Drop the pending handle, never the charge. Also safe after settlement."""
        with self.db.transaction():
            data = self._read()
            data['pending'].pop(reservation, None)
            self._write(data)

    def totals(self, *, today: date | None = None) -> dict:
        with self.db.transaction():
            data = self._read()
            return data['days'].get((today or self.today()).isoformat(),
                {'total': 0, 'providers': {}, 'models': {}})
