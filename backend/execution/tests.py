from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from execution.constants import ORDER_EXIT, ORDER_WORKING, POSITION_OPEN, SIGNAL_OPEN, SIGNAL_PENDING
from execution.models import ExecutionAccount, HarnessJournal, HarnessOrder, HarnessPosition, HarnessSignal
from execution.services.adapters import KalshiDeskAdapter, StubDeskAdapter
from execution.services.caps import CapViolation, check_caps
from execution.services.harness_client import MarketQuote
from execution.services.ingest import cancel_signal, ingest_signal
from execution.services.mcp_auth import generate_pat
from execution.services.rules_engine import evaluate_all_signals, evaluate_signal
from trading.constants import BROKER_ALPACA, BROKER_KALSHI, BROKER_ROBINHOOD
from trading.models import BrokerConnection
from trading.services.brokers import OrderFill


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
            user=self.user,
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
        first = ingest_signal(self.user, payload)
        second = ingest_signal(self.user, payload)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(HarnessSignal.objects.filter(user=self.user).count(), 1)

    def test_caps_reject_exposure(self):
        self.account.max_dollar_exposure = Decimal("100")
        self.account.save()
        with self.assertRaises(Exception) as ctx:
            ingest_signal(
                self.user,
                {
                    "ref_id": "sig-cap",
                    "account_slug": "prop-desk",
                    "symbol": "TSLA",
                    "entry_rule": {"type": "limit", "price": "5.00"},
                    "size": 2,
                },
            )
        self.assertIn("max dollar exposure", str(ctx.exception).lower())

    def test_check_caps_open_positions(self):
        self.account.max_open_positions = 1
        self.account.save(update_fields=["max_open_positions"])
        HarnessSignal.objects.create(
            user=self.user,
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
        mock_harness = MagicMock()
        mock_harness.get_quote.side_effect = [
            MarketQuote(mark=Decimal("1.20")),
            MarketQuote(mark=Decimal("0.40")),
        ]
        mock_harness.place_limit_entry.return_value = OrderFill("b1", "filled", 1, Decimal("1.20"))
        mock_harness.place_limit_exit.return_value = OrderFill("s1", "filled", 1, Decimal("2.00"))
        desk_for.return_value = MagicMock(harness_client=lambda: mock_harness)

        signal = HarnessSignal.objects.create(
            user=self.user,
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

    @patch("execution.services.adapters.KalshiRestClient")
    @patch("execution.services.broker_credentials.kalshi_config_for")
    def test_kalshi_desk_snapshot(self, cfg_for, client_cls):
        from execution.services.kalshi_api import KalshiConfig

        cfg_for.return_value = KalshiConfig(
            api_key_id="k", private_key_pem="x", base_url="https://demo-api.kalshi.co/trade-api/v2"
        )
        client_cls.return_value.balance.return_value = {"balance": {"balance": 2500}}
        self.connection.broker = BROKER_KALSHI
        self.connection.save(update_fields=["broker", "updated_at"])
        adapter = KalshiDeskAdapter(self.connection, "prop-desk", "Kalshi", dry_run=True)
        snap = adapter.snapshot_accounts()[0]
        self.assertEqual(snap.broker, BROKER_KALSHI)
        self.assertTrue(snap.trading_enabled)

    def test_stub_desk_adapter_snapshot(self):
        adapter = StubDeskAdapter(self.connection, "prop-desk", "label", True)
        snaps = adapter.snapshot_accounts()
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].buying_power, Decimal("50000"))

    @override_settings(EXECUTION_MCP_ADMIN_BEARER="")
    def test_mcp_pat_auth_and_ingest(self):
        raw, _ = generate_pat(self.user, "test-agent")
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
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(HarnessSignal.objects.filter(user=self.user, ref_id="mcp-1").exists())

    @patch("execution.services.adapters.list_accounts_for")
    def test_robinhood_adapter_mocked(self, list_accounts):
        from execution.services.adapters import RobinhoodDeskAdapter

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
            mcp_for.return_value.call_tool.return_value = {}
            with patch("execution.services.adapters.portfolio_equity", return_value=Decimal("10000")):
                with patch(
                    "execution.services.adapters.portfolio_spendable", return_value=Decimal("8000")
                ):
                    snaps = adapter.snapshot_accounts()
        self.assertEqual(snaps[0].broker_account_id, "RH123")

    @patch("execution.services.rules_engine.desk_adapter_for")
    def test_rules_engine_time_exit(self, desk_for):
        mock_harness = MagicMock()
        mock_harness.get_quote.return_value = MarketQuote(mark=Decimal("1.50"))
        desk_for.return_value = MagicMock(harness_client=lambda: mock_harness)

        past = timezone.now() - timedelta(minutes=5)
        signal = HarnessSignal.objects.create(
            user=self.user,
            ref_id="time-exit-1",
            execution_account=self.account,
            symbol="AAPL",
            option_type="call",
            strike=Decimal("200"),
            expiration=date.today() + timedelta(days=30),
            quantity=1,
            status=SIGNAL_OPEN,
            time_exit_at=past,
        )
        HarnessPosition.objects.create(
            signal=signal,
            execution_account=self.account,
            quantity=1,
            remaining_quantity=1,
            average_entry_price=Decimal("1.20"),
            status=POSITION_OPEN,
            opened_at=timezone.now(),
        )
        evaluate_signal(signal)
        signal.refresh_from_db()
        self.assertEqual(signal.status, "closed")

    @patch("execution.services.rules_engine.desk_adapter_for")
    def test_rules_engine_take_profit_target(self, desk_for):
        mock_harness = MagicMock()
        mock_harness.get_quote.return_value = MarketQuote(mark=Decimal("3.00"))
        desk_for.return_value = MagicMock(harness_client=lambda: mock_harness)

        signal = HarnessSignal.objects.create(
            user=self.user,
            ref_id="target-1",
            execution_account=self.account,
            symbol="AAPL",
            option_type="call",
            strike=Decimal("200"),
            expiration=date.today() + timedelta(days=30),
            quantity=2,
            targets=[{"price": "2.50", "quantity": 1}],
            status=SIGNAL_OPEN,
        )
        HarnessPosition.objects.create(
            signal=signal,
            execution_account=self.account,
            quantity=2,
            remaining_quantity=2,
            average_entry_price=Decimal("1.20"),
            targets=[{"price": "2.50", "quantity": 1}],
            status=POSITION_OPEN,
            opened_at=timezone.now(),
        )
        evaluate_signal(signal)
        signal.refresh_from_db()
        self.assertEqual(signal.status, SIGNAL_OPEN)
        signal.position.refresh_from_db()
        self.assertEqual(signal.position.remaining_quantity, 1)

    @override_settings(EXECUTION_DRY_RUN_DEFAULT=False)
    @patch("execution.services.rules_engine.desk_adapter_for")
    def test_no_duplicate_working_exit_orders(self, desk_for):
        self.account.dry_run = False
        self.account.save(update_fields=["dry_run"])
        mock_harness = MagicMock()
        mock_harness.get_quote.return_value = MarketQuote(mark=Decimal("0.40"))
        mock_harness.place_limit_exit.return_value = OrderFill("live-exit", "open", 0, Decimal("0.40"))
        desk_for.return_value = MagicMock(harness_client=lambda: mock_harness)

        signal = HarnessSignal.objects.create(
            user=self.user,
            ref_id="dup-exit-1",
            execution_account=self.account,
            symbol="AAPL",
            option_type="call",
            strike=Decimal("200"),
            expiration=date.today() + timedelta(days=30),
            quantity=1,
            stop_price=Decimal("0.50"),
            status=SIGNAL_OPEN,
        )
        HarnessPosition.objects.create(
            signal=signal,
            execution_account=self.account,
            quantity=1,
            remaining_quantity=1,
            average_entry_price=Decimal("1.20"),
            stop_price=Decimal("0.50"),
            status=POSITION_OPEN,
            opened_at=timezone.now(),
        )
        evaluate_signal(signal)
        evaluate_signal(signal)
        exit_orders = HarnessOrder.objects.filter(signal=signal, purpose=ORDER_EXIT, status=ORDER_WORKING)
        self.assertEqual(exit_orders.count(), 1)

    def test_cancel_signal_idempotent(self):
        ingest_signal(
            self.user,
            {
                "ref_id": "cancel-1",
                "account_slug": "prop-desk",
                "symbol": "SPY",
                "entry_rule": {"price": "1"},
                "size": 1,
            },
        )
        first = cancel_signal(self.user, {"ref_id": "cancel-1"})
        second = cancel_signal(self.user, {"ref_id": "cancel-1"})
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])

    @override_settings(EXECUTION_MCP_ADMIN_BEARER="")
    @patch("execution.services.rules_engine.desk_adapter_for")
    def test_mcp_e2e_dry_run_watcher(self, desk_for):
        mock_harness = MagicMock()
        mock_harness.get_quote.side_effect = [
            MarketQuote(mark=Decimal("1.00")),
            MarketQuote(mark=Decimal("0.40")),
        ]
        mock_harness.place_limit_entry.return_value = OrderFill("b1", "filled", 1, Decimal("1.00"))
        mock_harness.place_limit_exit.return_value = OrderFill("s1", "filled", 1, Decimal("2.00"))
        desk_for.return_value = MagicMock(harness_client=lambda: mock_harness)

        raw, _ = generate_pat(self.user, "watcher-e2e")
        client = Client()
        ingest_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ingest_signal",
                "arguments": {
                    "ref_id": "e2e-1",
                    "account_slug": "prop-desk",
                    "symbol": "AAPL",
                    "option_type": "call",
                    "strike": "200",
                    "expiration": (date.today() + timedelta(days=30)).isoformat(),
                    "entry_rule": {"type": "limit", "price": "1.25"},
                    "stop": "0.50",
                    "size": 1,
                },
            },
        }
        client.post(
            "/api/mcp/execution/",
            data=ingest_payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )
        self.assertEqual(evaluate_all_signals(), 1)
        signal = HarnessSignal.objects.get(user=self.user, ref_id="e2e-1")
        self.assertEqual(signal.status, SIGNAL_OPEN)
        self.assertEqual(evaluate_all_signals(), 1)
        signal.refresh_from_db()
        self.assertEqual(signal.status, "closed")


class ExecutionDryRunEnforcedTests(TestCase):
    @override_settings(EXECUTION_DRY_RUN_DEFAULT=True)
    def test_journal_on_ingest(self):
        user = User.objects.create_user(username="u2", email="u2@example.com", password="x")
        conn = BrokerConnection.objects.create(user=user, broker=BROKER_ALPACA, is_paper=True)
        ExecutionAccount.objects.create(
            user=user, slug="desk2", label="Desk", broker_connection=conn, dry_run=True
        )
        ingest_signal(
            user,
            {
                "ref_id": "j-1",
                "account_slug": "desk2",
                "symbol": "SPY",
                "entry_rule": {"price": "1"},
                "size": 1,
            },
        )
        self.assertTrue(HarnessJournal.objects.filter(user=user, action="signal_ingested").exists())
