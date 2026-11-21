"""Composition of the owner-approved Kimi K3 escalation; off by default.

ZION_KIMI_ESCALATION=true with ZION_KIMI_APPROVAL_UNTIL=YYYY-MM-DD records the
owner's acceptance of quality, data handling and pricing until that date
(end of day UTC). Without both, or after expiry, AIService is composed with
the Mistral baseline only, exactly as before. GenerationPolicy then sends
only demanding turns answered from PUBLIC evidence to K3, without history.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
import logging

from .evaluation_budget import PRICES
from .generation_policy import GenerationPolicy, ModelApproval
from .providers import KimiCompletionProvider
from .runtime_cost import RuntimeCostBudget
from .secret_store import SecretStore

logger = logging.getLogger("zion.escalation")

KIMI_MODEL = 'kimi-k3'
# Prices are reverified on the official pages; a running service accepts a
# snapshot this old and then fails closed until it is refreshed.
RUNTIME_PRICE_AGE_DAYS = 45
# Bounds one *reservation*, which is deliberately pessimistic (twice the
# serialized bytes, every token at the output rate): a K3 turn that costs
# about USD 0.03-0.05 reserves about USD 0.45. Settled cost is what the daily
# cap then accumulates.
REQUEST_CAP_MICRO_USD = 750_000


def approval_expiry(raw: str) -> float | None:
    try:
        day = date.fromisoformat((raw or '').strip())
    except ValueError:
        return None
    end = datetime.combine(day + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
    return end.timestamp()


def escalation_status(settings, kimi_store: SecretStore, *, now: float | None = None) -> str:
    if not settings.kimi_escalation_enabled:
        return 'off'
    expiry = approval_expiry(settings.kimi_approval_until)
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if expiry is None:
        return 'blocked:approval_date_missing'
    if now >= expiry:
        return 'blocked:approval_expired'
    if settings.mistral_model not in PRICES or KIMI_MODEL not in PRICES:
        return 'blocked:price_unknown'
    if kimi_store.status() != SecretStore.PRIVATE:
        return 'blocked:credential_unavailable'
    return 'active'


PRICE_WARN_DAYS = 14


def expiry_issues(settings, *, today: date | None = None) -> list[str]:
    """Deadlines that silently stop the AI while Kimi escalation is on.

    The runtime budget refuses prices verified more than RUNTIME_PRICE_AGE_DAYS
    ago (every AI call then fails closed), and escalation turns off at the
    owner's approval date. Nothing warned before either happened (2026-11-19:
    found with 27 days left), so health raises them 14 days ahead.
    """
    if not settings.kimi_escalation_enabled:
        return []
    today = today or datetime.now(timezone.utc).date()
    issues: list[str] = []
    for model in (settings.mistral_model, KIMI_MODEL):
        price = PRICES.get(model)
        if price is None:
            issues.append(f"ai_price_unknown:{model}")
            continue
        left = (price.verified_on + timedelta(days=RUNTIME_PRICE_AGE_DAYS) - today).days
        if left < 0:
            issues.append(f"ai_price_expired:{model}")
        elif left <= PRICE_WARN_DAYS:
            issues.append(f"ai_price_expires_soon:{model}")
    expiry = approval_expiry(settings.kimi_approval_until)
    if expiry is not None:
        left = (datetime.fromtimestamp(expiry, timezone.utc).date() - today).days
        if left <= 0:
            issues.append("kimi_approval_expired")
        elif left <= PRICE_WARN_DAYS:
            issues.append("kimi_approval_expires_soon")
    return issues


def build_ai_composition(settings, db, kimi_store: SecretStore) -> dict:
    """Keyword arguments for AIService; {} keeps the baseline-only service."""
    status = escalation_status(settings, kimi_store)
    if status != 'active':
        if status != 'off':
            logger.warning("Escalada Kimi bloqueada | motivo=%s", status)
        return {}
    cap = max(1, int(round(settings.ai_daily_usd_cap * 1_000_000)))
    models = {settings.mistral_model: cap, KIMI_MODEL: cap}
    prices = {m: PRICES[m] for m in models}
    costs = RuntimeCostBudget(
        db, daily_limit=cap, provider_limits={'mistral': cap, 'kimi': cap},
        model_limits=models, request_limit=REQUEST_CAP_MICRO_USD, prices=prices,
        max_price_age_days=RUNTIME_PRICE_AGE_DAYS)
    approval = ModelApproval('kimi', KIMI_MODEL, quality_accepted=True,
                             privacy_accepted=True, pricing_accepted=True,
                             expires_at=approval_expiry(settings.kimi_approval_until))
    logger.info("Escalada Kimi ativa | modelo=%s | teto_diario_usd=%.2f | ate=%s",
                KIMI_MODEL, settings.ai_daily_usd_cap, settings.kimi_approval_until)
    return {
        'generation_policy': GenerationPolicy(settings.mistral_model,
                                              min(settings.mistral_max_tokens, 4096),
                                              approvals=(approval,)),
        'completion_providers': {('kimi', KIMI_MODEL): KimiCompletionProvider(
            kimi_store, model=KIMI_MODEL)},
        'runtime_cost_budget': costs,
    }
