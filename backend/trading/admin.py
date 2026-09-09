from django.contrib import admin

from .models import (
    AccountTradingState,
    BrokerConnection,
    BrokerOrder,
    Decision,
    IngestedPost,
    InvestmentTier,
    Notification,
    PerformanceSnapshot,
    PlatformStats,
    Position,
    ResearchEvent,
    ResearchWatchConfig,
    Signal,
    SignalDecision,
    Strategy,
    Trade,
    TradeEvent,
    UserGroup,
    UserStrategyAssignment,
    WatchedCompany,
    XAccountSource,
)


@admin.register(InvestmentTier)
class InvestmentTierAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "slug",
        "name",
        "is_default",
        "max_open_positions",
        "max_risk_per_trade_pct",
        "hard_stop_pct",
        "daily_loss_limit_pct",
        "is_active",
    )
    list_filter = ("is_active", "is_default")
    search_fields = ("slug", "name")


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "name")
    filter_horizontal = ("members",)


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name", "strategy_type", "visibility", "is_active")
    list_filter = ("is_active", "strategy_type", "visibility")
    filter_horizontal = ("allowed_users", "allowed_groups")


@admin.register(XAccountSource)
class XAccountSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "handle",
        "strategy",
        "is_active",
        "poll_interval_seconds",
        "last_polled_at",
        "last_error",
    )
    list_filter = ("is_active",)
    search_fields = ("handle", "display_name")


@admin.register(IngestedPost)
class IngestedPostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "tweet_id",
        "parse_status",
        "posted_at",
        "created_at",
    )
    list_filter = ("parse_status", "source")
    search_fields = ("tweet_id", "text")
    readonly_fields = ("parsed_trades",)


@admin.register(ResearchWatchConfig)
class ResearchWatchConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "strategy",
        "poll_interval_seconds",
        "min_catalyst_score",
        "sectors",
        "last_polled_at",
        "last_error",
    )
    search_fields = ("strategy__slug", "strategy__name")


@admin.register(WatchedCompany)
class WatchedCompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "ticker", "name", "sector", "strategy", "is_active")
    list_filter = ("is_active", "sector")
    search_fields = ("ticker", "name")


@admin.register(ResearchEvent)
class ResearchEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "strategy",
        "headline",
        "status",
        "event_type",
        "direction",
        "score",
        "published_at",
    )
    list_filter = ("status", "event_type", "direction", "source")
    search_fields = ("headline", "external_id")
    readonly_fields = ("option_suggestion",)


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "broker",
        "status",
        "is_paper",
        "last_equity",
        "is_deleted",
    )
    list_filter = ("broker", "status", "is_paper", "is_deleted")
    search_fields = ("user__username", "broker_account_id")
    exclude = ("encrypted_credentials",)


@admin.register(UserStrategyAssignment)
class UserStrategyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "strategy", "investment_tier", "is_active", "assigned_at")
    list_filter = ("is_active", "investment_tier", "strategy")
    search_fields = ("user__username",)


@admin.register(AccountTradingState)
class AccountTradingStateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "lifetime_realized_pnl",
        "lifetime_unrealized_pnl",
        "daily_realized_pnl",
        "is_paused_daily_loss",
    )
    search_fields = ("user__username",)


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "strategy",
        "ticker",
        "option_type",
        "strike",
        "expiration",
        "status",
        "created_at",
    )
    list_filter = ("status", "option_type", "strategy")
    search_fields = ("code", "ticker")


class TradeEventInline(admin.TabularInline):
    model = TradeEvent
    extra = 0
    readonly_fields = (
        "event_type",
        "quantity",
        "price",
        "realized_pnl",
        "notes",
        "created_at",
    )


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "ticker",
        "status",
        "entry_quantity",
        "remaining_quantity",
        "realized_pnl",
        "entered_at",
    )
    list_filter = ("status", "investment_tier", "strategy")
    search_fields = ("user__username", "ticker", "signal__code")
    inlines = [TradeEventInline]


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "ticker",
        "quantity",
        "average_entry_price",
        "unrealized_pnl",
        "status",
    )
    list_filter = ("status",)
    search_fields = ("user__username", "ticker")


@admin.register(SignalDecision)
class SignalDecisionAdmin(admin.ModelAdmin):
    list_display = ("id", "signal", "user", "outcome", "skip_reason", "created_at")
    list_filter = ("outcome", "skip_reason")


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "action",
        "outcome",
        "reason_code",
        "ticker",
        "title",
        "created_at",
    )
    list_filter = ("action", "outcome", "reason_code")
    search_fields = ("user__username", "ticker", "title", "summary")


@admin.register(BrokerOrder)
class BrokerOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "trade", "side", "status", "quantity", "filled_avg_price")
    list_filter = ("side", "status")


@admin.register(PerformanceSnapshot)
class PerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "period_type",
        "period_start",
        "realized_pnl",
        "unrealized_pnl",
    )
    list_filter = ("period_type",)


@admin.register(PlatformStats)
class PlatformStatsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lifetime_realized_pnl",
        "lifetime_unrealized_pnl",
        "active_user_count",
        "open_position_count",
        "updated_at",
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__username", "title")
