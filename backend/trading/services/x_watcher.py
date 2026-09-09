"""Poll a watched X account and turn parsed trades into pending signals."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from trading.constants import SOURCE_X
from trading.models import IngestedPost, Signal, XAccountSource
from trading.services.signal_engine import process_signal
from trading.services.x_client import XApiError, XClient, XTweet, format_x_api_error, get_x_client
from trading.services.x_trade_parser import ParsedTrade, parse_trades

logger = logging.getLogger(__name__)


def _is_stale(posted_at: datetime | None, lookback_hours: int) -> bool:
    if posted_at is None:
        return False
    cutoff = timezone.now() - timedelta(hours=lookback_hours)
    if timezone.is_naive(posted_at):
        posted_at = timezone.make_aware(posted_at, timezone=timezone.utc)
    return posted_at < cutoff


def _is_due(source: XAccountSource) -> bool:
    if source.last_polled_at is None:
        return True
    elapsed = (timezone.now() - source.last_polled_at).total_seconds()
    return elapsed >= source.poll_interval_seconds


def _x_api_backoff(source: XAccountSource) -> bool:
    """Skip live polls for a bit after X rejects the token or runs out of credits."""
    err = (source.last_error or "").lower()
    if not any(token in err for token in ("unauthorized", "credits depleted", "x api 401", "x api 402")):
        return False
    if source.last_polled_at is None:
        return False
    return timezone.now() - source.last_polled_at < timedelta(minutes=15)


def _create_signal(
    source: XAccountSource,
    post: IngestedPost,
    trade: ParsedTrade,
    historical: bool = False,
) -> Signal | None:
    existing = Signal.objects.filter(
        ingested_post=post,
        ticker=trade.ticker,
        option_type=trade.option_type,
        strike=trade.strike,
        expiration=trade.expiration,
    ).first()
    if existing:
        return None
    notes = (trade.notes or "")[:255]
    extras: dict = {}
    if historical:
        extra = "Lookback ingest; not auto-traded."
        notes = f"{notes} {extra}".strip()[:255]
        extras["status"] = Signal.Status.PROCESSED
        extras["processed_at"] = timezone.now()
    try:
        with transaction.atomic():
            return Signal.objects.create(
                strategy=source.strategy,
                ticker=trade.ticker,
                option_type=trade.option_type,
                strike=trade.strike,
                expiration=trade.expiration,
                suggested_entry_price=trade.entry_price,
                quote_price=trade.entry_price,
                notes=notes,
                source=f"{SOURCE_X}:@{source.handle}/{post.tweet_id}",
                ingested_post=post,
                **extras,
            )
    except IntegrityError:
        return None


def ingest_tweet(
    source: XAccountSource,
    tweet_id: str,
    text: str,
    posted_at: datetime | None = None,
    process: bool = True,
    ignore_lookback: bool = False,
) -> IngestedPost:
    post, _signals, _duplicate = ingest_tweet_result(
        source,
        tweet_id=tweet_id,
        text=text,
        posted_at=posted_at,
        process=process,
        ignore_lookback=ignore_lookback,
    )
    return post


@transaction.atomic
def ingest_tweet_result(
    source: XAccountSource,
    tweet_id: str,
    text: str,
    posted_at: datetime | None = None,
    process: bool = True,
    ignore_lookback: bool = False,
    historical: bool = False,
) -> tuple[IngestedPost, list[Signal], bool]:
    post, created = IngestedPost.objects.select_for_update().get_or_create(
        source=source,
        tweet_id=str(tweet_id),
        defaults={"text": text, "posted_at": posted_at},
    )
    already_parsed = post.parse_status in (
        IngestedPost.ParseStatus.PARSED,
        IngestedPost.ParseStatus.NO_TRADE,
    )
    if not created and already_parsed:
        return post, [], True

    post.text = text
    post.posted_at = posted_at or post.posted_at

    if not ignore_lookback and _is_stale(posted_at, source.lookback_hours):
        post.parse_status = IngestedPost.ParseStatus.SKIPPED
        post.skip_reason = f"Older than {source.lookback_hours}h lookback"
        post.parsed_trades = []
        post.save(
            update_fields=[
                "text",
                "posted_at",
                "parse_status",
                "skip_reason",
                "parsed_trades",
                "updated_at",
            ]
        )
        return post, [], False

    try:
        trades = parse_trades(text, posted_at=posted_at)
    except Exception as exc:  # pragma: no cover - parser should not raise
        logger.exception("Failed to parse tweet %s", tweet_id)
        post.parse_status = IngestedPost.ParseStatus.ERROR
        post.skip_reason = str(exc)[:255]
        post.save(update_fields=["text", "posted_at", "parse_status", "skip_reason", "updated_at"])
        return post, [], False

    post.parsed_trades = [trade.as_dict() for trade in trades]
    entries = [trade for trade in trades if not trade.is_exit]
    if not entries:
        post.parse_status = IngestedPost.ParseStatus.NO_TRADE
        post.skip_reason = "No entry trades found" if not trades else "Exit-only post"
        post.save(
            update_fields=[
                "text",
                "posted_at",
                "parse_status",
                "skip_reason",
                "parsed_trades",
                "updated_at",
            ]
        )
        return post, [], False

    created_signals: list[Signal] = []
    for trade in entries:
        signal = _create_signal(source, post, trade, historical=historical)
        if signal:
            created_signals.append(signal)

    post.parse_status = IngestedPost.ParseStatus.PARSED
    post.skip_reason = ""
    post.save(
        update_fields=[
            "text",
            "posted_at",
            "parse_status",
            "skip_reason",
            "parsed_trades",
            "updated_at",
        ]
    )

    if process and not historical:
        for signal in created_signals:
            process_signal(signal)
    return post, created_signals, False


def ingest_xtweet(
    source: XAccountSource,
    tweet: XTweet,
    process: bool = True,
    ignore_lookback: bool = False,
) -> IngestedPost:
    return ingest_tweet(
        source,
        tweet_id=tweet.id,
        text=tweet.text,
        posted_at=tweet.created_at,
        process=process,
        ignore_lookback=ignore_lookback,
    )


def poll_source(
    source: XAccountSource,
    client: XClient | None = None,
    force: bool = False,
) -> dict:
    if not source.is_active:
        return {"source_id": source.id, "skipped": True, "reason": "inactive"}
    if not force and _x_api_backoff(source):
        return {"source_id": source.id, "skipped": True, "reason": "x_api_backoff"}
    if not force and not _is_due(source):
        return {"source_id": source.id, "skipped": True, "reason": "not_due"}

    client = client or get_x_client()
    if client is None:
        source.last_error = "X_BEARER_TOKEN is not configured"
        source.last_polled_at = timezone.now()
        source.save(update_fields=["last_error", "last_polled_at", "updated_at"])
        return {"source_id": source.id, "skipped": True, "reason": source.last_error}

    try:
        if not source.x_user_id:
            user = client.lookup_user(source.handle)
            source.x_user_id = user.id
            if not source.display_name:
                source.display_name = user.name or user.username
            source.save(update_fields=["x_user_id", "display_name", "updated_at"])
        tweets = client.user_tweets(
            source.x_user_id,
            since_id=source.last_tweet_id or None,
            max_results=20,
        )
    except XApiError as exc:
        source.last_error = format_x_api_error(exc)
        source.last_polled_at = timezone.now()
        source.save(update_fields=["last_error", "last_polled_at", "updated_at"])
        logger.warning("X poll failed for @%s: %s", source.handle, exc)
        return {"source_id": source.id, "error": source.last_error}

    # API returns newest first; process oldest first so last_tweet_id advances in order.
    ingested = 0
    signals = 0
    for tweet in reversed(tweets):
        post = ingest_xtweet(source, tweet)
        ingested += 1
        signals += post.signals.count()
        if not source.last_tweet_id or int(tweet.id) > int(source.last_tweet_id):
            source.last_tweet_id = tweet.id

    source.last_error = ""
    source.last_polled_at = timezone.now()
    source.save(update_fields=["last_tweet_id", "last_error", "last_polled_at", "updated_at"])
    return {
        "source_id": source.id,
        "handle": source.handle,
        "tweets": ingested,
        "signals": signals,
    }


def poll_all_sources(client: XClient | None = None) -> list[dict]:
    results = []
    for source in XAccountSource.objects.filter(is_active=True).select_related("strategy"):
        results.append(poll_source(source, client=client))
    return results


def lookback_source(
    source: XAccountSource,
    days: int = 30,
    client: XClient | None = None,
) -> dict:
    days = max(1, min(int(days), 90))
    start = timezone.now() - timedelta(days=days)
    result = {
        "source_id": source.id,
        "handle": source.handle,
        "days": days,
        "tweets_seen": 0,
        "tweets_ingested": 0,
        "tweets_duplicate": 0,
        "signals_created": 0,
    }
    client = client or get_x_client()
    if client is None:
        source.last_error = "X_BEARER_TOKEN is not configured"
        source.save(update_fields=["last_error", "updated_at"])
        result["error"] = source.last_error
        return result

    try:
        if not source.x_user_id:
            user = client.lookup_user(source.handle)
            source.x_user_id = user.id
            if not source.display_name:
                source.display_name = user.name or user.username
            source.save(update_fields=["x_user_id", "display_name", "updated_at"])
        if hasattr(client, "iter_user_tweets"):
            tweets = client.iter_user_tweets(source.x_user_id, start_time=start)
        else:
            tweets = client.user_tweets(source.x_user_id, max_results=100, start_time=start)
    except XApiError as exc:
        source.last_error = format_x_api_error(exc)
        source.save(update_fields=["last_error", "updated_at"])
        result["error"] = source.last_error
        return result

    newest_id = source.last_tweet_id or ""
    try:
        for tweet in tweets:
            result["tweets_seen"] += 1
            if tweet.created_at and tweet.created_at < start:
                continue
            _post, created_signals, duplicate = ingest_tweet_result(
                source,
                tweet_id=tweet.id,
                text=tweet.text,
                posted_at=tweet.created_at,
                process=True,
                ignore_lookback=True,
                historical=_is_stale(tweet.created_at, source.lookback_hours),
            )
            if duplicate:
                result["tweets_duplicate"] += 1
            else:
                result["tweets_ingested"] += 1
            result["signals_created"] += len(created_signals)
            if not newest_id or int(tweet.id) > int(newest_id):
                newest_id = tweet.id
    except XApiError as exc:
        source.last_error = format_x_api_error(exc)
        source.last_tweet_id = newest_id
        source.last_polled_at = timezone.now()
        source.save(update_fields=["last_error", "last_tweet_id", "last_polled_at", "updated_at"])
        result["error"] = source.last_error
        return result

    source.last_error = ""
    if newest_id:
        source.last_tweet_id = newest_id
    source.last_polled_at = timezone.now()
    source.save(update_fields=["last_tweet_id", "last_error", "last_polled_at", "updated_at"])
    return result
