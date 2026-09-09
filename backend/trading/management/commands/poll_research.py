from django.core.management.base import BaseCommand, CommandError

from trading.constants import STRATEGY_RESEARCH_BREAKTHROUGH
from trading.models import Strategy
from trading.services.research_watcher import ingest_headline, poll_all_research_strategies, poll_strategy


class Command(BaseCommand):
    help = "Poll Research / Breakthrough headlines, or ingest a headline into signals."

    def add_arguments(self, parser):
        parser.add_argument("--strategy-id", type=int, help="Poll a single research strategy.")
        parser.add_argument(
            "--ingest-headline",
            dest="ingest_headline",
            help="Classify this headline instead of fetching news.",
        )
        parser.add_argument("--summary", dest="summary", default="", help="Optional body text.")
        parser.add_argument(
            "--no-process",
            action="store_true",
            help="Create signals but do not distribute them yet.",
        )

    def handle(self, *args, **options):
        headline = options.get("ingest_headline")
        strategy_id = options.get("strategy_id")
        if headline:
            strategy = self._strategy(strategy_id)
            events, signals = ingest_headline(
                strategy,
                headline=headline,
                summary=options.get("summary") or "",
                process=not options["no_process"],
            )
            self.stdout.write(
                f"events={len(events)} signals={len(signals)} "
                f"status={[event.status for event in events]}"
            )
            return

        if strategy_id:
            strategy = self._strategy(strategy_id)
            result = poll_strategy(strategy, force=True)
        else:
            result = poll_all_research_strategies(force=True)
        self.stdout.write(str(result))

    def _strategy(self, strategy_id):
        if strategy_id:
            try:
                return Strategy.objects.get(pk=strategy_id)
            except Strategy.DoesNotExist as exc:
                raise CommandError(f"Strategy {strategy_id} not found") from exc
        strategy = Strategy.objects.filter(slug=STRATEGY_RESEARCH_BREAKTHROUGH).first()
        if strategy is None:
            raise CommandError("No Research / Breakthrough strategy. Run seed_trading first.")
        return strategy
