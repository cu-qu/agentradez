"""Kalshi trade-api v2 HTTP client (RSA-PSS signed requests)."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"
DEFAULT_PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiApiError(Exception):
    pass


@dataclass
class KalshiConfig:
    api_key_id: str
    private_key_pem: str
    base_url: str


def _pem_from_env() -> str:
    raw = (getattr(settings, "KALSHI_PRIVATE_KEY_PEM", None) or "").strip()
    if raw:
        return raw.replace("\\n", "\n")
    path = (getattr(settings, "KALSHI_PRIVATE_KEY_FILE", None) or "").strip()
    if path:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    return ""


def load_kalshi_config() -> KalshiConfig:
    key_id = (getattr(settings, "KALSHI_API_KEY_ID", None) or "").strip()
    pem = _pem_from_env()
    if not key_id or not pem:
        raise KalshiApiError("Kalshi credentials not configured in environment.")
    base = (getattr(settings, "KALSHI_API_BASE_URL", None) or "").strip().rstrip("/")
    if not base:
        demo = getattr(settings, "KALSHI_USE_DEMO", True)
        base = DEFAULT_DEMO_BASE if demo else DEFAULT_PROD_BASE
    return KalshiConfig(api_key_id=key_id, private_key_pem=pem, base_url=base)


def _sign(private_key_pem: str, timestamp_ms: str, method: str, path: str) -> str:
    message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


class KalshiRestClient:
    def __init__(self, config: KalshiConfig | None = None):
        self.config = config or load_kalshi_config()

    def _api_path(self, resource: str) -> str:
        """Signed path always includes /trade-api/v2 prefix."""
        resource = resource if resource.startswith("/") else f"/{resource}"
        if resource.startswith("/trade-api/v2"):
            return resource.split("?")[0]
        return f"/trade-api/v2{resource}".split("?")[0]

    def request(self, method: str, resource: str, *, json_body: dict | None = None) -> dict:
        path = self._api_path(resource)
        timestamp = str(int(time.time() * 1000))
        signature = _sign(self.config.private_key_pem, timestamp, method, path)
        base = self.config.base_url.rstrip("/")
        url = f"{base}/{resource.lstrip('/')}"
        headers = {
            "KALSHI-ACCESS-KEY": self.config.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "Content-Type": "application/json",
        }
        response = requests.request(
            method.upper(),
            url,
            headers=headers,
            json=json_body,
            timeout=30,
        )
        if response.status_code >= 400:
            logger.warning("Kalshi HTTP %s %s", response.status_code, response.text[:200])
            raise KalshiApiError(f"Kalshi HTTP {response.status_code}")
        if not response.text:
            return {}
        return response.json()

    def balance(self) -> dict:
        return self.request("GET", "/portfolio/balance")

    def positions(self) -> dict:
        return self.request("GET", "/portfolio/positions")

    def orders(self, *, limit: int = 100) -> dict:
        return self.request("GET", f"/portfolio/orders?limit={limit}")

    def get_order(self, order_id: str) -> dict:
        return self.request("GET", f"/portfolio/orders/{order_id}")

    def create_limit_order(
        self,
        *,
        ticker: str,
        action: str,
        side: str,
        count: int,
        yes_price_cents: int | None,
        no_price_cents: int | None,
        client_order_id: str,
    ) -> dict:
        body: dict = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "type": "limit",
            "client_order_id": client_order_id,
            "time_in_force": "good_till_canceled",
        }
        if yes_price_cents is not None:
            body["yes_price"] = yes_price_cents
        if no_price_cents is not None:
            body["no_price"] = no_price_cents
        return self.request("POST", "/portfolio/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict:
        return self.request("DELETE", f"/portfolio/orders/{order_id}")

    def market(self, ticker: str) -> dict:
        return self.request("GET", f"/markets/{ticker}")


def balance_buying_power_usd(payload: dict) -> Decimal | None:
    row = payload.get("balance") or payload
    for key in ("balance", "available_balance", "buying_power"):
        if key in row and row[key] is not None:
            cents = row[key]
            if isinstance(cents, (int, float)):
                return Decimal(str(cents)) / Decimal("100")
            return Decimal(str(cents))
    return None


def market_yes_mid_dollars(payload: dict) -> Decimal | None:
    market = payload.get("market") or payload
    yes_bid = market.get("yes_bid") or market.get("yes_bid_dollars")
    yes_ask = market.get("yes_ask") or market.get("yes_ask_dollars")
    last = market.get("last_price") or market.get("last_price_dollars")
    if last is not None:
        return _price_to_dollars(last)
    if yes_bid is not None and yes_ask is not None:
        return (_price_to_dollars(yes_bid) + _price_to_dollars(yes_ask)) / 2
    if yes_ask is not None:
        return _price_to_dollars(yes_ask)
    if yes_bid is not None:
        return _price_to_dollars(yes_bid)
    return None


def _price_to_dollars(value) -> Decimal:
    dec = Decimal(str(value))
    if dec > 1:
        return dec / Decimal("100")
    return dec


def dollars_to_yes_cents(price: Decimal) -> int:
    cents = int((price * Decimal("100")).quantize(Decimal("1")))
    return max(1, min(99, cents))


def parse_order_fill(payload: dict, *, fallback_qty: int, fallback_price: Decimal) -> tuple[str, str, int, Decimal]:
    order = payload.get("order") or payload
    order_id = str(order.get("order_id") or order.get("id") or "")
    status = str(order.get("status") or "submitted").lower()
    filled = order.get("fill_count") or order.get("filled_count") or 0
    try:
        filled_qty = int(Decimal(str(filled)))
    except Exception:
        filled_qty = 0
    avg = order.get("average_fill_price") or order.get("avg_fill_price")
    if avg is not None:
        avg_price = _price_to_dollars(avg)
    else:
        yes_price = order.get("yes_price")
        avg_price = _price_to_dollars(yes_price) if yes_price is not None else fallback_price
    if filled_qty <= 0 and status in ("executed", "filled"):
        filled_qty = fallback_qty
    if status in ("resting", "open"):
        status = "submitted"
    return order_id, status, filled_qty, avg_price
