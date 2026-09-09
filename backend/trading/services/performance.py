from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from trading.constants import ET, PERIOD_DAILY, PERIOD_LIFETIME, PERIOD_WEEKLY
from trading.models import (
    AccountTradingState,
    PerformanceSnapshot,
    PlatformStats,
    Position,
    Trade,
    UserStrategyAssignment,
)


def scope_key(user_id, strategy_id, tier_id, period_type, period_start: date | None) -> str:
    start = period_start.isoformat() if period_start else "none"
    return f"u{user_id or 0}:s{strategy_id or 0}:t{tier_id or 0}:{period_type}:{start}"


def _week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start, end


def _upsert_snapshot(**kwargs) -> PerformanceSnapshot:
    key = kwargs.pop("scope_key")
    obj, _ = PerformanceSnapshot.objects.update_or_create(scope_key=key, defaults=kwargs)
    return obj


def _trade_stats(qs):
    agg = qs.aggregate(
        realized=Sum("realized_pnl"),
        trades=Count("id"),
        wins=Count("id", filter=Q(realized_pnl__gt=0, status=Trade.Status.CLOSED)),
        losses=Count("id", filter=Q(realized_pnl__lt=0, status=Trade.Status.CLOSED)),
    )
    return (
        agg["realized"] or Decimal("0.00"),
        agg["trades"] or 0,
        agg["wins"] or 0,
        agg["losses"] or 0,
    )


def user_unrealized(user_id: int) -> Decimal:
    total = Position.objects.filter(user_id=user_id, status=Position.Status.OPEN).aggregate(
        total=Sum("unrealized_pnl")
    )["total"]
    return total or Decimal("0.00")


def refresh_account_and_platform_pnl(user=None) -> PlatformStats:
    if user is not None:
        state, _ = AccountTradingState.objects.get_or_create(user=user)
        realized = Trade.objects.filter(user=user).aggregate(total=Sum("realized_pnl"))[
            "total"
        ] or Decimal("0.00")
        state.lifetime_realized_pnl = realized
        state.lifetime_unrealized_pnl = user_unrealized(user.id)
        state.save(
            update_fields=[
                "lifetime_realized_pnl",
                "lifetime_unrealized_pnl",
                "updated_at",
            ]
        )

    realized = Trade.objects.aggregate(total=Sum("realized_pnl"))["total"] or Decimal("0.00")
    unrealized = Position.objects.filter(status=Position.Status.OPEN).aggregate(
        total=Sum("unrealized_pnl")
    )["total"] or Decimal("0.00")
    trade_stats = Trade.objects.aggregate(
        trades=Count("id"),
        wins=Count("id", filter=Q(realized_pnl__gt=0, status=Trade.Status.CLOSED)),
        losses=Count("id", filter=Q(realized_pnl__lt=0, status=Trade.Status.CLOSED)),
    )
    users_by_tier = {}
    for row in (
        UserStrategyAssignment.objects.filter(is_active=True)
        .values("investment_tier__slug")
        .annotate(count=Count("id"))
    ):
        users_by_tier[row["investment_tier__slug"]] = row["count"]

    pnl_by_strategy = {}
    for row in Trade.objects.values("strategy__slug").annotate(total=Sum("realized_pnl")):
        pnl_by_strategy[row["strategy__slug"]] = str(row["total"] or "0.00")

    pnl_by_tier = {}
    for row in Trade.objects.values("investment_tier__slug").annotate(total=Sum("realized_pnl")):
        pnl_by_tier[row["investment_tier__slug"]] = str(row["total"] or "0.00")

    stats = PlatformStats.load()
    stats.lifetime_realized_pnl = realized
    stats.lifetime_unrealized_pnl = unrealized
    stats.trade_count = trade_stats["trades"] or 0
    stats.win_count = trade_stats["wins"] or 0
    stats.loss_count = trade_stats["losses"] or 0
    stats.active_user_count = UserStrategyAssignment.objects.filter(is_active=True).values(
        "user_id"
    ).distinct().count()
    stats.open_position_count = Position.objects.filter(status=Position.Status.OPEN).count()
    stats.users_by_tier = users_by_tier
    stats.pnl_by_strategy = pnl_by_strategy
    stats.pnl_by_tier = pnl_by_tier
    stats.save()
    return stats


