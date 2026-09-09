from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from trading.models import (
    AccountTradingState,
    BrokerOrder,
    Position,
    Trade,
    TradeEvent,
)
from trading.services.brokers import BrokerError, OptionQuote, OrderFill, get_broker_client, option_pnl
from trading.services.decisions import record_daily_pause_activity, record_exit_activity
from trading.services.performance import refresh_account_and_platform_pnl
from trading.services.tier_rules import (
    gain_pct,
    is_expiration_day,
    leg_trigger_gain,
    next_take_profit_leg,
    quantity_for_leg,
    should_hard_stop,
    should_time_exit,
)

logger = logging.getLogger(__name__)


def _rules(trade: Trade) -> dict:
    return trade.tier_rules_snapshot or {}


def _event_type_for_reason(reason: str) -> str:
    mapping = {
        "take_profit": TradeEvent.EventType.TAKE_PROFIT,
        "stop_loss": TradeEvent.EventType.STOP_LOSS,
        "time_exit": TradeEvent.EventType.TIME_EXIT,
        "expiration_exit": TradeEvent.EventType.EXPIRATION_EXIT,
        "force_exit": TradeEvent.EventType.FORCE_EXIT,
    }
    return mapping.get(reason, TradeEvent.EventType.FORCE_EXIT)


@transaction.atomic
def close_quantity(
    position: Position,
    quantity: int,
    price: Decimal,
    reason: str,
    notes: str = "",
    extra_context: dict | None = None,
) -> TradeEvent | None:
    if quantity <= 0 or position.quantity <= 0:
        return None
    quantity = min(quantity, position.quantity)
    trade = position.trade
    rules = _rules(trade)
    client = get_broker_client(position.broker_connection, quote_override=price)
    try:
        fill = client.sell_to_close(
            position.ticker,
            position.option_type,
            position.strike,
            position.expiration,
            quantity,
            price,
        )
    except BrokerError as exc:
        if reason != "expiration_exit" and not is_expiration_day(position):
            raise
        fill = OrderFill(
            broker_order_id="",
            status="filled",
            filled_quantity=quantity,
            filled_avg_price=Decimal(str(price or 0)),
        )
        notes = (notes or f"Settled locally after broker close failed: {exc}")[:255]
    fill_price = fill.filled_avg_price
    pnl = option_pnl(trade.entry_price, fill_price, fill.filled_quantity)
    event = TradeEvent.objects.create(
        trade=trade,
        event_type=_event_type_for_reason(reason),
        quantity=fill.filled_quantity,
        price=fill_price,
        realized_pnl=pnl,
        notes=notes,
    )
    BrokerOrder.objects.create(
        trade=trade,
        broker_connection=position.broker_connection,
        broker_order_id=fill.broker_order_id,
        side=BrokerOrder.Side.SELL,
        status=BrokerOrder.Status.FILLED,
        quantity=fill.filled_quantity,
        filled_quantity=fill.filled_quantity,
        filled_avg_price=fill_price,
    )

    closed = trade.closed_quantity + fill.filled_quantity
    weighted = Decimal("0")
    if trade.average_exit_price and trade.closed_quantity:
        weighted = trade.average_exit_price * Decimal(trade.closed_quantity)
    weighted += fill_price * Decimal(fill.filled_quantity)
    trade.closed_quantity = closed
    trade.average_exit_price = (weighted / Decimal(closed)) if closed else fill_price
    trade.realized_pnl = trade.realized_pnl + pnl
    trade.remaining_quantity = max(0, trade.remaining_quantity - fill.filled_quantity)
    if reason == "take_profit":
        trade.tp_stage = trade.tp_stage + 1

    position.quantity = max(0, position.quantity - fill.filled_quantity)
    position.current_price = fill_price
    now = timezone.now()
    if position.quantity == 0:
        position.status = Position.Status.CLOSED
        position.unrealized_pnl = Decimal("0.00")
        position.closed_at = now
        trade.status = Trade.Status.CLOSED
        trade.closed_at = now
        trade.remaining_quantity = 0
    else:
        position.unrealized_pnl = option_pnl(
            trade.entry_price, fill_price, position.quantity
        )
        trade.status = Trade.Status.PARTIALLY_CLOSED

    position.save()
    trade.save()

    state, _ = AccountTradingState.objects.get_or_create(user=trade.user)
    state.daily_realized_pnl = state.daily_realized_pnl + pnl
    state.lifetime_realized_pnl = state.lifetime_realized_pnl + pnl
    state.save(update_fields=["daily_realized_pnl", "lifetime_realized_pnl", "updated_at"])

    context = {
        "fill_price": str(fill_price),
        "realized_pnl": str(pnl),
        "quantity": fill.filled_quantity,
        "gain_pct": str(gain_pct(trade.entry_price, fill_price)),
        "tier_name": trade.investment_tier.name,
        "tier_slug": trade.investment_tier.slug,
        "strategy_name": trade.strategy.name,
        "hard_stop_pct": str(rules.get("hard_stop_pct") or "0"),
        "max_hold_trading_days": rules.get("max_hold_trading_days"),
        "force_exit_time_et": rules.get("force_exit_time_et"),
        "remaining_quantity": trade.remaining_quantity,
    }
    if extra_context:
        context.update(extra_context)
    record_exit_activity(
        trade=trade, trade_event=event, reason=reason, context=context
    )
    refresh_account_and_platform_pnl(trade.user)
    return event


