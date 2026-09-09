"""Pick a call or put from a catalyst — not from another trader's ticket."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from trading.constants import DIR_BEARISH, DIR_BULLISH, ET, OPTION_CALL, OPTION_PUT
from trading.services.market_data import OptionQuote, UnderlyingSnapshot

DEFAULT_OTM_PCT = Decimal("5.00")
DEFAULT_MIN_DTE = 14
DEFAULT_MAX_DTE = 45


@dataclass(frozen=True)
class SelectedContract:
    ticker: str
    option_type: str
    strike: Decimal
    expiration: date
    entry_price: Decimal
    underlying_price: Decimal
    notes: str

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["strike"] = str(self.strike)
        payload["entry_price"] = str(self.entry_price)
        payload["underlying_price"] = str(self.underlying_price)
        payload["expiration"] = self.expiration.isoformat()
        return payload


class ContractSelectionError(Exception):
    pass


def _strike_increment(spot: Decimal) -> Decimal:
    if spot < 25:
        return Decimal("1")
    if spot < 50:
        return Decimal("2.5")
    if spot < 200:
        return Decimal("5")
    return Decimal("10")


def _round_strike(spot: Decimal, otm_pct: Decimal, option_type: str) -> Decimal:
    increment = _strike_increment(spot)
    offset = spot * (otm_pct / Decimal("100"))
    raw = spot + offset if option_type == OPTION_CALL else spot - offset
    if raw <= 0:
        raw = increment
    steps = (raw / increment).to_integral_value(rounding=ROUND_HALF_UP)
    strike = steps * increment
    if option_type == OPTION_CALL and strike <= spot:
        strike += increment
    if option_type == OPTION_PUT and strike >= spot:
        strike = max(increment, strike - increment)
    return strike.quantize(increment)


def _third_friday(year: int, month: int) -> date:
    day = date(year, month, 1)
    fridays = 0
    while True:
        if day.weekday() == 4:
            fridays += 1
            if fridays == 3:
                return day
        day += timedelta(days=1)


def _fallback_expiration(as_of: date, min_dte: int, max_dte: int) -> date:
    year, month = as_of.year, as_of.month
    for _ in range(6):
        candidate = _third_friday(year, month)
        dte = (candidate - as_of).days
        if min_dte <= dte <= max_dte:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return as_of + timedelta(days=max(min_dte, 21))


def _pick_expiration(
    snapshot: UnderlyingSnapshot,
    as_of: date,
    min_dte: int,
    max_dte: int,
) -> date:
    window = [
        exp
        for exp in sorted(set(snapshot.expirations))
        if min_dte <= (exp - as_of).days <= max_dte
    ]
    if window:
        return window[0]
    return _fallback_expiration(as_of, min_dte, max_dte)


def _contract_price(quote: OptionQuote, spot: Decimal, option_type: str, strike: Decimal) -> Decimal:
    mid = quote.mid
    if mid is not None:
        return mid
    intrinsic = Decimal("0")
    if option_type == OPTION_CALL:
        intrinsic = max(Decimal("0"), spot - strike)
    else:
        intrinsic = max(Decimal("0"), strike - spot)
    premium = max(spot * Decimal("0.01"), Decimal("0.05"))
    return (intrinsic + premium).quantize(Decimal("0.0001"))


def select_contract(
    snapshot: UnderlyingSnapshot,
    direction: str,
    otm_pct: Decimal | str | None = None,
    min_dte: int = DEFAULT_MIN_DTE,
    max_dte: int = DEFAULT_MAX_DTE,
    as_of: date | None = None,
) -> SelectedContract:
    if direction not in {DIR_BULLISH, DIR_BEARISH}:
        raise ContractSelectionError("Direction must be bullish or bearish to pick a contract.")
    option_type = OPTION_CALL if direction == DIR_BULLISH else OPTION_PUT
    otm = Decimal(str(otm_pct if otm_pct is not None else DEFAULT_OTM_PCT))
    as_of = as_of or datetime.now(tz=ET).date()
    expiration = _pick_expiration(snapshot, as_of, min_dte, max_dte)
    target = _round_strike(snapshot.price, otm, option_type)

    candidates = [
        row
        for row in snapshot.contracts
        if row.option_type == option_type and row.expiration == expiration
    ]
    chosen: OptionQuote | None = None
    if candidates:
        chosen = min(candidates, key=lambda row: abs(row.strike - target))
        strike = chosen.strike
        price = _contract_price(chosen, snapshot.price, option_type, strike)
    else:
        strike = target
        intrinsic = (
            max(Decimal("0"), snapshot.price - strike)
            if option_type == OPTION_CALL
            else max(Decimal("0"), strike - snapshot.price)
        )
        price = (intrinsic + max(snapshot.price * Decimal("0.015"), Decimal("0.10"))).quantize(
            Decimal("0.0001")
        )

    if price <= 0:
        raise ContractSelectionError("Could not derive a positive option price.")

    notes = (
        f"{snapshot.ticker} {option_type} {strike} {expiration.isoformat()} "
        f"spot={snapshot.price} target_otm={otm}%"
    )
    return SelectedContract(
        ticker=snapshot.ticker,
        option_type=option_type,
        strike=strike,
        expiration=expiration,
        entry_price=price,
        underlying_price=snapshot.price,
        notes=notes[:255],
    )
