import logging
import time
from datetime import date, timedelta

from celery import shared_task
from django.db.models import Q
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


DELAY_BETWEEN_PAGES = 0.7
DAYS_LOOKBACK = 5
MAX_PAGES_PER_PASS = 110
STOP_AFTER = 3
MIN_PAGES = 3
TRUNCATION_THRESHOLD = 100

FZ44_PRICE_RANGES: list[tuple[str, str | None, str | None]] = [
    ("≤100к",     None,      "100000"),
    ("100к-500к", "100001",  "500000"),
    ("500к-1млн", "500001",  "1000000"),
    ("1-5млн",    "1000001", "5000000"),
    ("5млн+",     "5000001", None),
]


def _fetch_pass(
    search_tenders_fn,
    upsert_fn,
    date_from: date,
    date_to: date,
    fz44: bool,
    fz223: bool,
    price_from: str | None,
    price_to: str | None,
    existing_numbers: set[str],
) -> dict:
    """Один проход пагинации с smart stopping. Мутирует existing_numbers."""
    pass_stats = {"fetched": 0, "new": 0, "pages": 0, "errors": 0, "truncated": False}
    consecutive_no_new = 0
    new_tender_pks: list[int] = []

    for page in range(1, MAX_PAGES_PER_PASS + 1):
        try:
            results = search_tenders_fn(
                date_from=date_from,
                date_to=date_to,
                page=page,
                fz44=fz44,
                fz223=fz223,
                price_from=price_from,
                price_to=price_to,
            )
        except Exception as exc:
            logger.error("sync fetch error page=%d: %s", page, exc)
            pass_stats["errors"] += 1
            break

        if not results:
            break

        pass_stats["pages"] = page
        page_new = 0
        for data in results:
            try:
                is_new = data["number"] not in existing_numbers
                data["raw_json"] = data.copy()
                tender = upsert_fn(data)
                pass_stats["fetched"] += 1
                if is_new:
                    page_new += 1
                    pass_stats["new"] += 1
                    existing_numbers.add(data["number"])
                    new_tender_pks.append(tender.pk)
            except Exception as exc:
                logger.error("sync upsert error %s: %s", data.get("number", "?"), exc)
                pass_stats["errors"] += 1

        if page >= MIN_PAGES:
            if page_new == 0:
                consecutive_no_new += 1
                if consecutive_no_new >= STOP_AFTER:
                    break
            else:
                consecutive_no_new = 0

        if len(results) < 50:
            break

        if page < MAX_PAGES_PER_PASS:
            time.sleep(DELAY_BETWEEN_PAGES)

    pass_stats["truncated"] = pass_stats["pages"] >= TRUNCATION_THRESHOLD

    for pk in new_tender_pks:
        enrich_tender.apply_async(args=[pk], countdown=5)

    return pass_stats