def _exit_limit(market: OptionQuote, position: Position, now: datetime | None = None) -> Decimal:
    if is_expiration_day(position, now=now):
        return market.last_day_exit
    return market.mark


def mark_to_market(position: Position, price: Decimal) -> None:
    position.current_price = price
    position.unrealized_pnl = option_pnl(
        position.average_entry_price, price, position.quantity
    )
    position.save(update_fields=["current_price", "unrealized_pnl", "updated_at"])


def manage_position(position: Position, now: datetime | None = None, quote: Decimal | None = None) -> str | None:
    if position.status != Position.Status.OPEN or position.quantity <= 0:
        return None
    trade = position.trade
    rules = _rules(trade)
    client = get_broker_client(position.broker_connection, quote_override=quote)
    try:
        if quote is not None:
            market = OptionQuote(mark=Decimal(str(quote)))
        else:
            market = client.get_option_market(
                position.ticker, position.option_type, position.strike, position.expiration
            )
        price = market.mark
    except BrokerError as exc:
        due, reason = should_time_exit(position, rules, now=now)
        if due and reason == "expiration_exit":
            price = position.current_price or position.average_entry_price or Decimal("0")
            close_quantity(
                position,
                position.quantity,
                price,
                "expiration_exit",
                notes=str(exc)[:255],
                extra_context={
                    "max_hold_trading_days": rules.get("max_hold_trading_days"),
                    "force_exit_time_et": rules.get("force_exit_time_et"),
                },
            )
            return "expiration_exit"
        logger.warning(
            "No live quote for position %s (%s %s %s %s): %s",
            position.pk,
            position.ticker,
            position.option_type,
            position.strike,
            position.expiration,
            exc,
        )
        return None
    mark_to_market(position, price)
    position.refresh_from_db()
    exit_price = _exit_limit(market, position, now=now)

    hard_stop = Decimal(str(rules.get("hard_stop_pct") or "0"))
    if should_hard_stop(position.average_entry_price, price, hard_stop):
        close_quantity(
            position,
            position.quantity,
            exit_price,
            "stop_loss",
            extra_context={"hard_stop_pct": str(hard_stop)},
        )
        return "stop_loss"

    due, reason = should_time_exit(position, rules, now=now)
    if due:
        position.refresh_from_db()
        if position.status == Position.Status.OPEN:
            close_quantity(
                position,
                position.quantity,
                exit_price,
                reason,
                extra_context={
                    "max_hold_trading_days": rules.get("max_hold_trading_days"),
                    "force_exit_time_et": rules.get("force_exit_time_et"),
                },
            )
            return reason

    leg = next_take_profit_leg(rules, trade.tp_stage)
    if not leg:
        return None
    trigger = leg_trigger_gain(leg)
    if trigger is None:
        return None
    if gain_pct(position.average_entry_price, price) >= trigger:
        qty = quantity_for_leg(leg, trade.entry_quantity, position.quantity)
        if qty:
            close_quantity(
                position,
                qty,
                exit_price,
                "take_profit",
                extra_context={
                    "trigger_gain_pct": str(trigger),
                    "pct_of_position": str(leg.get("pct_of_position") or ""),
                    "tp_stage": trade.tp_stage,
                },
            )
            return "take_profit"
        trade.tp_stage = trade.tp_stage + 1
        trade.save(update_fields=["tp_stage", "updated_at"])
    return None


