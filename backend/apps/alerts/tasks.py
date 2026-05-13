import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .telegram import send_telegram

logger = logging.getLogger(__name__)


@shared_task
def check_pipeline_health() -> None:
    from .models import PipelineRun

    last_sync = (
        PipelineRun.objects.filter(task_name="sync_active_tenders")
        .order_by("-finished_at")
        .first()
    )

    if not last_sync:
        send_telegram("\u26a0\ufe0f Нет ни одного запуска sync_active_tenders")
        return

    hours_ago = (timezone.now() - last_sync.finished_at).total_seconds() / 3600
    if hours_ago > 2:
        send_telegram(
            f"\u26a0\ufe0f sync_active_tenders не запускался <b>{hours_ago:.1f}ч</b>"
        )


@shared_task
def send_morning_digest() -> None:
    from .models import PipelineRun

    since = timezone.now() - timedelta(hours=24)
    runs = PipelineRun.objects.filter(finished_at__gte=since)

    sync_runs = runs.filter(task_name="sync_active_tenders")
    total_new = sum(r.stats.get("new", 0) for r in sync_runs)
    total_errors = sum(r.stats.get("errors", 0) for r in sync_runs)
    sync_ok = sync_runs.filter(status="ok").count()
    sync_fail = sync_runs.exclude(status="ok").count()

    enrich_runs = runs.filter(task_name="enrich_tender")
    enrich_ok = enrich_runs.filter(status="ok").count()
    enrich_fail = enrich_runs.filter(status="failed").count()

    from apps.tenders.models import Tender

    total = Tender.objects.count()
    active = Tender.objects.filter(status="active").count()
    not_enriched = (
        Tender.objects.filter(enriched_at__isnull=True)
        .exclude(source=Tender.Source.BIDZAAR)
        .count()
    )

    yesterday = (timezone.now() - timedelta(days=1)).date()
    fz44_count = Tender.objects.filter(
        published_at__date=yesterday, law_type="44-ФЗ",
    ).count()
    fz223_count = Tender.objects.filter(
        published_at__date=yesterday, law_type="223-ФЗ",
    ).count()

    truncated_total = 0
    for run in sync_runs:
        truncated_total += len(run.stats.get("truncated_passes", []))
    trunc_mark = "\u2705" if truncated_total == 0 else f"\u26a0\ufe0f {truncated_total}"

    recover_run = (
        runs.filter(task_name="recover_failed_tenders")
        .order_by("-finished_at")
        .first()
    )
    if recover_run:
        rs = recover_run.stats
        recover_text = (
            f"\n\n\U0001f501 <b>Восстановление (ночью):</b>\n"
            f"Обогащено: {rs.get('enrich_ok', 0)}, "
            f"не удалось: {rs.get('enrich_failed', 0)}\n"
            f"Embed: {rs.get('embed_queued', 0)} в очередь"
        )
    else:
        recover_text = ""

    text = (
        f"\U0001f4ca <b>Дайджест за 24ч</b>\n\n"
        f"<b>Sync:</b> {sync_ok} ok, {sync_fail} fail\n"
        f"Новых тендеров: {total_new}\n"
        f"Ошибок парсинга: {total_errors}\n\n"
        f"<b>Обогащение:</b> {enrich_ok} ok, {enrich_fail} fail\n\n"
        f"<b>БД:</b> {total} всего, {active} активных\n"
        f"Не обогащено: {not_enriched}\n\n"
        f"\U0001f310 <b>Покрытие ЕИС (вчера, {yesterday}):</b>\n"
        f"44-ФЗ: {fz44_count} тендеров в БД\n"
        f"223-ФЗ: {fz223_count} тендеров в БД\n"
        f"Усечённых проходов: {trunc_mark}"
        + recover_text
    )
    send_telegram(text)
