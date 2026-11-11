"""Unified limit-order interface for the execution harness (all markets)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from execution.constants import MARKET_OPTIONS
from execution.models import HarnessSignal
from trading.constants import BROKER_ALPACA, BROKER_COINBASE, BROKER_KALSHI, BROKER_ROBINHOOD, OPTION_CALL
from trading.models import BrokerConnection
from trading.services.brokers import BrokerClient, BrokerError, OrderFill, get_broker_client

FILLED_STATUSES = frozenset({"filled", "partial"})
WORKING_STATUSES = frozenset({"submitted", "pending", "open"})
TERMINAL_UNFILLED = frozenset({"cancelled", "rejected", "canceled", "expired"})


@dataclass
class MarketQuote:
    mark: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None


class HarnessBrokerClient(ABC):
    @abstractmethod
    def get_quote(self, signal: HarnessSignal) -> MarketQuote:
        raise NotImplementedError

    @abstractmethod
    def place_limit_entry(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        raise NotImplementedError

    @abstractmethod
    def place_limit_exit(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        raise NotImplementedError

    @abstractmethod
    def fetch_order(self, broker_order_id: str) -> OrderFill | None:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError


class OptionsHarnessClient(HarnessBrokerClient):
    def __init__(self, connection: BrokerConnection):
        self.connection = connection
        self._broker = get_broker_client(connection)

    def get_quote(self, signal: HarnessSignal) -> MarketQuote:
        quote = self._broker.get_option_market(
            signal.symbol,
            signal.option_type or OPTION_CALL,
            signal.strike or Decimal("0"),
            signal.expiration or date.today(),
        )
        return MarketQuote(mark=quote.mark, bid=quote.bid, ask=quote.ask)

    def place_limit_entry(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._broker.buy_to_open(
            signal.symbol,
            signal.option_type or OPTION_CALL,
            signal.strike or Decimal("0"),
            signal.expiration or date.today(),
            quantity,
            limit_price,
        )

    def place_limit_exit(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._broker.sell_to_close(
            signal.symbol,
            signal.option_type or OPTION_CALL,
            signal.strike or Decimal("0"),
            signal.expiration or date.today(),
            quantity,
            limit_price,
        )

    def fetch_order(self, broker_order_id: str) -> OrderFill | None:
        return self._broker.get_order(broker_order_id)

    def cancel_order(self, broker_order_id: str) -> None:
        raise BrokerError("Cancel not implemented for options broker in harness.")


def harness_client_for(connection: BrokerConnection) -> HarnessBrokerClient:
    from execution.services.coinbase_broker import CoinbaseHarnessClient
    from execution.services.kalshi_broker import KalshiHarnessClient

    broker = connection.broker
    if broker == BROKER_KALSHI:
        return KalshiHarnessClient(connection)
    if broker == BROKER_COINBASE:
        return CoinbaseHarnessClient(connection)
    if broker in (BROKER_ROBINHOOD, BROKER_ALPACA):
        return OptionsHarnessClient(connection)
    return OptionsHarnessClient(connection)


def market_multiplier(market: str) -> Decimal:
    if market == MARKET_OPTIONS:
        from trading.constants import CONTRACT_MULTIPLIER

        return CONTRACT_MULTIPLIER
    return Decimal("1")
