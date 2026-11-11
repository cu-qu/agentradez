"""Mocked HTTP tests for Kalshi and Coinbase harness adapters."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, override_settings

from execution.models import HarnessSignal
from execution.services.coinbase_broker import CoinbaseHarnessClient
from execution.services.kalshi_api import KalshiConfig, KalshiRestClient, _sign
from execution.services.kalshi_broker import KalshiHarnessClient


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@override_settings(
    KALSHI_API_KEY_ID="key-id",
    KALSHI_PRIVATE_KEY_PEM=_rsa_pem(),
    KALSHI_API_BASE_URL="https://demo-api.kalshi.co/trade-api/v2",
)
class KalshiApiTests(SimpleTestCase):
    def test_sign_produces_base64(self):
        pem = _rsa_pem()
        sig = _sign(pem, "1700000000000", "GET", "/trade-api/v2/portfolio/balance")
        self.assertTrue(len(sig) > 20)

    @patch("execution.services.kalshi_api.requests.request")
    def test_balance_request_headers(self, req):
        req.return_value = MagicMock(status_code=200, text='{"balance":{"balance":5000}}')
        client = KalshiRestClient(
            KalshiConfig(api_key_id="key-id", private_key_pem=_rsa_pem(), base_url="https://demo-api.kalshi.co/trade-api/v2")
        )
        client.balance()
        headers = req.call_args.kwargs["headers"]
        self.assertEqual(headers["KALSHI-ACCESS-KEY"], "key-id")
        self.assertIn("KALSHI-ACCESS-SIGNATURE", headers)

    @patch("execution.services.kalshi_api.requests.request")
    def test_create_limit_order_body(self, req):
        req.return_value = MagicMock(
            status_code=200,
            text='{"order":{"order_id":"oid-1","status":"resting","fill_count":"0"}}',
        )
        client = KalshiRestClient(
            KalshiConfig(api_key_id="key-id", private_key_pem=_rsa_pem(), base_url="https://demo-api.kalshi.co/trade-api/v2")
        )
        client.create_limit_order(
            ticker="TEST-MARKET",
            action="buy",
            side="yes",
            count=2,
            yes_price_cents=45,
            no_price_cents=None,
            client_order_id="client-1",
        )
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["type"], "limit")
        self.assertEqual(body["yes_price"], 45)
        self.assertEqual(body["time_in_force"], "good_till_canceled")

    @patch("execution.services.kalshi_broker.KalshiRestClient")
    def test_harness_place_entry(self, client_cls):
        mock = MagicMock()
        mock.create_limit_order.return_value = {
            "order": {"order_id": "o1", "status": "executed", "fill_count": "1", "yes_price": 40}
        }
        mock.market.return_value = {"market": {"yes_bid": 39, "yes_ask": 41}}
        conn = MagicMock()
        conn.encrypted_credentials = ""
        broker = KalshiHarnessClient(connection=conn, client=mock)
        signal = HarnessSignal(
            symbol="TICKER",
            side="buy",
            quantity=1,
            entry_rule={"kalshi_side": "yes"},
            market="kalshi",
        )
        fill = broker.place_limit_entry(signal, 1, Decimal("0.40"))
        self.assertEqual(fill.broker_order_id, "o1")
        self.assertEqual(fill.filled_quantity, 1)


@override_settings(
    COINBASE_ADVANCED_API_KEY_NAME="organizations/x/apiKeys/y",
    COINBASE_ADVANCED_API_PRIVATE_KEY_PEM="-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEICDummy\n-----END EC PRIVATE KEY-----\n",
)
class CoinbaseConfigTests(SimpleTestCase):
    def test_missing_credentials_raises(self):
        from execution.services.coinbase_api import CoinbaseApiError, load_coinbase_config

        with override_settings(COINBASE_ADVANCED_API_KEY_NAME="", COINBASE_ADVANCED_API_PRIVATE_KEY_PEM=""):
            with self.assertRaises(CoinbaseApiError):
                load_coinbase_config()


class CoinbaseHarnessMockTests(SimpleTestCase):
    @patch("execution.services.coinbase_broker.CoinbaseAdvancedClient")
    def test_limit_order_side_buy(self, client_cls):
        mock = MagicMock()
        mock.get_product.return_value = {"product": {"price": "100.50"}}
        mock.create_limit_order.return_value = {
            "success_response": {"order_id": "cb-1", "status": "OPEN"}
        }
        client_cls.return_value = mock
        broker = CoinbaseHarnessClient(connection=MagicMock(encrypted_credentials=""), client=mock)
        signal = HarnessSignal(symbol="BTC-USD", side="buy", quantity=1, market="coinbase")
        quote = broker.get_quote(signal)
        self.assertEqual(quote.mark, Decimal("100.50"))
        fill = broker.place_limit_entry(signal, 1, Decimal("99.00"))
        self.assertEqual(fill.broker_order_id, "cb-1")
        kwargs = mock.create_limit_order.call_args.kwargs
        self.assertEqual(kwargs["side"], "BUY")

    @patch("execution.services.coinbase_broker.CoinbaseAdvancedClient")
    def test_cancel_batch(self, client_cls):
        mock = MagicMock()
        client_cls.return_value = mock
        broker = CoinbaseHarnessClient(connection=MagicMock(encrypted_credentials=""), client=mock)
        broker.cancel_order("order-uuid")
        mock.cancel_orders.assert_called_once_with(["order-uuid"])
