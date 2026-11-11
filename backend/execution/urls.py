from django.urls import path

from execution.mcp_server import ExecutionMcpView, oauth_authorization_server_metadata
from execution.oauth_views import OAuthApproveView, OAuthAuthorizeView, OAuthClientCreateView, OAuthTokenView
from execution.views import (
    CoinbaseConnectView,
    ExecutionAccountDetailView,
    ExecutionAccountListCreateView,
    ExecutionAgentTokenListCreateView,
    ExecutionAgentTokenRevokeView,
    HarnessJournalListView,
    HarnessPositionListView,
    HarnessSignalListView,
    KalshiConnectView,
)

urlpatterns = [
    path("mcp/execution/", ExecutionMcpView.as_view(), name="execution-mcp"),
    path(
        "mcp/execution/.well-known/oauth-authorization-server",
        oauth_authorization_server_metadata,
        name="execution-oauth-metadata",
    ),
    path("execution/accounts/", ExecutionAccountListCreateView.as_view(), name="execution-accounts"),
    path(
        "execution/accounts/<slug:slug>/",
        ExecutionAccountDetailView.as_view(),
        name="execution-account-detail",
    ),
    path("execution/agent-tokens/", ExecutionAgentTokenListCreateView.as_view(), name="execution-agent-tokens"),
    path(
        "execution/agent-tokens/<int:pk>/revoke/",
        ExecutionAgentTokenRevokeView.as_view(),
        name="execution-agent-token-revoke",
    ),
    path("execution/connect/kalshi/", KalshiConnectView.as_view(), name="execution-connect-kalshi"),
    path("execution/connect/coinbase/", CoinbaseConnectView.as_view(), name="execution-connect-coinbase"),
    path("execution/signals/", HarnessSignalListView.as_view(), name="execution-signals"),
    path("execution/positions/", HarnessPositionListView.as_view(), name="execution-positions"),
    path("execution/journal/", HarnessJournalListView.as_view(), name="execution-journal"),
    path("execution/oauth/clients/", OAuthClientCreateView.as_view(), name="execution-oauth-clients"),
    path("execution/oauth/authorize/", OAuthAuthorizeView.as_view(), name="execution-oauth-authorize"),
    path("execution/oauth/approve/", OAuthApproveView.as_view(), name="execution-oauth-approve"),
    path("execution/oauth/token/", OAuthTokenView.as_view(), name="execution-oauth-token"),
]
