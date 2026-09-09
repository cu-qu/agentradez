"""Parse option trades out of X (Twitter) posts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from trading.constants import ET, OPTION_CALL, OPTION_PUT

RESERVED_TICKERS = {
    "BTO",
    "STC",
    "BTC",
    "STO",
    "CALL",
    "CALLS",
    "PUT",
    "PUTS",
    "TODAY",
    "TRADES",
    "DAILY",
    "LOTTO",
    "SWING",
    "DTE",
    "ODTE",
    "ATM",
    "ITM",
    "OTM",
    "THE",
    "AND",
    "FOR",
    "AT",
    "ON",
    "FROM",
    "WITH",
    "THIS",
    "THAT",
    "JUST",
    "HEAVY",
    "SMALL",
    "TRIM",
    "ADD",
    "ADDING",
    "BOUGHT",
    "BUYING",
    "SOLD",
    "SELLING",
    "CLOSED",
    "CLOSE",
    "ENTRY",
    "ENTERED",
    "LONG",
    "SHORT",
    "FILL",
    "FILLED",
    "DEBIT",
    "CREDIT",
}

EXIT_HINTS = re.compile(
    r"\b(?:stc|btc|sto|sold|selling|closed|closing|stopped|stop[\s-]?loss|"
    r"take[\s-]?profit|trimmed|trimming|out of)\b",
    re.IGNORECASE,
)
ZERO_DTE = re.compile(r"\b(?:0[\s-]?dte|odte)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

TRADE_RE = re.compile(
    r"""
    [?#$]?
    (?P<ticker>[A-Za-z]{1,5})
    (?:
        \s+(?P<exp_a>\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2})
        \s+(?P<strike_a>\d+(?:\.\d+)?)\s*(?P<type_a>[CcPp](?:alls?|uts?)?)
      |
        \s+(?P<strike_b>\d+(?:\.\d+)?)\s*(?P<type_b>[CcPp](?:alls?|uts?)?)
        (?:\s+(?P<exp_b>\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2}))?
    )
    (?:\s+(?:@|at|for|fill(?:ed)?|debit)\s*\$?(?P<price>\d*\.?\d+))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

TRAILING_PRICE_RE = re.compile(
    r"(?:@|at|for|fill(?:ed)?|debit)\s*\$?(?P<price>\d*\.?\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedTrade:
    ticker: str
    option_type: str
    strike: Decimal
    expiration: date
    entry_price: Decimal
    is_exit: bool
    notes: str

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["strike"] = str(self.strike)
        payload["entry_price"] = str(self.entry_price)
        payload["expiration"] = self.expiration.isoformat()
        return payload


def _as_decimal(value: str) -> Decimal | None:
    raw = (value or "").strip()
    if raw.startswith("."):
        raw = f"0{raw}"
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _normalize_option_type(raw: str) -> str:
    return OPTION_CALL if raw.lower().startswith("c") else OPTION_PUT


def _parse_expiration(raw: str | None, posted_on: date, zero_dte: bool) -> date | None:
    if not raw:
        return posted_on if zero_dte else posted_on
    if "-" in raw:
        year, month, day = (int(part) for part in raw.split("-"))
        return date(year, month, day)
    parts = [int(part) for part in raw.split("/")]
    month, day = parts[0], parts[1]
    if len(parts) == 3:
        year = parts[2]
        if year < 100:
            year += 2000
        return date(year, month, day)
    candidate = date(posted_on.year, month, day)
    if candidate < posted_on:
        candidate = date(posted_on.year + 1, month, day)
    return candidate


def _posted_on(posted_at: datetime | date | None) -> date:
    if posted_at is None:
        return datetime.now(tz=ET).date()
    if isinstance(posted_at, datetime):
        if posted_at.tzinfo is None:
            return posted_at.date()
        return posted_at.astimezone(ET).date()
    return posted_at


def _price_near_match(text: str, match: re.Match) -> Decimal | None:
    grouped = match.group("price")
    if grouped:
        return _as_decimal(grouped)
    window = text[match.end() : match.end() + 40]
    trailing = TRAILING_PRICE_RE.search(window)
    if trailing:
        return _as_decimal(trailing.group("price"))
    return None


def parse_trades(text: str, posted_at: datetime | date | None = None) -> list[ParsedTrade]:
    """Return option trades found in a tweet. Exits are included and flagged."""
    if not text or not text.strip():
        return []

    cleaned = URL_RE.sub(" ", text)
    posted_on = _posted_on(posted_at)
    zero_dte = bool(ZERO_DTE.search(cleaned))
    found: list[ParsedTrade] = []
    seen: set[tuple] = set()

    for match in TRADE_RE.finditer(cleaned):
        ticker = match.group("ticker").upper()
        if ticker in RESERVED_TICKERS:
            continue
        strike_raw = match.group("strike_a") or match.group("strike_b")
        type_raw = match.group("type_a") or match.group("type_b")
        exp_raw = match.group("exp_a") or match.group("exp_b")
        strike = _as_decimal(strike_raw)
        price = _price_near_match(cleaned, match)
        expiration = _parse_expiration(exp_raw, posted_on, zero_dte)
        if strike is None or price is None or expiration is None:
            continue
        option_type = _normalize_option_type(type_raw)
        key = (ticker, option_type, strike, expiration, price)
        if key in seen:
            continue
        seen.add(key)
        snippet = match.group(0).strip()
        line_start = cleaned.rfind("\n", 0, match.start()) + 1
        line_end = cleaned.find("\n", match.end())
        if line_end < 0:
            line_end = len(cleaned)
        line = cleaned[line_start:line_end]
        found.append(
            ParsedTrade(
                ticker=ticker,
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                entry_price=price,
                is_exit=bool(EXIT_HINTS.search(line)),
                notes=snippet[:255],
            )
        )
    return found


def parse_entry_trades(
    text: str, posted_at: datetime | date | None = None
) -> list[ParsedTrade]:
    return [trade for trade in parse_trades(text, posted_at=posted_at) if not trade.is_exit]
