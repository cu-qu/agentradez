"""Mint a one-time personal access token for MCP clients (e.g. Grok Bot)."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from execution.services.mcp_auth import DEFAULT_SCOPES, generate_pat

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create a per-user execution MCP bearer token (shown once). "
        "Use as Authorization: Bearer <token> against /api/mcp/execution/."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Agentradez user email")
        parser.add_argument("--label", default="grok-bot", help="Token label for revocation UI")
        parser.add_argument(
            "--scope",
            action="append",
            dest="scopes",
            default=None,
            help="Repeat for scopes (default: execution:read and execution:trade)",
        )

    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with email {email!r}") from exc

        scopes = options["scopes"] or list(DEFAULT_SCOPES)
        raw, row = generate_pat(user, options["label"], scopes=scopes)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created token id={row.pk} label={row.label!r} scopes={scopes} for user_id={user.pk}"
            )
        )
        self.stdout.write("Copy this token now; it cannot be shown again:")
        self.stdout.write(raw)