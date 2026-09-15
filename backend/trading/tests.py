from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from trading.constants import STRATEGY_COPY_TRADE
from trading.models import (
    AccountTradingState,
    BrokerConnection,
    BrokerOrder,
    Decision,
    InvestmentTier,
    Notification,
    Position,
    Signal,
    SignalDecision,
    Strategy,
    Trade,
    TradeEvent,
    UserStrategyAssignment,
    XAccountSource,
)
from trading.services.brokers import OrderFill
from trading.services.jobs import set_assignment
from trading.services.position_manager import manage_position
from trading.services.signal_engine import process_pending_signals, process_signal
from trading.services.tier_rules import position_size, slippage_exceeded
from trading.services.x_watcher import ingest_tweet


class TradingMixin:
    def seed(self):
        from django.core.management import call_command

        call_command("seed_trading")
        self.conservative = InvestmentTier.objects.get(slug="conservative")
        self.balanced = InvestmentTier.objects.get(slug="balanced")
        self.aggressive = InvestmentTier.objects.get(slug="aggressive")
        self.strategy = Strategy.objects.get(slug=STRATEGY_COPY_TRADE)

    def make_user(self, username="trader", entitled=True):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="longpassword1",
        )
        if entitled:
            from billing.services.entitlements import grant_subscription

            grant_subscription(email=user.email, plan_slug="yearly", note="test")
        return user

    def connect_broker(self, user, equity="100000.00"):
        return BrokerConnection.objects.create(
            user=user,
            broker="alpaca",
            status=BrokerConnection.Status.CONNECTED,
            is_paper=True,
            last_equity=equity,
        )

    def make_signal(self, **kwargs):
        defaults = {
            "strategy": self.strategy,
            "ticker": "AAPL",
            "option_type": "call",
            "strike": "200.00",
            "expiration": "2026-12-18",
            "suggested_entry_price": "2.00",
            "quote_price": "2.00",
        }
        defaults.update(kwargs)
        return Signal.objects.create(**defaults)


class TradingApiTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_lists_require_auth(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/strategies/").status_code, 401)
        self.assertEqual(anon.get("/api/investment-tiers/").status_code, 401)

    def test_list_strategies_and_tiers(self):
        strategies = self.client.get("/api/strategies/")
        self.assertEqual(strategies.status_code, 200)
        names = [row["slug"] for row in strategies.json()["results"]]
        self.assertIn("copy-trade", names)
        self.assertIsInstance(strategies.json()["results"][0]["id"], int)

        tiers = self.client.get("/api/investment-tiers/")
        self.assertEqual(tiers.status_code, 200)
        slugs = {row["slug"] for row in tiers.json()["results"]}
        self.assertEqual(slugs, {"conservative", "balanced", "aggressive"})

    def test_select_assignment_and_connect_broker(self):
        resp = self.client.put(
            "/api/assignment/",
            {
                "strategy_id": self.strategy.id,
                "investment_tier_id": self.balanced.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["strategy"]["slug"], "copy-trade")
        self.assertEqual(resp.json()["investment_tier"]["slug"], "balanced")
        self.assertIsInstance(resp.json()["id"], int)

        connect = self.client.post(
            "/api/broker-connections/",
            {
                "broker": "alpaca",
                "api_key": "key",
                "api_secret": "secret",
                "is_paper": True,
            },
            format="json",
        )
        self.assertEqual(connect.status_code, 201)
        self.assertNotIn("encrypted_credentials", connect.json())
        self.assertNotIn("api_secret", connect.json())
        pk = connect.json()["id"]
        listed = self.client.get("/api/broker-connections/")
        self.assertEqual(len(listed.json()), 1)
        disconnect = self.client.post(f"/api/broker-connections/{pk}/disconnect/")
        self.assertEqual(disconnect.status_code, 200)
        self.assertEqual(self.client.get("/api/broker-connections/").json(), [])

    def test_alpaca_account_detail_includes_strategy_and_performance(self):
        self.client.put(
            "/api/assignment/",
            {
                "strategy_id": self.strategy.id,
                "investment_tier_id": self.balanced.id,
            },
            format="json",
        )
        connect = self.client.post(
            "/api/broker-connections/",
            {
                "broker": "alpaca",
                "api_key": "key",
                "api_secret": "secret",
                "is_paper": True,
            },
            format="json",
        )
        pk = connect.json()["id"]
        resp = self.client.get(f"/api/broker-connections/{pk}/accounts/default/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["assignment"]["strategy"]["slug"], "copy-trade")
        self.assertEqual(body["assignment"]["investment_tier"]["slug"], "balanced")
        self.assertIn("lifetime_total_pnl", body["performance"])
        self.assertTrue(body["trading_enabled"])

    def test_performance_includes_lifetime_pnl(self):
        resp = self.client.get("/api/performance/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("lifetime_realized_pnl", resp.json())
        self.assertIn("lifetime_total_pnl", resp.json())


class SignalWorkflowTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.connect_broker(self.user)
        set_assignment(self.user, self.strategy, self.balanced)

    def test_enters_trade_for_assigned_user(self):
        signal = self.make_signal()
        decisions = process_signal(signal, live_price=signal.suggested_entry_price)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].outcome, SignalDecision.Outcome.ENTERED)
        trade = Trade.objects.get(user=self.user)
        self.assertIsInstance(trade.id, int)
        self.assertGreater(trade.entry_quantity, 0)
        self.assertEqual(Position.objects.filter(user=self.user, status="open").count(), 1)
        self.assertTrue(
            Notification.objects.filter(user=self.user, kind=Notification.Kind.ENTRY).exists()
        )
        signal.refresh_from_db()
        self.assertEqual(signal.status, Signal.Status.PROCESSED)
        self.assertTrue(signal.code.startswith("SIG-"))

    def test_stamps_and_filters_trades_by_broker_account(self):
        connection = BrokerConnection.objects.get(user=self.user)
        connection.broker_account_id = "222"
        connection.save(update_fields=["broker_account_id", "updated_at"])
        assignment = UserStrategyAssignment.objects.get(user=self.user, is_active=True)
        assignment.broker_account_id = "222"
        assignment.save(update_fields=["broker_account_id", "updated_at"])
        process_signal(self.make_signal(), live_price="2.00")
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.broker_account_id, "222")
        self.assertEqual(
            Notification.objects.get(user=self.user, kind=Notification.Kind.ENTRY).broker_account_id,
            "222",
        )
        client = APIClient()
        client.force_authenticate(self.user)
        listed = client.get("/api/trades/", {"broker_account_id": "222"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        empty = client.get("/api/trades/", {"broker_account_id": "999"})
        self.assertEqual(empty.json()["count"], 0)

    def test_skips_entry_without_paid_subscription(self):
        unpaid = self.make_user("unpaid", entitled=False)
        self.connect_broker(unpaid)
        set_assignment(unpaid, self.strategy, self.balanced)
        decisions = process_signal(self.make_signal(), live_price="2.00")
        skipped = next(row for row in decisions if row.user_id == unpaid.id)
        self.assertEqual(skipped.outcome, SignalDecision.Outcome.SKIPPED)
        self.assertEqual(skipped.skip_reason, SignalDecision.SkipReason.SUBSCRIPTION_REQUIRED)
        self.assertFalse(Trade.objects.filter(user=unpaid).exists())

    def test_records_unfilled_order_without_opening_a_position(self):
        signal = self.make_signal()
        fill = OrderFill(
            broker_order_id="rh-unfilled-1",
            status="cancelled",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            decisions = process_signal(signal, live_price=signal.suggested_entry_price)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].outcome, SignalDecision.Outcome.SKIPPED)
        self.assertEqual(decisions[0].skip_reason, SignalDecision.SkipReason.UNFILLED)
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.status, Trade.Status.CANCELLED)
        self.assertEqual(trade.remaining_quantity, 0)
        self.assertGreater(trade.entry_quantity, 0)
        self.assertFalse(Position.objects.filter(trade=trade).exists())
        event = TradeEvent.objects.get(trade=trade)
        self.assertEqual(event.event_type, TradeEvent.EventType.UNFILLED)
        order = BrokerOrder.objects.get(trade=trade)
        self.assertEqual(order.broker_order_id, "rh-unfilled-1")
        self.assertEqual(order.status, BrokerOrder.Status.CANCELLED)
        self.assertEqual(order.filled_quantity, 0)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, kind=Notification.Kind.SKIP, trade=trade
            ).exists()
        )
        client = APIClient()
        client.force_authenticate(self.user)
        detail = client.get(f"/api/trades/{trade.id}/")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["status"], "cancelled")
        self.assertEqual(body["orders"][0]["broker_order_id"], "rh-unfilled-1")
        self.assertEqual(body["events"][0]["event_type"], "unfilled")

    def test_submitted_limit_order_stays_pending_until_fill(self):
        signal = self.make_signal()
        fill = OrderFill(
            broker_order_id="rh-working-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            decisions = process_signal(signal, live_price=signal.suggested_entry_price)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].outcome, SignalDecision.Outcome.ENTERED)
        self.assertEqual(decisions[0].skip_reason, "")
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.status, Trade.Status.PENDING)
        self.assertEqual(trade.remaining_quantity, trade.entry_quantity)
        self.assertGreater(trade.entry_quantity, 0)
        self.assertIsNone(trade.closed_at)
        self.assertFalse(Position.objects.filter(trade=trade).exists())
        event = TradeEvent.objects.get(trade=trade)
        self.assertEqual(event.event_type, TradeEvent.EventType.SUBMITTED)
        order = BrokerOrder.objects.get(trade=trade)
        self.assertEqual(order.broker_order_id, "rh-working-1")
        self.assertEqual(order.status, BrokerOrder.Status.SUBMITTED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, kind=Notification.Kind.ENTRY, trade=trade
            ).exists()
        )
        log = Decision.objects.get(signal_decision=decisions[0])
        self.assertTrue(log.title.startswith("Placed "))
        client = APIClient()
        client.force_authenticate(self.user)
        detail = client.get(f"/api/trades/{trade.id}/")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["orders"][0]["status"], "submitted")
        self.assertEqual(body["events"][0]["event_type"], "submitted")

    def test_pending_limit_counts_toward_max_open_positions(self):
        self.balanced.max_open_positions = 1
        self.balanced.save()
        fill = OrderFill(
            broker_order_id="rh-working-cap-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            process_signal(self.make_signal(ticker="AAPL"), live_price="2.00")
        process_signal(self.make_signal(ticker="MSFT"), live_price="2.00")
        self.assertEqual(Trade.objects.filter(user=self.user).count(), 1)
        skipped = SignalDecision.objects.filter(
            user=self.user, outcome=SignalDecision.Outcome.SKIPPED
        ).first()
        self.assertEqual(skipped.skip_reason, SignalDecision.SkipReason.MAX_OPEN_POSITIONS)

    def test_reconcile_promotes_working_order_when_broker_fills(self):
        from trading.services.order_sync import reconcile_working_orders

        fill = OrderFill(
            broker_order_id="rh-working-fill-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            process_signal(self.make_signal(), live_price="2.00")
        trade = Trade.objects.get(user=self.user)
        filled = OrderFill(
            broker_order_id="rh-working-fill-1",
            status="filled",
            filled_quantity=trade.entry_quantity,
            filled_avg_price=Decimal("1.95"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.get_order",
            return_value=filled,
        ):
            self.assertEqual(reconcile_working_orders(), 1)
        trade.refresh_from_db()
        self.assertEqual(trade.status, Trade.Status.OPEN)
        self.assertEqual(trade.remaining_quantity, trade.entry_quantity)
        self.assertEqual(trade.entry_price, Decimal("1.95"))
        position = Position.objects.get(trade=trade)
        self.assertEqual(position.status, Position.Status.OPEN)
        self.assertEqual(position.quantity, trade.entry_quantity)
        self.assertTrue(
            trade.events.filter(event_type=TradeEvent.EventType.ENTRY).exists()
        )
        self.assertEqual(
            BrokerOrder.objects.get(trade=trade).status, BrokerOrder.Status.FILLED
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.user, kind=Notification.Kind.ENTRY, title__startswith="Filled "
            ).exists()
        )

    def test_reconcile_marks_working_order_cancelled_when_broker_cancels(self):
        from trading.services.order_sync import reconcile_working_orders

        fill = OrderFill(
            broker_order_id="rh-working-cancel-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            process_signal(self.make_signal(), live_price="2.00")
        cancelled = OrderFill(
            broker_order_id="rh-working-cancel-1",
            status="cancelled",
            filled_quantity=0,
            filled_avg_price=Decimal("2.00"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.get_order",
            return_value=cancelled,
        ):
            self.assertEqual(reconcile_working_orders(), 1)
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.status, Trade.Status.CANCELLED)
        self.assertEqual(trade.remaining_quantity, 0)
        self.assertIsNotNone(trade.closed_at)
        self.assertFalse(Position.objects.filter(trade=trade).exists())
        self.assertTrue(
            trade.events.filter(event_type=TradeEvent.EventType.UNFILLED).exists()
        )
        self.assertEqual(
            BrokerOrder.objects.get(trade=trade).status, BrokerOrder.Status.CANCELLED
        )

    def test_reconcile_repairs_cancelled_trade_with_live_submitted_order(self):
        from trading.services.order_sync import reconcile_working_orders

        fill = OrderFill(
            broker_order_id="rh-ko-placed-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("0.39"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            process_signal(self.make_signal(ticker="KO"), live_price="0.39")
        trade = Trade.objects.get(user=self.user)
        trade.status = Trade.Status.CANCELLED
        trade.remaining_quantity = 0
        trade.closed_at = timezone.now()
        trade.save(update_fields=["status", "remaining_quantity", "closed_at", "updated_at"])
        decision = SignalDecision.objects.get(trade=trade)
        decision.outcome = SignalDecision.Outcome.SKIPPED
        decision.skip_reason = SignalDecision.SkipReason.UNFILLED
        decision.save(update_fields=["outcome", "skip_reason"])
        still_live = OrderFill(
            broker_order_id="rh-ko-placed-1",
            status="submitted",
            filled_quantity=0,
            filled_avg_price=Decimal("0.39"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.get_order",
            return_value=still_live,
        ):
            self.assertEqual(reconcile_working_orders(), 1)
        trade.refresh_from_db()
        decision.refresh_from_db()
        self.assertEqual(trade.status, Trade.Status.PENDING)
        self.assertEqual(trade.remaining_quantity, trade.entry_quantity)
        self.assertIsNone(trade.closed_at)
        self.assertEqual(decision.outcome, SignalDecision.Outcome.ENTERED)
        self.assertEqual(decision.skip_reason, "")
        self.assertFalse(Position.objects.filter(trade=trade).exists())

    def test_imports_filled_broker_order_after_skip(self):
        from datetime import date

        from trading.services.order_sync import reconcile_working_orders

        connection = BrokerConnection.objects.get(user=self.user)
        connection.last_equity = Decimal("10.00")
        connection.save(update_fields=["last_equity", "updated_at"])
        signal = self.make_signal(
            ticker="KO",
            strike="91.00",
            expiration="2026-08-21",
            suggested_entry_price="5.00",
            quote_price="5.00",
        )
        process_signal(signal, live_price="5.00")
        decision = SignalDecision.objects.get(user=self.user, signal=signal)
        self.assertEqual(decision.skip_reason, SignalDecision.SkipReason.SIZE_ZERO)
        self.assertFalse(Trade.objects.filter(user=self.user).exists())
        filled_order = {
            "broker_order_id": "rh-ko-filled-1",
            "status": "filled",
            "filled_quantity": 1,
            "filled_avg_price": Decimal("0.39"),
            "quantity": 1,
            "side": "buy",
            "position_effect": "open",
            "ticker": "KO",
            "option_type": "call",
            "strike": Decimal("91.00"),
            "expiration": date(2026, 8, 21),
        }
        with patch(
            "trading.services.brokers.StubBrokerClient.list_option_orders",
            return_value=[filled_order],
        ):
            self.assertGreaterEqual(reconcile_working_orders(), 1)
        trade = Trade.objects.get(user=self.user, ticker="KO")
        self.assertEqual(trade.status, Trade.Status.OPEN)
        self.assertEqual(trade.entry_price, Decimal("0.39"))
        self.assertEqual(trade.remaining_quantity, 1)
        self.assertTrue(Position.objects.filter(trade=trade, status=Position.Status.OPEN).exists())
        order = BrokerOrder.objects.get(trade=trade)
        self.assertEqual(order.status, BrokerOrder.Status.FILLED)
        self.assertEqual(order.filled_quantity, 1)
        decision.refresh_from_db()
        self.assertEqual(decision.outcome, SignalDecision.Outcome.ENTERED)
        self.assertEqual(decision.trade_id, trade.id)
        self.assertTrue(
            trade.events.filter(event_type=TradeEvent.EventType.ENTRY).exists()
        )

    def test_promotes_cancelled_trade_when_broker_later_fills(self):
        from datetime import date

        from trading.services.order_sync import reconcile_working_orders

        fill = OrderFill(
            broker_order_id="rh-ko-cancel-then-fill",
            status="cancelled",
            filled_quantity=0,
            filled_avg_price=Decimal("0.39"),
        )
        with patch(
            "trading.services.brokers.StubBrokerClient.buy_to_open",
            return_value=fill,
        ):
            process_signal(
                self.make_signal(
                    ticker="KO",
                    strike="91.00",
                    expiration="2026-08-21",
                    suggested_entry_price="0.39",
                ),
                live_price="0.39",
            )
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.status, Trade.Status.CANCELLED)
        filled_order = {
            "broker_order_id": "rh-ko-cancel-then-fill",
            "status": "filled",
            "filled_quantity": 1,
            "filled_avg_price": Decimal("0.39"),
            "quantity": 1,
            "side": "buy",
            "position_effect": "open",
            "ticker": "KO",
            "option_type": "call",
            "strike": Decimal("91.00"),
            "expiration": date(2026, 8, 21),
        }
        with patch(
            "trading.services.brokers.StubBrokerClient.list_option_orders",
            return_value=[filled_order],
        ), patch(
            "trading.services.brokers.StubBrokerClient.get_order",
            return_value=OrderFill(
                broker_order_id="rh-ko-cancel-then-fill",
                status="filled",
                filled_quantity=1,
                filled_avg_price=Decimal("0.39"),
            ),
        ):
            self.assertGreaterEqual(reconcile_working_orders(), 1)
        trade.refresh_from_db()
        self.assertEqual(trade.status, Trade.Status.OPEN)
        self.assertEqual(trade.remaining_quantity, 1)
        self.assertIsNone(trade.closed_at)
        self.assertTrue(Position.objects.filter(trade=trade, status=Position.Status.OPEN).exists())
        self.assertEqual(
            BrokerOrder.objects.get(trade=trade).status, BrokerOrder.Status.FILLED
        )

    def test_skip_on_slippage(self):
        signal = self.make_signal(suggested_entry_price="2.00")
        process_signal(signal, live_price="3.00")
        decision = SignalDecision.objects.get(user=self.user, signal=signal)
        self.assertEqual(decision.outcome, SignalDecision.Outcome.SKIPPED)
        self.assertEqual(decision.skip_reason, SignalDecision.SkipReason.SLIPPAGE)
        self.assertFalse(Trade.objects.filter(user=self.user).exists())

    def test_skip_on_max_open_positions(self):
        self.balanced.max_open_positions = 1
        self.balanced.save()
        process_signal(self.make_signal(ticker="AAPL"), live_price="2.00")
        process_signal(self.make_signal(ticker="MSFT"), live_price="2.00")
        self.assertEqual(Trade.objects.filter(user=self.user).count(), 1)
        skipped = SignalDecision.objects.filter(
            user=self.user, outcome=SignalDecision.Outcome.SKIPPED
        ).first()
        self.assertEqual(skipped.skip_reason, SignalDecision.SkipReason.MAX_OPEN_POSITIONS)

    def test_skip_without_broker(self):
        BrokerConnection.objects.filter(user=self.user).delete()
        process_signal(self.make_signal(), live_price="2.00")
        decision = SignalDecision.objects.get(user=self.user)
        self.assertEqual(decision.skip_reason, SignalDecision.SkipReason.NO_BROKER)

    def test_skips_when_strategy_bound_to_other_account(self):
        connection = BrokerConnection.objects.get(user=self.user)
        connection.broker_account_id = "aaa"
        connection.save(update_fields=["broker_account_id", "updated_at"])
        assignment = UserStrategyAssignment.objects.get(user=self.user, is_active=True)
        assignment.broker_account_id = "bbb"
        assignment.save(update_fields=["broker_account_id", "updated_at"])
        process_signal(self.make_signal(), live_price="2.00")
        decision = SignalDecision.objects.get(user=self.user)
        self.assertEqual(decision.skip_reason, SignalDecision.SkipReason.WRONG_ACCOUNT)
        self.assertFalse(Trade.objects.filter(user=self.user).exists())

    def test_same_signal_different_tiers_different_size(self):
        other = self.make_user("aggressive-user")
        self.connect_broker(other)
        set_assignment(other, self.strategy, self.aggressive)
        signal = self.make_signal()
        process_signal(signal, live_price="2.00")
        balanced_qty = Trade.objects.get(user=self.user).entry_quantity
        aggressive_qty = Trade.objects.get(user=other).entry_quantity
        self.assertGreater(aggressive_qty, balanced_qty)

    def test_small_account_enters_one_contract_when_premium_is_affordable(self):
        BrokerConnection.objects.filter(user=self.user).update(last_equity="100.00")
        signal = self.make_signal(suggested_entry_price="0.80")
        process_signal(signal, live_price="0.80")
        trade = Trade.objects.get(user=self.user)
        self.assertEqual(trade.entry_quantity, 1)
        log = Decision.objects.get(user=self.user, signal=signal)
        self.assertEqual(log.reason_code, Decision.Reason.TIER_SIZE)
        self.assertIn("Starter size", log.summary)

    def test_small_account_skips_when_one_contract_costs_more_than_cash(self):
        BrokerConnection.objects.filter(user=self.user).update(last_equity="100.00")
        signal = self.make_signal(suggested_entry_price="2.00")
        process_signal(signal, live_price="2.00")
        decision = SignalDecision.objects.get(user=self.user, signal=signal)
        self.assertEqual(decision.outcome, SignalDecision.Outcome.SKIPPED)
        self.assertEqual(decision.skip_reason, SignalDecision.SkipReason.SIZE_ZERO)
        self.assertFalse(Trade.objects.filter(user=self.user).exists())
        log = Decision.objects.get(user=self.user, signal=signal)
        self.assertIn("more than", log.summary)

    def test_insufficient_funds_skip_is_recorded_on_the_assigned_account(self):
        connection = BrokerConnection.objects.get(user=self.user)
        connection.broker_account_id = "agentic-1"
        connection.last_equity = Decimal("125.00")
        connection.save(update_fields=["broker_account_id", "last_equity", "updated_at"])
        assignment = UserStrategyAssignment.objects.get(user=self.user, is_active=True)
        assignment.broker_account_id = "agentic-1"
        assignment.save(update_fields=["broker_account_id", "updated_at"])
        signal = self.make_signal(suggested_entry_price="2.00")
        process_signal(signal, live_price="2.00")
        log = Decision.objects.get(user=self.user, signal=signal)
        self.assertEqual(log.outcome, Decision.Outcome.PASSED)
        self.assertEqual(log.action, Decision.Action.SKIP)
        self.assertEqual(log.broker_account_id, "agentic-1")
        note = Notification.objects.get(user=self.user, kind=Notification.Kind.SKIP)
        self.assertEqual(note.broker_account_id, "agentic-1")
        self.assertEqual(note.decision_id, log.id)
        self.assertIn("more than", note.body)

    def test_process_pending_retries_processed_signal_with_no_decisions(self):
        signal = self.make_signal()
        signal.status = Signal.Status.PROCESSED
        signal.save(update_fields=["status"])
        self.assertFalse(SignalDecision.objects.filter(signal=signal).exists())
        count = process_pending_signals()
        self.assertGreaterEqual(count, 1)
        self.assertTrue(
            SignalDecision.objects.filter(signal=signal, user=self.user).exists()
        )

    def test_idempotent_signal_processing(self):
        signal = self.make_signal()
        process_signal(signal, live_price="2.00")
        process_signal(signal, live_price="2.00")
        self.assertEqual(SignalDecision.objects.filter(signal=signal, user=self.user).count(), 1)
        self.assertEqual(Trade.objects.filter(user=self.user).count(), 1)


class PositionManagementTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.connect_broker(self.user)
        set_assignment(self.user, self.strategy, self.conservative)
        signal = self.make_signal()
        process_signal(signal, live_price="2.00")
        self.position = Position.objects.get(user=self.user)
        self.trade = self.position.trade

    def test_take_profit_partial_close(self):
        entry = self.trade.entry_price
        tp_price = entry * 2  # +100% would hit first conservative TP at +50%
        manage_position(self.position, quote=tp_price)
        self.trade.refresh_from_db()
        self.position.refresh_from_db()
        self.assertEqual(self.trade.status, Trade.Status.PARTIALLY_CLOSED)
        self.assertLess(self.position.quantity, self.trade.entry_quantity)
        self.assertGreater(self.trade.realized_pnl, 0)

    def test_hard_stop_closes_position(self):
        stop_price = self.trade.entry_price * (1 - Decimal("0.45"))
        manage_position(self.position, quote=stop_price)
        self.trade.refresh_from_db()
        self.position.refresh_from_db()
        self.assertEqual(self.trade.status, Trade.Status.CLOSED)
        self.assertEqual(self.position.status, Position.Status.CLOSED)
        self.assertLess(self.trade.realized_pnl, 0)

    def test_lifetime_pnl_tracks_realized(self):
        stop_price = self.trade.entry_price * (1 - Decimal("0.45"))
        manage_position(self.position, quote=stop_price)
        self.trade.refresh_from_db()
        state = AccountTradingState.objects.get(user=self.user)
        self.assertEqual(state.lifetime_realized_pnl, self.trade.realized_pnl)

    def test_missing_option_quote_does_not_crash_the_monitor(self):
        from trading.services.brokers import BrokerError
        from trading.services.position_manager import monitor_open_positions

        with patch(
            "trading.services.brokers.StubBrokerClient.get_option_quote",
            side_effect=BrokerError("No Robinhood option instrument"),
        ):
            count = monitor_open_positions()
        self.position.refresh_from_db()
        self.assertEqual(self.position.status, Position.Status.OPEN)
        self.assertGreaterEqual(count, 1)

    def test_expired_position_settles_when_the_instrument_is_gone(self):
        from datetime import date

        from trading.services.brokers import BrokerError

        self.position.expiration = date(2020, 1, 1)
        self.position.save(update_fields=["expiration", "updated_at"])
        self.trade.expiration = date(2020, 1, 1)
        self.trade.save(update_fields=["expiration", "updated_at"])
        with patch(
            "trading.services.brokers.StubBrokerClient.get_option_market",
            side_effect=BrokerError("No Robinhood option instrument"),
        ), patch(
            "trading.services.brokers.StubBrokerClient.sell_to_close",
            side_effect=BrokerError("No Robinhood option instrument"),
        ):
            result = manage_position(self.position)
        self.assertEqual(result, "expiration_exit")
        self.position.refresh_from_db()
        self.trade.refresh_from_db()
        self.assertEqual(self.position.status, Position.Status.CLOSED)
        self.assertEqual(self.trade.status, Trade.Status.CLOSED)

    def test_expiration_day_before_force_exit_stays_open(self):
        from datetime import datetime

        from trading.constants import ET
        from trading.services.brokers import OptionQuote, StubBrokerClient

        now = datetime(2026, 8, 21, 11, 0, tzinfo=ET)
        self.position.expiration = now.date()
        self.position.save(update_fields=["expiration", "updated_at"])
        self.trade.expiration = now.date()
        self.trade.save(update_fields=["expiration", "updated_at"])
        market = OptionQuote(mark=Decimal("1.80"), bid=Decimal("1.75"))
        with patch.object(StubBrokerClient, "get_option_market", return_value=market):
            result = manage_position(self.position, now=now)
        self.assertIsNone(result)
        self.position.refresh_from_db()
        self.assertEqual(self.position.status, Position.Status.OPEN)
        self.assertEqual(self.position.current_price, Decimal("1.80"))

    def test_expiration_day_force_exit_sells_at_the_bid(self):
        from datetime import datetime

        from trading.constants import ET
        from trading.services.brokers import OptionQuote, StubBrokerClient

        now = datetime(2026, 8, 21, 15, 46, tzinfo=ET)
        self.position.expiration = now.date()
        self.position.save(update_fields=["expiration", "updated_at"])
        self.trade.expiration = now.date()
        self.trade.save(update_fields=["expiration", "updated_at"])
        market = OptionQuote(mark=Decimal("1.80"), bid=Decimal("1.75"))
        with patch.object(StubBrokerClient, "get_option_market", return_value=market):
            result = manage_position(self.position, now=now)
        self.assertEqual(result, "expiration_exit")
        self.trade.refresh_from_db()
        self.position.refresh_from_db()
        self.assertEqual(self.trade.status, Trade.Status.CLOSED)
        self.assertEqual(self.trade.average_exit_price, Decimal("1.75"))

    def test_expiration_day_stop_sells_at_the_bid(self):
        from datetime import datetime

        from trading.constants import ET
        from trading.services.brokers import OptionQuote, StubBrokerClient

        now = datetime(2026, 8, 21, 10, 59, tzinfo=ET)
        self.position.expiration = now.date()
        self.position.save(update_fields=["expiration", "updated_at"])
        self.trade.expiration = now.date()
        self.trade.save(update_fields=["expiration", "updated_at"])
        market = OptionQuote(mark=Decimal("0.12"), bid=Decimal("0.08"))
        with patch.object(StubBrokerClient, "get_option_market", return_value=market):
            result = manage_position(self.position, now=now)
        self.assertEqual(result, "stop_loss")
        self.trade.refresh_from_db()
        self.assertEqual(self.trade.status, Trade.Status.CLOSED)
        self.assertEqual(self.trade.average_exit_price, Decimal("0.08"))


class DecisionTrailTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.connect_broker(self.user)
        set_assignment(self.user, self.strategy, self.balanced)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_enter_creates_acted_decision_and_linked_notification(self):
        signal = self.make_signal()
        process_signal(signal, live_price="2.00")
        log = Decision.objects.get(user=self.user, signal=signal)
        self.assertEqual(log.action, Decision.Action.ENTER)
        self.assertEqual(log.outcome, Decision.Outcome.ACTED)
        self.assertEqual(log.reason_code, Decision.Reason.TIER_SIZE)
        self.assertIn("Balanced", log.summary)
        self.assertIn("hard stop", log.summary)
        note = Notification.objects.get(user=self.user, kind=Notification.Kind.ENTRY)
        self.assertEqual(note.decision_id, log.id)
        self.assertEqual(note.body, log.summary[:255])
        listed = self.client.get("/api/decisions/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        row = listed.json()["results"][0]
        self.assertEqual(row["id"], log.id)
        self.assertEqual(row["outcome"], "acted")
        self.assertEqual(row["notification_id"], note.id)
        detail = self.client.get(f"/api/decisions/{log.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["signal_code"], signal.code)
        trade_detail = self.client.get(f"/api/trades/{log.trade_id}/")
        self.assertEqual(len(trade_detail.json()["decision_logs"]), 1)

    def test_slippage_pass_explains_tier_rule(self):
        signal = self.make_signal(suggested_entry_price="2.00")
        process_signal(signal, live_price="3.00")
        log = Decision.objects.get(user=self.user, signal=signal)
        self.assertEqual(log.action, Decision.Action.SKIP)
        self.assertEqual(log.outcome, Decision.Outcome.PASSED)
        self.assertEqual(log.reason_code, Decision.Reason.SLIPPAGE)
        self.assertIn("slippage", log.summary.lower())
        self.assertIn("Balanced", log.summary)
        note = Notification.objects.get(user=self.user, kind=Notification.Kind.SKIP)
        self.assertEqual(note.decision_id, log.id)
        filtered = self.client.get("/api/decisions/", {"outcome": "passed"})
        self.assertEqual(filtered.json()["count"], 1)

    def test_take_profit_records_exit_decision(self):
        process_signal(self.make_signal(), live_price="2.00")
        position = Position.objects.get(user=self.user)
        trade = position.trade
        manage_position(position, quote=trade.entry_price * 2)
        log = Decision.objects.get(user=self.user, action=Decision.Action.TAKE_PROFIT)
        self.assertEqual(log.outcome, Decision.Outcome.ACTED)
        self.assertIn("take-profit", log.summary.lower())
        self.assertTrue(log.trade_event_id)
        note = Notification.objects.get(user=self.user, kind=Notification.Kind.TAKE_PROFIT)
        self.assertEqual(note.decision_id, log.id)

    def test_user_cannot_read_someone_elses_decision(self):
        process_signal(self.make_signal(), live_price="2.00")
        log = Decision.objects.get(user=self.user)
        other = APIClient()
        other.force_authenticate(self.make_user("other"))
        self.assertEqual(other.get(f"/api/decisions/{log.id}/").status_code, 404)
        self.assertEqual(other.get("/api/decisions/").json()["count"], 0)


class NotificationApiTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_read_all_marks_only_this_users_unread(self):
        unread = [
            Notification.objects.create(
                user=self.user,
                kind=Notification.Kind.SKIP,
                title=f"Unread {i}",
            )
            for i in range(3)
        ]
        already_read = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.ENTRY,
            title="Already read",
            is_read=True,
        )
        other = self.make_user("other")
        other_unread = Notification.objects.create(
            user=other,
            kind=Notification.Kind.SKIP,
            title="Other unread",
        )

        resp = self.client.post("/api/notifications/read-all/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"updated": 3})

        for note in unread:
            note.refresh_from_db()
            self.assertTrue(note.is_read)
        already_read.refresh_from_db()
        self.assertTrue(already_read.is_read)
        other_unread.refresh_from_db()
        self.assertFalse(other_unread.is_read)

        again = self.client.post("/api/notifications/read-all/")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), {"updated": 0})

    def test_read_all_requires_auth(self):
        anon = APIClient()
        self.assertEqual(anon.post("/api/notifications/read-all/").status_code, 401)


class AdminApiTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.admin = User.objects.create_user(
            username="adminuser",
            email="adminuser@example.com",
            password="longpassword1",
            is_staff=True,
        )
        self.user = self.make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_required(self):
        member = APIClient()
        member.force_authenticate(self.user)
        self.assertEqual(member.get("/api/admin/platform-stats/").status_code, 403)

    def test_force_change_tier_and_create_signal(self):
        self.connect_broker(self.user)
        set_assignment(self.user, self.strategy, self.balanced)
        resp = self.client.post(
            "/api/admin/users/assignment/",
            {"user_id": self.user.id, "investment_tier_id": self.aggressive.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["investment_tier"]["slug"], "aggressive")

        created = self.client.post(
            "/api/admin/signals/",
            {
                "strategy": self.strategy.id,
                "ticker": "nvda",
                "option_type": "call",
                "strike": "120.00",
                "expiration": "2026-12-18",
                "suggested_entry_price": "3.00",
                "quote_price": "3.00",
                "notes": "ADDING HEAVY",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(Trade.objects.filter(user=self.user, ticker="NVDA").exists())

        stats = self.client.get("/api/admin/platform-stats/")
        self.assertEqual(stats.status_code, 200)
        self.assertIn("lifetime_realized_pnl", stats.json())
        usage = self.client.get("/api/admin/tier-usage/")
        self.assertEqual(usage.json()["users_by_tier"].get("aggressive"), 1)

    def test_edit_tier_rules(self):
        resp = self.client.patch(
            f"/api/admin/investment-tiers/{self.balanced.id}/",
            {"max_open_positions": 6},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.balanced.refresh_from_db()
        self.assertEqual(self.balanced.max_open_positions, 6)

    def test_create_copy_trade_strategy_with_x_source(self):
        types = self.client.get("/api/admin/strategy-types/")
        self.assertEqual(types.status_code, 200)
        catalog = types.json()["results"]
        values = [row["value"] for row in catalog]
        self.assertIn("copy_trade", values)
        copy_trade = next(row for row in catalog if row["value"] == "copy_trade")
        self.assertEqual(copy_trade["label"], "Copy Trade")
        self.assertIn("signal_source", copy_trade["config_fields"])
        sources = copy_trade["signal_sources"]
        self.assertEqual(sources[0]["value"], "x")
        self.assertEqual(sources[0]["label"], "X")
        self.assertTrue(sources[0]["available"])
        self.assertEqual(sources[1]["value"], "chat_group")
        self.assertFalse(sources[1]["available"])

        created = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Copy Alpha",
                "description": "Copies @alpha",
                "strategy_type": "copy_trade",
                "x_source": {
                    "handle": "@AlphaTrader",
                    "display_name": "Alpha",
                    "is_active": True,
                    "lookback_hours": 24,
                    "poll_interval_seconds": 30,
                },
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.json())
        body = created.json()
        self.assertEqual(body["slug"], "copy-alpha")
        self.assertEqual(body["x_source"]["handle"], "alphatrader")
        self.assertEqual(body["x_source"]["lookback_hours"], 24)
        self.assertEqual(body["x_source"]["poll_interval_seconds"], 30)
        self.assertEqual(body["signal_source"], "x")
        self.assertEqual(body["assigned_user_count"], 0)
        self.assertEqual(body["visibility"], "public")
        self.assertIsInstance(body["id"], int)

        listed = self.client.get("/api/admin/strategies/?search=alpha")
        slugs = [row["slug"] for row in listed.json()["results"]]
        self.assertIn("copy-alpha", slugs)

        member = APIClient()
        member.force_authenticate(self.user)
        public = member.get("/api/strategies/")
        public_slugs = [row["slug"] for row in public.json()["results"]]
        self.assertIn("copy-alpha", public_slugs)
        self.assertEqual(
            next(row for row in public.json()["results"] if row["slug"] == "copy-alpha")[
                "source_handle"
            ],
            "alphatrader",
        )

        pk = body["id"]
        patched = self.client.patch(
            f"/api/admin/strategies/{pk}/",
            {"x_source": {"handle": "alphatrader", "is_active": False}},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.json()["x_source"]["is_active"])

        duplicate = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Copy Alpha 2",
                "x_source": {"handle": "alphatrader"},
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)

        chat_group = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Copy Chat",
                "strategy_type": "copy_trade",
                "signal_source": "chat_group",
            },
            format="json",
        )
        self.assertEqual(chat_group.status_code, 400)
        self.assertIn("signal_source", chat_group.json())

        deleted = self.client.delete(f"/api/admin/strategies/{pk}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(deleted.json()["is_active"])
        public_after = member.get("/api/strategies/")
        self.assertNotIn(
            "copy-alpha",
            [row["slug"] for row in public_after.json()["results"]],
        )

    def test_update_seeded_copy_trade_x_source_persists(self):
        source = XAccountSource.objects.get(handle="configure-me")
        self.assertEqual(source.strategy_id, self.strategy.id)
        resp = self.client.patch(
            f"/api/admin/strategies/{self.strategy.id}/",
            {
                "name": "Copy Trade",
                "strategy_type": "copy_trade",
                "signal_source": "x",
                "x_source": {
                    "handle": "@RealTrader",
                    "display_name": "Real desk",
                    "is_active": True,
                    "lookback_hours": 24,
                    "poll_interval_seconds": 45,
                },
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        body = resp.json()["x_source"]
        self.assertEqual(body["handle"], "realtrader")
        self.assertEqual(body["display_name"], "Real desk")
        self.assertTrue(body["is_active"])
        self.assertEqual(body["lookback_hours"], 24)
        self.assertEqual(body["poll_interval_seconds"], 45)
        source.refresh_from_db()
        self.assertEqual(source.handle, "realtrader")
        self.assertEqual(source.display_name, "Real desk")

        from django.core.management import call_command

        call_command("seed_trading")
        detail = self.client.get(f"/api/admin/strategies/{self.strategy.id}/")
        self.assertEqual(detail.json()["x_source"]["handle"], "realtrader")
        self.assertEqual(detail.json()["x_source"]["display_name"], "Real desk")
        self.assertFalse(
            XAccountSource.objects.filter(
                strategy=self.strategy, handle="configure-me"
            ).exists()
        )

    def test_x_source_save_ignores_placeholder_shadow_row(self):
        original = XAccountSource.objects.get(strategy=self.strategy)
        original.handle = "keep-me"
        original.display_name = "Old"
        original.is_active = True
        original.save()
        XAccountSource.objects.create(
            strategy=self.strategy,
            handle="configure-me",
            display_name="Placeholder",
            is_active=False,
        )
        listed = self.client.get(f"/api/admin/strategies/{self.strategy.id}/")
        self.assertEqual(listed.json()["x_source"]["handle"], "keep-me")

        resp = self.client.patch(
            f"/api/admin/strategies/{self.strategy.id}/",
            {
                "x_source": {
                    "handle": "keep-me",
                    "display_name": "Desk",
                    "is_active": True,
                    "lookback_hours": 12,
                    "poll_interval_seconds": 60,
                }
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertEqual(resp.json()["x_source"]["handle"], "keep-me")
        self.assertEqual(resp.json()["x_source"]["display_name"], "Desk")
        original.refresh_from_db()
        self.assertEqual(original.display_name, "Desk")
        self.assertFalse(
            XAccountSource.objects.get(handle="configure-me").is_active
        )

    def test_poll_interval_must_be_at_least_15_seconds(self):
        created = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Too Fast",
                "strategy_type": "copy_trade",
                "x_source": {"handle": "toofast", "poll_interval_seconds": 5},
            },
            format="json",
        )
        self.assertEqual(created.status_code, 400)
        self.assertIn("poll_interval_seconds", created.json()["x_source"])

    def test_create_tier_and_list_users(self):
        created = self.client.post(
            "/api/admin/investment-tiers/",
            {
                "slug": "scalp",
                "name": "Scalp",
                "description": "Very tight rules.",
                "max_entry_slippage_pct": "10.00",
                "max_risk_per_trade_pct": "0.50",
                "max_open_positions": 2,
                "take_profit_rules": [{"pct_of_position": "100", "gain_pct": "40"}],
                "hard_stop_pct": "30.00",
                "force_exit_time_et": "15:15:00",
                "max_hold_trading_days": 1,
                "daily_loss_limit_pct": "1.50",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.json())
        self.assertEqual(created.json()["slug"], "scalp")

        set_assignment(self.user, self.strategy, self.balanced)
        users = self.client.get("/api/admin/users/?search=trader")
        self.assertEqual(users.status_code, 200)
        row = next(item for item in users.json()["results"] if item["id"] == self.user.id)
        self.assertEqual(row["assignment"]["strategy"]["slug"], "copy-trade")
        self.assertEqual(row["assignment"]["investment_tier"]["slug"], "balanced")
        self.assertIsInstance(row["id"], int)

        forbidden = APIClient()
        forbidden.force_authenticate(self.user)
        self.assertEqual(forbidden.post("/api/admin/strategies/", {"name": "Nope"}).status_code, 403)

    def test_strategy_posts_and_signals(self):
        from trading.models import XAccountSource

        source = XAccountSource.objects.get(handle="configure-me")
        ingest_tweet(
            source,
            tweet_id="tweet-77",
            text="BTO $AAPL 200C 8/15 @ 2.50",
            posted_at=timezone.now(),
            process=False,
        )
        posts = self.client.get(f"/api/admin/strategies/{self.strategy.id}/posts/")
        self.assertEqual(posts.status_code, 200)
        row = posts.json()["results"][0]
        self.assertEqual(row["tweet_id"], "tweet-77")
        self.assertEqual(row["text"], "BTO $AAPL 200C 8/15 @ 2.50")
        self.assertEqual(row["strategy_id"], self.strategy.id)
        self.assertEqual(len(row["signals"]), 1)
        self.assertEqual(row["signals"][0]["ticker"], "AAPL")

        signals = self.client.get(f"/api/admin/strategies/{self.strategy.id}/signals/")
        self.assertEqual(signals.status_code, 200)
        sig = signals.json()["results"][0]
        self.assertEqual(sig["ticker"], "AAPL")
        self.assertEqual(sig["tweet_id"], "tweet-77")
        self.assertIn("BTO $AAPL", sig["tweet_text"])

        filtered = self.client.get(f"/api/admin/signals/?strategy={self.strategy.id}")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["count"], 1)

        by_strategy = self.client.get(f"/api/admin/x-posts/?strategy={self.strategy.id}")
        self.assertEqual(by_strategy.json()["count"], 1)

    def test_strategy_visibility_and_user_groups(self):
        invited = self.make_user("invited")
        outsider = self.make_user("outsider")
        grouped = self.make_user("grouped")

        group = self.client.post(
            "/api/admin/user-groups/",
            {
                "name": "VIP Desk",
                "description": "Invite-only copy traders",
                "member_ids": [grouped.id],
            },
            format="json",
        )
        self.assertEqual(group.status_code, 201, group.json())
        group_id = group.json()["id"]
        self.assertEqual(group.json()["slug"], "vip-desk")
        self.assertEqual(group.json()["member_count"], 1)
        self.assertEqual(group.json()["members"][0]["id"], grouped.id)

        created = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Copy VIP",
                "strategy_type": "copy_trade",
                "visibility": "restricted",
                "allowed_user_ids": [invited.id],
                "allowed_group_ids": [group_id],
                "x_source": {"handle": "vipdesk", "is_active": True},
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.json())
        body = created.json()
        self.assertEqual(body["visibility"], "restricted")
        self.assertEqual([row["id"] for row in body["allowed_users"]], [invited.id])
        self.assertEqual([row["id"] for row in body["allowed_groups"]], [group_id])
        strategy_id = body["id"]

        listed = self.client.get("/api/admin/strategies/?visibility=restricted")
        self.assertIn(strategy_id, [row["id"] for row in listed.json()["results"]])

        invited_client = APIClient()
        invited_client.force_authenticate(invited)
        grouped_client = APIClient()
        grouped_client.force_authenticate(grouped)
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider)

        invited_slugs = [row["slug"] for row in invited_client.get("/api/strategies/").json()["results"]]
        grouped_slugs = [row["slug"] for row in grouped_client.get("/api/strategies/").json()["results"]]
        outsider_slugs = [row["slug"] for row in outsider_client.get("/api/strategies/").json()["results"]]
        self.assertIn("copy-vip", invited_slugs)
        self.assertIn("copy-vip", grouped_slugs)
        self.assertNotIn("copy-vip", outsider_slugs)
        self.assertIn("copy-trade", outsider_slugs)

        allowed = invited_client.put(
            "/api/assignment/",
            {"strategy_id": strategy_id, "investment_tier_id": self.balanced.id},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)

        denied = outsider_client.put(
            "/api/assignment/",
            {"strategy_id": strategy_id, "investment_tier_id": self.balanced.id},
            format="json",
        )
        self.assertEqual(denied.status_code, 400)

        forced = self.client.post(
            "/api/admin/users/assignment/",
            {
                "user_id": outsider.id,
                "strategy_id": strategy_id,
                "investment_tier_id": self.balanced.id,
            },
            format="json",
        )
        self.assertEqual(forced.status_code, 200)
        self.assertEqual(forced.json()["strategy"]["slug"], "copy-vip")

        deactivated = self.client.delete(f"/api/admin/user-groups/{group_id}/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["is_active"])
        grouped_after = [row["slug"] for row in grouped_client.get("/api/strategies/").json()["results"]]
        self.assertNotIn("copy-vip", grouped_after)
        invited_after = [row["slug"] for row in invited_client.get("/api/strategies/").json()["results"]]
        self.assertIn("copy-vip", invited_after)

        empty = self.client.patch(
            f"/api/admin/strategies/{strategy_id}/",
            {"allowed_user_ids": [], "allowed_group_ids": []},
            format="json",
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["allowed_users"], [])
        staff_picker = APIClient()
        staff_picker.force_authenticate(self.admin)
        staff_slugs = [row["slug"] for row in staff_picker.get("/api/strategies/").json()["results"]]
        self.assertIn("copy-vip", staff_slugs)
        invited_empty = [row["slug"] for row in invited_client.get("/api/strategies/").json()["results"]]
        self.assertNotIn("copy-vip", invited_empty)


class TierRuleUnitTests(TestCase):
    def test_slippage_and_sizing(self):
        from decimal import Decimal

        self.assertFalse(slippage_exceeded(Decimal("2"), Decimal("2.20"), Decimal("15")))
        self.assertTrue(slippage_exceeded(Decimal("2"), Decimal("2.40"), Decimal("15")))
        qty = position_size(Decimal("100000"), Decimal("1.00"), Decimal("2.00"), Decimal("50"))
        self.assertGreater(qty, 0)

    def test_small_account_takes_one_contract_when_affordable(self):
        from trading.services.tier_rules import SIZE_MODE_MINIMUM_CONTRACT, size_position

        sized = size_position(
            Decimal("100"),
            Decimal("1.25"),
            Decimal("0.80"),
            Decimal("50"),
        )
        self.assertEqual(sized.quantity, 1)
        self.assertEqual(sized.mode, SIZE_MODE_MINIMUM_CONTRACT)
        self.assertEqual(sized.risk_quantity, 0)
        self.assertEqual(sized.contract_cost, Decimal("80.00"))

    def test_small_account_skips_when_premium_exceeds_cash(self):
        from trading.services.tier_rules import SIZE_MODE_UNAFFORDABLE, size_position

        sized = size_position(
            Decimal("100"),
            Decimal("1.25"),
            Decimal("2.00"),
            Decimal("50"),
        )
        self.assertEqual(sized.quantity, 0)
        self.assertEqual(sized.mode, SIZE_MODE_UNAFFORDABLE)
        self.assertEqual(sized.contract_cost, Decimal("200.00"))
        self.assertEqual(sized.max_affordable, 0)

    def test_size_scales_with_equity_and_respects_tier_risk(self):
        from trading.services.tier_rules import (
            SIZE_MODE_MINIMUM_CONTRACT,
            SIZE_MODE_RISK,
            size_position,
        )

        starter = size_position(Decimal("1000"), Decimal("1.25"), Decimal("2.00"), Decimal("50"))
        self.assertEqual(starter.quantity, 1)
        self.assertEqual(starter.mode, SIZE_MODE_MINIMUM_CONTRACT)

        mid = size_position(Decimal("10000"), Decimal("1.25"), Decimal("2.00"), Decimal("50"))
        self.assertEqual(mid.quantity, 1)
        self.assertEqual(mid.mode, SIZE_MODE_RISK)

        large = size_position(Decimal("100000"), Decimal("1.25"), Decimal("2.00"), Decimal("50"))
        self.assertEqual(large.quantity, 12)
        self.assertEqual(large.mode, SIZE_MODE_RISK)

        aggressive = size_position(
            Decimal("100000"), Decimal("2.00"), Decimal("2.00"), Decimal("55")
        )
        self.assertGreater(aggressive.quantity, large.quantity)

    def test_buying_power_caps_risk_size(self):
        from trading.services.tier_rules import SIZE_MODE_CASH_CAPPED, size_position

        sized = size_position(
            Decimal("100000"),
            Decimal("1.25"),
            Decimal("2.00"),
            Decimal("50"),
            buying_power=Decimal("250"),
        )
        self.assertEqual(sized.quantity, 1)
        self.assertEqual(sized.mode, SIZE_MODE_CASH_CAPPED)
        self.assertEqual(sized.risk_quantity, 12)
        self.assertEqual(sized.max_affordable, 1)


class CeleryTradingTests(TestCase):
    def test_trading_tasks_registered(self):
        from config.celery import app

        app.autodiscover_tasks(force=True)
        for name in (
            "trading.process_new_signals",
            "trading.monitor_open_positions",
            "trading.check_daily_loss_limits",
            "trading.force_expiration_exits",
            "trading.sync_broker_positions",
            "trading.calculate_daily_performance",
            "trading.reset_daily_flags",
            "trading.calculate_weekly_performance",
            "trading.reconcile_lifetime_pnl",
            "trading.tier_usage_stats",
            "trading.cleanup_old_signals_and_trades",
            "trading.poll_x_accounts",
        ):
            self.assertIn(name, app.tasks)
