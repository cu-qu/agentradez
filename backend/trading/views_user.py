from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from billing.permissions import HasTradingAccess
from trading.models import (
    BrokerConnection,
    Decision,
    InvestmentTier,
    Notification,
    Position,
    Signal,
    Strategy,
    Trade,
    UserStrategyAssignment,
)
from trading.serializers import (
    AgentToolSerializer,
    AssignmentSerializer,
    BrokerAccountDetailSerializer,
    BrokerAccountSerializer,
    BrokerConnectSerializer,
    BrokerConnectionSerializer,
    BrokerSelectAccountSerializer,
    DecisionSerializer,
    InvestmentTierSerializer,
    NotificationSerializer,
    PositionSerializer,
    RobinhoodOAuthCompleteResponseSerializer,
    RobinhoodOAuthCompleteSerializer,
    RobinhoodOAuthStartSerializer,
    SignalSerializer,
    StrategySerializer,
    TradeSerializer,
    disconnect_user_brokers,
)
from trading.services.credentials import encrypt_credentials
from trading.services.performance import account_performance, personal_performance
from trading.services.robinhood import (
    RobinhoodError,
    exchange_code,
    get_account_for,
    list_accounts_for,
    list_agent_tools_for,
    oauth_redirect_uri,
    pick_agentic_account,
    pop_oauth_state,
    start_oauth,
)
from trading.services.strategy_access import strategies_visible_to, user_can_access_strategy

TRADING_ACCESS = [IsAuthenticated, HasTradingAccess]


class StrategyListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StrategySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Strategy.objects.none()
        return strategies_visible_to(self.request.user).prefetch_related(
            "x_sources", "watched_companies"
        )


StrategyListView = extend_schema(
    tags=["Strategies"],
    summary="List strategies",
    description="Returns active strategies this user is allowed to pick (public plus restricted grants).",
)(StrategyListView)


