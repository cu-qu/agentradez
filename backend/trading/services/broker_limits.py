"""Pause broker calls after rate limits and gateway failures.

Overlapping monitor tasks were retrying the same Robinhood order refresh and
fill import many times a second. A shared cache pause and a single reconcile
lock keep one failure from turning into a request storm.
"""

from __future__ import annotations

from django.core.cache import cache

RETRYABLE_MARKERS = (
    "rate_limited",
    "too many requests",
    "429",
    "502",
    "503",
    "504",
    "connection aborted",
    "connection reset",
    "transport endpoint is not connected",
)

COOLDOWN_SECONDS = 60
RECONCILE_LOCK = "trading:reconcile_working_orders"
RECONCILE_LOCK_SECONDS = 90


def is_retryable_broker_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in RETRYABLE_MARKERS)


def _cooldown_key(connection_id: int) -> str:
    return f"trading:broker:cooldown:{connection_id}"


def broker_paused(connection_id: int) -> bool:
    return cache.get(_cooldown_key(connection_id)) is not None


def pause_broker(connection_id: int, exc: BaseException) -> bool:
    if not is_retryable_broker_error(exc):
        return False
    cache.set(_cooldown_key(connection_id), "1", COOLDOWN_SECONDS)
    return True


def claim_reconcile_lock() -> bool:
    return bool(cache.add(RECONCILE_LOCK, "1", RECONCILE_LOCK_SECONDS))


def release_reconcile_lock() -> None:
    cache.delete(RECONCILE_LOCK)
