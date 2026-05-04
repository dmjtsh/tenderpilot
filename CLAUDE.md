# Tender SaaS — Claude Code Instructions

## Project overview
AI-powered tender discovery platform for Russian public procurement (44-ФЗ, 223-ФЗ, 615-ПП).
Stack: Django 5 + DRF · Next.js 14 · Postgres · Qdrant · MinIO · Celery + Redis · OpenAI API

## Architecture
```
/backend
  /apps
    /tenders      — парсинг ЕИС, модели тендеров, справочник ОКВЭД, pipeline
    /search       — embedding, Qdrant, HyDE, матчинг
    /documents    — PDF парсинг, RAG, очистка (см. DOCUMENTS_ARCHITECTURE.md)
    /users        — авторизация, CompanyProfile, CompanyDirection
    /billing      — тарифы, ЮКасса (не реализовано)
    /alerts       — Celery tasks, Telegram bot (не реализовано)
  /config         — settings, urls, celery
/frontend
  /app            — Next.js App Router pages
  /components     — UI компоненты
  /lib            — API клиент, типы
  /b_cTFNgcyL3L3  — лендинг (старая копия, не трогать)
/infra            — docker-compose, nginx, .env.example
```

---

## Что сделано

### Бэкенд

- **Парсер ЕИС** (`apps/tenders/eis_client.py`)
  - `search_tenders()` — список тендеров: `--days`, `--fz`, `--query`, `--max-pages`
  - `fetch_tender_detail()` — детальное обогащение одного тендера
  - Команда: `python manage.py parse_eis --days=30 --query="кровля" --enrich`
  - **Важно**: фильтрация по региону через GET НЕ РАБОТАЕТ (AJAX-виджет). Обход: `--query` с ключевым словом региона.

- **Справочник ОКВЭД** (`apps/tenders/okved.py`)
  - `OKVED_NAMES` — dict 2773 кодов
  - `okved_to_text(codes)` — коды → читаемые названия через запятую

- **Семантический поиск** (`apps/search/`)
  - Embedding: `multilingual-e5-large` через fastembed (ONNX, CPU, ~450MB, singleton)
  - `tender_text(tender)` — title + ai_summary + ОКВЭД названия + регион + закон
  - Qdrant коллекция `tenders`, cosine similarity
  - `POST /api/v1/search/` — семантический поиск
  - `GET /api/v1/search/match/` — матчинг под профиль

- **HyDE** (`apps/search/hyde.py`)
  - GPT-4o-mini → 3 текста → усреднение эмбеддингов → profile_vector
  - GPT может возвращать JSON в ```json``` блоке — парсинг обходит это

- **CompanyDirection** (`apps/users/models.py`)
  - okved_codes, keywords, regions, nmck_min/max, law_types
  - content_hash + needs_reindex() для debounce
  - post_save → Celery task rebuild_direction_vector (countdown=30, фиксированный task_id)

- **match_profile** (`apps/search/services.py`)
  - Итерирует по направлениям с profile_vector
  - Payload-фильтры Qdrant: region, nmck, law_type
  - Берёт max score среди направлений, поддерживает direction_ids

- **DaData** (`apps/users/dadata.py`)
  - `enrich_company_by_inn(inn)` → name, region, okved_main, okved_list
  - `POST /api/v1/users/lookup-inn/`
  - Примечание: okveds в DaData часто пустой, только основной ОКВЭД

- **ОКВЭД поиск**: `GET /api/v1/tenders/okved/?q=` — до 20 результатов

- **Авторизация**: JWT, `/api/v1/users/auth/token/`, `/api/v1/users/register/`

- **Модуль documents** (`apps/documents/`) — см. DOCUMENTS_ARCHITECTURE.md
  - TenderDocument модель — хранение файлов, статусы парсинга
  - MinIO интеграция — upload/download/delete
  - Парсеры: pymupdf (PDF), python-docx (DOCX), rarfile/zipfile (архивы)
  - Celery pipeline: download → parse → classify → index → invalidate
  - get_summary_context() — RAG выборка через Qdrant для AI резюме
  - classify_documents_priority() — GPT определяет приоритет по имени файла
  - **TTL-очистка doc_chunks** (`cleanup_doc_chunks`) — каждый час, удаляет чанки из Qdrant + parsed_text из Postgres для тендеров где `docs_indexed_at` старше 48ч (`DOC_CHUNKS_TTL_HOURS=48`)
  - cleanup_old_documents() — Celery beat каждое воскресенье (nuclear: 730 дней, MinIO + записи)
  - **Переиндексация**: `POST /api/v1/tenders/{id}/reindex-docs/` — если parsed_text есть → re-embed, если очищен → re-parse из MinIO

