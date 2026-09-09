from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import SoftDeleteModel

from .constants import (
    BROKER_CHOICES,
    DIRECTION_CHOICES,
    DIR_UNKNOWN,
    EVENT_OTHER,
    EVENT_TYPE_CHOICES,
    OPTION_TYPE_CHOICES,
    PARSE_ERROR,
    PARSE_NO_TRADE,
    PARSE_PARSED,
    PARSE_PENDING,
    PARSE_SKIPPED,
    PARSE_STATUS_CHOICES,
    PERIOD_TYPE_CHOICES,
    RESEARCH_MAX_DTE_DEFAULT,
    RESEARCH_MIN_CATALYST_SCORE_DEFAULT,
    RESEARCH_MIN_DTE_DEFAULT,
    RESEARCH_OTM_PCT_DEFAULT,
    RESEARCH_PENDING,
    RESEARCH_POLL_INTERVAL_SECONDS_DEFAULT,
    RESEARCH_POLL_INTERVAL_SECONDS_MAX,
    RESEARCH_POLL_INTERVAL_SECONDS_MIN,
    RESEARCH_SIGNAL_COOLDOWN_HOURS_DEFAULT,
    RESEARCH_STATUS_CHOICES,
    SIGNAL_SOURCE_X,
    STRATEGY_TYPE_COPY_TRADE,
    STRATEGY_VISIBILITY_CHOICES,
    STRATEGY_VISIBILITY_PUBLIC,
    X_POLL_INTERVAL_SECONDS_DEFAULT,
    X_POLL_INTERVAL_SECONDS_MAX,
    X_POLL_INTERVAL_SECONDS_MIN,
)


