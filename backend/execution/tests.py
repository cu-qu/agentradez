from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from execution.constants import POSITION_OPEN, SIGNAL_OPEN, SIGNAL_PENDING
from execution.models import ExecutionAccount, HarnessJournal, HarnessSignal
from execution.services.adapters import CoinbaseDeskAdapter, KalshiDeskAdapter, StubDeskAdapter
from execution.services.caps import CapViolation, check_caps
from execution.services.ingest import ingest_signal
from execution.services.rules_engine import evaluate_signal
from trading.constants import BROKER_ALPACA
from trading.models import BrokerConnection
from trading.services.brokers import OrderFill, OptionQuote


class ExecutionHarnessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="desk", email="desk@example.com", password="x")
        self.connection = BrokerConnection.objects.create(
            user=self.user,
            broker=BROKER_ALPACA,
            broker_account_id="paper-1",
            is_paper=True,
            last_equity=Decimal("50000"),
        )
        self.account = ExecutionAccount.objects.create(
            slug="prop-desk",
            label="Prop Desk Paper",
            broker_connection=self.connection,
            dry_run=True,
            max_open_positions=2,
            max_dollar_exposure=Decimal("5000"),
            max_loss_per_position_usd=Decimal("300"),
        )

    def test_ingest_idempotent(self):
        payload = {
            "ref_id": "sig-001",
            "account_slug": "prop-desk",
            "symbol": "AAPL",
            "option_type": "call",
            "strike": "200",
            "expiration": "2030-01-17",
            "entry_rule": {"type": "limit", "price": "1.25"},
            "stop": "0.80",
            "size": 1,
        }
        first = ingest_signal(payload)
        second = ingest_signal(payload)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(HarnessSignal.objects.count(), 1)

    def test_caps_reject_exposure(self):
        self.account.max_dollar_exposure = Decimal("100")
        self.account.save()
        with self.assertRaises(Exception) as ctx:
            ingest_signal(
                {
                    "ref_id": "sig-cap",
                    "account_slug": "prop-desk",
                    "symbol": "TSLA",
                    "entry_rule": {"type": "limit", "price": "5.00"},
                    "size": 2,
                }
            )
        self.assertIn("max dollar exposure", str(ctx.exception).lower())

    def test_check_caps_open_positions(self):
        self.account.max_open_positions = 1
        self.account.save(update_fields=["max_open_positions"])
        HarnessSignal.objects.create(
            ref_id="open-1",
            execution_account=self.account,
            symbol="MSFT",
            status=SIGNAL_OPEN,
            quantity=1,
            entry_rule={"type": "limit", "price": "1"},
        )
        with self.assertRaises(CapViolation):
            check_caps(self.account, additional_contracts=1, entry_limit_price=Decimal("1"), quantity=1)

    @patch("execution.services.rules_engine.desk_adapter_for")
    def test_rules_engine_dry_run_entry_and_exit(self, desk_for):
        mock_client = MagicMock()
        mock_client.get_option_market.side_effect = [
            OptionQuote(mark=Decimal("1.20")),
            OptionQuote(mark=Decimal("0.40")),
        ]
        mock_client.buy_to_open.return_value = OrderFill("b1", "filled", 1, Decimal("1.20"))
        mock_client.sell_to_close.return_value = OrderFill("s1", "filled", 1, Decimal("2.00"))
        desk_for.return_value = MagicMock(client=lambda: mock_client)

        signal = HarnessSignal.objects.create(
            ref_id="eval-1",
            execution_account=self.account,
            symbol="AAPL",
            option_type="call",
            strike=Decimal("200"),
            expiration=date.today() + timedelta(days=30),
            quantity=1,
            entry_rule={"type": "limit", "price": "1.25"},
            stop_price=Decimal("0.50"),
            status=SIGNAL_PENDING,
        )
        evaluate_signal(signal)
        signal.refresh_from_db()
        self.assertEqual(signal.status, SIGNAL_OPEN)
        self.assertTrue(hasattr(signal, "position"))

        evaluate_signal(signal)
        signal.refresh_from_db()
        self.assertEqual(signal.status, "closed")

    def test_placeholder_adapters(self):
        kalshi = KalshiDeskAdapter("kalshi-desk", "Kalshi", dry_run=True)
        coinbase = CoinbaseDeskAdapter("cb-desk", "Coinbase", dry_run=True)
        self.assertEqual(kalshi.snapshot_accounts()[0].broker, "kalshi")
        self.assertFalse(coinbase.snapshot_accounts()[0].trading_enabled)

    def test_stub_desk_adapter_snapshot(self):
        adapter = StubDeskAdapter(self.connection, "prop-desk", "label", True)
        snaps = adapter.snapshot_accounts()
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].buying_power, Decimal("50000"))

    @override_settings(EXECUTION_MCP_BEARER_TOKEN="test-token")
    def test_mcp_auth_and_ingest(self):
        client = Client()
        unauthorized = client.post("/api/mcp/execution/", data="{}", content_type="application/json")
        self.assertEqual(unauthorized.status_code, 401)

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ingest_signal",
                "arguments": {
                    "ref_id": "mcp-1",
                    "account_slug": "prop-desk",
                    "symbol": "NVDA",
                    "entry_rule": {"type": "limit", "price": "2.00"},
                    "size": 1,
                },
            },
        }
        response = client.post(
            "/api/mcp/execution/",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("result", body)
        self.assertTrue(HarnessSignal.objects.filter(ref_id="mcp-1").exists())

    @patch("execution.services.adapters.list_accounts_for")
    def test_robinhood_adapter_mocked(self, list_accounts):
        from execution.services.adapters import RobinhoodDeskAdapter
        from trading.constants import BROKER_ROBINHOOD

        rh_user = User.objects.create_user(username="rh", email="rh@example.com", password="x")
        rh = BrokerConnection.objects.create(
            user=rh_user,
            broker=BROKER_ROBINHOOD,
            broker_account_id="RH123",
            is_paper=False,
        )
        list_accounts.return_value = [
            {"account_number": "RH123", "agentic_allowed": True, "option_level": "level3"}
        ]
        adapter = RobinhoodDeskAdapter(rh, "rh-desk", "RH", dry_run=True)
        with patch("execution.services.adapters.mcp_client_for") as mcp_for:
            mcp_for.return_value.call_tool.return_value = {
                "equity": "10000",
                "portfolio": {"equity": "10000"},
            }
            with patch("execution.services.adapters.portfolio_equity", return_value=Decimal("10000")):
                with patch(
                    "execution.services.adapters.portfolio_spendable", return_value=Decimal("8000")
                ):
                    snaps = adapter.snapshot_accounts()
        self.assertEqual(snaps[0].broker_account_id, "RH123")
        self.assertEqual(snaps[0].option_level, "level3")


class ExecutionDryRunEnforcedTests(TestCase):
    @override_settings(EXECUTION_DRY_RUN_DEFAULT=True)
    def test_journal_on_ingest(self):
        user = User.objects.create_user(username="u2", email="u2@example.com", password="x")
        conn = BrokerConnection.objects.create(user=user, broker=BROKER_ALPACA, is_paper=True)
        ExecutionAccount.objects.create(slug="desk2", label="Desk", broker_connection=conn, dry_run=True)
        ingest_signal(
            {
                "ref_id": "j-1",
                "account_slug": "desk2",
                "symbol": "SPY",
                "entry_rule": {"price": "1"},
                "size": 1,
            }
        )
        self.assertTrue(HarnessJournal.objects.filter(action="signal_ingested").exists())
