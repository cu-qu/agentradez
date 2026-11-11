from accounts.models import User
from django.utils import timezone

from execution.constants import ORDER_WORKING, POSITION_OPEN, SIGNAL_OPEN, SIGNAL_PENDING, SIGNAL_WORKING_ENTRY
from execution.models import ExecutionAccount, HarnessOrder, HarnessJournal, HarnessPosition, HarnessSignal
from execution.services.adapters import desk_adapter_for


def _serialize_signal(signal: HarnessSignal) -> dict:
    return {
        "ref_id": signal.ref_id,
        "status": signal.status,
        "symbol": signal.symbol,
        "market": signal.market,
        "quantity": signal.quantity,
        "entry_rule": signal.entry_rule,
        "stop_price": str(signal.stop_price) if signal.stop_price is not None else None,
        "targets": signal.targets,
        "last_mark_price": str(signal.last_mark_price) if signal.last_mark_price is not None else None,
        "last_tick_at": signal.last_tick_at.isoformat() if signal.last_tick_at else None,
        "account_slug": signal.execution_account.slug,
    }


def status_payload(user: User, account_slug: str | None = None) -> dict:
    signals = HarnessSignal.objects.filter(
        user=user,
        status__in=(SIGNAL_PENDING, SIGNAL_WORKING_ENTRY, SIGNAL_OPEN),
    )
    if account_slug:
        signals = signals.filter(execution_account__slug=account_slug)

    positions = HarnessPosition.objects.filter(user=user, status=POSITION_OPEN)
    if account_slug:
        positions = positions.filter(execution_account__slug=account_slug)

    working_orders = HarnessOrder.objects.filter(status=ORDER_WORKING, signal__user=user)
    if account_slug:
        working_orders = working_orders.filter(signal__execution_account__slug=account_slug)

    journal_qs = HarnessJournal.objects.filter(user=user).select_related("signal")[:30]
    if account_slug:
        journal_qs = journal_qs.filter(execution_account__slug=account_slug)

    recent_journal = [
        {
            "action": row.action,
            "ref_id": row.signal.ref_id if row.signal_id else None,
            "detail": row.detail,
            "at": row.created_at.isoformat(),
        }
        for row in journal_qs
    ]

    return {
        "as_of": timezone.now().isoformat(),
        "open_signals": [_serialize_signal(s) for s in signals.select_related("execution_account")[:100]],
        "open_positions": [
            {
                "ref_id": p.signal.ref_id,
                "symbol": p.signal.symbol,
                "quantity": p.remaining_quantity,
                "entry": str(p.average_entry_price),
                "mark": str(p.current_price) if p.current_price is not None else None,
                "unrealized_pnl": str(p.unrealized_pnl),
                "stop_price": str(p.stop_price) if p.stop_price is not None else None,
            }
            for p in positions.select_related("signal")[:100]
        ],
        "working_orders": [
            {
                "ref_id": o.signal.ref_id,
                "purpose": o.purpose,
                "limit_price": str(o.limit_price),
                "quantity": o.quantity,
                "broker_order_id": o.broker_order_id or None,
                "dry_run": o.dry_run,
            }
            for o in working_orders.select_related("signal")[:100]
        ],
        "recent_actions": recent_journal,
    }


def list_accounts_payload(user: User) -> dict:
    rows = []
    for account in ExecutionAccount.objects.filter(user=user, is_enabled=True).select_related(
        "broker_connection"
    ):
        adapter = desk_adapter_for(account)
        for snap in adapter.snapshot_accounts():
            rows.append(
                {
                    "account_slug": snap.account_slug,
                    "label": snap.label,
                    "broker": snap.broker,
                    "broker_account_id": snap.broker_account_id,
                    "equity": str(snap.equity) if snap.equity is not None else None,
                    "buying_power": str(snap.buying_power) if snap.buying_power is not None else None,
                    "option_level": snap.option_level,
                    "trading_enabled": snap.trading_enabled,
                    "dry_run": snap.dry_run,
                }
            )
    return {"accounts": rows, "count": len(rows)}
