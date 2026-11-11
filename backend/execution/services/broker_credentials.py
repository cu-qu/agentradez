"""Load per-user broker API credentials from BrokerConnection (env fallback for dev)."""

from __future__ import annotations

from django.conf import settings

from trading.models import BrokerConnection
from trading.services.credentials import decrypt_credentials

from execution.services.coinbase_api import CoinbaseConfig, CoinbaseApiError
from execution.services.kalshi_api import KalshiConfig, KalshiApiError


def kalshi_config_for(connection: BrokerConnection | None) -> KalshiConfig:
    if connection and connection.encrypted_credentials:
        creds = decrypt_credentials(connection.encrypted_credentials)
        key_id = (creds.get("kalshi_api_key_id") or creds.get("api_key_id") or "").strip()
        pem = (creds.get("kalshi_private_key_pem") or creds.get("private_key_pem") or "").strip()
        base = (creds.get("kalshi_api_base_url") or "").strip().rstrip("/")
        if key_id and pem:
            if not base:
                from execution.services.kalshi_api import DEFAULT_DEMO_BASE, DEFAULT_PROD_BASE

                demo = creds.get("kalshi_use_demo", True)
                base = DEFAULT_DEMO_BASE if demo else DEFAULT_PROD_BASE
            return KalshiConfig(api_key_id=key_id, private_key_pem=pem.replace("\\n", "\n"), base_url=base)
    from execution.services.kalshi_api import load_kalshi_config

    return load_kalshi_config()


def coinbase_config_for(connection: BrokerConnection | None) -> CoinbaseConfig:
    if connection and connection.encrypted_credentials:
        creds = decrypt_credentials(connection.encrypted_credentials)
        name = (creds.get("coinbase_api_key_name") or creds.get("api_key_name") or "").strip()
        pem = (creds.get("coinbase_private_key_pem") or creds.get("private_key_pem") or "").strip()
        base = (creds.get("coinbase_api_base_url") or "").strip()
        if name and pem:
            if not base:
                base = "https://api.coinbase.com"
            return CoinbaseConfig(
                api_key_name=name,
                private_key_pem=pem.replace("\\n", "\n"),
                base_url=base.rstrip("/"),
            )
    from execution.services.coinbase_api import load_coinbase_config

    try:
        return load_coinbase_config()
    except CoinbaseApiError as exc:
        raise exc
