from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers

from trading.constants import (
    BROKER_CHOICES,
    COPY_TRADE_SIGNAL_SOURCE_CATALOG,
    COPY_TRADE_SIGNAL_SOURCE_CHOICES,
    EVENT_TYPE_VALUES,
    SIGNAL_SOURCE_X,
    STRATEGY_TYPE_CHOICES,
    STRATEGY_TYPE_COPY_TRADE,
    STRATEGY_TYPE_RESEARCH_BREAKTHROUGH,
    STRATEGY_VISIBILITY_CHOICES,
    STRATEGY_VISIBILITY_PUBLIC,
)
from trading.models import (
    BrokerConnection,
    BrokerOrder,
    Decision,
    IngestedPost,
    InvestmentTier,
    Notification,
    Position,
    ResearchEvent,
    ResearchWatchConfig,
    Signal,
    SignalDecision,
    Strategy,
    Trade,
    TradeEvent,
    UserStrategyAssignment,
    UserGroup,
    WatchedCompany,
    XAccountSource,
)
from trading.services.credentials import encrypt_credentials
from trading.services.jobs import set_assignment
from trading.services.robinhood import RobinhoodError, list_account_summaries_for, parse_oauth_callback
from trading.services.strategy_access import strategies_visible_to, user_can_access_strategy

User = get_user_model()


class InvestmentTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestmentTier
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "is_default",
            "is_active",
            "sort_order",
            "max_entry_slippage_pct",
            "max_entry_slippage_pct_min",
            "max_risk_per_trade_pct",
            "max_risk_per_trade_pct_min",
            "max_open_positions",
            "take_profit_rules",
            "hard_stop_pct",
            "force_exit_time_et",
            "max_hold_trading_days",
            "daily_loss_limit_pct",
            "daily_loss_limit_pct_min",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "updated_at")


class AdminInvestmentTierSerializer(InvestmentTierSerializer):
    class Meta(InvestmentTierSerializer.Meta):
        read_only_fields = ("id", "updated_at")


class StrategySerializer(serializers.ModelSerializer):
    source_handle = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "strategy_type",
            "signal_source",
            "visibility",
            "source_handle",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "source_handle", "created_at", "updated_at")

    def get_source_handle(self, obj) -> str:
        if obj.strategy_type == STRATEGY_TYPE_RESEARCH_BREAKTHROUGH:
            companies = None
            cache = getattr(obj, "_prefetched_objects_cache", None)
            if cache and "watched_companies" in cache:
                companies = [row.ticker for row in obj.watched_companies.all() if row.is_active]
            else:
                companies = list(
                    obj.watched_companies.filter(is_active=True).values_list("ticker", flat=True)
                )
            return ", ".join(companies[:4])
        source = obj.primary_x_source()
        return source.handle if source and source.is_active else ""


class StrategyXSourceSerializer(serializers.ModelSerializer):
    """X watcher nested on a strategy so the admin form can configure both together."""

    class Meta:
        model = XAccountSource
        fields = (
            "id",
            "handle",
            "display_name",
            "x_user_id",
            "is_active",
            "lookback_hours",
            "poll_interval_seconds",
            "last_tweet_id",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "x_user_id",
            "last_tweet_id",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"handle": {"validators": []}}

    def get_attribute(self, instance):
        return instance.primary_x_source()


class ResearchWatchConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchWatchConfig
        fields = (
            "id",
            "poll_interval_seconds",
            "lookback_hours",
            "min_catalyst_score",
            "otm_pct",
            "min_dte",
            "max_dte",
            "signal_cooldown_hours",
            "sectors",
            "enabled_event_types",
            "news_keywords",
            "require_confirmation",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )

    def get_attribute(self, instance):
        try:
            return instance.research_config
        except ResearchWatchConfig.DoesNotExist:
            return None

    def validate_enabled_event_types(self, value):
        types = [str(item).strip() for item in (value or []) if str(item).strip()]
        unknown = [item for item in types if item not in EVENT_TYPE_VALUES]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown event types: {', '.join(unknown)}."
            )
        return types

    def validate_sectors(self, value):
        return [str(item).strip() for item in (value or []) if str(item).strip()]

    def validate_news_keywords(self, value):
        return [str(item).strip() for item in (value or []) if str(item).strip()]


class WatchedCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchedCompany
        fields = (
            "id",
            "strategy",
            "ticker",
            "name",
            "aliases",
            "sector",
            "rss_url",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_ticker(self, value):
        ticker = (value or "").strip().upper()
        if not ticker:
            raise serializers.ValidationError("Ticker is required.")
        return ticker


class NestedWatchedCompanySerializer(WatchedCompanySerializer):
    class Meta(WatchedCompanySerializer.Meta):
        fields = (
            "id",
            "ticker",
            "name",
            "aliases",
            "sector",
            "rss_url",
            "is_active",
            "created_at",
            "updated_at",
        )


class AccessUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email")


class UserGroupBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserGroup
        fields = ("id", "slug", "name", "is_active")


class UserGroupSerializer(serializers.ModelSerializer):
    member_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.filter(is_deleted=False),
        source="members",
        required=False,
        write_only=True,
    )
    members = AccessUserSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()
    slug = serializers.SlugField(max_length=64, required=False, allow_blank=True)

    class Meta:
        model = UserGroup
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "is_active",
            "member_ids",
            "members",
            "member_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "members", "member_count", "created_at", "updated_at")

    def validate(self, attrs):
        slug = (attrs.get("slug") or "").strip()
        name = attrs.get("name") or (self.instance.name if self.instance else "")
        if slug:
            attrs["slug"] = slug
        elif self.instance is None:
            generated = slugify(name)
            if not generated:
                raise serializers.ValidationError(
                    {"slug": "Provide a slug or a name that can be turned into one."}
                )
            attrs["slug"] = generated
        else:
            attrs.pop("slug", None)

        slug = attrs.get("slug")
        if slug:
            qs = UserGroup.objects.filter(slug=slug)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"slug": "This slug is already in use."})
        return attrs

    def create(self, validated_data):
        members = validated_data.pop("members", None)
        group = UserGroup.objects.create(**validated_data)
        if members is not None:
            group.members.set(members)
        return group

    def update(self, instance, validated_data):
        members = validated_data.pop("members", serializers.empty)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if members is not serializers.empty:
            instance.members.set(members)
        return instance

    def get_member_count(self, obj) -> int:
        count = getattr(obj, "member_count", None)
        if count is not None:
            return int(count)
        return obj.members.count()


