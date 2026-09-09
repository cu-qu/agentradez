import os

from celery.schedules import crontab

from celery import Celery

from trading.constants import RESEARCH_POLL_INTERVAL_SECONDS_MIN, X_POLL_INTERVAL_SECONDS_MIN

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("agentradez")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "process-new-signals": {
        "task": "trading.process_new_signals",
        "schedule": 15.0,
        "options": {"queue": "main"},
    },
    "poll-x-accounts": {
        "task": "trading.poll_x_accounts",
        "schedule": float(X_POLL_INTERVAL_SECONDS_MIN),
        "options": {"queue": "main"},
    },
    "poll-research-feeds": {
        "task": "trading.poll_research_feeds",
        "schedule": float(RESEARCH_POLL_INTERVAL_SECONDS_MIN),
        "options": {"queue": "main"},
    },
    "monitor-open-positions": {
        "task": "trading.monitor_open_positions",
        "schedule": 10.0,
        "options": {"queue": "main"},
    },
    "check-daily-loss-limits": {
        "task": "trading.check_daily_loss_limits",
        "schedule": 30.0,
        "options": {"queue": "main"},
    },
    "force-expiration-exits": {
        "task": "trading.force_expiration_exits",
        "schedule": 60.0,
        "options": {"queue": "main"},
    },
    "sync-broker-positions": {
        "task": "trading.sync_broker_positions",
        "schedule": 300.0,
        "options": {"queue": "main"},
    },
    "calculate-daily-performance": {
        "task": "trading.calculate_daily_performance",
        "schedule": crontab(hour=21, minute=5),
        "options": {"queue": "main"},
    },
    "reset-daily-flags": {
        "task": "trading.reset_daily_flags",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "main"},
    },
    "calculate-weekly-performance": {
        "task": "trading.calculate_weekly_performance",
        "schedule": crontab(hour=21, minute=30, day_of_week="fri"),
        "options": {"queue": "main"},
    },
    "reconcile-lifetime-pnl": {
        "task": "trading.reconcile_lifetime_pnl",
        "schedule": crontab(hour=22, minute=0),
        "options": {"queue": "main"},
    },
    "tier-usage-stats": {
        "task": "trading.tier_usage_stats",
        "schedule": crontab(minute=0),
        "options": {"queue": "main"},
    },
    "cleanup-old-signals-and-trades": {
        "task": "trading.cleanup_old_signals_and_trades",
        "schedule": crontab(hour=3, minute=0, day_of_week="sun"),
        "options": {"queue": "main"},
    },
}
