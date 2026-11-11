"""Kalshi event-contract harness broker (limit orders only)."""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_DOWN

from django.utils.crypto import get_random_string

from execution.models import HarnessSignal
from execution.services.harness_client import HarnessBrokerClient, MarketQuote
from execution.services.kalshi_api import (
    KalshiApiError,
    KalshiRestClient,
    dollars_to_yes_cents,
    market_yes_mid_dollars,
    parse_order_fill,
)
from trading.services.brokers import BrokerError, OrderFill


class KalshiHarnessClient(HarnessBrokerClient):
    def __init__(self, connection, client: KalshiRestClient | None = None):
        from execution.services.broker_credentials import kalshi_config_for

        try:
            self._client = client or KalshiRestClient(kalshi_config_for(connection))
        except KalshiApiError as exc:
            raise BrokerError(str(exc)) from exc

    def _contract_side(self, signal: HarnessSignal) -> str:
        rule = signal.entry_rule or {}
        leg = (rule.get("kalshi_side") or rule.get("contract_side") or "yes").lower()
        return "no" if leg == "no" else "yes"

    def get_quote(self, signal: HarnessSignal) -> MarketQuote:
        try:
            payload = self._client.market(signal.symbol)
        except KalshiApiError as exc:
            raise BrokerError(str(exc)) from exc
        mark = market_yes_mid_dollars(payload)
        if mark is None:
            raise BrokerError("Kalshi returned no quote.")
        return MarketQuote(mark=mark)

    def place_limit_entry(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._place(signal, quantity, limit_price, closing=False)

    def place_limit_exit(self, signal: HarnessSignal, quantity: int, limit_price: Decimal) -> OrderFill:
        return self._place(signal, quantity, limit_price, closing=True)

    def _place(
        self, signal: HarnessSignal, quantity: int, limit_price: Decimal, *, closing: bool
    ) -> OrderFill:
        side = self._contract_side(signal)
        if closing:
            action = "sell"
        else:
            action = "buy" if signal.side == "buy" else "sell"
        cents = dollars_to_yes_cents(limit_price)
        client_order_id = str(uuid.uuid4())
        try:
            payload = self._client.create_limit_order(
                ticker=signal.symbol,
                action=action,
                side=side,
                count=quantity,
                yes_price_cents=cents if side == "yes" else None,
                no_price_cents=cents if side == "no" else None,
                client_order_id=client_order_id,
            )
        except KalshiApiError as exc:
            raise BrokerError(str(exc)) from exc
        order_id, status, filled_qty, avg_price = parse_order_fill(
            payload, fallback_qty=quantity, fallback_price=limit_price
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
        except KalshiApiError:
            return None
        order_id, status, filled_qty, avg_price = parse_order_fill(
            payload, fallback_qty=0, fallback_price=Decimal("0")
        )
        return OrderFill(
            broker_order_id=order_id or broker_order_id,
            status=status,
            filled_quantity=filled_qty,
            filled_avg_price=avg_price,
        )

    def cancel_order(self, broker_order_id: str) -> None:
        try:
            self._client.cancel_order(broker_order_id)
        except KalshiApiError as exc:
            raise BrokerError(str(exc)) from exc
