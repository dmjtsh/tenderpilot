import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def process_renewals() -> None:
    from .services import process_renewals as _process
    count = _process()
    logger.info("Processed %d renewals", count)


@shared_task
def expire_canceled_subscriptions() -> None:
    from .services import expire_canceled_subscriptions as _expire
    count = _expire()
    logger.info("Expired %d canceled subscriptions", count)
