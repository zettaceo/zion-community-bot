"""Optional host-approved monetary caps, separate from token and evaluation ledgers.

Prices are explicit dated estimates with headroom, never inferred from secrets
or provider output. No default currency cap is imposed on an existing deployment.
"""
from datetime import date

from .evaluation_budget import PriceSnapshot
from .provider_budget import ProviderTokenBudget, ProviderBudgetError


class RuntimeCostBudget(ProviderTokenBudget):
    KEY = 'runtime_estimated_cost_micro_usd_v1'

    def __init__(self, db, *, daily_limit, provider_limits, model_limits,
                 request_limit, prices: dict[str, PriceSnapshot]):
        if any(type(n) is not int or n <= 0 for n in
               (daily_limit, request_limit, *provider_limits.values(), *model_limits.values())):
            raise ValueError('invalid_currency_cap')
        super().__init__(db, daily_limit=daily_limit, provider_limits=provider_limits,
                         model_limits=model_limits)
        if set(prices) != set(model_limits):
            raise ValueError('price_policy_incomplete')
        for model, price in prices.items():
            if (price.model != model or type(price.verified_on) is not date
                    or any(type(n) is not int or n <= 0 for n in
                        (price.input_micro_usd_per_million, price.output_micro_usd_per_million))):
                raise ValueError('invalid_price_policy')
        self.prices = dict(prices)
        self.request_limit = request_limit

    def _read(self):
        data = super()._read()
        for entry in data['pending'].values():
            rates = entry.get('price')
            if (not isinstance(rates, list) or len(rates) != 2
                    or any(type(v) is not int or v <= 0 for v in rates)):
                raise ProviderBudgetError('invalid_reserved_price')
        return data

    def reserve(self, provider, model, tokens, *, today=None):
        today = today or self.today()
        price = self.prices.get(model)
        if price is None or not 0 <= (today - price.verified_on).days <= 1:
            raise ProviderBudgetError('price_missing_or_stale')
        if type(tokens) is not int or tokens <= 0:
            raise ProviderBudgetError('invalid_usage_bound')
        # The supplied bound includes input + maximum output. Price every token
        # at the more expensive rate; no speculative cache discount.
        worst = max(price.input_micro_usd_per_million, price.output_micro_usd_per_million)
        amount = PriceSnapshot(model, worst, worst, price.verified_on).cost(tokens, 0)
        if amount > self.request_limit:
            raise ProviderBudgetError('request_cost_cap')
        with self.db.transaction():
            ref = super().reserve(provider, model, amount, today=today)
            # The just-created entry is still inside this transaction and has
            # not yet received its frozen price metadata.
            data = super()._read()
            data['pending'][ref]['price'] = [price.input_micro_usd_per_million,
                                           price.output_micro_usd_per_million]
            self._write(data)
        return ref

    def settle(self, reservation, input_tokens, output_tokens):
        # Retain the reservation's rates across midnight or price-policy updates.
        with self.db.transaction():
            data = self._read()
            entry = data['pending'].get(reservation)
            if not entry:
                raise ProviderBudgetError('unknown_reservation')
            rates = entry.get('price')
            if (not isinstance(rates, list) or len(rates) != 2
                    or any(type(v) is not int or v <= 0 for v in rates)):
                raise ProviderBudgetError('invalid_reserved_price')
            price = PriceSnapshot(entry['model'], *rates, date.fromisoformat(entry['day']))
            amount = price.cost(input_tokens, output_tokens)
        # No enclosing transaction: an overrun must persist the poisoned ledger
        # even though base settle raises after committing.
        super().settle(reservation, amount, 0)


class RequestAdmission:
    """Compatible admission interface; reserve tokens and money atomically."""
    def __init__(self, tokens: ProviderTokenBudget, costs: RuntimeCostBudget):
        if tokens.db is not costs.db:
            raise ValueError('admission_requires_same_database')
        self.tokens, self.costs = tokens, costs
        self.db = tokens.db

    def reserve(self, provider, model, tokens, *, today=None):
        with self.db.transaction():
            token_ref = self.tokens.reserve(provider, model, tokens, today=today)
            cost_ref = self.costs.reserve(provider, model, tokens, today=today)
        return token_ref + ':' + cost_ref

    @staticmethod
    def _refs(reservation):
        parts = reservation.split(':')
        if len(parts) != 2 or any(len(p) != 32 for p in parts):
            raise ProviderBudgetError('invalid_admission_handle')
        return parts

    def settle(self, reservation, input_tokens, output_tokens):
        token_ref, cost_ref = self._refs(reservation)
        self.tokens.settle(token_ref, input_tokens, output_tokens)
        self.costs.settle(cost_ref, input_tokens, output_tokens)

    def retain_uncertain(self, reservation):
        token_ref, cost_ref = self._refs(reservation)
        try:
            self.tokens.retain_uncertain(token_ref)
        finally:
            self.costs.retain_uncertain(cost_ref)

    def totals(self, *, today=None):
        self.costs.totals(today=today)  # Corrupt currency accounting fails closed.
        return self.tokens.totals(today=today)
