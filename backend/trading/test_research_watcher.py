from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from trading.constants import (
    DIR_BEARISH,
    DIR_BULLISH,
    EVENT_ACQUISITION,
    EVENT_CLINICAL,
    EVENT_FDA,
    EVENT_PRODUCT,
    RESEARCH_CATALYST,
    RESEARCH_NOISE,
    STRATEGY_RESEARCH_BREAKTHROUGH,
)
from trading.models import ResearchEvent, ResearchWatchConfig, Signal, Strategy, WatchedCompany
from trading.services.market_data import OptionQuote, UnderlyingSnapshot
from trading.services.option_selector import select_contract
from trading.services.research_classifier import CompanyRef, classify_text
from trading.services.research_feeds import google_news_url, parse_rss
from trading.services.research_watcher import active_companies, ingest_headline
from trading.tests import TradingMixin

MRNA = CompanyRef(ticker="MRNA", name="Moderna", aliases=["Moderna Inc"])
PFE = CompanyRef(ticker="PFE", name="Pfizer", aliases=["Pfizer Inc"])
WATCHLIST = [MRNA, PFE]


def mrna_snapshot(_ticker="MRNA"):
    exp = date(2026, 9, 18)
    return UnderlyingSnapshot(
        ticker="MRNA",
        price=Decimal("140.00"),
        expirations=[exp],
        contracts=[
            OptionQuote(
                strike=Decimal("145"),
                expiration=exp,
                option_type="call",
                bid=Decimal("4.00"),
                ask=Decimal("4.20"),
                last=Decimal("4.10"),
            ),
            OptionQuote(
                strike=Decimal("135"),
                expiration=exp,
                option_type="put",
                bid=Decimal("3.00"),
                ask=Decimal("3.20"),
                last=Decimal("3.10"),
            ),
        ],
    )


class ResearchClassifierTests(TestCase):
    def test_cancer_vaccine_phase3_is_bullish_catalyst(self):
        results = classify_text(
            "Moderna Announces Positive Phase 3 Results for Individualized Cancer Vaccine",
            companies=WATCHLIST,
        )
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row.ticker, "MRNA")
        self.assertTrue(row.is_catalyst)
        self.assertEqual(row.direction, DIR_BULLISH)
        self.assertIn(row.event_type, {EVENT_CLINICAL, "breakthrough"})
        self.assertGreaterEqual(row.score, 70)

    def test_fda_approval_is_bullish_catalyst(self):
        row = classify_text(
            "Pfizer announces FDA approval of new RSV vaccine",
            companies=WATCHLIST,
        )[0]
        self.assertTrue(row.is_catalyst)
        self.assertEqual(row.ticker, "PFE")
        self.assertEqual(row.direction, DIR_BULLISH)
        self.assertEqual(row.event_type, EVENT_FDA)
        self.assertGreaterEqual(row.score, 70)

    def test_failed_trial_is_bearish_catalyst(self):
        row = classify_text(
            "Pfizer announces Phase 3 trial failed to meet primary endpoint",
            companies=WATCHLIST,
        )[0]
        self.assertTrue(row.is_catalyst)
        self.assertEqual(row.direction, DIR_BEARISH)
        self.assertGreaterEqual(row.score, 70)

    def test_confirmed_acquisition_is_catalyst(self):
        row = classify_text(
            "Pfizer announces definitive agreement to acquire a rare-disease biotech",
            companies=WATCHLIST,
        )[0]
        self.assertTrue(row.is_catalyst)
        self.assertEqual(row.event_type, EVENT_ACQUISITION)
        self.assertEqual(row.direction, DIR_BULLISH)

    def test_product_launch_is_generic_catalyst(self):
        nvidia = CompanyRef(ticker="NVDA", name="NVIDIA", aliases=["Nvidia"])
        row = classify_text(
            "NVIDIA announces it is launching a new AI chip platform",
            companies=[nvidia],
        )[0]
        self.assertTrue(row.is_catalyst)
        self.assertEqual(row.event_type, EVENT_PRODUCT)
        self.assertEqual(row.direction, DIR_BULLISH)

    def test_enabled_event_types_ignore_other_catalysts(self):
        row = classify_text(
            "Pfizer announces FDA approval of new RSV vaccine",
            companies=WATCHLIST,
            enabled_event_types={EVENT_ACQUISITION},
        )[0]
        self.assertFalse(row.is_catalyst)
        self.assertNotEqual(row.event_type, EVENT_FDA)

    def test_rumor_is_not_a_catalyst(self):
        row = classify_text(
            "Sources say Merck is considering acquiring Moderna",
            companies=WATCHLIST,
        )[0]
        self.assertFalse(row.is_catalyst)
        self.assertLess(row.score, 70)

    def test_analyst_note_is_noise(self):
        row = classify_text(
            "Analyst upgrades MRNA to overweight with a $200 price target",
            companies=WATCHLIST,
        )[0]
        self.assertFalse(row.is_catalyst)

    def test_unrelated_headline_matches_nobody(self):
        row = classify_text("Apple unveils new iPhone", companies=WATCHLIST)[0]
        self.assertFalse(row.is_catalyst)
        self.assertEqual(row.ticker, "")


