from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from trading.constants import STRATEGY_TYPE_CATALOG
from trading.models import (
    Decision,
    IngestedPost,
    InvestmentTier,
    Position,
    ResearchEvent,
    Signal,
    SignalDecision,
    Strategy,
    Trade,
    UserGroup,
    UserStrategyAssignment,
    WatchedCompany,
    XAccountSource,
)
from trading.serializers import (
    AdminForceAssignmentSerializer,
    AdminInvestmentTierSerializer,
    AdminStrategySerializer,
    AdminUserSerializer,
    AssignmentSerializer,
    DecisionSerializer,
    IngestedPostSerializer,
    PlatformStatsSerializer,
    PositionSerializer,
    ResearchEventSerializer,
    ResearchIngestSerializer,
    ResearchParseSerializer,
    SignalCreateSerializer,
    SignalDecisionSerializer,
    SignalSerializer,
    TradeSerializer,
    UserGroupSerializer,
    WatchedCompanySerializer,
    XAccountSourceSerializer,
    XIngestSerializer,
    XLookbackSerializer,
    XParseSerializer,
)
from trading.services.jobs import set_assignment
from trading.services.performance import refresh_account_and_platform_pnl
from trading.services.research_classifier import CompanyRef, classify_text
from trading.services.research_watcher import ingest_headline, poll_strategy
from trading.services.signal_engine import process_signal
from trading.services.x_trade_parser import parse_trades
from trading.services.x_watcher import ingest_tweet, lookback_source, poll_source

User = get_user_model()


def admin_strategy_queryset():
    return (
        Strategy.objects.all()
        .prefetch_related("x_sources", "watched_companies", "allowed_users", "allowed_groups__members")
        .annotate(
            assigned_user_count=Count(
                "assignments",
                filter=Q(assignments__is_active=True),
            )
        )
        .order_by("name")
    )


class AdminStrategyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminStrategySerializer
    queryset = admin_strategy_queryset()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "strategy_type", "visibility"]
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["name", "created_at", "updated_at"]


AdminStrategyListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or create strategies",
    description=(
        "Create a strategy for the user picker. For copy_trade (Copy Trade), "
        "set `signal_source` (`x` now; chat groups later) and include nested "
        "`x_source` with the X handle and optional `poll_interval_seconds`. "
        "For research_breakthrough (Research / Breakthrough), include `research_config` "
        "(sectors, enabled_event_types, news_keywords, scoring, option DTE) and "
        "`watched_companies`. "
        "Set `visibility` to `public` or `restricted` with `allowed_user_ids` / "
        "`allowed_group_ids`."
    ),
    parameters=[
        OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("strategy_type", str, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("visibility", str, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("search", str, OpenApiParameter.QUERY, required=False),
    ],
)(AdminStrategyListCreateView)


class AdminStrategyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminStrategySerializer
    queryset = admin_strategy_queryset()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        instance.x_sources.update(is_active=False)
        instance.watched_companies.update(is_active=False)
        return Response(self.get_serializer(instance).data)


AdminStrategyDetailView = extend_schema(
    tags=["Admin"],
    summary="Get, update, or deactivate a strategy",
    description="DELETE deactivates the strategy and its watchers; history is kept.",
)(AdminStrategyDetailView)


class IngestedPostFilter(django_filters.FilterSet):
    strategy = django_filters.NumberFilter(field_name="source__strategy_id")

    class Meta:
        model = IngestedPost
        fields = ["source", "parse_status", "strategy"]


class AdminStrategyPostListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = IngestedPostSerializer
    filterset_fields = ["parse_status", "source"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return IngestedPost.objects.none()
        get_object_or_404(Strategy, pk=self.kwargs["pk"])
        return (
            IngestedPost.objects.filter(source__strategy_id=self.kwargs["pk"])
            .select_related("source")
            .prefetch_related("signals")
        )


AdminStrategyPostListView = extend_schema(
    tags=["Admin"],
    summary="Tweets ingested for a strategy",
    description="X posts watched for this copy-trade strategy, with parsed signals nested.",
)(AdminStrategyPostListView)


class AdminStrategySignalListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SignalSerializer
    filterset_fields = ["status", "ticker", "option_type"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Signal.objects.none()
        get_object_or_404(Strategy, pk=self.kwargs["pk"])
        return (
            Signal.objects.filter(strategy_id=self.kwargs["pk"])
            .select_related("strategy", "ingested_post", "research_event")
        )


AdminStrategySignalListView = extend_schema(
    tags=["Admin"],
    summary="Signals for a strategy",
    description="Includes tweet_text when the signal came from an ingested X post.",
)(AdminStrategySignalListView)


class AdminStrategyLookbackView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Look back and parse X copy-trade posts",
        description=(
            "Fetches tweets from the strategy's X account for the last N days, "
            "parses option entries into signals, and skips duplicates. Historical "
            "signals are stored but not auto-traded."
        ),
        request=XLookbackSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk)
        source = strategy.primary_x_source()
        if source is None or not source.is_active:
            return Response(
                {"detail": "This strategy has no active X account to look back on."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = XLookbackSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        payload = lookback_source(source, days=serializer.validated_data["days"])
        payload["strategy_id"] = strategy.id
        if payload.get("error"):
            payload["detail"] = payload["error"]
            return Response(payload, status=status.HTTP_502_BAD_GATEWAY)
        return Response(payload)


class AdminStrategyTypeListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Strategy types the admin form can create",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        return Response({"results": STRATEGY_TYPE_CATALOG})


class AdminUserGroupListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserGroupSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["name", "created_at"]
    queryset = UserGroup.objects.annotate(member_count=Count("members")).prefetch_related(
        "members"
    )


AdminUserGroupListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or create user groups",
    description="Groups are used to restrict strategies to a set of users.",
)(AdminUserGroupListCreateView)


class AdminUserGroupDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserGroupSerializer
    queryset = UserGroup.objects.annotate(member_count=Count("members")).prefetch_related(
        "members"
    )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(instance).data)


AdminUserGroupDetailView = extend_schema(
    tags=["Admin"],
    summary="Get, update, or deactivate a user group",
    description="DELETE deactivates the group; strategies using it stop granting access.",
)(AdminUserGroupDetailView)


class AdminTierListView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminInvestmentTierSerializer
    queryset = InvestmentTier.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "is_default"]
    search_fields = ["name", "slug"]
    ordering_fields = ["sort_order", "name"]


AdminTierListView = extend_schema(
    tags=["Admin"], summary="List or create investment tiers"
)(AdminTierListView)


class AdminTierDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminInvestmentTierSerializer
    queryset = InvestmentTier.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(instance).data)


AdminTierDetailView = extend_schema(
    tags=["Admin"],
    summary="View, edit, or deactivate an investment tier",
    description="DELETE deactivates the tier; assigned users keep their current rules snapshot on open trades.",
)(AdminTierDetailView)


class AdminTierUsageView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Users per investment tier",
        responses={
            200: inline_serializer(
                name="TierUsage",
                fields={"users_by_tier": serializers.DictField()},
            )
        },
    )
    def get(self, request):
        stats = refresh_account_and_platform_pnl()
        return Response({"users_by_tier": stats.users_by_tier})


class AdminPlatformStatsView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = PlatformStatsSerializer

    @extend_schema(tags=["Admin"], summary="Platform-wide lifetime P&L and totals")
    def get(self, request):
        stats = refresh_account_and_platform_pnl()
        return Response(
            {
                "lifetime_realized_pnl": str(stats.lifetime_realized_pnl),
                "lifetime_unrealized_pnl": str(stats.lifetime_unrealized_pnl),
                "lifetime_total_pnl": str(
                    stats.lifetime_realized_pnl + stats.lifetime_unrealized_pnl
                ),
                "trade_count": stats.trade_count,
                "win_count": stats.win_count,
                "loss_count": stats.loss_count,
                "active_user_count": stats.active_user_count,
                "open_position_count": stats.open_position_count,
                "users_by_tier": stats.users_by_tier,
                "pnl_by_strategy": stats.pnl_by_strategy,
                "pnl_by_tier": stats.pnl_by_tier,
                "updated_at": stats.updated_at,
            }
        )


