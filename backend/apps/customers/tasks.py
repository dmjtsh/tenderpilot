import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def enrich_customer_profile(self, inn: str) -> None:
    from apps.customers.services.enrichment import enrich_customer

    try:
        enrich_customer(inn)
    except Exception as exc:
        logger.error("enrich_customer_profile failed for %s: %s", inn, exc)
        raise self.retry(exc=exc)