class InvestmentTier(models.Model):
    """Editable rule set that controls how a user enters and manages trades."""

    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    max_entry_slippage_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Skip entry if live price is this percent above the signal price.",
    )
    max_entry_slippage_pct_min = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    max_risk_per_trade_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Operational max risk per trade as a percent of equity.",
    )
    max_risk_per_trade_pct_min = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    max_open_positions = models.PositiveSmallIntegerField()

    take_profit_rules = models.JSONField(
        default=list,
        help_text=(
            "List of legs: pct_of_position, gain_pct (trigger), optional "
            "gain_pct_min/max, optional is_runner."
        ),
    )
    hard_stop_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Close remaining size if loss reaches this percent (stored positive).",
    )
    force_exit_time_et = models.TimeField(
        help_text="Force-close on expiration day at this America/New_York time.",
    )
    max_hold_trading_days = models.PositiveSmallIntegerField()
    daily_loss_limit_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Pause new entries when daily P&L reaches this percent loss of equity.",
    )
    daily_loss_limit_pct_min = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            type(self).objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class UserGroup(models.Model):
    """Named set of users used to restrict strategy access."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="trading_groups",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Strategy(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    strategy_type = models.CharField(max_length=32, default=STRATEGY_TYPE_COPY_TRADE)
    signal_source = models.CharField(
        max_length=32,
        default=SIGNAL_SOURCE_X,
        blank=True,
        help_text="Where copy-trade signals are pulled from. Ignored for other strategy types.",
    )
    visibility = models.CharField(
        max_length=16,
        choices=STRATEGY_VISIBILITY_CHOICES,
        default=STRATEGY_VISIBILITY_PUBLIC,
        db_index=True,
        help_text="public: every user can pick it. restricted: only allowed_users and allowed_groups.",
    )
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="allowed_strategies",
    )
    allowed_groups = models.ManyToManyField(
        "UserGroup",
        blank=True,
        related_name="strategies",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Strategies"

    def __str__(self):
        return self.name

    def primary_x_source(self):
        """Single watcher the admin form reads and writes.

        A strategy can have leftover placeholder rows (e.g. seed recreating
        configure-me). Prefer an active source, then the oldest row, so save
        and GET stay on the same account.
        """
        sources = list(self.x_sources.all())
        if not sources:
            return None
        active = [row for row in sources if row.is_active]
        return min(active or sources, key=lambda row: row.id)


class XAccountSource(models.Model):
    """Watched X (Twitter) account that feeds a Copy Trade strategy."""

    strategy = models.ForeignKey(
        Strategy, on_delete=models.PROTECT, related_name="x_sources"
    )
    handle = models.CharField(
        max_length=64,
        unique=True,
        help_text="X username without @.",
    )
    display_name = models.CharField(max_length=128, blank=True)
    x_user_id = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    lookback_hours = models.PositiveSmallIntegerField(
        default=48,
        help_text="Ignore tweets older than this on ingest.",
    )
    poll_interval_seconds = models.PositiveIntegerField(
        default=X_POLL_INTERVAL_SECONDS_DEFAULT,
        validators=[
            MinValueValidator(X_POLL_INTERVAL_SECONDS_MIN),
            MaxValueValidator(X_POLL_INTERVAL_SECONDS_MAX),
        ],
        help_text="How often to pull new posts from X, in seconds.",
    )
    last_tweet_id = models.CharField(max_length=32, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["handle"]

    def __str__(self):
        return f"@{self.handle}"

    def save(self, *args, **kwargs):
        self.handle = (self.handle or "").lstrip("@").strip().lower()
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk).values("handle").first()
            )
            if previous and previous["handle"] != self.handle:
                self.x_user_id = ""
                self.last_tweet_id = ""
        super().save(*args, **kwargs)


class IngestedPost(models.Model):
    class ParseStatus(models.TextChoices):
        PENDING = PARSE_PENDING, "Pending"
        PARSED = PARSE_PARSED, "Parsed"
        NO_TRADE = PARSE_NO_TRADE, "No trade"
        SKIPPED = PARSE_SKIPPED, "Skipped"
        ERROR = PARSE_ERROR, "Error"

    source = models.ForeignKey(
        XAccountSource, on_delete=models.CASCADE, related_name="posts"
    )
    tweet_id = models.CharField(max_length=64)
    text = models.TextField()
    posted_at = models.DateTimeField(null=True, blank=True)
    parse_status = models.CharField(
        max_length=16,
        choices=PARSE_STATUS_CHOICES,
        default=PARSE_PENDING,
        db_index=True,
    )
    parsed_trades = models.JSONField(default=list)
    skip_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-posted_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "tweet_id"],
                name="unique_tweet_per_x_source",
            )
        ]

    def __str__(self):
        return f"{self.source_id}:{self.tweet_id}"


class ResearchWatchConfig(models.Model):
    """Poll and contract-selection settings for a Research / Breakthrough strategy."""

    strategy = models.OneToOneField(
        Strategy, on_delete=models.CASCADE, related_name="research_config"
    )
    poll_interval_seconds = models.PositiveIntegerField(
        default=RESEARCH_POLL_INTERVAL_SECONDS_DEFAULT,
        validators=[
            MinValueValidator(RESEARCH_POLL_INTERVAL_SECONDS_MIN),
            MaxValueValidator(RESEARCH_POLL_INTERVAL_SECONDS_MAX),
        ],
        help_text="How often to pull company news, in seconds.",
    )
    lookback_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text="Ignore headlines older than this on ingest.",
    )
    min_catalyst_score = models.PositiveSmallIntegerField(
        default=RESEARCH_MIN_CATALYST_SCORE_DEFAULT,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Minimum classification score (0-100) required to emit a signal.",
    )
    otm_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal(RESEARCH_OTM_PCT_DEFAULT),
        help_text="How far out-of-the-money to select the strike, as a percent of spot.",
    )
    min_dte = models.PositiveSmallIntegerField(default=RESEARCH_MIN_DTE_DEFAULT)
    max_dte = models.PositiveSmallIntegerField(default=RESEARCH_MAX_DTE_DEFAULT)
    signal_cooldown_hours = models.PositiveSmallIntegerField(
        default=RESEARCH_SIGNAL_COOLDOWN_HOURS_DEFAULT,
        help_text="Skip a second signal on the same ticker within this window.",
    )
    sectors = models.JSONField(
        default=list,
        blank=True,
        help_text="If set, only poll watched companies in these sectors. Empty means all.",
    )
    enabled_event_types = models.JSONField(
        default=list,
        blank=True,
        help_text="Catalyst types to trade. Empty means all types.",
    )
    news_keywords = models.JSONField(
        default=list,
        blank=True,
        help_text="Google News search terms. Empty uses a generic or event-type pack.",
    )
    require_confirmation = models.BooleanField(
        default=True,
        help_text="Ignore rumor/speculation unless the company or a regulator confirmed it.",
    )
    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"research-config:{self.strategy_id}"

    def normalized_list(self, values) -> list[str]:
        return [str(item).strip() for item in (values or []) if str(item).strip()]

    def normalized_sectors(self) -> list[str]:
        return [item.lower() for item in self.normalized_list(self.sectors)]

    def allowed_event_types(self) -> set[str] | None:
        types = self.normalized_list(self.enabled_event_types)
        return set(types) if types else None

    def search_keywords(self) -> list[str]:
        from trading.constants import news_keywords_for_event_types

        custom = self.normalized_list(self.news_keywords)
        if custom:
            return custom
        return news_keywords_for_event_types(self.enabled_event_types)


class WatchedCompany(models.Model):
    """Company on a Research / Breakthrough watchlist."""

    strategy = models.ForeignKey(
        Strategy, on_delete=models.CASCADE, related_name="watched_companies"
    )
    ticker = models.CharField(max_length=16)
    name = models.CharField(max_length=128)
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="Alternate names used to match headlines.",
    )
    sector = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Optional tag used with research_config.sectors (e.g. healthcare, tech).",
    )
    rss_url = models.URLField(blank=True, help_text="Optional company IR / press RSS feed.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ticker"]
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "ticker"],
                name="unique_watched_company_per_strategy",
            )
        ]

    def __str__(self):
        return f"{self.ticker} ({self.name})"

    def save(self, *args, **kwargs):
        self.ticker = (self.ticker or "").strip().upper()
        super().save(*args, **kwargs)


class ResearchEvent(models.Model):
    """Ingested headline that may become a Research / Breakthrough signal."""

    strategy = models.ForeignKey(
        Strategy, on_delete=models.CASCADE, related_name="research_events"
    )
    company = models.ForeignKey(
        WatchedCompany,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    external_id = models.CharField(max_length=128)
    source = models.CharField(max_length=32)
    source_url = models.URLField(max_length=1024, blank=True)
    headline = models.CharField(max_length=512)
    summary = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=RESEARCH_STATUS_CHOICES,
        default=RESEARCH_PENDING,
        db_index=True,
    )
    event_type = models.CharField(
        max_length=32, choices=EVENT_TYPE_CHOICES, default=EVENT_OTHER, blank=True
    )
    direction = models.CharField(
        max_length=16, choices=DIRECTION_CHOICES, default=DIR_UNKNOWN, blank=True
    )
    score = models.PositiveSmallIntegerField(default=0)
    rationale = models.CharField(max_length=255, blank=True)
    skip_reason = models.CharField(max_length=255, blank=True)
    option_suggestion = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "external_id"],
                name="unique_research_event_per_strategy",
            )
        ]

    def __str__(self):
        return f"{self.strategy_id}:{self.external_id}"


class BrokerConnection(SoftDeleteModel):
    class Status(models.TextChoices):
        CONNECTED = "connected", "Connected"
        ERROR = "error", "Error"
        DISCONNECTED = "disconnected", "Disconnected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="broker_connections",
    )
    broker = models.CharField(max_length=32, choices=BROKER_CHOICES)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.CONNECTED
    )
    broker_account_id = models.CharField(max_length=128, blank=True)
    encrypted_credentials = models.TextField(blank=True)
    is_paper = models.BooleanField(default=True)
    last_equity = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_deleted=False),
                name="one_active_broker_connection_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.broker}"


class UserStrategyAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="strategy_assignments",
    )
    strategy = models.ForeignKey(
        Strategy, on_delete=models.PROTECT, related_name="assignments"
    )
    investment_tier = models.ForeignKey(
        InvestmentTier, on_delete=models.PROTECT, related_name="assignments"
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_strategy_changes",
    )
    broker_account_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Brokerage account this strategy runs on. Empty means the connection default.",
    )

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="one_active_strategy_assignment_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.strategy_id}:{self.investment_tier_id}"


class AccountTradingState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trading_state",
    )
    is_paused_daily_loss = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    daily_realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    lifetime_realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    lifetime_unrealized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    last_reset_on = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"state:{self.user_id}"


class Signal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        CANCELLED = "cancelled", "Cancelled"
        ERROR = "error", "Error"

    code = models.CharField(max_length=32, unique=True, blank=True)
    strategy = models.ForeignKey(
        Strategy, on_delete=models.PROTECT, related_name="signals"
    )
    ticker = models.CharField(max_length=16)
    option_type = models.CharField(max_length=4, choices=OPTION_TYPE_CHOICES)
    strike = models.DecimalField(max_digits=12, decimal_places=4)
    expiration = models.DateField()
    suggested_entry_price = models.DecimalField(max_digits=12, decimal_places=4)
    quote_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional live quote captured with the signal.",
    )
    notes = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=128, blank=True)
    ingested_post = models.ForeignKey(
        IngestedPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signals",
    )
    research_event = models.ForeignKey(
        "ResearchEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signals",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "ingested_post",
                    "ticker",
                    "option_type",
                    "strike",
                    "expiration",
                ],
                condition=models.Q(ingested_post__isnull=False),
                name="one_signal_per_post_contract",
            ),
            models.UniqueConstraint(
                fields=["research_event"],
                condition=models.Q(research_event__isnull=False),
                name="one_signal_per_research_event",
            )
        ]

    def __str__(self):
        return self.code or f"signal-{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"SIG-{self.pk}"
            super().save(update_fields=["code"])


class Trade(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        OPEN = "open", "Open"
        PARTIALLY_CLOSED = "partially_closed", "Partially closed"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trades"
    )
    signal = models.ForeignKey(
        Signal, on_delete=models.PROTECT, related_name="trades"
    )
    strategy = models.ForeignKey(
        Strategy, on_delete=models.PROTECT, related_name="trades"
    )
    investment_tier = models.ForeignKey(
        InvestmentTier, on_delete=models.PROTECT, related_name="trades"
    )
    broker_connection = models.ForeignKey(
        BrokerConnection, on_delete=models.PROTECT, related_name="trades"
    )
    broker_account_id = models.CharField(max_length=128, blank=True, db_index=True)
    ticker = models.CharField(max_length=16)
    option_type = models.CharField(max_length=4, choices=OPTION_TYPE_CHOICES)
    strike = models.DecimalField(max_digits=12, decimal_places=4)
    expiration = models.DateField()
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    entry_price = models.DecimalField(max_digits=12, decimal_places=4)
    entry_quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField()
    average_exit_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    closed_quantity = models.PositiveIntegerField(default=0)
    tp_stage = models.PositiveSmallIntegerField(default=0)
    tier_rules_snapshot = models.JSONField(default=dict)
    entered_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entered_at"]

    def __str__(self):
        return f"trade-{self.pk}"


class TradeEvent(models.Model):
    class EventType(models.TextChoices):
        ENTRY = "entry", "Entry"
        TAKE_PROFIT = "take_profit", "Take profit"
        STOP_LOSS = "stop_loss", "Stop loss"
        TIME_EXIT = "time_exit", "Time exit"
        FORCE_EXIT = "force_exit", "Force exit"
        EXPIRATION_EXIT = "expiration_exit", "Expiration exit"
        SUBMITTED = "submitted", "Submitted"
        UNFILLED = "unfilled", "Unfilled"
        SYNC_ADJUST = "sync_adjust", "Broker sync"

    trade = models.ForeignKey(
        Trade, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=4)
    realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Position(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="positions"
    )
    trade = models.OneToOneField(
        Trade, on_delete=models.CASCADE, related_name="position"
    )
    broker_connection = models.ForeignKey(
        BrokerConnection, on_delete=models.PROTECT, related_name="positions"
    )
    ticker = models.CharField(max_length=16)
    option_type = models.CharField(max_length=4, choices=OPTION_TYPE_CHOICES)
    strike = models.DecimalField(max_digits=12, decimal_places=4)
    expiration = models.DateField()
    quantity = models.PositiveIntegerField()
    average_entry_price = models.DecimalField(max_digits=12, decimal_places=4)
    current_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    unrealized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"pos-{self.pk}"


class SignalDecision(models.Model):
    class Outcome(models.TextChoices):
        ENTERED = "entered", "Entered"
        SKIPPED = "skipped", "Skipped"

    class SkipReason(models.TextChoices):
        NO_BROKER = "no_broker", "No brokerage connection"
        PAUSED = "paused", "Daily loss pause"
        DAILY_LOSS_LIMIT = "daily_loss_limit", "Daily loss limit"
        MAX_OPEN_POSITIONS = "max_open_positions", "Max open positions"
        SLIPPAGE = "slippage", "Entry slippage"
        SIZE_ZERO = "size_zero", "Position size rounded to zero"
        BROKER_ERROR = "broker_error", "Broker error"
        UNFILLED = "unfilled", "Order did not fill"
        WRONG_ACCOUNT = (
            "wrong_account",
            "Strategy is assigned to a different brokerage account",
        )
        SUBSCRIPTION_REQUIRED = "subscription_required", "Paid subscription required"

    signal = models.ForeignKey(
        Signal, on_delete=models.CASCADE, related_name="decisions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signal_decisions"
    )
    assignment = models.ForeignKey(
        UserStrategyAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decisions",
    )
    investment_tier = models.ForeignKey(
        InvestmentTier, on_delete=models.SET_NULL, null=True, blank=True
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    skip_reason = models.CharField(
        max_length=32, choices=SkipReason.choices, blank=True
    )
    trade = models.OneToOneField(
        Trade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["signal", "user"], name="one_decision_per_user_per_signal"
            )
        ]


class Decision(models.Model):
    """User-facing paper trail of how a strategy evaluated a signal or managed a position."""

    class Action(models.TextChoices):
        ENTER = "enter", "Enter"
        SKIP = "skip", "Skip"
        TAKE_PROFIT = "take_profit", "Take profit"
        STOP_LOSS = "stop_loss", "Stop loss"
        TIME_EXIT = "time_exit", "Time exit"
        FORCE_EXIT = "force_exit", "Force exit"
        EXPIRATION_EXIT = "expiration_exit", "Expiration exit"
        DAILY_PAUSE = "daily_pause", "Daily loss pause"

    class Outcome(models.TextChoices):
        ACTED = "acted", "Acted"
        PASSED = "passed", "Passed"

    class Reason(models.TextChoices):
        TIER_SIZE = "tier_size", "Sized by investment tier"
        NO_BROKER = "no_broker", "No brokerage connection"
        PAUSED = "paused", "Daily loss pause"
        DAILY_LOSS_LIMIT = "daily_loss_limit", "Daily loss limit"
        MAX_OPEN_POSITIONS = "max_open_positions", "Max open positions"
        SLIPPAGE = "slippage", "Entry slippage"
        SIZE_ZERO = "size_zero", "Position size rounded to zero"
        BROKER_ERROR = "broker_error", "Broker error"
        UNFILLED = "unfilled", "Order did not fill"
        WRONG_ACCOUNT = "wrong_account", "Assigned to a different brokerage account"
        SUBSCRIPTION_REQUIRED = "subscription_required", "Paid subscription required"
        TAKE_PROFIT = "take_profit", "Take-profit rule"
        STOP_LOSS = "stop_loss", "Hard stop"
        TIME_EXIT = "time_exit", "Max hold"
        FORCE_EXIT = "force_exit", "Force exit"
        EXPIRATION_EXIT = "expiration_exit", "Expiration force exit"
        DAILY_PAUSE = "daily_pause", "Daily loss pause"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="decision_logs",
    )
    strategy = models.ForeignKey(
        Strategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_logs",
    )
    investment_tier = models.ForeignKey(
        InvestmentTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_logs",
    )
    signal = models.ForeignKey(
        Signal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_logs",
    )
    signal_decision = models.OneToOneField(
        SignalDecision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="log",
    )
    trade = models.ForeignKey(
        Trade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_logs",
    )
    trade_event = models.ForeignKey(
        TradeEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decision_logs",
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, db_index=True)
    reason_code = models.CharField(
        max_length=32, choices=Reason.choices, blank=True
    )
    title = models.CharField(max_length=128)
    summary = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    ticker = models.CharField(max_length=16, blank=True, db_index=True)
    option_type = models.CharField(max_length=4, blank=True)
    strike = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    expiration = models.DateField(null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    broker_account_id = models.CharField(max_length=128, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"decision-{self.pk}:{self.action}:{self.outcome}"


class BrokerOrder(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        FILLED = "filled", "Filled"
        PARTIAL = "partial", "Partial"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class Side(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    trade = models.ForeignKey(
        Trade, on_delete=models.CASCADE, related_name="orders"
    )
    broker_connection = models.ForeignKey(
        BrokerConnection, on_delete=models.PROTECT, related_name="orders"
    )
    broker_order_id = models.CharField(max_length=128, blank=True)
    side = models.CharField(max_length=8, choices=Side.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    quantity = models.PositiveIntegerField()
    filled_quantity = models.PositiveIntegerField(default=0)
    filled_avg_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]


class PerformanceSnapshot(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="performance_snapshots",
    )
    strategy = models.ForeignKey(
        Strategy, on_delete=models.SET_NULL, null=True, blank=True
    )
    investment_tier = models.ForeignKey(
        InvestmentTier, on_delete=models.SET_NULL, null=True, blank=True
    )
    period_type = models.CharField(max_length=16, choices=PERIOD_TYPE_CHOICES)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    scope_key = models.CharField(max_length=160, unique=True)
    realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    unrealized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    trade_count = models.PositiveIntegerField(default=0)
    win_count = models.PositiveIntegerField(default=0)
    loss_count = models.PositiveIntegerField(default=0)
    open_position_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start", "-id"]


class PlatformStats(models.Model):
    lifetime_realized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    lifetime_unrealized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    trade_count = models.PositiveIntegerField(default=0)
    win_count = models.PositiveIntegerField(default=0)
    loss_count = models.PositiveIntegerField(default=0)
    active_user_count = models.PositiveIntegerField(default=0)
    open_position_count = models.PositiveIntegerField(default=0)
    users_by_tier = models.JSONField(default=dict)
    pnl_by_strategy = models.JSONField(default=dict)
    pnl_by_tier = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Platform stats"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "platform-stats"


class Notification(models.Model):
    class Kind(models.TextChoices):
        ENTRY = "entry", "Entry"
        TAKE_PROFIT = "take_profit", "Take profit"
        STOP_LOSS = "stop_loss", "Stop loss"
        EXIT = "exit", "Exit"
        SKIP = "skip", "Skipped signal"
        DAILY_PAUSE = "daily_pause", "Daily loss pause"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trading_notifications",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=128)
    body = models.CharField(max_length=255, blank=True)
    trade = models.ForeignKey(
        Trade, on_delete=models.SET_NULL, null=True, blank=True
    )
    signal = models.ForeignKey(
        Signal, on_delete=models.SET_NULL, null=True, blank=True
    )
    decision = models.ForeignKey(
        "Decision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    broker_account_id = models.CharField(max_length=128, blank=True, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
