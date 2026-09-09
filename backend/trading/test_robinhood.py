import os
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from billing.services.entitlements import grant_subscription
from trading.models import BrokerConnection
from trading.services.brokers import RobinhoodBrokerClient, StubBrokerClient, get_broker_client
from trading.services.credentials import encrypt_credentials
from trading.services.robinhood import (
    _order_fill_fields,
    extract_tool_result,
    find_option_instrument,
    list_accounts_for,
    normalize_accounts,
    parse_oauth_callback,
    parse_sse_or_json,
    pick_agentic_account,
    portfolio_spendable,
)


def _oauth_metadata():
    return {
        "authorization_endpoint": "https://robinhood.com/oauth",
        "token_endpoint": "https://api.robinhood.com/oauth2/token/",
        "registration_endpoint": "https://agent.robinhood.com/oauth/trading/register",
        "scopes": ["internal"],
    }


class RobinhoodHelperTests(TestCase):
    def test_parses_sse_and_extracts_tool_result(self):
        raw = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"structuredContent":{"data":{"accounts":[]}}}}\n\n'
        messages = parse_sse_or_json(raw)
        self.assertEqual(extract_tool_result(messages[0]["result"]), {"accounts": []})

    def test_portfolio_spendable_uses_the_tighter_of_cash_and_buying_power(self):
        self.assertEqual(
            portfolio_spendable({"cash": "100.00", "buying_power": {"buying_power": "80.00"}}),
            Decimal("80.00"),
        )
        self.assertEqual(portfolio_spendable({"cash": "100.00"}), Decimal("100.00"))
        self.assertIsNone(portfolio_spendable({"total_value": "1000.00"}))

    def test_picks_single_agentic_account(self):
        accounts = normalize_accounts(
            {
                "accounts": [
                    {"account_number": "111", "agentic_allowed": False, "nickname": "Primary"},
                    {"account_number": "222", "agentic_allowed": True, "nickname": "Agentic"},
                ]
            }
        )
        self.assertEqual(pick_agentic_account(accounts)["account_number"], "222")

    def test_does_not_auto_pick_when_multiple_agentic(self):
        accounts = normalize_accounts(
            [
                {"account_number": "1", "agentic_allowed": True, "nickname": "A"},
                {"account_number": "2", "agentic_allowed": True, "nickname": "B"},
            ]
        )
        self.assertIsNone(pick_agentic_account(accounts))

    def test_order_fill_fields_does_not_fake_a_fill(self):
        submitted = _order_fill_fields(
            {"id": "ord-1", "state": "confirmed", "filled_quantity": "0"},
            1,
            Decimal("0.15"),
        )
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(submitted["filled_quantity"], 0)

        cancelled = _order_fill_fields(
            {
                "id": "ord-2",
                "state": "cancelled",
                "filled_quantity": "0",
                "canceled_quantity": "1",
            },
            1,
            Decimal("0.15"),
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["filled_quantity"], 0)
        self.assertEqual(cancelled["broker_order_id"], "ord-2")

        filled = _order_fill_fields(
            {
                "id": "ord-3",
                "state": "filled",
                "filled_quantity": "1",
                "average_price": "0.15",
            },
            1,
            Decimal("0.15"),
        )
        self.assertEqual(filled["status"], "filled")
        self.assertEqual(filled["filled_quantity"], 1)

        placed = _order_fill_fields(
            {"id": "ord-4", "state": "placed", "filled_quantity": "0"},
            1,
            Decimal("0.39"),
        )
        self.assertEqual(placed["status"], "submitted")
        self.assertEqual(placed["filled_quantity"], 0)

        executed = _order_fill_fields(
            {
                "id": "ord-5",
                "state": "filled",
                "quantity": "1",
                "executions": [{"quantity": "1", "price": "0.39"}],
            },
            1,
            Decimal("0.39"),
        )
        self.assertEqual(executed["status"], "filled")
        self.assertEqual(executed["filled_quantity"], 1)
        self.assertEqual(executed["filled_avg_price"], Decimal("0.39"))

    def test_parse_option_order_reads_legs(self):
        from datetime import date

        from trading.services.robinhood import parse_option_order

        parsed = parse_option_order(
            {
                "id": "ord-ko",
                "state": "filled",
                "processed_quantity": "1",
                "average_price": "0.39",
                "quantity": "1",
                "legs": [
                    {
                        "side": "buy",
                        "position_effect": "open",
                        "chain_symbol": "KO",
                        "option_type": "call",
                        "strike_price": "91.0000",
                        "expiration_date": "2026-08-21",
                    }
                ],
            }
        )
        self.assertEqual(parsed["broker_order_id"], "ord-ko")
        self.assertEqual(parsed["status"], "filled")
        self.assertEqual(parsed["ticker"], "KO")
        self.assertEqual(parsed["option_type"], "call")
        self.assertEqual(parsed["strike"], Decimal("91.0000"))
        self.assertEqual(parsed["expiration"], date(2026, 8, 21))
        self.assertEqual(parsed["side"], "buy")
        self.assertEqual(parsed["position_effect"], "open")

    def test_fetch_option_order_matches_by_id(self):
        from trading.services.robinhood import fetch_option_order

        class FakeClient:
            def call_tool(self, name, arguments=None):
                return {
                    "orders": [
                        {
                            "id": "ord-9",
                            "state": "placed",
                            "filled_quantity": "0",
                            "price": "0.39",
                        }
                    ]
                }

        row = fetch_option_order(FakeClient(), "acct-1", "ord-9")
        self.assertEqual(row["id"], "ord-9")
        self.assertEqual(row["state"], "placed")

    def test_find_option_instrument_retries_without_active_filter(self):
        class FakeClient:
            def call_tool(self, name, arguments=None):
                self.calls = getattr(self, "calls", [])
                self.calls.append(arguments or {})
                if arguments and arguments.get("state") == "active":
                    return {"results": []}
                return {"instruments": [{"id": "opt-ko-91"}]}

        client = FakeClient()
        instrument_id = find_option_instrument(
            client, "KO", "call", Decimal("91.0000"), "2026-08-21"
        )
        self.assertEqual(instrument_id, "opt-ko-91")
        self.assertGreater(len(client.calls), 1)

    def test_find_option_instrument_retries_expired_state(self):
        class FakeClient:
            def call_tool(self, name, arguments=None):
                self.calls = getattr(self, "calls", [])
                self.calls.append(arguments or {})
                if arguments and arguments.get("state") == "expired":
                    return {"instruments": [{"id": "opt-exp"}]}
                return {"results": []}

        client = FakeClient()
        instrument_id = find_option_instrument(
            client, "KO", "call", Decimal("91.0000"), "2026-08-21"
        )
        self.assertEqual(instrument_id, "opt-exp")
        self.assertTrue(any(call.get("state") == "expired" for call in client.calls))

    def test_parse_option_position_keeps_bid_and_instrument(self):
        from datetime import date

        from trading.services.robinhood import parse_option_position

        parsed = parse_option_position(
            {
                "chain_symbol": "KO",
                "option_type": "call",
                "strike_price": "91.0000",
                "expiration_date": "2026-08-21",
                "quantity": "1",
                "average_price": "0.39",
                "mark_price": "0.12",
                "bid_price": "0.08",
                "ask_price": "0.15",
                "option_id": "opt-ko-91",
            }
        )
        self.assertEqual(parsed["ticker"], "KO")
        self.assertEqual(parsed["expiration"], date(2026, 8, 21))
        self.assertEqual(parsed["current_price"], Decimal("0.12"))
        self.assertEqual(parsed["bid"], Decimal("0.08"))
        self.assertEqual(parsed["option_id"], "opt-ko-91")

    def test_list_accounts_attaches_portfolio_value(self):
        connection = BrokerConnection(
            encrypted_credentials=encrypt_credentials({"access_token": "tok"})
        )

        class FakeClient:
            def call_tool(self, name, arguments=None):
                if name == "get_accounts":
                    return {
                        "accounts": [
                            {
                                "account_number": "111",
                                "nickname": "Primary",
                                "agentic_allowed": False,
                            },
                            {
                                "account_number": "999",
                                "nickname": "Agentic",
                                "agentic_allowed": True,
                            },
                        ]
                    }
                if arguments and arguments.get("account_number") == "999":
                    return {
                        "total_value": "25.00",
                        "cash": "25.00",
                        "buying_power": {"buying_power": "25.00"},
                    }
                return {"total_value": "1000.00", "cash": "10.00"}

        with patch(
            "trading.services.robinhood.mcp_client_for", return_value=FakeClient()
        ):
            accounts = list_accounts_for(connection)
        by_id = {row["account_number"]: row for row in accounts}
        self.assertEqual(by_id["999"]["equity"], Decimal("25.00"))
        self.assertEqual(by_id["111"]["equity"], Decimal("1000.00"))


