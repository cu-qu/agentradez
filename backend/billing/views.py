from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Plan
from billing.serializers import CheckoutSerializer, PlanSerializer
from billing.services.catalog import ensure_default_plans
from billing.services.entitlements import entitlement_payload
from billing.services.stripe import (
    construct_event,
    create_checkout_session,
    create_portal_session,
    process_stripe_event,
)


class PlanListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        ensure_default_plans()
        return Plan.objects.filter(is_active=True, is_public=True)


PlanListView = extend_schema(
    tags=["Billing"],
    summary="List subscription plans",
    description="Public catalog: free, monthly, and yearly, including each plan's feature map.",
)(PlanListView)


class SubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Billing"],
        summary="My subscription",
        description="Current plan, source (stripe / grant / free), and resolved feature flags.",
        responses={
            200: inline_serializer(
                name="MySubscription",
                fields={
                    "plan": serializers.CharField(),
                    "plan_name": serializers.CharField(),
                    "status": serializers.CharField(),
                    "source": serializers.CharField(),
                    "features": serializers.DictField(),
                    "is_paid": serializers.BooleanField(),
                    "current_period_end": serializers.DateTimeField(allow_null=True),
                    "cancel_at_period_end": serializers.BooleanField(),
                    "interval": serializers.CharField(),
                    "amount_cents": serializers.IntegerField(),
                    "currency": serializers.CharField(),
                },
            )
        },
    )
    def get(self, request):
        ensure_default_plans()
        return Response(entitlement_payload(request.user))


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Billing"],
        summary="Start Stripe checkout",
        description="Creates a Stripe Checkout session for monthly or yearly. Returns a URL to redirect the user.",
        request=CheckoutSerializer,
        responses={
            200: inline_serializer(
                name="CheckoutSession",
                fields={
                    "checkout_url": serializers.URLField(),
                    "session_id": serializers.CharField(),
                },
            )
        },
    )
    def post(self, request):
        ensure_default_plans()
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = get_object_or_404(
            Plan, slug=serializer.validated_data["plan"], is_active=True
        )
        payload = create_checkout_session(request.user, plan)
        return Response(payload)


class PortalView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Billing"],
        summary="Open Stripe billing portal",
        description="Returns a Stripe Customer Portal URL to cancel or change the subscription.",
        request=None,
        responses={
            200: inline_serializer(
                name="PortalSession",
                fields={"portal_url": serializers.URLField()},
            )
        },
    )
    def post(self, request):
        return Response(create_portal_session(request.user))


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Billing"],
        summary="Stripe webhook",
        description="Stripe signature-verified webhook. Not called by the SPA.",
        request=None,
        responses={200: inline_serializer(name="StripeWebhookAck", fields={"received": serializers.BooleanField()})},
    )
    def post(self, request):
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        event = construct_event(request.body, signature)
        process_stripe_event(event)
        return Response({"received": True}, status=status.HTTP_200_OK)
