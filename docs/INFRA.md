# Инфраструктура

Дата обновления: 28 мая 2026

## Docker Compose

Базовые инфра-сервисы:
- `postgres:16` — БД tenders (порт 5432)
- `redis:7` — Celery broker (порт 6379)
- `qdrant:latest` — vector DB (порт 6333)
- `minio:latest` — S3 storage (порт 9000)

Мониторинг-стек (см. ниже):
- `prometheus` — сбор метрик (порт 9090)
- `grafana` — дашборды (порт 3001, логин admin / `GRAFANA_PASSWORD`)
- `flower` — Celery web UI (порт 5555)
- `celery_exporter` — Celery→Prometheus (порт 9808)
- `redis_exporter` — Redis→Prometheus (порт 9121)
- `postgres_exporter` — Postgres→Prometheus (порт 9187)
- `node_exporter` — CPU/RAM/диск (порт 9100, host network)

```bash
# Все сервисы
docker compose up -d

# Только мониторинг
docker compose up -d prometheus grafana flower celery_exporter redis_exporter postgres_exporter node_exporter
```

### Переменные для мониторинга
```
GRAFANA_PASSWORD=your_password   # default: admin
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

## Мониторинг (Prometheus + Grafana)

### Источники метрик

| Job | Target | Что собирает |
|-----|--------|-------------|
| `django` | `host:8080/metrics` | HTTP latency, DB queries, custom pipeline metrics |
| `celery` | `celery_exporter:9808` | Task success/failure/runtime по task_name |
| `redis` | `redis_exporter:9121` | Memory, ops/sec, connections, queue depth |
| `postgres` | `postgres_exporter:9187` | Connections, transactions, DB size |
| `node` | `localhost:9100` | CPU, RAM, disk, network |
| `qdrant` | `qdrant:6333/metrics` | Vector counts, storage size |

### Custom метрики Django (`/metrics`)

- `tenderpilot_tenders_total{source, status}` — количество тендеров
- `tenderpilot_pipeline_last_success_timestamp_seconds{task_name}` — последний успешный запуск
- `tenderpilot_pipeline_last_duration_ms{task_name}` — длительность последнего запуска
- `tenderpilot_pipeline_errors_last_run{task_name}` — ошибки в последнем запуске
- `tenderpilot_documents_total{parse_status}` — документы по статусу
- `tenderpilot_unenriched_tenders_total` — активные тендеры без enrichment
- `tenderpilot_unembedded_tenders_total` — активные тендеры без векторов

### Grafana дашборды

Провизионируются автоматически из `infra/grafana/provisioning/dashboards/`:

| Файл | Дашборд | Что показывает |
|------|---------|----------------|
| `pipeline.json` | Pipeline & Data | Наполняемость, coverage, pipeline задачи |
| `celery.json` | Celery & HTTP | Очереди, скорость/ошибки задач, HTTP latency |
| `infra.json` | Infrastructure | CPU/RAM/диск, Redis, Postgres, Qdrant |

### Prometheus конфиг
`infra/prometheus.yml` — retention 30 дней, scrape_interval 15s.

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
GRAFANA_PASSWORD=...
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
