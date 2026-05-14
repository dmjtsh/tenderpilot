import logging
import time
from datetime import date, datetime, timedelta, timezone as dt_tz

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


def _status_emoji(
    value: int | float,
    warning: int | float,
    critical: int | float,
    inverse: bool = False,
) -> str:
    if inverse:
        if value <= critical:
            return "\U0001f534"
        if value <= warning:
            return "\u26a0\ufe0f"
        return "\u2705"
    if value >= critical:
        return "\U0001f534"
    if value >= warning:
        return "\u26a0\ufe0f"
    return "\u2705"


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", "\u00a0")


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
    sync_total = sync_ok + sync_fail

    enrich_runs = runs.filter(task_name="enrich_tender")
    enrich_ok = enrich_runs.filter(status="ok").count()
    enrich_fail = enrich_runs.filter(status="failed").count()

    embed_runs = runs.filter(task_name="embed_tender")
    embed_ok = embed_runs.filter(status="ok").count()

    from apps.tenders.models import Tender

    total = Tender.objects.count()
    active = Tender.objects.filter(status="active").count()
    active_qs = Tender.objects.filter(status="active").exclude(source=Tender.Source.BIDZAAR)
    not_enriched = active_qs.filter(enriched_at__isnull=True).count()
    not_indexed = active_qs.filter(enriched_at__isnull=False, embedding_id__isnull=True).count()
    no_region = active_qs.filter(enriched_at__isnull=False, region="").count()
    no_deadline = active_qs.filter(deadline_at__isnull=True).count()

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

    issues: list[str] = []
    has_critical = False

    def _check(value, warning, critical, issue_text, inverse=False):
        nonlocal has_critical
        em = _status_emoji(value, warning, critical, inverse)
        if em == "\U0001f534":
            has_critical = True
            issues.append(issue_text)
        elif em == "\u26a0\ufe0f":
            issues.append(issue_text)
        return em

    e_sync = _check(sync_fail, 2, 5,
                     f"Sync: {sync_fail} из {sync_total} не завершились")
    e_errors = _check(total_errors, 20, 50,
                      f"Парсинг: {total_errors} ошибок (порог 20)")
    e_enrich = _check(enrich_fail, 20, 50,
                      f"Обогащение: {enrich_fail} ошибок (порог 20)")
    e_not_enriched = _check(not_enriched, 100, 500,
                            f"Не обогащено: {_fmt(not_enriched)} (порог 100)")
    e_not_indexed = _check(not_indexed, 100, 500,
                           f"Не проиндексировано: {_fmt(not_indexed)} (порог 100)")
    e_no_region = _check(no_region, 50, 200,
                         f"Без региона: {_fmt(no_region)} (порог 50)")
    e_no_deadline = _check(no_deadline, 200, 500,
                           f"Без дедлайна: {_fmt(no_deadline)} активных (порог 200)")
    e_truncated = _check(truncated_total, 1, 3,
                         f"Усечённых проходов: {truncated_total} (данные неполные)")

    if not issues:
        verdict = "\u2705 Всё в норме"
    elif has_critical:
        verdict = f"\U0001f534 Критические проблемы ({len(issues)})"
    else:
        verdict = f"\u26a0\ufe0f Есть замечания ({len(issues)})"

    sep = "\u2501" * 18

    recover_run = (
        runs.filter(task_name="recover_failed_tenders")
        .order_by("-finished_at")
        .first()
    )
    if recover_run:
        rs = recover_run.stats
        recover_text = (
            f"\n\n\U0001f501 <b>Восстановление (ночью)</b>\n"
            f"Обогащено: {rs.get('enrich_ok', 0)}, "
            f"не удалось: {rs.get('enrich_failed', 0)}\n"
            f"Embed: {rs.get('embed_queued', 0)} в очередь"
        )
    else:
        recover_text = ""

    attention_text = ""
    if issues:
        lines = "\n".join(f"\u2022 {i}" for i in issues)
        attention_text = f"\n\n\u26a0\ufe0f <b>Требует внимания:</b>\n{lines}"

    text = (
        f"<b>{verdict}</b>\n\n"
        f"{sep}\n\n"
        f"\U0001f4e1 <b>Синхронизация</b>\n"
        f"Проходов: {e_sync} {sync_ok} ok, {sync_fail} fail (из {sync_total})\n"
        f"Новых тендеров: {_fmt(total_new)}\n"
        f"Ошибок парсинга: {e_errors} {total_errors}\n\n"
        f"\U0001f4ca <b>Обогащение</b>\n"
        f"Обогащено: {e_enrich} {_fmt(enrich_ok)} ok, {enrich_fail} fail\n"
        f"Проиндексировано: {_fmt(embed_ok)} ok\n\n"
        f"\U0001f5c4 <b>База данных</b>\n"
        f"Всего: {_fmt(total)} | Активных: {_fmt(active)}\n"
        f"Не обогащено: {e_not_enriched} {_fmt(not_enriched)}\n"
        f"Не проиндексировано: {e_not_indexed} {_fmt(not_indexed)}\n"
        f"Без региона: {e_no_region} {_fmt(no_region)}\n"
        f"Без дедлайна: {e_no_deadline} {_fmt(no_deadline)}\n\n"
        f"\U0001f310 <b>Покрытие ЕИС (вчера, {yesterday})</b>\n"
        f"44-ФЗ: {_fmt(fz44_count)} | 223-ФЗ: {_fmt(fz223_count)}\n"
        f"Усечённых проходов: {e_truncated} {truncated_total}"
        + recover_text
        + attention_text
    )
    send_telegram(text)


