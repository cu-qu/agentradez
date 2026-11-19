from decimal import Decimal

from rest_framework import serializers

from execution.models import (
    ExecutionAccount,
    ExecutionAgentToken,
    ExecutionOAuthClient,
    HarnessJournal,
    HarnessPosition,
    HarnessSignal,
)
from execution.services.mcp_auth import DEFAULT_SCOPES, SCOPE_READ, SCOPE_TRADE, generate_pat
from execution.services.platform_caps import clamp_account_caps


class ExecutionAccountSerializer(serializers.ModelSerializer):
    broker = serializers.CharField(source="broker_connection.broker", read_only=True)

    class Meta:
        model = ExecutionAccount
        fields = (
            "id",
            "slug",
            "label",
            "broker",
            "is_enabled",
            "dry_run",
            "max_open_positions",
            "max_dollar_exposure",
            "max_loss_per_position_usd",
            "breakeven_ratchet_enabled",
            "breakeven_trigger_gain_pct",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "broker", "created_at", "updated_at")


class ExecutionAccountCreateSerializer(serializers.Serializer):
    broker_connection_id = serializers.IntegerField()
    slug = serializers.SlugField(max_length=64)
    label = serializers.CharField(max_length=128)


class ExecutionAccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionAccount
        fields = (
            "label",
            "is_enabled",
            "dry_run",
            "max_open_positions",
            "max_dollar_exposure",
            "max_loss_per_position_usd",
            "breakeven_ratchet_enabled",
            "breakeven_trigger_gain_pct",
        )

    def validate(self, attrs):
        account = self.instance
        if account:
            for key, value in attrs.items():
                setattr(account, key, value)
            clamp_account_caps(account)
            attrs["max_open_positions"] = account.max_open_positions
            attrs["max_dollar_exposure"] = account.max_dollar_exposure
            attrs["max_loss_per_position_usd"] = account.max_loss_per_position_usd
        return attrs


class ExecutionAgentTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionAgentToken
        fields = (
            "id",
            "label",
            "scopes",
            "token_prefix",
            "created_at",
            "last_used_at",
            "revoked_at",
        )


class ExecutionAgentTokenCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=128)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=[SCOPE_READ, SCOPE_TRADE]),
        required=False,
    )

    def create(self, validated_data):
        user = self.context["request"].user
        scopes = validated_data.get("scopes") or DEFAULT_SCOPES
        raw, row = generate_pat(user, validated_data["label"], scopes)
        self.context["raw_token"] = raw
        return row


class KalshiConnectSerializer(serializers.Serializer):
    api_key_id = serializers.CharField(write_only=True)
    private_key_pem = serializers.CharField(write_only=True)
    kalshi_api_base_url = serializers.URLField(required=False, allow_blank=True)
    kalshi_use_demo = serializers.BooleanField(required=False, default=True)
    slug = serializers.SlugField(max_length=64, default="main")
    label = serializers.CharField(max_length=128, default="Kalshi")


class CoinbaseConnectSerializer(serializers.Serializer):
    api_key_name = serializers.CharField(write_only=True)
    private_key_pem = serializers.CharField(write_only=True)
    coinbase_api_base_url = serializers.URLField(required=False, allow_blank=True)
    slug = serializers.SlugField(max_length=64, default="main")
    label = serializers.CharField(max_length=128, default="Coinbase Spot")


class HarnessSignalSerializer(serializers.ModelSerializer):
    account_slug = serializers.CharField(source="execution_account.slug", read_only=True)

    class Meta:
        model = HarnessSignal
        fields = (
            "ref_id",
            "account_slug",
            "market",
            "symbol",
            "status",
            "quantity",
            "entry_rule",
            "stop_price",
            "targets",
            "last_mark_price",
            "created_at",
        )


class HarnessPositionSerializer(serializers.ModelSerializer):
    ref_id = serializers.CharField(source="signal.ref_id", read_only=True)

    class Meta:
        model = HarnessPosition
        fields = (
            "ref_id",
            "remaining_quantity",
            "average_entry_price",
            "current_price",
            "unrealized_pnl",
            "status",
            "opened_at",
        )


class HarnessJournalSerializer(serializers.ModelSerializer):
    ref_id = serializers.CharField(source="signal.ref_id", read_only=True)

    class Meta:
        model = HarnessJournal
        fields = ("action", "ref_id", "detail", "created_at")
