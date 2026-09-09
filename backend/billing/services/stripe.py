from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from billing.constants import PLAN_FREE, SOURCE_STRIPE, STATUS_CANCELED, STRIPE_LIVE_STATUSES
from billing.models import BillingCustomer, Plan, StripeEvent, Subscription

User = get_user_model()


class StripeNotConfigured(APIException):
    status_code = 503
    default_detail = "Stripe billing is not configured."
    default_code = "stripe_not_configured"


def stripe_configured() -> bool:
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def _stripe():
    if not stripe_configured():
        raise StripeNotConfigured()
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, dt_timezone.utc)
        return value
    return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)


def plan_for_price(price_id: str) -> Plan | None:
    if not price_id:
        return None
    return Plan.objects.filter(stripe_price_id=price_id, is_active=True).first()


def get_or_create_customer(user) -> BillingCustomer:
    existing = BillingCustomer.objects.filter(user=user).first()
    if existing:
        return existing
    stripe = _stripe()
    customer = stripe.Customer.create(
        email=user.email,
        name=user.get_username(),
        metadata={"user_id": str(user.id)},
    )
    return BillingCustomer.objects.create(user=user, stripe_customer_id=customer.id)


def create_checkout_session(user, plan: Plan) -> dict:
    if plan.slug == PLAN_FREE:
        raise ValidationError({"plan": "The free plan does not require checkout."})
    if not stripe_configured():
        raise StripeNotConfigured()
    if not plan.stripe_price_id:
        raise ValidationError({"plan": "This plan is not linked to a Stripe price yet."})

    live = Subscription.objects.filter(
        user=user, source=SOURCE_STRIPE, status__in=STRIPE_LIVE_STATUSES
    ).exclude(stripe_subscription_id__isnull=True)
    if live.exists():
        raise ValidationError(
            {
                "detail": "You already have a Stripe subscription. Use the billing portal to change plans."
            }
        )

    customer = get_or_create_customer(user)
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer.stripe_customer_id,
        client_reference_id=str(user.id),
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        allow_promotion_codes=True,
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        metadata={"user_id": str(user.id), "plan": plan.slug},
        subscription_data={"metadata": {"user_id": str(user.id), "plan": plan.slug}},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def create_portal_session(user) -> dict:
    customer = BillingCustomer.objects.filter(user=user).first()
    if customer is None:
        raise ValidationError(
            {"detail": "No Stripe customer yet. Start a checkout session first."}
        )
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=settings.STRIPE_PORTAL_RETURN_URL,
    )
    return {"portal_url": session.url}


def construct_event(payload: bytes, signature: str):
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""
    if not secret or not stripe_configured():
        raise StripeNotConfigured()
    stripe = _stripe()
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.SignatureVerificationError as exc:
        raise ValidationError({"detail": "Invalid Stripe signature."}) from exc
    except ValueError as exc:
        raise ValidationError({"detail": "Invalid Stripe payload."}) from exc


def _user_from_stripe(subscription_obj, customer_id: str | None = None):
    metadata = dict(getattr(subscription_obj, "metadata", None) or {})
    if isinstance(subscription_obj, dict):
        metadata = dict(subscription_obj.get("metadata") or {})
        customer_id = customer_id or subscription_obj.get("customer")
    user_id = metadata.get("user_id")
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user
    if customer_id is None:
        customer_id = getattr(subscription_obj, "customer", None)
    if customer_id:
        row = (
            BillingCustomer.objects.filter(stripe_customer_id=customer_id)
            .select_related("user")
            .first()
        )
        if row:
            return row.user
    return None


def _price_id_from_subscription(subscription_obj) -> str:
    if isinstance(subscription_obj, dict):
        items = subscription_obj.get("items") or {}
        data = items.get("data") or []
        if not data:
            return ""
        price = data[0].get("price") or {}
        return price.get("id") or ""
    items = getattr(subscription_obj, "items", None)
    data = getattr(items, "data", None) if items is not None else None
    if not data:
        return ""
    price = getattr(data[0], "price", None)
    return getattr(price, "id", "") or ""


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def upsert_subscription_from_stripe(subscription_obj) -> Subscription | None:
    user = _user_from_stripe(subscription_obj)
    if user is None:
        return None
    price_id = _price_id_from_subscription(subscription_obj)
    plan = plan_for_price(price_id)
    if plan is None:
        metadata = _get(subscription_obj, "metadata") or {}
        slug = metadata.get("plan") if isinstance(metadata, dict) else getattr(metadata, "plan", None)
        if slug:
            plan = Plan.objects.filter(slug=slug).first()
    if plan is None:
        return None
    status = _get(subscription_obj, "status") or STATUS_CANCELED
    stripe_id = _get(subscription_obj, "id")
    defaults = {
        "user": user,
        "plan": plan,
        "status": status,
        "source": SOURCE_STRIPE,
        "current_period_start": _ts(_get(subscription_obj, "current_period_start")),
        "current_period_end": _ts(_get(subscription_obj, "current_period_end")),
        "cancel_at_period_end": bool(_get(subscription_obj, "cancel_at_period_end") or False),
    }
    row, _created = Subscription.objects.update_or_create(
        stripe_subscription_id=stripe_id,
        defaults=defaults,
    )
    return row


def process_stripe_event(event) -> bool:
    event_id = _get(event, "id")
    event_type = _get(event, "type")
    data = _get(event, "data")
    data_object = _get(data, "object") if data is not None else None
    if data_object is None and isinstance(event, dict):
        data_object = (event.get("data") or {}).get("object")
    _, created = StripeEvent.objects.get_or_create(
        stripe_id=event_id, defaults={"type": event_type}
    )
    if not created:
        return False

    if event_type == "checkout.session.completed":
        subscription_id = _get(data_object, "subscription")
        if subscription_id:
            stripe = _stripe()
            sub = stripe.Subscription.retrieve(subscription_id)
            upsert_subscription_from_stripe(sub)
        return True

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        upsert_subscription_from_stripe(data_object)
        return True

    if event_type == "invoice.payment_failed":
        subscription_id = _get(data_object, "subscription")
        if subscription_id:
            Subscription.objects.filter(stripe_subscription_id=subscription_id).update(
                status="past_due"
            )
        return True

    return True
