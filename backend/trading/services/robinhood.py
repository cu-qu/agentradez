"""Robinhood Agentic Trading MCP client (OAuth 2.1 + PKCE, streamable HTTP)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache

from trading.services.credentials import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)

MCP_URL = "https://agent.robinhood.com/mcp/trading"
RESOURCE_METADATA_URL = (
    "https://agent.robinhood.com/.well-known/oauth-protected-resource/mcp/trading"
)
AUTH_SERVER_METADATA_URL = (
    "https://agent.robinhood.com/.well-known/oauth-authorization-server/mcp/trading"
)
DEFAULT_AUTHORIZATION_ENDPOINT = "https://robinhood.com/oauth"
DEFAULT_TOKEN_ENDPOINT = "https://api.robinhood.com/oauth2/token/"
DEFAULT_REGISTRATION_ENDPOINT = "https://agent.robinhood.com/oauth/trading/register"
DEFAULT_SCOPES = ["internal"]

OAUTH_STATE_TTL = 15 * 60
CLIENT_ID_TTL = 30 * 24 * 60 * 60
HTTP_TIMEOUT = 20
LOOPBACK_OAUTH_ORIGIN = "http://localhost:8001"
OAUTH_CALLBACK_PATH = "/api/broker-connections/robinhood/oauth/callback/"


class RobinhoodError(Exception):
    pass


def is_loopback_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def oauth_redirect_uri(request=None, callback_path: str = OAUTH_CALLBACK_PATH) -> str:
    """Robinhood Agentic OAuth only completes for loopback redirects.

    Hosted HTTPS callbacks register, then fail on Robinhood's consent screen.
    Always send localhost so the web app can paste the callback URL into
    POST /api/broker-connections/robinhood/oauth/complete/.
    """
    del request  # authorize URI is not the public API origin
    path = callback_path or OAUTH_CALLBACK_PATH
    explicit = getattr(settings, "ROBINHOOD_OAUTH_REDIRECT_URI", "").strip()
    if explicit and is_loopback_url(explicit):
        return explicit
    public = getattr(settings, "PUBLIC_API_URL", "").rstrip("/")
    if public and is_loopback_url(public):
        return f"{public}{path}"
    return f"{LOOPBACK_OAUTH_ORIGIN}{path}"


def parse_oauth_callback(raw: str) -> tuple[str, str]:
    """Read code/state from a pasted localhost URL, query string, or full callback."""
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise RobinhoodError(
            "Paste the full URL from the address bar after allowing Robinhood."
        )
    if "code=" in text and "://" not in text.split("?", 1)[0]:
        text = "http://localhost/?" + text.split("?", 1)[-1].lstrip("?")
    query = parse_qs(urlsplit(text).query)
    error = (query.get("error") or [""])[0]
    if error:
        raise RobinhoodError(error.replace("_", " "))
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    if not code or not state:
        raise RobinhoodError(
            "That URL is missing code or state. Copy the entire address-bar URL."
        )
    return code, state


def mcp_url() -> str:
    return getattr(settings, "ROBINHOOD_MCP_URL", MCP_URL).rstrip("/")


def _get_json(url: str) -> dict:
    response = requests.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RobinhoodError("Unexpected metadata response.")
    return payload


def discover_oauth() -> dict:
    cached = cache.get("robinhood:oauth:metadata")
    if cached:
        return cached
    try:
        metadata = _get_json(AUTH_SERVER_METADATA_URL)
    except Exception:  # noqa: BLE001 — fall back to last-known Robinhood endpoints
        try:
            resource = _get_json(RESOURCE_METADATA_URL)
            servers = resource.get("authorization_servers") or []
            if servers:
                issuer = str(servers[0]).rstrip("/")
                metadata = _get_json(f"{issuer}/.well-known/oauth-authorization-server")
            else:
                metadata = {}
        except Exception:
            metadata = {}
    discovered = {
        "authorization_endpoint": metadata.get(
            "authorization_endpoint", DEFAULT_AUTHORIZATION_ENDPOINT
        ),
        "token_endpoint": metadata.get("token_endpoint", DEFAULT_TOKEN_ENDPOINT),
        "registration_endpoint": metadata.get(
            "registration_endpoint", DEFAULT_REGISTRATION_ENDPOINT
        ),
        "scopes": metadata.get("scopes_supported") or DEFAULT_SCOPES,
    }
    cache.set("robinhood:oauth:metadata", discovered, 60 * 60)
    return discovered


def generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


def _client_id_cache_key(redirect_uri: str) -> str:
    return f"robinhood:oauth:client_id:{redirect_uri}"


def register_oauth_client(redirect_uri: str) -> str:
    configured = getattr(settings, "ROBINHOOD_CLIENT_ID", "").strip()
    if configured:
        return configured
    cached = cache.get(_client_id_cache_key(redirect_uri))
    if cached:
        return cached
    endpoints = discover_oauth()
    payload = {
        "client_name": "Agentradez",
        "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    response = requests.post(
        endpoints["registration_endpoint"],
        json=payload,
        timeout=HTTP_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    if response.status_code not in (200, 201):
        raise RobinhoodError(
            f"Robinhood client registration failed ({response.status_code}): "
            f"{response.text[:300]}"
        )
    data = response.json()
    client_id = data.get("client_id")
    if not client_id:
        raise RobinhoodError("Robinhood registration did not return a client_id.")
    cache.set(_client_id_cache_key(redirect_uri), client_id, CLIENT_ID_TTL)
    return client_id


def start_oauth(user_id: int, redirect_uri: str) -> str:
    endpoints = discover_oauth()
    client_id = register_oauth_client(redirect_uri)
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    cache.set(
        f"robinhood:oauth:state:{state}",
        {
            "user_id": user_id,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        },
        OAUTH_STATE_TTL,
    )
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": mcp_url(),
        "scope": " ".join(endpoints["scopes"]),
    }
    return f"{endpoints['authorization_endpoint']}?{urlencode(params)}"


def pop_oauth_state(state: str) -> dict:
    key = f"robinhood:oauth:state:{state}"
    pending = cache.get(key)
    if not pending:
        raise RobinhoodError("Robinhood login expired or is invalid. Start again.")
    cache.delete(key)
    return pending


def _token_payload(data: dict, extra: dict | None = None) -> dict:
    body = dict(data)
    if extra:
        body.update(extra)
    if "resource" not in body:
        body["resource"] = mcp_url()
    return body


def exchange_code(code: str, pending: dict) -> dict:
    endpoints = discover_oauth()
    response = requests.post(
        endpoints["token_endpoint"],
        data=_token_payload(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": pending["client_id"],
                "redirect_uri": pending["redirect_uri"],
                "code_verifier": pending["code_verifier"],
            }
        ),
        timeout=HTTP_TIMEOUT,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        raise RobinhoodError(
            f"Robinhood token exchange failed ({response.status_code}): "
            f"{response.text[:300]}"
        )
    return normalize_tokens(response.json(), client_id=pending["client_id"])


def refresh_access_token(tokens: dict) -> dict:
    refresh_token = tokens.get("refresh_token")
    client_id = tokens.get("client_id")
    if not refresh_token or not client_id:
        raise RobinhoodError("Robinhood session expired. Reconnect the account.")
    endpoints = discover_oauth()
    response = requests.post(
        endpoints["token_endpoint"],
        data=_token_payload(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
        ),
        timeout=HTTP_TIMEOUT,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        raise RobinhoodError(
            f"Robinhood token refresh failed ({response.status_code}): "
            f"{response.text[:300]}"
        )
    refreshed = normalize_tokens(response.json(), client_id=client_id)
    if not refreshed.get("refresh_token"):
        refreshed["refresh_token"] = refresh_token
    return refreshed


def normalize_tokens(payload: dict, client_id: str = "") -> dict:
    access_token = payload.get("access_token")
    if not access_token:
        raise RobinhoodError("Robinhood did not return an access token.")
    expires_in = int(payload.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in * 0.9))
    return {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token") or "",
        "token_type": payload.get("token_type") or "Bearer",
        "expires_at": expires_at.isoformat(),
        "client_id": payload.get("client_id") or client_id,
    }


def tokens_expired(tokens: dict) -> bool:
    raw = tokens.get("expires_at")
    if not raw:
        return False
    try:
        expires_at = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expires_at


def parse_sse_or_json(body: str) -> list[dict]:
    results: list[dict] = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("data:"):
            json_str = stripped[5:].strip()
            if not json_str:
                continue
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                results.append(parsed)
    if not results and body.strip():
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, dict):
            results.append(parsed)
    return results


def extract_tool_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    if result.get("isError"):
        messages = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                messages.append(item.get("text") or "")
        raise RobinhoodError("; ".join(m for m in messages if m) or "Robinhood tool error.")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured.get("data", structured)
    for item in result.get("content") or []:
        if not (isinstance(item, dict) and item.get("type") == "text"):
            continue
        text = item.get("text") or ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed["data"]
        return parsed
    return result


class RobinhoodMcpClient:
    def __init__(self, access_token: str, on_refresh=None):
        self.access_token = access_token
        self.on_refresh = on_refresh
        self.session_id = ""
        self._request_id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, payload: dict, retry: bool = True) -> tuple[str, requests.Response]:
        response = requests.post(
            mcp_url(),
            json=payload,
            headers=self._headers(),
            timeout=HTTP_TIMEOUT,
        )
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session_id = session_id
        if response.status_code == 401 and retry and self.on_refresh:
            self.access_token = self.on_refresh()
            return self._post(payload, retry=False)
        if response.status_code >= 400:
            raise RobinhoodError(
                f"Robinhood MCP HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.text, response

    def _rpc(self, method: str, params: dict | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params
        raw, _ = self._post(payload)
        messages = parse_sse_or_json(raw)
        if not messages:
            raise RobinhoodError("Empty response from Robinhood MCP.")
        for message in messages:
            if "error" in message:
                error = message["error"] or {}
                raise RobinhoodError(error.get("message") or "Robinhood MCP error.")
            if "result" in message:
                return message["result"]
        return messages[0]

    def initialize(self) -> None:
        if self._initialized:
            return
        params = {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "agentradez", "version": "1.0.0"},
        }
        try:
            self._rpc("initialize", params)
        except RobinhoodError:
            self._rpc("initialize", {})
        try:
            self._post(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                retry=True,
            )
        except RobinhoodError:
            logger.debug("Robinhood MCP initialize notification was rejected.")
        self._initialized = True

    def list_tools(self) -> list[dict]:
        self.initialize()
        tools: list[dict] = []
        cursor = None
        while True:
            params: dict = {}
            if cursor:
                params["cursor"] = cursor
            result = self._rpc("tools/list", params)
            rows = result.get("tools") if isinstance(result, dict) else None
            if isinstance(rows, list):
                tools.extend(row for row in rows if isinstance(row, dict))
            cursor = result.get("nextCursor") if isinstance(result, dict) else None
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return extract_tool_result(result)


def as_list(value: Any, *keys: str) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict):
                nested = as_list(inner, *keys)
                if nested:
                    return nested
    return []


def normalize_accounts(payload: Any) -> list[dict]:
    accounts = []
    for row in as_list(payload, "accounts", "results", "data"):
        if not isinstance(row, dict):
            continue
        account_number = str(
            row.get("account_number")
            or row.get("accountNumber")
            or row.get("id")
            or ""
        ).strip()
        if not account_number:
            continue
        nickname = str(row.get("nickname") or row.get("name") or "").strip()
        agentic = bool(row.get("agentic_allowed")) or "agentic" in nickname.lower()
        accounts.append(
            {
                "account_number": account_number,
                "nickname": nickname,
                "type": str(row.get("type") or row.get("brokerage_account_type") or ""),
                "state": str(row.get("state") or ""),
                "agentic_allowed": agentic,
                "option_level": str(row.get("option_level") or ""),
                "is_default": bool(row.get("is_default")),
            }
        )
    return accounts


def pick_agentic_account(accounts: list[dict]) -> dict | None:
    agentic = [row for row in accounts if row.get("agentic_allowed")]
    if len(agentic) == 1:
        return agentic[0]
    if len(agentic) > 1:
        return None
    return None


def connection_tokens(connection) -> dict:
    return decrypt_credentials(connection.encrypted_credentials)


def persist_tokens(connection, tokens: dict) -> None:
    current = decrypt_credentials(connection.encrypted_credentials)
    current.update(tokens)
    connection.encrypted_credentials = encrypt_credentials(current)
    connection.save(update_fields=["encrypted_credentials", "updated_at"])


def mcp_client_for(connection) -> RobinhoodMcpClient:
    tokens = connection_tokens(connection)
    access = tokens.get("access_token")
    if not access:
        raise RobinhoodError("Robinhood is not connected with OAuth.")

    def on_refresh() -> str:
        refreshed = refresh_access_token(connection_tokens(connection))
        persist_tokens(connection, refreshed)
        return refreshed["access_token"]

    if tokens_expired(tokens):
        access = on_refresh()
    return RobinhoodMcpClient(access, on_refresh=on_refresh)


def list_account_summaries_for(connection) -> list[dict]:
    client = mcp_client_for(connection)
    return normalize_accounts(client.call_tool("get_accounts"))


def get_account_for(connection, account_number: str) -> dict | None:
    account_number = (account_number or "").strip()
    if not account_number:
        return None
    accounts = list_account_summaries_for(connection)
    match = next(
        (row for row in accounts if row.get("account_number") == account_number),
        None,
    )
    if match is None:
        return None
    client = mcp_client_for(connection)
    try:
        payload = client.call_tool("get_portfolio", {"account_number": account_number})
        match["equity"] = portfolio_equity(payload)
        match["cash"] = _decimal_from(payload, "cash")
        match["buying_power"] = portfolio_buying_power(payload)
    except RobinhoodError:
        match["equity"] = None
        match["cash"] = None
        match["buying_power"] = None
    return match


def list_accounts_for(connection) -> list[dict]:
    client = mcp_client_for(connection)
    accounts = normalize_accounts(client.call_tool("get_accounts"))
    for account in accounts:
        try:
            payload = client.call_tool(
                "get_portfolio", {"account_number": account["account_number"]}
            )
            account["equity"] = portfolio_equity(payload)
            account["cash"] = _decimal_from(payload, "cash")
            account["buying_power"] = portfolio_buying_power(payload)
        except RobinhoodError:
            account["equity"] = None
            account["cash"] = None
            account["buying_power"] = None
    return accounts


def _decimal_from(payload: Any, *keys: str) -> Decimal | None:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                try:
                    return Decimal(str(payload[key]))
                except Exception:
                    continue
        for value in payload.values():
            found = _decimal_from(value, *keys)
            if found is not None:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _decimal_from(item, *keys)
            if found is not None:
                return found
    return None


def _first_id(payload: Any, *keys: str) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        for value in payload.values():
            found = _first_id(value, *keys)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _first_id(item, *keys)
            if found:
                return found
    return ""


def _strike_lookup_values(strike: Decimal) -> list[str]:
    value = Decimal(str(strike))
    candidates = [f"{value:.4f}", f"{value:.2f}", format(value.normalize(), "f")]
    if value == value.to_integral_value():
        candidates.append(str(int(value)))
    seen: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.append(item)
    return seen


def find_option_instrument(
    client: RobinhoodMcpClient,
    ticker: str,
    option_type: str,
    strike: Decimal,
    expiration,
) -> str:
    expiration_text = str(expiration)[:10]
    attempts = []
    for strike_text in _strike_lookup_values(strike):
        base = {
            "chain_symbol": ticker.upper(),
            "expiration_dates": expiration_text,
            "strike_price": strike_text,
            "type": option_type.lower(),
        }
        attempts.append({**base, "state": "active", "tradability": "tradable"})
        attempts.append(base)
        attempts.append({**base, "state": "inactive"})
        attempts.append({**base, "state": "expired"})
    seen: set[tuple] = set()
    for arguments in attempts:
        key = tuple(sorted(arguments.items()))
        if key in seen:
            continue
        seen.add(key)
        try:
            payload = client.call_tool("get_option_instruments", arguments)
        except RobinhoodError:
            continue
        rows = as_list(payload, "instruments", "results", "data")
        if not rows and isinstance(payload, dict):
            rows = [payload]
        instrument_id = _first_id(
            rows[0] if rows else payload, "id", "instrument_id", "option_id"
        )
        if instrument_id:
            return instrument_id
    raise RobinhoodError(
        f"No Robinhood option instrument for {ticker} {option_type} "
        f"{strike} {expiration}."
    )


def option_quote_price(client: RobinhoodMcpClient, instrument_id: str) -> Decimal:
    market = option_quote_market(client, instrument_id)
    if market["mark"] is None:
        raise RobinhoodError("Robinhood did not return an option quote.")
    return market["mark"]


def option_quote_market(client: RobinhoodMcpClient, instrument_id: str) -> dict:
    payload = client.call_tool("get_option_quotes", {"instrument_ids": [instrument_id]})
    row = payload
    rows = as_list(payload, "quotes", "results", "data")
    if rows and isinstance(rows[0], dict):
        row = rows[0]
    mark = _direct_decimal(
        row,
        "adjusted_mark_price",
        "mark_price",
        "last_trade_price",
        "price",
    )
    if mark is None:
        mark = _decimal_from(
            payload,
            "adjusted_mark_price",
            "mark_price",
            "last_trade_price",
            "ask_price",
            "bid_price",
            "price",
        )
    return {
        "mark": mark,
        "bid": _direct_decimal(row, "bid_price", "bid"),
        "ask": _direct_decimal(row, "ask_price", "ask"),
        "instrument_id": instrument_id,
    }


def _direct_decimal(payload: Any, *keys: str) -> Decimal | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return Decimal(str(value))
        except Exception:
            continue
    return None


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _execution_fill(payload: Any) -> tuple[Decimal, Decimal | None]:
    total_qty = Decimal("0")
    total_notional = Decimal("0")
    for exe in as_list(payload, "executions"):
        if not isinstance(exe, dict):
            continue
        qty = _direct_decimal(exe, "quantity", "filled_quantity", "processed_quantity")
        price = _direct_decimal(exe, "price", "average_price", "premium")
        if qty and qty > 0:
            total_qty += qty
            if price and price > 0:
                total_notional += qty * price
    avg = (total_notional / total_qty) if total_qty > 0 and total_notional > 0 else None
    return total_qty, avg


def _map_order_status(status: str) -> str:
    value = (status or "").lower().replace(" ", "_")
    if value in {"filled", "complete", "completed", "executed"}:
        return "filled"
    if value in {"partial", "partially_filled"}:
        return "partial"
    if value in {"cancelled", "canceled"}:
        return "cancelled"
    if value in {"rejected", "failed"}:
        return "rejected"
    return "submitted"


def _order_fill_fields(payload: Any, fallback_qty: int, fallback_price: Decimal) -> dict:
    order_id = _first_id(payload, "id", "order_id", "option_order_id") or f"rh-{uuid4().hex[:16]}"
    status = _map_order_status(str(_first_id(payload, "state", "status") or "submitted"))
    filled_qty = _direct_decimal(
        payload,
        "processed_quantity",
        "filled_quantity",
        "cumulative_quantity",
    )
    exe_qty, exe_price = _execution_fill(payload)
    if (filled_qty is None or filled_qty <= 0) and exe_qty > 0:
        filled_qty = exe_qty
    filled_price = _direct_decimal(
        payload, "average_price", "filled_avg_price", "price", "premium"
    )
    if (filled_price is None or filled_price <= 0) and exe_price:
        filled_price = exe_price
    if status in {"filled", "partial"}:
        if filled_qty is None or filled_qty <= 0:
            filled_qty = _direct_decimal(payload, "quantity")
        quantity = int(filled_qty) if filled_qty and filled_qty > 0 else fallback_qty
        mapped = "filled" if status == "filled" else "partial"
        price = filled_price if filled_price and filled_price > 0 else fallback_price
    elif status == "cancelled":
        quantity = int(filled_qty) if filled_qty and filled_qty > 0 else 0
        mapped = "cancelled"
        price = filled_price if filled_price and filled_price > 0 else fallback_price
    elif status == "rejected":
        quantity = 0
        mapped = "rejected"
        price = fallback_price
    else:
        quantity = int(filled_qty) if filled_qty and filled_qty > 0 else 0
        mapped = "submitted"
        price = filled_price if filled_price and filled_price > 0 else fallback_price
    return {
        "broker_order_id": order_id,
        "status": mapped,
        "filled_quantity": quantity,
        "filled_avg_price": price,
    }


def option_order_fill(payload: Any, fallback_qty: int, fallback_price: Decimal) -> dict:
    return _order_fill_fields(payload, fallback_qty, fallback_price)


def option_orders(payload: Any) -> list[dict]:
    rows = as_list(payload, "orders", "results", "data")
    if not rows and isinstance(payload, dict):
        if payload.get("id") or payload.get("order_id") or payload.get("option_order_id"):
            return [payload]
        nested = as_list(payload, "option_orders")
        if nested:
            return [row for row in nested if isinstance(row, dict)]
    return [row for row in rows if isinstance(row, dict)]


def _contract_from_payload(payload: Any) -> dict:
    ticker = str(
        _first_id(payload, "chain_symbol", "symbol", "ticker", "underlying_symbol") or ""
    ).upper()
    option_type = str(
        _first_id(payload, "option_type", "type", "put_call") or ""
    ).lower()
    if option_type not in {"call", "put"}:
        option_type = ""
    strike = _direct_decimal(payload, "strike_price", "strike")
    raw_exp = None
    if isinstance(payload, dict):
        raw_exp = payload.get("expiration_date") or payload.get("expiration")
    expiration = _as_date(raw_exp) or _as_date(
        _first_id(payload, "expiration_date", "expiration")
    )
    side = str(_first_id(payload, "side") or "").lower()
    position_effect = str(_first_id(payload, "position_effect") or "").lower()
    ordered_qty = _direct_decimal(payload, "quantity", "open_quantity", "units")
    return {
        "ticker": ticker,
        "option_type": option_type,
        "strike": strike,
        "expiration": expiration,
        "side": side,
        "position_effect": position_effect,
        "quantity": int(ordered_qty) if ordered_qty and ordered_qty > 0 else 0,
    }


def parse_option_order(payload: Any, fallback_qty: int = 1, fallback_price: Decimal = Decimal("0")) -> dict | None:
    if not isinstance(payload, dict):
        return None
    fields = _order_fill_fields(payload, fallback_qty, fallback_price)
    contract = _contract_from_payload(payload)
    for leg in as_list(payload, "legs"):
        if not isinstance(leg, dict):
            continue
        leg_contract = _contract_from_payload(leg)
        for key, value in leg_contract.items():
            if value not in (None, "", 0) and not contract.get(key):
                contract[key] = value
        break
    quantity = contract["quantity"] or fallback_qty or fields["filled_quantity"] or 1
    return {
        **fields,
        **contract,
        "quantity": quantity,
    }


def parse_option_position(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    contract = _contract_from_payload(payload)
    if payload.get("option") and isinstance(payload["option"], dict):
        nested = _contract_from_payload(payload["option"])
        for key, value in nested.items():
            if value not in (None, "", 0) and not contract.get(key):
                contract[key] = value
    quantity = contract["quantity"]
    if quantity < 1:
        qty = _direct_decimal(payload, "quantity", "open_quantity", "units")
        quantity = int(qty) if qty and qty > 0 else 0
    if quantity < 1 or not contract["ticker"]:
        return None
    price = _direct_decimal(
        payload,
        "average_price",
        "average_open_price",
        "avg_price",
        "price",
        "mark_price",
    ) or Decimal("0")
    current = _direct_decimal(
        payload, "mark_price", "adjusted_mark_price", "current_price", "last_trade_price"
    )
    bid = _direct_decimal(payload, "bid_price", "bid")
    ask = _direct_decimal(payload, "ask_price", "ask")
    option_id = ""
    option_raw = payload.get("option")
    if isinstance(option_raw, dict):
        option_id = str(
            option_raw.get("id")
            or option_raw.get("option_id")
            or option_raw.get("instrument_id")
            or ""
        )
    elif isinstance(option_raw, str) and option_raw:
        option_id = option_raw.rstrip("/").rsplit("/", 1)[-1]
    option_id = option_id or str(
        payload.get("option_id") or payload.get("instrument_id") or ""
    )
    return {
        "ticker": contract["ticker"],
        "option_type": contract["option_type"] or "call",
        "strike": contract["strike"] or Decimal("0"),
        "expiration": contract["expiration"],
        "quantity": quantity,
        "average_price": price,
        "current_price": current,
        "bid": bid,
        "ask": ask,
        "option_id": option_id,
        "side": contract["side"],
        "position_effect": "open",
        "status": "filled",
        "filled_quantity": quantity,
        "filled_avg_price": price,
        "broker_order_id": "",
    }


def contracts_match(row: dict, ticker: str, option_type: str, strike, expiration) -> bool:
    if str(row.get("ticker") or "").upper() != str(ticker or "").upper():
        return False
    row_type = str(row.get("option_type") or "").lower()
    if row_type and row_type != str(option_type or "").lower():
        return False
    if row.get("strike") is not None and strike is not None:
        if Decimal(str(row["strike"])) != Decimal(str(strike)):
            return False
    row_exp = row.get("expiration")
    if row_exp and expiration and str(row_exp)[:10] != str(expiration)[:10]:
        return False
    return True


def _match_option_order(payload: Any, order_id: str) -> dict | None:
    for row in option_orders(payload):
        rid = str(row.get("id") or row.get("order_id") or row.get("option_order_id") or "")
        if rid == order_id:
            return row
    return None


def fetch_option_order(
    client: RobinhoodMcpClient,
    account_number: str,
    order_id: str,
) -> dict | None:
    order_id = (order_id or "").strip()
    if not order_id:
        return None
    attempts = [
        {"account_number": account_number, "ids": [order_id]},
        {"account_number": account_number, "id": order_id},
        {"account_number": account_number},
    ]
    for arguments in attempts:
        try:
            payload = client.call_tool("get_option_orders", arguments)
        except RobinhoodError:
            continue
        row = _match_option_order(payload, order_id)
        if row is not None:
            return row
    return None


def place_option_order(
    client: RobinhoodMcpClient,
    account_number: str,
    instrument_id: str,
    quantity: int,
    limit_price: Decimal,
    side: str,
    position_effect: str,
) -> dict:
    arguments = {
        "account_number": account_number,
        "quantity": str(quantity),
        "type": "limit",
        "price": str(limit_price),
        "legs": [
            {
                "option_id": instrument_id,
                "side": side,
                "position_effect": position_effect,
                "ratio_quantity": 1,
            }
        ],
    }
    payload = client.call_tool("place_option_order", arguments)
    return _order_fill_fields(payload, quantity, limit_price)


def portfolio_equity(payload: Any) -> Decimal:
    value = _decimal_from(
        payload,
        "total_value",
        "equity",
        "portfolio_value",
        "market_value",
        "buying_power",
        "cash",
    )
    if value is None:
        raise RobinhoodError("Robinhood portfolio did not include equity.")
    return value


def portfolio_buying_power(payload: Any) -> Decimal | None:
    if isinstance(payload, dict):
        buying = payload.get("buying_power")
        if isinstance(buying, dict):
            return _decimal_from(buying, "buying_power", "unleveraged_buying_power")
    return _decimal_from(payload, "buying_power")


def portfolio_spendable(payload: Any) -> Decimal | None:
    """Cash available to pay option premium; falls back to buying power."""
    cash = _decimal_from(payload, "cash")
    buying_power = portfolio_buying_power(payload)
    values = [value for value in (cash, buying_power) if value is not None]
    if not values:
        return None
    return min(values)


def option_positions(payload: Any) -> list[dict]:
    rows = []
    for row in as_list(payload, "positions", "results", "data"):
        if not isinstance(row, dict):
            continue
        quantity = _decimal_from(row, "quantity", "open_quantity", "units")
        if not quantity or quantity <= 0:
            continue
        rows.append(row)
    return rows


AGENT_TOOL_CATALOG = [
    {"name": "get_accounts", "category": "Account", "description": "List brokerage accounts on this Robinhood login."},
    {"name": "get_portfolio", "category": "Account", "description": "Balances, equity, cash, and buying power for an account."},
    {"name": "get_realized_pnl", "category": "Account", "description": "Realized profit and loss for an account."},
    {"name": "get_pnl_trade_history", "category": "Account", "description": "Trade history used to compute P&L."},
    {"name": "search", "category": "Account", "description": "Search symbols, instruments, and related entities."},
    {"name": "get_watchlists", "category": "Watchlists", "description": "List watchlists."},
    {"name": "get_watchlist_items", "category": "Watchlists", "description": "List symbols on a watchlist."},
    {"name": "get_option_watchlist", "category": "Watchlists", "description": "List option contracts on a watchlist."},
    {"name": "get_popular_watchlists", "category": "Watchlists", "description": "Popular public watchlists."},
    {"name": "create_watchlist", "category": "Watchlists", "description": "Create a watchlist."},
    {"name": "update_watchlist", "category": "Watchlists", "description": "Rename or update a watchlist."},
    {"name": "follow_watchlist", "category": "Watchlists", "description": "Follow a public watchlist."},
    {"name": "unfollow_watchlist", "category": "Watchlists", "description": "Unfollow a watchlist."},
    {"name": "add_to_watchlist", "category": "Watchlists", "description": "Add an equity symbol to a watchlist."},
    {"name": "remove_from_watchlist", "category": "Watchlists", "description": "Remove an equity symbol from a watchlist."},
    {"name": "add_option_to_watchlist", "category": "Watchlists", "description": "Add an option contract to a watchlist."},
    {"name": "remove_option_from_watchlist", "category": "Watchlists", "description": "Remove an option contract from a watchlist."},
    {"name": "get_equity_historicals", "category": "Market data", "description": "Historical equity bars."},
    {"name": "get_equity_fundamentals", "category": "Market data", "description": "Fundamental data for a stock."},
    {"name": "get_financials", "category": "Market data", "description": "Financial statements for a stock."},
    {"name": "get_equity_price_book", "category": "Market data", "description": "Equity order book / price levels."},
    {"name": "get_equity_technical_indicators", "category": "Market data", "description": "Technical indicators for a stock."},
    {"name": "get_earnings_results", "category": "Market data", "description": "Past earnings results."},
    {"name": "get_earnings_calendar", "category": "Market data", "description": "Upcoming earnings dates."},
    {"name": "get_indexes", "category": "Market data", "description": "Index metadata."},
    {"name": "get_index_quotes", "category": "Market data", "description": "Live index quotes."},
    {"name": "get_equity_positions", "category": "Equities", "description": "Open stock positions in an account."},
    {"name": "get_equity_tax_lots", "category": "Equities", "description": "Tax lots for equity positions."},
    {"name": "get_equity_quotes", "category": "Equities", "description": "Live stock quotes."},
    {"name": "get_equity_orders", "category": "Equities", "description": "Stock order history."},
    {"name": "get_equity_tradability", "category": "Equities", "description": "Whether a stock can be traded in the account."},
    {"name": "review_equity_order", "category": "Equities", "description": "Preview a stock order before placing it."},
    {"name": "place_equity_order", "category": "Equities", "description": "Place a stock order. Writes only to an Agentic account."},
    {"name": "cancel_equity_order", "category": "Equities", "description": "Cancel an open stock order."},
    {"name": "get_option_level_upgrade_info", "category": "Options", "description": "Option approval level and upgrade info."},
    {"name": "get_option_historicals", "category": "Options", "description": "Historical option bars."},
    {"name": "get_option_chains", "category": "Options", "description": "Option chains for an underlying."},
    {"name": "get_option_instruments", "category": "Options", "description": "Option contract details."},
    {"name": "get_option_quotes", "category": "Options", "description": "Live option quotes."},
    {"name": "get_option_positions", "category": "Options", "description": "Open option positions in an account."},
    {"name": "get_option_orders", "category": "Options", "description": "Option order history."},
    {"name": "review_option_order", "category": "Options", "description": "Preview an option order before placing it."},
    {"name": "place_option_order", "category": "Options", "description": "Place an option order. Writes only to an Agentic account."},
    {"name": "cancel_option_order", "category": "Options", "description": "Cancel an open option order."},
    {"name": "get_scans", "category": "Scanners", "description": "Saved scanners."},
    {"name": "get_scanner_filter_specs", "category": "Scanners", "description": "Available scanner filter definitions."},
    {"name": "create_scan", "category": "Scanners", "description": "Create a scanner."},
    {"name": "run_scan", "category": "Scanners", "description": "Run a scanner and return matches."},
    {"name": "update_scan_filters", "category": "Scanners", "description": "Update scanner filters."},
    {"name": "update_scan_config", "category": "Scanners", "description": "Update scanner configuration."},
]


def list_agent_tools_for(connection) -> list[dict]:
    catalog = {row["name"]: row for row in AGENT_TOOL_CATALOG}
    try:
        live = mcp_client_for(connection).list_tools()
    except RobinhoodError:
        live = []
    tools = []
    seen: set[str] = set()
    for item in live:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        seen.add(name)
        known = catalog.get(name, {})
        tools.append(
            {
                "name": name,
                "description": str(item.get("description") or known.get("description") or ""),
                "category": known.get("category") or "Other",
                "available": True,
            }
        )
    if not tools:
        return [{**row, "available": False} for row in AGENT_TOOL_CATALOG]
    for row in AGENT_TOOL_CATALOG:
        if row["name"] not in seen:
            tools.append({**row, "available": False})
    return tools