def calculate_daily_performance(day: date | None = None) -> int:
    day = day or timezone.now().astimezone(ET).date()
    written = 0
    user_ids = set(
        Trade.objects.filter(entered_at__date=day).values_list("user_id", flat=True)
    ) | set(
        Position.objects.filter(status=Position.Status.OPEN).values_list("user_id", flat=True)
    ) | set(
        AccountTradingState.objects.values_list("user_id", flat=True)
    )
    for user_id in user_ids:
        qs = Trade.objects.filter(user_id=user_id, entered_at__date=day)
        realized, trades, wins, losses = _trade_stats(qs)
        closed_today = Trade.objects.filter(user_id=user_id, closed_at__date=day)
        closed_realized = closed_today.aggregate(total=Sum("realized_pnl"))["total"] or Decimal(
            "0.00"
        )
        # Daily realized should reflect P&L booked today (exits), not entries.
        if closed_today.exists():
            realized = closed_realized
            trades = closed_today.count()
            wins = closed_today.filter(realized_pnl__gt=0).count()
            losses = closed_today.filter(realized_pnl__lt=0).count()
        unrealized = user_unrealized(user_id)
        _upsert_snapshot(
            scope_key=scope_key(user_id, None, None, PERIOD_DAILY, day),
            user_id=user_id,
            period_type=PERIOD_DAILY,
            period_start=day,
            period_end=day,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            trade_count=trades,
            win_count=wins,
            loss_count=losses,
            open_position_count=Position.objects.filter(
                user_id=user_id, status=Position.Status.OPEN
            ).count(),
        )
        written += 1

        for strategy_id in (
            Trade.objects.filter(user_id=user_id)
            .values_list("strategy_id", flat=True)
            .distinct()
        ):
            s_qs = Trade.objects.filter(
                user_id=user_id, strategy_id=strategy_id, closed_at__date=day
            )
            s_realized, s_trades, s_wins, s_losses = _trade_stats(s_qs)
            _upsert_snapshot(
                scope_key=scope_key(user_id, strategy_id, None, PERIOD_DAILY, day),
                user_id=user_id,
                strategy_id=strategy_id,
                period_type=PERIOD_DAILY,
                period_start=day,
                period_end=day,
                realized_pnl=s_realized,
                unrealized_pnl=Decimal("0.00"),
                trade_count=s_trades,
                win_count=s_wins,
                loss_count=s_losses,
            )
            written += 1

        lifetime_realized = Trade.objects.filter(user_id=user_id).aggregate(
            total=Sum("realized_pnl")
        )["total"] or Decimal("0.00")
        _upsert_snapshot(
            scope_key=scope_key(user_id, None, None, PERIOD_LIFETIME, None),
            user_id=user_id,
            period_type=PERIOD_LIFETIME,
            period_start=None,
            period_end=day,
            realized_pnl=lifetime_realized,
            unrealized_pnl=unrealized,
            trade_count=Trade.objects.filter(user_id=user_id).count(),
            win_count=Trade.objects.filter(
                user_id=user_id, status=Trade.Status.CLOSED, realized_pnl__gt=0
            ).count(),
            loss_count=Trade.objects.filter(
                user_id=user_id, status=Trade.Status.CLOSED, realized_pnl__lt=0
            ).count(),
            open_position_count=Position.objects.filter(
                user_id=user_id, status=Position.Status.OPEN
            ).count(),
        )
        written += 1

    platform_realized = Trade.objects.filter(closed_at__date=day).aggregate(
        total=Sum("realized_pnl")
    )["total"] or Decimal("0.00")
    platform_unrealized = Position.objects.filter(status=Position.Status.OPEN).aggregate(
        total=Sum("unrealized_pnl")
    )["total"] or Decimal("0.00")
    _upsert_snapshot(
        scope_key=scope_key(None, None, None, PERIOD_DAILY, day),
        period_type=PERIOD_DAILY,
        period_start=day,
        period_end=day,
        realized_pnl=platform_realized,
        unrealized_pnl=platform_unrealized,
        trade_count=Trade.objects.filter(closed_at__date=day).count(),
        open_position_count=Position.objects.filter(status=Position.Status.OPEN).count(),
    )
    refresh_account_and_platform_pnl()
    return written


