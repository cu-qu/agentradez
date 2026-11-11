from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from trading.models import BrokerConnection

from .constants import (
    DEFAULT_MAX_EXPOSURE_USD,
    DEFAULT_MAX_LOSS_PER_POSITION_USD,
    DEFAULT_MAX_OPEN_POSITIONS,
    MARKET_CHOICES,
    ORDER_CANCELLED,
    ORDER_ENTRY,
    ORDER_EXIT,
    ORDER_FILLED,
    ORDER_WORKING,
    POSITION_CLOSED,
    POSITION_OPEN,
    SIDE_CHOICES,
    SIGNAL_STATUS_CHOICES,
    SIGNAL_PENDING,
)


class ExecutionAccount(models.Model):
    """Per-user execution desk account linked to one BrokerConnection."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_accounts",
    )
    slug = models.SlugField(max_length=64)
    label = models.CharField(max_length=128)
    broker_connection = models.ForeignKey(
        BrokerConnection,
        on_delete=models.PROTECT,
        related_name="execution_accounts",
    )
    is_enabled = models.BooleanField(default=True)
    dry_run = models.BooleanField(
        default=True,
        help_text="When true, journal actions but do not send live orders.",
    )
    max_open_positions = models.PositiveSmallIntegerField(default=DEFAULT_MAX_OPEN_POSITIONS)
    max_dollar_exposure = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=DEFAULT_MAX_EXPOSURE_USD,
    )
    max_loss_per_position_usd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=DEFAULT_MAX_LOSS_PER_POSITION_USD,
    )
    breakeven_ratchet_enabled = models.BooleanField(default=False)
    breakeven_trigger_gain_pct = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("15"),
        help_text="Move stop to entry after unrealized gain reaches this percent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"],
                name="unique_execution_account_slug_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.slug}"


class ExecutionAgentToken(models.Model):
    """Personal access token for user's MCP agents (shown once at creation)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_agent_tokens",
    )
    label = models.CharField(max_length=128)
    token_prefix = models.CharField(max_length=16, db_index=True)
    token_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ExecutionOAuthClient(models.Model):
    """Registered OAuth client (per user) for third-party MCP agents."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_oauth_clients",
    )
    name = models.CharField(max_length=128)
    client_id = models.CharField(max_length=64, unique=True, db_index=True)
    client_secret_hash = models.CharField(max_length=64)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ExecutionOAuthCode(models.Model):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    client = models.ForeignKey(
        ExecutionOAuthClient, on_delete=models.CASCADE, related_name="codes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_oauth_codes",
    )
    scopes = models.JSONField(default=list)
    code_challenge = models.CharField(max_length=128)
    code_challenge_method = models.CharField(max_length=16, default="S256")
    redirect_uri = models.URLField(max_length=512)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at


class ExecutionMcpAccessGrant(models.Model):
    """Issued OAuth access token (hash only)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_mcp_grants",
    )
    client = models.ForeignKey(
        ExecutionOAuthClient, on_delete=models.CASCADE, related_name="grants"
    )
    access_token_hash = models.CharField(max_length=64, db_index=True)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class HarnessSignal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="harness_signals",
    )
    ref_id = models.CharField(max_length=128, db_index=True)
    execution_account = models.ForeignKey(
        ExecutionAccount,
        on_delete=models.PROTECT,
        related_name="signals",
    )
    market = models.CharField(max_length=16, choices=MARKET_CHOICES, default="options")
    symbol = models.CharField(max_length=64, help_text="Ticker or Kalshi market ticker.")
    side = models.CharField(max_length=8, choices=SIDE_CHOICES, default="buy")
    option_type = models.CharField(max_length=4, blank=True)
    strike = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    expiration = models.DateField(null=True, blank=True)
    entry_rule = models.JSONField(default=dict)
    stop_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    stop_loss_pct = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    targets = models.JSONField(default=list)
    quantity = models.PositiveIntegerField(default=1)
    signal_expires_at = models.DateTimeField(null=True, blank=True)
    time_exit_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=SIGNAL_STATUS_CHOICES,
        default=SIGNAL_PENDING,
        db_index=True,
    )
    reject_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    last_mark_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    last_tick_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "ref_id"],
                name="unique_harness_ref_id_per_user",
            )
        ]

    def __str__(self):
        return self.ref_id

    def is_expired(self) -> bool:
        if self.signal_expires_at and timezone.now() >= self.signal_expires_at:
            return True
        return False

    def save(self, *args, **kwargs):
        if self.execution_account_id and not self.user_id:
            self.user_id = self.execution_account.user_id
        super().save(*args, **kwargs)


class HarnessPosition(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="harness_positions",
    )
    signal = models.OneToOneField(
        HarnessSignal, on_delete=models.CASCADE, related_name="position"
    )
    execution_account = models.ForeignKey(
        ExecutionAccount, on_delete=models.PROTECT, related_name="positions"
    )
    quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField()
    average_entry_price = models.DecimalField(max_digits=12, decimal_places=4)
    current_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    unrealized_pnl = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    stop_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    targets = models.JSONField(default=list)
    status = models.CharField(max_length=16, default=POSITION_OPEN, db_index=True)
    breakeven_armed = models.BooleanField(default=False)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opened_at"]


class HarnessOrder(models.Model):
    signal = models.ForeignKey(
        HarnessSignal, on_delete=models.CASCADE, related_name="orders"
    )
    purpose = models.CharField(max_length=16)
    limit_price = models.DecimalField(max_digits=12, decimal_places=4)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=16, default=ORDER_WORKING)
    broker_order_id = models.CharField(max_length=128, blank=True)
    filled_quantity = models.PositiveIntegerField(default=0)
    filled_avg_price = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    dry_run = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class HarnessJournal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="harness_journal",
        null=True,
        blank=True,
    )
    execution_account = models.ForeignKey(
        ExecutionAccount,
        on_delete=models.CASCADE,
        related_name="journal",
        null=True,
        blank=True,
    )
    signal = models.ForeignKey(
        HarnessSignal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal",
    )
    action = models.CharField(max_length=64)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
