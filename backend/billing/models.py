from django.conf import settings
from django.db import models

from billing.constants import (
    INTERVAL_CHOICES,
    INTERVAL_NONE,
    SOURCE_CHOICES,
    SOURCE_FREE,
    STATUS_ACTIVE,
    SUBSCRIPTION_STATUS_CHOICES,
    VALUE_BOOLEAN,
    VALUE_TYPE_CHOICES,
)


def default_feature_value():
    return False


class Feature(models.Model):
    """Catalog of entitlements plans can turn on or set limits for."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    value_type = models.CharField(
        max_length=16, choices=VALUE_TYPE_CHOICES, default=VALUE_BOOLEAN
    )
    default_value = models.JSONField(default=default_feature_value)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return self.slug


class Plan(models.Model):
    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    interval = models.CharField(
        max_length=16, choices=INTERVAL_CHOICES, default=INTERVAL_NONE
    )
    amount_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=8, default="usd")
    stripe_product_id = models.CharField(max_length=128, blank=True)
    stripe_price_id = models.CharField(max_length=128, blank=True)
    features = models.JSONField(
        default=dict,
        help_text='Feature map, e.g. {"trading": true}. Unknown keys are kept for later.',
    )
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return self.slug

    @property
    def is_paid(self) -> bool:
        return self.amount_cents > 0 or bool(self.stripe_price_id)


class BillingCustomer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_customer",
    )
    stripe_customer_id = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.stripe_customer_id


class Subscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=24, choices=SUBSCRIPTION_STATUS_CHOICES, default=STATUS_ACTIVE
    )
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_FREE)
    stripe_subscription_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}:{self.plan.slug}:{self.status}"


class SubscriptionGrant(models.Model):
    """Complimentary access, including pending grants by email before signup."""

    email = models.EmailField(db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_grants",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="grants")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_subscriptions",
    )
    note = models.CharField(max_length=255, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Leave blank for access until the grant is revoked.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email}:{self.plan.slug}"


class StripeEvent(models.Model):
    stripe_id = models.CharField(max_length=128, unique=True)
    type = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.stripe_id
