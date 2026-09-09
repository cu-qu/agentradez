from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Feature, Plan, SubscriptionGrant
from billing.serializers import (
    AdminPlanSerializer,
    FeatureSerializer,
    GrantCreateSerializer,
    GrantSerializer,
)
from billing.services.catalog import ensure_default_plans
from billing.services.entitlements import grant_subscription, revoke_grant


class AdminPlanListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminPlanSerializer
    pagination_class = None
    queryset = Plan.objects.all()

    def get_queryset(self):
        ensure_default_plans()
        return Plan.objects.all()


AdminPlanListView = extend_schema(
    tags=["Admin"],
    summary="List billing plans",
    description="Staff: inspect Stripe price IDs and the per-plan feature map.",
)(AdminPlanListView)


class AdminPlanDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminPlanSerializer
    queryset = Plan.objects.all()


AdminPlanDetailView = extend_schema(
    tags=["Admin"],
    summary="Update a billing plan",
    description="Change display copy, Stripe IDs, or the JSON feature map (e.g. add a future flag).",
)(AdminPlanDetailView)


class AdminFeatureListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = FeatureSerializer
    pagination_class = None
    queryset = Feature.objects.all()

    def get_queryset(self):
        ensure_default_plans()
        return Feature.objects.all()


AdminFeatureListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or create billing features",
    description="Feature catalog used by plan.features. Add a slug now; turn it on per plan later.",
)(AdminFeatureListCreateView)


class AdminFeatureDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = FeatureSerializer
    queryset = Feature.objects.all()


AdminFeatureDetailView = extend_schema(
    tags=["Admin"],
    summary="Update a billing feature",
)(AdminFeatureDetailView)


class AdminGrantListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = GrantSerializer
    filterset_fields = ["is_active", "email", "plan__slug"]
    queryset = SubscriptionGrant.objects.select_related("plan", "user", "granted_by")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GrantCreateSerializer
        return GrantSerializer

    def create(self, request, *args, **kwargs):
        serializer = GrantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = Plan.objects.get(slug=serializer.validated_data["plan"])
        grant = grant_subscription(
            email=serializer.validated_data["email"],
            plan=plan,
            granted_by=request.user,
            days=serializer.validated_data.get("days"),
            note=serializer.validated_data.get("note") or "",
        )
        return Response(GrantSerializer(grant).data, status=status.HTTP_201_CREATED)


AdminGrantListCreateView = extend_schema(
    tags=["Admin"],
    summary="List or grant complimentary subscriptions",
    description=(
        "Grant monthly or yearly access by email. If the account does not exist yet, "
        "the grant is claimed automatically on registration. Omit `days` for access until revoked."
    ),
    parameters=[
        OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
        OpenApiParameter("email", str, OpenApiParameter.QUERY, required=False),
    ],
)(AdminGrantListCreateView)


class AdminGrantRevokeView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin"],
        summary="Revoke a complimentary grant",
        request=None,
        responses={200: GrantSerializer},
    )
    def post(self, request, pk):
        grant = get_object_or_404(SubscriptionGrant, pk=pk)
        revoke_grant(grant)
        return Response(GrantSerializer(grant).data)