def calculate_weekly_performance(day: date | None = None) -> int:
    day = day or timezone.now().astimezone(ET).date()
    start, end = _week_bounds(day)
    written = 0
    user_ids = Trade.objects.filter(
        closed_at__date__gte=start, closed_at__date__lte=end
    ).values_list("user_id", flat=True).distinct()
    for user_id in user_ids:
        qs = Trade.objects.filter(
            user_id=user_id, closed_at__date__gte=start, closed_at__date__lte=end
        )
        realized, trades, wins, losses = _trade_stats(qs)
        _upsert_snapshot(
            scope_key=scope_key(user_id, None, None, PERIOD_WEEKLY, start),
            user_id=user_id,
            period_type=PERIOD_WEEKLY,
            period_start=start,
            period_end=end,
            realized_pnl=realized,
            unrealized_pnl=user_unrealized(user_id),
            trade_count=trades,
            win_count=wins,
            loss_count=losses,
        )
        written += 1

        for strategy_id in qs.values_list("strategy_id", flat=True).distinct():
            s_qs = qs.filter(strategy_id=strategy_id)
            s_realized, s_trades, s_wins, s_losses = _trade_stats(s_qs)
            _upsert_snapshot(
                scope_key=scope_key(user_id, strategy_id, None, PERIOD_WEEKLY, start),
                user_id=user_id,
                strategy_id=strategy_id,
                period_type=PERIOD_WEEKLY,
                period_start=start,
                period_end=end,
                realized_pnl=s_realized,
                trade_count=s_trades,
                win_count=s_wins,
                loss_count=s_losses,
            )
            written += 1

        for tier_id in qs.values_list("investment_tier_id", flat=True).distinct():
            t_qs = qs.filter(investment_tier_id=tier_id)
            t_realized, t_trades, t_wins, t_losses = _trade_stats(t_qs)
            _upsert_snapshot(
                scope_key=scope_key(user_id, None, tier_id, PERIOD_WEEKLY, start),
                user_id=user_id,
                investment_tier_id=tier_id,
                period_type=PERIOD_WEEKLY,
                period_start=start,
                period_end=end,
                realized_pnl=t_realized,
                trade_count=t_trades,
                win_count=t_wins,
                loss_count=t_losses,
            )
            written += 1

    _upsert_snapshot(
        scope_key=scope_key(None, None, None, PERIOD_WEEKLY, start),
        period_type=PERIOD_WEEKLY,
        period_start=start,
        period_end=end,
        realized_pnl=Trade.objects.filter(
            closed_at__date__gte=start, closed_at__date__lte=end
        ).aggregate(total=Sum("realized_pnl"))["total"]
        or Decimal("0.00"),
        trade_count=Trade.objects.filter(
            closed_at__date__gte=start, closed_at__date__lte=end
        ).count(),
    )
    written += 1
    return written


def reconcile_lifetime_pnl() -> dict:
    stats = refresh_account_and_platform_pnl()
    for state in AccountTradingState.objects.all():
        realized = Trade.objects.filter(user_id=state.user_id).aggregate(total=Sum("realized_pnl"))[
            "total"
        ] or Decimal("0.00")
        state.lifetime_realized_pnl = realized
        state.lifetime_unrealized_pnl = user_unrealized(state.user_id)
        state.save(
            update_fields=["lifetime_realized_pnl", "lifetime_unrealized_pnl", "updated_at"]
        )
        _upsert_snapshot(
            scope_key=scope_key(state.user_id, None, None, PERIOD_LIFETIME, None),
            user_id=state.user_id,
            period_type=PERIOD_LIFETIME,
            realized_pnl=realized,
            unrealized_pnl=state.lifetime_unrealized_pnl,
            trade_count=Trade.objects.filter(user_id=state.user_id).count(),
        )
    return {
        "lifetime_realized_pnl": str(stats.lifetime_realized_pnl),
        "lifetime_unrealized_pnl": str(stats.lifetime_unrealized_pnl),
    }


