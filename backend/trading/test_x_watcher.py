from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from trading.constants import ET, STRATEGY_COPY_TRADE, STRATEGY_VISIBILITY_RESTRICTED
from trading.models import IngestedPost, Signal, SignalDecision, Strategy, Trade, XAccountSource
from trading.services.jobs import set_assignment
from trading.services.x_client import XTweet, XUser
from trading.services.x_trade_parser import parse_entry_trades, parse_trades
from trading.services.x_watcher import ingest_tweet, lookback_source, poll_all_sources, poll_source
from trading.tests import TradingMixin

POSTED = datetime(2026, 8, 15, 14, 30, tzinfo=ET)


class TradeParserTests(TestCase):
    def test_bto_ticker_strike_expiration_price(self):
        trades = parse_entry_trades("BTO $AAPL 200C 8/15 @ 2.50", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.ticker, "AAPL")
        self.assertEqual(trade.option_type, "call")
        self.assertEqual(trade.strike, Decimal("200"))
        self.assertEqual(trade.expiration.isoformat(), "2026-08-15")
        self.assertEqual(trade.entry_price, Decimal("2.50"))

    def test_expiration_before_strike(self):
        trades = parse_entry_trades("BTO AAPL 8/15 200c @ 2.50", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].strike, Decimal("200"))
        self.assertEqual(trades[0].expiration.isoformat(), "2026-08-15")

    def test_call_word_and_dollar_price(self):
        trades = parse_entry_trades("$NVDA 120 CALL 12/18 @ $3.00", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].ticker, "NVDA")
        self.assertEqual(trades[0].option_type, "call")
        self.assertEqual(trades[0].expiration.isoformat(), "2026-12-18")

    def test_put_and_for_price(self):
        trades = parse_entry_trades("Bought 10 SPY 450P 08/15 for 1.50", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].ticker, "SPY")
        self.assertEqual(trades[0].option_type, "put")
        self.assertEqual(trades[0].entry_price, Decimal("1.50"))

    def test_fractional_price_and_adding(self):
        trades = parse_entry_trades("ADDING HEAVY $TSLA 250c 8/22 @ .85", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].ticker, "TSLA")
        self.assertEqual(trades[0].entry_price, Decimal("0.85"))
        self.assertEqual(trades[0].expiration.isoformat(), "2026-08-22")

    def test_daily_recap_multiple_lines(self):
        text = "Today's trades:\nBTO AAPL 200C 8/15 @ 2.00\nBTO NVDA 120C 8/22 @ 3.50"
        trades = parse_entry_trades(text, posted_at=POSTED)
        self.assertEqual([t.ticker for t in trades], ["AAPL", "NVDA"])

    def test_exit_is_not_an_entry(self):
        trades = parse_trades("STC $AAPL 200C 8/15 @ 4.00", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertTrue(trades[0].is_exit)
        self.assertEqual(parse_entry_trades("STC $AAPL 200C 8/15 @ 4.00", posted_at=POSTED), [])

    def test_missing_expiration_uses_posted_date(self):
        trades = parse_entry_trades("0DTE $SPY 640C @ 1.20", posted_at=POSTED)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].expiration.isoformat(), "2026-08-15")

    def test_past_month_day_rolls_to_next_year(self):
        trades = parse_entry_trades("BTO AAPL 1/15 200c @ 2.00", posted_at=POSTED)
        self.assertEqual(trades[0].expiration.isoformat(), "2027-01-15")

    def test_commentary_is_ignored(self):
        self.assertEqual(parse_entry_trades("Market looking heavy into close", posted_at=POSTED), [])


class FakeXClient:
    def __init__(self, tweets):
        self.tweets = tweets
        self.lookups = []

    def lookup_user(self, username):
        self.lookups.append(username)
        return XUser(id="42", username=username, name="Copy Trader")

    def user_tweets(self, user_id, since_id=None, max_results=20, **kwargs):
        return list(self.tweets)


class XWatcherTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.source = XAccountSource.objects.get(handle="configure-me")
        self.source.handle = "copytrader"
        self.source.is_active = True
        self.source.save()
        self.user = self.make_user()
        self.connect_broker(self.user)
        set_assignment(self.user, self.strategy, self.balanced)

    def test_ingest_creates_and_distributes_signal(self):
        post = ingest_tweet(
            self.source,
            tweet_id="1001",
            text="BTO $AAPL 200C 8/15 @ 2.50",
            posted_at=timezone.now(),
        )
        self.assertEqual(post.parse_status, IngestedPost.ParseStatus.PARSED)
        signal = Signal.objects.get(ingested_post=post)
        self.assertEqual(signal.ticker, "AAPL")
        self.assertEqual(signal.source, "x:@copytrader/1001")
        self.assertEqual(signal.status, Signal.Status.PROCESSED)
        self.assertTrue(Trade.objects.filter(user=self.user, ticker="AAPL").exists())

    def test_ingest_is_idempotent(self):
        kwargs = {
            "source": self.source,
            "tweet_id": "1002",
            "text": "BTO $MSFT 400C 8/22 @ 1.25",
            "posted_at": timezone.now(),
        }
        ingest_tweet(**kwargs)
        ingest_tweet(**kwargs)
        self.assertEqual(Signal.objects.filter(ticker="MSFT").count(), 1)
        self.assertEqual(IngestedPost.objects.filter(tweet_id="1002").count(), 1)

    def test_stale_tweet_is_skipped(self):
        posted = timezone.now() - timedelta(hours=72)
        post = ingest_tweet(
            self.source,
            tweet_id="1003",
            text="BTO $NVDA 120C 8/22 @ 3.00",
            posted_at=posted,
        )
        self.assertEqual(post.parse_status, IngestedPost.ParseStatus.SKIPPED)
        self.assertFalse(Signal.objects.filter(ticker="NVDA").exists())

    def test_poll_uses_client_and_advances_cursor(self):
        client = FakeXClient(
            [
                XTweet(
                    id="2002",
                    text="BTO $QQQ 480C 8/15 @ 1.10",
                    created_at=timezone.now(),
                ),
                XTweet(
                    id="2001",
                    text="just vibes today",
                    created_at=timezone.now(),
                ),
            ]
        )
        result = poll_source(self.source, client=client)
        self.source.refresh_from_db()
        self.assertEqual(self.source.x_user_id, "42")
        self.assertEqual(self.source.last_tweet_id, "2002")
        self.assertEqual(result["tweets"], 2)
        self.assertEqual(Signal.objects.filter(ticker="QQQ").count(), 1)
        self.assertEqual(
            IngestedPost.objects.get(tweet_id="2001").parse_status,
            IngestedPost.ParseStatus.NO_TRADE,
        )

    def test_poll_skips_when_interval_not_elapsed(self):
        self.source.last_polled_at = timezone.now()
        self.source.poll_interval_seconds = 60
        self.source.save()
        client = FakeXClient(
            [
                XTweet(
                    id="3001",
                    text="BTO $SPY 500C 8/15 @ 1.00",
                    created_at=timezone.now(),
                )
            ]
        )
        result = poll_source(self.source, client=client)
        self.assertEqual(result["skipped"], True)
        self.assertEqual(result["reason"], "not_due")
        self.assertEqual(client.lookups, [])
        self.assertFalse(Signal.objects.filter(ticker="SPY").exists())

    def test_poll_force_ignores_interval(self):
        self.source.last_polled_at = timezone.now()
        self.source.poll_interval_seconds = 3600
        self.source.save()
        client = FakeXClient([])
        result = poll_source(self.source, client=client, force=True)
        self.assertNotIn("skipped", result)
        self.assertEqual(result["tweets"], 0)
        self.assertEqual(client.lookups, ["copytrader"])

    def test_poll_all_sources_respects_interval(self):
        self.source.last_polled_at = timezone.now()
        self.source.poll_interval_seconds = 60
        self.source.save()
        results = poll_all_sources(client=FakeXClient([]))
        self.assertEqual(results[0]["reason"], "not_due")

    def test_poll_backs_off_after_unauthorized(self):
        self.source.last_error = "X API unauthorized. The bearer token was rejected."
        self.source.last_polled_at = timezone.now()
        self.source.save()
        result = poll_source(self.source, client=FakeXClient([]))
        self.assertEqual(result["reason"], "x_api_backoff")

    def test_lookback_parses_old_tweets_without_duplicates_or_trades(self):
        posted = timezone.now() - timedelta(days=10)
        client = FakeXClient(
            [
                XTweet(
                    id="4001",
                    text="BTO $AMD 150C 8/22 @ 2.10",
                    created_at=posted,
                )
            ]
        )
        first = lookback_source(self.source, days=30, client=client)
        self.assertEqual(first["signals_created"], 1)
        self.assertEqual(first["tweets_ingested"], 1)
        signal = Signal.objects.get(ticker="AMD")
        self.assertEqual(signal.status, Signal.Status.PROCESSED)
        self.assertIn("Lookback", signal.notes)
        self.assertFalse(Trade.objects.filter(ticker="AMD").exists())

        second = lookback_source(self.source, days=30, client=client)
        self.assertEqual(second["signals_created"], 0)
        self.assertEqual(second["tweets_duplicate"], 1)
        self.assertEqual(Signal.objects.filter(ticker="AMD").count(), 1)

    def test_lookback_copies_recent_tweets_to_assigned_accounts(self):
        client = FakeXClient(
            [
                XTweet(
                    id="4003",
                    text="BTO $KO 91C 8/21 @ 0.80",
                    created_at=timezone.now(),
                )
            ]
        )
        result = lookback_source(self.source, days=30, client=client)
        self.assertEqual(result["signals_created"], 1)
        signal = Signal.objects.get(ticker="KO")
        self.assertEqual(signal.status, Signal.Status.PROCESSED)
        self.assertNotIn("Lookback ingest; not auto-traded.", signal.notes)
        decision = SignalDecision.objects.get(user=self.user, signal=signal)
        self.assertEqual(decision.outcome, SignalDecision.Outcome.ENTERED)
        self.assertTrue(Trade.objects.filter(user=self.user, ticker="KO").exists())

    def test_lookback_reparses_stale_skip(self):
        posted = timezone.now() - timedelta(days=10)
        ingest_tweet(
            self.source,
            tweet_id="4002",
            text="BTO $INTC 40C 8/22 @ 1.00",
            posted_at=posted,
        )
        self.assertFalse(Signal.objects.filter(ticker="INTC").exists())
        client = FakeXClient(
            [
                XTweet(
                    id="4002",
                    text="BTO $INTC 40C 8/22 @ 1.00",
                    created_at=posted,
                )
            ]
        )
        result = lookback_source(self.source, days=30, client=client)
        self.assertEqual(result["signals_created"], 1)
        self.assertEqual(Signal.objects.filter(ticker="INTC").count(), 1)


class XWatcherApiTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.source = XAccountSource.objects.get(handle="configure-me")
        self.admin = User.objects.create_user(
            username="adminuser",
            email="adminuser@example.com",
            password="longpassword1",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_strategy_list_includes_source_handle(self):
        self.source.handle = "copytrader"
        self.source.is_active = True
        self.source.save()
        member = self.make_user()
        api = APIClient()
        api.force_authenticate(member)
        resp = api.get("/api/strategies/")
        row = next(item for item in resp.json()["results"] if item["slug"] == STRATEGY_COPY_TRADE)
        self.assertEqual(row["source_handle"], "copytrader")

    def test_parse_preview_and_ingest(self):
        preview = self.client.post(
            "/api/admin/x-parse/",
            {"text": "BTO $AAPL 200C 8/15 @ 2.50", "posted_at": POSTED.isoformat()},
            format="json",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["trades"][0]["ticker"], "AAPL")

        ingested = self.client.post(
            f"/api/admin/x-sources/{self.source.id}/ingest/",
            {
                "text": "BTO $AAPL 200C 8/15 @ 2.50",
                "tweet_id": "api-1",
                "posted_at": timezone.now().isoformat(),
                "process": False,
            },
            format="json",
        )
        self.assertEqual(ingested.status_code, 200)
        self.assertEqual(ingested.json()["parse_status"], "parsed")
        self.assertEqual(len(ingested.json()["signal_ids"]), 1)
        self.assertFalse(SignalDecision.objects.exists())

    @override_settings(X_BEARER_TOKEN="", X_PULLCALLS_BEARER_TOKEN="")
    def test_poll_without_token_records_error(self):
        self.source.is_active = True
        self.source.save()
        resp = self.client.post(f"/api/admin/x-sources/{self.source.id}/poll/")
        self.assertEqual(resp.status_code, 200)
        self.source.refresh_from_db()
        self.assertIn("X_BEARER_TOKEN", self.source.last_error)

    def test_member_cannot_ingest(self):
        member = APIClient()
        member.force_authenticate(self.make_user())
        resp = member.post(
            f"/api/admin/x-sources/{self.source.id}/ingest/",
            {"text": "BTO $AAPL 200C 8/15 @ 2.50"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_strategy_signals_visible_to_assigned_and_public_users(self):
        self.source.handle = "copytrader"
        self.source.is_active = True
        self.source.save()
        ingest_tweet(
            self.source,
            tweet_id="api-sig-1",
            text="BTO $AAPL 200C 8/15 @ 2.50",
            posted_at=timezone.now(),
            process=False,
        )
        listed = self.client.get(
            f"/api/admin/strategies/{self.strategy.id}/signals/"
        )
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["results"][0]["ticker"], "AAPL")

        member = self.make_user()
        set_assignment(member, self.strategy, self.balanced)
        user_api = APIClient()
        user_api.force_authenticate(member)
        user_listed = user_api.get(f"/api/strategies/{self.strategy.id}/signals/")
        self.assertEqual(user_listed.status_code, 200)
        self.assertGreaterEqual(user_listed.json()["count"], 1)

        outsider = APIClient()
        outsider.force_authenticate(self.make_user("outsider"))
        public_ok = outsider.get(f"/api/strategies/{self.strategy.id}/signals/")
        self.assertEqual(public_ok.status_code, 200)

        restricted = Strategy.objects.create(
            name="Private copy",
            slug="private-copy",
            strategy_type=STRATEGY_COPY_TRADE,
            visibility=STRATEGY_VISIBILITY_RESTRICTED,
        )
        denied = outsider.get(f"/api/strategies/{restricted.id}/signals/")
        self.assertEqual(denied.status_code, 403)

    def test_lookback_api_parses_without_duplicates(self):
        self.source.handle = "copytrader"
        self.source.is_active = True
        self.source.save()
        posted = timezone.now() - timedelta(days=10)
        client = FakeXClient(
            [
                XTweet(
                    id="5001",
                    text="BTO $AMD 150C 8/22 @ 2.10",
                    created_at=posted,
                )
            ]
        )
        with patch("trading.views_admin.lookback_source") as mocked:
            mocked.side_effect = lambda source, days=30: lookback_source(
                source, days=days, client=client
            )
            first = self.client.post(
                f"/api/admin/strategies/{self.strategy.id}/lookback/",
                {"days": 30},
                format="json",
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["signals_created"], 1)
            self.assertEqual(first.json()["tweets_ingested"], 1)

            second = self.client.post(
                f"/api/admin/strategies/{self.strategy.id}/lookback/",
                {"days": 30},
                format="json",
            )
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["signals_created"], 0)
            self.assertEqual(second.json()["tweets_duplicate"], 1)

        self.assertEqual(Signal.objects.filter(ticker="AMD").count(), 1)
        self.assertFalse(Trade.objects.filter(ticker="AMD").exists())

    def test_lookback_requires_active_x_source(self):
        other = Strategy.objects.create(name="Manual", slug="manual-strat")
        resp = self.client.post(
            f"/api/admin/strategies/{other.id}/lookback/",
            {"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
