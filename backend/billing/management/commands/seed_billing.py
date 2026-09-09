from django.core.management.base import BaseCommand

from billing.services.catalog import ensure_default_plans


class Command(BaseCommand):
    help = "Seed free / monthly / yearly plans and the trading feature flag."

    def handle(self, *args, **options):
        plans = ensure_default_plans()
        for slug, plan in plans.items():
            price = plan.stripe_price_id or "(no Stripe price yet)"
            self.stdout.write(f"{slug}: {plan.name} {plan.amount_cents}¢ {price}")
        self.stdout.write(self.style.SUCCESS("Billing plans seeded."))
