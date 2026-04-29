# Tender SaaS — Claude Code Instructions

## Project overview
AI-powered tender discovery platform for Russian public procurement (44-ФЗ, 223-ФЗ).
Stack: Django 5 + DRF · Next.js 14 · Postgres · Qdrant · MinIO · Celery + Redis · Claude API

## Architecture
```
/backend          — Django project
  /apps
    /tenders      — парсинг, модели тендеров
    /search       — embedding, Qdrant интеграция
    /documents    — PDF парсинг, OCR, RAG
    /users        — авторизация, профили компаний
    /billing      — тарифы, ЮКасса
    /alerts       — Celery tasks, Telegram bot
  /config         — settings, urls, celery config
/frontend         — Next.js app
  /app            — App Router pages
  /components     — UI компоненты
  /lib            — API клиент, утилиты
/infra            — docker-compose, nginx, .env.example
```

## MCP Tools

Активные MCP серверы в этом проекте. Используй их проактивно —
не пиши код вслепую если можешь проверить реальное состояние системы.

### postgres-mcp ✓
Прямой доступ к Postgres БД.
```
Когда использовать:
- перед написанием любого Django ORM запроса — проверь реальную схему
- когда нужно проверить что данные сохранились правильно
- когда дебажишь N+1 запросы
```

### qdrant ✓
Доступ к Qdrant векторной БД (http://localhost:6333).
```
Когда использовать:
- проверить что коллекция создана и содержит векторы
- посмотреть payload конкретного вектора
- проверить результаты поиска напрямую

Коллекции проекта:
- tenders       — векторы тендеров (название + описание + ОКПД)
- doc_chunks    — чанки тендерных документов для RAG
```

### sequential-thinking ✓
Claude думает пошагово перед тем как писать код.
```
Когда использовать — ОБЯЗАТЕЛЬНО для:
- проектирования новых модулей (RAG пайплайн, embedding логика)
- архитектурных решений (как структурировать Celery tasks)
- сложных багов которые не очевидны с первого взгляда
- любой задачи где есть несколько подходов

Как вызвать: начни промпт с "Используй sequential thinking. Задача: ..."
```

### filesystem ✓
Чтение и запись файлов проекта.
Путь: /Users/dmitriyshutov/Desktop/tender_pilot
```
Когда использовать:
- читать существующий код перед тем как его менять
- проверять структуру проекта
- писать новые файлы

Правило: всегда читай файл перед редактированием — не пиши вслепую.
```

### memory ✓
Сохраняет важные решения между сессиями.
```
Что сохранять:
- архитектурные решения ("решили использовать chunk_size=512")
- найденные баги и их причины
- договорённости команды по именованию
- нестандартные конфигурации окружения
```

### fetch (опционально)
Чтение внешних URL — документация, API specs.
```
Когда использовать:
- читать документацию ЕИС API
- смотреть актуальные доки LlamaIndex / Qdrant
- проверять формат данных внешних источников
```

## Critical rules — ALWAYS follow

### Перед написанием кода
1. Прочитай существующий файл через filesystem если он уже есть
2. Проверь схему БД через postgres-mcp если пишешь ORM запросы
3. Для сложных задач — сначала sequential thinking, потом код

### Django
- Все API через Django REST Framework, не Django views
- Модели только в /apps/*/models.py, никогда в других файлах
- Бизнес-логику в services.py, не в views и не в models
- Celery tasks в tasks.py, импортировать через app.task декоратор
- Все секреты через os.environ.get(), никогда хардкодить
- Миграции генерировать через python manage.py makemigrations, не вручную
- Типизация везде — использовать type hints

### API design
- REST endpoints: /api/v1/...
- Всегда возвращать {data: ..., error: null} или {data: null, error: "..."}
- Пагинация на всех list endpoints (page_size=20 по умолчанию)
- Аутентификация: JWT Bearer token в заголовке

### AI / ML компоненты
- Все LLM вызовы через backend/apps/documents/llm_client.py — единая точка входа
- Кэшировать результаты LLM в Postgres (поле ai_summary в модели)
- Rate limiting на AI endpoints: max 10 req/min на пользователя
- Логировать все LLM вызовы: токены, время, стоимость
- Embedding модель: multilingual-e5-large (основная), deepvk/USER-bge-m3 (альтернатива)
- Chunk size: 512 токенов, overlap: 50 токенов

### Frontend
- App Router (не Pages Router)
- Компоненты на shadcn/ui — не изобретать велосипед
- Данные через React Query (tanstack/query)
- Типы генерировать из Django DRF схемы

### Что НИКОГДА не делать
- Не писать бизнес-логику в Django views
- Не делать синхронные HTTP запросы внутри Celery tasks
- Не хранить PDF файлы локально — только MinIO
- Не делать N+1 запросы — всегда select_related/prefetch_related
- Не коммитить .env файлы
- Не писать код не прочитав существующий файл

## Key models

```python
Tender: id, number, title, nmck, customer, region, okpd_codes,
        published_at, deadline_at, status, source_url, raw_json, ai_summary

Customer: id, inn, name, region, full_name

Document: id, tender, filename, s3_key, parsed_text, ocr_quality, chunks_indexed

CompanyProfile: id, user, name, inn, description, okved_codes, regions, keywords

TenderMatch: id, profile, tender, score, notified_at

Subscription: id, user, plan (free/solo/team), expires_at
```

## Environment variables
```
DATABASE_URL=postgresql://tender_user:tender_pass@localhost:5432/tenders
QDRANT_URL=http://localhost:6333
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=tender_admin
MINIO_SECRET_KEY=tender_secret_123
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=...
TELEGRAM_BOT_TOKEN=...
YUKASSA_SHOP_ID=...
YUKASSA_SECRET_KEY=...
```

## Commands

### Локальная разработка
```bash
docker compose up -d             # запустить инфраструктуру
cd backend
python manage.py migrate         # применить миграции
python manage.py runserver       # Django dev server
celery -A config worker -l info  # воркер задач
celery -A config beat -l info    # планировщик

cd frontend
npm run dev                      # Next.js dev server
```

### Полезные команды
```bash
python manage.py shell_plus          # Django shell с автоимпортом моделей
python manage.py index_tenders       # переиндексировать тендеры в Qdrant
python manage.py parse_eis --days=7  # спарсить последние 7 дней
```

## Custom commands (.claude/commands/)
```
/new-endpoint       — создать новый Django REST endpoint
/new-celery-task    — создать новую Celery задачу
/debug              — режим отладки: логи + БД + очередь
```

## Current sprint
- [ ] День 1–2: инфраструктура + парсер + загрузка данных
- [ ] День 3: embedding индекс в Qdrant
- [ ] День 4: авторизация + профиль компании
- [ ] День 5: алерты + Telegram bot
- [ ] День 6–7: PDF парсинг + RAG
- [ ] День 8: резюме тендера + аналитика заказчика
- [ ] День 9: черновик заявки
- [ ] День 10: pipeline управление (kanban)
- [ ] День 11–12: монетизация (ЮКасса, тарифы)
- [ ] День 13: стабильность (rate limiting, Sentry)
- [ ] День 14: запуск