@shared_task(name="apps.tenders.tasks.sync_active_tenders", time_limit=1800)
def sync_active_tenders() -> dict:
    """
    Почасовая синхронизация активных тендеров с ЕИС.

    Разбивает по дням и ценовым диапазонам (44-ФЗ × 5 диапазонов + 223-ФЗ),
    чтобы обойти лимит ЕИС ~5000 записей на запрос.
    """
    from .models import Tender
    from .eis_client import search_tenders
    from .services import upsert_tender

    start_time = timezone.now()
    stats = {
        "fetched": 0, "new": 0, "updated": 0,
        "expired": 0, "errors": 0,
        "passes": [], "truncated_passes": [],
    }

    today = date.today()
    days = [today - timedelta(days=d) for d in range(DAYS_LOOKBACK + 1)]

    logger.info("sync_active_tenders: %s → %s (%d days)", days[-1], today, len(days))

    for day in days:
        existing_numbers = set(
            Tender.objects.filter(
                published_at__date=day,
            ).values_list("number", flat=True)
        )

        for range_label, price_from, price_to in FZ44_PRICE_RANGES:
            ps = _fetch_pass(
                search_tenders, upsert_tender,
                date_from=day, date_to=day,
                fz44=True, fz223=False,
                price_from=price_from, price_to=price_to,
                existing_numbers=existing_numbers,
            )
            pass_info = {
                "law": "44-ФЗ", "range": range_label,
                "day": str(day), **ps,
            }
            stats["passes"].append(pass_info)
            stats["fetched"] += ps["fetched"]
            stats["new"] += ps["new"]
            stats["errors"] += ps["errors"]
            if ps["truncated"]:
                stats["truncated_passes"].append(pass_info)
            if ps["new"] or ps["fetched"]:
                logger.info(
                    "  %s 44-ФЗ %s: fetched=%d new=%d pages=%d%s",
                    day, range_label, ps["fetched"], ps["new"], ps["pages"],
                    " TRUNCATED" if ps["truncated"] else "",
                )

        ps = _fetch_pass(
            search_tenders, upsert_tender,
            date_from=day, date_to=day,
            fz44=False, fz223=True,
            price_from=None, price_to=None,
            existing_numbers=existing_numbers,
        )
        pass_info = {
            "law": "223-ФЗ", "range": "все",
            "day": str(day), **ps,
        }
        stats["passes"].append(pass_info)
        stats["fetched"] += ps["fetched"]
        stats["new"] += ps["new"]
        stats["errors"] += ps["errors"]
        if ps["truncated"]:
            stats["truncated_passes"].append(pass_info)
        if ps["new"] or ps["fetched"]:
            logger.info(
                "  %s 223-ФЗ: fetched=%d new=%d pages=%d%s",
                day, ps["fetched"], ps["new"], ps["pages"],
                " TRUNCATED" if ps["truncated"] else "",
            )

    stats["updated"] = stats["fetched"] - stats["new"]

    # --- Помечаем просроченные тендеры как FINISHED и удаляем из Qdrant ---
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

    # --- Тендеры без дедлайна, опубликованные > 180 дней назад ---
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
        logger.info("sync: removed %d old no-deadline tenders from Qdrant", len(old_ids))

    logger.info(
        "sync_active_tenders done: fetched=%d new=%d updated=%d expired=%d errors=%d truncated=%d",
        stats["fetched"], stats["new"], stats["updated"],
        stats["expired"], stats["errors"], len(stats["truncated_passes"]),
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


@shared_task(name="apps.tenders.tasks.recover_failed_tenders", time_limit=3600)
def recover_failed_tenders() -> dict:
    """Ночная задача: подбирает активные тендеры без обогащения или embedding."""
    from .models import Tender
    from .eis_client import fetch_tender_detail
    from .services import upsert_tender
    from apps.alerts.services import log_pipeline_run

    start_time = timezone.now()
    stats = {"enrich_ok": 0, "enrich_failed": 0, "enrich_skipped": 0, "embed_queued": 0}

    to_enrich = list(
        Tender.objects.filter(
            Q(enriched_at__isnull=True) | Q(enriched_at__isnull=False, region=""),
            status=Tender.Status.ACTIVE,
        ).exclude(source=Tender.Source.BIDZAAR).order_by("deadline_at")[:500]
    )

    for tender in to_enrich:
        try:
            detail = fetch_tender_detail(tender.number, tender.source_url)
            if detail:
                detail["raw_json"] = detail.copy()
                upsert_tender(detail)
                Tender.objects.filter(pk=tender.pk).update(enriched_at=timezone.now())
                stats["enrich_ok"] += 1
            else:
                stats["enrich_skipped"] += 1
        except Exception as exc:
            stats["enrich_failed"] += 1
            logger.warning("recover enrich %s: %s", tender.number, exc)
        time.sleep(0.5)

    to_embed = list(
        Tender.objects.filter(
            enriched_at__isnull=False,
            embedding_id__isnull=True,
            status=Tender.Status.ACTIVE,
        ).exclude(source=Tender.Source.BIDZAAR)[:1000]
    )

    from apps.search.tasks import embed_tender as embed_task

    for tender in to_embed:
        try:
            embed_task.delay(tender.pk)
            stats["embed_queued"] += 1
        except Exception as exc:
            logger.warning("recover embed queue %s: %s", tender.number, exc)

    logger.info(
        "recover_failed_tenders: enrich ok=%d failed=%d skipped=%d embed_queued=%d",
        stats["enrich_ok"], stats["enrich_failed"],
        stats["enrich_skipped"], stats["embed_queued"],
    )

    status = "failed" if stats["enrich_failed"] > stats["enrich_ok"] else "ok"
    log_pipeline_run(
        task_name="recover_failed_tenders",
        started_at=start_time,
        stats=stats,
        status=status,
    )

    return stats


# Тендеры хранятся 30 дней после истечения дедлайна, затем удаляются из БД и MinIO.
# Тендеры с pipeline-записями пользователей не трогаем никогда.
TENDER_RETENTION_DAYS = 7
CLEANUP_BATCH = 200


@shared_task(name="apps.tenders.tasks.cleanup_finished_tenders", time_limit=3600)
def cleanup_finished_tenders() -> dict:
    """
    Еженедельная очистка: удаляет из БД тендеры со статусом FINISHED
    у которых deadline_at старше TENDER_RETENTION_DAYS дней.
    Тендеры с записями в pipeline пользователей пропускает.
    Порядок: MinIO → Qdrant doc_chunks → DELETE из БД (CASCADE удаляет TenderDocument и SummaryExperiment).
    """
    from .models import Tender
    from apps.alerts.services import log_pipeline_run
    from apps.documents.storage import delete_prefix
    from apps.search.services import qdrant_service, COLLECTION_DOC_CHUNKS
    from qdrant_client.models import Filter, FieldCondition, MatchAny

    start_time = timezone.now()
    cutoff = timezone.now() - timedelta(days=TENDER_RETENTION_DAYS)
    stats = {"deleted": 0, "skipped_pipeline": 0, "minio_files": 0, "errors": 0}

    base_qs = Tender.objects.filter(
        status=Tender.Status.FINISHED,
        deadline_at__lt=cutoff,
        deadline_at__isnull=False,
    ).exclude(pipeline_entries__isnull=False)

    stats["skipped_pipeline"] = Tender.objects.filter(
        status=Tender.Status.FINISHED,
        deadline_at__lt=cutoff,
        deadline_at__isnull=False,
        pipeline_entries__isnull=False,
    ).count()

    while True:
        batch = list(
            base_qs.only("pk", "number").values("pk", "number")[:CLEANUP_BATCH]
        )
        if not batch:
            break

        batch_ids = [t["pk"] for t in batch]

        # 1. MinIO: удаляем original/ и extracted/ для каждого тендера
        for t in batch:
            try:
                stats["minio_files"] += delete_prefix(f"original/{t['number']}/")
                stats["minio_files"] += delete_prefix(f"extracted/{t['number']}/")
            except Exception as exc:
                logger.warning("MinIO delete error tender %s: %s", t["number"], exc)
                stats["errors"] += 1

        # 2. Qdrant doc_chunks (на случай если TTL-очистка ещё не прошла)
        try:
            qdrant_service.client.delete(
                collection_name=COLLECTION_DOC_CHUNKS,
                points_selector=Filter(
                    must=[FieldCondition(key="tender_id", match=MatchAny(any=batch_ids))]
                ),
            )
        except Exception as exc:
            logger.warning("Qdrant doc_chunks delete error: %s", exc)
            stats["errors"] += 1

        # 3. Удаляем из БД — CASCADE убивает TenderDocument и SummaryExperiment
        deleted, _ = Tender.objects.filter(pk__in=batch_ids).delete()
        stats["deleted"] += deleted

        logger.info("cleanup_finished_tenders: batch deleted %d", deleted)

    logger.info(
        "cleanup_finished_tenders done: deleted=%d skipped_pipeline=%d minio_files=%d errors=%d",
        stats["deleted"], stats["skipped_pipeline"], stats["minio_files"], stats["errors"],
    )

    log_pipeline_run(
        task_name="cleanup_finished_tenders",
        started_at=start_time,
        stats=stats,
        status="ok" if stats["errors"] == 0 else "partial",
    )
    return stats
