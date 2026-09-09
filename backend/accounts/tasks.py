import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="accounts.ping", queue="main")
def ping():
    """Example no-op task so Celery autodiscover has something to find."""
    logger.info("accounts.ping")
    return "pong"
