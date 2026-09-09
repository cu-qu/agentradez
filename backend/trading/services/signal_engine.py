from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from billing.services.entitlements import user_can_trade
from trading.models import (
    AccountTradingState,
    BrokerConnection,
    BrokerOrder,
    Position,
    Signal,
    SignalDecision,
    Trade,
    TradeEvent,
    UserStrategyAssignment,
)
from trading.services.brokers import (
    BrokerError,
    FILLED_ORDER_STATUSES,
    TERMINAL_UNFILLED_STATUSES,
    WORKING_ORDER_STATUSES,
    get_broker_client,
    option_pnl,
)
from trading.services.decisions import entry_context, record_signal_activity
from trading.services.performance import refresh_account_and_platform_pnl
from trading.services.tier_rules import (
    size_position,
    slippage_exceeded,
    snapshot_tier,
)


def get_or_create_state(user) -> AccountTradingState:
    state, _ = AccountTradingState.objects.get_or_create(user=user)
    return state


def _open_position_count(user) -> int:
    open_positions = Position.objects.filter(
        user=user, status=Position.Status.OPEN
    ).count()
    pending_entries = Trade.objects.filter(
        user=user, status=Trade.Status.PENDING
    ).count()
    return open_positions + pending_entries


def _unrealized_total(user) -> Decimal:
    total = Position.objects.filter(user=user, status=Position.Status.OPEN).aggregate(
        total=Sum("unrealized_pnl")
    )["total"]
    return total or Decimal("0.00")


def evaluate_assignment(
    signal: Signal,
    assignment: UserStrategyAssignment,
    live_price: Decimal,
    equity: Decimal,
    open_count: int,
    state: AccountTradingState,
    buying_power: Decimal | None = None,
) -> tuple[str, str, int, dict]:
    """Return (outcome, skip_reason, quantity, size_context)."""
    tier = assignment.investment_tier
    if state.is_paused_daily_loss:
        return SignalDecision.Outcome.SKIPPED, SignalDecision.SkipReason.PAUSED, 0, {}
    daily_pnl = state.daily_realized_pnl + _unrealized_total(assignment.user)
    loss_limit = equity * (tier.daily_loss_limit_pct / Decimal("100"))
    if daily_pnl <= -loss_limit:
        return SignalDecision.Outcome.SKIPPED, SignalDecision.SkipReason.DAILY_LOSS_LIMIT, 0, {}
    if open_count >= tier.max_open_positions:
        return SignalDecision.Outcome.SKIPPED, SignalDecision.SkipReason.MAX_OPEN_POSITIONS, 0, {}
    if slippage_exceeded(signal.suggested_entry_price, live_price, tier.max_entry_slippage_pct):
        return SignalDecision.Outcome.SKIPPED, SignalDecision.SkipReason.SLIPPAGE, 0, {}
    sized = size_position(
        equity,
        tier.max_risk_per_trade_pct,
        live_price,
        tier.hard_stop_pct,
        buying_power=buying_power if buying_power is not None else equity,
    )
    size_context = {
        "size_mode": sized.mode,
        "contract_cost": str(sized.contract_cost),
        "risk_quantity": sized.risk_quantity,
        "max_affordable": sized.max_affordable,
        "buying_power": str(sized.buying_power),
    }
    if sized.quantity < 1:
        return (
            SignalDecision.Outcome.SKIPPED,
            SignalDecision.SkipReason.SIZE_ZERO,
            0,
            size_context,
        )
    return SignalDecision.Outcome.ENTERED, "", sized.quantity, size_context


def _persist_signal_decision(
    *,
    signal: Signal,
    assignment: UserStrategyAssignment,
    outcome: str,
    skip_reason: str = "",
    notes: str = "",
    trade=None,
    context: dict | None = None,
) -> SignalDecision:
    row = SignalDecision.objects.create(
        signal=signal,
        user=assignment.user,
        assignment=assignment,
        investment_tier=assignment.investment_tier,
        outcome=outcome,
        skip_reason=skip_reason,
        trade=trade,
        notes=(notes or "")[:255],
    )
    payload = dict(context or {})
    payload.setdefault("broker_account_id", payload.get("broker_account_id") or "")
    if notes:
        payload.setdefault("notes", notes)
    record_signal_activity(
        row, signal=signal, assignment=assignment, context=payload
    )
    return row


def _broker_order_status(status: str) -> str:
    value = (status or "").lower()
    if value in {"cancelled", "canceled"}:
        return BrokerOrder.Status.CANCELLED
    if value in {"rejected", "failed"}:
        return BrokerOrder.Status.REJECTED
    if value in {"partial", "partially_filled"}:
        return BrokerOrder.Status.PARTIAL
    if value == "filled":
        return BrokerOrder.Status.FILLED
    return BrokerOrder.Status.SUBMITTED


