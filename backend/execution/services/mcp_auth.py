"""Per-user MCP authentication (PAT + OAuth access tokens)."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from accounts.models import User
from execution.models import ExecutionAgentToken, ExecutionMcpAccessGrant

SCOPE_READ = "execution:read"
SCOPE_TRADE = "execution:trade"
DEFAULT_SCOPES = [SCOPE_READ, SCOPE_TRADE]
READ_TOOLS = frozenset({"list_accounts", "status"})
TRADE_TOOLS = frozenset({"ingest_signal", "set_levels", "cancel_signal"})


class McpAuthError(Exception):
    pass


@dataclass
class McpAuthContext:
    user: User
    token: ExecutionAgentToken | None
    grant: ExecutionMcpAccessGrant | None
    scopes: list[str]


def _hash_token(raw: str) -> str:
    pepper = settings.SECRET_KEY
    return hashlib.sha256(f"{pepper}:{raw}".encode("utf-8")).hexdigest()


def generate_pat(user: User, label: str, scopes: list[str] | None = None) -> tuple[str, ExecutionAgentToken]:
    raw = f"agz_pat_{secrets.token_urlsafe(32)}"
    prefix = raw[:16]
    scopes = scopes or DEFAULT_SCOPES
    row = ExecutionAgentToken.objects.create(
        user=user,
        label=label,
        token_prefix=prefix,
        token_hash=_hash_token(raw),
        scopes=scopes,
    )
    return raw, row


def authenticate_bearer(raw_token: str) -> McpAuthContext:
    raw_token = (raw_token or "").strip()
    if not raw_token:
        raise McpAuthError("Missing bearer token.")

    admin = (
        (getattr(settings, "EXECUTION_MCP_ADMIN_BEARER", None) or "").strip()
        or (getattr(settings, "EXECUTION_MCP_BEARER_TOKEN", None) or "").strip()
    )
    if admin and secrets.compare_digest(raw_token, admin):
        staff = User.objects.filter(is_superuser=True).order_by("id").first()
        if staff is None:
            raise McpAuthError("No admin user for ops token.")
        return McpAuthContext(
            user=staff,
            token=None,
            grant=None,
            scopes=DEFAULT_SCOPES,
        )

    if raw_token.startswith("agz_pat_"):
        prefix = raw_token[:16]
        token_hash = _hash_token(raw_token)
        row = (
            ExecutionAgentToken.objects.select_related("user")
            .filter(token_prefix=prefix, token_hash=token_hash, revoked_at__isnull=True)
            .first()
        )
        if row is None:
            raise McpAuthError("Invalid or revoked token.")
        ExecutionAgentToken.objects.filter(pk=row.pk).update(last_used_at=timezone.now())
        return McpAuthContext(user=row.user, token=row, grant=None, scopes=list(row.scopes or []))

    if raw_token.startswith("agz_oauth_"):
        token_hash = _hash_token(raw_token)
        grant = (
            ExecutionMcpAccessGrant.objects.select_related("user", "client")
            .filter(access_token_hash=token_hash, revoked_at__isnull=True)
            .first()
        )
        if grant is None:
            raise McpAuthError("Invalid or revoked OAuth token.")
        if grant.expires_at and timezone.now() >= grant.expires_at:
            raise McpAuthError("OAuth token expired.")
        ExecutionMcpAccessGrant.objects.filter(pk=grant.pk).update(last_used_at=timezone.now())
        return McpAuthContext(
            user=grant.user,
            token=None,
            grant=grant,
            scopes=list(grant.scopes or []),
        )

    raise McpAuthError("Unrecognized token format.")


def assert_tool_allowed(ctx: McpAuthContext, tool_name: str) -> None:
    if tool_name in READ_TOOLS:
        if SCOPE_READ in ctx.scopes or SCOPE_TRADE in ctx.scopes:
            return
        raise McpAuthError("Token lacks execution:read scope.")
    if tool_name in TRADE_TOOLS:
        if SCOPE_TRADE in ctx.scopes:
            return
        raise McpAuthError("Token lacks execution:trade scope.")
    raise McpAuthError(f"Unknown tool: {tool_name}")
