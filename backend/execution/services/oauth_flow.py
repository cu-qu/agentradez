"""OAuth 2.1 authorization code + PKCE for MCP agents."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from execution.models import ExecutionMcpAccessGrant, ExecutionOAuthClient, ExecutionOAuthCode
from execution.services.mcp_auth import DEFAULT_SCOPES, _hash_token


class OAuthError(Exception):
    pass


def register_client(user: User, name: str, redirect_uris: list[str]) -> tuple[ExecutionOAuthClient, str]:
    client_id = f"agz_{secrets.token_urlsafe(16)}"
    client_secret = secrets.token_urlsafe(32)
    row = ExecutionOAuthClient.objects.create(
        user=user,
        name=name,
        client_id=client_id,
        client_secret_hash=_hash_token(client_secret),
        redirect_uris=redirect_uris,
    )
    return row, client_secret


def issue_authorization_code(
    user: User,
    client: ExecutionOAuthClient,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str,
    code_challenge_method: str = "S256",
) -> str:
    if redirect_uri not in (client.redirect_uris or []):
        raise OAuthError("redirect_uri mismatch")
    code = secrets.token_urlsafe(32)
    ExecutionOAuthCode.objects.create(
        code=code,
        client=client,
        user=user,
        scopes=scopes or DEFAULT_SCOPES,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return code


def _verify_pkce(code_challenge: str, code_verifier: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return secrets.compare_digest(expected, code_challenge)


def exchange_code(
    client: ExecutionOAuthClient,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> tuple[str, ExecutionMcpAccessGrant]:
    if _hash_token(client_secret) != client.client_secret_hash:
        raise OAuthError("invalid_client")
    row = ExecutionOAuthCode.objects.select_related("user").filter(code=code, client=client).first()
    if row is None or not row.is_valid():
        raise OAuthError("invalid_grant")
    if row.redirect_uri != redirect_uri:
        raise OAuthError("redirect_uri mismatch")
    if not _verify_pkce(row.code_challenge, code_verifier):
        raise OAuthError("invalid code_verifier")
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])

    access_raw = f"agz_oauth_{secrets.token_urlsafe(32)}"
    grant = ExecutionMcpAccessGrant.objects.create(
        user=row.user,
        client=client,
        access_token_hash=_hash_token(access_raw),
        scopes=row.scopes,
        expires_at=timezone.now() + timedelta(days=30),
    )
    return access_raw, grant
