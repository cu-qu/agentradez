import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from core.constants import LANGUAGE_CHOICES


class User(AbstractUser):
    email = models.EmailField(unique=True)
    preferred_language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default="en"
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    email_verified = models.BooleanField(default=False, db_index=True)
    email_verification_token = models.CharField(max_length=128, blank=True, db_index=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "accounts_user"

    def regenerate_email_verification_token(self) -> str:
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        self.save(
            update_fields=["email_verification_token", "email_verification_sent_at"]
        )
        return self.email_verification_token

    def mark_email_verified(self) -> None:
        self.email_verified = True
        self.email_verification_token = ""
        self.save(update_fields=["email_verified", "email_verification_token"])


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    preferred_language = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default="en"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userprofile"
