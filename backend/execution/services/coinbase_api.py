"""Coinbase Advanced Trade REST (spot) — CDP JWT per request."""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.coinbase.com"


class CoinbaseApiError(Exception):
    pass


@dataclass
class CoinbaseConfig:
    api_key_name: str
    private_key_pem: str
    base_url: str


def _pem_from_env() -> str:
    raw = (getattr(settings, "COINBASE_ADVANCED_API_PRIVATE_KEY_PEM", None) or "").strip()
    if raw:
        return raw.replace("\\n", "\n")
    path = (getattr(settings, "COINBASE_ADVANCED_API_PRIVATE_KEY_FILE", None) or "").strip()
    if path:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    return ""


def load_coinbase_config() -> CoinbaseConfig:
    key_name = (getattr(settings, "COINBASE_ADVANCED_API_KEY_NAME", None) or "").strip()
    pem = _pem_from_env()
    if not key_name or not pem:
        raise CoinbaseApiError("Coinbase Advanced Trade credentials not configured in environment.")
    base = (getattr(settings, "COINBASE_ADVANCED_API_BASE_URL", None) or DEFAULT_BASE).strip().rstrip("/")
    return CoinbaseConfig(api_key_name=key_name, private_key_pem=pem, base_url=base)


def build_jwt(
    api_key_name: str,
    private_key_pem: str,
    method: str,
    request_path: str,
    *,
    request_host: str = "api.coinbase.com",
) -> str:
    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    uri = f"{method.upper()} {request_host}{request_path}"
    now = int(time.time())
    payload = {
        "sub": api_key_name,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": uri,
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": api_key_name, "nonce": secrets.token_hex(16)},
    )


class CoinbaseAdvancedClient:
    def __init__(self, config: CoinbaseConfig | None = None):
        self.config = config or load_coinbase_config()

    def request(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        if not path.startswith("/"):
            path = f"/{path}"
        from urllib.parse import urlparse

        host = urlparse(self.config.base_url).netloc or "api.coinbase.com"
        token = build_jwt(
            self.config.api_key_name,
            self.config.private_key_pem,
            method,
            path,
            request_host=host,
        )
        url = urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))
        response = requests.request(
            method.upper(),
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=json_body,
            timeout=30,
        )
        if response.status_code >= 400:
            logger.warning("Coinbase HTTP %s", response.status_code)
            raise CoinbaseApiError(f"Coinbase HTTP {response.status_code}")
        if not response.text:
            return {}
        return response.json()

    def list_accounts(self) -> dict:
        return self.request("GET", "/api/v3/brokerage/accounts")

    def get_product(self, product_id: str) -> dict:
        return self.request("GET", f"/api/v3/brokerage/market/products/{product_id}")

    def create_limit_order(
        self,
        *,
        product_id: str,
        side: str,
        base_size: str,
        limit_price: str,
        client_order_id: str,
    ) -> dict:
        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": base_size,
                    "limit_price": limit_price,
                    "post_only": False,
                }
            },
        }
        return self.request("POST", "/api/v3/brokerage/orders", json_body=body)

    def get_order(self, order_id: str) -> dict:
        return self.request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")

    def cancel_orders(self, order_ids: list[str]) -> dict:
        return self.request("POST", "/api/v3/brokerage/orders/batch_cancel", json_body={"order_ids": order_ids})

    def list_fills(self, *, product_id: str | None = None, limit: int = 50) -> dict:
        query = f"?limit={limit}"
        if product_id:
            query += f"&product_id={product_id}"
        return self.request("GET", f"/api/v3/brokerage/orders/historical/fills{query}")


def accounts_buying_power(payload: dict) -> tuple[Decimal | None, Decimal | None]:
    accounts = payload.get("accounts") or []
    available = Decimal("0")
    equity = Decimal("0")
    for row in accounts:
        bal = row.get("available_balance") or {}
        val = bal.get("value")
        if val is not None:
            available += Decimal(str(val))
        hold = row.get("hold") or {}
        if hold.get("value") is not None:
            equity += Decimal(str(hold.get("value")))
        if row.get("balance") and row["balance"].get("value"):
            equity += Decimal(str(row["balance"]["value"]))
    if not accounts:
        return None, None
    return equity or available, available


def product_mid_price(payload: dict) -> Decimal | None:
    product = payload.get("product") or payload
    price = product.get("price") or product.get("mid_market_price")
    if price is not None:
        return Decimal(str(price))
    bid = product.get("bid")
    ask = product.get("ask")
    if bid and ask:
        return (Decimal(str(bid)) + Decimal(str(ask))) / 2
    return None


def parse_order_response(payload: dict, *, fallback_qty: Decimal, fallback_price: Decimal) -> tuple[str, str, int, Decimal]:
    order = payload.get("order") or payload.get("success_response") or payload
    if isinstance(order, dict) and order.get("order_id"):
        oid = str(order["order_id"])
    else:
        oid = str(order.get("order_id") or payload.get("order_id") or "")
    status = str(order.get("status") or "OPEN").lower()
    filled_size = order.get("filled_size") or order.get("filled_base_size") or "0"
    filled_qty = int(Decimal(str(filled_size)))
    avg = order.get("average_filled_price") or order.get("limit_price")
    avg_price = Decimal(str(avg)) if avg is not None else fallback_price
    if status in ("open", "pending"):
        status = "submitted"
    if status == "filled":
        status = "filled"
    if filled_qty <= 0 and status == "filled":
        filled_qty = int(fallback_qty)
    return oid, status, filled_qty, avg_price
