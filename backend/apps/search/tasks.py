import logging
from celery import shared_task
from django.utils import timezone

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

    # Не индексируем неактивные тендеры — экономим память Qdrant
    if tender.status != Tender.Status.ACTIVE:
        logger.info("Skipping embed for non-active tender %d (status=%s)", tender_id, tender.status)
        return

    text = tender_text(tender)
    vector = embedder.embed_passages([text])[0]

    payload = {
        "number": tender.number,
        "title": tender.title,
        "nmck": float(tender.nmck) if tender.nmck else None,
        "customer_name": tender.customer.name if tender.customer else "",
        "region": tender.region,
        "law_type": tender.law_type,
        "status": tender.status,
        "published_at": tender.published_at.isoformat() if tender.published_at else None,
        "procedure_type": tender.procedure_type or "",
        "deadline_at_ts": int(tender.deadline_at.timestamp()) if tender.deadline_at else 0,
    }
    qdrant.upsert_tender(tender.pk, vector, payload)

    Tender.objects.filter(pk=tender_id).update(embedding_id=tender_id)
    logger.info("Embedded tender %s (id=%d)", tender.number, tender_id)


@shared_task(bind=True)
def rebuild_direction_vector(self, direction_id: int) -> str:
    from apps.users.models import CompanyDirection
    from .hyde import build_direction_vector

    try:
        direction = CompanyDirection.objects.select_related("profile").get(id=direction_id)
    except CompanyDirection.DoesNotExist:
        return "skip: direction not found"

    new_hash = direction.compute_content_hash()
    if new_hash == direction.content_hash and direction.profile_vector:
        return "skip: already up to date"

    try:
        final_vector, hyde_texts = build_direction_vector(direction)
    except Exception as exc:
        logger.error("HyDE failed for direction %d: %s", direction_id, exc)
        raise

    CompanyDirection.objects.filter(id=direction_id).update(
        hyde_texts=hyde_texts,
        profile_vector=final_vector,
        content_hash=new_hash,
        vector_updated_at=timezone.now(),
    )
    logger.info("Direction %d vector rebuilt", direction_id)
    return f"ok: direction {direction_id}"
