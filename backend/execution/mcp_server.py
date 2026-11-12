"""Streamable HTTP MCP endpoint for the execution harness."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from execution.services.ingest import IngestError, cancel_signal, ingest_signal, set_levels
from execution.services.status import list_accounts_payload, status_payload

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "list_accounts",
        "description": "Connected execution desk accounts with buying power and option level.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "ingest_signal",
        "description": "Idempotent harness signal ingest (ref_id unique).",
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
        "description": "Update stop, targets, entry_rule, or time_exit for a signal/position.",
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
        "description": "Cancel a pending or working harness signal.",
        "inputSchema": {
            "type": "object",
            "required": ["ref_id"],
            "properties": {"ref_id": {"type": "string"}, "reason": {"type": "string"}},
        },
    },
    {
        "name": "status",
        "description": "Open signals, positions, working orders, ticks, recent journal actions.",
        "inputSchema": {
            "type": "object",
            "properties": {"account_slug": {"type": "string"}},
        },
    },
]


def _mcp_bearer_token() -> str:
    return (getattr(settings, "EXECUTION_MCP_BEARER_TOKEN", None) or "").strip()


def _authorized(request: HttpRequest) -> bool:
    expected = _mcp_bearer_token()
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    return header.split(" ", 1)[1].strip() == expected


def _tool_result(data: Any) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(data, default=str)}],
        "structuredContent": data,
    }


def _call_tool(name: str, arguments: dict) -> dict:
    arguments = arguments or {}
    if name == "list_accounts":
        return _tool_result(list_accounts_payload())
    if name == "ingest_signal":
        return _tool_result(ingest_signal(arguments))
    if name == "set_levels":
        return _tool_result(set_levels(arguments))
    if name == "cancel_signal":
        return _tool_result(cancel_signal(arguments))
    if name == "status":
        return _tool_result(status_payload(arguments.get("account_slug")))
    raise ValueError(f"Unknown tool: {name}")


def _rpc_error(rid, code: int, message: str) -> JsonResponse:
    return JsonResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


@method_decorator(csrf_exempt, name="dispatch")
class ExecutionMcpView(View):
    """POST JSON-RPC 2.0 (initialize, tools/list, tools/call)."""

    def post(self, request: HttpRequest) -> JsonResponse:
        if not _authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

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
                        "serverInfo": {"name": "agentradez-execution", "version": "1.0.0"},
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
                result = _call_tool(name, params.get("arguments") or {})
            except IngestError as exc:
                return _rpc_error(rid, -32000, f"{exc.code}: {exc}")
            except ValueError as exc:
                return _rpc_error(rid, -32601, str(exc))
            except Exception as exc:
                logger.exception("mcp tools/call failed tool=%s", name)
                return _rpc_error(rid, -32000, str(exc))
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": result})

        if method == "ping":
            return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": {}})

        return _rpc_error(rid, -32601, f"Method not found: {method}")

    def get(self, request: HttpRequest) -> JsonResponse:
        if not _authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        return JsonResponse({"name": "agentradez-execution", "tools": [t["name"] for t in TOOLS]})