class OptionSelectorTests(TestCase):
    def test_bullish_picks_otm_call(self):
        contract = select_contract(mrna_snapshot(), DIR_BULLISH, as_of=date(2026, 8, 19))
        self.assertEqual(contract.option_type, "call")
        self.assertEqual(contract.ticker, "MRNA")
        self.assertEqual(contract.strike, Decimal("145"))
        self.assertEqual(contract.expiration, date(2026, 9, 18))
        self.assertEqual(contract.entry_price, Decimal("4.1000"))

    def test_bearish_picks_otm_put(self):
        contract = select_contract(mrna_snapshot(), DIR_BEARISH, as_of=date(2026, 8, 19))
        self.assertEqual(contract.option_type, "put")
        self.assertEqual(contract.strike, Decimal("135"))


class ResearchFeedParseTests(TestCase):
    def test_parses_google_news_rss(self):
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Moderna announces cancer vaccine Phase 3 success - Reuters</title>
              <link>https://example.com/mrna-vaccine</link>
              <guid>https://example.com/mrna-vaccine</guid>
              <pubDate>Wed, 19 Aug 2026 12:00:00 GMT</pubDate>
              <description>Company reported positive data.</description>
            </item>
          </channel>
        </rss>
        """
        items = parse_rss(xml_text, source="google_news")
        self.assertEqual(len(items), 1)
        self.assertIn("Moderna", items[0].headline)
        self.assertEqual(items[0].url, "https://example.com/mrna-vaccine")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 19, 12, 0, tzinfo=dt_timezone.utc))

    def test_news_query_uses_configured_keywords(self):
        url = google_news_url("NVDA", "NVIDIA", keywords=["launch", "acquisition"])
        self.assertIn("NVDA", url)
        self.assertIn("launch", url)
        self.assertIn("acquisition", url)
        self.assertNotIn("phase", url.lower())


class ResearchWatcherTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.strategy = Strategy.objects.get(slug=STRATEGY_RESEARCH_BREAKTHROUGH)
        self.user = self.make_user()
        self.connect_broker(self.user)
        self.moderna = WatchedCompany.objects.create(
            strategy=self.strategy,
            ticker="MRNA",
            name="Moderna",
            aliases=["Moderna Inc"],
            sector="healthcare",
        )

    def test_seed_creates_generic_research_strategy(self):
        self.assertTrue(self.strategy.is_active)
        self.assertEqual(self.strategy.strategy_type, "research_breakthrough")
        self.assertTrue(hasattr(self.strategy, "research_config"))
        config = ResearchWatchConfig.objects.get(strategy=self.strategy)
        self.assertEqual(config.sectors, [])
        self.assertEqual(config.enabled_event_types, [])
        self.assertEqual(config.news_keywords, [])

    def test_sector_filter_limits_the_universe(self):
        nvidia = WatchedCompany.objects.create(
            strategy=self.strategy,
            ticker="NVDA",
            name="NVIDIA",
            sector="tech",
        )
        config = self.strategy.research_config
        config.sectors = ["tech"]
        config.save(update_fields=["sectors", "updated_at"])
        watched = active_companies(self.strategy, config)
        self.assertEqual([row.ticker for row in watched], [nvidia.ticker])

    @patch("trading.services.research_watcher.fetch_option_snapshot", side_effect=mrna_snapshot)
    def test_confirmed_headline_creates_option_signal(self, _mock):
        events, signals = ingest_headline(
            self.strategy,
            "Moderna announces positive Phase 3 results for its individualized cancer vaccine",
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.status, RESEARCH_CATALYST)
        self.assertEqual(event.company.ticker, "MRNA")
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.ticker, "MRNA")
        self.assertEqual(signal.option_type, "call")
        self.assertEqual(signal.research_event_id, event.id)
        self.assertTrue(signal.source.startswith("research:"))

    @patch("trading.services.research_watcher.fetch_option_snapshot", side_effect=mrna_snapshot)
    def test_duplicate_headline_does_not_create_second_signal(self, _mock):
        ingest_headline(
            self.strategy,
            "Moderna announces FDA approval of a new mRNA vaccine",
            source_url="https://example.com/fda",
        )
        events, signals = ingest_headline(
            self.strategy,
            "Moderna announces FDA approval of a new mRNA vaccine",
            source_url="https://example.com/fda",
        )
        self.assertEqual(len(signals), 0)
        self.assertEqual(
            Signal.objects.filter(strategy=self.strategy, ticker="MRNA").count(), 1
        )
        self.assertEqual(len(events), 1)

    @patch("trading.services.research_watcher.fetch_option_snapshot", side_effect=mrna_snapshot)
    def test_rumor_does_not_create_a_signal(self, _mock):
        events, signals = ingest_headline(
            self.strategy,
            "Sources say Merck is considering acquiring Moderna",
        )
        self.assertEqual(signals, [])
        self.assertEqual(events[0].status, RESEARCH_NOISE)

    @patch("trading.services.research_watcher.fetch_option_snapshot", side_effect=mrna_snapshot)
    def test_not_a_copy_of_someone_elses_option_ticket(self, _mock):
        events, signals = ingest_headline(
            self.strategy,
            "BTO $MRNA 100C 8/21 @ 0.05 someone turned 10k into 40 million",
        )
        self.assertEqual(signals, [])
        self.assertNotEqual(events[0].status, RESEARCH_CATALYST)


class ResearchAdminApiTests(TradingMixin, TestCase):
    def setUp(self):
        self.seed()
        self.admin = self.make_user("admin")
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.strategy = Strategy.objects.get(slug=STRATEGY_RESEARCH_BREAKTHROUGH)
        WatchedCompany.objects.create(
            strategy=self.strategy,
            ticker="MRNA",
            name="Moderna",
            aliases=["Moderna Inc"],
            sector="healthcare",
        )

    def test_catalog_includes_research_breakthrough(self):
        types = self.client.get("/api/admin/strategy-types/")
        values = [row["value"] for row in types.json()["results"]]
        self.assertIn("copy_trade", values)
        self.assertIn("research_breakthrough", values)
        research = next(row for row in types.json()["results"] if row["value"] == "research_breakthrough")
        self.assertEqual(research["label"], "Research / Breakthrough")
        self.assertIn("watched_companies", research["config_fields"])
        self.assertNotIn("x_source", research["config_fields"])
        self.assertNotIn("signal_source", research["config_fields"])
        preset_ids = [row["id"] for row in research["presets"]]
        self.assertEqual(preset_ids, ["any", "healthcare", "technology", "deals"])

    def test_create_research_strategy_with_watchlist(self):
        created = self.client.post(
            "/api/admin/strategies/",
            {
                "name": "Tech Catalysts",
                "description": "Configurable research strategy pointed at tech names.",
                "strategy_type": "research_breakthrough",
                "research_config": {
                    "poll_interval_seconds": 45,
                    "min_catalyst_score": 75,
                    "otm_pct": "6.00",
                    "min_dte": 21,
                    "max_dte": 60,
                    "sectors": ["tech"],
                    "enabled_event_types": ["product_launch", "acquisition", "partnership"],
                    "news_keywords": ["launch", "acquisition"],
                    "require_confirmation": True,
                },
                "watched_companies": [
                    {
                        "ticker": "nvda",
                        "name": "NVIDIA",
                        "aliases": ["Nvidia"],
                        "sector": "tech",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.json())
        body = created.json()
        self.assertEqual(body["strategy_type"], "research_breakthrough")
        self.assertEqual(body["research_config"]["min_catalyst_score"], 75)
        self.assertEqual(body["watched_companies"][0]["ticker"], "NVDA")
        self.assertEqual(body["watched_companies"][0]["name"], "NVIDIA")
        self.assertEqual(body["research_config"]["poll_interval_seconds"], 45)
        self.assertEqual(body["research_config"]["sectors"], ["tech"])
        self.assertEqual(body["research_config"]["enabled_event_types"], [
            "product_launch",
            "acquisition",
            "partnership",
        ])

        member = APIClient()
        member.force_authenticate(self.make_user("member"))
        listed = member.get("/api/strategies/")
        slugs = [row["slug"] for row in listed.json()["results"]]
        self.assertIn("tech-catalysts", slugs)
        preview = next(row for row in listed.json()["results"] if row["slug"] == "tech-catalysts")
        self.assertEqual(preview["source_handle"], "NVDA")
        self.assertNotIn("x_source", preview)

    @patch("trading.services.research_watcher.fetch_option_snapshot", side_effect=mrna_snapshot)
    def test_ingest_headline_endpoint(self, _mock):
        resp = self.client.post(
            f"/api/admin/strategies/{self.strategy.id}/research-ingest/",
            {
                "headline": "Moderna announces positive Phase 3 results for its cancer vaccine",
                "process": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.json())
        row = resp.json()[0]
        self.assertEqual(row["status"], RESEARCH_CATALYST)
        self.assertEqual(row["ticker"], "MRNA")
        self.assertTrue(row["signals"])
        self.assertEqual(ResearchEvent.objects.filter(strategy=self.strategy).count(), 1)

    def test_parse_preview_does_not_write_events(self):
        resp = self.client.post(
            "/api/admin/research-parse/",
            {
                "headline": "Moderna announces FDA approval of a cancer vaccine",
                "tickers": ["MRNA"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        row = resp.json()["classifications"][0]
        self.assertTrue(row["is_catalyst"])
        self.assertEqual(row["ticker"], "MRNA")
        self.assertEqual(ResearchEvent.objects.count(), 0)
