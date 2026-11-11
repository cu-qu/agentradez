"""Per-account hard caps enforced before any order."""

from __future__ import annotations

from decimal import Decimal

from execution.constants import POSITION_OPEN, SIGNAL_OPEN, SIGNAL_WORKING_ENTRY
from execution.models import ExecutionAccount, HarnessPosition, HarnessSignal
from trading.constants import CONTRACT_MULTIPLIER


class CapViolation(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _open_position_count(account: ExecutionAccount) -> int:
    return HarnessPosition.objects.filter(
        execution_account=account, status=POSITION_OPEN
    ).count()


def _working_or_open_signals(account: ExecutionAccount) -> int:
    return HarnessSignal.objects.filter(
        execution_account=account,
        status__in=(SIGNAL_WORKING_ENTRY, SIGNAL_OPEN),
    ).count()


def _exposure_usd(account: ExecutionAccount) -> Decimal:
    total = Decimal("0")
    for pos in HarnessPosition.objects.filter(
        execution_account=account, status=POSITION_OPEN
    ):
        mark = pos.current_price or pos.average_entry_price
        total += mark * CONTRACT_MULTIPLIER * Decimal(pos.remaining_quantity)
    for sig in HarnessSignal.objects.filter(
        execution_account=account, status=SIGNAL_WORKING_ENTRY
    ):
        price = sig.entry_rule.get("price") if isinstance(sig.entry_rule, dict) else None
        if price is not None:
            total += Decimal(str(price)) * CONTRACT_MULTIPLIER * Decimal(sig.quantity)
    return total


def check_caps(
    account: ExecutionAccount,
    *,
    additional_contracts: int = 0,
    entry_limit_price: Decimal | None = None,
    quantity: int = 1,
) -> None:
    open_count = _open_position_count(account) + _working_or_open_signals(account)
    if open_count + (1 if additional_contracts else 0) > account.max_open_positions:
        raise CapViolation(
            "max_open_positions",
            f"Would exceed max open positions ({account.max_open_positions}).",
        )

    exposure = _exposure_usd(account)
    if entry_limit_price is not None:
        exposure += entry_limit_price * CONTRACT_MULTIPLIER * Decimal(quantity)
    if exposure > account.max_dollar_exposure:
        raise CapViolation(
            "max_dollar_exposure",
            f"Would exceed max dollar exposure ({account.max_dollar_exposure}).",
        )


def max_loss_for_position(
    account: ExecutionAccount, entry_price: Decimal, stop_price: Decimal | None, quantity: int
) -> Decimal | None:
    if stop_price is None:
        return None
    loss = (entry_price - stop_price) * CONTRACT_MULTIPLIER * Decimal(quantity)
    if loss < 0:
        loss = -loss
    return loss


def check_stop_within_max_loss(
    account: ExecutionAccount,
    entry_price: Decimal,
    stop_price: Decimal | None,
    quantity: int,
) -> None:
    loss = max_loss_for_position(account, entry_price, stop_price, quantity)
    if loss is not None and loss > account.max_loss_per_position_usd:
        raise CapViolation(
            "max_loss_per_position",
            f"Stop implies max loss {loss} > cap {account.max_loss_per_position_usd}.",
        )
