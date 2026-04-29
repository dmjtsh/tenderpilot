import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_tender(self, tender_id: int) -> None:
    """Детально обогащает тендер данными со страницы ЕИС."""
    from .models import Tender
    from .eis_client import fetch_tender_detail
    from .services import upsert_tender

    try:
        tender = Tender.objects.get(pk=tender_id)
    except Tender.DoesNotExist:
        logger.warning("Tender %d not found", tender_id)
        return

    detail = fetch_tender_detail(tender.number, tender.source_url)
    if not detail:
        logger.warning("No detail fetched for tender %s", tender.number)
        return

    detail["raw_json"] = detail.copy()
    upsert_tender(detail)
    logger.info("Enriched tender %s", tender.number)

    from apps.search.tasks import embed_tender
    embed_tender.delay(tender_id)