class AdminStrategySerializer(serializers.ModelSerializer):
    x_source = StrategyXSourceSerializer(required=False, allow_null=True)
    research_config = ResearchWatchConfigSerializer(required=False, allow_null=True)
    watched_companies = NestedWatchedCompanySerializer(many=True, required=False)
    assigned_user_count = serializers.SerializerMethodField()
    slug = serializers.SlugField(max_length=64, required=False, allow_blank=True)
    strategy_type = serializers.ChoiceField(
        choices=STRATEGY_TYPE_CHOICES, default=STRATEGY_TYPE_COPY_TRADE
    )
    signal_source = serializers.ChoiceField(
        choices=COPY_TRADE_SIGNAL_SOURCE_CHOICES,
        default=SIGNAL_SOURCE_X,
        required=False,
        allow_blank=True,
    )
    visibility = serializers.ChoiceField(
        choices=STRATEGY_VISIBILITY_CHOICES, default=STRATEGY_VISIBILITY_PUBLIC
    )
    allowed_user_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.filter(is_deleted=False),
        source="allowed_users",
        required=False,
        write_only=True,
    )
    allowed_group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UserGroup.objects.filter(is_active=True),
        source="allowed_groups",
        required=False,
        write_only=True,
    )
    allowed_users = AccessUserSerializer(many=True, read_only=True)
    allowed_groups = UserGroupBriefSerializer(many=True, read_only=True)

    class Meta:
        model = Strategy
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "strategy_type",
            "signal_source",
            "visibility",
            "is_active",
            "x_source",
            "research_config",
            "watched_companies",
            "allowed_user_ids",
            "allowed_group_ids",
            "allowed_users",
            "allowed_groups",
            "assigned_user_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "allowed_users",
            "allowed_groups",
            "assigned_user_count",
            "created_at",
            "updated_at",
        )

    def get_assigned_user_count(self, obj) -> int:
        count = getattr(obj, "assigned_user_count", None)
        if count is not None:
            return int(count)
        return obj.assignments.filter(is_active=True).count()

    def validate(self, attrs):
        slug = (attrs.get("slug") or "").strip()
        name = attrs.get("name") or (self.instance.name if self.instance else "")
        if slug:
            attrs["slug"] = slug
        elif self.instance is None:
            generated = slugify(name)
            if not generated:
                raise serializers.ValidationError(
                    {"slug": "Provide a slug or a name that can be turned into one."}
                )
            attrs["slug"] = generated
        else:
            attrs.pop("slug", None)

        strategy_type = attrs.get("strategy_type") or (
            self.instance.strategy_type if self.instance else STRATEGY_TYPE_COPY_TRADE
        )
        if strategy_type == STRATEGY_TYPE_COPY_TRADE:
            signal_source = attrs.get("signal_source")
            if not signal_source:
                signal_source = (
                    self.instance.signal_source if self.instance else SIGNAL_SOURCE_X
                ) or SIGNAL_SOURCE_X
            source_meta = next(
                (
                    row
                    for row in COPY_TRADE_SIGNAL_SOURCE_CATALOG
                    if row["value"] == signal_source
                ),
                None,
            )
            if source_meta is None:
                raise serializers.ValidationError(
                    {"signal_source": "Unknown copy-trade source."}
                )
            if not source_meta["available"]:
                raise serializers.ValidationError(
                    {
                        "signal_source": (
                            f"{source_meta['label']} is not available yet."
                        )
                    }
                )
            attrs["signal_source"] = signal_source

        source = attrs.get("x_source")
        if source:
            handle = (source.get("handle") or "").lstrip("@").strip().lower()
            qs = XAccountSource.objects.filter(handle=handle)
            if self.instance:
                qs = qs.exclude(strategy_id=self.instance.pk)
            if handle and qs.exists():
                raise serializers.ValidationError(
                    {"x_source": {"handle": "That X account is already watched."}}
                )
        companies = attrs.get("watched_companies")
        if companies:
            tickers = [(row.get("ticker") or "").strip().upper() for row in companies]
            if len(tickers) != len(set(tickers)):
                raise serializers.ValidationError(
                    {"watched_companies": "Each ticker can only appear once on a strategy."}
                )
        return attrs

    def _upsert_x_source(self, strategy, data):
        existing = strategy.primary_x_source()
        if existing is None:
            created = XAccountSource.objects.create(strategy=strategy, **data)
            strategy.x_sources.exclude(pk=created.pk).update(is_active=False)
            return created
        for field, value in data.items():
            setattr(existing, field, value)
        existing.save()
        strategy.x_sources.exclude(pk=existing.pk).update(is_active=False)
        return existing

    def _upsert_research_config(self, strategy, data):
        existing = getattr(strategy, "research_config", None)
        if existing is None:
            return ResearchWatchConfig.objects.create(strategy=strategy, **(data or {}))
        if not data:
            return existing
        for field, value in data.items():
            setattr(existing, field, value)
        existing.save()
        return existing

    def _upsert_watched_companies(self, strategy, rows):
        for data in rows:
            ticker = (data.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            payload = {**data, "ticker": ticker}
            payload.pop("strategy", None)
            WatchedCompany.objects.update_or_create(
                strategy=strategy, ticker=ticker, defaults=payload
            )

    def create(self, validated_data):
        users = validated_data.pop("allowed_users", None)
        groups = validated_data.pop("allowed_groups", None)
        source_data = validated_data.pop("x_source", None)
        research_data = validated_data.pop("research_config", None)
        companies = validated_data.pop("watched_companies", None)
        strategy = Strategy.objects.create(**validated_data)
        if users is not None:
            strategy.allowed_users.set(users)
        if groups is not None:
            strategy.allowed_groups.set(groups)
        if source_data:
            self._upsert_x_source(strategy, source_data)
        if (
            strategy.strategy_type == STRATEGY_TYPE_RESEARCH_BREAKTHROUGH
            or research_data
            or companies
        ):
            self._upsert_research_config(strategy, research_data)
        if companies:
            self._upsert_watched_companies(strategy, companies)
        return strategy

    def update(self, instance, validated_data):
        users = validated_data.pop("allowed_users", serializers.empty)
        groups = validated_data.pop("allowed_groups", serializers.empty)
        source_data = validated_data.pop("x_source", serializers.empty)
        research_data = validated_data.pop("research_config", serializers.empty)
        companies = validated_data.pop("watched_companies", serializers.empty)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if users is not serializers.empty:
            instance.allowed_users.set(users)
        if groups is not serializers.empty:
            instance.allowed_groups.set(groups)
        if source_data is serializers.empty:
            pass
        elif source_data is None:
            instance.x_sources.update(is_active=False)
        else:
            self._upsert_x_source(instance, source_data)
        if research_data is serializers.empty:
            pass
        elif research_data is None:
            ResearchWatchConfig.objects.filter(strategy=instance).delete()
        else:
            self._upsert_research_config(instance, research_data)
        if companies is serializers.empty:
            self._drop_prefetched(instance, "x_sources", "watched_companies", "allowed_users", "allowed_groups")
            return instance
        if companies is None:
            instance.watched_companies.update(is_active=False)
            self._drop_prefetched(instance, "x_sources", "watched_companies", "allowed_users", "allowed_groups")
            return instance
        self._upsert_watched_companies(instance, companies)
        self._drop_prefetched(instance, "x_sources", "watched_companies", "allowed_users", "allowed_groups")
        return instance

    def _drop_prefetched(self, instance, *lookups):
        cache = getattr(instance, "_prefetched_objects_cache", None)
        if not cache:
            return
        for lookup in lookups:
            cache.pop(lookup, None)


class BrokerConnectionSerializer(serializers.ModelSerializer):
    agentic_ready = serializers.SerializerMethodField()

    class Meta:
        model = BrokerConnection
        fields = (
            "id",
            "broker",
            "status",
            "broker_account_id",
            "is_paper",
            "last_equity",
            "last_synced_at",
            "last_error",
            "agentic_ready",
            "created_at",
        )
        read_only_fields = fields

    def get_agentic_ready(self, obj) -> bool:
        if obj.broker != "robinhood":
            return True
        return bool(obj.broker_account_id)


class BrokerAccountSerializer(serializers.Serializer):
    account_number = serializers.CharField()
    nickname = serializers.CharField(allow_blank=True)
    type = serializers.CharField(allow_blank=True)
    state = serializers.CharField(allow_blank=True)
    agentic_allowed = serializers.BooleanField()
    option_level = serializers.CharField(allow_blank=True)
    is_default = serializers.BooleanField()
    equity = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    cash = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    buying_power = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )


