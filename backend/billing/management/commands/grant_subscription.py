from django.core.management.base import BaseCommand, CommandError

from billing.models import Plan, SubscriptionGrant
from billing.services.entitlements import grant_subscription, revoke_grant


class Command(BaseCommand):
    help = (
        "Grant or revoke a complimentary monthly/yearly subscription by email. "
        "If the user has not signed up yet, the grant is claimed on registration."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--plan",
            default="yearly",
            help="Plan slug to grant (monthly or yearly). Default: yearly.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Optional duration in days. Omit for access until revoked.",
        )
        parser.add_argument("--note", default="", help="Internal note.")
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke all active grants for this email instead of creating one.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip()
        if options["revoke"]:
            grants = SubscriptionGrant.objects.filter(email__iexact=email, is_active=True)
            count = grants.count()
            for grant in grants:
                revoke_grant(grant)
            self.stdout.write(self.style.SUCCESS(f"Revoked {count} grant(s) for {email}."))
            return

        plan_slug = options["plan"].strip().lower()
        if not Plan.objects.filter(slug=plan_slug, is_active=True).exists():
            raise CommandError(f"Unknown plan: {plan_slug}")
        grant = grant_subscription(
            email=email,
            plan_slug=plan_slug,
            days=options["days"],
            note=options["note"],
        )
        until = grant.ends_at.isoformat() if grant.ends_at else "until revoked"
        claimed = "claimed" if grant.user_id else "pending signup"
        self.stdout.write(
            self.style.SUCCESS(
                f"Granted {plan_slug} to {email} ({claimed}, {until}). Grant id={grant.id}."
            )
        )