class AdminPerformanceByTierView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Performance breakdown by tier",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        stats = refresh_account_and_platform_pnl()
        return Response(stats.pnl_by_tier)


class AdminPerformanceByStrategyView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Performance breakdown by strategy",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        stats = refresh_account_and_platform_pnl()
        return Response(stats.pnl_by_strategy)


class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_staff", "is_active", "email_verified"]
    search_fields = ["username", "email"]
    ordering_fields = ["username", "date_joined"]
    queryset = (
        User.objects.filter(is_deleted=False)
        .prefetch_related(
            Prefetch(
                "strategy_assignments",
                queryset=UserStrategyAssignment.objects.filter(is_active=True).select_related(
                    "strategy", "investment_tier"
                ),
                to_attr="active_assignments",
            )
        )
        .order_by("username")
    )


AdminUserListView = extend_schema(
    tags=["Admin"],
    summary="List users for strategy assignment",
    parameters=[
        OpenApiParameter("search", str, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
    ],
)(AdminUserListView)


class AdminUserDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = (
        User.objects.filter(is_deleted=False)
        .prefetch_related(
            Prefetch(
                "strategy_assignments",
                queryset=UserStrategyAssignment.objects.filter(is_active=True).select_related(
                    "strategy", "investment_tier"
                ),
                to_attr="active_assignments",
            )
        )
    )


AdminUserDetailView = extend_schema(tags=["Admin"], summary="User detail with assignment")(
    AdminUserDetailView
)


class AdminForceAssignmentView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminForceAssignmentSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Force-change a user's strategy and/or tier",
        request=AdminForceAssignmentSerializer,
        responses=AssignmentSerializer,
    )
    def post(self, request):
        serializer = AdminForceAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=serializer.validated_data["user_id"])
        current = UserStrategyAssignment.objects.filter(user=user, is_active=True).first()
        strategy_id = serializer.validated_data.get("strategy_id")
        if strategy_id:
            strategy = get_object_or_404(Strategy, pk=strategy_id)
        elif current:
            strategy = current.strategy
        else:
            return Response(
                {"detail": "strategy_id is required when the user has no assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tier = get_object_or_404(
            InvestmentTier, pk=serializer.validated_data["investment_tier_id"]
        )
        assignment = set_assignment(user, strategy, tier, assigned_by=request.user)
        return Response(AssignmentSerializer(assignment).data)


class AdminSignalListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Signal.objects.select_related("strategy", "ingested_post", "research_event")
    filterset_fields = ["strategy", "status", "ticker", "option_type", "ingested_post"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SignalCreateSerializer
        return SignalSerializer

    def perform_create(self, serializer):
        signal = serializer.save()
        process_signal(signal)


AdminSignalListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or create signals",
    description="Creating a signal distributes it to assigned users and applies tier rules.",
)(AdminSignalListCreateView)


class AdminSignalDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SignalSerializer
    queryset = Signal.objects.select_related("strategy", "ingested_post", "research_event")


AdminSignalDetailView = extend_schema(tags=["Admin"], summary="Signal detail")(
    AdminSignalDetailView
)


class AdminSignalDecisionListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SignalDecisionSerializer
    filterset_fields = ["signal", "outcome", "user"]
    queryset = SignalDecision.objects.select_related("user", "signal", "log")


AdminSignalDecisionListView = extend_schema(
    tags=["Admin"], summary="Signal decisions (enter vs skip)"
)(AdminSignalDecisionListView)


class AdminDecisionListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = DecisionSerializer
    filterset_fields = ["action", "outcome", "user", "strategy", "ticker", "trade"]
    queryset = Decision.objects.select_related(
        "user", "strategy", "investment_tier", "signal", "trade"
    ).prefetch_related("notifications")


AdminDecisionListView = extend_schema(
    tags=["Admin"],
    summary="Strategy decision paper trail",
    description="Acted vs passed decisions across all users, including skip reasons and exits.",
)(AdminDecisionListView)


class AdminTradeListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = TradeSerializer
    filterset_fields = ["status", "user", "strategy", "investment_tier", "ticker"]
    queryset = (
        Trade.objects.select_related("signal", "strategy", "investment_tier", "user")
        .prefetch_related("events", "orders", "decision_logs__notifications")
    )


AdminTradeListView = extend_schema(tags=["Admin"], summary="All trades")(AdminTradeListView)


class AdminTradeDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = TradeSerializer
    queryset = Trade.objects.select_related(
        "signal", "strategy", "investment_tier"
    ).prefetch_related("events", "orders", "decision_logs__notifications")


AdminTradeDetailView = extend_schema(tags=["Admin"], summary="Trade detail (admin)")(
    AdminTradeDetailView
)


class AdminPositionListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PositionSerializer
    filterset_fields = ["status", "user", "ticker"]
    queryset = Position.objects.select_related("trade__investment_tier", "user")


AdminPositionListView = extend_schema(tags=["Admin"], summary="All positions")(
    AdminPositionListView
)


class AdminXSourceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = XAccountSourceSerializer
    queryset = XAccountSource.objects.select_related("strategy")
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["strategy", "is_active"]
    search_fields = ["handle", "display_name"]
    ordering_fields = ["handle", "last_polled_at"]


AdminXSourceListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or create X account watchers",
    description=(
        "X watchers for Copy Trade strategies. Each source's poll_interval_seconds controls "
        "how often Celery pulls new posts. Polling uses X_BEARER_TOKEN from the environment."
    ),
)(AdminXSourceListCreateView)


class AdminXSourceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = XAccountSourceSerializer
    queryset = XAccountSource.objects.select_related("strategy")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(instance).data)


AdminXSourceDetailView = extend_schema(
    tags=["Admin"],
    summary="Get, update, or deactivate an X account watcher",
    description="DELETE stops polling; ingested posts are kept.",
)(AdminXSourceDetailView)


class AdminXSourcePollView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Poll an X account now",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, pk):
        source = get_object_or_404(XAccountSource, pk=pk)
        return Response(poll_source(source, force=True))


class AdminXSourceIngestView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = XIngestSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Ingest a tweet into copy-trade signals",
        description="Parse tweet text and create signals without calling the X API.",
        request=XIngestSerializer,
        responses={200: IngestedPostSerializer},
    )
    def post(self, request, pk):
        source = get_object_or_404(XAccountSource, pk=pk)
        serializer = XIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tweet_id = (data.get("tweet_id") or "").strip()
        if not tweet_id:
            tweet_id = f"manual-{int(timezone.now().timestamp() * 1000)}"
        post = ingest_tweet(
            source,
            tweet_id=tweet_id,
            text=data["text"],
            posted_at=data.get("posted_at"),
            process=data.get("process", True),
        )
        return Response(IngestedPostSerializer(post).data)


class AdminXParseView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = XParseSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Preview parsed trades from tweet text",
        request=XParseSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = XParseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trades = parse_trades(
            serializer.validated_data["text"],
            posted_at=serializer.validated_data.get("posted_at"),
        )
        return Response({"trades": [trade.as_dict() for trade in trades]})


class AdminIngestedPostListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = IngestedPostSerializer
    filterset_class = IngestedPostFilter
    queryset = IngestedPost.objects.select_related("source").prefetch_related("signals")


AdminIngestedPostListView = extend_schema(
    tags=["Admin"], summary="List ingested X posts"
)(AdminIngestedPostListView)


class AdminIngestedPostDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = IngestedPostSerializer
    queryset = IngestedPost.objects.select_related("source").prefetch_related("signals")


AdminIngestedPostDetailView = extend_schema(
    tags=["Admin"], summary="Ingested X post detail"
)(AdminIngestedPostDetailView)


class AdminStrategyEventListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ResearchEventSerializer
    filterset_fields = ["status", "event_type", "direction", "source"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ResearchEvent.objects.none()
        get_object_or_404(Strategy, pk=self.kwargs["pk"])
        return (
            ResearchEvent.objects.filter(strategy_id=self.kwargs["pk"])
            .select_related("company", "strategy")
            .prefetch_related("signals")
        )


AdminStrategyEventListView = extend_schema(
    tags=["Admin"],
    summary="Research events for a strategy",
    description="Headlines ingested for a Research / Breakthrough strategy, with classification and any signals.",
)(AdminStrategyEventListView)


class AdminStrategyResearchPollView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Poll research headlines now",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk)
        return Response(poll_strategy(strategy, force=True))


class AdminStrategyResearchIngestView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = ResearchIngestSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Ingest a research headline",
        description=(
            "Classify a headline against the strategy watchlist and, on a catalyst, "
            "select an options contract. Does not copy a trader's ticket."
        ),
        request=ResearchIngestSerializer,
        responses={200: ResearchEventSerializer(many=True)},
    )
    def post(self, request, pk):
        strategy = get_object_or_404(Strategy, pk=pk)
        serializer = ResearchIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        events, _signals = ingest_headline(
            strategy,
            headline=data["headline"],
            summary=data.get("summary") or "",
            source_url=data.get("source_url") or "",
            published_at=data.get("published_at"),
            process=data.get("process", True),
        )
        return Response(ResearchEventSerializer(events, many=True).data)


class AdminResearchParseView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = ResearchParseSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Preview research catalyst classification",
        request=ResearchParseSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = ResearchParseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        headline = serializer.validated_data["headline"]
        summary = serializer.validated_data.get("summary") or ""
        tickers = [
            row.strip().upper()
            for row in serializer.validated_data.get("tickers") or []
            if row.strip()
        ]
        queryset = WatchedCompany.objects.filter(is_active=True)
        if tickers:
            queryset = queryset.filter(ticker__in=tickers)
        companies = [
            CompanyRef(ticker=row.ticker, name=row.name, aliases=row.aliases or [])
            for row in queryset
        ]
        if tickers:
            have = {row.ticker for row in companies}
            for ticker in tickers:
                if ticker not in have:
                    companies.append(CompanyRef(ticker=ticker, name=ticker, aliases=[]))
        results = classify_text(
            headline,
            summary,
            companies,
            enabled_event_types=serializer.validated_data.get("enabled_event_types") or None,
            require_confirmation=serializer.validated_data.get("require_confirmation", True),
        )
        return Response({"classifications": [row.as_dict() for row in results]})


class AdminWatchedCompanyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = WatchedCompanySerializer
    queryset = WatchedCompany.objects.select_related("strategy")
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["strategy", "is_active", "sector"]
    search_fields = ["ticker", "name"]
    ordering_fields = ["ticker", "name"]


AdminWatchedCompanyListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or add watched companies",
    description="Universe for Research / Breakthrough. Tag a sector if the strategy filters by sector.",
)(AdminWatchedCompanyListCreateView)


class AdminWatchedCompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = WatchedCompanySerializer
    queryset = WatchedCompany.objects.select_related("strategy")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(instance).data)


AdminWatchedCompanyDetailView = extend_schema(
    tags=["Admin"],
    summary="Get, update, or deactivate a watched company",
    description="DELETE stops matching headlines for this ticker; past events are kept.",
)(AdminWatchedCompanyDetailView)


class AdminResearchEventListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ResearchEventSerializer
    filterset_fields = ["strategy", "status", "event_type", "direction", "source"]
    queryset = ResearchEvent.objects.select_related("company", "strategy").prefetch_related(
        "signals"
    )


AdminResearchEventListView = extend_schema(
    tags=["Admin"], summary="List research events"
)(AdminResearchEventListView)


class AdminResearchEventDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ResearchEventSerializer
    queryset = ResearchEvent.objects.select_related("company", "strategy").prefetch_related(
        "signals"
    )


AdminResearchEventDetailView = extend_schema(
    tags=["Admin"], summary="Research event detail"
)(AdminResearchEventDetailView)
