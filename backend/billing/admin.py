from django.contrib import admin

from billing.models import (
    BillingCustomer,
    Feature,
    Plan,
    StripeEvent,
    Subscription,
    SubscriptionGrant,
)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name", "value_type", "default_value", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    search_fields = ("slug", "name")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "slug",
        "name",
        "interval",
        "amount_cents",
        "stripe_price_id",
        "is_public",
        "is_active",
    )
    list_filter = ("interval", "is_public", "is_active")
    search_fields = ("slug", "name", "stripe_price_id")


@admin.register(BillingCustomer)
class BillingCustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "stripe_customer_id", "created_at")
    search_fields = ("user__email", "user__username", "stripe_customer_id")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan",
        "status",
        "source",
        "current_period_end",
        "cancel_at_period_end",
    )
    list_filter = ("status", "source", "plan")
    search_fields = ("user__email", "user__username", "stripe_subscription_id")
    raw_id_fields = ("user",)


@admin.register(SubscriptionGrant)
class SubscriptionGrantAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "user",
        "plan",
        "is_active",
        "starts_at",
        "ends_at",
        "granted_by",
        "claimed_at",
    )
    list_filter = ("is_active", "plan")
    search_fields = ("email", "user__email", "user__username", "note")
    raw_id_fields = ("user", "granted_by")
    actions = ["revoke_selected"]

    @admin.action(description="Revoke selected grants")
    def revoke_selected(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("id", "stripe_id", "type", "processed_at")
    search_fields = ("stripe_id", "type")
    readonly_fields = ("stripe_id", "type", "processed_at")
