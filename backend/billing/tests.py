from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.constants import FEATURE_TRADING, PLAN_MONTHLY, PLAN_YEARLY
from billing.models import Feature, Plan, Subscription, SubscriptionGrant
from billing.services.catalog import ensure_default_plans
from billing.services.entitlements import grant_subscription, user_can_trade
from billing.services.stripe import process_stripe_event, upsert_subscription_from_stripe


class BillingApiTests(TestCase):
    def setUp(self):
        ensure_default_plans()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="payer",
            email="payer@example.com",
            password="longpassword1",
        )
        self.staff = User.objects.create_user(
            username="staffer",
            email="staffer@example.com",
            password="longpassword1",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)

    def test_lists_free_monthly_yearly_plans(self):
        resp = self.client.get("/api/billing/plans/")
        self.assertEqual(resp.status_code, 200)
        slugs = [row["slug"] for row in resp.json()]
        self.assertEqual(slugs, ["free", "monthly", "yearly"])
        features = {row["slug"]: row["features"] for row in resp.json()}
        self.assertFalse(features["free"][FEATURE_TRADING])
        self.assertTrue(features["monthly"][FEATURE_TRADING])
        self.assertTrue(features["yearly"][FEATURE_TRADING])

    def test_me_and_subscription_start_on_free(self):
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        sub = me.json()["subscription"]
        self.assertEqual(sub["plan"], "free")
        self.assertFalse(sub["is_paid"])
        self.assertFalse(sub["features"][FEATURE_TRADING])

        mine = self.client.get("/api/billing/subscription/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["source"], "free")

    def test_paywall_blocks_assignment_until_granted(self):
        blocked = self.client.put(
            "/api/assignment/",
            {"strategy_id": 1, "investment_tier_id": 1},
            format="json",
        )
        self.assertEqual(blocked.status_code, 402)
        self.assertEqual(blocked.json()["code"], "subscription_required")

        grant_subscription(email=self.user.email, plan_slug=PLAN_MONTHLY, note="friend")
        self.assertTrue(user_can_trade(self.user))
        mine = self.client.get("/api/billing/subscription/")
        self.assertEqual(mine.json()["plan"], "monthly")
        self.assertEqual(mine.json()["source"], "grant")
        self.assertTrue(mine.json()["is_paid"])

    def test_staff_can_grant_by_email_before_signup(self):
        staff_client = APIClient()
        staff_client.force_authenticate(self.staff)
        resp = staff_client.post(
            "/api/admin/billing/grants/",
            {
                "email": "pal@example.com",
                "plan": "yearly",
                "note": "beta friend",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.json())
        self.assertIsNone(resp.json()["user_id"])
        self.assertTrue(resp.json()["is_active"])

        pal = User.objects.create_user(
            username="pal",
            email="pal@example.com",
            password="longpassword1",
        )
        pal.refresh_from_db()
        grant = SubscriptionGrant.objects.get(email="pal@example.com")
        self.assertEqual(grant.user_id, pal.id)
        self.assertTrue(user_can_trade(pal))

    def test_revoke_grant_and_feature_config(self):
        grant = grant_subscription(email=self.user.email, plan_slug=PLAN_YEARLY)
        staff_client = APIClient()
        staff_client.force_authenticate(self.staff)
        revoked = staff_client.post(f"/api/admin/billing/grants/{grant.id}/revoke/")
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.json()["is_active"])
        self.assertFalse(user_can_trade(self.user))

        monthly = Plan.objects.get(slug=PLAN_MONTHLY)
        patched = staff_client.patch(
            f"/api/admin/billing/plans/{monthly.id}/",
            {"features": {FEATURE_TRADING: True, "copy_trade": True}},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertTrue(patched.json()["features"]["copy_trade"])

        created = staff_client.post(
            "/api/admin/billing/features/",
            {
                "slug": "copy_trade",
                "name": "Copy Trade",
                "description": "Use copy-trade strategies.",
                "value_type": "boolean",
                "default_value": False,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.json())
        self.assertEqual(Feature.objects.get(slug="copy_trade").name, "Copy Trade")

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_dummy",
        STRIPE_PRICE_MONTHLY="price_monthly",
    )
    def test_checkout_returns_stripe_url(self):
        ensure_default_plans()
        stripe_mod = MagicMock()
        stripe_mod.Customer.create.return_value = SimpleNamespace(id="cus_123")
        stripe_mod.checkout.Session.create.return_value = SimpleNamespace(
            id="cs_test_123",
            url="https://checkout.stripe.com/c/pay/cs_test_123",
        )
        with patch("billing.services.stripe._stripe", return_value=stripe_mod):
            resp = self.client.post(
                "/api/billing/checkout/",
                {"plan": "monthly"},
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.json())
        self.assertTrue(resp.json()["checkout_url"].startswith("https://checkout.stripe.com/"))
        stripe_mod.checkout.Session.create.assert_called_once()

    def test_checkout_without_stripe_is_unavailable(self):
        resp = self.client.post("/api/billing/checkout/", {"plan": "monthly"}, format="json")
        self.assertEqual(resp.status_code, 503)

    @override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
    def test_webhook_upserts_subscription(self):
        ensure_default_plans()
        Plan.objects.filter(slug=PLAN_MONTHLY).update(stripe_price_id="price_monthly")
        event = {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_123",
                    "status": "active",
                    "customer": "cus_123",
                    "cancel_at_period_end": False,
                    "current_period_start": int(timezone.now().timestamp()),
                    "current_period_end": int(timezone.now().timestamp()) + 30 * 24 * 3600,
                    "metadata": {"user_id": str(self.user.id), "plan": "monthly"},
                    "items": {"data": [{"price": {"id": "price_monthly"}}]},
                }
            },
        }
        with patch("billing.views.construct_event", return_value=event):
            resp = self.client.post(
                "/api/billing/webhooks/stripe/",
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
            )
        self.assertEqual(resp.status_code, 200)
        row = Subscription.objects.get(stripe_subscription_id="sub_123")
        self.assertEqual(row.user_id, self.user.id)
        self.assertEqual(row.plan.slug, "monthly")
        self.assertTrue(user_can_trade(self.user))
        process_stripe_event(event)
        self.assertEqual(Subscription.objects.filter(stripe_subscription_id="sub_123").count(), 1)

    def test_grant_command(self):
        call_command("grant_subscription", "friend@example.com", plan="yearly", note="pal")
        grant = SubscriptionGrant.objects.get(email="friend@example.com")
        self.assertEqual(grant.plan.slug, PLAN_YEARLY)
        call_command("grant_subscription", "friend@example.com", revoke=True)
        grant.refresh_from_db()
        self.assertFalse(grant.is_active)


class StripeSyncTests(TestCase):
    def setUp(self):
        ensure_default_plans()
        Plan.objects.filter(slug=PLAN_YEARLY).update(stripe_price_id="price_yearly")
        self.user = User.objects.create_user(
            username="stripeuser",
            email="stripeuser@example.com",
            password="longpassword1",
        )

    def test_upsert_from_stripe_object(self):
        sub = SimpleNamespace(
            id="sub_yearly",
            status="active",
            customer="cus_abc",
            cancel_at_period_end=False,
            current_period_start=int(timezone.now().timestamp()),
            current_period_end=int(timezone.now().timestamp()) + 365 * 24 * 3600,
            metadata={"user_id": str(self.user.id), "plan": "yearly"},
            items=SimpleNamespace(data=[SimpleNamespace(price=SimpleNamespace(id="price_yearly"))]),
        )
        row = upsert_subscription_from_stripe(sub)
        self.assertEqual(row.plan.slug, PLAN_YEARLY)
        self.assertTrue(user_can_trade(self.user))
