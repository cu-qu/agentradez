import logging

from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .emails import PasswordResetEmail, VerifyAccountEmail

logger = logging.getLogger(__name__)


def send_verification_email(user, *, verification_url: str | None = None) -> None:
    """
    Generate a fresh verification token, persist it, and send the verification email.
    Logs and swallows errors so callers (e.g. registration) are not blocked by mail outages.
    """
    try:
        user.regenerate_email_verification_token()
        token = user.email_verification_token
        VerifyAccountEmail(user, token, verification_url=verification_url).send()
    except Exception:
        logger.exception(
            "Failed to send verification email for user_id=%s email=%s",
            getattr(user, "pk", None),
            getattr(user, "email", None),
        )


def send_password_reset_email(user, *, reset_url: str | None = None) -> None:
    """Send password reset link (Django PasswordResetTokenGenerator). Logs failures."""
    try:
        uid = urlsafe_base64_encode(force_bytes(str(user.pk)))
        token = default_token_generator.make_token(user)
        PasswordResetEmail(user, uid, token, reset_url=reset_url).send()
    except Exception:
        logger.exception(
            "Failed to send password reset email for user_id=%s email=%s",
            getattr(user, "pk", None),
            getattr(user, "email", None),
        )