- **AI резюме** (`apps/tenders/services.py`)
  - generate_tender_summary(tender) — GPT-4o-mini с RAG контекстом
  - get_or_create_summary(tender) — кэш в tender.ai_summary
  - Промпт: чеклист по категориям, конкретные значения, универсальный тип
  - Числовые значения копировать ТОЧНО как в документах (не конвертировать)
  - `GET /api/v1/tenders/{id}/summary/`

- **RAG вопросы** (`apps/documents/services.py`)
  - answer_question(tender_id, question) — поиск в doc_chunks + GPT
  - Возвращает полный текст чанков + document_id для цитирования
  - `needs_reindex: true` если доки есть но чанки очищены (TTL) — фронтенд показывает кнопку переиндексации
  - `POST /api/v1/tenders/{id}/ask/`

### Фронтенд

#### Дизайн-система
- **Лендинг** (`/frontend/components/landing/`): белая тема, Stripe/Minerva стиль
- **Приложение** (`/app`): светлая тема, Linear.app стиль
- Tailwind v3 (не v4 — shadcn генерирует v4-синтаксис)
- **Логотип**: `pilot_logo.png` → `/frontend/public/logo.png` + `/frontend/app/icon.png` (favicon с закруглёнными углами через PIL)
- Все логотипы используют `<Image src="/logo.png" className="rounded-xl">` (28x28 основные, 26x26 логин)

#### Цветовая схема приложения
```
Background:  white / gray-50 (#FAFAFA)
Cards:       white, border gray-200
Accent:      violet-600 (#7C3AED) — score, direction badges, кнопки фильтров
Text:        gray-900 (#111827) primary, gray-500 secondary
Direction buttons active: bg-violet-100 border-violet-300 text-violet-800
"Все" button active: bg-[#111827] text-white
```

#### Цветовая схема лендинга (светлая)
```
Background:  white (#FFFFFF)
Cards:       gray-50 (#F9FAFB), border gray-200
Accent:      black (#111827) для кнопок
Text:        gray-900 (primary), gray-500 (secondary)
Highlight:   violet-600 — только для акцентов, не доминирует
```

#### Страницы приложения
- `/login` — авторизация + регистрация
- `/tenders` — лента (табы: Все / Для вас), фильтр по направлениям с violet-кнопками
- `/tenders/[id]` — детальная страница тендера с AI-резюме, документами, RAG-чатом с цитатами
- `/profile` — профиль компании с направлениями, анимация fade-in
- `/pipeline` — kanban-доска тендеров со статусами участия (новый/изучаю/готовлю/подал/выиграл/проиграл)

#### Лендинг (`/frontend/components/landing/`)
- `Navbar` — auth-aware (показывает "Личный кабинет" когда авторизован), breakpoint sm
- `Hero` — staggered `animate-hero` анимации, `hero.png` справа + статистика столбиком слева
- `Features` — scroll-анимации (left/right чередование) через IntersectionObserver
- `FAQ` — оригинальная 2x2 сетка карточек (не стандартный аккордеон), `grid-rows-[1fr]/[0fr]` анимация
- `CTA` — скрывается когда пользователь авторизован
- `Footer` — логотип + ссылки

#### Компоненты
- `TenderCard` — карточка тендера, бейдж matched_direction (violet), score gradient (violet), фиксированные колонки с "—" fallback
- `OkvedCombobox` — топ-20 популярных при открытии, поиск без минимума
- `InnSuggestPanel` — автозаполнение по ИНН + чекбоксы направлений
- `DirectionCard` — форма направления (ОКВЭД, НМЦ presets, 44/223/615)
- `DocumentsBlock` — загрузка документов, polling статусов
- `AiSummaryBlock` — резюме с прогрессом, бейдж "На основе документов"
- `TenderChat` — RAG чат, история в сессии (не в БД)
- `SourceCitation` — цитата из документа в RAG-ответе (expand/collapse, violet border-left)
- `PipelineStatusButtons` — кнопки статусов на странице тендера
- `PipelineKanban` — kanban-доска на странице /pipeline
- `useScrollAnimation` hook — IntersectionObserver для scroll-анимаций лендинга

#### CSS-анимации (`globals.css`)
- `scroll-hidden` / `scroll-visible` — fade-up при скролле
- `scroll-hidden-left` / `scroll-hidden-right` — directional slide-in
- `scroll-hidden-scale` — scale-up при скролле
- `.stagger-1..6` — задержки для каскадных анимаций
- `.animate-hero` — entrance для hero секции
- `.btn-hover-lift` — подъём кнопок при hover
- Глобальный `cursor: pointer` для button/a/[role="button"] (Tailwind v3 preflight fix)
- `@media (prefers-reduced-motion: reduce)` — accessibility

