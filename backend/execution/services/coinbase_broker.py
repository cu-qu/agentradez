"""Coinbase Advanced Trade spot harness broker (limit GTC only)."""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_DOWN

from execution.models import HarnessSignal
from execution.services.coinbase_api import (
    CoinbaseAdvancedClient,
    CoinbaseApiError,
    parse_order_response,
    product_mid_price,
)
from execution.services.harness_client import HarnessBrokerClient, MarketQuote
from trading.services.brokers import BrokerError, OrderFill


class CoinbaseHarnessClient(HarnessBrokerClient):
    def __init__(self, client: CoinbaseAdvancedClient | None = None):
        try:
            self._client = client or CoinbaseAdvancedClient()
        except CoinbaseApiError as exc:
            raise BrokerError(str(exc)) from exc

    def get_quote(self, signal: HarnessSignal) -> MarketQuote:
        product_id = signal.symbol
        try:
            payload = self._client.get_product(product_id)
        except CoinbaseApiError as exc:
            raise BrokerError(str(exc)) from exc
        mark = product_mid_price(payload)
        if mark is None:
            raise BrokerError("Coinbase returned no product price.")
        return MarketQuote(mark=mark)

    def place_limit_entry(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._place(signal, quantity, limit_price, entry=True)

    def place_limit_exit(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._place(signal, quantity, limit_price, entry=False)

    def _place(
        self, signal: HarnessSignal, quantity: int, limit_price: Decimal, *, entry: bool
    ) -> OrderFill:
        if entry:
            side = "BUY" if signal.side == "buy" else "SELL"
        else:
            side = "SELL" if signal.side == "buy" else "BUY"
        base_size = Decimal(quantity).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        client_order_id = str(uuid.uuid4())
        try:
            payload = self._client.create_limit_order(
                product_id=signal.symbol,
                side=side,
                base_size=f"{base_size}",
                limit_price=f"{limit_price.quantize(Decimal('0.01'))}",
                client_order_id=client_order_id,
            )
        except CoinbaseApiError as exc:
            raise BrokerError(str(exc)) from exc
        order_id, status, filled_qty, avg_price = parse_order_response(
            payload, fallback_qty=Decimal(quantity), fallback_price=limit_price
        )
        if not order_id:
            order_id = client_order_id
        return OrderFill(
            broker_order_id=order_id,
            status=status,
            filled_quantity=filled_qty,
            filled_avg_price=avg_price,
        )

    def fetch_order(self, broker_order_id: str) -> OrderFill | None:
        try:
            payload = self._client.get_order(broker_order_id)
        except CoinbaseApiError:
            return None
        order_id, status, filled_qty, avg_price = parse_order_response(
            payload, fallback_qty=Decimal("0"), fallback_price=Decimal("0")
        )
        return OrderFill(
            broker_order_id=order_id or broker_order_id,
            status=status,
            filled_quantity=filled_qty,
            filled_avg_price=avg_price,
        )

    def cancel_order(self, broker_order_id: str) -> None:
        try:
            self._client.cancel_orders([broker_order_id])
        except CoinbaseApiError as exc:
            raise BrokerError(str(exc)) from exc