def _is_filled_entry(fill) -> bool:
    return fill.status in FILLED_ORDER_STATUSES and fill.filled_quantity >= 1


def _is_working_entry(fill) -> bool:
    if _is_filled_entry(fill):
        return False
    if fill.status in TERMINAL_UNFILLED_STATUSES:
        return False
    return fill.status in WORKING_ORDER_STATUSES or not fill.status


def _existing_entry_decision(signal: Signal, assignment: UserStrategyAssignment, fill) -> SignalDecision | None:
    existing = SignalDecision.objects.filter(signal=signal, user=assignment.user).first()
    if existing:
        return existing
    if not fill.broker_order_id:
        return None
    existing_order = (
        BrokerOrder.objects.filter(broker_order_id=fill.broker_order_id)
        .select_related("trade")
        .first()
    )
    if existing_order:
        return SignalDecision.objects.filter(trade=existing_order.trade).first()
    return None


@transaction.atomic
def record_unfilled_entry(
    signal: Signal,
    assignment: UserStrategyAssignment,
    connection: BrokerConnection,
    account_id: str,
    fill,
    quantity: int,
    limit_price: Decimal,
    submitted_at=None,
    closed_at=None,
    notes: str = "",
) -> SignalDecision:
    """Persist a broker order that was rejected or cancelled without a fill."""
    existing = _existing_entry_decision(signal, assignment, fill)
    if existing:
        return existing

    now = timezone.now()
    entered_at = submitted_at or now
    finished_at = closed_at or now
    order_status = _broker_order_status(fill.status)
    note = (notes or f"Robinhood order {order_status}; 0 contracts filled.")[:255]
    trade = Trade.objects.create(
        user=assignment.user,
        signal=signal,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        broker_connection=connection,
        broker_account_id=account_id,
        ticker=signal.ticker,
        option_type=signal.option_type,
        strike=signal.strike,
        expiration=signal.expiration,
        status=Trade.Status.CANCELLED,
        entry_price=limit_price,
        entry_quantity=quantity,
        remaining_quantity=0,
        tier_rules_snapshot=snapshot_tier(assignment.investment_tier),
        entered_at=entered_at,
        closed_at=finished_at,
    )
    TradeEvent.objects.create(
        trade=trade,
        event_type=TradeEvent.EventType.UNFILLED,
        quantity=0,
        price=limit_price,
        notes=note,
    )
    order = BrokerOrder.objects.create(
        trade=trade,
        broker_connection=connection,
        broker_order_id=fill.broker_order_id,
        side=BrokerOrder.Side.BUY,
        status=order_status,
        quantity=quantity,
        filled_quantity=fill.filled_quantity or 0,
        filled_avg_price=fill.filled_avg_price,
    )
    if submitted_at:
        BrokerOrder.objects.filter(pk=order.pk).update(submitted_at=submitted_at)
    return _persist_signal_decision(
        signal=signal,
        assignment=assignment,
        outcome=SignalDecision.Outcome.SKIPPED,
        skip_reason=SignalDecision.SkipReason.UNFILLED,
        notes=note,
        trade=trade,
        context=entry_context(
            signal=signal,
            assignment=assignment,
            quote=limit_price,
            quantity=quantity,
            extra={
                "broker_account_id": account_id,
                "limit_price": str(limit_price),
                "notes": note,
            },
        ),
    )


@transaction.atomic
def record_working_entry(
    signal: Signal,
    assignment: UserStrategyAssignment,
    connection: BrokerConnection,
    account_id: str,
    fill,
    quantity: int,
    limit_price: Decimal,
    submitted_at=None,
    notes: str = "",
) -> SignalDecision:
    """Persist a resting limit that the broker accepted but has not filled yet."""
    existing = _existing_entry_decision(signal, assignment, fill)
    if existing:
        return existing

    now = timezone.now()
    entered_at = submitted_at or now
    note = (notes or "Limit order is live at the broker.")[:255]
    trade = Trade.objects.create(
        user=assignment.user,
        signal=signal,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        broker_connection=connection,
        broker_account_id=account_id,
        ticker=signal.ticker,
        option_type=signal.option_type,
        strike=signal.strike,
        expiration=signal.expiration,
        status=Trade.Status.PENDING,
        entry_price=limit_price,
        entry_quantity=quantity,
        remaining_quantity=quantity,
        tier_rules_snapshot=snapshot_tier(assignment.investment_tier),
        entered_at=entered_at,
    )
    TradeEvent.objects.create(
        trade=trade,
        event_type=TradeEvent.EventType.SUBMITTED,
        quantity=quantity,
        price=limit_price,
        notes=note,
    )
    order = BrokerOrder.objects.create(
        trade=trade,
        broker_connection=connection,
        broker_order_id=fill.broker_order_id,
        side=BrokerOrder.Side.BUY,
        status=BrokerOrder.Status.SUBMITTED,
        quantity=quantity,
        filled_quantity=fill.filled_quantity or 0,
        filled_avg_price=fill.filled_avg_price,
    )
    if submitted_at:
        BrokerOrder.objects.filter(pk=order.pk).update(submitted_at=submitted_at)
    return _persist_signal_decision(
        signal=signal,
        assignment=assignment,
        outcome=SignalDecision.Outcome.ENTERED,
        notes=note,
        trade=trade,
        context=entry_context(
            signal=signal,
            assignment=assignment,
            quote=limit_price,
            quantity=quantity,
            extra={
                "broker_account_id": account_id,
                "limit_price": str(limit_price),
                "awaiting_fill": True,
                "notes": note,
            },
        ),
    )


