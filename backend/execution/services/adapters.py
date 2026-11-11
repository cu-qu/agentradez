"""Unified broker adapter surface for the execution harness."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading.constants import (
    BROKER_ALPACA,
    BROKER_COINBASE,
    BROKER_KALSHI,
    BROKER_ROBINHOOD,
)
from trading.models import BrokerConnection
from trading.services.brokers import BrokerClient, BrokerError, get_broker_client
from trading.services.robinhood import (
    RobinhoodError,
    list_accounts_for,
    mcp_client_for,
    portfolio_equity,
    portfolio_spendable,
)

from execution.services.coinbase_api import CoinbaseAdvancedClient, CoinbaseApiError, accounts_buying_power
from execution.services.harness_client import HarnessBrokerClient, harness_client_for
from execution.services.kalshi_api import KalshiApiError, KalshiRestClient, balance_buying_power_usd


@dataclass
class DeskAccountSnapshot:
    account_slug: str
    broker: str
    broker_account_id: str
    label: str
    equity: Decimal | None
    buying_power: Decimal | None
    option_level: str | None
    trading_enabled: bool
    dry_run: bool


class DeskBrokerAdapter:
    def __init__(
        self,
        connection: BrokerConnection,
        account_slug: str,
        label: str,
        dry_run: bool,
    ):
        self.connection = connection
        self.account_slug = account_slug
        self.label = label
        self.dry_run = dry_run

    def harness_client(self) -> HarnessBrokerClient:
        return harness_client_for(self.connection)

    def client(self) -> BrokerClient:
        """Legacy options broker — Robinhood/Alpaca only."""
        if self.connection.broker in (BROKER_KALSHI, BROKER_COINBASE):
            raise BrokerError("Use harness_client() for Kalshi/Coinbase.")
        return get_broker_client(self.connection)

    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        raise NotImplementedError


class RobinhoodDeskAdapter(DeskBrokerAdapter):
    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        snapshots: list[DeskAccountSnapshot] = []
        try:
            accounts = list_accounts_for(self.connection)
        except RobinhoodError:
            accounts = []
        selected = (self.connection.broker_account_id or "").strip()
        for row in accounts:
            account_number = str(row.get("account_number") or "")
            if selected and account_number != selected:
                continue
            equity = None
            buying_power = None
            try:
                payload = mcp_client_for(self.connection).call_tool(
                    "get_portfolio", {"account_number": account_number}
                )
                equity = portfolio_equity(payload)
                buying_power = portfolio_spendable(payload)
            except RobinhoodError:
                pass
            snapshots.append(
                DeskAccountSnapshot(
                    account_slug=self.account_slug,
                    broker=BROKER_ROBINHOOD,
                    broker_account_id=account_number,
                    label=self.label,
                    equity=equity,
                    buying_power=buying_power,
                    option_level=str(row.get("option_level") or row.get("options_level") or ""),
                    trading_enabled=bool(row.get("agentic_allowed")),
                    dry_run=self.dry_run,
                )
            )
        if not snapshots and selected:
            snapshots.append(
                DeskAccountSnapshot(
                    account_slug=self.account_slug,
                    broker=BROKER_ROBINHOOD,
                    broker_account_id=selected,
                    label=self.label,
                    equity=None,
                    buying_power=None,
                    option_level=None,
                    trading_enabled=True,
                    dry_run=self.dry_run,
                )
            )
        return snapshots


class StubDeskAdapter(DeskBrokerAdapter):
    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        client = get_broker_client(self.connection)
        equity = client.get_equity()
        capital = client.get_capital()
        return [
            DeskAccountSnapshot(
                account_slug=self.account_slug,
                broker=self.connection.broker,
                broker_account_id=self.connection.broker_account_id or "default",
                label=self.label,
                equity=equity,
                buying_power=capital.buying_power,
                option_level="stub",
                trading_enabled=True,
                dry_run=self.dry_run,
            )
        ]


class KalshiDeskAdapter(DeskBrokerAdapter):
    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        try:
            from execution.services.broker_credentials import kalshi_config_for

            client = KalshiRestClient(kalshi_config_for(self.connection))
            balance = client.balance()
            buying_power = balance_buying_power_usd(balance)
        except KalshiApiError:
            buying_power = None
        account_id = self.connection.broker_account_id or "primary"
        return [
            DeskAccountSnapshot(
                account_slug=self.account_slug,
                broker=BROKER_KALSHI,
                broker_account_id=account_id,
                label=self.label,
                equity=buying_power,
                buying_power=buying_power,
                option_level="event_contracts",
                trading_enabled=buying_power is not None,
                dry_run=self.dry_run,
            )
        ]


class CoinbaseDeskAdapter(DeskBrokerAdapter):
    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        try:
            from execution.services.broker_credentials import coinbase_config_for

            client = CoinbaseAdvancedClient(coinbase_config_for(self.connection))
            payload = client.list_accounts()
            equity, buying_power = accounts_buying_power(payload)
        except CoinbaseApiError:
            equity, buying_power = None, None
        account_id = self.connection.broker_account_id or "spot"
        return [
            DeskAccountSnapshot(
                account_slug=self.account_slug,
                broker=BROKER_COINBASE,
                broker_account_id=account_id,
                label=self.label,
                equity=equity,
                buying_power=buying_power,
                option_level="spot",
                trading_enabled=buying_power is not None,
                dry_run=self.dry_run,
            )
        ]


def desk_adapter_for(execution_account) -> DeskBrokerAdapter:
    connection = execution_account.broker_connection
    slug = execution_account.slug
    label = execution_account.label
    dry_run = execution_account.dry_run
    broker = connection.broker
    if broker == BROKER_ROBINHOOD:
        return RobinhoodDeskAdapter(connection, slug, label, dry_run)
    if broker == BROKER_ALPACA:
        return StubDeskAdapter(connection, slug, label, dry_run)
    if broker == BROKER_KALSHI:
        return KalshiDeskAdapter(connection, slug, label, dry_run)
    if broker == BROKER_COINBASE:
        return CoinbaseDeskAdapter(connection, slug, label, dry_run)
    return StubDeskAdapter(connection, slug, label, dry_run)
