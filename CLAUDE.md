# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Tender SaaS — Claude Code Instructions

> **ПРАВИЛО**: После ключевых изменений (новая модель, endpoint, task, компонент, интеграция) — **обновить соответствующий docs/*.md файл**. CLAUDE.md устаревает быстро, модульные доки должны быть актуальны.

## Project overview
AI-powered tender discovery platform for Russian public procurement (44-ФЗ, 223-ФЗ, 615-ПП) and commercial tenders (B2B).
Stack: Django 5 + DRF · Next.js 14 · Postgres · Qdrant · MinIO · Celery + Redis · OpenAI/DeepSeek API

## Architecture
```
/backend
  /apps
    /tenders      — парсинг ЕИС, TenderGuru, Komtender, pipeline, AI резюме
    /search       — embedding, Qdrant, HyDE, матчинг
    /documents    — PDF/DOCX парсинг, RAG, MinIO, TTL-очистка
    /users        — авторизация, CompanyProfile, CompanyDirection
    /billing      — тарифы, ЮКасса, подписки
    /alerts       — мониторинг пайплайна, Telegram алерты
    /customers    — CustomerProfile, RusProfile, DaData enrichment
  /config         — settings, urls, celery
/frontend
  /app            — Next.js App Router pages
  /components     — UI + landing + pipeline + filters
  /lib            — API клиент, типы, утилиты
/infra            — docker-compose, nginx, systemd
/docs             — модульная документация (см. ниже)
```

## Модульная документация

Детали каждого модуля (модели с полями, функции, endpoints, tasks, commands) — в отдельных файлах:

| Файл | Модуль |
|------|--------|
| [docs/TENDERS.md](docs/TENDERS.md) | Тендеры: модели, парсеры (ЕИС, TenderGuru, Komtender), tasks, commands, API |
| [docs/SEARCH.md](docs/SEARCH.md) | Поиск: embedder, HyDE, scoring, Qdrant, match_profile |
| [docs/DOCUMENTS.md](docs/DOCUMENTS.md) | Документы: парсеры, MinIO, RAG, TTL-очистка, pipeline |
| [docs/BILLING.md](docs/BILLING.md) | Биллинг: тарифы, ЮКасса, подписки, lifecycle |
| [docs/USERS.md](docs/USERS.md) | Пользователи: User, CompanyProfile, CompanyDirection, DaData |
| [docs/ALERTS.md](docs/ALERTS.md) | Мониторинг: PipelineRun, Telegram, health checks |
| [docs/CUSTOMERS.md](docs/CUSTOMERS.md) | Заказчики: CustomerProfile, RusProfile, enrichment |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Фронтенд: страницы, компоненты, дизайн-система, CSS |
| [docs/INFRA.md](docs/INFRA.md) | Инфраструктура: docker, deploy, Celery beat, env vars |

---

## Данные (прод, 28 мая 2026)
- ~133k тендеров (active: 58.9k 44-ФЗ + 15k 223-ФЗ + ~79k TenderGuru b2b)
- TenderGuru: bulk load завершён (~79k тендеров)
- Komtender: интеграция активна (sync каждые 30 мин)
- 100% ЕИС обогащены (enriched_at IS NOT NULL)
- Sync покрывает ~100% ЕИС (ценовые диапазоны)

---

## Не трогать
- `apps/tenders/eis_client.py` — не рефакторить
- `apps/search/embedder.py` — singleton намеренный (~450MB)
- `apps/tenders/services.py:MODEL_PRICING` — только при изменении тарифов
- `apps/customers/services/rusprofile.py` — работает через прокси
- `frontend/app/providers.tsx` — `useState(() => new QueryClient())` намеренно
- `frontend/components/Shell.tsx` — `mounted` state = hydration fix
- Tailwind v3 — не обновлять

---

## MCP Tools

### postgres-mcp
Использовать перед любым ORM запросом — проверить реальную схему.

### qdrant
http://localhost:6333. Коллекции: `tenders` (векторы, cosine 1024-dim), `doc_chunks` (RAG). mmap включён.

### sequential-thinking
Обязательно для проектирования, архитектурных решений, сложных багов.

### filesystem
`/Users/dmitriyshutov/Desktop/tender_pilot`. Всегда читать файл перед редактированием.

### memory
Сохранять важные архитектурные решения между сессиями.

---

## Critical rules

### Перед кодом
1. Прочитай файл через filesystem
2. Проверь схему через postgres-mcp
3. Для сложных задач — sequential thinking сначала

### Django
- API только через DRF
- Модели только в `apps/*/models.py`
- Бизнес-логика только в `services.py`
- Celery tasks только в `tasks.py`
- Секреты через `django.conf.settings`
- Миграции только через `makemigrations`
- Type hints везде
- venv: `backend/.venv/bin/python`

### API
- Endpoints: `/api/v1/...`
- Ответ: `{data: ..., error: null}` или `{data: null, error: "..."}`
- Пагинация: page_size=20
- Auth: JWT Bearer token

### AI / ML
- HyDE вызовы через `apps/search/hyde.py`
- GPT JSON — всегда зачищать ```json``` блок перед json.loads
- LLM результаты кэшировать в Postgres
- Embedding: `multilingual-e5-large` через fastembed (не менять)
- Debounce векторов: countdown=30, фиксированный task_id
- **НЕ добавлять description в HyDE** — размывает вектора
- Дефолтная модель: DeepSeek V4 Flash (`deepseek-chat`)
- Circuit breaker: DeepSeek → gpt-4o-mini fallback

### Documents
- Документы качаются ТОЛЬКО по явному запросу пользователя
- document_id в каждом Qdrant payload — для точечного удаления
- Инвалидация ai_summary при новом документе (post_save сигнал)
- ai_summary НЕ удалять при очистке
- TTL-очистка (48ч): cleanup_doc_chunks. Nuclear (730 дней): cleanup_old_documents

### AI резюме
- Структурированный JSON v2: 6 параллельных шагов + risks
- Числовые значения ТОЧНО как в документах
- Параметр экспорта `type`, не `format` (DRF перехватывает format)

### Pipeline
- unique_together: (user, tender)
- Статусы: new / studying / preparing / submitted / won / lost
- studying/preparing/submitted исключаются из "Для вас"

### Frontend
- Светлая тема (Linear стиль для app, Stripe/Minerva для лендинга)
- violet-600 для акцентов
- React Query v5: `isLoading = isPending && isFetching`
- DRF ListCreateAPIView: `r.data.results ?? r.data`
- DocumentsBlock и AiSummaryBlock: один React Query ключ для /docs/

### Никогда
- Бизнес-логику в views
- Синхронные HTTP в Celery tasks
- PDF локально — только MinIO
- N+1 запросы — select_related/prefetch_related
- Коммитить .env
- Писать код не прочитав файл
- Автоматически качать документы при парсинге
- Менять тему на тёмную

---

## LLM модели

Дефолт: **DeepSeek V4 Flash** (`deepseek-chat`, deprecation 24 июля 2026 → `deepseek-v4-flash`)

| Модель | Input | Output | Назначение |
|--------|-------|--------|------------|
| deepseek-chat | $0.14 | $0.28 | AI-резюме (дефолт) |
| gpt-4o-mini | $0.15 | $0.60 | классификация, fallback |
| gpt-4o | $2.50 | $10.00 | резерв |
| gpt-5-nano | $0.05 | $0.40 | reasoning (не для extraction) |

Стратегия: **Full context** (truncation >100k токенов по приоритетам).

### Отвергнутые подходы
- ~~Description в HyDE~~ — размывает направления
- ~~Smart Score~~ — чистый cosine лучше
- ~~Метаданные в tender_text~~ — загрязняют вектор
- ~~RAG для резюме~~ — Full context лучше
- ~~GPT-5 Nano для extraction~~ — 47с vs 15с, хуже качество

---

## Commands

```bash
# Инфраструктура
docker compose up -d

