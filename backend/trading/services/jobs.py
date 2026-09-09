from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from trading.models import (
    AccountTradingState,
    BrokerConnection,
    Signal,
    Trade,
    UserStrategyAssignment,
)
from trading.services.brokers import get_broker_client
from trading.services.performance import refresh_account_and_platform_pnl


def reset_daily_flags() -> int:
    today = timezone.now().date()
    return AccountTradingState.objects.update(
        is_paused_daily_loss=False,
        paused_at=None,
        daily_realized_pnl=0,
        last_reset_on=today,
    )


def sync_broker_positions() -> int:
    synced = 0
    now = timezone.now()
    for connection in BrokerConnection.objects.filter(is_deleted=False):
        client = get_broker_client(connection)
        try:
            equity = client.get_equity()
            connection.last_equity = equity
            connection.last_synced_at = now
            connection.status = BrokerConnection.Status.CONNECTED
            connection.last_error = ""
            connection.save(
                update_fields=[
                    "last_equity",
                    "last_synced_at",
                    "status",
                    "last_error",
                    "updated_at",
                ]
            )
            from trading.services.order_sync import _import_connection_fills

            _import_connection_fills(connection)
            synced += 1
        except Exception as exc:  # noqa: BLE001 — isolate one bad broker from the batch
            connection.status = BrokerConnection.Status.ERROR
            connection.last_error = str(exc)[:255]
            connection.save(update_fields=["status", "last_error", "updated_at"])
    refresh_account_and_platform_pnl()
    return synced


def cleanup_old_signals_and_trades(days: int = 365) -> dict:
    cutoff = timezone.now() - timedelta(days=days)
    signals = Signal.objects.filter(
        created_at__lt=cutoff, is_archived=False, status=Signal.Status.PROCESSED
    )
    trades = Trade.objects.filter(
        created_at__lt=cutoff, is_archived=False, status=Trade.Status.CLOSED
    )
    signal_count = signals.update(is_archived=True)
    trade_count = trades.update(is_archived=True)
    return {"signals": signal_count, "trades": trade_count}


@transaction.atomic
def set_assignment(
    user,
    strategy,
    investment_tier,
    assigned_by=None,
    broker_account_id=None,
) -> UserStrategyAssignment:
    current = UserStrategyAssignment.objects.filter(user=user, is_active=True).first()
    if broker_account_id is None:
        broker_account_id = current.broker_account_id if current else ""
    broker_account_id = (broker_account_id or "").strip()
    UserStrategyAssignment.objects.filter(user=user, is_active=True).update(is_active=False)
    assignment = UserStrategyAssignment.objects.create(
        user=user,
        strategy=strategy,
        investment_tier=investment_tier,
        assigned_by=assigned_by,
        broker_account_id=broker_account_id,
        is_active=True,
    )
    if broker_account_id:
        connection = BrokerConnection.objects.filter(user=user).first()
        if connection and connection.broker_account_id != broker_account_id:
            connection.broker_account_id = broker_account_id
            connection.last_error = ""
            connection.status = BrokerConnection.Status.CONNECTED
            connection.save(
                update_fields=[
                    "broker_account_id",
                    "last_error",
                    "status",
                    "updated_at",
                ]
            )
    return assignment
