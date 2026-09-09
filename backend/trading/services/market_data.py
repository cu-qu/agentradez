"""Underlying and option-chain snapshots used to pick a contract.

Yahoo Finance is used as a public market-data fallback so this strategy can
choose a strike/expiry without copying a trader's ticket. Callers should stub
this in tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

YAHOO_OPTIONS_URL = "https://query2.finance.yahoo.com/v7/finance/options/{ticker}"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HTTP_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (compatible; AgenticTrading/1.0; research-breakthrough)"
)


class MarketDataError(Exception):
    pass


@dataclass
class OptionQuote:
    strike: Decimal
    expiration: date
    option_type: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: int = 0
    open_interest: int = 0

    @property
    def mid(self) -> Decimal | None:
        if self.bid and self.ask and self.bid > 0 and self.ask > 0:
            return ((self.bid + self.ask) / Decimal("2")).quantize(Decimal("0.0001"))
        if self.last and self.last > 0:
            return self.last
        if self.ask and self.ask > 0:
            return self.ask
        if self.bid and self.bid > 0:
            return self.bid
        return None


@dataclass
class UnderlyingSnapshot:
    ticker: str
    price: Decimal
    expirations: list[date] = field(default_factory=list)
    contracts: list[OptionQuote] = field(default_factory=list)


def _as_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if number <= 0:
        return None
    return number


def _unix_to_date(value) -> date | None:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def _get_json(url: str, params: dict | None = None) -> dict:
    response = requests.get(
        url,
        params=params,
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise MarketDataError("Unexpected market-data payload.")
    return payload


def fetch_underlying_price(ticker: str) -> Decimal:
    symbol = ticker.strip().upper()
    payload = _get_json(
        YAHOO_CHART_URL.format(ticker=symbol),
        params={"interval": "1d", "range": "1d"},
    )
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    meta = result.get("meta") or {}
    price = _as_decimal(meta.get("regularMarketPrice") or meta.get("previousClose"))
    if price is None:
        raise MarketDataError(f"No last price for {symbol}.")
    return price


def fetch_option_snapshot(ticker: str, expiration: date | None = None) -> UnderlyingSnapshot:
    symbol = ticker.strip().upper()
    params = {}
    if expiration is not None:
        midnight = datetime(expiration.year, expiration.month, expiration.day, tzinfo=timezone.utc)
        params["date"] = int(midnight.timestamp())
    try:
        payload = _get_json(YAHOO_OPTIONS_URL.format(ticker=symbol), params=params or None)
    except Exception as exc:  # noqa: BLE001 — fall back to spot only
        logger.warning("Option chain fetch failed for %s: %s", symbol, exc)
        price = fetch_underlying_price(symbol)
        return UnderlyingSnapshot(ticker=symbol, price=price)

    result = ((payload.get("optionChain") or {}).get("result") or [None])[0]
    if not result:
        price = fetch_underlying_price(symbol)
        return UnderlyingSnapshot(ticker=symbol, price=price)

    quote = result.get("quote") or {}
    price = _as_decimal(quote.get("regularMarketPrice") or quote.get("regularMarketPreviousClose"))
    if price is None:
        price = fetch_underlying_price(symbol)

    expirations = []
    for raw in result.get("expirationDates") or []:
        parsed = _unix_to_date(raw)
        if parsed:
            expirations.append(parsed)

    contracts: list[OptionQuote] = []
    for chain in result.get("options") or []:
        exp = _unix_to_date(chain.get("expirationDate"))
        if exp is None:
            continue
        for option_type, rows in (("call", chain.get("calls") or []), ("put", chain.get("puts") or [])):
            for row in rows:
                strike = _as_decimal(row.get("strike"))
                if strike is None:
                    continue
                contracts.append(
                    OptionQuote(
                        strike=strike,
                        expiration=exp,
                        option_type=option_type,
                        bid=_as_decimal(row.get("bid")),
                        ask=_as_decimal(row.get("ask")),
                        last=_as_decimal(row.get("lastPrice")),
                        volume=int(row.get("volume") or 0),
                        open_interest=int(row.get("openInterest") or 0),
                    )
                )
    return UnderlyingSnapshot(
        ticker=symbol,
        price=price,
        expirations=expirations,
        contracts=contracts,
    )
