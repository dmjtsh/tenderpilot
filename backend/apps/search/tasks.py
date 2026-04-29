import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def embed_tender(self, tender_id: int) -> None:
    """Генерирует embedding для тендера и загружает в Qdrant."""
    from apps.tenders.models import Tender
    from .embedder import embedder, tender_text
    from .services import qdrant

    try:
        tender = Tender.objects.select_related("customer").get(pk=tender_id)
    except Tender.DoesNotExist:
        logger.warning("Tender %d not found", tender_id)
        return

    text = tender_text(
        title=tender.title,
        okpd_codes=tender.okpd_codes,
        customer_name=tender.customer.name if tender.customer else "",
    )
    vector = embedder.embed_passages([text])[0]

    payload = {
        "number": tender.number,
        "title": tender.title,
        "nmck": float(tender.nmck) if tender.nmck else None,
        "customer_name": tender.customer.name if tender.customer else "",
        "region": tender.region,
        "status": tender.status,
        "published_at": tender.published_at.isoformat() if tender.published_at else None,
    }
    qdrant.upsert_tender(tender.pk, vector, payload)

    Tender.objects.filter(pk=tender_id).update(embedding_id=tender_id)
    logger.info("Embedded tender %s (id=%d)", tender.number, tender_id)
