import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = (
        "Create a superuser from ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD. "
        "Skips if those env vars are unset or if the username already exists."
    )

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        email = os.environ.get("ADMIN_EMAIL", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "").strip()

        if not username or not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping admin creation: set ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD."
                )
            )
            return

        user = User.objects.filter(username=username).first()
        if user:
            self.stdout.write(self.style.WARNING(f"Admin user already exists: {username}"))
            return

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_superuser = True
        user.is_staff = True
        user.email_verified = True
        user.save(update_fields=["is_superuser", "is_staff", "email_verified"])
        self.stdout.write(self.style.SUCCESS(f"Admin user created: {user.username}"))