class StrategySignalListView(generics.ListAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = SignalSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Signal.objects.none()
        strategy = get_object_or_404(Strategy, pk=self.kwargs["pk"])
        allowed = user_can_access_strategy(self.request.user, strategy) or (
            UserStrategyAssignment.objects.filter(
                user=self.request.user, strategy=strategy, is_active=True
            ).exists()
        )
        if not allowed:
            raise PermissionDenied()
        return Signal.objects.filter(strategy=strategy).select_related(
            "strategy", "ingested_post", "research_event"
        )


StrategySignalListView = extend_schema(
    tags=["Strategies"],
    summary="Parsed signals for a strategy",
    description="Option trades parsed from this strategy's X posts (and any other stored signals).",
)(StrategySignalListView)


class InvestmentTierListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InvestmentTierSerializer
    queryset = InvestmentTier.objects.filter(is_active=True)


InvestmentTierListView = extend_schema(
    tags=["Tiers"],
    summary="List investment tiers",
    description=(
        "Each tier's max_risk_per_trade_pct sizes entries as a percent of equity. "
        "If that percent is below one options contract, the engine still buys 1 "
        "contract when the premium is affordable, then scales with the risk "
        "percent as the account grows."
    ),
)(InvestmentTierListView)


class AssignmentView(APIView):
    permission_classes = TRADING_ACCESS
    serializer_class = AssignmentSerializer

    def get_object(self, user):
        return (
            UserStrategyAssignment.objects.filter(user=user, is_active=True)
            .select_related("strategy", "investment_tier")
            .first()
        )

    @extend_schema(tags=["Assignment"], summary="Get my strategy and tier")
    def get(self, request):
        assignment = self.get_object(request.user)
        if not assignment:
            return Response({"detail": "No strategy selected."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AssignmentSerializer(assignment).data)

    @extend_schema(
        tags=["Assignment"],
        summary="Select strategy, tier, and brokerage account",
        description=(
            "Assigns one strategy and investment tier. Pass broker_account_id to bind "
            "that assignment to a single Robinhood Agentic account (and turn trading on there)."
        ),
        request=AssignmentSerializer,
        responses=AssignmentSerializer,
    )
    def put(self, request):
        serializer = AssignmentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(AssignmentSerializer(assignment).data)


class BrokerConnectionListCreateView(APIView):
    permission_classes = TRADING_ACCESS
    serializer_class = BrokerConnectionSerializer

    @extend_schema(tags=["Broker"], summary="List my brokerage connections")
    def get(self, request):
        qs = BrokerConnection.objects.filter(user=request.user)
        return Response(BrokerConnectionSerializer(qs, many=True).data)

    @extend_schema(
        tags=["Broker"],
        summary="Connect brokerage account",
        request=BrokerConnectSerializer,
        responses={201: BrokerConnectionSerializer},
    )
    def post(self, request):
        serializer = BrokerConnectSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        connection = serializer.save()
        return Response(
            BrokerConnectionSerializer(connection).data, status=status.HTTP_201_CREATED
        )


PASTE_CALLBACK_INSTRUCTION = (
    "Robinhood opens a localhost page that will not load. Copy the full URL "
    "from that tab's address bar and send it as callback_url to "
    "POST /api/broker-connections/robinhood/oauth/complete/."
)


def _finish_robinhood_oauth(code: str, state: str, expected_user=None):
    pending = pop_oauth_state(state)
    if expected_user is not None and int(pending["user_id"]) != int(expected_user.id):
        raise RobinhoodError(
            "This Robinhood login belongs to a different account. Start again."
        )
    tokens = exchange_code(code, pending)
    user = expected_user or User.objects.filter(pk=pending["user_id"]).first()
    if user is None:
        raise RobinhoodError("User no longer exists.")
    disconnect_user_brokers(user)
    connection = BrokerConnection.objects.create(
        user=user,
        broker="robinhood",
        is_paper=False,
        encrypted_credentials=encrypt_credentials(tokens),
        status=BrokerConnection.Status.CONNECTED,
        last_equity=Decimal("0.00"),
    )
    try:
        accounts = list_accounts_for(connection)
        selected = pick_agentic_account(accounts)
        if selected:
            connection.broker_account_id = selected["account_number"]
            connection.last_error = ""
            connection.save(update_fields=["broker_account_id", "last_error", "updated_at"])
            return "connected", connection
        if any(row.get("agentic_allowed") for row in accounts):
            connection.last_error = "Select which Agentic account to trade."
            connection.save(update_fields=["last_error", "updated_at"])
            return "needs_account", connection
        connection.last_error = (
            "No Agentic account yet. Finish Robinhood onboarding on desktop, "
            "then return here to select it."
        )
        connection.save(update_fields=["last_error", "updated_at"])
        return "needs_account", connection
    except RobinhoodError as exc:
        connection.last_error = str(exc)[:255]
        connection.status = BrokerConnection.Status.ERROR
        connection.save(update_fields=["last_error", "status", "updated_at"])
        raise


def _frontend_broker_redirect(status_name: str, message: str = "") -> str:
    query = {"robinhood": status_name}
    if message:
        query["message"] = message[:200]
    return f"{settings.FRONTEND_URL.rstrip('/')}/settings?{urlencode(query)}"


def _sync_connection_equity(connection, accounts: list[dict]) -> None:
    selected = next(
        (
            row
            for row in accounts
            if row.get("account_number") == connection.broker_account_id
            and row.get("equity") is not None
        ),
        None,
    )
    if selected is None:
        selected = next(
            (
                row
                for row in accounts
                if row.get("agentic_allowed") and row.get("equity") is not None
            ),
            None,
        )
    if selected is None:
        return
    connection.last_equity = selected["equity"]
    connection.last_synced_at = timezone.now()
    if connection.status == BrokerConnection.Status.ERROR:
        connection.status = BrokerConnection.Status.CONNECTED
        connection.last_error = ""
        connection.save(
            update_fields=[
                "last_equity",
                "last_synced_at",
                "status",
                "last_error",
                "updated_at",
            ]
        )
        return
    connection.save(update_fields=["last_equity", "last_synced_at", "updated_at"])


def _alpaca_account_snapshot(connection, account_number: str) -> dict | None:
    account_id = (connection.broker_account_id or "default").strip() or "default"
    requested = (account_number or "").strip() or "default"
    if requested not in ("default", account_id, str(connection.id)):
        return None
    return {
        "account_number": account_id,
        "nickname": connection.broker.title(),
        "type": "paper" if connection.is_paper else "live",
        "state": connection.status,
        "agentic_allowed": True,
        "option_level": "",
        "is_default": True,
        "equity": connection.last_equity,
        "cash": None,
        "buying_power": None,
    }


def _account_detail_payload(request, connection, account: dict) -> dict:
    account_number = account["account_number"]
    assignment = (
        UserStrategyAssignment.objects.filter(
            user=request.user,
            is_active=True,
            broker_account_id=account_number,
        )
        .select_related("strategy", "investment_tier")
        .first()
    )
    if (
        assignment is None
        and connection.broker != "robinhood"
        and not (connection.broker_account_id or "").strip()
    ):
        assignment = (
            UserStrategyAssignment.objects.filter(user=request.user, is_active=True)
            .filter(Q(broker_account_id="") | Q(broker_account_id="default"))
            .select_related("strategy", "investment_tier")
            .first()
        )
    return {
        "connection": connection,
        "account": account,
        "trading_enabled": connection.broker_account_id == account_number
        or (
            connection.broker != "robinhood"
            and connection.status == BrokerConnection.Status.CONNECTED
        ),
        "assignment": assignment,
        "performance": account_performance(request.user, account_number),
    }


class RobinhoodOAuthStartView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="Start Robinhood OAuth",
        description=(
            "Registers this app with Robinhood if needed and returns the URL to "
            "authorize Agentic Trading MCP access. Robinhood only completes "
            "OAuth for a localhost callback, so the web app should open that URL "
            "then POST the resulting address-bar URL to oauth/complete/."
        ),
        request=None,
        responses={200: RobinhoodOAuthStartSerializer},
    )
    def post(self, request):
        redirect_uri = oauth_redirect_uri(
            request, reverse("robinhood-oauth-callback")
        )
        try:
            authorization_url = start_oauth(request.user.id, redirect_uri)
        except RobinhoodError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(
            {
                "authorization_url": authorization_url,
                "paste_required": True,
                "instruction": PASTE_CALLBACK_INSTRUCTION,
            }
        )


class RobinhoodOAuthCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Broker"],
        summary="Robinhood OAuth callback",
        description="Optional local callback. Hosted apps should paste this URL into oauth/complete/ instead.",
        parameters=[
            OpenApiParameter(name="code", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="state", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="error", type=str, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={302: None},
    )
    def get(self, request):
        error = request.query_params.get("error")
        if error:
            return redirect(_frontend_broker_redirect("error", error.replace("_", " ")))
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return redirect(_frontend_broker_redirect("error", "Missing OAuth code."))
        try:
            status_name, _connection = _finish_robinhood_oauth(code, state)
        except RobinhoodError as exc:
            return redirect(_frontend_broker_redirect("error", str(exc)))
        return redirect(_frontend_broker_redirect(status_name))


class RobinhoodOAuthCompleteView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="Finish Robinhood OAuth",
        description=(
            "Paste the localhost callback URL Robinhood opened after you allowed "
            "access. That page does not need to load; the address-bar URL is enough."
        ),
        request=RobinhoodOAuthCompleteSerializer,
        responses={200: RobinhoodOAuthCompleteResponseSerializer},
    )
    def post(self, request):
        serializer = RobinhoodOAuthCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            status_name, connection = _finish_robinhood_oauth(
                serializer.validated_data["code"],
                serializer.validated_data["state"],
                expected_user=request.user,
            )
        except RobinhoodError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "status": status_name,
                "connection": BrokerConnectionSerializer(connection).data,
            }
        )