class BrokerSelectAccountSerializer(serializers.Serializer):
    account_number = serializers.CharField(
        allow_blank=True,
        help_text="Agentic account to trade in. Blank disables trading.",
    )


class AgentToolSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    category = serializers.CharField()
    available = serializers.BooleanField()


class RobinhoodOAuthStartSerializer(serializers.Serializer):
    authorization_url = serializers.URLField(read_only=True)
    paste_required = serializers.BooleanField(read_only=True)
    instruction = serializers.CharField(read_only=True)


class RobinhoodOAuthCompleteSerializer(serializers.Serializer):
    callback_url = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=4000,
        help_text="Full localhost URL from the address bar after allowing Robinhood.",
    )
    code = serializers.CharField(required=False, allow_blank=True, max_length=512)
    state = serializers.CharField(required=False, allow_blank=True, max_length=512)

    def validate(self, attrs):
        callback_url = (attrs.get("callback_url") or "").strip()
        code = (attrs.get("code") or "").strip()
        state = (attrs.get("state") or "").strip()
        if callback_url:
            try:
                parsed_code, parsed_state = parse_oauth_callback(callback_url)
            except RobinhoodError as exc:
                raise serializers.ValidationError({"callback_url": str(exc)}) from exc
            code = code or parsed_code
            state = state or parsed_state
        if not code or not state:
            raise serializers.ValidationError(
                {
                    "callback_url": (
                        "Paste the full URL from the address bar after allowing "
                        "Robinhood. It includes code= and state=."
                    )
                }
            )
        attrs["code"] = code
        attrs["state"] = state
        return attrs


class RobinhoodOAuthCompleteResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("connected", "needs_account"))
    connection = BrokerConnectionSerializer()


class BrokerConnectSerializer(serializers.Serializer):
    broker = serializers.ChoiceField(choices=BROKER_CHOICES)
    api_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    api_secret = serializers.CharField(required=False, allow_blank=True, write_only=True)
    broker_account_id = serializers.CharField(required=False, allow_blank=True)
    is_paper = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        broker = attrs["broker"]
        if broker == "robinhood":
            raise serializers.ValidationError(
                {
                    "broker": (
                        "Robinhood connects through OAuth. "
                        "POST /api/broker-connections/robinhood/oauth/start/"
                    )
                }
            )
        if broker == "alpaca" and not (attrs.get("api_key") and attrs.get("api_secret")):
            raise serializers.ValidationError(
                {"api_key": "Alpaca requires api_key and api_secret."}
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        disconnect_user_brokers(user)
        secrets = {
            "api_key": validated_data.pop("api_key", ""),
            "api_secret": validated_data.pop("api_secret", ""),
        }
        from decimal import Decimal

        connection = BrokerConnection.objects.create(
            user=user,
            broker=validated_data["broker"],
            broker_account_id=validated_data.get("broker_account_id") or "",
            is_paper=validated_data.get("is_paper", True),
            encrypted_credentials=encrypt_credentials(secrets),
            status=BrokerConnection.Status.CONNECTED,
            last_equity=Decimal("100000.00"),
        )
        return connection


def disconnect_user_brokers(user) -> None:
    for existing in BrokerConnection.objects.filter(user=user):
        existing.soft_delete()
        existing.status = BrokerConnection.Status.DISCONNECTED
        existing.save(update_fields=["status", "updated_at"])


class AssignmentSerializer(serializers.ModelSerializer):
    strategy = StrategySerializer(read_only=True)
    investment_tier = InvestmentTierSerializer(read_only=True)
    strategy_id = serializers.PrimaryKeyRelatedField(
        queryset=Strategy.objects.filter(is_active=True),
        source="strategy",
        write_only=True,
    )
    investment_tier_id = serializers.PrimaryKeyRelatedField(
        queryset=InvestmentTier.objects.filter(is_active=True),
        source="investment_tier",
        write_only=True,
    )
    broker_account_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Brokerage account this strategy should run on. Required to bind a Robinhood Agentic account.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_staff:
            self.fields["strategy_id"].queryset = strategies_visible_to(user)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        strategy = attrs.get("strategy")
        if user is not None and strategy is not None and not user_can_access_strategy(user, strategy):
            raise serializers.ValidationError(
                {"strategy_id": "You cannot select this strategy."}
            )
        if "broker_account_id" not in attrs:
            return attrs
        account_id = (attrs.get("broker_account_id") or "").strip()
        attrs["broker_account_id"] = account_id
        if not account_id or user is None:
            return attrs
        connection = BrokerConnection.objects.filter(user=user).first()
        if connection is None:
            raise serializers.ValidationError(
                {"broker_account_id": "Connect a brokerage account first."}
            )
        if connection.broker != "robinhood":
            return attrs
        try:
            accounts = list_account_summaries_for(connection)
        except RobinhoodError as exc:
            raise serializers.ValidationError({"broker_account_id": str(exc)}) from exc
        match = next(
            (row for row in accounts if row.get("account_number") == account_id),
            None,
        )
        if match is None:
            raise serializers.ValidationError(
                {"broker_account_id": "That account was not returned by Robinhood."}
            )
        if not match.get("agentic_allowed"):
            raise serializers.ValidationError(
                {
                    "broker_account_id": (
                        "Strategies can only run on a Robinhood Agentic account."
                    )
                }
            )
        return attrs

    class Meta:
        model = UserStrategyAssignment
        fields = (
            "id",
            "strategy",
            "investment_tier",
            "strategy_id",
            "investment_tier_id",
            "broker_account_id",
            "is_active",
            "assigned_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_active", "assigned_at", "updated_at")

    def create(self, validated_data):
        request = self.context["request"]
        kwargs = {
            "user": self.context.get("target_user") or request.user,
            "strategy": validated_data["strategy"],
            "investment_tier": validated_data["investment_tier"],
            "assigned_by": request.user,
        }
        if "broker_account_id" in validated_data:
            kwargs["broker_account_id"] = validated_data["broker_account_id"]
        return set_assignment(**kwargs)


class AccountPerformanceSerializer(serializers.Serializer):
    lifetime_realized_pnl = serializers.CharField()
    lifetime_unrealized_pnl = serializers.CharField()
    lifetime_total_pnl = serializers.CharField()
    daily_realized_pnl = serializers.CharField()
    weekly_realized_pnl = serializers.CharField()
    open_positions = serializers.IntegerField()
    closed_trades = serializers.IntegerField()


class BrokerAccountDetailSerializer(serializers.Serializer):
    connection = BrokerConnectionSerializer()
    account = BrokerAccountSerializer()
    trading_enabled = serializers.BooleanField()
    assignment = AssignmentSerializer(allow_null=True)
    performance = AccountPerformanceSerializer()


class DecisionSerializer(serializers.ModelSerializer):
    strategy_name = serializers.SerializerMethodField()
    tier_name = serializers.SerializerMethodField()
    signal_code = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    reason_label = serializers.CharField(source="get_reason_code_display", read_only=True)
    notification_id = serializers.SerializerMethodField()

    class Meta:
        model = Decision
        fields = (
            "id",
            "action",
            "action_label",
            "outcome",
            "outcome_label",
            "reason_code",
            "reason_label",
            "title",
            "summary",
            "context",
            "strategy_id",
            "strategy_name",
            "investment_tier_id",
            "tier_name",
            "signal_id",
            "signal_code",
            "trade_id",
            "trade_event_id",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "quantity",
            "price",
            "broker_account_id",
            "notification_id",
            "created_at",
        )

    def get_strategy_name(self, obj) -> str:
        return obj.strategy.name if obj.strategy_id else ""

    def get_tier_name(self, obj) -> str:
        return obj.investment_tier.name if obj.investment_tier_id else ""

    def get_signal_code(self, obj) -> str:
        return obj.signal.code if obj.signal_id else ""

    def get_notification_id(self, obj) -> int | None:
        rows = getattr(obj, "_prefetched_objects_cache", {}).get("notifications")
        if rows is not None:
            return rows[0].id if rows else None
        notification = obj.notifications.order_by("id").first()
        return notification.id if notification else None


class TradeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeEvent
        fields = (
            "id",
            "event_type",
            "quantity",
            "price",
            "realized_pnl",
            "notes",
            "created_at",
        )


class BrokerOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerOrder
        fields = (
            "id",
            "broker_order_id",
            "side",
            "status",
            "quantity",
            "filled_quantity",
            "filled_avg_price",
            "submitted_at",
        )


class TradeSerializer(serializers.ModelSerializer):
    events = TradeEventSerializer(many=True, read_only=True)
    orders = BrokerOrderSerializer(many=True, read_only=True)
    decision_logs = DecisionSerializer(many=True, read_only=True)
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    tier_name = serializers.CharField(source="investment_tier.name", read_only=True)
    signal_code = serializers.CharField(source="signal.code", read_only=True)

    class Meta:
        model = Trade
        fields = (
            "id",
            "signal_id",
            "signal_code",
            "strategy_id",
            "strategy_name",
            "investment_tier_id",
            "tier_name",
            "broker_account_id",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "status",
            "entry_price",
            "entry_quantity",
            "remaining_quantity",
            "average_exit_price",
            "realized_pnl",
            "entered_at",
            "closed_at",
            "events",
            "orders",
            "decision_logs",
        )


class PositionSerializer(serializers.ModelSerializer):
    trade_id = serializers.IntegerField(read_only=True)
    tier_name = serializers.CharField(
        source="trade.investment_tier.name", read_only=True
    )

    class Meta:
        model = Position
        fields = (
            "id",
            "trade_id",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "quantity",
            "average_entry_price",
            "current_price",
            "unrealized_pnl",
            "status",
            "tier_name",
            "opened_at",
            "updated_at",
        )


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "title",
            "body",
            "trade_id",
            "signal_id",
            "decision_id",
            "broker_account_id",
            "is_read",
            "created_at",
        )


