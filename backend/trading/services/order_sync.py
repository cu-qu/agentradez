"""Keep resting broker orders in sync with Trade / Position records."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from trading.models import (
    BrokerConnection,
    BrokerOrder,
    Decision,
    Notification,
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
    OrderFill,
    TERMINAL_UNFILLED_STATUSES,
    get_broker_client,
    option_pnl,
)
from trading.services.decisions import record_activity
from trading.services.performance import refresh_account_and_platform_pnl
from trading.services.tier_rules import snapshot_tier

logger = logging.getLogger(__name__)


def _orders_to_reconcile():
    return (
        BrokerOrder.objects.filter(side=BrokerOrder.Side.BUY)
        .exclude(status=BrokerOrder.Status.FILLED)
        .select_related(
            "trade",
            "trade__signal",
            "trade__strategy",
            "trade__investment_tier",
            "trade__user",
            "broker_connection",
        )
    )


def _fill_from_row(row, fallback_qty=1, fallback_price=Decimal("0")) -> OrderFill:
    qty = int(row.get("filled_quantity") or 0)
    if qty < 1:
        qty = int(row.get("quantity") or fallback_qty or 1)
    price = Decimal(
        str(row.get("filled_avg_price") or row.get("average_price") or fallback_price or 0)
    )
    return OrderFill(
        broker_order_id=str(row.get("broker_order_id") or ""),
        status=str(row.get("status") or "filled"),
        filled_quantity=qty,
        filled_avg_price=price,
    )


def restore_working_trade(trade: Trade) -> bool:
    """Fix trades that were marked cancelled while the broker order is still live."""
    if Position.objects.filter(trade=trade).exists():
        return False
    if trade.status in {
        Trade.Status.OPEN,
        Trade.Status.PARTIALLY_CLOSED,
        Trade.Status.CLOSED,
    }:
        return False
    changed = False
    updates = []
    if trade.status != Trade.Status.PENDING:
        trade.status = Trade.Status.PENDING
        updates.append("status")
        changed = True
    if trade.closed_at is not None:
        trade.closed_at = None
        updates.append("closed_at")
        changed = True
    if trade.remaining_quantity == 0 and trade.entry_quantity:
        trade.remaining_quantity = trade.entry_quantity
        updates.append("remaining_quantity")
        changed = True
    if updates:
        updates.append("updated_at")
        trade.save(update_fields=updates)

    for event in trade.events.filter(event_type=TradeEvent.EventType.UNFILLED):
        event.event_type = TradeEvent.EventType.SUBMITTED
        event.quantity = trade.entry_quantity
        event.notes = "Limit order is live at the broker."
        event.save(update_fields=["event_type", "quantity", "notes"])
        changed = True

    for decision in SignalDecision.objects.filter(
        trade=trade, outcome=SignalDecision.Outcome.SKIPPED
    ):
        _mark_decision_entered(decision, trade, waiting=True)
        changed = True
    return changed


def _mark_decision_entered(decision: SignalDecision, trade: Trade, waiting: bool = False) -> None:
    decision.outcome = SignalDecision.Outcome.ENTERED
    decision.skip_reason = ""
    decision.notes = (
        "Limit order placed; waiting for fill."
        if waiting
        else "Limit order filled at the broker."
    )
    decision.trade = trade
    decision.save(update_fields=["outcome", "skip_reason", "notes", "trade"])
    ticker = trade.ticker
    qty = trade.remaining_quantity or trade.entry_quantity
    price = trade.entry_price
    title = f"{'Placed' if waiting else 'Filled'} {ticker}"
    if waiting:
        summary = (
            f"Acted. Limit buy for {qty} {ticker} at {price} was placed "
            f"and is waiting to fill."
        )
    else:
        summary = f"Acted. Limit buy for {qty} {ticker} filled at {price}."
    for log in Decision.objects.filter(signal_decision=decision):
        log.action = Decision.Action.ENTER
        log.outcome = Decision.Outcome.ACTED
        log.reason_code = Decision.Reason.TIER_SIZE
        log.title = title[:128]
        log.summary = summary
        log.trade = trade
        log.save(
            update_fields=[
                "action",
                "outcome",
                "reason_code",
                "title",
                "summary",
                "trade",
            ]
        )
        for note in Notification.objects.filter(decision=log):
            note.kind = Notification.Kind.ENTRY
            note.title = title[:128]
            note.body = summary[:255]
            note.trade = trade
            note.save(update_fields=["kind", "title", "body", "trade"])


@transaction.atomic
def _promote_filled_order(order: BrokerOrder, fill) -> bool:
    trade = order.trade
    qty = fill.filled_quantity
    price = Decimal(str(fill.filled_avg_price or trade.entry_price or 0))
    now = timezone.now()
    if Position.objects.filter(trade=trade, status=Position.Status.OPEN).exists():
        if order.status != BrokerOrder.Status.FILLED:
            order.status = BrokerOrder.Status.FILLED
            order.filled_quantity = qty
            order.filled_avg_price = price
            order.save(update_fields=["status", "filled_quantity", "filled_avg_price"])
            return True
        return False
    restore_working_trade(trade)

    order.status = (
        BrokerOrder.Status.FILLED
        if fill.status != "partial"
        else BrokerOrder.Status.PARTIAL
    )
    order.filled_quantity = qty
    order.filled_avg_price = price
    if fill.broker_order_id and not order.broker_order_id:
        order.broker_order_id = fill.broker_order_id
        order.save(
            update_fields=[
                "status",
                "filled_quantity",
                "filled_avg_price",
                "broker_order_id",
            ]
        )
    else:
        order.save(update_fields=["status", "filled_quantity", "filled_avg_price"])

    trade.status = Trade.Status.OPEN
    trade.entry_price = price
    trade.entry_quantity = qty
    trade.remaining_quantity = qty
    trade.closed_at = None
    trade.save(
        update_fields=[
            "status",
            "entry_price",
            "entry_quantity",
            "remaining_quantity",
            "closed_at",
            "updated_at",
        ]
    )

    if not Position.objects.filter(trade=trade).exists():
        Position.objects.create(
            user=trade.user,
            trade=trade,
            broker_connection=order.broker_connection,
            ticker=trade.ticker,
            option_type=trade.option_type,
            strike=trade.strike,
            expiration=trade.expiration,
            quantity=qty,
            average_entry_price=price,
            current_price=price,
            unrealized_pnl=option_pnl(price, price, qty),
            status=Position.Status.OPEN,
            opened_at=now,
        )

    if not trade.events.filter(event_type=TradeEvent.EventType.ENTRY).exists():
        event = TradeEvent.objects.create(
            trade=trade,
            event_type=TradeEvent.EventType.ENTRY,
            quantity=qty,
            price=price,
            notes="Filled at the broker.",
        )
        title = f"Filled {trade.ticker}"
        summary = f"Acted. Limit buy for {qty} {trade.ticker} filled at {price}."
        record_activity(
            user=trade.user,
            action=Decision.Action.ENTER,
            outcome=Decision.Outcome.ACTED,
            title=title,
            summary=summary,
            reason_code=Decision.Reason.TIER_SIZE,
            strategy=trade.strategy,
            investment_tier=trade.investment_tier,
            signal=trade.signal,
            trade=trade,
            trade_event=event,
            quantity=qty,
            price=price,
            broker_account_id=trade.broker_account_id,
        )

    for decision in SignalDecision.objects.filter(
        Q(trade=trade) | Q(signal=trade.signal, user=trade.user)
    ):
        if decision.outcome != SignalDecision.Outcome.ENTERED or decision.skip_reason:
            _mark_decision_entered(decision, trade)

    refresh_account_and_platform_pnl(trade.user)
    return True


@transaction.atomic
def _cancel_working_order(order: BrokerOrder, fill) -> bool:
    trade = order.trade
    if (
        trade.status == Trade.Status.CANCELLED
        and order.status in {BrokerOrder.Status.CANCELLED, BrokerOrder.Status.REJECTED}
        and trade.remaining_quantity == 0
        and not Position.objects.filter(trade=trade).exists()
    ):
        return False
    order.status = (
        BrokerOrder.Status.REJECTED
        if fill.status == "rejected"
        else BrokerOrder.Status.CANCELLED
    )
    order.filled_quantity = fill.filled_quantity or 0
    order.save(update_fields=["status", "filled_quantity"])

    trade.status = Trade.Status.CANCELLED
    trade.remaining_quantity = 0
    trade.closed_at = timezone.now()
    trade.save(update_fields=["status", "remaining_quantity", "closed_at", "updated_at"])

    if not trade.events.filter(event_type=TradeEvent.EventType.UNFILLED).exists():
        event = TradeEvent.objects.create(
            trade=trade,
            event_type=TradeEvent.EventType.UNFILLED,
            quantity=0,
            price=trade.entry_price,
            notes="Resting limit was cancelled without a fill.",
        )
        title = f"Unfilled {trade.ticker}"
        summary = (
            f"Passed. The resting buy for {trade.ticker} was cancelled without a fill."
        )
        record_activity(
            user=trade.user,
            action=Decision.Action.SKIP,
            outcome=Decision.Outcome.PASSED,
            title=title,
            summary=summary,
            reason_code=Decision.Reason.UNFILLED,
            strategy=trade.strategy,
            investment_tier=trade.investment_tier,
            signal=trade.signal,
            trade=trade,
            trade_event=event,
            quantity=trade.entry_quantity,
            price=trade.entry_price,
            broker_account_id=trade.broker_account_id,
        )
    return True


def _reconcile_order(order: BrokerOrder) -> bool:
    trade = order.trade
    if Position.objects.filter(trade=trade, status=Position.Status.OPEN).exists():
        return False
    client = get_broker_client(order.broker_connection)
    try:
        fill = client.get_order(
            order.broker_order_id,
            quantity=order.quantity,
            limit_price=trade.entry_price,
        )
    except BrokerError:
        logger.exception(
            "Could not refresh working order %s for trade %s",
            order.broker_order_id,
            trade.pk,
        )
        if order.status == BrokerOrder.Status.SUBMITTED or trade.status == Trade.Status.PENDING:
            return restore_working_trade(trade)
        return False

    if fill is None:
        if order.status == BrokerOrder.Status.SUBMITTED or trade.status == Trade.Status.PENDING:
            return restore_working_trade(trade)
        return False

    if fill.filled_quantity >= 1:
        return _promote_filled_order(order, fill)
    if fill.status in TERMINAL_UNFILLED_STATUSES:
        return _cancel_working_order(order, fill)
    return restore_working_trade(trade)


def _find_openable_trade(user, row) -> Trade | None:
    qs = Trade.objects.filter(
        user=user,
        ticker__iexact=str(row.get("ticker") or ""),
        status__in={Trade.Status.PENDING, Trade.Status.CANCELLED},
    ).order_by("-entered_at")
    option_type = str(row.get("option_type") or "").lower()
    if option_type:
        qs = qs.filter(option_type=option_type)
    if row.get("strike") is not None:
        qs = qs.filter(strike=row["strike"])
    if row.get("expiration"):
        qs = qs.filter(expiration=row["expiration"])
    return qs.first()


@transaction.atomic
def _open_trade_from_broker_fill(connection: BrokerConnection, row: dict) -> bool:
    ticker = str(row.get("ticker") or "").upper()
    option_type = str(row.get("option_type") or "call").lower()
    strike = row.get("strike")
    expiration = row.get("expiration")
    qty = int(row.get("filled_quantity") or row.get("quantity") or 0)
    price = Decimal(str(row.get("filled_avg_price") or row.get("average_price") or 0))
    if qty < 1 or not ticker or strike is None or expiration is None:
        return False
    if Position.objects.filter(
        user=connection.user,
        ticker__iexact=ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        status=Position.Status.OPEN,
    ).exists():
        return False

    assignment = (
        UserStrategyAssignment.objects.filter(user=connection.user, is_active=True)
        .select_related("strategy", "investment_tier")
        .first()
    )
    if assignment is None:
        return False
    signal = (
        Signal.objects.filter(
            strategy=assignment.strategy,
            ticker__iexact=ticker,
            option_type=option_type,
            strike=strike,
            expiration=expiration,
        )
        .order_by("-created_at")
        .first()
    )
    if signal is None:
        return False

    now = timezone.now()
    account_id = (connection.broker_account_id or "").strip()
    trade = Trade.objects.create(
        user=connection.user,
        signal=signal,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        broker_connection=connection,
        broker_account_id=account_id,
        ticker=ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        status=Trade.Status.OPEN,
        entry_price=price,
        entry_quantity=qty,
        remaining_quantity=qty,
        tier_rules_snapshot=snapshot_tier(assignment.investment_tier),
        entered_at=now,
    )
    TradeEvent.objects.create(
        trade=trade,
        event_type=TradeEvent.EventType.ENTRY,
        quantity=qty,
        price=price,
        notes="Filled at the broker.",
    )
    BrokerOrder.objects.create(
        trade=trade,
        broker_connection=connection,
        broker_order_id=str(row.get("broker_order_id") or ""),
        side=BrokerOrder.Side.BUY,
        status=BrokerOrder.Status.FILLED,
        quantity=qty,
        filled_quantity=qty,
        filled_avg_price=price,
    )
    current = Decimal(str(row.get("current_price") or price))
    Position.objects.create(
        user=connection.user,
        trade=trade,
        broker_connection=connection,
        ticker=ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        quantity=qty,
        average_entry_price=price,
        current_price=current,
        unrealized_pnl=option_pnl(price, current, qty),
        status=Position.Status.OPEN,
        opened_at=now,
    )
    decision = SignalDecision.objects.filter(signal=signal, user=connection.user).first()
    if decision:
        _mark_decision_entered(decision, trade)
    title = f"Filled {ticker}"
    summary = f"Acted. Limit buy for {qty} {ticker} filled at {price}."
    record_activity(
        user=connection.user,
        action=Decision.Action.ENTER,
        outcome=Decision.Outcome.ACTED,
        title=title,
        summary=summary,
        reason_code=Decision.Reason.TIER_SIZE,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        signal=signal,
        signal_decision=decision,
        trade=trade,
        quantity=qty,
        price=price,
        broker_account_id=account_id,
    )
    refresh_account_and_platform_pnl(connection.user)
    return True


def apply_broker_fill(connection: BrokerConnection, row: dict) -> bool:
    """Open or promote a local trade to match a filled broker buy-to-open."""
    status = str(row.get("status") or "")
    filled = int(row.get("filled_quantity") or 0)
    if filled < 1 and status not in FILLED_ORDER_STATUSES:
        return False
    qty = filled if filled >= 1 else int(row.get("quantity") or 0)
    if qty < 1:
        return False
    side = str(row.get("side") or "buy").lower()
    effect = str(row.get("position_effect") or "open").lower()
    if side and side != "buy":
        return False
    if effect and effect not in {"open", ""}:
        return False

    order_id = str(row.get("broker_order_id") or "").strip()
    if order_id:
        existing = (
            BrokerOrder.objects.filter(broker_order_id=order_id)
            .select_related("trade", "broker_connection")
            .first()
        )
        if existing:
            return _promote_filled_order(
                existing,
                _fill_from_row(row, existing.quantity, existing.trade.entry_price),
            )

    trade = _find_openable_trade(connection.user, row)
    if trade is not None:
        order = trade.orders.filter(side=BrokerOrder.Side.BUY).order_by("-id").first()
        if order is None:
            order = BrokerOrder.objects.create(
                trade=trade,
                broker_connection=connection,
                broker_order_id=order_id,
                side=BrokerOrder.Side.BUY,
                status=BrokerOrder.Status.SUBMITTED,
                quantity=qty,
                filled_quantity=0,
                filled_avg_price=trade.entry_price,
            )
        return _promote_filled_order(
            order, _fill_from_row(row, trade.entry_quantity, trade.entry_price)
        )
    return _open_trade_from_broker_fill(connection, row)


def _import_connection_fills(connection: BrokerConnection) -> int:
    try:
        client = get_broker_client(connection)
        orders = client.list_option_orders()
        positions = client.list_open_option_positions()
    except BrokerError:
        logger.exception("Could not import broker fills for connection %s", connection.pk)
        return 0
    updated = 0
    for row in orders:
        try:
            if apply_broker_fill(connection, row):
                updated += 1
        except Exception:  # noqa: BLE001
            logger.exception("Failed importing broker order %s", row.get("broker_order_id"))
    for row in positions:
        try:
            if apply_broker_fill(connection, row):
                updated += 1
        except Exception:  # noqa: BLE001
            logger.exception("Failed importing broker position %s", row.get("ticker"))
    return updated


def reconcile_working_orders() -> int:
    updated = 0
    for order in _orders_to_reconcile():
        try:
            if _reconcile_order(order):
                updated += 1
        except Exception:  # noqa: BLE001 — isolate one bad order from the batch
            logger.exception(
                "Failed reconciling working order %s",
                order.pk,
            )
    for connection in BrokerConnection.objects.filter(is_deleted=False):
        try:
            updated += _import_connection_fills(connection)
        except Exception:  # noqa: BLE001
            logger.exception("Failed importing fills for connection %s", connection.pk)
    return updated
