from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from billing.constants import (
    DEFAULT_FEATURES,
    FEATURE_TRADING,
    INTERVAL_MONTH,
    INTERVAL_NONE,
    INTERVAL_YEAR,
    PLAN_FREE,
    PLAN_MONTHLY,
    PLAN_YEARLY,
    SOURCE_FREE,
    SOURCE_GRANT,
    SOURCE_STRIPE,
    STATUS_ACTIVE,
    STRIPE_LIVE_STATUSES,
    VALUE_BOOLEAN,
    VALUE_INTEGER,
)
from billing.models import Feature, Plan, Subscription, SubscriptionGrant

User = get_user_model()


@dataclass(frozen=True)
class Entitlement:
    plan: Plan | None
    plan_slug: str
    status: str
    source: str
    features: dict
    current_period_end: object | None
    cancel_at_period_end: bool
    is_paid: bool
    grant_id: int | None = None
    subscription_id: int | None = None


def _coerce_feature_value(feature: Feature | None, value):
    value_type = feature.value_type if feature else None
    if value_type == VALUE_INTEGER:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(feature.default_value) if feature else 0
    if isinstance(value, bool):
        return value
    if value in (0, "0", "false", "False", "no", None, ""):
        return False
    return bool(value)


def _feature_catalog() -> dict[str, Feature]:
    return {row.slug: row for row in Feature.objects.filter(is_active=True)}


def default_feature_map(catalog: dict[str, Feature] | None = None) -> dict:
    catalog = catalog if catalog is not None else _feature_catalog()
    features = dict(DEFAULT_FEATURES[PLAN_FREE])
    for slug, feature in catalog.items():
        features.setdefault(slug, feature.default_value)
    return features


def _merge_features(base: dict, overlay: dict, catalog: dict[str, Feature]) -> dict:
    merged = dict(base)
    for slug, value in (overlay or {}).items():
        feature = catalog.get(slug)
        coerced = _coerce_feature_value(feature, value)
        existing = merged.get(slug)
        if feature and feature.value_type == VALUE_INTEGER:
            merged[slug] = max(int(existing or 0), int(coerced or 0))
        else:
            merged[slug] = bool(existing) or bool(coerced)
    return merged


def _plan_rank(plan: Plan | None) -> int:
    if plan is None:
        return 0
    if plan.slug == PLAN_YEARLY or plan.interval == INTERVAL_YEAR:
        return 3
    if plan.slug == PLAN_MONTHLY or plan.interval == INTERVAL_MONTH:
        return 2
    if plan.slug == PLAN_FREE or plan.interval == INTERVAL_NONE:
        return 1
    return 1


def live_grants_for(user):
    now = timezone.now()
    return (
        SubscriptionGrant.objects.filter(is_active=True)
        .filter(Q(user=user) | Q(email__iexact=user.email))
        .filter(starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("plan")
        .order_by("-created_at")
    )


def live_stripe_subscriptions_for(user):
    now = timezone.now()
    qs = Subscription.objects.filter(
        user=user,
        source=SOURCE_STRIPE,
        status__in=STRIPE_LIVE_STATUSES,
    ).select_related("plan")
    return [
        row
        for row in qs
        if row.current_period_end is None or row.current_period_end > now
    ]


def entitlements_for(user) -> Entitlement:
    catalog = _feature_catalog()
    features = default_feature_map(catalog)
    free_plan = Plan.objects.filter(slug=PLAN_FREE, is_active=True).first()
    if free_plan:
        features = _merge_features(features, free_plan.features, catalog)

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        for slug, feature in catalog.items():
            if feature.value_type == VALUE_BOOLEAN:
                features[slug] = True
        features.setdefault(FEATURE_TRADING, True)
        return Entitlement(
            plan=free_plan,
            plan_slug=PLAN_FREE,
            status=STATUS_ACTIVE,
            source=SOURCE_FREE,
            features=features,
            current_period_end=None,
            cancel_at_period_end=False,
            is_paid=True,
        )

    chosen_plan = free_plan
    source = SOURCE_FREE
    status = STATUS_ACTIVE
    period_end = None
    cancel_at_period_end = False
    grant_id = None
    subscription_id = None

    for grant in live_grants_for(user):
        features = _merge_features(features, grant.plan.features, catalog)
        if _plan_rank(grant.plan) >= _plan_rank(chosen_plan):
            chosen_plan = grant.plan
            source = SOURCE_GRANT
            status = STATUS_ACTIVE
            period_end = grant.ends_at
            cancel_at_period_end = False
            grant_id = grant.id

    for sub in live_stripe_subscriptions_for(user):
        features = _merge_features(features, sub.plan.features, catalog)
        if _plan_rank(sub.plan) >= _plan_rank(chosen_plan):
            chosen_plan = sub.plan
            source = SOURCE_STRIPE
            status = sub.status
            period_end = sub.current_period_end
            cancel_at_period_end = sub.cancel_at_period_end
            subscription_id = sub.id
            grant_id = None

    is_paid = bool(features.get(FEATURE_TRADING)) and source != SOURCE_FREE

    return Entitlement(
        plan=chosen_plan,
        plan_slug=chosen_plan.slug if chosen_plan else PLAN_FREE,
        status=status,
        source=source,
        features=features,
        current_period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
        is_paid=is_paid,
        grant_id=grant_id,
        subscription_id=subscription_id,
    )


def user_has_feature(user, slug: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    value = entitlements_for(user).features.get(slug)
    if isinstance(value, bool):
        return value
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return bool(value)


def user_can_trade(user) -> bool:
    return user_has_feature(user, FEATURE_TRADING)


def entitlement_payload(user) -> dict:
    entitlement = entitlements_for(user)
    plan = entitlement.plan
    return {
        "plan": plan.slug if plan else PLAN_FREE,
        "plan_name": plan.name if plan else "Free",
        "status": entitlement.status,
        "source": entitlement.source,
        "features": entitlement.features,
        "is_paid": entitlement.is_paid,
        "current_period_end": entitlement.current_period_end,
        "cancel_at_period_end": entitlement.cancel_at_period_end,
        "interval": plan.interval if plan else INTERVAL_NONE,
        "amount_cents": plan.amount_cents if plan else 0,
        "currency": plan.currency if plan else "usd",
    }


def claim_grants_for_user(user) -> int:
    now = timezone.now()
    pending = SubscriptionGrant.objects.filter(
        email__iexact=user.email, user__isnull=True, is_active=True
    )
    return pending.update(user=user, claimed_at=now)


def grant_subscription(
    *,
    email: str,
    plan: Plan | None = None,
    plan_slug: str = PLAN_YEARLY,
    granted_by=None,
    days: int | None = None,
    note: str = "",
) -> SubscriptionGrant:
    from billing.services.catalog import ensure_default_plans

    ensure_default_plans()
    email = email.strip().lower()
    if plan is None:
        plan = Plan.objects.get(slug=plan_slug)
    now = timezone.now()
    user = User.objects.filter(email__iexact=email).first()
    ends = now + timedelta(days=days) if days else None
    return SubscriptionGrant.objects.create(
        email=email,
        user=user,
        plan=plan,
        granted_by=granted_by,
        note=note,
        starts_at=now,
        ends_at=ends,
        is_active=True,
        claimed_at=now if user else None,
    )


def revoke_grant(grant: SubscriptionGrant) -> SubscriptionGrant:
    grant.is_active = False
    grant.save(update_fields=["is_active", "updated_at"])
    return grant
