from django.urls import path

from billing.views import CheckoutView, PlanListView, PortalView, StripeWebhookView, SubscriptionView
from billing.views_admin import (
    AdminFeatureDetailView,
    AdminFeatureListCreateView,
    AdminGrantListCreateView,
    AdminGrantRevokeView,
    AdminPlanDetailView,
    AdminPlanListView,
)

urlpatterns = [
    path("billing/plans/", PlanListView.as_view(), name="billing-plans"),
    path("billing/subscription/", SubscriptionView.as_view(), name="billing-subscription"),
    path("billing/checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("billing/portal/", PortalView.as_view(), name="billing-portal"),
    path(
        "billing/webhooks/stripe/",
        StripeWebhookView.as_view(),
        name="billing-stripe-webhook",
    ),
    path("admin/billing/plans/", AdminPlanListView.as_view(), name="admin-billing-plans"),
    path(
        "admin/billing/plans/<int:pk>/",
        AdminPlanDetailView.as_view(),
        name="admin-billing-plan-detail",
    ),
    path(
        "admin/billing/features/",
        AdminFeatureListCreateView.as_view(),
        name="admin-billing-features",
    ),
    path(
        "admin/billing/features/<int:pk>/",
        AdminFeatureDetailView.as_view(),
        name="admin-billing-feature-detail",
    ),
    path(
        "admin/billing/grants/",
        AdminGrantListCreateView.as_view(),
        name="admin-billing-grants",
    ),
    path(
        "admin/billing/grants/<int:pk>/revoke/",
        AdminGrantRevokeView.as_view(),
        name="admin-billing-grant-revoke",
    ),
]