# Бэкенд
cd backend && .venv/bin/python manage.py runserver 8080
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/celery -A config worker -l info -Q celery,high_priority

# Фронтенд
cd frontend && npm run dev

# Парсинг / загрузка
python manage.py parse_eis --days=30 --query="кровля" --enrich
python manage.py bulk_load_tenders --days=90 --delay=0.5
python manage.py bulk_load_tenderguru --limit=5000 --delay=0.3
python manage.py enrich_missing --delay=0.5
python manage.py index_tenders [--only-new]
python manage.py reindex_payloads [--dry-run]
python manage.py backfill_content_quality [--dry-run]

# Эксперименты
python manage.py run_experiment --config=experiment_models.yaml --tender-ids=1082,1148,2458
```

Полный список команд — в docs/TENDERS.md и docs/SEARCH.md.

---

## Custom commands (.claude/commands/)
```
/new-endpoint       — новый Django REST endpoint
/new-celery-task    — новая Celery задача
/debug              — отладка: логи + БД + очередь
/review             — code review на нарушения правил
```

---

## Roadmap

### Приоритет 1 — до первых пользователей
- [ ] Интеграция ЗаЧестныйБизнес API (замена RusProfile) — ресерч готов
- [ ] Рекуррентные платежи ЮКасса — требует согласование с менеджером
- [ ] **Анализ рынка** — "Есть ли у меня шансы?". Мокап: market_analysis_mockup (1).html. У СБИС есть аналог (статистический прогноз победителя) — ускорить
- [ ] **Сохранённые поисковые запросы** — у СБИС неограниченные, критично для паритета

### Приоритет 2
- [ ] **Анализ конкурентов** — кто участвует, ценовая стратегия (данные из ЕИС протоколов). У СБИС ключевая фича
- [ ] Карточка заказчика (история победителей, бенчмарки)
- [ ] Мониторинг изменений документов (file_hash + diff)
- [ ] Rate limiting на AI endpoints + Sentry
- [ ] Cross-encoder reranking
- [ ] OCR для сканированных PDF

### Приоритет 3
- [ ] Черновик заявки (LLM)

### Продакшн

- Сервер: Ubuntu 22.04, `root@147.45.141.195`, путь `/opt/tenderpilot`
- venv: `/opt/tenderpilot/venv/` (НЕ `.venv`, а `../venv/bin/python` из backend/)
- Деплой: `./deploy.sh` (git pull, pip install, migrate, build, systemd restart)
- Подробности — в [docs/INFRA.md](docs/INFRA.md)

#### Диагностика на проде
- **Логи worker**: `tail -100 /var/log/tenderpilot/celery-worker.log` (НЕ journalctl — worker пишет в файл через `--logfile`)
- **Логи web**: `journalctl -u tenderpilot-web --since "1 hour ago" --no-pager`
- **Логи beat**: `journalctl -u tenderpilot-beat --since "1 hour ago" --no-pager`
- **Systemd сервисы**: `tenderpilot-web`, `tenderpilot-worker`, `tenderpilot-beat`, `tenderpilot-frontend`
- **Celery ping**: `DJANGO_SETTINGS_MODULE=config.settings ../venv/bin/celery -A config inspect ping`
- **Django shell**: `cd /opt/tenderpilot/backend && DJANGO_SETTINGS_MODULE=config.settings ../venv/bin/python -c "..."`
- **Worker concurrency=2**: один процесс на синк (ЕИС/TenderGuru), один на пользовательские задачи (доки, парсинг)
