from __future__ import annotations

from django.conf import settings

from billing.constants import (
    DEFAULT_FEATURES,
    FEATURE_TRADING,
    INTERVAL_MONTH,
    INTERVAL_NONE,
    INTERVAL_YEAR,
    PLAN_FREE,
    PLAN_MONTHLY,
    PLAN_YEARLY,
    VALUE_BOOLEAN,
)
from billing.models import Feature, Plan


def ensure_default_features() -> None:
    Feature.objects.update_or_create(
        slug=FEATURE_TRADING,
        defaults={
            "name": "Trading",
            "description": "Connect a broker, pick a strategy, and run automated trades.",
            "value_type": VALUE_BOOLEAN,
            "default_value": False,
            "is_active": True,
            "sort_order": 1,
        },
    )


def ensure_default_plans() -> dict[str, Plan]:
    ensure_default_features()
    specs = [
        {
            "slug": PLAN_FREE,
            "name": "Free",
            "description": "Create an account and browse plans. Paid features stay locked.",
            "interval": INTERVAL_NONE,
            "amount_cents": 0,
            "stripe_price_id": "",
            "sort_order": 1,
        },
        {
            "slug": PLAN_MONTHLY,
            "name": "Monthly",
            "description": "Full trading access, billed every month.",
            "interval": INTERVAL_MONTH,
            "amount_cents": 2900,
            "stripe_price_id": getattr(settings, "STRIPE_PRICE_MONTHLY", "") or "",
            "sort_order": 2,
        },
        {
            "slug": PLAN_YEARLY,
            "name": "Yearly",
            "description": "Full trading access, billed once a year.",
            "interval": INTERVAL_YEAR,
            "amount_cents": 29000,
            "stripe_price_id": getattr(settings, "STRIPE_PRICE_YEARLY", "") or "",
            "sort_order": 3,
        },
    ]
    plans = {}
    for spec in specs:
        slug = spec["slug"]
        defaults = {
            "name": spec["name"],
            "description": spec["description"],
            "interval": spec["interval"],
            "amount_cents": spec["amount_cents"],
            "currency": "usd",
            "features": dict(DEFAULT_FEATURES[slug]),
            "is_public": True,
            "is_active": True,
            "sort_order": spec["sort_order"],
        }
        plan, created = Plan.objects.get_or_create(slug=slug, defaults=defaults)
        if not created:
            updates = []
            price_id = spec["stripe_price_id"]
            if price_id and plan.stripe_price_id != price_id:
                plan.stripe_price_id = price_id
                updates.append("stripe_price_id")
            if not plan.features:
                plan.features = dict(DEFAULT_FEATURES[slug])
                updates.append("features")
            if updates:
                updates.append("updated_at")
                plan.save(update_fields=updates)
        elif spec["stripe_price_id"]:
            plan.stripe_price_id = spec["stripe_price_id"]
            plan.save(update_fields=["stripe_price_id", "updated_at"])
        plans[slug] = plan
    return plans