class SignalSerializer(serializers.ModelSerializer):
    tweet_id = serializers.CharField(
        source="ingested_post.tweet_id", read_only=True, allow_null=True, default=None
    )
    tweet_text = serializers.CharField(
        source="ingested_post.text", read_only=True, allow_null=True, default=None
    )
    tweet_posted_at = serializers.DateTimeField(
        source="ingested_post.posted_at", read_only=True, allow_null=True, default=None
    )
    tweet_parse_status = serializers.CharField(
        source="ingested_post.parse_status", read_only=True, allow_null=True, default=None
    )
    research_event_id = serializers.IntegerField(read_only=True, allow_null=True)
    headline = serializers.CharField(
        source="research_event.headline", read_only=True, allow_null=True, default=None
    )
    event_type = serializers.CharField(
        source="research_event.event_type", read_only=True, allow_null=True, default=None
    )
    catalyst_score = serializers.IntegerField(
        source="research_event.score", read_only=True, allow_null=True, default=None
    )
    source_url = serializers.CharField(
        source="research_event.source_url", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = Signal
        fields = (
            "id",
            "code",
            "strategy",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "suggested_entry_price",
            "quote_price",
            "notes",
            "source",
            "ingested_post_id",
            "tweet_id",
            "tweet_text",
            "tweet_posted_at",
            "tweet_parse_status",
            "research_event_id",
            "headline",
            "event_type",
            "catalyst_score",
            "source_url",
            "status",
            "processed_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "code",
            "ingested_post_id",
            "tweet_id",
            "tweet_text",
            "tweet_posted_at",
            "tweet_parse_status",
            "research_event_id",
            "headline",
            "event_type",
            "catalyst_score",
            "source_url",
            "status",
            "processed_at",
            "created_at",
        )


class SignalCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signal
        fields = (
            "strategy",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "suggested_entry_price",
            "quote_price",
            "notes",
            "source",
        )

    def create(self, validated_data):
        validated_data["ticker"] = validated_data["ticker"].upper()
        return super().create(validated_data)


class SignalDecisionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    decision_id = serializers.SerializerMethodField()

    class Meta:
        model = SignalDecision
        fields = (
            "id",
            "signal_id",
            "user_id",
            "username",
            "outcome",
            "skip_reason",
            "trade_id",
            "decision_id",
            "notes",
            "created_at",
        )

    def get_decision_id(self, obj) -> int | None:
        try:
            return obj.log.id
        except Decision.DoesNotExist:
            return None


class XAccountSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = XAccountSource
        fields = (
            "id",
            "strategy",
            "handle",
            "display_name",
            "x_user_id",
            "is_active",
            "lookback_hours",
            "poll_interval_seconds",
            "last_tweet_id",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "x_user_id",
            "last_tweet_id",
            "last_polled_at",
            "last_error",
            "created_at",
            "updated_at",
        )


class SignalSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Signal
        fields = (
            "id",
            "code",
            "ticker",
            "option_type",
            "strike",
            "expiration",
            "suggested_entry_price",
            "status",
            "created_at",
        )


class IngestedPostSerializer(serializers.ModelSerializer):
    handle = serializers.CharField(source="source.handle", read_only=True)
    strategy_id = serializers.IntegerField(source="source.strategy_id", read_only=True)
    signal_ids = serializers.PrimaryKeyRelatedField(
        source="signals", many=True, read_only=True
    )
    signals = SignalSummarySerializer(many=True, read_only=True)

    class Meta:
        model = IngestedPost
        fields = (
            "id",
            "source",
            "strategy_id",
            "handle",
            "tweet_id",
            "text",
            "posted_at",
            "parse_status",
            "parsed_trades",
            "skip_reason",
            "signal_ids",
            "signals",
            "created_at",
            "updated_at",
        )


class XIngestSerializer(serializers.Serializer):
    text = serializers.CharField()
    tweet_id = serializers.CharField(required=False, allow_blank=True)
    posted_at = serializers.DateTimeField(required=False)
    process = serializers.BooleanField(required=False, default=True)


class XParseSerializer(serializers.Serializer):
    text = serializers.CharField()
    posted_at = serializers.DateTimeField(required=False)


class XLookbackSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=90, required=False, default=30)