class BrokerAccountListView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="List Robinhood accounts",
        responses={200: BrokerAccountSerializer(many=True)},
    )
    def get(self, request, pk):
        connection = get_object_or_404(BrokerConnection, pk=pk, user=request.user)
        if connection.broker != "robinhood":
            return Response(
                {"detail": "Account listing is only available for Robinhood."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            accounts = list_accounts_for(connection)
        except RobinhoodError as exc:
            connection.status = BrokerConnection.Status.ERROR
            connection.last_error = str(exc)[:255]
            connection.save(update_fields=["status", "last_error", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        _sync_connection_equity(connection, accounts)
        return Response(BrokerAccountSerializer(accounts, many=True).data)


class BrokerAccountDetailView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="Brokerage account detail",
        description=(
            "Strategy, investment tier, balances, and P&L for one account on a "
            "brokerage connection."
        ),
        responses={200: BrokerAccountDetailSerializer},
    )
    def get(self, request, pk, account_number):
        connection = get_object_or_404(BrokerConnection, pk=pk, user=request.user)
        if connection.broker == "robinhood":
            try:
                account = get_account_for(connection, account_number)
            except RobinhoodError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        else:
            account = _alpaca_account_snapshot(connection, account_number)
        if account is None:
            return Response(
                {"detail": "Account not found on this brokerage connection."},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = _account_detail_payload(request, connection, account)
        return Response(
            BrokerAccountDetailSerializer(payload, context={"request": request}).data
        )


class BrokerSelectAccountView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="Select Robinhood Agentic account",
        description="Sets which Agentic account receives trades. Send a blank account_number to turn trading off.",
        request=BrokerSelectAccountSerializer,
        responses={200: BrokerConnectionSerializer},
    )
    def post(self, request, pk):
        connection = get_object_or_404(BrokerConnection, pk=pk, user=request.user)
        if connection.broker != "robinhood":
            return Response(
                {"detail": "Account selection is only available for Robinhood."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = BrokerSelectAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_number = serializer.validated_data["account_number"].strip()
        if not account_number:
            connection.broker_account_id = ""
            connection.status = BrokerConnection.Status.CONNECTED
            connection.last_error = "Trading is off. Toggle an Agentic account to enable it."
            connection.save(
                update_fields=["broker_account_id", "status", "last_error", "updated_at"]
            )
            return Response(BrokerConnectionSerializer(connection).data)
        try:
            accounts = list_accounts_for(connection)
        except RobinhoodError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        match = next(
            (row for row in accounts if row["account_number"] == account_number),
            None,
        )
        if match is None:
            return Response(
                {"account_number": "That account was not returned by Robinhood."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not match.get("agentic_allowed"):
            return Response(
                {
                    "account_number": (
                        "Robinhood only lets agents trade in an Agentic account."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        connection.broker_account_id = account_number
        connection.status = BrokerConnection.Status.CONNECTED
        connection.last_error = ""
        connection.save(
            update_fields=["broker_account_id", "status", "last_error", "updated_at"]
        )
        _sync_connection_equity(connection, accounts)
        return Response(BrokerConnectionSerializer(connection).data)


class BrokerAgentToolsView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Broker"],
        summary="List Robinhood agent tools",
        description=(
            "Returns MCP tools available on the connected Robinhood Agentic Trading "
            "endpoint (tools/list), merged with the documented catalog."
        ),
        responses={200: AgentToolSerializer(many=True)},
    )
    def get(self, request, pk):
        connection = get_object_or_404(BrokerConnection, pk=pk, user=request.user)
        if connection.broker != "robinhood":
            return Response(
                {"detail": "Agent tools are only available for Robinhood."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tools = list_agent_tools_for(connection)
        except RobinhoodError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(AgentToolSerializer(tools, many=True).data)


class BrokerDisconnectView(APIView):
    permission_classes = TRADING_ACCESS
    serializer_class = BrokerConnectionSerializer

    @extend_schema(tags=["Broker"], summary="Disconnect brokerage account")
    def post(self, request, pk):
        connection = get_object_or_404(BrokerConnection, pk=pk, user=request.user)
        connection.soft_delete()
        connection.status = BrokerConnection.Status.DISCONNECTED
        connection.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Disconnected."})


class PositionListView(generics.ListAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = PositionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Position.objects.none()
        qs = Position.objects.filter(
            user=self.request.user, status=Position.Status.OPEN
        ).select_related("trade__investment_tier")
        account_id = (self.request.query_params.get("broker_account_id") or "").strip()
        if account_id:
            if account_id == "default":
                qs = qs.filter(
                    Q(trade__broker_account_id="") | Q(trade__broker_account_id="default")
                )
            else:
                qs = qs.filter(trade__broker_account_id=account_id)
        return qs


PositionListView = extend_schema(
    tags=["Positions"],
    summary="List my open positions",
    parameters=[
        OpenApiParameter(
            name="broker_account_id",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Limit to positions opened in this brokerage account.",
        )
    ],
)(PositionListView)


class TradeListView(generics.ListAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = TradeSerializer
    filterset_fields = ["status", "ticker", "strategy"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Trade.objects.none()
        qs = (
            Trade.objects.filter(user=self.request.user, is_archived=False)
            .select_related("signal", "strategy", "investment_tier")
            .prefetch_related("events", "orders", "decision_logs__notifications")
        )
        account_id = (self.request.query_params.get("broker_account_id") or "").strip()
        if account_id == "default":
            qs = qs.filter(Q(broker_account_id="") | Q(broker_account_id="default"))
        elif account_id:
            qs = qs.filter(broker_account_id=account_id)
        return qs


TradeListView = extend_schema(
    tags=["Trades"],
    summary="List my trade history",
    parameters=[
        OpenApiParameter(
            name="broker_account_id",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Limit to trades opened in this brokerage account.",
        )
    ],
)(TradeListView)


class TradeDetailView(generics.RetrieveAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = TradeSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Trade.objects.none()
        return (
            Trade.objects.filter(user=self.request.user)
            .select_related("signal", "strategy", "investment_tier")
            .prefetch_related("events", "orders", "decision_logs__notifications")
        )


TradeDetailView = extend_schema(tags=["Trades"], summary="Trade detail")(TradeDetailView)


class PerformanceView(APIView):
    permission_classes = TRADING_ACCESS

    @extend_schema(
        tags=["Performance"],
        summary="My performance including lifetime P&L",
        responses={
            200: inline_serializer(
                name="PersonalPerformance",
                fields={
                    "lifetime_realized_pnl": serializers.CharField(),
                    "lifetime_unrealized_pnl": serializers.CharField(),
                    "lifetime_total_pnl": serializers.CharField(),
                    "daily_realized_pnl": serializers.CharField(),
                    "weekly_realized_pnl": serializers.CharField(),
                    "is_paused_daily_loss": serializers.BooleanField(),
                    "open_positions": serializers.IntegerField(),
                    "closed_trades": serializers.IntegerField(),
                },
            )
        },
    )
    def get(self, request):
        return Response(personal_performance(request.user))


class DecisionListView(generics.ListAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = DecisionSerializer
    filterset_fields = ["action", "outcome", "ticker", "strategy", "trade"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Decision.objects.none()
        qs = (
            Decision.objects.filter(user=self.request.user)
            .select_related("strategy", "investment_tier", "signal", "trade")
            .prefetch_related("notifications")
        )
        account_id = (self.request.query_params.get("broker_account_id") or "").strip()
        if account_id == "default":
            qs = qs.filter(Q(broker_account_id="") | Q(broker_account_id="default"))
        elif account_id:
            qs = qs.filter(broker_account_id=account_id)
        return qs


DecisionListView = extend_schema(
    tags=["Decisions"],
    summary="Strategy decision paper trail",
    description=(
        "How your assigned strategy evaluated incoming signals and managed positions: "
        "acted vs passed, the investment-tier rule that applied, and the linked notification."
    ),
    parameters=[
        OpenApiParameter(
            name="action",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="enter, skip, take_profit, stop_loss, time_exit, expiration_exit, daily_pause.",
        ),
        OpenApiParameter(
            name="outcome",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="acted or passed.",
        ),
        OpenApiParameter(
            name="ticker",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
        ),
        OpenApiParameter(
            name="strategy",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
        ),
        OpenApiParameter(
            name="trade",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
        ),
        OpenApiParameter(
            name="broker_account_id",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Limit to decisions for this brokerage account.",
        ),
    ],
)(DecisionListView)


class DecisionDetailView(generics.RetrieveAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = DecisionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Decision.objects.none()
        return (
            Decision.objects.filter(user=self.request.user)
            .select_related("strategy", "investment_tier", "signal", "trade")
            .prefetch_related("notifications")
        )


DecisionDetailView = extend_schema(
    tags=["Decisions"],
    summary="Decision detail",
    description="Full rationale and context for one strategy decision.",
)(DecisionDetailView)


class NotificationListView(generics.ListAPIView):
    permission_classes = TRADING_ACCESS
    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        qs = Notification.objects.filter(user=self.request.user)
        unread = self.request.query_params.get("unread")
        if unread in ("1", "true", "True"):
            qs = qs.filter(is_read=False)
        account_id = (self.request.query_params.get("broker_account_id") or "").strip()
        if account_id:
            if account_id == "default":
                qs = qs.filter(Q(broker_account_id="") | Q(broker_account_id="default"))
            else:
                qs = qs.filter(broker_account_id=account_id)
        return qs


NotificationListView = extend_schema(
    tags=["Notifications"],
    summary="List my trading notifications",
    parameters=[
        OpenApiParameter(
            name="unread",
            type=bool,
            location=OpenApiParameter.QUERY,
            required=False,
            description="If true, only unread notifications.",
        ),
        OpenApiParameter(
            name="broker_account_id",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Limit to updates for this brokerage account.",
        ),
    ],
)(NotificationListView)


class NotificationReadView(APIView):
    permission_classes = TRADING_ACCESS
    serializer_class = NotificationSerializer

    @extend_schema(tags=["Notifications"], summary="Mark notification as read")
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)
