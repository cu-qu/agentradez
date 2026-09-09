from rest_framework import serializers

from billing.constants import PLAN_FREE, PLAN_MONTHLY, PLAN_YEARLY
from billing.models import Feature, Plan, SubscriptionGrant


class FeatureSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Feature
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "value_type",
            "default_value",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PlanSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "interval",
            "amount_cents",
            "currency",
            "features",
            "is_public",
            "is_active",
            "sort_order",
        )
        read_only_fields = fields


class AdminPlanSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "interval",
            "amount_cents",
            "currency",
            "stripe_product_id",
            "stripe_price_id",
            "features",
            "is_public",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=[PLAN_MONTHLY, PLAN_YEARLY])


class GrantCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    plan = serializers.SlugField()
    days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_plan(self, value):
        from billing.services.catalog import ensure_default_plans

        ensure_default_plans()
        slug = value.strip().lower()
        if slug == PLAN_FREE:
            raise serializers.ValidationError("Grant a monthly or yearly plan, not free.")
        if not Plan.objects.filter(slug=slug, is_active=True).exists():
            raise serializers.ValidationError("Unknown plan.")
        return slug


class GrantSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    plan = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    granted_by_username = serializers.CharField(
        source="granted_by.username", read_only=True, allow_null=True
    )
    user_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = SubscriptionGrant
        fields = (
            "id",
            "email",
            "user_id",
            "plan",
            "granted_by_username",
            "note",
            "starts_at",
            "ends_at",
            "is_active",
            "claimed_at",
            "created_at",
        )
        read_only_fields = fields
