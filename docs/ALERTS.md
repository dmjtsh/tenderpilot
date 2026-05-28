# Мониторинг — apps/alerts

Дата обновления: 28 мая 2026

## Модель PipelineRun

```python
task_name    CharField(db_index)
  # SYNC_ACTIVE, ENRICH_TENDER, EMBED_TENDER, CLEANUP_CHUNKS,
  # CLEANUP_DOCS, CLEANUP_TENDERS, RECOVER, SYNC_KOMTENDER, SYNC_TENDERGURU
status       CharField(OK|PARTIAL|FAILED)
started_at   DateTimeField
finished_at  DateTimeField
duration_ms  PositiveIntegerField(default=0)
stats        JSONField(default=dict)   # {fetched, new, updated, errors, ...}
error_message TextField(blank)
```

## Services (services.py)

- `log_pipeline_run(task_name, started_at, stats, status, error_message)` → PipelineRun
  - Автоматически вызывает check_critical_alerts() при failures
- `check_critical_alerts(task_name, stats, error)` — отправляет Telegram алерты:
  - sync failure
  - 0 new тендеров 3 раза подряд
  - 5+ enrich failures
  - truncation (≥100 страниц ЕИС)
- `send_telegram(text)` → requests.post к Telegram Bot API
- Дедупликация: `_should_alert(key)` с cooldown 1 час

## Celery Tasks

| Task | Расписание | Описание |
|------|-----------|----------|
| `check_pipeline_health` | каждые 15 мин | Алерт если sync не запускался >2ч |
| `check_coverage` | каждые 3ч | Сравнение наших active vs ЕИС count за 5 дней. Warning <80%, critical <60% |

**Не в Celery beat (ручной запуск):**
- `send_morning_digest` — 09:00 MSK, сводка за 24ч (sync/enrich/БД/покрытие/recover)
- `recover_failed_tenders` — 04:00 MSK, подбирает необогащённые (≤500) и без embedding (≤1000)

## Telegram

- `POST /api/v1/alerts/tg/{token}/` — webhook endpoint
- Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`
- Тест: `python manage.py shell -c "from apps.alerts.telegram import send_telegram; print(send_telegram('test'))"`
