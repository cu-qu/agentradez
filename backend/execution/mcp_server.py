"""Streamable HTTP MCP endpoint — per-user auth, tenant-isolated tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from execution.services.ingest import IngestError, cancel_signal, ingest_signal, set_levels
from execution.services.mcp_auth import McpAuthContext, McpAuthError, assert_tool_allowed, authenticate_bearer
from execution.services.status import list_accounts_payload, status_payload

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "list_accounts",
        "description": (
            "List your connected brokerage accounts, buying power, and trading levels. "
            "Agentradez does not recommend or select trades; it only executes instructions "
            "your own agent submits."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "ingest_signal",
        "description": (
            "Submit a trade instruction from your agent: symbol, limit entry/exit rules, "
            "stops, targets, and size that you (or your agent) chose. Idempotent on ref_id "
            "per user. Agentradez will not generate, recommend, resize, or advise."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["ref_id", "account_slug", "symbol"],
            "properties": {
                "ref_id": {"type": "string"},
                "account_slug": {"type": "string"},
                "account_id": {"type": "integer"},
                "market": {"type": "string"},
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "option_type": {"type": "string"},
                "strike": {"type": "string"},
                "expiration": {"type": "string"},
                "entry_rule": {"type": "object"},
                "stop": {"type": "string"},
                "stop_loss_pct": {"type": "string"},
                "targets": {"type": "array"},
                "size": {"type": "integer"},
                "expiry": {"type": "string"},
                "time_exit_at": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "set_levels",
        "description": (
            "Update user-supplied stop, targets, entry_rule, or time_exit on an existing "
            "instruction. No advice or auto-sizing."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["ref_id"],
            "properties": {
                "ref_id": {"type": "string"},
                "stop": {"type": "string"},
                "stop_price": {"type": "string"},
                "targets": {"type": "array"},
                "entry_rule": {"type": "object"},
                "time_exit_at": {"type": "string"},
            },
        },
    },
    {
        "name": "cancel_signal",
        "description": "Cancel a pending or working instruction your agent previously submitted.",
        "inputSchema": {
            "type": "object",
            "required": ["ref_id"],
            "properties": {"ref_id": {"type": "string"}, "reason": {"type": "string"}},
        },
    },
    {
        "name": "status",
        "description": (
            "Your open instructions, positions, working limit orders, last ticks, and "
            "execution journal (fills/exits only)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"account_slug": {"type": "string"}},
        },
    },
]


def _auth_context(request: HttpRequest) -> McpAuthContext:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise McpAuthError("Missing bearer token.")
    return authenticate_bearer(header.split(" ", 1)[1].strip())


def _tool_result(data: Any) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(data, default=str)}],
        "structuredContent": data,
    }


def _call_tool(ctx: McpAuthContext, name: str, arguments: dict) -> dict:
    assert_tool_allowed(ctx, name)
    arguments = arguments or {}
    if name == "list_accounts":
        return _tool_result(list_accounts_payload(ctx.user))
    if name == "ingest_signal":
        return _tool_result(ingest_signal(ctx.user, arguments))
    if name == "set_levels":
        return _tool_result(set_levels(ctx.user, arguments))
    if name == "cancel_signal":
        return _tool_result(cancel_signal(ctx.user, arguments))
    if name == "status":
        return _tool_result(status_payload(ctx.user, arguments.get("account_slug")))
    raise ValueError(f"Unknown tool: {name}")


def _rpc_error(rid, code: int, message: str) -> JsonResponse:
    return JsonResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def oauth_authorization_server_metadata(request: HttpRequest) -> JsonResponse:
    base = getattr(settings, "PUBLIC_API_URL", request.build_absolute_uri("/")).rstrip("/")
    return JsonResponse(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/api/execution/oauth/authorize/",
            "token_endpoint": f"{base}/api/execution/oauth/token/",
            "registration_endpoint": f"{base}/api/execution/oauth/clients/",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
        }
    )


@method_decorator(csrf_exempt, name="dispatch")
class ExecutionMcpView(View):
    """POST JSON-RPC 2.0 (initialize, tools/list, tools/call)."""

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            ctx = _auth_context(request)
        except McpAuthError as exc:
            return JsonResponse({"error": str(exc)}, status=401)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        method = payload.get("method")
        rid = payload.get("id")
        params = payload.get("params") or {}

        if method == "initialize":
            return JsonResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agentradez-execution", "version": "2.0.0"},
                    },
                }
            )

        if method == "notifications/initialized":
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": {}})

        if method == "tools/list":
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})

        if method == "tools/call":
            name = params.get("name")
            try:
                result = _call_tool(ctx, name, params.get("arguments") or {})
            except McpAuthError as exc:
                return _rpc_error(rid, -32000, str(exc))
            except IngestError as exc:
                return _rpc_error(rid, -32000, f"{exc.code}: {exc}")
            except ValueError as exc:
                return _rpc_error(rid, -32601, str(exc))
            except Exception as exc:
                logger.exception("mcp tools/call failed tool=%s user=%s", name, ctx.user_id)
                return _rpc_error(rid, -32000, str(exc))
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": result})

        if method == "ping":
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": {}})

        return _rpc_error(rid, -32601, f"Method not found: {method}")

    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            _auth_context(request)
        except McpAuthError as exc:
            return JsonResponse({"error": str(exc)}, status=401)
        return JsonResponse({"name": "agentradez-execution", "tools": [t["name"] for t in TOOLS]})