def monitor_open_positions(now: datetime | None = None) -> int:
    from trading.services.order_sync import reconcile_working_orders

    reconcile_working_orders()
    count = 0
    for position in Position.objects.filter(status=Position.Status.OPEN).select_related(
        "trade",
        "trade__investment_tier",
        "trade__strategy",
        "trade__signal",
        "broker_connection",
        "user",
    ):
        try:
            manage_position(position, now=now)
            count += 1
        except Exception:  # noqa: BLE001 — isolate one bad position from the batch
            logger.exception("Failed managing position %s", position.pk)
    return count


def force_expiration_exits(now: datetime | None = None) -> int:
    closed = 0
    for position in Position.objects.filter(status=Position.Status.OPEN).select_related(
        "trade", "broker_connection"
    ):
        due, reason = should_time_exit(position, _rules(position.trade), now=now)
        if due and reason == "expiration_exit":
            try:
                client = get_broker_client(position.broker_connection)
                market = client.get_option_market(
                    position.ticker,
                    position.option_type,
                    position.strike,
                    position.expiration,
                )
                price = _exit_limit(market, position, now=now)
            except BrokerError:
                price = position.current_price or position.average_entry_price or Decimal("0")
            try:
                close_quantity(position, position.quantity, price, "expiration_exit")
                closed += 1
            except Exception:  # noqa: BLE001
                logger.exception("Failed expiration exit for position %s", position.pk)
    return closed


def check_daily_loss_limits() -> int:
    paused = 0
    open_users = (
        Position.objects.filter(status=Position.Status.OPEN)
        .values_list("user_id", flat=True)
        .distinct()
    )
    from trading.models import BrokerConnection, UserStrategyAssignment

    user_ids = set(open_users) | set(
        UserStrategyAssignment.objects.filter(is_active=True).values_list("user_id", flat=True)
    )
    for user_id in user_ids:
        assignment = (
            UserStrategyAssignment.objects.filter(user_id=user_id, is_active=True)
            .select_related("investment_tier", "strategy")
            .first()
        )
        if not assignment:
            continue
        state, _ = AccountTradingState.objects.get_or_create(user_id=user_id)
        if state.is_paused_daily_loss:
            continue
        connection = BrokerConnection.objects.filter(user_id=user_id, is_deleted=False).first()
        equity = connection.last_equity if connection and connection.last_equity else Decimal("100000")
        unrealized = Position.objects.filter(
            user_id=user_id, status=Position.Status.OPEN
        ).aggregate(total=Sum("unrealized_pnl"))["total"] or Decimal("0")
        daily_pnl = state.daily_realized_pnl + unrealized
        limit = equity * (assignment.investment_tier.daily_loss_limit_pct / Decimal("100"))
        if daily_pnl <= -limit:
            state.is_paused_daily_loss = True
            state.paused_at = timezone.now()
            state.save(update_fields=["is_paused_daily_loss", "paused_at", "updated_at"])
            record_daily_pause_activity(
                user=assignment.user,
                assignment=assignment,
                context={
                    "daily_pnl": str(daily_pnl),
                    "equity": str(equity),
                    "daily_loss_limit_pct": str(
                        assignment.investment_tier.daily_loss_limit_pct
                    ),
                    "tier_name": assignment.investment_tier.name,
                    "tier_slug": assignment.investment_tier.slug,
                    "strategy_name": assignment.strategy.name,
                },
            )
            paused += 1
    return paused
