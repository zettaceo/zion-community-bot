"""Native Mistral generation evaluation with per-request monetary admission.

Uses the actual answer/tool path. No Telegram intake, private source, retry or
production budget is authorized here. This remains synthetic generation testing.
"""
from __future__ import annotations

import json

from .evaluation_budget import EvaluationBudget
from .mistral import MistralClient


class NativeEvaluationClient(MistralClient):
    def __init__(self, settings, secret_store, *, knowledge_tools, budget: EvaluationBudget):
        if settings.mistral_rate_limit_retries != 0:
            raise ValueError('evaluation_retries_forbidden')
        super().__init__(settings, secret_store, knowledge_tools=knowledge_tools)
        self.evaluation_budget = budget
        self.estimated_micro_usd = 0
        self.request_count = 0
        self.uncertain_request_count = 0

    async def _chat(self, messages, **kwargs):
        # Tool envelopes/schemas consume input tokens too. This extra synthetic
        # message is used ONLY for conservative cost estimation, never sent.
        estimate = [*messages, {'role': 'user', 'content': json.dumps(kwargs, ensure_ascii=False)}]
        max_tokens = kwargs.get('max_tokens', self.settings.mistral_max_tokens)
        reservation = self.evaluation_budget.reserve(self.settings.mistral_model, estimate, max_tokens)
        self.request_count += 1
        self.uncertain_request_count += 1
        # A failed/cancelled request keeps its durable reservation; there is no refund.
        response = await super()._chat(messages, **kwargs)
        self.estimated_micro_usd += self.evaluation_budget.settle(reservation, response)
        self.uncertain_request_count -= 1
        return response
