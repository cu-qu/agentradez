"""Run Django dev server bound for execution MCP smoke tests (same process as API)."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print execution MCP URL and remind to use the main API server (mcp route is on Django)."

    def handle(self, *args, **options):
        self.stdout.write(
            "Execution MCP is served at POST /api/mcp/execution/ on the Django API process.\n"
            "Start with: python manage.py runserver 0.0.0.0:8000 (or docker compose app).\n"
            "Authorize with header: Authorization: Bearer <user agz_pat_... from Settings>"
        )