def tier_usage_stats() -> dict:
    stats = refresh_account_and_platform_pnl()
    return stats.users_by_tier


def personal_performance(user) -> dict:
    refresh_account_and_platform_pnl(user)
    state, _ = AccountTradingState.objects.get_or_create(user=user)
    today = timezone.now().astimezone(ET).date()
    week_start, week_end = _week_bounds(today)
    daily = Trade.objects.filter(user=user, closed_at__date=today).aggregate(
        total=Sum("realized_pnl")
    )["total"] or Decimal("0.00")
    weekly = Trade.objects.filter(
        user=user, closed_at__date__gte=week_start, closed_at__date__lte=week_end
    ).aggregate(total=Sum("realized_pnl"))["total"] or Decimal("0.00")
    by_strategy = list(
        Trade.objects.filter(user=user)
        .values("strategy_id", "strategy__slug", "strategy__name")
        .annotate(realized_pnl=Sum("realized_pnl"), trade_count=Count("id"))
    )
    by_tier = list(
        Trade.objects.filter(user=user)
        .values("investment_tier_id", "investment_tier__slug", "investment_tier__name")
        .annotate(realized_pnl=Sum("realized_pnl"), trade_count=Count("id"))
    )
    return {
        "lifetime_realized_pnl": str(state.lifetime_realized_pnl),
        "lifetime_unrealized_pnl": str(state.lifetime_unrealized_pnl),
        "lifetime_total_pnl": str(state.lifetime_realized_pnl + state.lifetime_unrealized_pnl),
        "daily_realized_pnl": str(daily),
        "weekly_realized_pnl": str(weekly),
        "is_paused_daily_loss": state.is_paused_daily_loss,
        "open_positions": Position.objects.filter(user=user, status=Position.Status.OPEN).count(),
        "closed_trades": Trade.objects.filter(user=user, status=Trade.Status.CLOSED).count(),
        "by_strategy": [
            {
                "strategy_id": row["strategy_id"],
                "slug": row["strategy__slug"],
                "name": row["strategy__name"],
                "realized_pnl": str(row["realized_pnl"] or "0.00"),
                "trade_count": row["trade_count"],
            }
            for row in by_strategy
        ],
        "by_tier": [
            {
                "investment_tier_id": row["investment_tier_id"],
                "slug": row["investment_tier__slug"],
                "name": row["investment_tier__name"],
                "realized_pnl": str(row["realized_pnl"] or "0.00"),
                "trade_count": row["trade_count"],
            }
            for row in by_tier
        ],
    }


def account_trades(user, broker_account_id: str):
    account_id = (broker_account_id or "").strip()
    qs = Trade.objects.filter(user=user)
    if account_id in ("", "default"):
        return qs.filter(Q(broker_account_id="") | Q(broker_account_id="default"))
    return qs.filter(broker_account_id=account_id)


def account_performance(user, broker_account_id: str) -> dict:
    today = timezone.now().astimezone(ET).date()
    week_start, week_end = _week_bounds(today)
    trades = account_trades(user, broker_account_id)
    open_positions = Position.objects.filter(
        user=user,
        status=Position.Status.OPEN,
        trade__in=trades,
    )
    realized = trades.aggregate(total=Sum("realized_pnl"))["total"] or Decimal("0.00")
    unrealized = open_positions.aggregate(total=Sum("unrealized_pnl"))["total"] or Decimal(
        "0.00"
    )
    daily = trades.filter(closed_at__date=today).aggregate(total=Sum("realized_pnl"))[
        "total"
    ] or Decimal("0.00")
    weekly = trades.filter(
        closed_at__date__gte=week_start, closed_at__date__lte=week_end
    ).aggregate(total=Sum("realized_pnl"))["total"] or Decimal("0.00")
    return {
        "lifetime_realized_pnl": str(realized),
        "lifetime_unrealized_pnl": str(unrealized),
        "lifetime_total_pnl": str(realized + unrealized),
        "daily_realized_pnl": str(daily),
        "weekly_realized_pnl": str(weekly),
        "open_positions": open_positions.count(),
        "closed_trades": trades.filter(status=Trade.Status.CLOSED).count(),
    }
