"""Ingest company research headlines and turn catalysts into option signals."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from trading.constants import (
    DIR_UNKNOWN,
    EVENT_OTHER,
    RESEARCH_CATALYST,
    RESEARCH_ERROR,
    RESEARCH_NOISE,
    RESEARCH_PENDING,
    RESEARCH_SKIPPED,
    SOURCE_MANUAL,
    SOURCE_RESEARCH,
    STRATEGY_TYPE_RESEARCH_BREAKTHROUGH,
)
from trading.models import (
    ResearchEvent,
    ResearchWatchConfig,
    Signal,
    Strategy,
    WatchedCompany,
)
from trading.services.market_data import MarketDataError, UnderlyingSnapshot, fetch_option_snapshot
from trading.services.option_selector import ContractSelectionError, select_contract
from trading.services.research_classifier import CompanyRef, classify_text
from trading.services.research_feeds import FeedItem, fetch_google_news, fetch_rss
from trading.services.signal_engine import process_signal

logger = logging.getLogger(__name__)


def _company_ref(company: WatchedCompany) -> CompanyRef:
    aliases = company.aliases if isinstance(company.aliases, list) else []
    return CompanyRef(ticker=company.ticker, name=company.name, aliases=aliases)


def get_or_create_config(strategy: Strategy) -> ResearchWatchConfig:
    config, _ = ResearchWatchConfig.objects.get_or_create(strategy=strategy)
    return config


def active_companies(strategy: Strategy, config: ResearchWatchConfig | None = None) -> list[WatchedCompany]:
    config = config or get_or_create_config(strategy)
    queryset = strategy.watched_companies.filter(is_active=True)
    sectors = config.normalized_sectors()
    if sectors:
        sector_q = Q()
        for sector in sectors:
            sector_q |= Q(sector__iexact=sector)
        queryset = queryset.filter(sector_q)
    return list(queryset)


def _is_due(config: ResearchWatchConfig) -> bool:
    if config.last_polled_at is None:
        return True
    elapsed = (timezone.now() - config.last_polled_at).total_seconds()
    return elapsed >= config.poll_interval_seconds


def _is_stale(published_at: datetime | None, lookback_hours: int) -> bool:
    if published_at is None:
        return False
    cutoff = timezone.now() - timedelta(hours=lookback_hours)
    if timezone.is_naive(published_at):
        published_at = timezone.make_aware(published_at, timezone=timezone.utc)
    return published_at < cutoff


def _cooldown_active(strategy: Strategy, ticker: str, hours: int) -> bool:
    if hours <= 0:
        return False
    cutoff = timezone.now() - timedelta(hours=hours)
    return Signal.objects.filter(
        strategy=strategy,
        ticker=ticker.upper(),
        research_event__isnull=False,
        created_at__gte=cutoff,
    ).exists()


def _fetch_snapshot(ticker: str, snapshot_loader=None) -> UnderlyingSnapshot:
    loader = snapshot_loader or fetch_option_snapshot
    return loader(ticker)


def _create_signal(event: ResearchEvent, contract, historical: bool = False) -> Signal | None:
    existing = Signal.objects.filter(research_event=event).first()
    if existing:
        return None
    extras: dict = {}
    notes = (contract.notes or event.headline)[:255]
    if historical:
        extra = "Lookback ingest; not auto-traded."
        notes = f"{notes} {extra}".strip()[:255]
        extras["status"] = Signal.Status.PROCESSED
        extras["processed_at"] = timezone.now()
    try:
        with transaction.atomic():
            return Signal.objects.create(
                strategy=event.strategy,
                ticker=contract.ticker,
                option_type=contract.option_type,
                strike=contract.strike,
                expiration=contract.expiration,
                suggested_entry_price=contract.entry_price,
                quote_price=contract.entry_price,
                notes=notes,
                source=f"{SOURCE_RESEARCH}:{event.source}/{event.pk}",
                research_event=event,
                **extras,
            )
    except IntegrityError:
        return None


@transaction.atomic
def ingest_feed_item(
    strategy: Strategy,
    item: FeedItem,
    companies: list[WatchedCompany] | None = None,
    process: bool = True,
    ignore_lookback: bool = False,
    historical: bool = False,
    snapshot_loader=None,
) -> tuple[list[ResearchEvent], list[Signal]]:
    config = get_or_create_config(strategy)
    companies = companies if companies is not None else active_companies(strategy, config)
    refs = [_company_ref(row) for row in companies]
    company_by_ticker = {row.ticker.upper(): row for row in companies}

    if not ignore_lookback and _is_stale(item.published_at, config.lookback_hours):
        event, _ = ResearchEvent.objects.select_for_update().get_or_create(
            strategy=strategy,
            external_id=item.external_id[:128],
            defaults={
                "source": item.source,
                "source_url": item.url,
                "headline": item.headline[:512],
                "summary": item.summary,
                "published_at": item.published_at,
                "status": RESEARCH_SKIPPED,
                "skip_reason": f"Older than {config.lookback_hours}h lookback",
            },
        )
        return [event], []

    classifications = classify_text(
        item.headline,
        item.summary,
        refs,
        enabled_event_types=config.allowed_event_types(),
        require_confirmation=config.require_confirmation,
    )
    created_events: list[ResearchEvent] = []
    created_signals: list[Signal] = []

    for classification in classifications:
        external_id = item.external_id[:128]
        if len(classifications) > 1 and classification.ticker:
            suffix = f":{classification.ticker.lower()}"
            external_id = f"{external_id[:128 - len(suffix)]}{suffix}"
        company = company_by_ticker.get(classification.ticker.upper()) if classification.ticker else None
        event, created = ResearchEvent.objects.select_for_update().get_or_create(
            strategy=strategy,
            external_id=external_id,
            defaults={
                "company": company,
                "source": item.source,
                "source_url": item.url,
                "headline": item.headline[:512],
                "summary": item.summary,
                "published_at": item.published_at,
                "status": RESEARCH_PENDING,
            },
        )
        if not created and event.status in {RESEARCH_CATALYST, RESEARCH_NOISE, RESEARCH_SKIPPED}:
            created_events.append(event)
            continue

        event.company = company
        event.source = item.source
        event.source_url = item.url
        event.headline = item.headline[:512]
        event.summary = item.summary
        event.published_at = item.published_at or event.published_at
        event.event_type = classification.event_type or EVENT_OTHER
        event.direction = classification.direction or DIR_UNKNOWN
        event.score = classification.score
        event.rationale = classification.rationale[:255]

        if not classification.is_catalyst or classification.score < config.min_catalyst_score:
            event.status = RESEARCH_NOISE
            event.skip_reason = (
                classification.rationale if not classification.is_catalyst else "Score below threshold"
            )[:255]
            event.option_suggestion = {}
            event.save()
            created_events.append(event)
            continue

        ticker = classification.ticker or (company.ticker if company else "")
        if not ticker:
            event.status = RESEARCH_SKIPPED
            event.skip_reason = "Catalyst without a ticker"
            event.save()
            created_events.append(event)
            continue

        if _cooldown_active(strategy, ticker, config.signal_cooldown_hours):
            event.status = RESEARCH_SKIPPED
            event.skip_reason = f"{ticker} signal cooldown ({config.signal_cooldown_hours}h)"
            event.save()
            created_events.append(event)
            continue

        try:
            snapshot = _fetch_snapshot(ticker, snapshot_loader=snapshot_loader)
            contract = select_contract(
                snapshot,
                classification.direction,
                otm_pct=config.otm_pct,
                min_dte=config.min_dte,
                max_dte=config.max_dte,
            )
        except (MarketDataError, ContractSelectionError) as exc:
            event.status = RESEARCH_ERROR
            event.skip_reason = str(exc)[:255]
            event.save()
            created_events.append(event)
            continue

        event.status = RESEARCH_CATALYST
        event.skip_reason = ""
        event.option_suggestion = contract.as_dict()
        event.save()
        created_events.append(event)

        signal = _create_signal(event, contract, historical=historical)
        if signal:
            created_signals.append(signal)
            if process and not historical:
                process_signal(signal)

    return created_events, created_signals


def ingest_headline(
    strategy: Strategy,
    headline: str,
    summary: str = "",
    source: str = SOURCE_MANUAL,
    source_url: str = "",
    published_at: datetime | None = None,
    process: bool = True,
    snapshot_loader=None,
) -> tuple[list[ResearchEvent], list[Signal]]:
    raw = (source_url or f"manual:{headline}|{summary}").encode("utf-8")
    item = FeedItem(
        external_id=hashlib.sha256(raw).hexdigest()[:32],
        headline=headline,
        summary=summary,
        url=source_url,
        published_at=published_at or timezone.now(),
        source=source,
    )
    return ingest_feed_item(
        strategy,
        item,
        process=process,
        ignore_lookback=True,
        snapshot_loader=snapshot_loader,
    )


def _collect_items(strategy: Strategy, config: ResearchWatchConfig) -> list[FeedItem]:
    items: list[FeedItem] = []
    seen: set[str] = set()
    companies = active_companies(strategy, config)
    keywords = config.search_keywords()
    for company in companies:
        try:
            fetched = fetch_google_news(
                company.ticker,
                company.name,
                lookback_hours=config.lookback_hours,
                keywords=keywords,
            )
        except Exception as exc:  # noqa: BLE001 — keep remaining tickers polling
            logger.warning("Google News failed for %s: %s", company.ticker, exc)
            fetched = []
        if company.rss_url:
            try:
                fetched.extend(fetch_rss(company.rss_url, source="rss"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("RSS failed for %s: %s", company.ticker, exc)
        for item in fetched:
            if item.external_id in seen:
                continue
            seen.add(item.external_id)
            items.append(item)
    return items


def poll_strategy(
    strategy: Strategy,
    force: bool = False,
    process: bool = True,
    snapshot_loader=None,
) -> dict:
    if strategy.strategy_type != STRATEGY_TYPE_RESEARCH_BREAKTHROUGH:
        return {"strategy_id": strategy.id, "skipped": True, "reason": "wrong_type"}
    if not strategy.is_active:
        return {"strategy_id": strategy.id, "skipped": True, "reason": "inactive"}
    config = get_or_create_config(strategy)
    if not force and not _is_due(config):
        return {"strategy_id": strategy.id, "skipped": True, "reason": "not_due"}

    try:
        items = _collect_items(strategy, config)
    except Exception as exc:  # noqa: BLE001
        config.last_error = str(exc)[:255]
        config.last_polled_at = timezone.now()
        config.save(update_fields=["last_error", "last_polled_at", "updated_at"])
        return {"strategy_id": strategy.id, "error": config.last_error}

    events = 0
    signals = 0
    companies = active_companies(strategy, config)
    for item in items:
        created_events, created_signals = ingest_feed_item(
            strategy,
            item,
            companies=companies,
            process=process,
            snapshot_loader=snapshot_loader,
        )
        events += len(created_events)
        signals += len(created_signals)

    config.last_error = ""
    config.last_polled_at = timezone.now()
    config.save(update_fields=["last_error", "last_polled_at", "updated_at"])
    return {
        "strategy_id": strategy.id,
        "headlines": len(items),
        "events": events,
        "signals": signals,
    }


def poll_all_research_strategies(force: bool = False) -> list[dict]:
    results = []
    queryset = Strategy.objects.filter(
        is_active=True, strategy_type=STRATEGY_TYPE_RESEARCH_BREAKTHROUGH
    )
    for strategy in queryset:
        results.append(poll_strategy(strategy, force=force))
    return results
