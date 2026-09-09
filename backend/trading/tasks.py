import logging

from celery import shared_task

from trading.services.jobs import (
    cleanup_old_signals_and_trades,
    reset_daily_flags,
    sync_broker_positions,
)
from trading.services.performance import (
    calculate_daily_performance,
    calculate_weekly_performance,
    reconcile_lifetime_pnl,
    tier_usage_stats,
)
from trading.services.position_manager import (
    check_daily_loss_limits,
    force_expiration_exits,
    monitor_open_positions,
)
from trading.services.research_watcher import poll_all_research_strategies
from trading.services.signal_engine import process_pending_signals
from trading.services.x_watcher import poll_all_sources

logger = logging.getLogger(__name__)


@shared_task(name="trading.process_new_signals", queue="main")
def process_new_signals():
    count = process_pending_signals()
    logger.info("process_new_signals processed=%s", count)
    return count


@shared_task(name="trading.poll_x_accounts", queue="main")
def poll_x_accounts():
    results = poll_all_sources()
    logger.info("poll_x_accounts results=%s", results)
    return results


@shared_task(name="trading.poll_research_feeds", queue="main")
def poll_research_feeds():
    results = poll_all_research_strategies()
    logger.info("poll_research_feeds results=%s", results)
    return results


@shared_task(name="trading.monitor_open_positions", queue="main")
def monitor_open_positions_task():
    count = monitor_open_positions()
    logger.info("monitor_open_positions count=%s", count)
    return count


@shared_task(name="trading.check_daily_loss_limits", queue="main")
def check_daily_loss_limits_task():
    paused = check_daily_loss_limits()
    logger.info("check_daily_loss_limits paused=%s", paused)
    return paused


@shared_task(name="trading.force_expiration_exits", queue="main")
def force_expiration_exits_task():
    closed = force_expiration_exits()
    logger.info("force_expiration_exits closed=%s", closed)
    return closed


@shared_task(name="trading.sync_broker_positions", queue="main")
def sync_broker_positions_task():
    synced = sync_broker_positions()
    logger.info("sync_broker_positions synced=%s", synced)
    return synced


@shared_task(name="trading.calculate_daily_performance", queue="main")
def calculate_daily_performance_task():
    written = calculate_daily_performance()
    logger.info("calculate_daily_performance snapshots=%s", written)
    return written


@shared_task(name="trading.reset_daily_flags", queue="main")
def reset_daily_flags_task():
    updated = reset_daily_flags()
    logger.info("reset_daily_flags updated=%s", updated)
    return updated


@shared_task(name="trading.calculate_weekly_performance", queue="main")
def calculate_weekly_performance_task():
    written = calculate_weekly_performance()
    logger.info("calculate_weekly_performance snapshots=%s", written)
    return written


@shared_task(name="trading.reconcile_lifetime_pnl", queue="main")
def reconcile_lifetime_pnl_task():
    result = reconcile_lifetime_pnl()
    logger.info("reconcile_lifetime_pnl %s", result)
    return result


@shared_task(name="trading.tier_usage_stats", queue="main")
def tier_usage_stats_task():
    result = tier_usage_stats()
    logger.info("tier_usage_stats %s", result)
    return result


@shared_task(name="trading.cleanup_old_signals_and_trades", queue="main")
def cleanup_old_signals_and_trades_task():
    result = cleanup_old_signals_and_trades()
    logger.info("cleanup_old_signals_and_trades %s", result)
    return result
