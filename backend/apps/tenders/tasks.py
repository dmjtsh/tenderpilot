import logging
import time
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

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


@shared_task(name="apps.tenders.tasks.sync_active_tenders")
def sync_active_tenders() -> dict:
    """
    Почасовая синхронизация активных тендеров с ЕИС.

    Что делает:
    1. Забирает тендеры опубликованные за последние 2 дня (перекрытие на случай задержек ЕИС)
    2. Делает upsert в БД (update_or_create по number)
    3. Ставит новые тендеры в очередь на enrich
    4. Помечает просроченные тендеры как FINISHED
    5. Удаляет тендеры старше KEEP_DAYS дней (если настроено)
    """
    from .models import Tender
    from .eis_client import search_tenders
    from .services import upsert_tender

    DELAY_BETWEEN_PAGES = 0.7   # сек между страницами (чтобы не банили)
    MAX_PAGES = 20               # лимит страниц за один запуск
    DAYS_LOOKBACK = 5            # смотрим за последние N дней (запас на простои ЕИС)

    stats = {"fetched": 0, "new": 0, "updated": 0, "expired": 0, "errors": 0}

    # --- 1. Забираем новые тендеры ---
    date_to = date.today()
    date_from = date_to - timedelta(days=DAYS_LOOKBACK)

    logger.info("sync_active_tenders: fetching %s → %s", date_from, date_to)

    existing_numbers = set(
        Tender.objects.filter(
            published_at__date__gte=date_from
        ).values_list("number", flat=True)
    )

    for page in range(1, MAX_PAGES + 1):
        try:
            results = search_tenders(
                date_from=date_from,
                date_to=date_to,
                page=page,
                fz44=True,
                fz223=True,
            )
        except Exception as exc:
            logger.error("sync_active_tenders: eis fetch error page=%d: %s", page, exc)
            stats["errors"] += 1
            break

        if not results:
            logger.info("sync_active_tenders: page %d empty, done", page)
            break

        for data in results:
            try:
                is_new = data["number"] not in existing_numbers
                data["raw_json"] = data.copy()
                tender = upsert_tender(data)
                stats["fetched"] += 1

                if is_new:
                    stats["new"] += 1
                    # Ставим в очередь на детальное обогащение
                    enrich_tender.apply_async(
                        args=[tender.pk],
                        countdown=5,  # небольшая задержка чтобы не перегружать ЕИС
                    )
                else:
                    stats["updated"] += 1

            except Exception as exc:
                logger.error(
                    "sync_active_tenders: upsert error number=%s: %s",
                    data.get("number", "?"), exc
                )
                stats["errors"] += 1

        if len(results) < 50:
            # Последняя страница — меньше записей чем RECORDS_PER_PAGE
            break

        if page < MAX_PAGES:
            time.sleep(DELAY_BETWEEN_PAGES)

    # --- 2. Помечаем просроченные тендеры как FINISHED и удаляем из Qdrant ---
    from apps.search.services import qdrant

    now = timezone.now()

    expired_ids = list(
        Tender.objects.filter(
            deadline_at__lt=now,
            deadline_at__isnull=False,
            status=Tender.Status.ACTIVE,
        ).values_list("pk", flat=True)
    )
    if expired_ids:
        Tender.objects.filter(pk__in=expired_ids).update(status=Tender.Status.FINISHED)
        for tender_id in expired_ids:
            try:
                qdrant.delete_tender(tender_id)
            except Exception as exc:
                logger.warning("qdrant delete_tender %d failed: %s", tender_id, exc)

    stats["expired"] = len(expired_ids)

    # --- 3. Тендеры без дедлайна, опубликованные > 180 дней назад ---
    old_ids = list(
        Tender.objects.filter(
            deadline_at__isnull=True,
            published_at__lt=now - timedelta(days=180),
            status=Tender.Status.ACTIVE,
        ).values_list("pk", flat=True)
    )
    if old_ids:
        Tender.objects.filter(pk__in=old_ids).update(status=Tender.Status.FINISHED)
        for tender_id in old_ids:
            try:
                qdrant.delete_tender(tender_id)
            except Exception as exc:
                logger.warning("qdrant delete_tender %d failed: %s", tender_id, exc)
        logger.info("sync_active_tenders: removed %d old no-deadline tenders from Qdrant", len(old_ids))

    logger.info(
        "sync_active_tenders done: fetched=%d new=%d updated=%d expired=%d errors=%d",
        stats["fetched"], stats["new"], stats["updated"], stats["expired"], stats["errors"],
    )
    return stats


@shared_task(name="apps.tenders.tasks.sync_bidzaar_tenders")
def sync_bidzaar_tenders() -> dict:
    """
    Почасовая синхронизация тендеров с Bidzaar B2B.

    Что делает:
    1. Забирает тендеры за последние 2 дня
    2. Делает upsert в БД
    3. Ставит новые тендеры в очередь на индексацию в Qdrant
    """
    from .models import Tender
    from .bidzaar_client import search_tenders, fetch_tender_detail
    from .services import upsert_tender
    from apps.search.tasks import embed_tender

    days = 2

    stats = {"fetched": 0, "new": 0, "updated": 0, "errors": 0}

    try:
        items = search_tenders(days=days, max_pages=20, active_only=True)
    except Exception as exc:
        logger.error("sync_bidzaar_tenders: search_tenders failed: %s", exc)
        return stats

    stats["fetched"] = len(items)
    logger.info("sync_bidzaar_tenders: fetched %d items", len(items))

    for data in items:
        bidzaar_id: str = data.pop("bidzaar_id", "")

        # Обогащение деталями (бюджет, ОКПД)
        if bidzaar_id:
            try:
                detail = fetch_tender_detail(bidzaar_id)
                if detail:
                    data["nmck"] = detail["nmck"]
                    data["okpd_codes"] = detail["okpd_codes"]
                    if detail.get("customer_inn"):
                        data["customer_inn"] = detail["customer_inn"]
                time.sleep(0.3)
            except Exception as exc:
                logger.warning("sync_bidzaar_tenders: enrich failed %s: %s", bidzaar_id, exc)

        try:
            data["raw_json"] = {k: v for k, v in data.items() if k != "raw_json"}
            number = data.get("number", "")
            existing_id = Tender.objects.filter(
                number=number, source=Tender.Source.BIDZAAR
            ).values_list("pk", flat=True).first()
            tender = upsert_tender(data)
            if existing_id is None:
                stats["new"] += 1
                embed_tender.delay(tender.pk)
            else:
                stats["updated"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.error("sync_bidzaar_tenders: upsert error %s: %s", data.get("number"), exc)

    logger.info(
        "sync_bidzaar_tenders done: fetched=%d new=%d updated=%d errors=%d",
        stats["fetched"], stats["new"], stats["updated"], stats["errors"],
    )
    return stats
