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
        send_telegram("⚠️ Нет ни одного запуска sync_active_tenders")
        return

    hours_ago = (timezone.now() - last_sync.finished_at).total_seconds() / 3600
    if hours_ago > 2:
        send_telegram(
            f"⚠️ sync_active_tenders не запускался <b>{hours_ago:.1f}ч</b>"
        )


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


COVERAGE_DAYS = 5
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

    MSK_OFFSET = timedelta(hours=3)
    today = (timezone.now() + MSK_OFFSET).date()
    rows: list[str] = []
    has_problem = False

    for delta in range(1, COVERAGE_DAYS + 1):
        day = today - timedelta(days=delta)
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
                emoji = "\U0001f534" if ratio < COVERAGE_CRIT_THRESHOLD else "⚠️"
            else:
                emoji = "✅"
            rows.append(
                f"  {emoji} {day}: ЕИС ~{_fmt(eis_count)} | active {_fmt(db_count)} ({ratio:.0%})"
            )

        time.sleep(2)

    if not rows:
        return "no data"

    header = "\U0001f534 Покрытие ЕИС неполное" if has_problem else "✅ Покрытие ЕИС в норме"
    text = f"<b>{header}</b>\n\n" + "\n".join(rows)

    if has_problem or notify_always:
        send_telegram(text)
    else:
        logger.info("check_coverage ok:\n%s", "\n".join(rows))

    return text
