from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import User


class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("accounts.views.send_verification_email")
    def test_register_returns_jwt_and_integer_id(self, mock_send):
        resp = self.client.post(
            "/api/auth/register/",
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "longpassword1",
            },
        )
        self.assertEqual(resp.status_code, 201)
        mock_send.assert_called_once()
        data = resp.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIsInstance(data["user"]["id"], int)
        self.assertNotIn("origin_brand", data["user"])
        user = User.objects.get(username="newuser")
        self.assertFalse(user.email_verified)
        self.assertIsInstance(user.id, int)


class VerifyEmailApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="verifyme",
            email="verify@example.com",
            password="testpass123",
        )
        self.user.regenerate_email_verification_token()

    def test_verify_email_success(self):
        token = self.user.email_verification_token
        resp = self.client.get(f"/api/auth/verify-email/?token={token}")
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertEqual(self.user.email_verification_token, "")

    def test_verify_email_missing_token(self):
        resp = self.client.get("/api/auth/verify-email/")
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_invalid_token(self):
        resp = self.client.get("/api/auth/verify-email/?token=not-a-real-token")
        self.assertEqual(resp.status_code, 400)


class ResendVerificationEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="resenduser",
            email="resend@example.com",
            password="testpass123",
        )

    @patch("accounts.services.VerifyAccountEmail.send")
    def test_resend_sends_when_not_verified(self, mock_send):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/auth/verify-email/resend/")
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()

    def test_resend_rejected_when_already_verified(self):
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])
        self.client.force_authenticate(user=self.user)
        resp = self.client.post("/api/auth/verify-email/resend/")
        self.assertEqual(resp.status_code, 400)


class PasswordResetApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="pwuser",
            email="pw@example.com",
            password="oldpass123",
        )

    @patch("accounts.views.send_password_reset_email")
    def test_password_reset_request_sends_when_user_exists(self, mock_send):
        resp = self.client.post(
            "/api/auth/password-reset/",
            {"email": "pw@example.com"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()

    @patch("accounts.views.send_password_reset_email")
    def test_password_reset_request_same_response_when_unknown_email(self, mock_send):
        resp = self.client.post(
            "/api/auth/password-reset/",
            {"email": "nobody@example.com"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()

    def test_password_reset_confirm_updates_password(self):
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        token = default_token_generator.make_token(self.user)
        resp = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "new-strong-pass-99",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-strong-pass-99"))

    def test_password_reset_confirm_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(str(self.user.pk)))
        resp = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "new-strong-pass-99",
            },
        )
        self.assertEqual(resp.status_code, 400)


class MeAndProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="profileuser",
            email="profile@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.user)

    def test_me_returns_integer_id(self):
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data["id"], int)
        self.assertEqual(data["username"], "profileuser")
        self.assertFalse(data["is_staff"])
        self.assertNotIn("origin_brand", data)

    def test_profile_preferred_language(self):
        resp = self.client.get("/api/auth/profile/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data["id"], int)
        self.assertEqual(data["preferred_language"], "en")
        self.assertNotIn("monthly_listings_remaining", data)

        resp = self.client.patch(
            "/api/auth/profile/",
            {"preferred_language": "es"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["preferred_language"], "es")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_USE_ANYMAIL_TAGS=False,
    DEFAULT_FROM_EMAIL="Test <from@test.com>",
)
class TransactionalMailTests(TestCase):
    def test_verify_account_email_renders_and_sends(self):
        from django.core import mail

        from accounts.emails import VerifyAccountEmail

        user = User.objects.create_user(
            username="m1",
            email="m1@example.com",
            password="x",
        )
        VerifyAccountEmail(user, "tokensecret").send()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("tokensecret", msg.body)
        self.assertTrue(any("tokensecret" in alt for alt, _ in msg.alternatives))

    def test_password_reset_email_includes_link(self):
        from django.core import mail

        from accounts.emails import PasswordResetEmail

        user = User.objects.create_user(
            username="m2",
            email="m2@example.com",
            password="x",
        )
        PasswordResetEmail(user, "dXNlcg", "reset-token-xyz").send()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-token-xyz", mail.outbox[0].body)
