from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from trading.constants import CONTRACT_MULTIPLIER, ET
from trading.models import InvestmentTier, Position

SIZE_MODE_RISK = "risk"
SIZE_MODE_MINIMUM_CONTRACT = "minimum_contract"
SIZE_MODE_CASH_CAPPED = "cash_capped"
SIZE_MODE_UNAFFORDABLE = "unaffordable"
SIZE_MODE_INVALID = "invalid"


@dataclass(frozen=True)
class PositionSizeResult:
    quantity: int
    mode: str
    contract_cost: Decimal
    risk_quantity: int
    max_affordable: int
    risk_dollars: Decimal
    buying_power: Decimal


def snapshot_tier(tier: InvestmentTier) -> dict:
    return {
        "slug": tier.slug,
        "max_entry_slippage_pct": str(tier.max_entry_slippage_pct),
        "max_risk_per_trade_pct": str(tier.max_risk_per_trade_pct),
        "max_open_positions": tier.max_open_positions,
        "take_profit_rules": tier.take_profit_rules,
        "hard_stop_pct": str(tier.hard_stop_pct),
        "force_exit_time_et": tier.force_exit_time_et.strftime("%H:%M:%S"),
        "max_hold_trading_days": tier.max_hold_trading_days,
        "daily_loss_limit_pct": str(tier.daily_loss_limit_pct),
    }


def _d(value, default="0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def slippage_exceeded(suggested_entry, live_price, max_slippage_pct) -> bool:
    suggested_entry = _d(suggested_entry)
    live_price = _d(live_price)
    max_slippage_pct = _d(max_slippage_pct)
    if suggested_entry <= 0:
        return True
    ceiling = suggested_entry * (Decimal("1") + max_slippage_pct / Decimal("100"))
    return live_price > ceiling


def size_position(
    equity,
    risk_pct,
    entry_price,
    hard_stop_pct,
    buying_power=None,
) -> PositionSizeResult:
    """Size an options debit using the tier risk percent, with a 1-contract floor.

    Large accounts use floor(risk_dollars / max_loss_per_contract). When that
    rounds to zero, take 1 contract if the premium is affordable so a $100
    account can still enter. Never size above what buying power can pay.
    """
    equity = _d(equity)
    risk_pct = _d(risk_pct)
    entry_price = _d(entry_price)
    hard_stop_pct = _d(hard_stop_pct)
    spendable = _d(buying_power) if buying_power is not None else equity

    def _result(
        quantity: int,
        mode: str,
        *,
        contract_cost=Decimal("0"),
        risk_quantity=0,
        max_affordable=0,
        risk_dollars=Decimal("0"),
    ) -> PositionSizeResult:
        return PositionSizeResult(
            quantity=quantity,
            mode=mode,
            contract_cost=contract_cost,
            risk_quantity=risk_quantity,
            max_affordable=max_affordable,
            risk_dollars=risk_dollars,
            buying_power=spendable,
        )

    if equity <= 0 or risk_pct <= 0 or entry_price <= 0 or hard_stop_pct <= 0:
        return _result(0, SIZE_MODE_INVALID)

    contract_cost = entry_price * CONTRACT_MULTIPLIER
    max_loss_per_contract = contract_cost * (hard_stop_pct / Decimal("100"))
    if contract_cost <= 0 or max_loss_per_contract <= 0:
        return _result(0, SIZE_MODE_INVALID, contract_cost=contract_cost)

    risk_dollars = equity * (risk_pct / Decimal("100"))
    risk_quantity = int(risk_dollars / max_loss_per_contract)
    max_affordable = int(spendable / contract_cost) if spendable > 0 else 0
    target = max(risk_quantity, 1)
    quantity = min(target, max_affordable)

    if quantity < 1:
        mode = SIZE_MODE_UNAFFORDABLE
    elif quantity < risk_quantity:
        mode = SIZE_MODE_CASH_CAPPED
    elif risk_quantity < 1:
        mode = SIZE_MODE_MINIMUM_CONTRACT
    else:
        mode = SIZE_MODE_RISK
    return _result(
        quantity,
        mode,
        contract_cost=contract_cost,
        risk_quantity=risk_quantity,
        max_affordable=max_affordable,
        risk_dollars=risk_dollars,
    )


def position_size(equity, risk_pct, entry_price, hard_stop_pct, buying_power=None) -> int:
    return size_position(
        equity,
        risk_pct,
        entry_price,
        hard_stop_pct,
        buying_power=buying_power,
    ).quantity


def trading_days_between(start: date, end: date) -> int:
    """Count weekdays strictly after start through end inclusive."""
    if end <= start:
        return 0
    days = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def gain_pct(entry_price, current_price) -> Decimal:
    entry_price = _d(entry_price)
    current_price = _d(current_price)
    if entry_price <= 0:
        return Decimal("0")
    return (current_price - entry_price) / entry_price * Decimal("100")


def next_take_profit_leg(rules: dict, tp_stage: int) -> dict | None:
    legs = rules.get("take_profit_rules") or []
    if tp_stage >= len(legs):
        return None
    return legs[tp_stage]


def leg_trigger_gain(leg: dict) -> Decimal | None:
    if leg.get("is_runner"):
        return None
    if leg.get("gain_pct") not in (None, ""):
        return _d(leg["gain_pct"])
    if leg.get("gain_pct_min") not in (None, ""):
        return _d(leg["gain_pct_min"])
    return None


def quantity_for_leg(leg: dict, original_quantity: int, remaining: int) -> int:
    if remaining <= 0:
        return 0
    if leg.get("is_runner"):
        return 0
    pct = _d(leg.get("pct_of_position") or 0)
    qty = int((Decimal(original_quantity) * pct / Decimal("100")).to_integral_value())
    return max(0, min(qty, remaining))


def should_hard_stop(entry_price, current_price, hard_stop_pct) -> bool:
    return gain_pct(entry_price, current_price) <= -_d(hard_stop_pct)


def is_expiration_day(position: Position, now: datetime | None = None) -> bool:
    now = now or datetime.now(tz=ET)
    return position.expiration <= now.astimezone(ET).date()


def should_time_exit(position: Position, rules: dict, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(tz=ET)
    now_et = now.astimezone(ET)
    today = now_et.date()
    max_hold = int(rules.get("max_hold_trading_days") or 0)
    held = trading_days_between(position.opened_at.astimezone(ET).date(), today)
    if max_hold and held >= max_hold:
        return True, "time_exit"
    if position.expiration < today:
        return True, "expiration_exit"
    if position.expiration == today:
        raw = rules.get("force_exit_time_et") or "15:45:00"
        hour, minute, *rest = [int(p) for p in raw.split(":")]
        second = rest[0] if rest else 0
        if now_et.timetz().replace(tzinfo=None) >= datetime.strptime(
            f"{hour:02d}:{minute:02d}:{second:02d}", "%H:%M:%S"
        ).time():
            return True, "expiration_exit"
    return False, ""