class ResearchEventSerializer(serializers.ModelSerializer):
    ticker = serializers.CharField(source="company.ticker", read_only=True, default="")
    signal_ids = serializers.PrimaryKeyRelatedField(
        source="signals", many=True, read_only=True
    )
    signals = SignalSummarySerializer(many=True, read_only=True)

    class Meta:
        model = ResearchEvent
        fields = (
            "id",
            "strategy",
            "company",
            "ticker",
            "external_id",
            "source",
            "source_url",
            "headline",
            "summary",
            "published_at",
            "status",
            "event_type",
            "direction",
            "score",
            "rationale",
            "skip_reason",
            "option_suggestion",
            "signal_ids",
            "signals",
            "created_at",
            "updated_at",
        )


class ResearchIngestSerializer(serializers.Serializer):
    headline = serializers.CharField()
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    source_url = serializers.URLField(required=False, allow_blank=True, default="")
    published_at = serializers.DateTimeField(required=False)
    process = serializers.BooleanField(required=False, default=True)


class ResearchParseSerializer(serializers.Serializer):
    headline = serializers.CharField()
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    tickers = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Optional ticker subset. Defaults to the strategy watchlist.",
    )
    enabled_event_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Limit classification to these catalyst types. Empty means all.",
    )
    require_confirmation = serializers.BooleanField(required=False, default=True)


class AdminForceAssignmentSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    strategy_id = serializers.IntegerField(required=False)
    investment_tier_id = serializers.IntegerField()


class AdminUserSerializer(serializers.ModelSerializer):
    assignment = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "is_staff",
            "is_active",
            "email_verified",
            "date_joined",
            "assignment",
            "subscription",
        )

    def get_subscription(self, obj) -> dict:
        from billing.services.entitlements import entitlement_payload

        return entitlement_payload(obj)

    def get_assignment(self, obj) -> dict | None:
        rows = getattr(obj, "active_assignments", None)
        if rows is None:
            row = (
                obj.strategy_assignments.filter(is_active=True)
                .select_related("strategy", "investment_tier")
                .first()
            )
        else:
            row = rows[0] if rows else None
        if row is None:
            return None
        return AssignmentSerializer(row).data


class PlatformStatsSerializer(serializers.Serializer):
    lifetime_realized_pnl = serializers.CharField()
    lifetime_unrealized_pnl = serializers.CharField()
    lifetime_total_pnl = serializers.CharField()
    trade_count = serializers.IntegerField()
    win_count = serializers.IntegerField()
    loss_count = serializers.IntegerField()
    active_user_count = serializers.IntegerField()
    open_position_count = serializers.IntegerField()
    users_by_tier = serializers.DictField()
    pnl_by_strategy = serializers.DictField()
    pnl_by_tier = serializers.DictField()
    updated_at = serializers.DateTimeField()
