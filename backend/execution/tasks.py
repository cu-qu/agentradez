import logging

from celery import shared_task

from execution.services.rules_engine import evaluate_all_signals

logger = logging.getLogger(__name__)


@shared_task(name="execution.evaluate_harness_rules", queue="main")
def evaluate_harness_rules():
    count = evaluate_all_signals()
    logger.info("evaluate_harness_rules evaluated=%s", count)
    return count
