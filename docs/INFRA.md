# Инфраструктура

Дата обновления: 28 мая 2026

## Docker Compose (локальная разработка)

4 сервиса с healthchecks:
- `postgres:16` — БД tenders (порт 5432)
- `redis:7` — Celery broker (порт 6379)
- `qdrant:latest` — vector DB (порт 6333)
- `minio:latest` — S3 storage (порт 9000)

```bash
docker compose up -d
```

## Celery Beat (полное расписание)

| Task | Расписание | Описание |
|------|-----------|----------|
| `sync_active_tenders` | каждый час :00 | Парсинг ЕИС × ценовые диапазоны, time_limit=1800 |
| `sync_tenderguru` | каждые 2ч :15 | Коммерческие тендеры, 5000/run |
| `sync_komtender` | каждые 30 мин :30 | Komtender.ru тендеры |
| `check_pipeline_health` | каждые 15 мин | Алерт если sync >2ч назад |
| `check_coverage` | каждые 3ч | Сравнение active count vs ЕИС |
| `cleanup_doc_chunks` | каждый час :00 | TTL-очистка чанков (48ч) |
| `cleanup_old_documents` | воскресенье 03:00 | Nuclear cleanup (730 дней) |
| `cleanup_finished_tenders` | воскресенье 04:00 | Пометка старых завершённых |
| `process_renewals` | 03:00 daily | Expired subs → free |
| `expire_canceled_subscriptions` | 03:30 daily | Canceled → expired → free |

### Task Routing
- **high_priority** queue: download_and_parse_documents, parse_document, index_document_chunks, rebuild_direction_vector
- **celery** queue: всё остальное
- Worker: `-Q high_priority,celery`

## Продакшн

- Сервер: Ubuntu 22.04, `root@147.45.141.195`
- Путь: `/opt/tenderpilot` (venv в `/opt/tenderpilot/venv/`)
- Systemd сервисы: `tenderpilot-web`, `tenderpilot-worker`, `tenderpilot-beat`, `tenderpilot-frontend`
- Долгие задачи: tmux (`tmux new -s bulk`)
- Django shell: `cd /opt/tenderpilot/backend && source ../venv/bin/activate && python manage.py shell`
- psql НЕ установлен — SQL только через Django `connection.cursor()`
- **Cast**: `ROUND(PERCENTILE_CONT(...)::numeric, N)` — нужен для psycopg3

## Деплой

```bash
./deploy.sh  # git pull, pip install, migrate, collectstatic, npm build, systemd restart
```

### С переиндексацией
```bash
./deploy.sh
tmux new -s reindex
cd /opt/tenderpilot/backend && source ../venv/bin/activate
python manage.py index_tenders          # ~40 мин
python manage.py shell -c "
from apps.search.tasks import rebuild_direction_vector
from apps.users.models import CompanyDirection
for d in CompanyDirection.objects.all():
    rebuild_direction_vector(d.id)
    print(f'rebuilt {d.id} {d.name}')
"
```

## Environment Variables

```
DATABASE_URL=postgresql://tender_user:tender_pass@localhost:5432/tenders
QDRANT_URL=http://localhost:6333
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=tender_admin
MINIO_SECRET_KEY=tender_secret_123
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
DADATA_TOKEN=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...
RUSPROFILE_PROXY_URL=...
TENDERGURU_API_KEY=...
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
YOOKASSA_RETURN_URL=...
```

## Разработка

```bash
# Бэкенд
cd backend
.venv/bin/python manage.py runserver 8080
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/celery -A config worker -l info -Q celery,high_priority

# Фронтенд
cd frontend && npm run dev
```
