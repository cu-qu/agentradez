from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand

from trading.constants import (
    SIGNAL_SOURCE_X,
    STRATEGY_COPY_TRADE,
    STRATEGY_RESEARCH_BREAKTHROUGH,
    STRATEGY_TYPE_COPY_TRADE,
    STRATEGY_TYPE_RESEARCH_BREAKTHROUGH,
    STRATEGY_VISIBILITY_PUBLIC,
)
from trading.models import (
    InvestmentTier,
    PlatformStats,
    ResearchWatchConfig,
    Strategy,
    XAccountSource,
)

DEFAULT_TIERS = [
    {
        "slug": "conservative",
        "name": "Conservative",
        "description": (
            "Tight slippage, smaller size, faster time exits. "
            "Accounts too small for the risk percent still take 1 contract when the premium is affordable."
        ),
        "is_default": False,
        "sort_order": 1,
        "max_entry_slippage_pct": "15.00",
        "max_entry_slippage_pct_min": "15.00",
        "max_risk_per_trade_pct": "0.75",
        "max_risk_per_trade_pct_min": "0.50",
        "max_open_positions": 3,
        "take_profit_rules": [
            {
                "pct_of_position": "50",
                "gain_pct": "50",
                "gain_pct_min": "50",
                "gain_pct_max": "60",
            },
            {
                "pct_of_position": "50",
                "gain_pct": "100",
                "gain_pct_min": "100",
                "gain_pct_max": "120",
            },
        ],
        "hard_stop_pct": "40.00",
        "force_exit_time_et": time(15, 30),
        "max_hold_trading_days": 3,
        "daily_loss_limit_pct": "2.00",
        "daily_loss_limit_pct_min": "2.00",
    },
    {
        "slug": "balanced",
        "name": "Balanced",
        "description": (
            "Default tier. Moderate slippage, size, and hold time. "
            "Accounts too small for the risk percent still take 1 contract when the premium is affordable."
        ),
        "is_default": True,
        "sort_order": 2,
        "max_entry_slippage_pct": "25.00",
        "max_entry_slippage_pct_min": "20.00",
        "max_risk_per_trade_pct": "1.25",
        "max_risk_per_trade_pct_min": "0.75",
        "max_open_positions": 5,
        "take_profit_rules": [
            {
                "pct_of_position": "50",
                "gain_pct": "60",
                "gain_pct_min": "60",
                "gain_pct_max": "80",
            },
            {
                "pct_of_position": "50",
                "gain_pct": "140",
                "gain_pct_min": "140",
                "gain_pct_max": "160",
            },
        ],
        "hard_stop_pct": "50.00",
        "force_exit_time_et": time(15, 45),
        "max_hold_trading_days": 4,
        "daily_loss_limit_pct": "3.50",
        "daily_loss_limit_pct_min": "3.00",
    },
    {
        "slug": "aggressive",
        "name": "Aggressive",
        "description": (
            "Wider entries, larger size, scaled take-profits with a runner. "
            "Accounts too small for the risk percent still take 1 contract when the premium is affordable."
        ),
        "is_default": False,
        "sort_order": 3,
        "max_entry_slippage_pct": "30.00",
        "max_entry_slippage_pct_min": "30.00",
        "max_risk_per_trade_pct": "2.00",
        "max_risk_per_trade_pct_min": "1.25",
        "max_open_positions": 7,
        "take_profit_rules": [
            {
                "pct_of_position": "40",
                "gain_pct": "70",
                "gain_pct_min": "70",
                "gain_pct_max": "70",
            },
            {
                "pct_of_position": "30",
                "gain_pct": "120",
                "gain_pct_min": "120",
                "gain_pct_max": "120",
            },
            {
                "pct_of_position": "30",
                "is_runner": True,
            },
        ],
        "hard_stop_pct": "55.00",
        "force_exit_time_et": time(15, 50),
        "max_hold_trading_days": 5,
        "daily_loss_limit_pct": "5.00",
        "daily_loss_limit_pct_min": "4.50",
    },
]


class Command(BaseCommand):
    help = "Seed investment tiers, Copy Trade, and Research / Breakthrough."

    def handle(self, *args, **options):
        for payload in DEFAULT_TIERS:
            slug = payload["slug"]
            InvestmentTier.objects.update_or_create(slug=slug, defaults=payload)
            self.stdout.write(f"Tier {slug} ready.")

        strategy, _ = Strategy.objects.update_or_create(
            slug=STRATEGY_COPY_TRADE,
            defaults={
                "name": "Copy Trade",
                "description": (
                    "Copies option trades from a configured source (X today; "
                    "chat groups later) and distributes them as signals to assigned "
                    "users using each account's tier rules."
                ),
                "strategy_type": STRATEGY_TYPE_COPY_TRADE,
                "signal_source": SIGNAL_SOURCE_X,
                "visibility": STRATEGY_VISIBILITY_PUBLIC,
                "is_active": True,
            },
        )
        handle = (getattr(settings, "X_COPY_TRADE_HANDLE", "") or "").lstrip("@").strip().lower()
        existing = strategy.x_sources.order_by("id").first()
        if existing is None:
            XAccountSource.objects.create(
                strategy=strategy,
                handle=handle or "configure-me",
                display_name=handle or "Copy Trade X account",
                is_active=bool(handle),
            )
            if handle:
                self.stdout.write(f"X watcher @{handle} ready.")
            else:
                self.stdout.write("X watcher placeholder ready (set X_COPY_TRADE_HANDLE).")
        else:
            if handle and existing.handle in {"", "configure-me"}:
                existing.handle = handle
                existing.display_name = existing.display_name or handle
                existing.is_active = True
                existing.save()
            strategy.x_sources.exclude(pk=existing.pk).update(is_active=False)
            self.stdout.write(f"X watcher @{existing.handle} ready.")

        research, _ = Strategy.objects.update_or_create(
            slug=STRATEGY_RESEARCH_BREAKTHROUGH,
            defaults={
                "name": "Research / Breakthrough",
                "description": (
                    "Configurable catalyst strategy: add companies, set sectors and "
                    "event types, then trade confirmed research, product, or deal news. "
                    "Does not copy another trader."
                ),
                "strategy_type": STRATEGY_TYPE_RESEARCH_BREAKTHROUGH,
                "visibility": STRATEGY_VISIBILITY_PUBLIC,
                "is_active": True,
            },
        )
        ResearchWatchConfig.objects.get_or_create(strategy=research)
        self.stdout.write(
            "Research / Breakthrough ready (configure sectors, keywords, and companies)."
        )
        PlatformStats.load()
        self.stdout.write(self.style.SUCCESS("Trading reference data seeded."))