#### Ключевые фиксы — не трогать
- `frontend/app/providers.tsx` — `useState(() => new QueryClient())` намеренно
- `frontend/components/Shell.tsx` — `mounted` state намеренный (hydration fix)
- 401 interceptor только при наличии токена
- Таб "Для вас" персистится в URL (`?tab=match`)
- Cursor pointer через global CSS — Tailwind v3 preflight ставит `cursor: default` на кнопки

### Данные
- ~3400+ тендеров, ~700+ обогащено
- Темы: кровля, благоустройство, капремонт
- Регионы: Дальний Восток (случайная выборка), Самарская обл

---

## Не трогать — работает
- `apps/tenders/eis_client.py` — не рефакторить
- `apps/search/embedder.py` — singleton намеренный (модель ~450MB)
- `frontend/app/providers.tsx` — см. выше
- `frontend/components/Shell.tsx` — см. выше
- Tailwind v3 — не обновлять

---

## MCP Tools

### postgres-mcp ✓
Использовать перед любым ORM запросом — проверить реальную схему.

### qdrant ✓
http://localhost:6333
Коллекции:
- `tenders` — векторы тендеров для матчинга
- `doc_chunks` — RAG чанки документов
  payload: {tender_id, document_id, chunk_index, text, filename, content_priority}
- **mmap включён** для обеих коллекций (memmap_threshold=10000, on_disk HNSW) — векторы на диске, ОС кеширует в RAM

### sequential-thinking ✓
Обязательно для проектирования, архитектурных решений, сложных багов.
Вызов: "Используй sequential thinking. Задача: ..."

### filesystem ✓
`/Users/dmitriyshutov/Desktop/tender_pilot`
Всегда читать файл перед редактированием.

### memory ✓
Сохранять важные архитектурные решения между сессиями.

### fetch (опционально)
Чтение внешних URL — документация, API specs.

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

### Documents (полная архитектура в DOCUMENTS_ARCHITECTURE.md)
- Документы качаются ТОЛЬКО по явному запросу пользователя
- Режим А (резюме): get_summary_context() → RAG через Qdrant doc_chunks
- Режим Б (вопросы): answer_question() → RAG с filter(tender_id)
- SUMMARY_QUERIES универсальные — без привязки к сфере
- document_id в каждом Qdrant payload — для точечного удаления
- Инвалидация ai_summary при новом документе (post_save сигнал)
- ai_summary НЕ удалять при очистке
- **TTL-очистка (48ч)**: cleanup_doc_chunks каждый час — Qdrant doc_chunks + parsed_text. MinIO файлы остаются для re-parse
- **Nuclear-очистка (730 дней)**: cleanup_old_documents — MinIO + записи TenderDocument
- `docs_indexed_at` на Tender — ставится при index_document_chunks, сбрасывается при TTL-очистке

### AI резюме промпт
- Чеклист с □ по категориям
- Числовые значения ТОЧНО как в документах — не конвертировать
- Тип тендера GPT определяет сам
- Обеспечение > 15% → красный флаг с процентом
- source="none" → предупреждение что только метаданные

### Pipeline
- Один статус на пару (user, tender) — unique_together
- Статусы: new / studying / preparing / submitted / won / lost
- Pipeline показывается на странице тендера и на отдельной /pipeline
- Метрика "сумма в работе" — sum НМЦ для статусов studying/preparing/submitted
- Метрика "выиграно" — sum НМЦ для статуса won (для дашборда инвесторов)

### Frontend — дизайн
- Лендинг (`/frontend/components/landing/`): светлая тема, Stripe/Minerva стиль
- Приложение (`/app`): светлая тема, Linear стиль
- При редизайне — брать токены из светлой схемы (white/gray-50/gray-200/violet-600)
- React Query v5: `isLoading = isPending && isFetching`
- Типы из `frontend/lib/api.ts`
- DRF ListCreateAPIView: `r.data.results ?? r.data`
- DocumentsBlock и AiSummaryBlock: один React Query ключ для /docs/

### Никогда
- Бизнес-логику в views
- Синхронные HTTP в Celery tasks
- PDF локально — только MinIO
- N+1 запросы — select_related/prefetch_related
- Коммитить .env
- Писать код не прочитав файл
- Автоматически качать документы при парсинге ЕИС
- Менять тему лендинга на тёмную
- Менять тему приложения на тёмную

---

## Key models

