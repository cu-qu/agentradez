"""Hit the X API with the configured client and print the raw responses.

Does not ingest posts or create signals. Uses the connected strategy's X
watcher by default (or --handle / --source-id / --strategy-id).
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from trading.models import XAccountSource
from trading.services.x_client import XApiError, get_x_client
from trading.services.x_trade_parser import parse_trades


def _dump(value) -> str:
    return json.dumps(value, indent=2, default=str)


class Command(BaseCommand):
    help = "Call the configured X client and print user/tweet API responses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--handle",
            help="X username to fetch. Defaults to the connected strategy watcher.",
        )
        parser.add_argument("--source-id", type=int, help="Use this XAccountSource.")
        parser.add_argument("--strategy-id", type=int, help="Use this strategy's X watcher.")
        parser.add_argument(
            "--max-results",
            type=int,
            default=10,
            help="Tweets to request (5–100). Default 10.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all_sources",
            help="Probe every active X watcher.",
        )
        parser.add_argument(
            "--no-parse",
            action="store_true",
            help="Skip option-trade parsing of tweet text.",
        )

    def handle(self, *args, **options):
        client = get_x_client()
        self._print_client(client)
        if client is None:
            raise CommandError(
                "X client is not configured. Set X_PULLCALLS_BEARER_TOKEN or X_BEARER_TOKEN."
            )

        sources = self._sources(options)
        if sources:
            for source in sources:
                self._probe_source(client, source, options)
            return

        handle = (options.get("handle") or getattr(settings, "X_COPY_TRADE_HANDLE", "") or "").strip()
        if not handle:
            raise CommandError(
                "No connected X watcher found. Pass --handle, or create a strategy X source."
            )
        self._probe_handle(client, handle, options)

    def _print_client(self, client) -> None:
        pull = bool(getattr(settings, "X_PULLCALLS_BEARER_TOKEN", ""))
        bearer = bool(getattr(settings, "X_BEARER_TOKEN", ""))
        if pull:
            token_source = "X_PULLCALLS_BEARER_TOKEN"
        elif bearer:
            token_source = "X_BEARER_TOKEN"
        else:
            token_source = "(none)"
        self.stdout.write("=== X client ===")
        self.stdout.write(
            _dump(
                {
                    "configured": client is not None,
                    "base_url": getattr(client, "base_url", getattr(settings, "X_API_BASE_URL", "")),
                    "token_source": token_source,
                    "consumer_key_set": bool(getattr(settings, "X_PULLCALLS_API_CONSUMER_KEY", "")),
                }
            )
        )
        self.stdout.write("")

    def _sources(self, options) -> list[XAccountSource]:
        qs = XAccountSource.objects.select_related("strategy").order_by("id")
        if options.get("source_id"):
            try:
                return [qs.get(pk=options["source_id"])]
            except XAccountSource.DoesNotExist as exc:
                raise CommandError(f"X watcher {options['source_id']} not found") from exc
        if options.get("strategy_id"):
            rows = list(qs.filter(strategy_id=options["strategy_id"]))
            if not rows:
                raise CommandError(
                    f"No X watcher on strategy {options['strategy_id']}"
                )
            return rows
        if options.get("handle"):
            return []
        if options.get("all_sources"):
            return list(qs.filter(is_active=True))
        source = qs.filter(is_active=True).first() or qs.first()
        return [source] if source else []

    def _probe_source(self, client, source: XAccountSource, options) -> None:
        strategy = source.strategy
        self.stdout.write("=== Connected strategy ===")
        self.stdout.write(
            _dump(
                {
                    "strategy_id": strategy.id,
                    "strategy_name": strategy.name,
                    "strategy_slug": strategy.slug,
                    "strategy_type": strategy.strategy_type,
                    "source_id": source.id,
                    "handle": source.handle,
                    "display_name": source.display_name,
                    "x_user_id": source.x_user_id,
                    "is_active": source.is_active,
                    "lookback_hours": source.lookback_hours,
                    "poll_interval_seconds": source.poll_interval_seconds,
                    "last_tweet_id": source.last_tweet_id,
                    "last_polled_at": source.last_polled_at,
                    "last_error": source.last_error,
                }
            )
        )
        self.stdout.write("")
        self._probe_handle(client, source.handle, options, x_user_id=source.x_user_id or None)

    def _probe_handle(self, client, handle: str, options, x_user_id: str | None = None) -> None:
        handle = handle.lstrip("@").strip()
        self.stdout.write(f"=== GET /users/by/username/{handle} ===")
        try:
            user_payload = client._get(f"/users/by/username/{handle}")
        except XApiError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        self.stdout.write(_dump(user_payload))
        self.stdout.write("")

        user_id = (user_payload.get("data") or {}).get("id") or x_user_id
        if not user_id:
            self.stderr.write(self.style.ERROR(f"X user @{handle} has no id in the response"))
            return

        max_results = max(5, min(int(options["max_results"]), 100))
        params = {
            "max_results": max_results,
            "tweet.fields": "created_at,text,note_tweet",
            "exclude": "retweets,replies",
        }
        self.stdout.write(f"=== GET /users/{user_id}/tweets ===")
        try:
            tweets_payload = client._get(f"/users/{user_id}/tweets", params=params)
        except XApiError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        self.stdout.write(_dump(tweets_payload))
        self.stdout.write("")

        if options.get("no_parse"):
            return

        rows = []
        for item in tweets_payload.get("data") or []:
            note = (item.get("note_tweet") or {}).get("text")
            text = note or item.get("text") or ""
            posted_at = parse_datetime(item["created_at"]) if item.get("created_at") else None
            trades = [trade.as_dict() for trade in parse_trades(text, posted_at)]
            rows.append(
                {
                    "id": item.get("id"),
                    "created_at": item.get("created_at"),
                    "text": text,
                    "parsed_trades": trades,
                }
            )
        self.stdout.write("=== Parsed tweets (strategy parser, not ingested) ===")
        self.stdout.write(_dump(rows if rows else {"tweets": 0, "note": "API returned no tweets"}))
        self.stdout.write("")
