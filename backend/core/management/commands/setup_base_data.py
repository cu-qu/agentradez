from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed admin user plus trading reference data and billing plans."

    def handle(self, *args, **options):
        call_command("create_admin_user")
        call_command("seed_trading")
        call_command("seed_billing")
        self.stdout.write(self.style.SUCCESS("Base data seeded successfully."))