@transaction.atomic
def apply_decision(
    signal: Signal,
    assignment: UserStrategyAssignment,
    connection: BrokerConnection | None,
    live_price: Decimal | None = None,
) -> SignalDecision:
    existing = SignalDecision.objects.filter(signal=signal, user=assignment.user).first()
    if existing:
        return existing

    user = assignment.user
    if not user_can_trade(user):
        return _persist_signal_decision(
            signal=signal,
            assignment=assignment,
            outcome=SignalDecision.Outcome.SKIPPED,
            skip_reason=SignalDecision.SkipReason.SUBSCRIPTION_REQUIRED,
            context=entry_context(signal=signal, assignment=assignment),
        )

    state = get_or_create_state(user)
    if connection is None:
        return _persist_signal_decision(
            signal=signal,
            assignment=assignment,
            outcome=SignalDecision.Outcome.SKIPPED,
            skip_reason=SignalDecision.SkipReason.NO_BROKER,
            context=entry_context(
                signal=signal,
                assignment=assignment,
                extra={
                    "broker_account_id": (assignment.broker_account_id or "").strip()
                },
            ),
        )

    bound_account = (assignment.broker_account_id or "").strip()
    selected_account = (connection.broker_account_id or "").strip()
    if bound_account and not selected_account:
        return _persist_signal_decision(
            signal=signal,
            assignment=assignment,
            outcome=SignalDecision.Outcome.SKIPPED,
            skip_reason=SignalDecision.SkipReason.NO_BROKER,
            context=entry_context(
                signal=signal,
                assignment=assignment,
                extra={"broker_account_id": bound_account, "trading_off": True},
            ),
        )
    if bound_account and selected_account and bound_account != selected_account:
        return _persist_signal_decision(
            signal=signal,
            assignment=assignment,
            outcome=SignalDecision.Outcome.SKIPPED,
            skip_reason=SignalDecision.SkipReason.WRONG_ACCOUNT,
            context=entry_context(
                signal=signal,
                assignment=assignment,
                extra={"broker_account_id": bound_account},
            ),
        )

    account_id = bound_account or selected_account
    client = get_broker_client(connection, quote_override=live_price)
    try:
        if live_price is not None:
            quote = Decimal(str(live_price))
        else:
            quote = client.get_option_quote(
                signal.ticker, signal.option_type, signal.strike, signal.expiration
            )
        capital = client.get_capital()
        equity = capital.equity
        buying_power = capital.buying_power
        connection.last_equity = equity
        connection.save(update_fields=["last_equity", "updated_at"])
        outcome, skip_reason, qty, size_context = evaluate_assignment(
            signal,
            assignment,
            quote,
            equity,
            _open_position_count(user),
            state,
            buying_power=buying_power,
        )
        if outcome == SignalDecision.Outcome.SKIPPED:
            return _persist_signal_decision(
                signal=signal,
                assignment=assignment,
                outcome=outcome,
                skip_reason=skip_reason,
                context=entry_context(
                    signal=signal,
                    assignment=assignment,
                    quote=quote,
                    equity=equity,
                    buying_power=buying_power,
                    open_count=_open_position_count(user),
                    state=state,
                    quantity=qty,
                    extra={"broker_account_id": account_id, **size_context},
                ),
            )

        fill = client.buy_to_open(
            signal.ticker,
            signal.option_type,
            signal.strike,
            signal.expiration,
            qty,
            quote,
        )
        if not _is_filled_entry(fill):
            if _is_working_entry(fill):
                return record_working_entry(
                    signal,
                    assignment,
                    connection,
                    account_id,
                    fill,
                    quantity=qty,
                    limit_price=quote,
                )
            return record_unfilled_entry(
                signal,
                assignment,
                connection,
                account_id,
                fill,
                quantity=qty,
                limit_price=quote,
            )
    except BrokerError as exc:
        return _persist_signal_decision(
            signal=signal,
            assignment=assignment,
            outcome=SignalDecision.Outcome.SKIPPED,
            skip_reason=SignalDecision.SkipReason.BROKER_ERROR,
            notes=str(exc)[:255],
            context=entry_context(
                signal=signal,
                assignment=assignment,
                quote=live_price,
                extra={
                    "broker_account_id": account_id,
                    "notes": str(exc)[:255],
                },
            ),
        )

    now = timezone.now()
    trade = Trade.objects.create(
        user=user,
        signal=signal,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        broker_connection=connection,
        broker_account_id=account_id,
        ticker=signal.ticker,
        option_type=signal.option_type,
        strike=signal.strike,
        expiration=signal.expiration,
        status=Trade.Status.OPEN,
        entry_price=fill.filled_avg_price,
        entry_quantity=fill.filled_quantity,
        remaining_quantity=fill.filled_quantity,
        tier_rules_snapshot=snapshot_tier(assignment.investment_tier),
        entered_at=now,
    )
    TradeEvent.objects.create(
        trade=trade,
        event_type=TradeEvent.EventType.ENTRY,
        quantity=fill.filled_quantity,
        price=fill.filled_avg_price,
    )
    BrokerOrder.objects.create(
        trade=trade,
        broker_connection=connection,
        broker_order_id=fill.broker_order_id,
        side=BrokerOrder.Side.BUY,
        status=BrokerOrder.Status.FILLED,
        quantity=fill.filled_quantity,
        filled_quantity=fill.filled_quantity,
        filled_avg_price=fill.filled_avg_price,
    )
    Position.objects.create(
        user=user,
        trade=trade,
        broker_connection=connection,
        ticker=signal.ticker,
        option_type=signal.option_type,
        strike=signal.strike,
        expiration=signal.expiration,
        quantity=fill.filled_quantity,
        average_entry_price=fill.filled_avg_price,
        current_price=fill.filled_avg_price,
        unrealized_pnl=option_pnl(fill.filled_avg_price, fill.filled_avg_price, fill.filled_quantity),
        status=Position.Status.OPEN,
        opened_at=now,
    )
    decision = _persist_signal_decision(
        signal=signal,
        assignment=assignment,
        outcome=SignalDecision.Outcome.ENTERED,
        trade=trade,
        context=entry_context(
            signal=signal,
            assignment=assignment,
            quote=fill.filled_avg_price,
            equity=equity,
            buying_power=buying_power,
            open_count=_open_position_count(user),
            state=state,
            quantity=fill.filled_quantity,
            extra={
                "broker_account_id": account_id,
                "fill_price": str(fill.filled_avg_price),
                **size_context,
            },
        ),
    )
    refresh_account_and_platform_pnl(user)
    return decision


