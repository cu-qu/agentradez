"""Minute rule evaluation — no LLM calls."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from execution.constants import (
    ORDER_ENTRY,
    ORDER_EXIT,
    ORDER_FILLED,
    ORDER_WORKING,
    POSITION_CLOSED,
    POSITION_OPEN,
    SIGNAL_CANCELLED,
    SIGNAL_CLOSED,
    SIGNAL_EXPIRED,
    SIGNAL_OPEN,
    SIGNAL_PENDING,
    SIGNAL_REJECTED,
    SIGNAL_WORKING_ENTRY,
)
from execution.models import (
    ExecutionAccount,
    HarnessOrder,
    HarnessPosition,
    HarnessSignal,
)
from execution.services.adapters import desk_adapter_for
from execution.services.caps import CapViolation, check_caps
from execution.services.platform_caps import clamp_account_caps
from trading.services.broker_limits import broker_paused, pause_broker
from execution.services.harness_client import FILLED_STATUSES, TERMINAL_UNFILLED, WORKING_STATUSES, market_multiplier
from execution.services.journal import journal
from trading.services.brokers import BrokerError
logger = logging.getLogger(__name__)


def _global_dry_run_default() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "EXECUTION_DRY_RUN_DEFAULT", True))


def _effective_dry_run(account: ExecutionAccount) -> bool:
    """Live orders only when global EXECUTION_DRY_RUN_DEFAULT is off and account.dry_run is off."""
    if _global_dry_run_default():
        return True
    return bool(account.dry_run)


def _entry_limit_price(signal: HarnessSignal) -> Decimal | None:
    rule = signal.entry_rule or {}
    raw = rule.get("price")
    if raw is None:
        return None
    return Decimal(str(raw))


def _should_submit_entry(signal: HarnessSignal, mark: Decimal) -> bool:
    limit = _entry_limit_price(signal)
    if limit is None:
        return True
    rule_type = (signal.entry_rule or {}).get("type", "limit")
    side = signal.side
    if rule_type == "limit":
        if side == "buy":
            return mark <= limit
        return mark >= limit
    return True


def _resolve_stop(signal: HarnessSignal, entry: Decimal, mark: Decimal) -> Decimal | None:
    if signal.stop_price is not None:
        return signal.stop_price
    if signal.stop_loss_pct is not None and entry > 0:
        pct = Decimal(str(signal.stop_loss_pct)) / Decimal("100")
        return entry * (Decimal("1") - pct)
    return None


def _place_entry(signal: HarnessSignal, limit_price: Decimal) -> HarnessOrder | None:
    account = signal.execution_account
    dry_run = _effective_dry_run(account)
    try:
        check_caps(
            account,
            market=signal.market,
            additional_contracts=1,
            entry_limit_price=limit_price,
            quantity=signal.quantity,
        )
    except CapViolation as exc:
        signal.status = SIGNAL_REJECTED
        signal.reject_reason = str(exc)
        signal.save(update_fields=["status", "reject_reason", "updated_at"])
        journal("entry_rejected_caps", execution_account=account, signal=signal, detail={"error": str(exc)})
        return None

    order = HarnessOrder.objects.create(
        signal=signal,
        purpose=ORDER_ENTRY,
        limit_price=limit_price,
        quantity=signal.quantity,
        status=ORDER_WORKING,
        dry_run=dry_run,
    )
    signal.status = SIGNAL_WORKING_ENTRY
    signal.save(update_fields=["status", "updated_at"])

    if dry_run:
        order.status = ORDER_FILLED
        order.filled_quantity = signal.quantity
        order.filled_avg_price = limit_price
        order.broker_order_id = f"dry-run-entry-{order.pk}"
        order.save()
        _open_position_from_fill(signal, limit_price, signal.quantity)
        journal(
            "entry_dry_run_filled",
            execution_account=account,
            signal=signal,
            detail={"limit": str(limit_price), "qty": signal.quantity},
        )
        return order

    adapter = desk_adapter_for(account)
    try:
        fill = adapter.harness_client().place_limit_entry(signal, signal.quantity, limit_price)
    except BrokerError as exc:
        order.status = "rejected"
        order.save(update_fields=["status", "updated_at"])
        signal.status = SIGNAL_REJECTED
        signal.reject_reason = str(exc)[:255]
        signal.save(update_fields=["status", "reject_reason", "updated_at"])
        journal("entry_rejected_broker", execution_account=account, signal=signal, detail={"error": str(exc)})
        return order

    order.broker_order_id = fill.broker_order_id
    order.filled_quantity = fill.filled_quantity
    order.filled_avg_price = fill.filled_avg_price
    if fill.status in FILLED_STATUSES or fill.filled_quantity >= signal.quantity:
        order.status = ORDER_FILLED
        order.save()
        _open_position_from_fill(signal, fill.filled_avg_price or limit_price, fill.filled_quantity)
        journal("entry_filled", execution_account=account, signal=signal, detail={"order_id": fill.broker_order_id})
    elif fill.status in WORKING_STATUSES:
        order.save()
        journal("entry_submitted", execution_account=account, signal=signal, detail={"order_id": fill.broker_order_id})
    else:
        order.status = "rejected"
        order.save()
        signal.status = SIGNAL_REJECTED
        signal.reject_reason = f"Unexpected order status: {fill.status}"
        signal.save(update_fields=["status", "reject_reason", "updated_at"])
    return order


def _open_position_from_fill(signal: HarnessSignal, entry_price: Decimal, quantity: int) -> None:
    signal.status = SIGNAL_OPEN
    signal.save(update_fields=["status", "updated_at"])
    HarnessPosition.objects.update_or_create(
        signal=signal,
        defaults={
            "user": signal.user,
            "execution_account": signal.execution_account,
            "quantity": quantity,
            "remaining_quantity": quantity,
            "average_entry_price": entry_price,
            "stop_price": signal.stop_price,
            "targets": signal.targets,
            "status": POSITION_OPEN,
            "opened_at": timezone.now(),
        },
    )


def _reconcile_working_entry(signal: HarnessSignal, order: HarnessOrder) -> None:
    if order.status == ORDER_FILLED:
        return
    account = signal.execution_account
    if _effective_dry_run(account):
        return
    adapter = desk_adapter_for(account)
    try:
        fill = adapter.harness_client().fetch_order(order.broker_order_id)
    except BrokerError:
        return
    if fill is None:
        return
    order.filled_quantity = fill.filled_quantity
    order.filled_avg_price = fill.filled_avg_price
    if fill.status in FILLED_STATUSES or fill.filled_quantity >= order.quantity:
        order.status = ORDER_FILLED
        order.save()
        _open_position_from_fill(signal, fill.filled_avg_price or order.limit_price, fill.filled_quantity)
        journal("entry_filled_reconcile", execution_account=account, signal=signal, detail={})
    elif fill.status in TERMINAL_UNFILLED:
        order.status = "cancelled"
        order.save()
        signal.status = SIGNAL_CANCELLED
        signal.save(update_fields=["status", "updated_at"])
        journal("entry_unfilled", execution_account=account, signal=signal, detail={"status": fill.status})


def _exit_position(signal: HarnessSignal, position: HarnessPosition, quantity: int, limit_price: Decimal, reason: str):
    account = signal.execution_account
    dry_run = _effective_dry_run(account)
    order = HarnessOrder.objects.create(
        signal=signal,
        purpose=ORDER_EXIT,
        limit_price=limit_price,
        quantity=quantity,
        status=ORDER_WORKING,
        dry_run=dry_run,
    )
    if dry_run:
        order.status = ORDER_FILLED
        order.filled_quantity = quantity
        order.filled_avg_price = limit_price
        order.broker_order_id = f"dry-run-exit-{order.pk}"
        order.save()
        _apply_exit_fill(position, signal, quantity, limit_price)
        journal("exit_dry_run", execution_account=account, signal=signal, detail={"reason": reason, "qty": quantity})
        return

    adapter = desk_adapter_for(account)
    try:
        fill = adapter.harness_client().place_limit_exit(signal, quantity, limit_price)
    except BrokerError as exc:
        journal("exit_rejected", execution_account=account, signal=signal, detail={"error": str(exc), "reason": reason})
        return

    order.broker_order_id = fill.broker_order_id
    order.filled_quantity = fill.filled_quantity
    order.filled_avg_price = fill.filled_avg_price
    if fill.status in FILLED_STATUSES or fill.filled_quantity >= quantity:
        order.status = ORDER_FILLED
        order.save()
        _apply_exit_fill(position, signal, fill.filled_quantity, fill.filled_avg_price or limit_price)
        journal("exit_filled", execution_account=account, signal=signal, detail={"reason": reason})
    else:
        order.save()
        journal("exit_submitted", execution_account=account, signal=signal, detail={"reason": reason})


def _apply_exit_fill(position: HarnessPosition, signal: HarnessSignal, quantity: int, price: Decimal) -> None:
    position.remaining_quantity = max(0, position.remaining_quantity - quantity)
    if position.remaining_quantity == 0:
        position.status = POSITION_CLOSED
        position.closed_at = timezone.now()
        signal.status = SIGNAL_CLOSED
        signal.save(update_fields=["status", "updated_at"])
    position.save()


def _manage_open(signal: HarnessSignal, position: HarnessPosition, mark: Decimal) -> None:
    entry = position.average_entry_price
    position.current_price = mark
    mult = market_multiplier(signal.market)
    position.unrealized_pnl = (mark - entry) * mult * Decimal(position.remaining_quantity)
    position.save(update_fields=["current_price", "unrealized_pnl", "updated_at"])

    account = signal.execution_account
    stop = position.stop_price or _resolve_stop(signal, entry, mark)
    if (
        account.breakeven_ratchet_enabled
        and not position.breakeven_armed
        and entry > 0
        and mark >= entry * (Decimal("1") + account.breakeven_trigger_gain_pct / Decimal("100"))
    ):
        position.stop_price = entry
        position.breakeven_armed = True
        position.save(update_fields=["stop_price", "breakeven_armed", "updated_at"])
        journal("breakeven_ratchet", execution_account=account, signal=signal, detail={"stop": str(entry)})
        stop = entry

    if stop is not None and mark <= stop:
        _exit_position(signal, position, position.remaining_quantity, mark, "stop")
        return

    if signal.time_exit_at and timezone.now() >= signal.time_exit_at:
        _exit_position(signal, position, position.remaining_quantity, mark, "time_exit")
        return

    for leg in position.targets or []:
        target_price = leg.get("price")
        if target_price is None:
            continue
        target_price = Decimal(str(target_price))
        if mark >= target_price:
            leg_qty = int(leg.get("quantity") or leg.get("qty") or 0)
            if leg_qty <= 0:
                pct = Decimal(str(leg.get("pct_of_position") or leg.get("pct") or "0"))
                leg_qty = max(1, int(position.quantity * pct / Decimal("100")))
            leg_qty = min(leg_qty, position.remaining_quantity)
            if leg_qty > 0:
                _exit_position(signal, position, leg_qty, mark, "target")
                position.targets = [row for row in position.targets if row is not leg]
                position.save(update_fields=["targets", "updated_at"])
                break


def evaluate_signal(signal: HarnessSignal) -> None:
    if signal.status in (SIGNAL_CANCELLED, SIGNAL_CLOSED, SIGNAL_EXPIRED, SIGNAL_REJECTED):
        return
    if signal.is_expired() and signal.status in (SIGNAL_PENDING, SIGNAL_WORKING_ENTRY):
        signal.status = SIGNAL_EXPIRED
        signal.save(update_fields=["status", "updated_at"])
        journal("signal_expired", execution_account=signal.execution_account, signal=signal, detail={})
        return

    account = signal.execution_account
    adapter = desk_adapter_for(account)
    try:
        quote = adapter.harness_client().get_quote(signal)
        mark = quote.mark
    except BrokerError as exc:
        logger.warning("quote_failed signal=%s err=%s", signal.ref_id, exc)
        return

    signal.last_mark_price = mark
    signal.last_tick_at = timezone.now()
    signal.save(update_fields=["last_mark_price", "last_tick_at", "updated_at"])

    if signal.status == SIGNAL_PENDING:
        limit = _entry_limit_price(signal) or mark
        if _should_submit_entry(signal, mark):
            _place_entry(signal, limit)
        return

    if signal.status == SIGNAL_WORKING_ENTRY:
        order = (
            signal.orders.filter(purpose=ORDER_ENTRY, status=ORDER_WORKING)
            .order_by("-id")
            .first()
        )
        if order:
            _reconcile_working_entry(signal, order)
        return

    if signal.status == SIGNAL_OPEN:
        position = HarnessPosition.objects.filter(signal=signal, status=POSITION_OPEN).first()
        if position:
            _manage_open(signal, position, mark)


def evaluate_all_signals() -> int:
    count = 0
    qs = HarnessSignal.objects.filter(
        status__in=(SIGNAL_PENDING, SIGNAL_WORKING_ENTRY, SIGNAL_OPEN)
    ).select_related(
        "execution_account",
        "execution_account__broker_connection",
        "user",
    )
    by_connection: dict[int, list[HarnessSignal]] = {}
    for signal in qs.iterator():
        conn_id = signal.execution_account.broker_connection_id
        by_connection.setdefault(conn_id, []).append(signal)

    for conn_id, batch in by_connection.items():
        if broker_paused(conn_id):
            continue
        for signal in batch:
            clamp_account_caps(signal.execution_account)
            try:
                evaluate_signal(signal)
                count += 1
            except Exception as exc:
                logger.exception(
                    "evaluate_signal failed ref_id=%s user=%s",
                    signal.ref_id,
                    signal.user_id,
                )
                pause_broker(conn_id, exc)
    return count
