"""Host-owned model selection; prompts and credentials never grant activation.

The default policy preserves the configured Mistral model. Candidate approval
must be supplied by the composition root after independent quality/privacy
acceptance. This module does not persist or mint approval from a model response.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

from .response_planner import ResponsePlan, ResponseMode


_REVIEWED = frozenset({('mistral', 'mistral-large-2512'),
                      ('kimi', 'kimi-k2.6'), ('kimi', 'kimi-k3')})


class GenerationFailure(RuntimeError):
    def __init__(self, provider: str, model: str):
        super().__init__('provider_generation_failed')
        self.provider = provider
        self.model = model


@dataclass(frozen=True, slots=True)
class ModelApproval:
    provider: str
    model: str
    quality_accepted: bool
    privacy_accepted: bool
    expires_at: float
    pricing_accepted: bool = False
    max_output_tokens: int = 700

    def __post_init__(self):
        if ((self.provider, self.model) not in _REVIEWED
                or type(self.quality_accepted) is not bool
                or type(self.privacy_accepted) is not bool
                or type(self.pricing_accepted) is not bool
                or type(self.expires_at) not in (int, float)
                or not 0 < self.expires_at < 32503680000
                or type(self.max_output_tokens) is not int
                or not 1 <= self.max_output_tokens <= 4096):
            raise ValueError('invalid_model_approval')


@dataclass(frozen=True, slots=True)
class ModelSelection:
    provider: str
    model: str
    max_output_tokens: int
    reason: str


class GenerationPolicy:
    def __init__(self, baseline_model: str, baseline_max_tokens: int,
                 approvals: tuple[ModelApproval, ...] = ()):
        if not isinstance(baseline_model, str) or not baseline_model.strip():
            raise ValueError('invalid_baseline_model')
        if type(baseline_max_tokens) is not int or not 1 <= baseline_max_tokens <= 4096:
            raise ValueError('invalid_output_bound')
        if len(approvals) > 3 or len({(a.provider, a.model) for a in approvals}) != len(approvals):
            raise ValueError('invalid_approval_set')
        self.baseline = ModelSelection('mistral', baseline_model, baseline_max_tokens, 'baseline')
        self.approvals = tuple(approvals)

    def select(self, plan: ResponsePlan, *, has_evidence: bool,
               public_only: bool, available: frozenset[tuple[str, str]],
               now: float | None = None) -> ModelSelection:
        # A request for a premium model, founder claim or configured key is not
        # an escalation criterion. Missing evidence requires clarification.
        demanding = plan.complexity == 'complex' or plan.mode in {
            ResponseMode.COMPARISON, ResponseMode.OBJECTION}
        if not has_evidence or not public_only or not demanding:
            return self.baseline
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        for approved in self.approvals:
            if (approved.quality_accepted and approved.privacy_accepted and approved.pricing_accepted
                    and now < approved.expires_at
                    and (approved.provider, approved.model) in available):
                return ModelSelection(approved.provider, approved.model,
                                      approved.max_output_tokens, 'approved_escalation')
        return self.baseline
