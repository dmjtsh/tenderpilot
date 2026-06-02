import logging
import time as _time

from django.utils import timezone

from .telegram import send_telegram

logger = logging.getLogger(__name__)

_last_alerts: dict[str, float] = {}
ALERT_COOLDOWN = 3600


def _should_alert(key: str) -> bool:
    now = _time.time()
    last = _last_alerts.get(key, 0)
    if now - last < ALERT_COOLDOWN:
        return False
    _last_alerts[key] = now
    return True


def log_pipeline_run(
    task_name: str,
    started_at,
    stats: dict,
    status: str,
    error_message: str = "",
):
    from .models import PipelineRun

    duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
    run = PipelineRun.objects.create(
        task_name=task_name,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        stats=stats,
        error_message=error_message,
    )
    try:
        check_critical_alerts(run)
    except Exception as exc:
        logger.error("check_critical_alerts failed: %s", exc)
    return run


def check_critical_alerts(run) -> None:
    from .models import PipelineRun

    if run.task_name == "sync_active_tenders":
        fetched = run.stats.get("fetched", 0)
        errors = run.stats.get("errors", 0)
        new = run.stats.get("new", 0)

        if fetched == 0 and errors > 0:
            if _should_alert("sync_failed"):
                msg = f"\u26a0\ufe0f <b>Sync failed</b>\n0 fetched, {errors} errors"
                if run.error_message:
                    msg += f"\n{run.error_message[:200]}"
                send_telegram(msg)

        if new == 0:
            last_3 = list(
                PipelineRun.objects.filter(
                    task_name="sync_active_tenders",
                ).order_by("-finished_at")[:3].values_list("stats", flat=True)
            )
            if len(last_3) >= 3 and all(s.get("new", 0) == 0 for s in last_3):
                if _should_alert("sync_no_new"):
                    send_telegram(
                        "\u26a0\ufe0f <b>0 новых тендеров</b> 3 sync подряд"
                    )

        truncated = run.stats.get("truncated_passes", [])
        if truncated and _should_alert("sync_truncated"):
            lines = [
                f"  {p.get('law', '?')} {p.get('range', '?')} ({p.get('day', '?')})"
                for p in truncated[:5]
            ]
            send_telegram(
                f"\u26a0\ufe0f <b>ЕИС truncation</b>\n"
                f"{len(truncated)} проходов уперлись в лимит 5000:\n"
                + "\n".join(lines)
                + "\nНужно дробить ценовые диапазоны"
            )

    elif run.task_name == "sync_tenderguru" and run.status == "failed":
        if _should_alert("tenderguru_failed"):
            send_telegram(
                f"⚠️ <b>sync_tenderguru упал</b>\n"
                f"{run.error_message[:200] if run.error_message else 'без деталей'}"
            )

    elif run.task_name == "enrich_tender" and run.status == "failed":
        last_5 = list(
            PipelineRun.objects.filter(
                task_name="enrich_tender",
            ).order_by("-finished_at")[:5].values_list("status", flat=True)
        )
        if len(last_5) >= 5 and all(s == "failed" for s in last_5):
            if _should_alert("enrich_5_fails"):
                send_telegram(
                    "\u26a0\ufe0f <b>5 обогащений подряд провалились</b>\n"
                    f"Последняя ошибка: {run.error_message[:200]}"
                )