```python
Tender: id, number, title, nmck, customer, region, okpd_codes,
        published_at, deadline_at, auction_date, status,
        law_type, trading_platform, trading_platform_url,
        bid_security_amount, bid_security_required,
        contract_security_amount, contract_security_percent,
        source_url, raw_json, ai_summary, embedding_id,
        docs_indexed_at (nullable — когда чанки проиндексированы)

Customer: id, inn, name, region, full_name

CompanyProfile: id, user, name, inn, description, okved_codes, regions, keywords

CompanyDirection: id, profile, name, okved_codes, keywords,
                  nmck_min, nmck_max, law_types,
                  hyde_texts, profile_vector, content_hash,
                  vector_updated_at, created_at

TenderDocument: id, tender, filename, file_type, s3_key, file_size,
                parent_document (FK self, nullable), archive_path,
                parsed_text, is_scanned, file_hash,
                parse_status (pending/processing/done/failed/skipped/cleaned),
                parse_error, content_priority (0-99),
                created_at, parsed_at

TenderPipeline: id, user, tender, status, notes,
                created_at, updated_at
                # status: new / studying / preparing / submitted / won / lost
                # unique_together: (user, tender)

TenderMatch: id, profile, tender, score, notified_at
Subscription: id, user, plan (free/solo/team), expires_at
```

---

## Environment variables
```
DATABASE_URL=postgresql://tender_user:tender_pass@localhost:5432/tenders
QDRANT_URL=http://localhost:6333
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=tender_admin
MINIO_SECRET_KEY=tender_secret_123
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=...         # HyDE + AI резюме + RAG
DADATA_TOKEN=...           # автозаполнение по ИНН
TELEGRAM_BOT_TOKEN=...
YUKASSA_SHOP_ID=...
YUKASSA_SECRET_KEY=...
```

---

## Commands

```bash
# Инфраструктура
docker compose up -d

# Бэкенд
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8080
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/celery -A config worker -l info

# Фронтенд
cd frontend && npm run dev

# Парсинг
python manage.py parse_eis --days=30 --query="кровля" --max-pages=20 --enrich

# Индексация тендеров в Qdrant
python manage.py index_tenders

# Принудительная переиндексация направлений
python manage.py shell -c "
from apps.search.tasks import rebuild_direction_vector
from apps.users.models import CompanyDirection
for d in CompanyDirection.objects.filter(profile_vector__isnull=True):
    rebuild_direction_vector(d.id)
    print(f'rebuilt {d.id} {d.name}')
"

# Обогащение тендеров без Celery
python manage.py shell -c "
import time
from apps.tenders.models import Tender
from apps.tenders.eis_client import fetch_tender_detail
from apps.tenders.services import upsert_tender
for pk, num, url in Tender.objects.filter(trading_platform='').values_list('pk','number','source_url'):
    d = fetch_tender_detail(num, url)
    if d: d['raw_json']=d.copy(); upsert_tender(d)
    time.sleep(0.4)
"
```

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

### Сделано
- [x] Справочник ОКВЭД (2773 кода)
- [x] Обогащённый tender_text()
- [x] CompanyDirection + HyDE + debounce
- [x] Payload фильтры Qdrant (НМЦ, регион, закон)
- [x] Фронт — направления, ОКВЭД combobox, НМЦ presets
- [x] DaData автозаполнение по ИНН
- [x] Фильтр по направлениям в "Для вас"
- [x] TenderDocument модель + MinIO + парсеры PDF/DOCX/RAR/ZIP
- [x] Celery pipeline: download → parse → classify → index → invalidate
- [x] AI резюме с RAG контекстом (GPT-4o-mini)
- [x] DocumentsBlock + AiSummaryBlock на странице тендера
- [x] RAG чат по тендеру (TenderChat)
- [x] Очистка старых документов (Celery beat)
- [x] Лендинг белая тема (Stripe/Minerva стиль)
- [x] Редизайн фильтра направлений (violet кнопки, "Все" toggle)
- [x] Связка лендинг ↔ приложение (CTA → /login, auth-aware navbar)
- [x] Scroll-анимации лендинга
- [x] Hero, FAQ редизайн
- [x] RAG цитаты: SourceCitation
- [x] Логотип pilot_logo.png + favicon
- [x] TTL-очистка doc_chunks (48ч) + mmap для Qdrant
- [x] Эндпоинт переиндексации документов

### Приоритет 1 — до первых пользователей
- [x] Pipeline тендеров (kanban + статусы участия)
- [ ] Обратный отсчёт дедлайна в TenderCard
- [ ] Telegram bot алерты
- [ ] Монетизация (ЮКасса) — free/solo/team

### Приоритет 2 — после первых платящих
- [ ] Карточка заказчика (история победителей, бенчмарки) — данные из ЕИС
- [ ] Мониторинг изменений документов (file_hash + diff)
- [ ] Bidding outcomes tracking (расширение Pipeline для аналитики)
- [ ] Rate limiting на AI endpoints + Sentry
- [ ] Cross-encoder reranking
- [ ] OCR для сканированных PDF

### Приоритет 3 — по фидбеку
- [ ] Черновик заявки (LLM)
- [ ] Сохранённые поисковые запросы
- [ ] Фильтры в UI: площадка, дата торгов