COVERAGE_DAYS = 5
# Тревога если у нас < 80% от того что показывает ЕИС
COVERAGE_WARN_THRESHOLD = 0.80
COVERAGE_CRIT_THRESHOLD = 0.60


@shared_task(name="apps.alerts.tasks.check_coverage", time_limit=300)
def check_coverage(notify_always: bool = False) -> str:
    """
    Каждые 3 часа сравнивает кол-во АКТИВНЫХ тендеров в БД с тем что показывает ЕИС.
    notify_always=True — слать в Telegram даже при норме (для ручного запроса из бота).
    """
    from apps.tenders.models import Tender
    from apps.tenders.eis_client import fetch_day_count

    # ЕИС использует московское время, поэтому "день по МСК" = UTC [day-1 21:00, day 21:00)
    MSK_OFFSET = timedelta(hours=3)
    today = (timezone.now() + MSK_OFFSET).date()
    rows: list[str] = []
    has_problem = False

    for delta in range(1, COVERAGE_DAYS + 1):
        day = today - timedelta(days=delta)
        # Диапазон published_at в UTC соответствующий московскому дню
        day_start = datetime(day.year, day.month, day.day, tzinfo=dt_tz.utc) - MSK_OFFSET
        day_end = day_start + timedelta(days=1)

        eis_count = fetch_day_count(day, fz44=True, fz223=True)
        db_count = Tender.objects.filter(
            published_at__gte=day_start,
            published_at__lt=day_end,
            status="active",
        ).count()

        if eis_count is None:
            rows.append(f"  ❓ {day}: ЕИС недоступен | БД active: {_fmt(db_count)}")
        elif eis_count == 0:
            rows.append(f"  ✅ {day}: ЕИС 0 | БД active: {_fmt(db_count)}")
        else:
            ratio = db_count / eis_count
            if ratio < COVERAGE_WARN_THRESHOLD:
                has_problem = True
                emoji = "🔴" if ratio < COVERAGE_CRIT_THRESHOLD else "⚠️"
            else:
                emoji = "✅"
            rows.append(
                f"  {emoji} {day}: ЕИС ~{_fmt(eis_count)} | active {_fmt(db_count)} ({ratio:.0%})"
            )

        time.sleep(2)

    if not rows:
        return "no data"

    header = "🔴 Покрытие ЕИС неполное" if has_problem else "✅ Покрытие ЕИС в норме"
    text = f"<b>{header}</b>\n\n" + "\n".join(rows)

    if has_problem or notify_always:
        send_telegram(text)
    else:
        logger.info("check_coverage ok:\n%s", "\n".join(rows))

    return text
