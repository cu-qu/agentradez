from django.core.management.base import BaseCommand, CommandError

from trading.models import XAccountSource
from trading.services.x_watcher import ingest_tweet, poll_all_sources, poll_source


class Command(BaseCommand):
    help = "Poll watched X accounts, or ingest tweet text into copy-trade signals."

    def add_arguments(self, parser):
        parser.add_argument("--source-id", type=int, help="Poll a single watcher.")
        parser.add_argument(
            "--ingest-text",
            dest="ingest_text",
            help="Parse this tweet text instead of calling the X API.",
        )
        parser.add_argument("--tweet-id", dest="tweet_id", default="", help="Optional tweet id.")
        parser.add_argument(
            "--no-process",
            action="store_true",
            help="Create signals but do not distribute them yet.",
        )

    def handle(self, *args, **options):
        ingest_text = options.get("ingest_text")
        source_id = options.get("source_id")
        if ingest_text:
            if not source_id:
                source = XAccountSource.objects.order_by("id").first()
                if source is None:
                    raise CommandError("No X watcher exists. Run seed_trading first.")
            else:
                try:
                    source = XAccountSource.objects.get(pk=source_id)
                except XAccountSource.DoesNotExist as exc:
                    raise CommandError(f"X watcher {source_id} not found") from exc
            tweet_id = options.get("tweet_id") or "manual-cli"
            post = ingest_tweet(
                source,
                tweet_id=tweet_id,
                text=ingest_text,
                process=not options["no_process"],
            )
            self.stdout.write(
                f"Post {post.id} status={post.parse_status} signals={post.signals.count()}"
            )
            return

        if source_id:
            try:
                source = XAccountSource.objects.get(pk=source_id)
            except XAccountSource.DoesNotExist as exc:
                raise CommandError(f"X watcher {source_id} not found") from exc
            result = poll_source(source, force=True)
        else:
            result = poll_all_sources()
        self.stdout.write(str(result))