def process_signal(signal: Signal, live_price: Decimal | None = None) -> list[SignalDecision]:
    quote = live_price if live_price is not None else signal.quote_price
    assignments = (
        UserStrategyAssignment.objects.filter(strategy=signal.strategy, is_active=True)
        .select_related("user", "investment_tier", "strategy")
    )
    decisions = []
    for assignment in assignments:
        connection = (
            BrokerConnection.objects.filter(user=assignment.user, is_deleted=False)
            .order_by("-created_at")
            .first()
        )
        decisions.append(apply_decision(signal, assignment, connection, live_price=quote))
    signal.status = Signal.Status.PROCESSED
    signal.processed_at = timezone.now()
    signal.save(update_fields=["status", "processed_at"])
    return decisions


def _is_live_copy_signal(signal: Signal) -> bool:
    """True when this signal is still in the source's live copy window."""
    post = getattr(signal, "ingested_post", None)
    if post is None:
        return True
    source = getattr(post, "source", None)
    posted_at = getattr(post, "posted_at", None)
    if source is None or posted_at is None:
        return True
    hours = int(getattr(source, "lookback_hours", 0) or 0)
    if hours <= 0:
        return True
    if timezone.is_naive(posted_at):
        posted_at = timezone.make_aware(posted_at, timezone.utc)
    return posted_at >= timezone.now() - timedelta(hours=hours)


def process_pending_signals() -> int:
    pending = list(
        Signal.objects.filter(status=Signal.Status.PENDING)
        .select_related("strategy", "ingested_post", "ingested_post__source", "research_event")
        .order_by("created_at")
    )
    unapplied = list(
        Signal.objects.filter(status=Signal.Status.PROCESSED)
        .annotate(decision_count=Count("decisions"))
        .filter(decision_count=0)
        .select_related("strategy", "ingested_post", "ingested_post__source", "research_event")
        .order_by("created_at")
    )
    seen: set[int] = set()
    count = 0
    for signal in pending + unapplied:
        if signal.id in seen:
            continue
        seen.add(signal.id)
        if (
            signal.status == Signal.Status.PROCESSED
            and not _is_live_copy_signal(signal)
        ):
            continue
        process_signal(signal)
        count += 1
    return count
