"""Platform-wide maximums applied on top of per-user execution account caps."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from execution.models import ExecutionAccount


def platform_max_open_positions() -> int:
    return int(getattr(settings, "EXECUTION_PLATFORM_MAX_OPEN_POSITIONS", 20))


def platform_max_dollar_exposure() -> Decimal:
    return Decimal(str(getattr(settings, "EXECUTION_PLATFORM_MAX_DOLLAR_EXPOSURE", "100000")))


def platform_max_loss_per_position() -> Decimal:
    return Decimal(str(getattr(settings, "EXECUTION_PLATFORM_MAX_LOSS_PER_POSITION_USD", "2500")))


def clamp_account_caps(account: ExecutionAccount) -> ExecutionAccount:
    """Return account with caps clamped in-memory (does not save)."""
    account.max_open_positions = min(
        account.max_open_positions, platform_max_open_positions()
    )
    account.max_dollar_exposure = min(
        account.max_dollar_exposure, platform_max_dollar_exposure()
    )
    account.max_loss_per_position_usd = min(
        account.max_loss_per_position_usd, platform_max_loss_per_position()
    )
    return account
