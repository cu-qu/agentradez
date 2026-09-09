"""Broker adapters.

Alpaca still uses StubBrokerClient until a live adapter is wired. Robinhood
uses the official Agentic Trading MCP when the connection has OAuth tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils.crypto import get_random_string

from trading.constants import BROKER_ALPACA, BROKER_ROBINHOOD, CONTRACT_MULTIPLIER
from trading.models import BrokerConnection
from trading.services.credentials import decrypt_credentials
from trading.services.robinhood import (
    RobinhoodError,
    contracts_match,
    fetch_option_order,
    find_option_instrument,
    list_accounts_for,
    mcp_client_for,
    option_order_fill,
    option_orders,
    option_positions,
    option_quote_market,
    parse_option_order,
    parse_option_position,
    place_option_order,
    portfolio_equity,
    portfolio_spendable,
)


WORKING_ORDER_STATUSES = frozenset({"submitted"})
FILLED_ORDER_STATUSES = frozenset({"filled", "partial"})
TERMINAL_UNFILLED_STATUSES = frozenset({"cancelled", "rejected"})


@dataclass
class OrderFill:
    broker_order_id: str
    status: str
    filled_quantity: int
    filled_avg_price: Decimal


@dataclass
class OptionQuote:
    mark: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    instrument_id: str = ""

    @property
    def last_day_exit(self) -> Decimal:
        if self.bid is not None and self.bid > 0:
            return self.bid
        return self.mark


@dataclass
class AccountCapital:
    equity: Decimal
    buying_power: Decimal


class BrokerError(Exception):
    pass


class BrokerClient:
    def get_equity(self) -> Decimal:
        raise NotImplementedError

    def get_capital(self) -> AccountCapital:
        equity = self.get_equity()
        return AccountCapital(equity=equity, buying_power=equity)

    def get_option_quote(
        self,
        ticker: str,
        option_type: str,
        strike: Decimal,
        expiration: date,
    ) -> Decimal:
        raise NotImplementedError

    def get_option_market(
        self,
        ticker: str,
        option_type: str,
        strike: Decimal,
        expiration: date,
    ) -> OptionQuote:
        return OptionQuote(mark=self.get_option_quote(ticker, option_type, strike, expiration))

    def buy_to_open(
        self,
        ticker: str,
        option_type: str,
        strike: Decimal,
        expiration: date,
        quantity: int,
        limit_price: Decimal,
    ) -> OrderFill:
        raise NotImplementedError

    def sell_to_close(
        self,
        ticker: str,
        option_type: str,
        strike: Decimal,
        expiration: date,
        quantity: int,
        limit_price: Decimal,
    ) -> OrderFill:
        raise NotImplementedError

    def list_open_option_positions(self) -> list[dict]:
        raise NotImplementedError

    def get_order(
        self,
        broker_order_id: str,
        quantity: int = 0,
        limit_price: Decimal = Decimal("0"),
    ) -> OrderFill | None:
        return None

    def list_option_orders(self) -> list[dict]:
        return []


class StubBrokerClient(BrokerClient):
    """Immediate-fill paper broker used until live adapters are wired."""

    def __init__(self, connection: BrokerConnection, quote_override: Decimal | None = None):
        self.connection = connection
        self.quote_override = quote_override

    def get_equity(self) -> Decimal:
        equity = self.connection.last_equity
        if equity is None or equity <= 0:
            return Decimal("100000.00")
        return equity

    def get_option_quote(self, ticker, option_type, strike, expiration) -> Decimal:
        if self.quote_override is not None:
            return self.quote_override
        quotes = getattr(self.connection, "_stub_quotes", None)
        if quotes:
            key = (ticker.upper(), option_type, str(strike), str(expiration))
            if key in quotes:
                return Decimal(str(quotes[key]))
        return Decimal("1.00")

    def get_option_market(self, ticker, option_type, strike, expiration) -> OptionQuote:
        mark = self.get_option_quote(ticker, option_type, strike, expiration)
        return OptionQuote(mark=mark)

    def buy_to_open(self, ticker, option_type, strike, expiration, quantity, limit_price):
        return OrderFill(
            broker_order_id=f"stub-buy-{get_random_string(12)}",
            status="filled",
            filled_quantity=quantity,
            filled_avg_price=limit_price,
        )

    def sell_to_close(self, ticker, option_type, strike, expiration, quantity, limit_price):
        return OrderFill(
            broker_order_id=f"stub-sell-{get_random_string(12)}",
            status="filled",
            filled_quantity=quantity,
            filled_avg_price=limit_price,
        )

    def list_open_option_positions(self) -> list[dict]:
        return []


class RobinhoodBrokerClient(BrokerClient):
    """Live Robinhood Agentic Trading MCP adapter."""

    def __init__(self, connection: BrokerConnection, quote_override: Decimal | None = None):
        self.connection = connection
        self.quote_override = quote_override

    def _account_number(self) -> str:
        account_id = (self.connection.broker_account_id or "").strip()
        if account_id:
            return account_id
        accounts = list_accounts_for(self.connection)
        agentic = [row for row in accounts if row.get("agentic_allowed")]
        if len(agentic) == 1:
            self.connection.broker_account_id = agentic[0]["account_number"]
            self.connection.save(update_fields=["broker_account_id", "updated_at"])
            return self.connection.broker_account_id
        raise BrokerError(
            "Select a Robinhood Agentic account before trading. "
            "Open one in Robinhood if none are listed."
        )

    def _client(self):
        try:
            return mcp_client_for(self.connection)
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc

    def get_capital(self) -> AccountCapital:
        try:
            payload = self._client().call_tool(
                "get_portfolio", {"account_number": self._account_number()}
            )
            equity = portfolio_equity(payload)
            spendable = portfolio_spendable(payload)
            if spendable is None or spendable < 0:
                spendable = equity
            return AccountCapital(equity=equity, buying_power=spendable)
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc

    def get_equity(self) -> Decimal:
        return self.get_capital().equity

    def get_option_quote(self, ticker, option_type, strike, expiration) -> Decimal:
        return self.get_option_market(ticker, option_type, strike, expiration).mark

    def get_option_market(self, ticker, option_type, strike, expiration) -> OptionQuote:
        if self.quote_override is not None:
            return OptionQuote(mark=Decimal(str(self.quote_override)))
        last_error: Exception | None = None
        try:
            client = self._client()
            instrument_id = find_option_instrument(
                client, ticker, option_type, strike, expiration
            )
            market = option_quote_market(client, instrument_id)
            if market["mark"] is None:
                raise RobinhoodError("Robinhood did not return an option quote.")
            return OptionQuote(
                mark=market["mark"],
                bid=market["bid"],
                ask=market["ask"],
                instrument_id=instrument_id,
            )
        except RobinhoodError as exc:
            last_error = exc
        try:
            for row in self.list_open_option_positions():
                if not contracts_match(row, ticker, option_type, strike, expiration):
                    continue
                mark = row.get("current_price") or row.get("bid") or row.get("ask")
                if mark is None:
                    continue
                bid = row.get("bid")
                ask = row.get("ask")
                return OptionQuote(
                    mark=Decimal(str(mark)),
                    bid=Decimal(str(bid)) if bid is not None else None,
                    ask=Decimal(str(ask)) if ask is not None else None,
                    instrument_id=str(row.get("option_id") or ""),
                )
        except BrokerError as exc:
            last_error = last_error or exc
        raise BrokerError(str(last_error) if last_error else "No option quote.")

    def buy_to_open(self, ticker, option_type, strike, expiration, quantity, limit_price):
        return self._place(ticker, option_type, strike, expiration, quantity, limit_price, "buy", "open")

    def sell_to_close(self, ticker, option_type, strike, expiration, quantity, limit_price):
        return self._place(ticker, option_type, strike, expiration, quantity, limit_price, "sell", "close")

    def _instrument_id(self, ticker, option_type, strike, expiration) -> str:
        client = self._client()
        try:
            return find_option_instrument(client, ticker, option_type, strike, expiration)
        except RobinhoodError:
            for row in self.list_open_option_positions():
                if contracts_match(row, ticker, option_type, strike, expiration):
                    option_id = str(row.get("option_id") or "")
                    if option_id:
                        return option_id
            raise

    def _place(
        self,
        ticker,
        option_type,
        strike,
        expiration,
        quantity,
        limit_price,
        side: str,
        position_effect: str,
    ) -> OrderFill:
        try:
            client = self._client()
            instrument_id = self._instrument_id(
                ticker, option_type, strike, expiration
            )
            fill = place_option_order(
                client,
                self._account_number(),
                instrument_id,
                quantity,
                Decimal(str(limit_price)),
                side,
                position_effect,
            )
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc
        return OrderFill(
            broker_order_id=fill["broker_order_id"],
            status=fill["status"],
            filled_quantity=fill["filled_quantity"],
            filled_avg_price=fill["filled_avg_price"],
        )

    def list_open_option_positions(self) -> list[dict]:
        try:
            payload = self._client().call_tool(
                "get_option_positions", {"account_number": self._account_number()}
            )
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc
        parsed = []
        for row in option_positions(payload):
            item = parse_option_position(row)
            if item:
                parsed.append(item)
        return parsed

    def list_option_orders(self) -> list[dict]:
        try:
            payload = self._client().call_tool(
                "get_option_orders", {"account_number": self._account_number()}
            )
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc
        parsed = []
        for row in option_orders(payload):
            item = parse_option_order(row)
            if item:
                parsed.append(item)
        return parsed

    def get_order(
        self,
        broker_order_id: str,
        quantity: int = 0,
        limit_price: Decimal = Decimal("0"),
    ) -> OrderFill | None:
        try:
            row = fetch_option_order(
                self._client(), self._account_number(), broker_order_id
            )
        except RobinhoodError as exc:
            raise BrokerError(str(exc)) from exc
        if row is None:
            for item in self.list_option_orders():
                if item.get("broker_order_id") == broker_order_id:
                    return OrderFill(
                        broker_order_id=item["broker_order_id"],
                        status=item["status"],
                        filled_quantity=item["filled_quantity"],
                        filled_avg_price=item["filled_avg_price"],
                    )
            return None
        fields = option_order_fill(
            row,
            quantity if quantity > 0 else 1,
            Decimal(str(limit_price or 0)),
        )
        return OrderFill(
            broker_order_id=fields["broker_order_id"],
            status=fields["status"],
            filled_quantity=fields["filled_quantity"],
            filled_avg_price=fields["filled_avg_price"],
        )


def _has_robinhood_oauth(connection: BrokerConnection) -> bool:
    creds = decrypt_credentials(connection.encrypted_credentials)
    return bool(creds.get("access_token"))


def get_broker_client(
    connection: BrokerConnection, quote_override: Decimal | None = None
) -> BrokerClient:
    if connection.broker == BROKER_ROBINHOOD and _has_robinhood_oauth(connection):
        return RobinhoodBrokerClient(connection, quote_override=quote_override)
    if connection.broker in (BROKER_ALPACA, BROKER_ROBINHOOD):
        return StubBrokerClient(connection, quote_override=quote_override)
    raise BrokerError(f"Unsupported broker: {connection.broker}")


def option_pnl(entry_price: Decimal, exit_price: Decimal, quantity: int) -> Decimal:
    entry_price = Decimal(str(entry_price))
    exit_price = Decimal(str(exit_price))
    return (exit_price - entry_price) * CONTRACT_MULTIPLIER * Decimal(quantity)


def unrealized_pnl(entry_price: Decimal, current_price: Decimal, quantity: int) -> Decimal:
    return option_pnl(entry_price, current_price, quantity)
