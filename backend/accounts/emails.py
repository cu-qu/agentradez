from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings

from .mail import send_transactional_mail

if TYPE_CHECKING:
    from accounts.models import User


@dataclass
class VerifyAccountEmail:
    """Account verification email (Django templates + Anymail)."""

    user: User
    verification_token: str
    verification_url: str | None = None

    def __post_init__(self) -> None:
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        if not isinstance(self.user, UserModel):
            raise TypeError("user must be the configured user model instance.")

    def build_verification_url(self) -> str:
        if self.verification_url:
            return self.verification_url
        base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        path = getattr(settings, "EMAIL_VERIFICATION_FRONTEND_PATH", "/verify-email")
        path = path if path.startswith("/") else f"/{path}"
        q = urlencode({"token": self.verification_token})
        return f"{base}{path}?{q}"

    def send(self) -> None:
        subject = getattr(
            settings,
            "EMAIL_VERIFICATION_SUBJECT",
            "Confirm your email address",
        )
        send_transactional_mail(
            subject=subject,
            text_template="emails/account_verify.txt",
            html_template="emails/account_verify.html",
            context={
                "username": self.user.username,
                "verify_url": self.build_verification_url(),
            },
            to_email=self.user.email,
            tags=["account-verification"],
        )


@dataclass
class PasswordResetEmail:
    """Password reset link email."""

    user: User
    uid: str
    token: str
    reset_url: str | None = None

    def __post_init__(self) -> None:
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        if not isinstance(self.user, UserModel):
            raise TypeError("user must be the configured user model instance.")

    def build_reset_url(self) -> str:
        if self.reset_url:
            return self.reset_url
        base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        path = getattr(settings, "PASSWORD_RESET_FRONTEND_PATH", "/reset-password")
        path = path if path.startswith("/") else f"/{path}"
        q = urlencode({"uid": self.uid, "token": self.token})
        return f"{base}{path}?{q}"

    def send(self) -> None:
        subject = getattr(
            settings,
            "EMAIL_PASSWORD_RESET_SUBJECT",
            "Reset your password",
        )
        send_transactional_mail(
            subject=subject,
            text_template="emails/password_reset.txt",
            html_template="emails/password_reset.html",
            context={
                "username": self.user.username,
                "reset_url": self.build_reset_url(),
            },
            to_email=self.user.email,
            tags=["password-reset"],
        )
