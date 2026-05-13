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

    if tender.source == Tender.Source.BIDZAAR:
        logger.debug("Skip bidzaar tender %s", tender.number)
        return

    from apps.alerts.services import log_pipeline_run

    started_at = timezone.now()
    detail = fetch_tender_detail(tender.number, tender.source_url)
    if not detail:
        logger.warning(
            "No detail for tender %s (attempt %d/%d)",
            tender.number, self.request.retries + 1, self.max_retries + 1,
        )
        try:
            raise self.retry(exc=Exception(f"Empty detail for {tender.number}"))
        except self.MaxRetriesExceededError:
            Tender.objects.filter(pk=tender_id).update(enriched_at=timezone.now())
            logger.error("Enrichment failed after retries: %s", tender.number)
            log_pipeline_run(
                task_name="enrich_tender",
                started_at=started_at,
                stats={"tender_id": tender_id, "number": tender.number},
                status="failed",
                error_message=f"Empty detail after {self.max_retries + 1} attempts",
            )
            return

    detail["raw_json"] = detail.copy()
    upsert_tender(detail)
    Tender.objects.filter(pk=tender_id).update(enriched_at=timezone.now())
    logger.info("Enriched tender %s", tender.number)
    log_pipeline_run(
        task_name="enrich_tender",
        started_at=started_at,
        stats={"tender_id": tender_id, "number": tender.number},
        status="ok",
    )

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

    start_time = timezone.now()
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

    from apps.alerts.services import log_pipeline_run

    if stats["fetched"] == 0 and stats["errors"] > 0:
        sync_status = "failed"
    elif stats["errors"] > 0:
        sync_status = "partial"
    else:
        sync_status = "ok"
    log_pipeline_run(
        task_name="sync_active_tenders",
        started_at=start_time,
        stats=stats,
        status=sync_status,
    )

    return stats


