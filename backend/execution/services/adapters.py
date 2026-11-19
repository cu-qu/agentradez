"""Unified broker adapter surface for the execution harness."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from trading.constants import BROKER_ALPACA, BROKER_ROBINHOOD
from trading.models import BrokerConnection
from trading.services.brokers import (
    BrokerClient,
    BrokerError,
    OrderFill,
    get_broker_client,
)
from trading.services.robinhood import (
    RobinhoodError,
    list_accounts_for,
    portfolio_spendable,
    portfolio_equity,
    mcp_client_for,
)


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


class DeskBrokerAdapter(ABC):
    @abstractmethod
    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        raise NotImplementedError

    @abstractmethod
    def client(self) -> BrokerClient:
        raise NotImplementedError


class RobinhoodDeskAdapter(DeskBrokerAdapter):
    def __init__(self, connection: BrokerConnection, account_slug: str, label: str, dry_run: bool):
        self.connection = connection
        self.account_slug = account_slug
        self.label = label
        self.dry_run = dry_run

    def client(self) -> BrokerClient:
        return get_broker_client(self.connection)

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
    """Alpaca / paper connections use the existing stub broker."""

    def __init__(self, connection: BrokerConnection, account_slug: str, label: str, dry_run: bool):
        self.connection = connection
        self.account_slug = account_slug
        self.label = label
        self.dry_run = dry_run

    def client(self) -> BrokerClient:
        return get_broker_client(self.connection)

    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        client = self.client()
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
    """Placeholder adapter — live RSA-PSS REST in a follow-up PR."""

    def __init__(self, account_slug: str, label: str, dry_run: bool):
        self.account_slug = account_slug
        self.label = label
        self.dry_run = dry_run

    def client(self) -> BrokerClient:
        raise BrokerError("Kalshi adapter not wired in this PR.")

    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        return [
            DeskAccountSnapshot(
                account_slug=self.account_slug,
                broker="kalshi",
                broker_account_id="pending",
                label=self.label,
                equity=None,
                buying_power=None,
                option_level=None,
                trading_enabled=False,
                dry_run=self.dry_run,
            )
        ]


class CoinbaseDeskAdapter(DeskBrokerAdapter):
    """Placeholder adapter — Advanced Trade spot in a follow-up PR."""

    def __init__(self, account_slug: str, label: str, dry_run: bool):
        self.account_slug = account_slug
        self.label = label
        self.dry_run = dry_run

    def client(self) -> BrokerClient:
        raise BrokerError("Coinbase adapter not wired in this PR.")

    def snapshot_accounts(self) -> list[DeskAccountSnapshot]:
        return [
            DeskAccountSnapshot(
                account_slug=self.account_slug,
                broker="coinbase",
                broker_account_id="pending",
                label=self.label,
                equity=None,
                buying_power=None,
                option_level=None,
                trading_enabled=False,
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
    if broker == "kalshi":
        return KalshiDeskAdapter(slug, label, dry_run)
    if broker == "coinbase":
        return CoinbaseDeskAdapter(slug, label, dry_run)
    return StubDeskAdapter(connection, slug, label, dry_run)
