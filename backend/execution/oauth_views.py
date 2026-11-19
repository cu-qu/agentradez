from urllib.parse import urlencode

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import HasTradingAccess
from execution.models import ExecutionOAuthClient
from execution.services.oauth_flow import OAuthError, exchange_code, issue_authorization_code, register_client

TRADING = [IsAuthenticated, HasTradingAccess]


class OAuthClientCreateView(APIView):
    permission_classes = TRADING

    @extend_schema(tags=["Execution OAuth"], summary="Register MCP OAuth client")
    def post(self, request):
        name = (request.data.get("name") or "MCP Agent").strip()
        redirect_uris = request.data.get("redirect_uris") or []
        if not redirect_uris:
            return Response({"redirect_uris": "Required"}, status=status.HTTP_400_BAD_REQUEST)
        client, secret = register_client(request.user, name, redirect_uris)
        return Response(
            {
                "client_id": client.client_id,
                "client_secret": secret,
                "redirect_uris": client.redirect_uris,
            },
            status=status.HTTP_201_CREATED,
        )


class OAuthAuthorizeView(APIView):
    """Return consent metadata for the web consent screen."""

    permission_classes = TRADING

    def get(self, request):
        client_id = request.query_params.get("client_id")
        redirect_uri = request.query_params.get("redirect_uri")
        scope = request.query_params.get("scope", "execution:read execution:trade")
        code_challenge = request.query_params.get("code_challenge")
        client = get_object_or_404(ExecutionOAuthClient, client_id=client_id, user=request.user, revoked_at__isnull=True)
        return Response(
            {
                "client_name": client.name,
                "scopes": scope.split(),
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
            }
        )


class OAuthApproveView(APIView):
    permission_classes = TRADING

    def post(self, request):
        client_id = request.data.get("client_id")
        redirect_uri = request.data.get("redirect_uri")
        code_challenge = request.data.get("code_challenge")
        scopes = request.data.get("scopes") or ["execution:read", "execution:trade"]
        client = get_object_or_404(ExecutionOAuthClient, client_id=client_id, user=request.user, revoked_at__isnull=True)
        try:
            code = issue_authorization_code(
                request.user, client, redirect_uri, scopes, code_challenge
            )
        except OAuthError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        redirect = f"{redirect_uri}?{urlencode({'code': code})}"
        return Response({"redirect_to": redirect})


class OAuthTokenView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        grant_type = request.data.get("grant_type")
        if grant_type != "authorization_code":
            return Response({"error": "unsupported_grant_type"}, status=status.HTTP_400_BAD_REQUEST)
        client_id = request.data.get("client_id")
        client_secret = request.data.get("client_secret")
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")
        code_verifier = request.data.get("code_verifier")
        client = ExecutionOAuthClient.objects.filter(client_id=client_id, revoked_at__isnull=True).first()
        if client is None:
            return Response({"error": "invalid_client"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            access_token, grant = exchange_code(
                client, client_secret, code, redirect_uri, code_verifier
            )
        except OAuthError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 2592000,
                "scope": " ".join(grant.scopes or []),
            }
        )
