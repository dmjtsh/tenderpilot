import logging
import time
from datetime import date, datetime, timedelta, timezone as dt_tz

from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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

    if tender.source == Tender.Source.KOMTENDER:
        if not tender.enriched_at:
            Tender.objects.filter(pk=tender_id).update(enriched_at=timezone.now())
        from apps.search.tasks import embed_tender
        embed_tender.delay(tender_id)
        return

    if tender.source == Tender.Source.TENDERGURU:
        from .tenderguru_client import fetch_tender_detail as tg_fetch, enrich_from_detail, parse_list_item
        from .services import upsert_tender as upsert_fn
        tg_id = tender.number.replace("tg-", "")
        detail = tg_fetch(tg_id)
        if detail:
            base = parse_list_item(detail)
            if base:
                enriched = enrich_from_detail(base, detail)
                upsert_fn(enriched)
        if not tender.enriched_at:
            Tender.objects.filter(pk=tender_id).update(enriched_at=timezone.now())
        from apps.search.tasks import embed_tender
        embed_tender.delay(tender_id)
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

    # ЕИС использует московское время — берём текущий день по МСК
    MSK_OFFSET = timedelta(hours=3)
    today = (timezone.now() + MSK_OFFSET).date()
    days = [today - timedelta(days=d) for d in range(DAYS_LOOKBACK + 1)]

    logger.info("sync_active_tenders: %s → %s (%d days)", days[-1], today, len(days))

    for day in days:
        # Диапазон published_at в UTC для московского дня: [day 00:00 MSK, day+1 00:00 MSK)
        day_start = datetime(day.year, day.month, day.day, tzinfo=dt_tz.utc) - MSK_OFFSET
        day_end = day_start + timedelta(days=1)
        existing_numbers = set(
            Tender.objects.filter(
                published_at__gte=day_start,
                published_at__lt=day_end,
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
    # TenderGuru исключён: его дедлайны часто продлевают, поэтому TG-тендеры
    # экспирируются отдельно в sync_tenderguru с предварительной проверкой по API
    # (см. _verify_and_expire_tenderguru). Для ЕИС такой проверки не нужно.
    from apps.search.services import qdrant

    now = timezone.now()

    expired_ids = list(
        Tender.objects.filter(
            deadline_at__lt=now,
            deadline_at__isnull=False,
            status=Tender.Status.ACTIVE,
        ).exclude(source=Tender.Source.TENDERGURU).values_list("pk", flat=True)
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
        ).exclude(source=Tender.Source.TENDERGURU).values_list("pk", flat=True)
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
    from apps.search.services import qdrant, COLLECTION_DOC_CHUNKS
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
            qdrant.client.delete(
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


# ---------------------------------------------------------------------------
# TenderGuru sync
# ---------------------------------------------------------------------------

TENDERGURU_MAX_PER_RUN = 5000
TENDERGURU_DELAY = 0.3
# Окно публикации: берём тендеры за последние N дней.
# Покрывает пропуски при простое синка (рестарты, деплой и т.д.)
TENDERGURU_DATE_WINDOW_DAYS = 2  # вчера + сегодня, покрывает ночной пропуск

# Verified expiry: за один прогон проверяем по API не больше N протухших
# TG-тендеров (защита от спама лимитов). Остаток досматривается в следующий
# прогон — пока он остаётся active, что безопасно.
TENDERGURU_EXPIRE_MAX_CHECKS = 1000
TENDERGURU_EXPIRE_DELAY = 0.3


def _verify_and_expire_tenderguru(now, session=None) -> dict:
    """Аккуратно экспирировать протухшие TenderGuru-тендеры с проверкой по API.

    TenderGuru часто продлевает дедлайны: тендер с прошедшим у нас `deadline_at`
    может всё ещё быть активным (новый `EndTime` в будущем). Поэтому перед тем
    как гасить, перечитываем карточку через detail-API:
      * свежий дедлайн в будущем  -> продлеваем `deadline_at`, оставляем active,
        обновляем payload в Qdrant (embed_tender);
      * иначе (прошёл / карточка пропала / ошибка) -> FINISHED + удаляем из Qdrant.

    Лимитировано TENDERGURU_EXPIRE_MAX_CHECKS за прогон.
    """
    from .models import Tender
    from .tenderguru_client import fetch_tender_detail, parse_list_item
    from apps.search.services import qdrant
    from apps.search.tasks import embed_tender

    res = {"checked": 0, "extended": 0, "finished": 0, "errors": 0}

    candidates = list(
        Tender.objects.filter(
            source=Tender.Source.TENDERGURU,
            status=Tender.Status.ACTIVE,
            deadline_at__lt=now,
            deadline_at__isnull=False,
        )
        .order_by("deadline_at")
        .values_list("pk", "number")[:TENDERGURU_EXPIRE_MAX_CHECKS]
    )

    for pk, number in candidates:
        res["checked"] += 1
        tg_id = number.replace("tg-", "")

        fresh_deadline = None
        try:
            detail = fetch_tender_detail(tg_id, session=session)
            if detail:
                parsed = parse_list_item(detail)
                if parsed and parsed.get("deadline_at"):
                    fresh_deadline = parse_datetime(parsed["deadline_at"])
        except Exception as exc:
            logger.warning("tg expire: detail %s failed: %s", number, exc)
            res["errors"] += 1

        if fresh_deadline and fresh_deadline > now:
            # Продлён в TenderGuru — оставляем активным, освежаем дедлайн и Qdrant.
            Tender.objects.filter(pk=pk).update(deadline_at=fresh_deadline)
            try:
                embed_tender.delay(pk)
            except Exception as exc:
                logger.warning("tg expire: embed %d failed: %s", pk, exc)
            res["extended"] += 1
        else:
            Tender.objects.filter(pk=pk).update(status=Tender.Status.FINISHED)
            try:
                qdrant.delete_tender(pk)
            except Exception as exc:
                logger.warning("tg expire: qdrant delete %d failed: %s", pk, exc)
            res["finished"] += 1

        time.sleep(TENDERGURU_EXPIRE_DELAY)

    return res


@shared_task(name="apps.tenders.tasks.sync_tenderguru", time_limit=7200)
def sync_tenderguru() -> dict:
    """Sync of commercial tenders from TenderGuru API.

    Filters by date_start (last TENDERGURU_DATE_WINDOW_DAYS days) so we only
    scan recently published tenders instead of the entire 84k catalogue.

    IMPORTANT: TenderGuru sorts newest-day-first but ID-ASCENDING within a day,
    so the freshest tenders of the current day live in the TAIL of that day's
    page range, not on page 1. We therefore crawl the ENTIRE date window (no
    early page cap) until an empty page marks the real end — otherwise every
    run would re-scan only the stale head of the day and miss all new tenders.

    At the end we run verified expiry (_verify_and_expire_tenderguru): TG
    deadlines are often extended, so a TG tender past its stored deadline is
    re-checked via the detail API before being finished. This is why TG is
    excluded from the deadline-based expiry in sync_active_tenders.
    """
    from .models import Tender
    from .tenderguru_client import (
        fetch_list_page,
        fetch_tender_detail,
        parse_list_item,
        enrich_from_detail,
    )
    from .services import upsert_tender
    from apps.alerts.services import log_pipeline_run

    start_time = timezone.now()
    stats = {
        "pages": 0,
        "fetched": 0,
        "new": 0,
        "enriched": 0,
        "errors": 0,
        "expired_checked": 0,
        "extended": 0,
        "finished": 0,
    }

    existing_numbers = set(
        Tender.objects.filter(source=Tender.Source.TENDERGURU)
        .values_list("number", flat=True)
    )

    session = None
    try:
        import requests as req
        session = req.Session()
        session.headers["User-Agent"] = "Tenderoll/1.0 (tender aggregator; support@tenderoll.ru)"
    except Exception:
        pass

    # Фильтр по дате — берём только свежие публикации
    date_from = (timezone.now() - timedelta(days=TENDERGURU_DATE_WINDOW_DAYS))
    date_start = date_from.strftime("%d.%m.%Y")

    new_tender_pks: list[int] = []

    # TenderGuru sorts newest-day-first but ID-ascending WITHIN a day, so the
    # freshest tenders of the current day sit in the TAIL of the day's page
    # range — well beyond a small page cap. We must therefore crawl the whole
    # date window, not just the first N pages, or we permanently miss the newest
    # tenders every run. An empty page marks the real end of the window; a page
    # that fails every retry is skipped, not fatal.
    EMPTY_STOP = 3
    HARD_PAGE_CAP = 4000  # safety guard (~2-day window is ~1800 pages)
    consecutive_empty = 0
    page = 1

    while page < HARD_PAGE_CAP:
        try:
            items, _ = fetch_list_page(
                page=page,
                law_filter="kom",
                actual=True,
                date_start=date_start,
                session=session,
            )
        except Exception as exc:
            logger.error("sync_tenderguru list page=%d failed after retries, skipping: %s", page, exc)
            stats["errors"] += 1
            page += 1
            continue

        if not items:
            consecutive_empty += 1
            if consecutive_empty >= EMPTY_STOP:
                break
            page += 1
            continue
        consecutive_empty = 0

        stats["pages"] = page

        for item in items:
            try:
                parsed = parse_list_item(item)
                if not parsed:
                    continue
                if parsed.get("law_type") != "b2b":
                    continue

                stats["fetched"] += 1
                is_new = parsed["number"] not in existing_numbers

                if is_new:
                    tg_id = item.get("ID")
                    detail = fetch_tender_detail(tg_id, session=session)
                    if detail:
                        parsed = enrich_from_detail(parsed, detail)
                        stats["enriched"] += 1
                    time.sleep(TENDERGURU_DELAY)

                    tender = upsert_tender(parsed)
                    Tender.objects.filter(pk=tender.pk).update(enriched_at=timezone.now())
                    existing_numbers.add(parsed["number"])
                    new_tender_pks.append(tender.pk)
                    stats["new"] += 1

                    if len(new_tender_pks) >= TENDERGURU_MAX_PER_RUN:
                        break
            except Exception as exc:
                logger.error("sync_tenderguru item error: %s", exc)
                stats["errors"] += 1

        # A short page (<20) is normal mid-window — only an empty page (handled
        # above) marks the end, so we keep crawling instead of bailing early.
        if len(new_tender_pks) >= TENDERGURU_MAX_PER_RUN:
            break

        page += 1
        time.sleep(TENDERGURU_DELAY)

    for pk in new_tender_pks:
        enrich_tender.apply_async(args=[pk], countdown=5)

    # Аккуратная экспирация протухших TG-тендеров с проверкой дедлайна по API.
    try:
        exp = _verify_and_expire_tenderguru(timezone.now(), session=session)
        stats["expired_checked"] = exp["checked"]
        stats["extended"] = exp["extended"]
        stats["finished"] = exp["finished"]
        stats["errors"] += exp["errors"]
    except Exception as exc:
        logger.error("sync_tenderguru expire step error: %s", exc)
        stats["errors"] += 1

    if stats["new"] == 0 and stats["errors"] > 0:
        sync_status = "failed"
    elif stats["errors"] > 0:
        sync_status = "partial"
    else:
        sync_status = "ok"

    logger.info(
        "sync_tenderguru done: pages=%d fetched=%d new=%d enriched=%d errors=%d "
        "| expire: checked=%d extended=%d finished=%d",
        stats["pages"], stats["fetched"], stats["new"],
        stats["enriched"], stats["errors"],
        stats["expired_checked"], stats["extended"], stats["finished"],
    )
    log_pipeline_run(
        task_name="sync_tenderguru",
        started_at=start_time,
        stats=stats,
        status=sync_status,
    )
    return stats