class RobinhoodRedirectUriTests(TestCase):
    def test_parses_pasted_localhost_callback_url(self):
        code, state = parse_oauth_callback(
            "http://localhost:8001/api/broker-connections/robinhood/oauth/callback/"
            "?code=abc&state=xyz"
        )
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")

    def test_parses_query_string_only(self):
        code, state = parse_oauth_callback("code=abc&state=xyz")
        self.assertEqual(code, "abc")
        self.assertEqual(state, "xyz")


class RobinhoodOAuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="rhuser",
            email="rhuser@example.com",
            password="longpassword1",
        )
        grant_subscription(email=self.user.email, plan_slug="yearly", note="test")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_direct_robinhood_connect_is_rejected(self):
        resp = self.client.post(
            "/api/broker-connections/",
            {"broker": "robinhood", "username": "x", "password": "y"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("OAuth", str(resp.json()))

    @patch("trading.services.robinhood.register_oauth_client", return_value="client-123")
    @patch("trading.services.robinhood.discover_oauth", return_value=_oauth_metadata())
    def test_oauth_start_returns_authorization_url(self, _discover, _register):
        resp = self.client.post("/api/broker-connections/robinhood/oauth/start/")
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["authorization_url"]
        parsed = urlparse(url)
        self.assertEqual(parsed.netloc, "robinhood.com")
        params = parse_qs(parsed.query)
        self.assertEqual(params["client_id"], ["client-123"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertIn("state", params)
        self.assertTrue(cache.get(f"robinhood:oauth:state:{params['state'][0]}"))
        self.assertTrue(resp.json()["paste_required"])
        self.assertEqual(
            params["redirect_uri"],
            ["http://localhost:8001/api/broker-connections/robinhood/oauth/callback/"],
        )

    @override_settings(
        ROBINHOOD_OAUTH_REDIRECT_URI=(
            "https://agentictradingbackend-production.up.railway.app"
            "/api/broker-connections/robinhood/oauth/callback/"
        ),
        PUBLIC_API_URL="https://agentictradingbackend-production.up.railway.app",
    )
    @patch.dict(
        os.environ,
        {"RAILWAY_PUBLIC_DOMAIN": "agentictradingbackend-production.up.railway.app"},
    )
    @patch("trading.services.robinhood.register_oauth_client", return_value="client-123")
    @patch("trading.services.robinhood.discover_oauth", return_value=_oauth_metadata())
    def test_oauth_start_keeps_loopback_callback_in_production(self, _discover, _register):
        resp = self.client.post("/api/broker-connections/robinhood/oauth/start/")
        self.assertEqual(resp.status_code, 200)
        params = parse_qs(urlparse(resp.json()["authorization_url"]).query)
        self.assertEqual(
            params["redirect_uri"],
            ["http://localhost:8001/api/broker-connections/robinhood/oauth/callback/"],
        )

    @override_settings(FRONTEND_URL="http://localhost:3000")
    @patch("trading.views_user.list_accounts_for")
    @patch("trading.views_user.exchange_code")
    @patch("trading.services.robinhood.discover_oauth", return_value=_oauth_metadata())
    @patch("trading.services.robinhood.register_oauth_client", return_value="client-123")
    def test_oauth_callback_creates_connection(self, _register, _discover, exchange, list_accounts):
        start = self.client.post("/api/broker-connections/robinhood/oauth/start/")
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        exchange.return_value = {
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "client_id": "client-123",
        }
        list_accounts.return_value = [
            {
                "account_number": "999",
                "nickname": "Agentic",
                "type": "cash",
                "state": "active",
                "agentic_allowed": True,
                "option_level": "option_level_3",
                "is_default": False,
            }
        ]
        anon = APIClient()
        resp = anon.get(
            "/api/broker-connections/robinhood/oauth/callback/",
            {"code": "abc", "state": state},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("robinhood=connected", resp["Location"])
        connection = BrokerConnection.objects.get(user=self.user)
        self.assertEqual(connection.broker, "robinhood")
        self.assertEqual(connection.broker_account_id, "999")
        self.assertFalse(connection.is_paper)

    @override_settings(FRONTEND_URL="http://localhost:3000")
    @patch("trading.views_user.list_accounts_for")
    @patch("trading.views_user.exchange_code")
    @patch("trading.services.robinhood.discover_oauth", return_value=_oauth_metadata())
    @patch("trading.services.robinhood.register_oauth_client", return_value="client-123")
    def test_oauth_callback_without_agentic_account(self, _register, _discover, exchange, list_accounts):
        start = self.client.post("/api/broker-connections/robinhood/oauth/start/")
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        exchange.return_value = {
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "client_id": "client-123",
        }
        list_accounts.return_value = [
            {
                "account_number": "111",
                "nickname": "Primary",
                "type": "margin",
                "state": "active",
                "agentic_allowed": False,
                "option_level": "",
                "is_default": True,
            }
        ]
        resp = APIClient().get(
            "/api/broker-connections/robinhood/oauth/callback/",
            {"code": "abc", "state": state},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("robinhood=needs_account", resp["Location"])
        connection = BrokerConnection.objects.get(user=self.user)
        self.assertEqual(connection.broker_account_id, "")
        self.assertIn("Agentic account", connection.last_error)

    @override_settings(FRONTEND_URL="http://localhost:3000")
    @patch("trading.views_user.list_accounts_for")
    @patch("trading.views_user.exchange_code")
    @patch("trading.services.robinhood.discover_oauth", return_value=_oauth_metadata())
    @patch("trading.services.robinhood.register_oauth_client", return_value="client-123")
    def test_oauth_complete_accepts_pasted_callback_url(
        self, _register, _discover, exchange, list_accounts
    ):
        start = self.client.post("/api/broker-connections/robinhood/oauth/start/")
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        exchange.return_value = {
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "client_id": "client-123",
        }
        list_accounts.return_value = [
            {
                "account_number": "999",
                "nickname": "Agentic",
                "type": "cash",
                "state": "active",
                "agentic_allowed": True,
                "option_level": "option_level_3",
                "is_default": False,
            }
        ]
        resp = self.client.post(
            "/api/broker-connections/robinhood/oauth/complete/",
            {
                "callback_url": (
                    "http://localhost:8001/api/broker-connections/robinhood/"
                    f"oauth/callback/?code=abc&state={state}"
                )
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "connected")
        self.assertEqual(resp.json()["connection"]["broker_account_id"], "999")
        self.assertEqual(BrokerConnection.objects.get(user=self.user).broker, "robinhood")

    def test_oauth_complete_requires_callback_url(self):
        resp = self.client.post(
            "/api/broker-connections/robinhood/oauth/complete/",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_select_account_rejects_non_agentic(self):
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        with patch(
            "trading.views_user.list_accounts_for",
            return_value=[
                {
                    "account_number": "111",
                    "nickname": "Primary",
                    "type": "margin",
                    "state": "active",
                    "agentic_allowed": False,
                    "option_level": "",
                    "is_default": True,
                }
            ],
        ):
            resp = self.client.post(
                f"/api/broker-connections/{connection.id}/select-account/",
                {"account_number": "111"},
                format="json",
            )
        self.assertEqual(resp.status_code, 400)

    def test_lists_account_values(self):
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            broker_account_id="999",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        with patch(
            "trading.views_user.list_accounts_for",
            return_value=[
                {
                    "account_number": "111",
                    "nickname": "Primary",
                    "type": "margin",
                    "state": "active",
                    "agentic_allowed": False,
                    "option_level": "",
                    "is_default": True,
                    "equity": Decimal("1000.00"),
                    "cash": Decimal("10.00"),
                    "buying_power": Decimal("10.00"),
                },
                {
                    "account_number": "999",
                    "nickname": "Agentic",
                    "type": "cash",
                    "state": "active",
                    "agentic_allowed": True,
                    "option_level": "",
                    "is_default": False,
                    "equity": Decimal("25.00"),
                    "cash": Decimal("25.00"),
                    "buying_power": Decimal("25.00"),
                },
            ],
        ):
            resp = self.client.get(f"/api/broker-connections/{connection.id}/accounts/")
        self.assertEqual(resp.status_code, 200)
        by_id = {row["account_number"]: row for row in resp.json()}
        self.assertEqual(by_id["999"]["equity"], "25.00")
        connection.refresh_from_db()
        self.assertEqual(connection.last_equity, Decimal("25.00"))

    def test_select_and_clear_agentic_account(self):
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        accounts = [
            {
                "account_number": "111",
                "nickname": "Primary",
                "type": "margin",
                "state": "active",
                "agentic_allowed": False,
                "option_level": "",
                "is_default": True,
            },
            {
                "account_number": "222",
                "nickname": "Agentic",
                "type": "cash",
                "state": "active",
                "agentic_allowed": True,
                "option_level": "option_level_3",
                "is_default": False,
            },
        ]
        with patch("trading.views_user.list_accounts_for", return_value=accounts):
            selected = self.client.post(
                f"/api/broker-connections/{connection.id}/select-account/",
                {"account_number": "222"},
                format="json",
            )
            self.assertEqual(selected.status_code, 200)
            self.assertEqual(selected.json()["broker_account_id"], "222")
            self.assertTrue(selected.json()["agentic_ready"])
            cleared = self.client.post(
                f"/api/broker-connections/{connection.id}/select-account/",
                {"account_number": ""},
                format="json",
            )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["broker_account_id"], "")
        self.assertFalse(cleared.json()["agentic_ready"])

    def test_assign_strategy_to_agentic_account(self):
        from django.core.management import call_command

        from trading.models import InvestmentTier, Strategy

        call_command("seed_trading")
        strategy = Strategy.objects.get(slug="copy-trade")
        tier = InvestmentTier.objects.get(slug="balanced")
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        accounts = [
            {
                "account_number": "111",
                "nickname": "Primary",
                "type": "margin",
                "state": "active",
                "agentic_allowed": False,
                "option_level": "",
                "is_default": True,
            },
            {
                "account_number": "222",
                "nickname": "Agentic",
                "type": "cash",
                "state": "active",
                "agentic_allowed": True,
                "option_level": "option_level_3",
                "is_default": False,
            },
        ]
        with patch(
            "trading.serializers.list_account_summaries_for", return_value=accounts
        ):
            resp = self.client.put(
                "/api/assignment/",
                {
                    "strategy_id": strategy.id,
                    "investment_tier_id": tier.id,
                    "broker_account_id": "222",
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["broker_account_id"], "222")
        connection.refresh_from_db()
        self.assertEqual(connection.broker_account_id, "222")

    def test_cannot_assign_strategy_to_non_agentic_account(self):
        from django.core.management import call_command

        from trading.models import InvestmentTier, Strategy

        call_command("seed_trading")
        strategy = Strategy.objects.get(slug="copy-trade")
        tier = InvestmentTier.objects.get(slug="balanced")
        BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        accounts = [
            {
                "account_number": "111",
                "nickname": "Primary",
                "agentic_allowed": False,
            }
        ]
        with patch(
            "trading.serializers.list_account_summaries_for", return_value=accounts
        ):
            resp = self.client.put(
                "/api/assignment/",
                {
                    "strategy_id": strategy.id,
                    "investment_tier_id": tier.id,
                    "broker_account_id": "111",
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 400)

    def test_agent_tools_lists_catalog(self):
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )

        class FakeClient:
            def list_tools(self):
                return [{"name": "get_accounts", "description": "Live accounts"}]

        with patch(
            "trading.services.robinhood.mcp_client_for", return_value=FakeClient()
        ):
            resp = self.client.get(
                f"/api/broker-connections/{connection.id}/agent-tools/"
            )
        self.assertEqual(resp.status_code, 200)
        by_name = {row["name"]: row for row in resp.json()}
        self.assertTrue(by_name["get_accounts"]["available"])
        self.assertEqual(by_name["get_accounts"]["description"], "Live accounts")
        self.assertIn("place_option_order", by_name)
        self.assertFalse(by_name["place_option_order"]["available"])

    def test_account_detail_returns_strategy_and_performance(self):
        from django.core.management import call_command

        from trading.models import InvestmentTier, Strategy
        from trading.services.jobs import set_assignment

        call_command("seed_trading")
        strategy = Strategy.objects.get(slug="copy-trade")
        tier = InvestmentTier.objects.get(slug="balanced")
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            broker_account_id="222",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials({"access_token": "tok"}),
        )
        set_assignment(
            self.user,
            strategy,
            tier,
            broker_account_id="222",
        )
        account = {
            "account_number": "222",
            "nickname": "Agentic",
            "type": "cash",
            "state": "active",
            "agentic_allowed": True,
            "option_level": "option_level_3",
            "is_default": False,
            "equity": Decimal("25.00"),
            "cash": Decimal("25.00"),
            "buying_power": Decimal("25.00"),
        }
        with patch("trading.views_user.get_account_for", return_value=account):
            resp = self.client.get(
                f"/api/broker-connections/{connection.id}/accounts/222/"
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["account"]["account_number"], "222")
        self.assertEqual(body["account"]["equity"], "25.00")
        self.assertTrue(body["trading_enabled"])
        self.assertEqual(body["assignment"]["broker_account_id"], "222")
        self.assertEqual(body["assignment"]["strategy"]["slug"], "copy-trade")
        self.assertIn("lifetime_total_pnl", body["performance"])


class RobinhoodBrokerClientTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="liveuser",
            email="liveuser@example.com",
            password="longpassword1",
        )
        self.connection = BrokerConnection.objects.create(
            user=self.user,
            broker="robinhood",
            broker_account_id="999",
            status=BrokerConnection.Status.CONNECTED,
            encrypted_credentials=encrypt_credentials(
                {
                    "access_token": "tok",
                    "refresh_token": "ref",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                    "client_id": "client-123",
                }
            ),
        )

    def test_uses_live_client_when_oauth_tokens_present(self):
        client = get_broker_client(self.connection)
        self.assertIsInstance(client, RobinhoodBrokerClient)

    def test_falls_back_to_stub_without_tokens(self):
        self.connection.encrypted_credentials = encrypt_credentials({})
        self.connection.save()
        client = get_broker_client(self.connection)
        self.assertIsInstance(client, StubBrokerClient)

    @patch("trading.services.brokers.place_option_order")
    @patch("trading.services.brokers.find_option_instrument", return_value="opt-1")
    @patch("trading.services.brokers.mcp_client_for")
    def test_buy_to_open_places_option_order(self, mcp_for, _instrument, place):
        mcp_for.return_value = object()
        place.return_value = {
            "broker_order_id": "ord-1",
            "status": "filled",
            "filled_quantity": 2,
            "filled_avg_price": Decimal("1.25"),
        }
        fill = RobinhoodBrokerClient(self.connection).buy_to_open(
            "AAPL", "call", Decimal("200"), "2026-12-18", 2, Decimal("1.25")
        )
        self.assertEqual(fill.broker_order_id, "ord-1")
        self.assertEqual(fill.filled_quantity, 2)
        place.assert_called_once()

    @patch("trading.services.brokers.find_option_instrument")
    @patch("trading.services.brokers.mcp_client_for")
    def test_quote_falls_back_to_open_position_on_expiration_day(self, mcp_for, instrument):
        from datetime import date

        from trading.services.robinhood import RobinhoodError

        mcp_for.return_value = object()
        instrument.side_effect = RobinhoodError(
            "No Robinhood option instrument for KO call 91.0000 2026-08-21."
        )
        broker = RobinhoodBrokerClient(self.connection)
        with patch.object(
            broker,
            "list_open_option_positions",
            return_value=[
                {
                    "ticker": "KO",
                    "option_type": "call",
                    "strike": Decimal("91.00"),
                    "expiration": date(2026, 8, 21),
                    "current_price": Decimal("0.12"),
                    "bid": Decimal("0.08"),
                    "ask": Decimal("0.15"),
                    "option_id": "opt-ko-91",
                }
            ],
        ):
            market = broker.get_option_market(
                "KO", "call", Decimal("91"), date(2026, 8, 21)
            )
        self.assertEqual(market.mark, Decimal("0.12"))
        self.assertEqual(market.bid, Decimal("0.08"))
        self.assertEqual(market.instrument_id, "opt-ko-91")
        self.assertEqual(market.last_day_exit, Decimal("0.08"))

    @patch("trading.services.brokers.place_option_order")
    @patch("trading.services.brokers.find_option_instrument")
    @patch("trading.services.brokers.mcp_client_for")
    def test_sell_to_close_uses_open_position_instrument(self, mcp_for, instrument, place):
        from datetime import date

        from trading.services.robinhood import RobinhoodError

        mcp_for.return_value = object()
        instrument.side_effect = RobinhoodError("No Robinhood option instrument")
        place.return_value = {
            "broker_order_id": "ord-sell",
            "status": "filled",
            "filled_quantity": 1,
            "filled_avg_price": Decimal("0.08"),
        }
        broker = RobinhoodBrokerClient(self.connection)
        with patch.object(
            broker,
            "list_open_option_positions",
            return_value=[
                {
                    "ticker": "KO",
                    "option_type": "call",
                    "strike": Decimal("91.00"),
                    "expiration": date(2026, 8, 21),
                    "option_id": "opt-ko-91",
                }
            ],
        ):
            fill = broker.sell_to_close(
                "KO", "call", Decimal("91"), date(2026, 8, 21), 1, Decimal("0.08")
            )
        self.assertEqual(fill.broker_order_id, "ord-sell")
        self.assertEqual(place.call_args.args[2], "opt-ko-91")
